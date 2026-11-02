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


@pytest.mark.parametrize("kerf", [0.3, 0.5])
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


def test_zero_kerf_does_not_fabricate_common_cuts_across_a_real_gap():
    sources, baseline = _domain_fixture(kerf=0.5)
    assert not validate_plan(baseline, sources, 100, 100, kerf_cm=0)
    # With zero kerf the actual 5 mm gap is still a gap: no false joining.
    assert _run_alignment(baseline, sources, kerf=0) is baseline


def test_uploaded_non_aligned_dxf_is_accepted_and_not_repositioned(tmp_path):
    """Strict importer must not turn optional System alignment into a validation rule."""
    import ezdxf
    from almdina_erp.tests.test_cutter_center_paths import (
        _import, _order, _piece, _rect, _sheet,
    )

    document = ezdxf.new("R2010")
    for layer in ("SHEET_OUTLINE", "GEOMETRY", "TEXT"):
        document.layers.add(layer)
    model = _sheet(document)
    for number, x, y in ((1, 150, 100), (2, 153, 305)):
        model.add_lwpolyline(
            _rect(x, y, 200, 200), close=True,
            dxfattribs={"layer": "GEOMETRY"},
        )
        model.add_text(
            str(number), dxfattribs={
                "layer": "TEXT", "insert": (x + 100, y + 100), "height": 12,
            },
        )
    path = tmp_path / "nonaligned-original.dxf"
    document.saveas(path)
    original_bytes = path.read_bytes()
    order = _order([
        _piece(piece_instance_id="door-1", width_cm=20, length_cm=20,
               cut_width_cm=20, cut_length_cm=20),
        _piece(piece_instance_id="door-2", width_cm=20, length_cm=20,
               cut_width_cm=20, cut_length_cm=20),
    ])
    imported = _import(str(path), order, kerf_mm=5, trim_mm=0)
    placed = [p for sheet in imported["sheets"] for p in sheet["pieces"]]
    assert len(placed) == 2
    assert sorted(p["x"] for p in placed) == pytest.approx([15, 15.3])
    assert path.read_bytes() == original_bytes


def test_five_candidate_alignment_runtime_and_memory_evidence():
    """Measured A/B application projection under identical candidate inputs.

    Intentionally diagnostic: timing is runner-sensitive, so no flaky wall-clock
    threshold is used as a correctness assertion.
    """
    import statistics
    import time
    import tracemalloc
    from unittest.mock import patch

    from almdina_erp.almdina_erp.domain.cutting import final_cut_line_alignment as align

    class FiveCandidates(TwoRowsEngine):
        def optimize(self, *args, **kwargs):
            result = super().optimize(*args, **kwargs)
            result["smart_candidates"] = [
                deepcopy(result["smart_candidates"][0]) for _ in range(5)
            ]
            return result

    command = OptimizeOrderPlanCommand(
        engine_version="five-plan-benchmark", input_fingerprint="same-input",
        board=BoardGeometry(100, 100, 0, .5),
        optimizer=OptimizerOptions("smart", "CNC Router", 10, 40, 30, 30, .09),
        piece_rows=({"width_cm": 20, "length_cm": 20, "qty": 2},),
        plan_settings=PlanSettings("smart", "CNC Router", 10, 5, 0),
    )
    output = {}
    for enabled in (False, True):
        elapsed, memory, shifts = [], [], []
        for _ in range(3):
            engine = FiveCandidates()
            tracemalloc.start()
            started = time.perf_counter()
            if enabled:
                result = optimize_order_plan(command, engine=engine)
            else:
                with patch.object(
                    align, "align_regular_cut_lines",
                    side_effect=lambda plan, *args, **kwargs: plan,
                ):
                    result = optimize_order_plan(command, engine=engine)
            elapsed.append((time.perf_counter() - started) * 1000)
            memory.append(tracemalloc.get_traced_memory()[1] / 1024)
            tracemalloc.stop()
            assert result.snapshot["validation"]["is_valid"]
            assert result.required_boards == 1
            shifts.append(
                result.snapshot["sheets"][0]["pieces"][1]["x"] -
                result.snapshot["sheets"][0]["pieces"][0]["x"]
            )
        output[enabled] = (statistics.median(elapsed), max(memory), shifts)
    print(
        "CUT_ALIGNMENT_5_CANDIDATES "
        f"baseline_median_ms={output[False][0]:.3f} "
        f"enabled_median_ms={output[True][0]:.3f} "
        f"baseline_peak_KiB={output[False][1]:.1f} "
        f"enabled_peak_KiB={output[True][1]:.1f} "
        f"baseline_delta_cm={output[False][2][-1]:.3f} "
        f"enabled_delta_cm={output[True][2][-1]:.3f}",
        flush=True,
    )
