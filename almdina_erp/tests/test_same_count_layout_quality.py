"""Manufacturing-valid quality repair after a proven regular-board lower bound."""
from copy import deepcopy
import json
from pathlib import Path
import time

import pytest

from almdina_erp.almdina_erp.domain.cutting import optimizer as opt, plan_search as search
from almdina_erp.almdina_erp.domain.cutting.primitives import create_sheet, make_placed_piece, expand_piece_groups
from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan, placement_permission_errors
from scripts.research_direct_kerf import case_data, metrics

OPTIONS = dict(machine_type='CNC Router', mirroring_allowed=False,
               metric_kwargs=dict(min_remnant_width_cm=30, min_remnant_length_cm=30, min_remnant_area_m2=.09))


def golden():
    _, rows, pieces = case_data('3687')
    source = {p['id']: p for p in pieces}
    fixture = json.loads((Path(__file__).parent/'fixtures/layout_3687_baseline.json').read_text())
    sheets = []
    for i, placements in enumerate(fixture['placements'], 1):
        sheet = create_sheet(i, 121.4, 243.4)
        sheet['pieces'] = [make_placed_piece(source[pid], x, y, w, h, rotated)
                           for pid, x, y, w, h, rotated in placements]
        sheets.append(sheet)
    used = sum(p['area_m2'] for p in pieces)
    plan = dict(sheets=sheets, unplaced=[], method_key='MaxRects Best Short Side', complexity=3,
                used_area_m2=used, waste_area_m2=len(sheets)*121.4*243.4/10000-used)
    return opt.enrich_plan_metrics(plan, plan['method_key'], 'CNC Router'), pieces, rows


def repair(plan, pieces, **kwargs):
    return search.improve_same_count_layout(plan, pieces, 121.4, 243.4, .5,
        **(OPTIONS | dict(deadline=time.monotonic()+3) | kwargs))


def test_3687_repair_improves_geometry_without_losing_boards_remnant_or_identity():
    plan, pieces, _ = golden()
    original = deepcopy(plan)
    result = repair(plan, pieces)
    before, after = metrics(plan), metrics(result)
    assert result is not plan and plan == original
    assert before['boards'] == after['boards'] == 3
    assert before['industrial']['largest_reusable_free_area_m2'] == pytest.approx(2.125714)
    assert after['industrial']['largest_reusable_free_area_m2'] == pytest.approx(2.125714)
    assert before['aligned']/before['adjacent'] == pytest.approx(37/70)
    assert after['aligned']/after['adjacent'] == pytest.approx(42/74)
    assert before['group_splits'] == 5 and after['group_splits'] == 4
    assert before['industrial']['estimated_cut_count'] == 102
    assert after['industrial']['estimated_cut_count'] == 91
    assert after['rank'] < before['rank']
    assert not validate_plan(result, pieces, 121.4, 243.4, kerf_cm=.5)
    assert not placement_permission_errors(result, pieces, mirroring_allowed=False)
    assert sorted(p['piece_instance_id'] for s in result['sheets'] for p in s['pieces']) == sorted(p['piece_instance_id'] for p in pieces)


@pytest.mark.parametrize('marker', ['source_offcut','placed_offcut','sheet_offcut','glass','corner','outline','geometry','overlay','guest','not_floor','panel','expired'])
def test_protected_or_unproven_plans_never_start_packing(monkeypatch, marker):
    plan, pieces, _ = golden()
    options = {}
    first = plan['sheets'][0]['pieces'][0]
    if marker == 'source_offcut': pieces[0]['resource_kind'] = 'OFFCUT'
    if marker == 'placed_offcut': first['resource_kind'] = 'OFFCUT'
    if marker == 'sheet_offcut': plan['sheets'][0]['resource_kind'] = 'OFFCUT'
    if marker == 'glass': pieces[0]['piece_type'] = 'Glass'
    if marker == 'corner': pieces[0]['piece_type'] = 'L-Shaped Corner'
    if marker == 'outline': first['placement_outline_cm'] = [[0,0],[1,0],[1,1]]
    if marker == 'geometry': first['geometry'] = {'points': [[0,0],[1,0],[1,1]]}
    if marker == 'overlay': first['overlays'] = [{'layer': 'Liner'}]
    if marker == 'guest': first['glass_host_piece_id'] = pieces[-1]['id']
    if marker == 'not_floor': pieces[0]['width_cm'] = .01; pieces[0]['length_cm'] = .01
    if marker == 'panel': options['machine_type'] = 'Panel Saw'
    if marker == 'expired': options['deadline'] = time.monotonic()-1
    if marker == 'not_floor':
        for p in pieces: p['width_cm'] = p['length_cm'] = .01
    monkeypatch.setattr(opt, '_run_preordered_method', lambda *a, **kw: pytest.fail('unsafe packing'))
    assert repair(plan, pieces, **options) is plan


def test_pair_work_is_bounded_and_sheet_metadata_survives(monkeypatch):
    plan, pieces, _ = golden()
    for sheet in plan['sheets']: sheet['research_board_identity'] = sheet['sheet_no']
    original = opt._run_preordered_method
    calls = []
    def record(*a, **kw):
        calls.append(len(a[0]))
        return original(*a, **kw)
    monkeypatch.setattr(opt, '_run_preordered_method', record)
    result = repair(plan, pieces)
    assert 0 < len(calls) <= 3 and max(calls) <= 64
    assert [s['research_board_identity'] for s in result['sheets']] == [s['research_board_identity'] for s in plan['sheets']]


def test_oversize_pair_cannot_start_packing(monkeypatch):
    plan, pieces, _ = golden()
    monkeypatch.setattr(search, '_MAX_REPACK_PIECES', 1)
    monkeypatch.setattr(opt, '_run_preordered_method', lambda *a, **kw: pytest.fail('oversize packing'))
    assert repair(plan, pieces) is plan


@pytest.mark.parametrize('width,expected_deep_budget', [(90, .95), (80, 1)])
def test_quality_time_is_reclaimed_only_after_proving_the_board_floor(monkeypatch, width, expected_deep_budget):
    pieces = expand_piece_groups([dict(width_cm=width, length_cm=60, qty=2)])
    baseline = opt.auto_fast(pieces, 100, 100, .5, 'CNC Router')
    assert len(baseline['sheets']) == 2
    monkeypatch.setattr(opt.time, 'monotonic', lambda: 0)
    monkeypatch.setattr(opt, 'auto_fast', lambda *a, **kw: deepcopy(baseline))
    monkeypatch.setattr(opt, '_run_preordered_method', lambda *a, **kw: deepcopy(baseline))
    monkeypatch.setattr(opt, '_cp_sat_available', lambda: False)
    def finish(raw, *a, **kw):
        kw['final_candidate_callback'](raw)
        return raw
    monkeypatch.setattr(opt, '_finish_plan_search', finish)
    deep_budgets, repair_deadlines = [], []
    def deep(*a, **kw):
        deep_budgets.append(a[5])
        return kw['initial_plan']
    def quality(plan, *a, **kw):
        repair_deadlines.append(kw['deadline'])
        return plan
    monkeypatch.setattr(opt, 'deep_search', deep)
    monkeypatch.setattr(search, 'improve_same_count_layout', quality)
    result = opt.smart_search(pieces, 100, 100, .5, 'CNC Router', 1)
    assert deep_budgets == [expected_deep_budget]
    assert repair_deadlines == [1]  # The original deadline, never extra time.
    assert result['sheets'] == baseline['sheets']


@pytest.mark.parametrize('mutation', ['trim','kerf','rotation','identity','size'])
def test_noop_stage_proofs_are_reused_but_changed_geometry_is_revalidated(monkeypatch, mutation):
    pieces = expand_piece_groups([dict(width_cm=20, length_cm=30, qty=2)])
    base = opt.auto_fast(pieces, 100, 100, .5)
    def noop(p, *a, **kw):
        return dict(deepcopy(p), postpass='noop')
    def invalid(p, *a, **kw):
        result = deepcopy(p)
        one, two = result['sheets'][0]['pieces']
        if mutation == 'trim': one['x'] = -1
        elif mutation == 'kerf': two.update(x=one['x']+one['w']+.1, y=one['y'])
        elif mutation == 'rotation': one.update(rotated=True, w=30, h=20)
        elif mutation == 'identity': two['id'] = one['id']
        else: one['w'] += 1
        return result
    monkeypatch.setattr('almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting.nest_glass_openings', noop)
    monkeypatch.setattr('almdina_erp.almdina_erp.domain.cutting.shape_aware_nesting.apply_shape_aware_nesting', noop)
    monkeypatch.setattr(search, 'improve_plan_search', invalid)
    offered = []
    result = opt._finish_plan_search(base, pieces, 100, 100, .5, 'CNC Router', .1, False,
        OPTIONS['metric_kwargs'], require_importable_geometry=True,
        final_candidate_callback=lambda p: offered.append(deepcopy(p)))
    assert len(offered) == 1  # Copies of the same validated geometry are not new finals.
    assert result.get('postpass') == 'noop'  # Keep post-pass provenance on ties.
    assert not validate_plan(result, pieces, 100, 100, kerf_cm=.5)
    assert all(p['x'] >= 0 for s in result['sheets'] for p in s['pieces'])


@pytest.mark.parametrize('addons', [False, True])
def test_repair_survives_snapshot_centering_reload_and_real_strict_roundtrip(tmp_path, addons):
    from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
        BoardGeometry, OptimizerOptions, OptimizeOrderPlanCommand, optimize_order_plan,
    )
    from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import domain_cutting_engine
    from scripts.research_direct_kerf import strict_roundtrip
    plan, pieces, rows = golden()
    if addons:
        metadata = dict(extra_liner=1, liner_reference_side='edge_long_left',
            liner_width_cm=1, liner_offset_cm=1, liner_start_cm=1, liner_length_cm=5,
            extra_double=1, extra_double_reference_sides='edge_long_right')
        for row in rows: row.update(metadata)
        for piece in pieces: piece.update(metadata)
        source = {p['id']: p for p in pieces}
        for sheet in plan['sheets']:
            sheet['pieces'] = [make_placed_piece(source[p['id']], p['x'], p['y'], p['w'], p['h'], p['rotated'])
                               for p in sheet['pieces']]
        plan = opt.enrich_plan_metrics(plan, plan['method_key'], 'CNC Router')
    result = repair(plan, pieces)
    if addons:
        for sheet in result['sheets']:
            for piece in sheet['pieces']:
                assert all(piece[key] == value for key, value in metadata.items())
    class Frozen:
        expand_pieces = domain_cutting_engine.expand_pieces
        validate = domain_cutting_engine.validate
        def __init__(self, plan): self.plan = plan
        def optimize(self, *a, **kw): return deepcopy(self.plan)
    # This test owns the *same-count repair* delta (35/70 -> 39/74).
    # Freeze the independent Final Alignment stage so its legitimate new
    # improvements cannot mutate this stage's before/after baseline.
    command = OptimizeOrderPlanCommand('quality-test','quality-test',BoardGeometry(122,244,.3,.5),
        OptimizerOptions('smart','CNC Router',5,40,30,30,.09,
                         alignment_search_budget_sec=0),tuple(rows))
    before = optimize_order_plan(command,engine=Frozen(plan)).snapshot
    after = optimize_order_plan(command,engine=Frozen(result)).snapshot
    assert metrics(before)['alignment_ratio'] == pytest.approx(35/70)
    assert metrics(after)['alignment_ratio'] == pytest.approx(39/74)
    assert after['industrial_rank'] < before['industrial_rank']
    saved = tmp_path/'selected.json'; saved.write_text(json.dumps(after))
    reloaded = json.loads(saved.read_text())
    assert reloaded == after
    strict_roundtrip(reloaded,rows,122,244,tmp_path)


def order_241_before():
    data = json.loads((Path(__file__).parent/'fixtures/layout_241_before.json').read_text())
    pieces = expand_piece_groups(data['rows'])
    source = {p['id']: p for p in pieces}
    sheets = []
    for i, placements in enumerate(data['placements'], 1):
        sheet = create_sheet(i, 120, 242)
        sheet['pieces'] = [make_placed_piece(source[pid], x, y, w, h, rotated)
            for pid, x, y, w, h, rotated in placements]
        sheets.append(sheet)
    used = sum(p['area_m2'] for p in pieces)
    plan = dict(sheets=sheets, unplaced=[], method_key='MaxRects Bottom Left', complexity=3,
        used_area_m2=used, total_board_area_m2=5.808, waste_area_m2=5.808-used)
    return opt.enrich_plan_metrics(plan, plan['method_key'], 'CNC Router'), pieces, data['rows']


def _occupied_area(plan):
    return sum((max(p['x']+p['w'] for p in s['pieces'])-min(p['x'] for p in s['pieces']))*
        (max(p['y']+p['h'] for p in s['pieces'])-min(p['y'] for p in s['pieces']))
        for s in plan['sheets'] if s['pieces'])


def _real_rectangular_path_length(plan, kerf_cm=.5):
    from math import dist
    from almdina_erp.almdina_erp.domain.cutting.cutter_center_paths import cutter_center_segments
    length = 0
    for sheet in plan['sheets']:
        shapes = [([(p['x']*10, p['y']*10), ((p['x']+p['w'])*10, p['y']*10),
            ((p['x']+p['w'])*10, (p['y']+p['h'])*10), (p['x']*10, (p['y']+p['h'])*10)], [])
            for p in sheet['pieces']]
        length += sum(dist(a, b) for a, b in cutter_center_segments(shapes, kerf_cm*5))/10
    return length


def compact_final(plan, pieces, **options):
    return search.compact_regular_final(plan, pieces, 120, 242, .5, **(OPTIONS | options))


@pytest.mark.parametrize('budget', [.2, 2])
def test_241_cleanup_keeps_tight_layout_despite_better_estimated_cut_count(budget):
    plan, pieces, _ = order_241_before()
    original = deepcopy(plan)
    assert [len(s['pieces']) for s in plan['sheets']] == [7, 15]
    assert plan['industrial_metrics']['largest_reusable_free_area_m2'] == 0
    assert not validate_plan(plan, pieces, 120, 242, kerf_cm=.5)
    result = search.improve_plan_search(plan, pieces, 120, 242, .5,
        machine_type='CNC Router', time_limit_sec=budget, **OPTIONS['metric_kwargs'])
    result = compact_final(result, pieces)
    assert plan == original
    assert len(result['sheets']) == 2 and not result['unplaced']
    assert result['industrial_metrics']['largest_reusable_free_area_m2'] == 0
    assert _occupied_area(result) <= _occupied_area(plan)+1e-6
    assert _real_rectangular_path_length(result) <= _real_rectangular_path_length(plan)+1e-6
    assert not validate_plan(result, pieces, 120, 242, kerf_cm=.5)
    assert not placement_permission_errors(result, pieces, mirroring_allowed=False)


@pytest.mark.parametrize('stage', ['compaction', 'remnant'])
def test_final_compaction_repairs_the_241_move_from_either_cleanup_stage(monkeypatch, stage):
    plan, pieces, _ = order_241_before()
    candidate = deepcopy(plan)
    for piece in candidate['sheets'][0]['pieces']:
        if piece['id'] in {5, 6}:
            piece['y'] = 0
    candidate = opt.enrich_plan_metrics(candidate, candidate['method_key'], 'CNC Router')
    assert candidate['industrial_rank'] < plan['industrial_rank']
    assert candidate['industrial_metrics']['estimated_cut_count'] == 46
    assert plan['industrial_metrics']['estimated_cut_count'] == 47
    assert not validate_plan(candidate, pieces, 120, 242, kerf_cm=.5)
    assert _real_rectangular_path_length(candidate) > _real_rectangular_path_length(plan)
    monkeypatch.setattr(search, '_repacked_board_candidates', lambda *a, **kw: iter(()))
    monkeypatch.setattr(search, '_compaction_candidates', lambda *a, **kw: iter([candidate] if stage == 'compaction' else []))
    monkeypatch.setattr(search, '_move_sheet_onto_others', lambda *a, **kw: None)
    monkeypatch.setattr(search, '_remnant_moves', lambda *a, **kw: [()] if stage == 'remnant' else [])
    monkeypatch.setattr(search, '_relocate', lambda *a, **kw: candidate)
    result = search.improve_plan_search(plan, pieces, 120, 242, .5,
        machine_type='CNC Router', time_limit_sec=2, **OPTIONS['metric_kwargs'])
    assert result is not plan
    fixed = compact_final(result, pieces)
    assert _occupied_area(fixed) <= _occupied_area(plan)+1e-6
    assert _real_rectangular_path_length(fixed) <= _real_rectangular_path_length(plan)+1e-6


@pytest.mark.parametrize('reverse', [False, True])
def test_cleanup_cannot_trade_a_larger_envelope_for_shorter_paths_or_the_reverse(reverse):
    pieces = expand_piece_groups([dict(width_cm=10, length_cm=30, qty=2)])
    def placed(positions):
        raw = dict(sheets=[dict(sheet_no=1, w=120, h=242,
            pieces=[make_placed_piece(p, x, y, 10, 30, False)
            for p, (x, y) in zip(pieces, positions)])], unplaced=[])
        return opt.enrich_plan_metrics(raw, 'MaxRects Bottom Left', 'CNC Router',
            min_remnant_width_cm=300, min_remnant_length_cm=300, min_remnant_area_m2=9)
    narrow = placed([(0, 0), (0, 30.5)])
    shorter_cut = placed([(0, 0), (10.5, 0)])
    assert _occupied_area(narrow) < _occupied_area(shorter_cut)
    assert _real_rectangular_path_length(narrow) > _real_rectangular_path_length(shorter_cut)
    before, after = (shorter_cut, narrow) if reverse else (narrow, shorter_cut)
    assert compact_final(before, pieces) is before  # Already tight; no repacking or rotation.


@pytest.mark.parametrize('kerf', [0, .3, .5, .7])
def test_cleanup_measures_the_full_canonical_network_in_centimeters(kerf):
    pieces = expand_piece_groups([dict(width_cm=10, length_cm=30, qty=2)])
    plan = dict(sheets=[dict(pieces=[make_placed_piece(p, x, 0, 10, 30, False)
        for p, x in zip(pieces, [0, 10+kerf])])])
    area, length = search._rectangular_cleanup_geometry(plan, [0], kerf)
    # Two offset rectangle perimeters minus one shared 30+Kerf cm side.
    assert area == pytest.approx((20+kerf)*30)
    assert length == pytest.approx(130+7*kerf)


@pytest.mark.parametrize('skip', ['remnant', 'panel', 'oversize'])
def test_final_compaction_skips_positive_remnants_panel_saw_and_large_orders(monkeypatch, skip):
    plan, pieces, _ = order_241_before()
    options = {}
    if skip == 'remnant': plan['industrial_metrics']['largest_reusable_free_area_m2'] = .1
    if skip == 'panel': options['machine_type'] = 'Panel Saw'
    if skip == 'oversize': pieces = pieces*3
    monkeypatch.setattr(search, '_rectangular_cleanup_geometry', lambda *a: pytest.fail('primary gain blocked'))
    assert compact_final(plan, pieces, **options) is plan


@pytest.mark.parametrize('marker', ['sheet_offcut', 'piece_offcut', 'glass', 'corner', 'outline',
    'geometry', 'overlay', 'special_shape', 'guest', 'nest', 'mirror'])
def test_cleanup_guard_leaves_protected_geometry_to_its_existing_contract(monkeypatch, marker):
    plan, pieces, _ = order_241_before()
    first = plan['sheets'][0]['pieces'][0]
    if marker == 'sheet_offcut': plan['sheets'][0]['resource_kind'] = 'OFFCUT'
    if marker == 'piece_offcut': first['resource_kind'] = 'OFFCUT'
    if marker == 'glass': first['piece_type'] = 'Glass'
    if marker == 'corner': first['piece_type'] = 'Clipped Corner'
    if marker == 'outline': first['placement_outline_cm'] = [[0,0],[1,0],[1,1]]
    if marker == 'geometry': first['geometry'] = {'outer': [[0,0],[1,0],[1,1]]}
    if marker == 'overlay': first['overlays'] = [{'layer': 'Liner'}]
    if marker == 'special_shape': first['special_shape_geometry_json'] = '{"outer": [[0,0],[1,0],[1,1]]}'
    if marker == 'guest': first['glass_host_piece_id'] = 5
    if marker == 'nest': first['placement_quarter_turns'] = 0
    if marker == 'mirror': first['placement_mirrored'] = True
    monkeypatch.setattr(search, '_rectangular_cleanup_geometry', lambda *a: pytest.fail('protected geometry measured as rectangles'))
    assert compact_final(plan, pieces) is plan


def test_241_preserved_snapshot_survives_centering_reload_and_actual_js_strict_import(tmp_path):
    from almdina_erp.tests.test_smart_cutting_manufacturing import import_saved_plan
    from almdina_erp.tests.test_cutting_industrial_gaps import export_real_js
    from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
        BoardGeometry, OptimizerOptions, OptimizeOrderPlanCommand, optimize_order_plan,
    )
    from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import domain_cutting_engine
    plan, pieces, rows = order_241_before()
    result = search.improve_plan_search(plan, pieces, 120, 242, .5,
        machine_type='CNC Router', time_limit_sec=2, **OPTIONS['metric_kwargs'])
    class Frozen:
        expand_pieces = domain_cutting_engine.expand_pieces
        validate = domain_cutting_engine.validate
        def optimize(self, *a, **kw): return deepcopy(result)
    command = OptimizeOrderPlanCommand('regression-241', 'regression-241', BoardGeometry(122, 244, 1, .5),
        OptimizerOptions('smart', 'CNC Router', 5, 40, 30, 30, .09), tuple(rows))
    snapshot = optimize_order_plan(command, engine=Frozen()).snapshot
    assert snapshot['validation']['is_valid']
    assert snapshot['trim_cm'] == 1
    assert _occupied_area(snapshot) <= _occupied_area(plan)+1e-6
    assert _real_rectangular_path_length(snapshot) <= _real_rectangular_path_length(plan)+1e-6
    saved = tmp_path/'241.json'
    saved.write_text(json.dumps(snapshot))
    reloaded = json.loads(saved.read_text())
    imported = import_saved_plan(reloaded, rows, export_real_js(reloaded, tmp_path))
    assert len(imported['sheets']) == 2
    assert sorted(p['piece_instance_id'] for s in imported['sheets'] for p in s['pieces']) == sorted(
        p['piece_instance_id'] for s in reloaded['sheets'] for p in s['pieces'])
    for before, after in zip(reloaded['sheets'], imported['sheets'], strict=True):
        geometry = lambda s: sorted(tuple(p[k] for k in ('x', 'y', 'w', 'h')) for p in s['pieces'])
        for expected, actual in zip(geometry(before), geometry(after), strict=True):
            assert actual == pytest.approx(expected, abs=.0001)


def test_compacted_duplicate_views_keep_all_unmodified_raw_warm_seeds():
    from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
        BoardGeometry, OptimizerOptions, OptimizeOrderPlanCommand, optimize_order_plan,
    )
    from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import domain_cutting_engine
    from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import geometry_signature
    rows = [dict(width_cm=10, length_cm=30, qty=2, allow_rotation=0)]
    pieces = expand_piece_groups(rows)
    raw = dict(sheets=[dict(sheet_no=1, w=120, h=242,
        pieces=[make_placed_piece(p, 0, y, 10, 30, False) for p, y in zip(pieces, [0, 50])])],
        unplaced=[], method_key='MaxRects Bottom Left')
    one = opt.enrich_plan_metrics(raw, raw['method_key'], 'CNC Router',
        min_remnant_width_cm=300, min_remnant_length_cm=300, min_remnant_area_m2=9)
    two = deepcopy(one)
    for p in two['sheets'][0]['pieces']: p['y'] += 5
    original = deepcopy([one, two])
    class Frozen:
        expand_pieces = domain_cutting_engine.expand_pieces
        validate = domain_cutting_engine.validate
        def optimize(self, *a, **kw):
            return dict(deepcopy(one), smart_candidates=deepcopy([one, two]))
    command = OptimizeOrderPlanCommand('duplicate-final', 'duplicate-final', BoardGeometry(122, 244, 1, .5),
        OptimizerOptions('smart', 'CNC Router', 5, 40, 300, 300, 9), tuple(rows))
    outcome = optimize_order_plan(command, engine=Frozen())
    assert len(outcome.candidate_snapshots) == 1
    assert len(outcome.search_seeds) == 2
    assert sorted(geometry_signature(p) for p in outcome.search_seeds) == sorted(geometry_signature(p) for p in original)
    assert [one, two] == original
    assert outcome.snapshot['validation']['is_valid']


@pytest.mark.parametrize('addons', [False, True])
def test_3687_final_alignment_and_same_count_repair_combined_strict_roundtrip(tmp_path, addons):
    """Test the new postpass separately from the frozen repair-only regression.

    This exercises the real pipeline including enabled Final Alignment; it must
    not weaken the repair-only 35/70 => 39/74 golden check above.
    """
    from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
        BoardGeometry, OptimizerOptions, OptimizeOrderPlanCommand, optimize_order_plan,
    )
    from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import domain_cutting_engine
    from scripts.research_direct_kerf import strict_roundtrip
    plan, pieces, rows = golden()
    if addons:
        metadata = dict(extra_liner=1, liner_reference_side='edge_long_left',
            liner_width_cm=1, liner_offset_cm=1, liner_start_cm=1, liner_length_cm=5,
            extra_double=1, extra_double_reference_sides='edge_long_right')
        for row in rows: row.update(metadata)
        for piece in pieces: piece.update(metadata)
        source = {p['id']: p for p in pieces}
        for sheet in plan['sheets']:
            sheet['pieces'] = [make_placed_piece(source[p['id']], p['x'], p['y'], p['w'], p['h'], p['rotated'])
                               for p in sheet['pieces']]
        plan = opt.enrich_plan_metrics(plan, plan['method_key'], 'CNC Router')
    improved = repair(plan, pieces)
    class Frozen:
        expand_pieces = domain_cutting_engine.expand_pieces
        validate = domain_cutting_engine.validate
        def __init__(self, value): self.plan = value
        def optimize(self, *a, **kw): return deepcopy(self.plan)
    command = OptimizeOrderPlanCommand('alignment-integration','alignment-integration',
        BoardGeometry(122,244,.3,.5),
        OptimizerOptions('smart','CNC Router',5,40,30,30,.09,
                         alignment_search_budget_sec=1),tuple(rows))
    original = deepcopy(plan)
    baseline = optimize_order_plan(command, engine=Frozen(plan)).snapshot
    finished = optimize_order_plan(command, engine=Frozen(improved)).snapshot
    assert plan == original
    assert baseline['validation']['is_valid'] and finished['validation']['is_valid']
    assert len(baseline['sheets']) == len(finished['sheets']) == 3
    assert sorted(p['piece_instance_id'] for s in baseline['sheets'] for p in s['pieces']) == sorted(
        p['piece_instance_id'] for s in finished['sheets'] for p in s['pieces'])
    assert baseline['industrial_rank'][:4] == finished['industrial_rank'][:4]
    # Persisted final geometry must remain the exact geometry exported to DXF.
    for name, snapshot in (('baseline', baseline), ('refined', finished)):
        saved = tmp_path / (name + '.json')
        saved.write_text(json.dumps(snapshot))
        assert json.loads(saved.read_text()) == snapshot
        work = tmp_path / name
        work.mkdir()
        strict_roundtrip(snapshot, rows, 122, 244, work)
