"""Behavioral safety of the ALNS stage reached by the Recalculate pipeline."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import time

import pytest

from almdina_erp.tests.frappe_test_stub import install_if_unavailable
install_if_unavailable()
from almdina_erp.tests.test_fixed_board_layout_search import fixture, METRICS
from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
    BoardGeometry, OptimizerOptions, OptimizeOrderPlanCommand, optimize_order_plan)
from almdina_erp.almdina_erp.domain.cutting import same_count_layout_search as search
from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import final_system_sort_keys
from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan, placement_permission_errors
from almdina_erp.almdina_erp.domain.cutting.optimizer import enrich_plan_metrics
from almdina_erp.almdina_erp.domain.cutting.primitives import expand_piece_groups, make_placed_piece
from almdina_erp.almdina_erp.domain.cutting.shape_aware_nesting import _placed_corner
from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import DomainCuttingEngineAdapter


class FrozenEngine(DomainCuttingEngineAdapter):
    def __init__(self, plan):
        self.plan = deepcopy(plan)

    def optimize(self, *args, **kwargs):
        return dict(deepcopy(self.plan), smart_candidates=[deepcopy(self.plan)])


def command(rows, *, seconds=1, mode='smart', trim=0, mirror=False):
    return OptimizeOrderPlanCommand('alns-test', 'alns-test',
        BoardGeometry(10+trim*2, 10+trim*2, trim, .5),
        OptimizerOptions(mode, 'CNC Router', 5, 40, 1, 1, .0001,
            alignment_search_budget_sec=0, alns_search_budget_sec=seconds), tuple(rows),
        allow_piece_mirroring=mirror)


def mixed_fixture(kind='Clipped Corner', mirror=False):
    rows, _, plan = fixture('grid')
    rows.append(dict(width_cm=9, length_cm=9, qty=1, allow_rotation=1,
        piece_type=kind, clipped_corner_position='Top Right',
        clipped_corner_width_cm=.6, clipped_corner_length_cm=.7, piece_instance_id='smart:3'))
    sources = expand_piece_groups(rows)
    plan['sheets'].append(dict(sheet_no=3, w=10, h=10,
        pieces=[_placed_corner(sources[-1], x_cm=0, y_cm=0, mirrored=mirror, turns=0)]))
    plan = enrich_plan_metrics(plan, str(plan.get('method_key') or 'MaxRects Contact Point'), 'CNC Router', **METRICS)
    plan.update(kerf_cm=.5, machine_type='CNC Router')
    assert not validate_plan(plan, sources, 10, 10, kerf_cm=.5)
    return rows, sources, plan


@pytest.mark.parametrize('kind', ['L-Shaped Corner', 'Clipped Corner'])
@pytest.mark.parametrize('mirror', [False, True])
def test_mixed_grid_improves_regulars_and_pins_corner_exactly(kind, mirror):
    _, sources, plan = mixed_fixture(kind, mirror)
    original = deepcopy((plan, sources))
    candidates, trace = search.improve_fixed_board_layout(plan, sources, 10, 10, .5,
        deadline=time.monotonic()+5, metric_kwargs=METRICS, mirroring_allowed=mirror,
        policy=search.FixedBoardSearchPolicy(operators=('grid',), pinned_shapes=True, max_attempts=24))
    assert trace['pinned_pieces'] == 1
    assert trace['operators']['grid']['improvements'] > 0
    fixed = plan['sheets'][-1]['pieces'][-1]
    for candidate in candidates:
        assert next(p for s in candidate['sheets'] for p in s['pieces'] if p['id']==fixed['id']) == fixed
        assert not validate_plan(candidate, sources, 10, 10, kerf_cm=.5)
        assert not placement_permission_errors(candidate, sources, mirroring_allowed=mirror)
    assert (plan, sources) == original


def test_pinned_mirror_is_not_implicitly_authorized():
    _, sources, plan = mixed_fixture(mirror=True)
    result, trace = search.improve_fixed_board_layout(plan, sources, 10, 10, .5,
        deadline=time.monotonic()+1, metric_kwargs=METRICS,
        policy=search.FixedBoardSearchPolicy(pinned_shapes=True), mirroring_allowed=False)
    assert trace['stop'] == 'invalid_incumbent'
    assert result == [plan]


def test_generator_cannot_move_a_pinned_shape_even_if_bounds_still_fit(monkeypatch):
    _, sources, plan = mixed_fixture()
    def malicious(current, *args):
        trial = deepcopy(current)
        trial['sheets'][-1]['pieces'][-1]['x'] += .1
        yield trial, {}
    monkeypatch.setattr(search, '_grid', malicious)
    candidates, trace = search.improve_fixed_board_layout(plan, sources, 10, 10, .5,
        deadline=time.monotonic()+1, metric_kwargs=METRICS,
        policy=search.FixedBoardSearchPolicy(operators=('grid',), pinned_shapes=True, max_attempts=2))
    assert candidates == [plan]
    assert trace['operators']['grid']['rejects']['changed_pinned_geometry'] > 0


@pytest.mark.parametrize('trim', [0, .3])
def test_application_real_refinement_is_no_worse_and_roundtrips(trim):
    from scripts.benchmark_alns import strict_check
    rows, _, plan = fixture('exchange')
    # Identical operational copies belong to one quantity row. Two synthetic
    # indistinguishable source rows make source-number binding ambiguous in
    # the legacy geometric importer, unrelated to layout identity inventory.
    rows = [dict(rows[0], qty=2), rows[2], rows[3]]
    rows = [dict(row, piece_instance_id=f'smart:{i}') for i, row in enumerate(rows, 1)]
    sources = expand_piece_groups(rows)
    for sheet in plan['sheets']:
        sheet['pieces'] = [make_placed_piece(sources[p['id']-1], p['x'], p['y'], p['w'], p['h'], p['rotated'])
                           for p in sheet['pieces']]
    baseline = optimize_order_plan(command(rows, seconds=0, trim=trim), engine=FrozenEngine(plan))
    result = optimize_order_plan(command(rows, trim=trim), engine=FrozenEngine(plan))
    assert result.snapshot['validation']['is_valid']
    assert result.snapshot['smart_search']['alns']['attempts'] > 0
    assert final_system_sort_keys([baseline.snapshot, result.snapshot])[1] <= final_system_sort_keys([baseline.snapshot, result.snapshot])[0]
    assert baseline.required_boards == 2
    assert result.required_boards == 1
    assert result.snapshot['total_board_area_m2'] == pytest.approx(.01)
    assert result.snapshot['waste_area_m2'] == pytest.approx(.01-result.snapshot['used_area_m2'])
    assert len(result.candidate_snapshots) <= 5
    for snapshot in result.candidate_snapshots:
        assert strict_check(snapshot, rows)


@pytest.mark.parametrize('seconds', [0, -1, float('nan'), float('inf')])
def test_disabled_or_invalid_allowance_cannot_start_refinement(monkeypatch, seconds):
    rows, _, plan = fixture()
    monkeypatch.setattr(search, 'improve_fixed_board_layout', lambda *a, **k: pytest.fail('Refinement started'))
    result = optimize_order_plan(command(rows, seconds=seconds), engine=FrozenEngine(plan))
    assert result.snapshot['validation']['is_valid']
    assert 'alns' not in result.snapshot['smart_search']


def test_fast_calculation_does_not_call_alns(monkeypatch):
    rows, _, plan = fixture()
    monkeypatch.setattr(search, 'improve_fixed_board_layout', lambda *a, **k: pytest.fail('Fast called ALNS'))
    result = optimize_order_plan(command(rows, mode='auto'), engine=FrozenEngine(plan))
    assert result.snapshot['validation']['is_valid']


def test_invalid_proposal_cannot_replace_the_completed_native_snapshot(monkeypatch):
    from almdina_erp.almdina_erp.domain.cutting import system_layout_refinement as refinement
    rows, _, plan = fixture()
    baseline = optimize_order_plan(command(rows, seconds=0), engine=FrozenEngine(plan))
    def bad(raw, *args, **kwargs):
        proposal = deepcopy(raw)
        proposal['sheets'][0]['pieces'][0]['x'] = 999
        return [raw, proposal], dict(attempts=1, stop='done', operators={})
    monkeypatch.setattr(refinement, 'refine_system_layout', bad)
    result = optimize_order_plan(command(rows), engine=FrozenEngine(plan))
    assert result.snapshot['sheets'] == baseline.snapshot['sheets']
    assert result.snapshot['smart_search']['alns']['projected_improvements'] == 0


def test_stage_budget_is_capped_and_is_additional_to_native(monkeypatch):
    from almdina_erp.almdina_erp.domain.cutting import system_layout_refinement as refinement
    rows, _, plan = fixture()
    seen = []
    def observe(raw, *args, **kw):
        seen.append(kw['deadline']-time.monotonic())
        return [raw], dict(attempts=0, stop='done', operators={})
    monkeypatch.setattr(refinement, 'refine_system_layout', observe)
    result = optimize_order_plan(command(rows, seconds=100), engine=FrozenEngine(plan))
    assert 0 < seen[0] <= 4.25
    assert result.snapshot['smart_search']['alns']['budget_sec'] == 5.0
    assert result.snapshot['smart_search']['alns']['additional_to_native_search'] is True


@pytest.mark.parametrize('mirror', [False, True])
def test_recalculate_workspace_wires_the_actual_stage_and_order_mirror_flag(monkeypatch, mirror):
    from almdina_erp.almdina_erp.infrastructure.frappe import cutting_plan_workspace as workspace
    from almdina_erp.almdina_erp.domain.cutting.plan_settings import PlanSettings
    rows, _, plan = fixture()
    factory = SimpleNamespace(optimal_search_piece_limit=40, min_remnant_width_mm=10,
        min_remnant_length_mm=10, min_remnant_area_m2=.0001,
        alignment_search_budget_sec=0, max_centerable_edge_gap_cm=5)
    monkeypatch.setattr(workspace.frappe, 'get_cached_doc', lambda *a: factory, raising=False)
    monkeypatch.setattr(workspace, '_board_dimensions_mm', lambda order: (100,100))
    monkeypatch.setattr(workspace, '_validated_plan_settings', lambda plan: PlanSettings('smart','CNC Router',5,5,0))
    monkeypatch.setattr(workspace, 'plan_input_fingerprint', lambda *a, **k: 'current-inputs')
    monkeypatch.setattr(workspace, '_piece_rows', lambda order: tuple(rows))
    monkeypatch.setattr(workspace, 'domain_cutting_engine', FrozenEngine(plan))
    applied = []
    commands=[]
    actual_calculate=workspace.optimize_order_plan
    def observe_command(cmd,**kwargs):
        commands.append(cmd)
        return actual_calculate(cmd,**kwargs)
    monkeypatch.setattr(workspace,'optimize_order_plan',observe_command)
    monkeypatch.setattr(workspace, 'apply_calculation_outcome', lambda order, target, outcome, **kw: applied.append(outcome))
    outcome = workspace.calculate_system_plan(SimpleNamespace(allow_piece_mirroring=mirror), SimpleNamespace())
    assert applied == [outcome]
    assert outcome.snapshot['smart_search']['alns']['attempts'] > 0
    assert outcome.snapshot['allow_piece_mirroring'] is mirror
    assert outcome.snapshot['engine_version'] == '2.4.0-coupled-corners'
    assert outcome.snapshot['smart_search']['pattern_search']['budget_sec'] == 5
    assert commands[0].optimizer.corner_search_budget_sec==10


def test_global_refill_keeps_real_identity_and_its_whole_pool_cap():
    _, sources, plan = fixture('exchange')
    result, trace = search.improve_fixed_board_layout(plan, sources, 10, 10, .5,
        deadline=time.monotonic()+2, metric_kwargs=METRICS,
        policy=search.FixedBoardSearchPolicy(operators=('global_refill',), max_attempts=20))
    assert trace['attempts'] > 0
    for trial in result:
        assert sorted(p['id'] for s in trial['sheets'] for p in s['pieces']) == sorted(p['id'] for p in sources)
        assert len(trial['sheets']) == 2
        assert not validate_plan(trial, sources, 10, 10, kerf_cm=.5)
    result, trace = search.improve_fixed_board_layout(plan, sources, 10, 10, .5,
        deadline=time.monotonic()+2, metric_kwargs=METRICS,
        policy=search.FixedBoardSearchPolicy(operators=('global_refill',), max_pair_pieces=1))
    assert result == [plan] and trace['attempts'] == 0


def test_zero_alignment_setting_also_disables_alignment_for_alns_nominees(monkeypatch):
    from almdina_erp.almdina_erp.domain.cutting import final_cut_line_alignment as alignment
    rows, _, plan = fixture('exchange')
    original = alignment.align_regular_cut_lines
    deadlines = []
    def observe(*args, **kwargs):
        deadlines.append(kwargs['deadline_monotonic']-time.monotonic())
        return original(*args, **kwargs)
    monkeypatch.setattr(alignment, 'align_regular_cut_lines', observe)
    result = optimize_order_plan(command(rows), engine=FrozenEngine(plan))
    assert result.snapshot['validation']['is_valid']
    assert deadlines and all(value <= 0 for value in deadlines)
