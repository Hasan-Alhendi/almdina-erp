"""Regression: final System projection should share real cutter-center segments."""

from copy import deepcopy

import pytest

from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
    BoardGeometry,
    OptimizeOrderPlanCommand,
    OptimizerOptions,
    optimize_order_plan,
)
from almdina_erp.almdina_erp.domain.cutting import expand_piece_groups
from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan
from almdina_erp.almdina_erp.domain.cutting.optimizer import enrich_plan_metrics
from almdina_erp.almdina_erp.domain.cutting.plan_search import _rectangular_cleanup_geometry
from almdina_erp.almdina_erp.domain.cutting.plan_settings import PlanSettings
from almdina_erp.almdina_erp.domain.cutting.primitives import make_placed_piece


class TwoRowsEngine:
    """Complete, real-geometry Smart candidate; no packing is mocked away."""

    def __init__(self):
        self.original = None

    def expand_pieces(self, rows):
        return expand_piece_groups(rows)

    def optimize(self, pieces, board_width_cm, board_length_cm, kerf_cm, **kwargs):
        assert (board_width_cm, board_length_cm, kerf_cm) == (100, 100, 0.5)
        plan = {
            "method_key": "MaxRects Best Short Side",
            "method_label": "Fixture",
            "optimization_mode": "smart",
            "sheets": [{
                "sheet_no": 1, "resource_kind": "FULL_BOARD", "w": 100, "h": 100,
                "pieces": [
                    make_placed_piece(pieces[0], 15.0, 0.0, 20.0, 20.0, False),
                    make_placed_piece(pieces[1], 15.3, 20.5, 20.0, 20.0, False),
                ],
            }],
            "unplaced": [],
            "used_area_m2": 0.08,
            "total_board_area_m2": 1.0,
            "waste_area_m2": 0.92,
        }
        self.original = enrich_plan_metrics(plan, plan["method_key"], "CNC Router")
        return {**deepcopy(self.original), "smart_candidates": [deepcopy(self.original)]}

    def validate(self, plan, pieces, board_width_cm, board_length_cm):
        return validate_plan(plan, pieces, board_width_cm, board_length_cm, kerf_cm=0.5)


def test_system_snapshot_recovers_three_mm_alignment_without_repacking():
    engine = TwoRowsEngine()
    rows = ({"width_cm": 20, "length_cm": 20, "qty": 2},)
    command = OptimizeOrderPlanCommand(
        engine_version="final-alignment-fixture", input_fingerprint="unchanged",
        board=BoardGeometry(100, 100, 0, 0.5),
        optimizer=OptimizerOptions("smart", "CNC Router", 10, 40, 30, 30, 0.09),
        piece_rows=rows,
        plan_settings=PlanSettings("smart", "CNC Router", 10, 5, 0),
    )
    outcome = optimize_order_plan(command, engine=engine)
    baseline = engine.original
    assert baseline is not None
    assert baseline["industrial_metrics"]["largest_reusable_free_area_m2"] > 0
    assert not validate_plan(baseline, engine.expand_pieces(list(rows)), 100, 100, kerf_cm=0.5)
    final = outcome.snapshot
    assert final["validation"]["is_valid"]
    assert len(final["sheets"]) == 1
    positioned = {p["id"]: p for p in final["sheets"][0]["pieces"]}
    assert positioned[1]["x"] == pytest.approx(positioned[2]["x"])
    before_length = _rectangular_cleanup_geometry(baseline, [0], 0.5)[1]
    after_length = _rectangular_cleanup_geometry(final, [0], 0.5)[1]
    assert after_length < before_length - 0.01  # centimeters: measured cutter-center network
    assert final["industrial_metrics"]["largest_reusable_free_area_m2"] >= (
        baseline["industrial_metrics"]["largest_reusable_free_area_m2"]
    )
    assert {(p["id"], p.get("piece_instance_id"), p.get("rotated"))
            for p in final["sheets"][0]["pieces"]} == {
        (p["id"], p.get("piece_instance_id"), p.get("rotated"))
        for p in baseline["sheets"][0]["pieces"]
    }
    assert engine.original == baseline  # never modify raw Smart seed


def _domain_fixture(*, kerf=0.5, offset=0.3):
    from almdina_erp.almdina_erp.domain.cutting.final_cut_line_alignment import _rectangles
    sources = expand_piece_groups([dict(width_cm=20, length_cm=20, qty=2,
                                        piece_instance_id="stable-door")])
    plan = dict(
        method_key="MaxRects Best Short Side",
        sheets=[dict(sheet_no=1, resource_kind="FULL_BOARD", w=100, h=100, pieces=[
            make_placed_piece(sources[0], 15, 0, 20, 20, False),
            make_placed_piece(sources[1], 15 + offset, 20 + kerf, 20, 20, False),
        ])],
        unplaced=[], used_area_m2=.08, total_board_area_m2=1, waste_area_m2=.92,
    )
    plan = enrich_plan_metrics(plan, plan["method_key"], "CNC Router")
    assert not validate_plan(plan, sources, 100, 100, kerf_cm=kerf)
    assert _rectangles(plan, kerf)[0] > 0
    return sources, plan


def _run_alignment(plan, sources, *, kerf=0.5, deadline=None):
    from almdina_erp.almdina_erp.domain.cutting.final_cut_line_alignment import align_regular_cut_lines
    return align_regular_cut_lines(
        plan, sources, 100, 100, kerf,
        machine_type="CNC Router", mirroring_allowed=False,
        metric_kwargs=dict(min_remnant_width_cm=30, min_remnant_length_cm=30,
                           min_remnant_area_m2=.09),
        deadline_monotonic=deadline,
    )


@pytest.mark.parametrize("kerf", [0, 0.5])
def test_exact_center_network_gets_shorter_without_changing_original(kerf):
    from almdina_erp.almdina_erp.domain.cutting.final_cut_line_alignment import _rectangles
    sources, original = _domain_fixture(kerf=kerf)
    original_copy = deepcopy(original)
    changed = _run_alignment(original, sources, kerf=kerf)
    assert changed is not original
    assert original == original_copy
    assert _rectangles(changed, kerf)[0] < _rectangles(original, kerf)[0] - .05
    assert _rectangles(changed, kerf)[1] <= _rectangles(original, kerf)[1]
    assert not validate_plan(changed, sources, 100, 100, kerf_cm=kerf)
    assert changed["industrial_rank"][:4] <= original["industrial_rank"][:4]
    for a, b in zip(original["sheets"][0]["pieces"], changed["sheets"][0]["pieces"]):
        assert {k: v for k, v in a.items() if k not in ("x", "y")} == {
            k: v for k, v in b.items() if k not in ("x", "y")
        }
    # Idempotence of an already-aligned locally optimal plan.
    again = _run_alignment(changed, sources, kerf=kerf)
    assert again == changed


def test_already_aligned_no_op_returns_the_exact_object():
    sources, plan = _domain_fixture(offset=0)
    assert _run_alignment(plan, sources) is plan


def test_time_expiry_does_not_change_any_geometry():
    sources, plan = _domain_fixture()
    assert _run_alignment(plan, sources, deadline=0) is plan


@pytest.mark.parametrize("protected", ["Glass", "OFFCUT", "overlay", "geometry"])
def test_protected_nests_and_offcut_do_not_move(protected):
    sources, plan = _domain_fixture()
    original = deepcopy(plan)
    if protected == "Glass":
        sources[0]["piece_type"] = plan["sheets"][0]["pieces"][0]["piece_type"] = "Glass"
    elif protected == "OFFCUT":
        sources[0]["resource_kind"] = plan["sheets"][0]["pieces"][0]["resource_kind"] = "OFFCUT"
    elif protected == "overlay":
        plan["sheets"][0]["pieces"][0]["overlays"] = [{"type": "protected"}]
    else:
        plan["sheets"][0]["pieces"][0]["geometry"] = {"version": 2}
    expected = deepcopy(plan)
    assert _run_alignment(plan, sources) is plan
    assert plan == expected
    assert original["sheets"][0]["pieces"][0]["x"] == 15


def test_group_candidate_preserves_internal_kerf_and_identity():
    from almdina_erp.almdina_erp.domain.cutting.final_cut_line_alignment import (
        _groups, _translate_if_clear,
    )
    sources = expand_piece_groups([dict(width_cm=20, length_cm=20, qty=3,
                                        piece_instance_id="row")])
    sheet = dict(sheet_no=1, w=100, h=100, pieces=[
        make_placed_piece(sources[0], 10, 0, 20, 20, False),
        make_placed_piece(sources[1], 30.5, 0, 20, 20, False),
        make_placed_piece(sources[2], 10.3, 20.5, 20, 20, False),
    ])
    assert (1, 2) in _groups(sheet, "x")
    moved = _translate_if_clear(dict(sheets=[sheet]), 0, "x", (1, 2), 0.3, 0.5)
    assert moved is not None
    placed = moved["sheets"][0]["pieces"]
    assert placed[1]["x"] - placed[0]["x"] == pytest.approx(20.5)
    assert placed[2]["x"] == 10.3
    assert [p["piece_instance_id"] for p in placed] == [
        p["piece_instance_id"] for p in sheet["pieces"]
    ]
    assert not validate_plan(dict(sheets=moved["sheets"], unplaced=[]), sources, 100, 100, kerf_cm=.5)


def test_non_aligned_regular_geometry_is_not_an_import_validation_error():
    sources, plan = _domain_fixture(offset=.3)
    assert not validate_plan(plan, sources, 100, 100, kerf_cm=.5)
    bad = deepcopy(plan)
    bad["sheets"][0]["pieces"][1]["y"] = 20.2  # breaks the actual 5 mm kerf
    assert validate_plan(bad, sources, 100, 100, kerf_cm=.5)


def test_vertical_alignment_is_measured_on_the_entire_board():
    from almdina_erp.almdina_erp.domain.cutting.final_cut_line_alignment import _rectangles
    sources = expand_piece_groups([dict(width_cm=20, length_cm=20, qty=2)])
    plan = dict(
        method_key="MaxRects Best Short Side",
        sheets=[dict(sheet_no=1, w=100, h=100, pieces=[
            make_placed_piece(sources[0], 0, 15, 20, 20, False),
            make_placed_piece(sources[1], 20.5, 15.3, 20, 20, False),
        ])],
        unplaced=[], used_area_m2=.08, total_board_area_m2=1, waste_area_m2=.92,
    )
    baseline = enrich_plan_metrics(plan, plan["method_key"], "CNC Router")
    assert not validate_plan(baseline, sources, 100, 100, kerf_cm=.5)
    candidate = _run_alignment(baseline, sources)
    assert candidate["sheets"][0]["pieces"][0]["y"] == pytest.approx(
        candidate["sheets"][0]["pieces"][1]["y"]
    )
    assert _rectangles(candidate, .5)[0] < _rectangles(baseline, .5)[0]
    assert not validate_plan(candidate, sources, 100, 100, kerf_cm=.5)


def test_repeated_generation_is_deterministic_and_large_shift_is_not_forced():
    sources, plan = _domain_fixture()
    runs = [_run_alignment(deepcopy(plan), sources) for _ in range(3)]
    assert runs[0] == runs[1] == runs[2]
    sources, distant = _domain_fixture(offset=2.0)
    assert _run_alignment(distant, sources) is distant
