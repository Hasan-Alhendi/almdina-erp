"""Synthetic witnesses for coupled shape/guest/family repair and rigid contact."""
from copy import deepcopy
import time

import pytest

from almdina_erp.almdina_erp.domain.cutting import system_layout_refinement as refinement
from almdina_erp.almdina_erp.domain.cutting import shape_aware_nesting as shape
from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import final_system_sort_keys, plan_cut_line_quality
from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan, placement_permission_errors
from almdina_erp.almdina_erp.domain.cutting.optimizer import enrich_plan_metrics
from almdina_erp.almdina_erp.domain.cutting.primitives import expand_piece_groups, make_placed_piece
from almdina_erp.almdina_erp.domain.cutting.rigid_layout_refinement import improve_rigid_contacts
from almdina_erp.almdina_erp.domain.cutting.same_count_layout_search import material_signature

METRICS = dict(min_remnant_width_cm=1, min_remnant_length_cm=1, min_remnant_area_m2=.0001)


def corner_rows(rotation=True):
    return [dict(width_cm=6, length_cm=6, qty=4, allow_rotation=rotation,
        piece_type='L-Shaped Corner', clipped_corner_position='Top Right',
        clipped_corner_width_cm=4, clipped_corner_length_cm=4, piece_instance_id='smart:1'),
        dict(width_cm=2, length_cm=2, qty=4, allow_rotation=rotation,
             piece_type='Regular', piece_instance_id='smart:2')]


def spread_case(rotation=True):
    rows = corner_rows(rotation)
    sources = expand_piece_groups(rows)
    sheets = [dict(sheet_no=i+1, w=13, h=13, pieces=[
        shape._placed_corner(sources[i], x_cm=0, y_cm=0, mirrored=False, turns=0),
        make_placed_piece(sources[4+i], 7, 0, 2, 2, False)]) for i in range(4)]
    plan = enrich_plan_metrics(dict(sheets=sheets, unplaced=[]), 'MaxRects Contact Point','CNC Router', **METRICS)
    plan.update(kerf_cm=.5, machine_type='CNC Router')
    assert not validate_plan(plan, sources, 13, 13, kerf_cm=.5)
    return rows, sources, plan


@pytest.mark.parametrize('mirror', [False, True])
def test_compound_repair_can_remove_boards_with_original_shape_and_guest_instances(mirror):
    _, sources, plan = spread_case()
    before = deepcopy((plan, sources))
    candidates, trace = refinement.refine_system_layout(plan, sources, 13, 13, .5,
        deadline=time.monotonic()+3, machine_type='CNC Router', mirroring_allowed=mirror,
        metric_kwargs=METRICS)
    assert trace['skeletons'] > 0
    assert min(len(p['sheets']) for p in candidates) == 1
    assert candidates[0] == plan
    for trial in candidates:
        assert not validate_plan(trial, sources, 13, 13, kerf_cm=.5)
        assert not placement_permission_errors(trial, sources, mirroring_allowed=mirror)
        assert sorted(p['piece_instance_id'] for s in trial['sheets'] for p in s['pieces']) == sorted(p['piece_instance_id'] for p in sources)
    assert (plan, sources) == before


def test_forbidden_turns_are_not_used_by_rotated_blocks():
    _, sources, plan = spread_case(rotation=False)
    candidates, _ = refinement.refine_system_layout(plan, sources, 13, 13, .5,
        deadline=time.monotonic()+1, machine_type='CNC Router', mirroring_allowed=False,
        metric_kwargs=METRICS)
    for trial in candidates:
        assert not placement_permission_errors(trial, sources, mirroring_allowed=False)
        assert not validate_plan(trial, sources, 13, 13, kerf_cm=.5)


@pytest.mark.parametrize('marker', ['Panel Saw', 'sheet_offcut', 'source_offcut'])
def test_unsupported_resource_or_machine_never_reaches_skeleton_construction(monkeypatch, marker):
    _, sources, plan = spread_case()
    if marker == 'sheet_offcut':
        plan['sheets'][0]['resource_kind'] = 'OFFCUT'
    if marker == 'source_offcut':
        sources[0]['resource_kind'] = 'OFFCUT'
    monkeypatch.setattr(refinement, '_skeletons', lambda *a: pytest.fail('Unsupported skeleton'))
    candidates, trace = refinement.refine_system_layout(plan, sources, 13, 13, .5,
        deadline=time.monotonic()+1, machine_type='Panel Saw' if marker=='Panel Saw' else 'CNC Router',
        mirroring_allowed=True, metric_kwargs=METRICS)
    assert candidates == [plan] and trace['stop'] == 'unsupported_or_expired'


def test_expired_stage_cannot_start_compound_work(monkeypatch):
    _, sources, plan = spread_case()
    monkeypatch.setattr(refinement, 'improve_fixed_board_layout', lambda *a, **kw: pytest.fail('Expired stage'))
    result, _ = refinement.refine_system_layout(plan, sources, 13, 13, .5,
        deadline=time.monotonic()-1, machine_type='CNC Router', mirroring_allowed=True,
        metric_kwargs=METRICS)
    assert result == [plan]


def test_large_guest_preference_is_an_ordered_proposal_not_a_fake_piece():
    rows = [corner_rows()[0], dict(width_cm=7, length_cm=3, qty=1, allow_rotation=True, piece_type='Regular'),
            dict(width_cm=3, length_cm=3, qty=4, allow_rotation=True, piece_type='Regular')]
    sources = expand_piece_groups(rows)
    blocks = shape._cluster_sheet(sources,13,13,.5,mirroring_allowed=True,
                                 deadline=time.monotonic()+2,formation_alternatives=True)[0]
    kwargs = dict(mirroring_allowed=True,hosted=set(),quarter_turns_only=True,deadline=time.monotonic()+2)
    normal = shape._seat_void_guests(blocks,sources,.5,13,13,**kwargs)
    preferred = shape._seat_void_guests(blocks,sources,.5,13,13,preferred_guest_ids=frozenset({5}),**kwargs)
    normal_guests = [p for b in normal for p in b['guests']]
    preferred_guests = [p for b in preferred for p in b['guests']]
    assert len(normal_guests) == 4 and 5 not in {p['id'] for p in normal_guests}
    assert 5 in {p['id'] for p in preferred_guests}
    assert all(p['id'] in {s['id'] for s in sources} for p in preferred_guests)
    assert len({p['id'] for b in preferred for p in b['pieces']}) == sum(len(b['pieces']) for b in preferred)


def test_rigid_contact_moves_a_complete_nest_and_shortens_its_actual_network():
    rows = [dict(width_cm=6,length_cm=6,qty=1,piece_type='L-Shaped Corner',allow_rotation=0,
        clipped_corner_position='Top Right',clipped_corner_width_cm=3,clipped_corner_length_cm=3),
        dict(width_cm=2,length_cm=2,qty=1,piece_type='Regular',allow_rotation=0),
        dict(width_cm=2,length_cm=3,qty=1,piece_type='Regular',allow_rotation=0),
        dict(width_cm=1,length_cm=1,qty=1,piece_type='Regular',allow_rotation=0)]
    rows = [dict(r,piece_instance_id=f'smart:{i}') for i,r in enumerate(rows,1)]
    sources = expand_piece_groups(rows)
    sheets = [dict(sheet_no=1,w=12,h=12,pieces=[
        shape._placed_corner(sources[0],x_cm=1,y_cm=1,mirrored=False,turns=0),
        make_placed_piece(sources[1],4.5,1.5,2,2,False),
        make_placed_piece(sources[2],7.5,4.3,2,3,False)]),
        dict(sheet_no=2,w=12,h=12,pieces=[make_placed_piece(sources[3],0,0,1,1,False)])]
    plan=enrich_plan_metrics(dict(sheets=sheets,unplaced=[]),'MaxRects Contact Point','CNC Router',**METRICS)
    plan.update(kerf_cm=.5,machine_type='CNC Router')
    assert not validate_plan(plan,sources,12,12,kerf_cm=.5)
    original=deepcopy(plan)
    result,trace=improve_rigid_contacts(plan,sources,12,12,.5,deadline=time.monotonic()+3,
        machine_type='CNC Router',mirroring_allowed=False,metric_kwargs=METRICS)
    assert trace['improvements'] > 0
    assert plan_cut_line_quality(result,.5)[0] < plan_cut_line_quality(plan,.5)[0]
    assert not validate_plan(result,sources,12,12,kerf_cm=.5)
    assert not placement_permission_errors(result,sources,mirroring_allowed=False)
    before={p['id']:p for s in plan['sheets'] for p in s['pieces']}
    after={p['id']:p for s in result['sheets'] for p in s['pieces']}
    assert after[1]['x']-before[1]['x'] == pytest.approx(after[2]['x']-before[2]['x'])
    assert after[1]['y']-before[1]['y'] == pytest.approx(after[2]['y']-before[2]['y'])
    assert result['sheets'][1] == plan['sheets'][1]
    assert plan == original


@pytest.mark.parametrize('rotation', [False, True])
def test_remnant_board_repack_obeys_rotation_and_discovers_a_shorter_strip(rotation):
    from almdina_erp.almdina_erp.domain.cutting.same_count_layout_search import (
        improve_fixed_board_layout, FixedBoardSearchPolicy)
    sources = expand_piece_groups([
        dict(width_cm=2.7,length_cm=3,qty=2,piece_type='Regular',allow_rotation=rotation,piece_instance_id='small'),
        dict(width_cm=11.5,length_cm=23.5,qty=1,piece_type='Regular',allow_rotation=0,piece_instance_id='large')])
    sheets = [dict(sheet_no=1,w=12,h=24,pieces=[
        make_placed_piece(sources[0],0,0,2.7,3,False),make_placed_piece(sources[1],3.2,0,2.7,3,False)]),
        dict(sheet_no=2,w=12,h=24,pieces=[make_placed_piece(sources[2],0,0,11.5,23.5,False)])]
    plan = enrich_plan_metrics(dict(sheets=sheets,unplaced=[]),'MaxRects Contact Point','CNC Router',**METRICS)
    plan.update(kerf_cm=.5,machine_type='CNC Router')
    candidates,trace=improve_fixed_board_layout(plan,sources,12,24,.5,deadline=time.monotonic()+2,
        metric_kwargs=METRICS,policy=FixedBoardSearchPolicy(operators=('owner_repack',),max_attempts=16))
    best=max(p['industrial_metrics']['largest_reusable_free_area_m2'] for p in candidates)
    if rotation:
        assert best > plan['industrial_metrics']['largest_reusable_free_area_m2']
    else:
        assert best == plan['industrial_metrics']['largest_reusable_free_area_m2']
    for p in candidates:
        assert len(p['sheets']) == 2
        assert not validate_plan(p,sources,12,24,kerf_cm=.5)
        assert not placement_permission_errors(p,sources,mirroring_allowed=False)
