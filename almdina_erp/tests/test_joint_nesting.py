"""Smart must discover joint nests from source pieces, never merged coordinates."""
from copy import deepcopy
import time

import pytest

from almdina_erp.almdina_erp.domain.cutting import optimizer as opt
from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan, placement_permission_errors
from almdina_erp.almdina_erp.domain.cutting.primitives import expand_piece_groups
from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import geometry_signature
from almdina_erp.tests.joint_nesting_cases import CASES, source_rows


def run(name, *, budget=2, kerf=.3, machine="CNC Router", rotate=None, mirror=False):
    width, height, _, _ = CASES[name]
    rows = source_rows(name)
    if rotate is not None:
        for row in rows:
            row['allow_rotation'] = rotate
    pieces = expand_piece_groups(rows)
    plan = opt.smart_search(pieces, width, height, kerf, machine_type=machine,
                            time_limit_sec=budget, mirroring_allowed=mirror)
    for candidate in plan['smart_candidates']:
        assert not validate_plan(candidate, pieces, width, height, kerf_cm=kerf)
        assert not placement_permission_errors(candidate, pieces, mirroring_allowed=mirror)
    assert len({geometry_signature(p) for p in plan['smart_candidates']}) == len(plan['smart_candidates'])
    return pieces, plan


@pytest.mark.parametrize("name", ["P4-independent", "P4-dependent"])
def test_smart_discovers_one_board_joint_plan_from_sources(name):
    pieces, plan = run(name)
    assert len(plan['sheets']) == 1
    assert any(p.get('glass_host_piece_id') for s in plan['sheets'] for p in s['pieces'])
    assert (plan.get('shape_nesting_diagnostics') or {}).get('void_guests')
    assert {p['id'] for s in plan['sheets'] for p in s['pieces']} == {p['id'] for p in pieces}


def test_joint_board_saving_beats_both_separate_searches(monkeypatch):
    from almdina_erp.almdina_erp.domain.cutting import glass_opening_nesting as glass
    from almdina_erp.almdina_erp.domain.cutting import shape_aware_nesting as shape
    _, joint = run('P4-independent')
    for module, name in [(glass, 'nest_glass_openings'), (shape, 'apply_shape_aware_nesting')]:
        with monkeypatch.context() as patcher:
            patcher.setattr(module, name, lambda plan, *args, **kw: deepcopy(plan))
            _, separate = run('P4-independent')
            assert len(joint['sheets']) < len(separate['sheets'])


def test_joint_is_not_forced_when_glass_only_saves_a_board():
    _, plan = run('P4-joint-not-best')
    assert len(plan['sheets']) == 1
    assert tuple(plan['industrial_rank']) == min(tuple(p['industrial_rank']) for p in plan['smart_candidates'])


@pytest.mark.parametrize('name', ['P4-competing', 'P4-clipped', 'P4-regular'])
def test_mixed_sources_keep_complete_identity_and_supported_rotations(name):
    _, plan = run(name)
    assert all(abs(float(p.get('placement_rotation_deg') or 0) % 90) < 1e-6
               for c in plan['smart_candidates'] for s in c['sheets'] for p in s['pieces'])


@pytest.mark.parametrize('kerf', [0, .3])
def test_joint_physics_and_rotation_denial_are_not_relaxed(kerf):
    run('P4-independent', kerf=kerf)
    pieces, plan = run('P4-independent', kerf=kerf, rotate=0)
    assert not placement_permission_errors(plan, pieces, mirroring_allowed=False)


def test_joint_mirroring_is_available_only_when_the_order_permits_it():
    pieces, plan = run('P4-independent', mirror=True)
    assert len(plan['sheets']) == 1
    assert not placement_permission_errors(plan,pieces,mirroring_allowed=True)


@pytest.mark.parametrize('name,machine', [('P4-regular','CNC Router'), ('P4-independent','Panel Saw')])
def test_joint_search_is_not_started_without_permitted_opportunities(name, machine, monkeypatch):
    from almdina_erp.almdina_erp.domain.cutting import joint_nesting
    monkeypatch.setattr(joint_nesting, 'joint_nesting_candidates', lambda *a, **kw: pytest.fail('unnecessary joint search'))
    run(name, machine=machine)


def test_selection_keeps_the_proven_guest_host_mapping(monkeypatch):
    from almdina_erp.almdina_erp.domain.cutting import glass_opening_nesting as glass
    pieces = expand_piece_groups(source_rows('P4-independent'))
    plan = opt.auto_fast(pieces, 80.6, 40.3, .3)
    records = []
    guests = glass._select_guests(pieces, glass._openings(plan, .3), .3, assignment_records=records)
    source = glass._without_guests(plan, {p['id'] for p in guests})
    monkeypatch.setattr(glass, '_assign_into_openings', lambda *a, **kw: pytest.fail('proven assignment recomputed'))
    result = glass._place_guests(source, guests, .3, assignments=records)
    links = {int(p['id']): p.get('glass_host_piece_id') for s in result['sheets'] for p in s['pieces']}
    assert all(links[a['guest']['id']] == a['opening']['host_id'] for a in records)
    assert not validate_plan(result, pieces, 80.6, 40.3, kerf_cm=.3)


def test_competing_guest_is_reassigned_to_glass_and_shape_gets_the_alternative():
    from almdina_erp.almdina_erp.domain.cutting.shape_aware_nesting import apply_shape_aware_nesting
    from almdina_erp.almdina_erp.domain.cutting.joint_nesting import joint_nesting_candidates
    width,height,_,_ = CASES['P4-competing']
    pieces = expand_piece_groups(source_rows('P4-competing'))
    baseline = opt.auto_fast(pieces,width,height,.3)
    metric_kwargs = dict(min_remnant_width_cm=30,min_remnant_length_cm=30,min_remnant_area_m2=.09)
    shape = apply_shape_aware_nesting(deepcopy(baseline),pieces,width,height,.3,
        machine_type='CNC Router',mirroring_allowed=False,time_limit_sec=2,**metric_kwargs)
    assert shape['shape_nesting_diagnostics']['void_guests'] == [6]
    candidates,diagnostic = joint_nesting_candidates(baseline,shape,pieces,width,height,.3,
        machine_type='CNC Router',mirroring_allowed=False,deadline=time.monotonic()+2,metric_kwargs=metric_kwargs)
    assert diagnostic['guest_reassignments'] > 0
    assert diagnostic['joint_candidates_generated'] <= 12
    assert len(candidates) <= 4
    assert any(7 in (p.get('shape_nesting_diagnostics') or {}).get('void_guests', [])
               and any(x['id']==6 and x.get('glass_host_piece_id')==1 for s in p['sheets'] for x in s['pieces'])
               for p in candidates)


def test_expired_joint_budget_cannot_mutate_or_replace_the_incumbent():
    from almdina_erp.almdina_erp.domain.cutting.joint_nesting import joint_nesting_candidates
    pieces = expand_piece_groups(source_rows('P4-independent'))
    baseline = opt.auto_fast(pieces,80.6,40.3,.3)
    original = deepcopy(baseline)
    candidates,diagnostic = joint_nesting_candidates(baseline,baseline,pieces,80.6,40.3,.3,
        machine_type='CNC Router',mirroring_allowed=False,deadline=time.monotonic()-1,metric_kwargs={})
    assert candidates == [] and diagnostic['joint_candidates_generated'] == 0
    assert baseline == original


def test_release_is_isolated_and_preserves_the_glass_subtree():
    from almdina_erp.almdina_erp.domain.cutting.joint_nesting import _release_guest
    pieces, plan = run('P4-dependent')
    before = deepcopy(plan)
    # Root Glass 1 owns small guest 6; release its shape relation as a unit.
    result = _release_guest(plan, 1, 100.3, 100.3, .3, time.monotonic()+1)
    assert plan == before
    assert not validate_plan(result, pieces, 100.3, 100.3, kerf_cm=.3)
    original = {p['id']: p for s in plan['sheets'] for p in s['pieces']}
    changed = {p['id']: p for s in result['sheets'] for p in s['pieces']}
    assert changed[6]['glass_host_piece_id'] == 1
    assert changed[6]['x']-changed[1]['x'] == pytest.approx(original[6]['x']-original[1]['x'])
    assert changed[6]['y']-changed[1]['y'] == pytest.approx(original[6]['y']-original[1]['y'])
    assert all(changed[i] == original[i] for i in original if i not in {1,6})


@pytest.mark.parametrize('name', ['P4-independent', 'P4-clipped', 'P4-dependent', 'P4-addon-guard', 'P4-mixed'])
def test_joint_portfolio_json_reload_exports_and_strictly_imports(name, tmp_path):
    import json
    from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
        BoardGeometry, OptimizeOrderPlanCommand, OptimizerOptions, optimize_order_plan)
    from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import domain_cutting_engine
    from almdina_erp.tests.test_smart_cutting_manufacturing import import_saved_plan, rows_with_identity
    from almdina_erp.tests.test_cutting_industrial_gaps import export_real_js
    width,height,trim,_ = CASES[name]
    rows = rows_with_identity(source_rows(name))
    outcome = optimize_order_plan(OptimizeOrderPlanCommand(engine_version='joint-test', input_fingerprint='joint-test',
        board=BoardGeometry(width,height,trim,.3), optimizer=OptimizerOptions('smart','CNC Router',4 if name == 'P4-mixed' else 2,20,30,30,.09),
        piece_rows=tuple(rows)), engine=domain_cutting_engine)
    if name != 'P4-addon-guard':
        assert len(outcome.snapshot['sheets']) == 1
    for snapshot in outcome.candidate_snapshots:
        reloaded = json.loads(json.dumps(snapshot))
        imported = import_saved_plan(reloaded, rows, export_real_js(reloaded, tmp_path))
        assert sum(len(s['pieces']) for s in imported['sheets']) == sum(r['qty'] for r in rows)


def test_glass_machining_guest_is_not_certified_with_ambiguous_overlay_ownership():
    from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import manufacturing_export_rejection
    _, plan = run('P4-addon-guard')
    assert all(not manufacturing_export_rejection(p) for p in plan['smart_candidates'])
    assert all(not p.get('glass_host_piece_id') for c in plan['smart_candidates']
               for s in c['sheets'] for p in s['pieces'] if p.get('extra_back_groove'))


@pytest.mark.parametrize('name', ['P4-independent', 'P4-clipped', 'P4-dependent'])
def test_native_layout_reader_and_export_rebuild_preserve_recorded_corner_transforms(name):
    from almdina_erp.tests.test_glass_opening_nesting import _cutting_plan_for_layout, _reload_export_snapshot
    pieces, plan = run(name)
    assert len(plan['sheets']) == 1
    issues,_,_ = _cutting_plan_for_layout(plan['sheets'][0]['pieces'],kerf_mm=3)
    assert not issues
    width,height,_,_ = CASES[name]
    # This legacy single-sheet fixture writes its child/source rows as sheet 1.
    persisted = deepcopy(plan)
    persisted['sheets'][0]['sheet_no'] = 1
    _,rebuilt,_ = _reload_export_snapshot(persisted,board_w_cm=width,board_h_cm=height)
    source = {p['id']:p for s in plan['sheets'] for p in s['pieces']}
    for sheet in rebuilt['sheets']:
        for p in sheet['pieces']:
            for key in ('corner_rotation_quarter_turns','placement_quarter_turns','corner_mirrored','mirrored','placement_mirrored'):
                if key in source[p['id']]:
                    assert p.get(key) == source[p['id']][key]
