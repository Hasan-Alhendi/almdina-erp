"""Whole guest groups repair the first-fit trap without relaxing geometry."""
from copy import deepcopy
from collections import Counter
import time
import pytest

from almdina_erp.almdina_erp.domain.cutting import shape_aware_nesting as shape
from almdina_erp.almdina_erp.domain.cutting.corner_frame_search import guest_row_blocks,corner_frames,refine_corner_layout
from almdina_erp.almdina_erp.domain.cutting.primitives import expand_piece_groups
from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import material_outline_cm
from almdina_erp.almdina_erp.domain.cutting.evaluation import placement_permission_errors


def source_rows(rotation=True):
    return [dict(width_cm=59.9,length_cm=70,piece_type='Clipped Corner',qty=2,
                 clipped_corner_position='Bottom Left',clipped_corner_width_cm=cut,
                 clipped_corner_length_cm=cut+10,allow_rotation=1,piece_instance_id=f'corner:{cut}') for cut in (33,30)]+[
        dict(width_cm=w,length_cm=40,piece_type='Regular',qty=5,allow_rotation=int(rotation),piece_instance_id=f'guest:{w}') for w in (5.9,11.9)]


def test_mixed_guest_row_escapes_native_first_fit_trap_and_keeps_real_kerf():
    sources=expand_piece_groups(source_rows())
    original=deepcopy(sources)
    block=shape._take_quad(sources[:4],122,244,.5,mirroring_allowed=True)['block']
    legacy=shape._seat_void_guests([block],sources,.5,122,244,mirroring_allowed=True,
        hosted=set(),quarter_turns_only=True,contact_anchors=True,area_first=True,deadline=time.monotonic()+1)
    assert len(legacy[0]['guests'])==1  # The existing failure, not a changed expectation.
    proposals=guest_row_blocks(block,sources,.5,122,244,deadline=time.monotonic()+2)
    assert proposals and max(len(b['guests']) for b in proposals)>=3
    assert any(len({p['source_piece_no'] for p in b['guests']})>1 for b in proposals)
    for b in proposals:
        ids=[p['piece_instance_id'] for p in b['pieces']]
        assert len(ids)==len(set(ids))
        for i,p in enumerate(b['pieces']):
            assert shape._clears(material_outline_cm(p),b['pieces'][:i],.5)
        assert not placement_permission_errors(dict(sheets=[dict(pieces=b['pieces'])]),sources,mirroring_allowed=True)
    assert sources==original


def test_guest_rotation_permissions_and_deadline():
    sources=expand_piece_groups(source_rows(False))
    block=shape._take_quad(sources[:4],122,244,.5,mirroring_allowed=True)['block']
    assert guest_row_blocks(block,sources,.5,122,244,deadline=time.monotonic()-1)==[]
    proposals=guest_row_blocks(block,sources,.5,122,244,deadline=time.monotonic()+2)
    assert proposals
    assert all(not p['rotated'] for b in proposals for p in b['guests'])


@pytest.mark.parametrize('mirror',[False,True])
def test_fresh_frames_cover_every_corner_once_and_never_reuse_guests(mirror):
    sources=expand_piece_groups(source_rows())
    template=dict(sheets=[dict(sheet_no=i+1,w=122,h=244,pieces=[]) for i in range(3)],unplaced=[])
    original=deepcopy((template,sources))
    frames=list(corner_frames(template,sources,122,244,.5,deadline=time.monotonic()+2,
                              mirroring_allowed=mirror,limit=4))
    for f in frames:
        parts=[p for s in f['sheets'] for p in s['pieces']]
        assert len(parts)==len({p['piece_instance_id'] for p in parts})
        assert Counter(p['id'] for p in parts if p['piece_type']=='Clipped Corner')==Counter(p['id'] for p in sources[:4])
        assert not placement_permission_errors(f,sources,mirroring_allowed=mirror)
    assert (template,sources)==original


def test_unsupported_corner_stage_returns_the_untouched_baseline():
    sources=expand_piece_groups(source_rows())
    template=dict(sheets=[dict(w=122,h=244,pieces=[])],unplaced=[])
    before=deepcopy((template,sources))
    values,trace=refine_corner_layout(template,[],sources,122,244,.5,deadline=time.monotonic()+1,
        machine_type='Panel Saw',mirroring_allowed=True,metric_kwargs={},row_solver=lambda:None)
    assert values==[template] and trace['stop']=='unsupported_or_expired'
    assert (template,sources)==before


def test_repeated_guest_bundle_is_not_starved_by_larger_single_rows():
    rows=[dict(width_cm=58,length_cm=77.9,piece_type='L-Shaped Corner',qty=4,
        clipped_corner_position='Bottom Left',clipped_corner_width_cm=39.1,
        clipped_corner_length_cm=48.1,allow_rotation=1,piece_instance_id='host'),
        dict(width_cm=29.9,length_cm=74.8,piece_type='Regular',qty=4,allow_rotation=1,piece_instance_id='repeated'),
        dict(width_cm=39.9,length_cm=74.8,piece_type='Regular',qty=1,allow_rotation=1,piece_instance_id='large')]
    sources=expand_piece_groups(rows)
    block=shape._take_quad(sources[:4],122,244,.5,mirroring_allowed=True)['block']
    choices=guest_row_blocks(block,sources,.5,122,244,deadline=time.monotonic()+1,limit=1)
    assert choices and len(choices[0]['guests'])==3
    assert all(p['source_piece_no']==2 for p in choices[0]['guests'])


def test_application_corner_stage_preserves_baseline_on_exception(monkeypatch):
    from dataclasses import replace
    from almdina_erp.tests.test_compound_layout_refinement import spread_case
    from almdina_erp.tests.test_alns_recalculation import command,FrozenEngine
    from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import BoardGeometry,optimize_order_plan
    from almdina_erp.almdina_erp.domain.cutting import corner_frame_search
    rows,_,plan=spread_case()
    cmd=command(rows,seconds=0,mirror=True)
    cmd=replace(cmd,board=BoardGeometry(13,13,0,.5))
    original=optimize_order_plan(cmd,engine=FrozenEngine(plan))
    def failed(*a,**kw):raise RuntimeError('solver unavailable')
    monkeypatch.setattr(corner_frame_search,'refine_corner_layout',failed)
    changed=optimize_order_plan(replace(cmd,optimizer=replace(cmd.optimizer,corner_search_budget_sec=100)),engine=FrozenEngine(plan))
    assert changed.snapshot['sheets']==original.snapshot['sheets']
    assert changed.snapshot['smart_search']['corner_search']['stop']=='refinement_error'
    assert changed.snapshot['smart_search']['corner_search']['budget_sec']==5


def test_cut_work_is_an_optional_numeric_nomination_and_keeps_legacy_height_objective():
    from almdina_erp.almdina_erp.domain.cutting.pattern_master import ShelfColumn
    from almdina_erp.almdina_erp.infrastructure.cutting.pattern_solver import solve_shelf_master
    columns=((ShelfColumn((1,),2,10),ShelfColumn((1,),3,1)),)
    args=(columns,(1,),(3,),(0,),(False,),0,3)
    old=solve_shelf_master(*args,deadline=time.monotonic()+1)
    new=solve_shelf_master(*args,deadline=time.monotonic()+1,cut_work=True)
    assert old.allocations==((1,0),)
    assert new.allocations==((0,1),)


def test_contact_repair_uses_right_hand_kerf_anchor_after_a_first_placement():
    from almdina_erp.almdina_erp.domain.cutting.corner_frame_search import _contact_repair
    from almdina_erp.almdina_erp.domain.cutting.same_count_layout_search import _cache
    from almdina_erp.almdina_erp.domain.cutting.primitives import make_placed_piece
    from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan
    sources=expand_piece_groups([dict(width_cm=3,length_cm=10,qty=1,piece_instance_id='fixed'),
        dict(width_cm=2,length_cm=5,qty=2,piece_instance_id='repair')])
    sheet=dict(sheet_no=1,w=10,h=10,pieces=[make_placed_piece(sources[0],7,0,3,10,False)])
    _cache(sheet,.5)
    trial=dict(sheets=[sheet],unplaced=[])
    assert _contact_repair(trial,sources,{2,3},(0,),.5,time.monotonic()+1,fixed_axes=True)
    assert sorted(p['x'] for p in sheet['pieces'] if p['id']!=1)==[2.,4.5]
    assert not validate_plan(trial,sources,10,10,kerf_cm=.5)


def test_coupled_guest_material_survives_real_js_and_strict_roundtrip(tmp_path):
    from almdina_erp.almdina_erp.domain.cutting.primitives import make_placed_piece
    from almdina_erp.almdina_erp.domain.cutting.optimizer import enrich_plan_metrics
    from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
        BoardGeometry,OptimizerOptions,OptimizeOrderPlanCommand,optimize_order_plan)
    from almdina_erp.tests.test_alns_recalculation import FrozenEngine
    from almdina_erp.tests.test_cutting_industrial_gaps import export_real_js
    from almdina_erp.tests.test_smart_cutting_manufacturing import import_saved_plan
    rows=[dict(row,piece_instance_id=f'smart:{i}') for i,row in enumerate(source_rows(),1)]
    sources=expand_piece_groups(rows)
    block=shape._take_quad(sources[:4],122,244,.5,mirroring_allowed=True)['block']
    bundle=guest_row_blocks(block,sources,.5,122,244,deadline=time.monotonic()+2,limit=1)[0]
    pieces=deepcopy(bundle['pieces'])
    used={p['id'] for p in pieces}
    x=0.
    for p in sources:
        if p['id'] not in used:
            pieces.append(make_placed_piece(p,x,141,p['width_cm'],p['length_cm'],False))
            x+=p['width_cm']+.5
    native=enrich_plan_metrics(dict(sheets=[dict(sheet_no=1,w=122,h=244,pieces=pieces)],unplaced=[]),
        'MaxRects Contact Point','CNC Router')
    native.update(kerf_cm=.5,machine_type='CNC Router')
    command=OptimizeOrderPlanCommand('coupled-test','coupled-test',BoardGeometry(122,244,0,.5),
        OptimizerOptions('smart','CNC Router',.1,40,30,30,.09,alignment_search_budget_sec=0),
        tuple(rows),allow_piece_mirroring=True)
    outcome=optimize_order_plan(command,engine=FrozenEngine(native))
    assert outcome.snapshot['validation']['is_valid']
    imported=import_saved_plan(outcome.snapshot,rows,export_real_js(outcome.snapshot,tmp_path))
    import json
    (tmp_path/'before.json').write_text(json.dumps(outcome.snapshot),encoding='utf-8')
    (tmp_path/'after.json').write_text(json.dumps(imported),encoding='utf-8')
    from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import parse_geometry_mm,geometry_mm_to_cm
    # Imported snapshots own explicit geometry.outer in mm; source corner
    # fields are not the authority for their physical placed outline.
    outer=lambda p:(geometry_mm_to_cm(parse_geometry_mm(p['geometry'])).outer if p.get('geometry') else material_outline_cm(p))
    polygons=lambda plan:sorted(tuple(sorted((round(x,4),round(y,4)) for x,y in
        outer(p))) for s in plan['sheets'] for p in s['pieces'])
    assert polygons(imported)==polygons(outcome.snapshot)
    assert sorted(p['piece_instance_id'] for s in imported['sheets'] for p in s['pieces'])==sorted(p['piece_instance_id'] for p in sources)
