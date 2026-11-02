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


@pytest.mark.parametrize("protected", ["Glass", "L-Shaped Corner", "Clipped Corner", "Joint", "OFFCUT", "overlay", "geometry"])
def test_protected_nests_and_offcut_do_not_move(protected):
    sources, plan = _domain_fixture()
    original = deepcopy(plan)
    if protected in {"Glass", "L-Shaped Corner", "Clipped Corner", "Joint"}:
        sources[0]["piece_type"] = plan["sheets"][0]["pieces"][0]["piece_type"] = protected
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
    aligned = _run_alignment(distant, sources)
    # Geometry, not a 10 mm magic number, now determines legal translations.
    assert aligned["sheets"][0]["pieces"][0]["x"] == pytest.approx(
        aligned["sheets"][0]["pieces"][1]["x"]
    )
    assert not validate_plan(aligned, sources, 100, 100, kerf_cm=.5)


def test_zero_kerf_does_not_fabricate_common_cuts_across_a_real_gap():
    from almdina_erp.almdina_erp.domain.cutting.final_cut_line_alignment import _rectangles
    sources, baseline = _domain_fixture(kerf=0.5)
    assert not validate_plan(baseline, sources, 100, 100, kerf_cm=0)
    result = _run_alignment(baseline, sources, kerf=0)
    # An optional axis alignment is allowed but must not fabricate shared cuts
    # where the real 5 mm space remains.
    assert _rectangles(result, 0) == pytest.approx(_rectangles(baseline, 0))
    assert not validate_plan(result, sources, 100, 100, kerf_cm=0)


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
    def run_once(enabled):
        engine = FiveCandidates()
        if enabled:
            return optimize_order_plan(command, engine=engine)
        with patch.object(
            align, "align_regular_cut_lines",
            side_effect=lambda plan, *args, **kwargs: plan,
        ):
            return optimize_order_plan(command, engine=engine)

    # First warm imports, then time with tracemalloc OFF (its overhead
    # distorts short projections). Measure memory peaks in separate runs.
    run_once(False)
    run_once(True)
    output = {}
    for enabled in (False, True):
        elapsed, memory, shifts, profiles, remnants = [], [], [], [], []
        for _ in range(7):
            started = time.perf_counter()
            result = run_once(enabled)
            elapsed.append((time.perf_counter() - started) * 1000)
            assert result.snapshot["validation"]["is_valid"]
            assert result.required_boards == 1
            shifts.append(
                result.snapshot["sheets"][0]["pieces"][1]["x"] -
                result.snapshot["sheets"][0]["pieces"][0]["x"]
            )
            profiles.append(align._rectangles(result.snapshot, .5))
            remnants.append(result.snapshot["industrial_metrics"]["largest_reusable_free_area_m2"])
        for _ in range(3):
            tracemalloc.start()
            result = run_once(enabled)
            memory.append(tracemalloc.get_traced_memory()[1] / 1024)
            tracemalloc.stop()
        output[enabled] = (
            statistics.median(elapsed), statistics.median(memory), shifts, profiles, remnants,
        )
    print(
        "CUT_ALIGNMENT_5_CANDIDATES "
        f"baseline_median_ms={output[False][0]:.3f} "
        f"enabled_median_ms={output[True][0]:.3f} "
        f"baseline_peak_KiB={output[False][1]:.1f} "
        f"enabled_peak_KiB={output[True][1]:.1f} "
        f"baseline_delta_cm={output[False][2][-1]:.3f} "
        f"enabled_delta_cm={output[True][2][-1]:.3f} "
        f"baseline_network_mm={output[False][3][-1][0]:.3f} "
        f"enabled_network_mm={output[True][3][-1][0]:.3f} "
        f"baseline_segments={output[False][3][-1][1]} "
        f"enabled_segments={output[True][3][-1][1]} "
        f"baseline_remnant_m2={output[False][4][-1]:.6f} "
        f"enabled_remnant_m2={output[True][4][-1]:.6f}",
        flush=True,
    )


# General, non-image-specific witnesses for alignment rather than shared cutting.
def _separated_fixture(*, axis="x"):
    sources = expand_piece_groups([dict(width_cm=20, length_cm=20, qty=2)])
    points = [(0.0, 0.0), (0.3, 50.0)] if axis == "x" else [(0.0, 0.0), (50.0, 0.3)]
    placements = [make_placed_piece(p, x, y, 20, 20, False)
                  for p, (x, y) in zip(sources, points)]
    plan = dict(method_key="MaxRects Best Short Side",
                sheets=[dict(sheet_no=1, resource_kind="FULL_BOARD", w=100, h=100, pieces=placements)],
                unplaced=[], used_area_m2=.08, total_board_area_m2=1, waste_area_m2=.92)
    plan = enrich_plan_metrics(plan, plan["method_key"], "CNC Router")
    assert not validate_plan(plan, sources, 100, 100, kerf_cm=.5)
    return sources, plan


@pytest.mark.parametrize("axis", ["x", "y"])
def test_distant_rows_and_columns_gain_axis_alignment_without_fake_shared_cut(axis):
    from almdina_erp.almdina_erp.domain.cutting.final_cut_line_alignment import _rectangles
    sources, raw = _separated_fixture(axis=axis)
    before = deepcopy(raw)
    outcome = _run_alignment(raw, sources)
    a, b = outcome["sheets"][0]["pieces"]
    assert a[axis] == pytest.approx(b[axis])
    other_axis = "y" if axis == "x" else "x"
    assert [p[other_axis] for p in outcome["sheets"][0]["pieces"]] == [
        p[other_axis] for p in raw["sheets"][0]["pieces"]
    ]  # no closing the distant perpendicular gap under an alignment pretext
    assert _rectangles(outcome, .5) == pytest.approx(_rectangles(raw, .5))
    assert not validate_plan(outcome, sources, 100, 100, kerf_cm=.5)
    assert raw == before


def test_large_multi_board_plan_does_not_disable_small_board_alignment():
    sources = expand_piece_groups([
        dict(width_cm=20, length_cm=20, qty=2),
        dict(width_cm=1, length_cm=1, qty=65),
    ])
    first = [make_placed_piece(sources[0], 0, 0, 20, 20, False),
             make_placed_piece(sources[1], .3, 50, 20, 20, False)]
    second = [
        make_placed_piece(p, 2.5 * ((index - 2) % 13),
                          2.5 * ((index - 2) // 13), 1, 1, False)
        for index, p in enumerate(sources[2:], 2)
    ]
    plan = dict(method_key="MaxRects Best Short Side",
                sheets=[dict(sheet_no=1, resource_kind="FULL_BOARD", w=100, h=100, pieces=first),
                        dict(sheet_no=2, resource_kind="FULL_BOARD", w=100, h=100, pieces=second)],
                unplaced=[], used_area_m2=.145, total_board_area_m2=2, waste_area_m2=1.855)
    plan = enrich_plan_metrics(plan, plan["method_key"], "CNC Router")
    assert not validate_plan(plan, sources, 100, 100, kerf_cm=.5)
    after = _run_alignment(plan, sources)
    assert after["sheets"][0]["pieces"][0]["x"] == pytest.approx(
        after["sheets"][0]["pieces"][1]["x"])
    assert after["sheets"][1]["pieces"] == plan["sheets"][1]["pieces"]
    assert len(after["sheets"]) == 2
    assert not validate_plan(after, sources, 100, 100, kerf_cm=.5)


def test_diagnostics_distinguish_candidates_from_eligibility_and_time_budget():
    from almdina_erp.almdina_erp.domain.cutting.final_cut_line_alignment import align_regular_cut_lines
    sources, plan = _separated_fixture()
    diagnostics = {}
    result = align_regular_cut_lines(
        plan, sources, 100, 100, .5, machine_type="CNC Router",
        mirroring_allowed=False, metric_kwargs=dict(
            min_remnant_width_cm=30, min_remnant_length_cm=30,
            min_remnant_area_m2=.09),
        diagnostics=diagnostics,
    )
    assert result["sheets"][0]["pieces"][0]["x"] == pytest.approx(
        result["sheets"][0]["pieces"][1]["x"])
    assert diagnostics.get("candidate_count", 0) > 0
    assert diagnostics.get("tested", 0) > 0
    assert diagnostics.get("accepted", 0) > 0
    expired = {}
    unchanged = align_regular_cut_lines(
        plan, sources, 100, 100, .5, machine_type="CNC Router",
        mirroring_allowed=False, metric_kwargs=dict(
            min_remnant_width_cm=30, min_remnant_length_cm=30,
            min_remnant_area_m2=.09),
        deadline_monotonic=0, diagnostics=expired,
    )
    assert unchanged is plan
    assert expired["reason"] == "deadline"


def test_protected_glass_stays_fixed_while_independent_regular_pair_aligns():
    sources = expand_piece_groups([
        dict(width_cm=20, length_cm=20, qty=2),
        dict(width_cm=15, length_cm=15, qty=1, piece_type="Glass"),
    ])
    placed = [
        make_placed_piece(sources[0], 0, 0, 20, 20, False),
        make_placed_piece(sources[1], .3, 50, 20, 20, False),
        make_placed_piece(sources[2], 70, 80, 15, 15, False),
    ]
    plan = dict(method_key="MaxRects Best Short Side",
                sheets=[dict(sheet_no=1, resource_kind="FULL_BOARD",
                             w=100, h=100, pieces=placed)],
                unplaced=[], used_area_m2=.1025, total_board_area_m2=1, waste_area_m2=.8975)
    plan = enrich_plan_metrics(plan, plan["method_key"], "CNC Router")
    assert not validate_plan(plan, sources, 100, 100, kerf_cm=.5)
    original = deepcopy(plan)
    changed = _run_alignment(plan, sources)
    assert changed["sheets"][0]["pieces"][0]["x"] == pytest.approx(
        changed["sheets"][0]["pieces"][1]["x"])
    assert changed["sheets"][0]["pieces"][2] == original["sheets"][0]["pieces"][2]
    assert not validate_plan(changed, sources, 100, 100, kerf_cm=.5)
    assert plan == original


def test_large_single_sheet_is_bounded_and_diagnosed_without_repacking():
    from almdina_erp.almdina_erp.domain.cutting.final_cut_line_alignment import align_regular_cut_lines
    sources = expand_piece_groups([dict(width_cm=1, length_cm=1, qty=65)])
    sheet = dict(sheet_no=1, w=100, h=100, resource_kind="FULL_BOARD", pieces=[
        make_placed_piece(source, (i % 13) * 2.5, (i // 13) * 2.5, 1, 1, False)
        for i, source in enumerate(sources)
    ])
    plan = dict(method_key="MaxRects Best Short Side", sheets=[sheet], unplaced=[],
                used_area_m2=.0065, total_board_area_m2=1, waste_area_m2=.9935)
    plan = enrich_plan_metrics(plan, plan["method_key"], "CNC Router")
    assert not validate_plan(plan, sources, 100, 100, kerf_cm=.5)
    diagnostics = {}
    result = align_regular_cut_lines(
        plan, sources, 100, 100, .5,
        machine_type="CNC Router", mirroring_allowed=False,
        metric_kwargs=dict(min_remnant_width_cm=30, min_remnant_length_cm=30,
                           min_remnant_area_m2=.09),
        diagnostics=diagnostics,
    )
    assert result is plan
    assert diagnostics["large_sheets_skipped"] == 1
    assert diagnostics["reason"] == "no_eligible_pair"


def test_aligned_projection_is_repeatable_after_second_application_run():
    sources, plan = _separated_fixture()
    first = _run_alignment(plan, sources)
    second = _run_alignment(first, sources)
    assert second == first
    assert not validate_plan(second, sources, 100, 100, kerf_cm=.5)


# Anonymized manufacturing-geometry witness reconstructed from an exported
# three-board rectangular DXF. Only one 16-piece board is needed to reproduce
# the grouped-axis opportunity; no customer/order identifiers are stored.
_FIRST_BOARD_MM = (
    (33, 4, 1010, 299),
    (33, 308, 1010, 299),
    (33, 612, 1010, 269),
    (33, 886, 1010, 269),
    (6.5, 1160, 903, 299),
    (914.5, 1160, 299, 903),
    (6.5, 1464, 903, 299),
    (6.5, 1768, 903, 299),
    (1048, 4, 139, 461),
    (1048, 470, 139, 461),
    (22.5, 2072, 461, 129),
    (22.5, 2206, 461, 129),
    (488.5, 2072, 461, 129),
    (954.5, 2068, 119, 368),
    (488.5, 2206, 400, 119),
    (1078.5, 2068, 119, 368),
)
_RIGID_SIX_IDS = frozenset((1, 2, 3, 4, 9, 10))


def _production_geometry_witness():
    sources = expand_piece_groups([
        dict(width_cm=w / 10, length_cm=h / 10, qty=1)
        for x, y, w, h in _FIRST_BOARD_MM
    ])
    pieces = [
        make_placed_piece(source, x / 10, y / 10, w / 10, h / 10, False)
        for source, (x, y, w, h) in zip(sources, _FIRST_BOARD_MM)
    ]
    used = sum(piece["w"] * piece["h"] for piece in pieces) / 10000
    plan = dict(
        method_key="MaxRects Best Short Side",
        sheets=[dict(sheet_no=1, resource_kind="FULL_BOARD",
                     w=122, h=244, pieces=pieces)],
        unplaced=[], used_area_m2=used,
        total_board_area_m2=122 * 244 / 10000,
        waste_area_m2=122 * 244 / 10000 - used,
    )
    plan = enrich_plan_metrics(plan, plan["method_key"], "CNC Router")
    assert not validate_plan(plan, sources, 122, 244, kerf_cm=.5)
    return sources, plan


def _six_piece_group_shift(plan):
    moved = deepcopy(plan)
    for piece in moved["sheets"][0]["pieces"]:
        if piece["id"] in _RIGID_SIX_IDS:
            piece["x"] -= 2.65
    return moved


def test_anonymized_large_board_real_kerf_prefers_group_six_over_four():
    from almdina_erp.almdina_erp.domain.cutting.final_cut_line_alignment import (
        _rectangles, _groups,
    )
    from almdina_erp.almdina_erp.domain.cutting.optimizer import (
        _largest_reusable_free_area,
    )
    sources, original = _production_geometry_witness()
    assert _RIGID_SIX_IDS in [
        frozenset(group) for group in _groups(original["sheets"][0], "x")
    ]
    four = deepcopy(original)
    for piece in four["sheets"][0]["pieces"]:
        if piece["id"] in {1, 2, 3, 4}:
            piece["x"] -= 2.65
    full = _six_piece_group_shift(original)
    assert not validate_plan(four, sources, 122, 244, kerf_cm=.5)
    assert not validate_plan(full, sources, 122, 244, kerf_cm=.5)
    before_length, before_segments = _rectangles(original, .5)
    four_length, four_segments = _rectangles(four, .5)
    after_length, after_segments = _rectangles(full, .5)
    assert four_length > before_length + 900  # mm: breaks existing shared cutters
    assert four_segments > before_segments
    assert after_length == pytest.approx(before_length, abs=.05)
    assert after_segments < before_segments
    assert full["sheets"][0]["pieces"][0]["x"] == pytest.approx(
        full["sheets"][0]["pieces"][4]["x"]
    )
    def reusable(p):
        return _largest_reusable_free_area(p, 30, 30, .09, machine_type="CNC Router")
    assert reusable(full) >= reusable(original) - 1e-9
    # A second independent rigid six-piece group can also align without
    # destroying any original cut: this proves why two sweeps matter.
    combined = deepcopy(full)
    for piece in combined["sheets"][0]["pieces"]:
        if piece["id"] in {11, 12, 13, 14, 15, 16}:
            piece["x"] -= 1.6
    assert not validate_plan(combined, sources, 122, 244, kerf_cm=.5)
    combined_length, combined_segments = _rectangles(combined, .5)
    assert combined_length <= after_length + .05
    assert combined_segments < after_segments
    assert reusable(combined) >= reusable(original) - 1e-9
    assert original["sheets"][0]["pieces"][0]["x"] == pytest.approx(3.3)


def test_anonymized_board_alignment_search_reaches_proven_six_piece_move():
    from almdina_erp.almdina_erp.domain.cutting.final_cut_line_alignment import (
        align_regular_cut_lines, _rectangles,
    )
    sources, original = _production_geometry_witness()
    diagnostics = {}
    result = align_regular_cut_lines(
        original, sources, 122, 244, .5,
        machine_type="CNC Router", mirroring_allowed=False,
        metric_kwargs=dict(min_remnant_width_cm=30, min_remnant_length_cm=30,
                           min_remnant_area_m2=.09),
        diagnostics=diagnostics,
    )
    before = {p["id"]: p for p in original["sheets"][0]["pieces"]}
    after = {p["id"]: p for p in result["sheets"][0]["pieces"]}
    assert after[1]["x"] == pytest.approx(after[5]["x"])
    assert after[1]["x"] == pytest.approx(.65)  # 6.5 mm from board origin
    # Group's vertical and internal geometry must remain unaltered.
    for piece_id in _RIGID_SIX_IDS:
        assert after[piece_id]["x"] - before[piece_id]["x"] == pytest.approx(-2.65)
        assert after[piece_id]["y"] == before[piece_id]["y"]
    assert _rectangles(result, .5)[0] <= _rectangles(original, .5)[0] + .05
    assert _rectangles(result, .5)[1] < _rectangles(original, .5)[1]
    assert not validate_plan(result, sources, 122, 244, kerf_cm=.5)
    assert diagnostics["accepted"] >= 1


# Remaining two sheet rectangles in the same anonymized DXF. This captures
# portfolio/multi-sheet budget pressure without storing uploaded file contents.
_SECOND_BOARD_MM = (
    (5, 12, 448, 299), (5, 316, 903, 269), (913, 12, 299, 770),
    (5, 590, 818, 299), (828, 787, 299, 818), (5, 894, 818, 299),
    (5, 1198, 818, 299), (5, 1502, 818, 139), (828, 1610, 139, 818),
    (5, 1646, 409, 745), (458, 12, 448, 299),
    (419, 1646, 400, 119), (419, 1770, 400, 119),
    (419, 1894, 400, 119), (419, 2018, 400, 119),
    (419, 2142, 400, 119), (419, 2266, 400, 119),
    (972, 1610, 119, 400), (1096, 1610, 119, 368),
    (1096, 1983, 119, 368), (972, 2015, 119, 368),
)
_THIRD_BOARD_MM = (
    (0, 0, 903, 269), (0, 274, 745, 409),
    (750, 274, 368, 119), (750, 398, 368, 119), (750, 522, 368, 119),
)


def _three_sheet_dxf_geometry_witness():
    board_sets = (_FIRST_BOARD_MM, _SECOND_BOARD_MM, _THIRD_BOARD_MM)
    sources = expand_piece_groups([
        dict(width_cm=w / 10, length_cm=h / 10, qty=1)
        for board_set in board_sets for x, y, w, h in board_set
    ])
    sheets = []
    index = 0
    for no, board_set in enumerate(board_sets, 1):
        pieces = []
        for x, y, w, h in board_set:
            pieces.append(make_placed_piece(
                sources[index], x / 10, y / 10, w / 10, h / 10, False
            ))
            index += 1
        sheets.append(dict(sheet_no=no, resource_kind="FULL_BOARD", w=122, h=244,
                           pieces=pieces))
    used = sum(p["w"] * p["h"] for s in sheets for p in s["pieces"]) / 10000
    total = len(sheets) * 122 * 244 / 10000
    plan = enrich_plan_metrics(
        dict(method_key="MaxRects Best Short Side", sheets=sheets, unplaced=[],
             used_area_m2=used, total_board_area_m2=total,
             waste_area_m2=total - used), "MaxRects Best Short Side", "CNC Router"
    )
    assert len(sources) == 42 and len(plan["sheets"]) == 3
    assert not validate_plan(plan, sources, 122, 244, kerf_cm=.5)
    return sources, plan


def test_anonymized_three_board_dxf_search_finds_group_without_clock_assumptions():
    import time
    from almdina_erp.almdina_erp.domain.cutting.final_cut_line_alignment import (
        align_regular_cut_lines, _rectangles,
    )
    sources, plan = _three_sheet_dxf_geometry_witness()
    diagnostics = {}
    result = align_regular_cut_lines(
        plan, sources, 122, 244, .5,
        machine_type="CNC Router", mirroring_allowed=False,
        metric_kwargs=dict(min_remnant_width_cm=30, min_remnant_length_cm=30,
                           min_remnant_area_m2=.09),
        diagnostics=diagnostics,
    )
    first = {p["id"]: p for p in result["sheets"][0]["pieces"]}
    assert first[1]["x"] == pytest.approx(first[5]["x"]), diagnostics
    assert len(result["sheets"]) == 3
    assert _rectangles(result, .5)[0] <= _rectangles(plan, .5)[0] + .05
    assert not validate_plan(result, sources, 122, 244, kerf_cm=.5)


def test_anonymized_three_board_budget_observation_not_flaky_clock_gate():
    import time
    from almdina_erp.almdina_erp.domain.cutting.final_cut_line_alignment import (
        align_regular_cut_lines,
    )
    sources, plan = _three_sheet_dxf_geometry_witness()
    for seconds in (.15, .50, 1.0):
        diagnostic = {}
        started = time.monotonic()
        result = align_regular_cut_lines(
            plan, sources, 122, 244, .5,
            machine_type="CNC Router", mirroring_allowed=False,
            metric_kwargs=dict(min_remnant_width_cm=30, min_remnant_length_cm=30,
                               min_remnant_area_m2=.09),
            deadline_monotonic=time.monotonic() + seconds,
            diagnostics=diagnostic,
        )
        x = result["sheets"][0]["pieces"][0]["x"]
        print(
            f"DXF_3_BOARD_ALIGNMENT_BUDGET budget_s={seconds:g} "
            f"elapsed_ms={(time.monotonic()-started)*1000:.2f} "
            f"first_x_cm={x:g} diagnostics={diagnostic}",
            flush=True,
        )
        # Timing is diagnostic only; acceptance must remain manufacturing-safe
        # on any CI runner, even where the budget causes a clean no-op.
        assert len(result["sheets"]) == 3
        assert not validate_plan(result, sources, 122, 244, kerf_cm=.5)


def test_factory_budget_zero_disables_alignment_without_changing_raw_seed():
    engine = TwoRowsEngine()
    command = OptimizeOrderPlanCommand(
        engine_version="budget-zero-regression", input_fingerprint="unchanged",
        board=BoardGeometry(100, 100, 0, .5),
        optimizer=OptimizerOptions(
            "smart", "CNC Router", 10, 40, 30, 30, .09,
            alignment_search_budget_sec=0,
        ),
        piece_rows=({"width_cm": 20, "length_cm": 20, "qty": 2},),
        plan_settings=PlanSettings("smart", "CNC Router", 10, 5, 0),
    )
    outcome = optimize_order_plan(command, engine=engine)
    placed = outcome.snapshot["sheets"][0]["pieces"]
    assert placed[0]["x"] != pytest.approx(placed[1]["x"])
    assert engine.original is not None
    assert outcome.snapshot["validation"]["is_valid"]


def test_factory_alignment_budget_metadata_and_security_contract():
    import json
    from pathlib import Path
    from almdina_erp.almdina_erp.domain.security.factory_settings import (
        FactorySettingsSection, SECTION_FIELDS,
    )
    path = (Path(__file__).resolve().parents[1] / "almdina_erp" /
            "doctype" / "almdina_erp_settings" / "almdina_erp_settings.json")
    metadata = json.loads(path.read_text())
    fields = {f["fieldname"]: f for f in metadata["fields"]}
    budget = fields["alignment_search_budget_sec"]
    assert budget["fieldtype"] == "Float"
    assert budget["non_negative"] == 1
    assert float(budget["default"]) > 0
    assert "alignment_search_budget_sec" in SECTION_FIELDS[FactorySettingsSection.CUTTING]


def test_contact_chain_moves_together_when_single_piece_cannot_preserve_shared_cuts():
    """A Kerf-spaced column forms a cut-connected group despite no Y overlap."""
    from almdina_erp.almdina_erp.domain.cutting.final_cut_line_alignment import (
        align_regular_cut_lines, _rectangles,
    )
    sources = expand_piece_groups([dict(width_cm=20, length_cm=10, qty=4)])
    placements = ((3, 0), (3, 10.5), (3, 21), (1, 50))
    placed = [make_placed_piece(p, x, y, 20, 10, False)
              for p, (x, y) in zip(sources, placements)]
    plan = dict(method_key="MaxRects Best Short Side",
                sheets=[dict(sheet_no=1, resource_kind="FULL_BOARD",
                             w=100, h=100, pieces=placed)],
                unplaced=[], used_area_m2=.08,
                total_board_area_m2=1, waste_area_m2=.92)
    plan = enrich_plan_metrics(plan, plan["method_key"], "CNC Router")
    assert not validate_plan(plan, sources, 100, 100, kerf_cm=.5)
    before_profile = _rectangles(plan, .5)
    original = deepcopy(plan)
    result = align_regular_cut_lines(
        plan, sources, 100, 100, .5,
        machine_type="CNC Router", mirroring_allowed=False,
        metric_kwargs=dict(min_remnant_width_cm=30, min_remnant_length_cm=30,
                           min_remnant_area_m2=.09),
    )
    changed = result["sheets"][0]["pieces"]
    # All Kerf-connected regular pieces can be translated as one rigid group
    # while preserving the two shared cutter centers between stacked doors.
    assert [p["x"] for p in changed] == pytest.approx([1, 1, 1, 1])
    assert [p["y"] for p in changed] == pytest.approx([p["y"] for p in placed])
    after_profile = _rectangles(result, .5)
    assert after_profile[0] <= before_profile[0] + .05
    assert after_profile[1] <= before_profile[1]
    assert not validate_plan(result, sources, 100, 100, kerf_cm=.5)
    assert plan == original


def test_protected_adjacent_piece_cannot_lose_existing_shared_cutter_center():
    """The secondary regular-only score must not erase a cut shared with Glass."""
    from almdina_erp.almdina_erp.domain.cutting.final_cut_line_alignment import (
        align_regular_cut_lines,
    )
    sources = expand_piece_groups([
        dict(width_cm=20, length_cm=20, qty=2),
        dict(width_cm=20, length_cm=20, qty=1, piece_type="Glass"),
    ])
    placed = [
        make_placed_piece(sources[0], 3, 10, 20, 20, False),
        make_placed_piece(sources[1], 1, 50, 20, 20, False),
        make_placed_piece(sources[2], 23.5, 10, 20, 20, False),
    ]
    plan = dict(method_key="MaxRects Best Short Side",
                sheets=[dict(sheet_no=1, resource_kind="FULL_BOARD",
                             w=100, h=100, pieces=placed)],
                unplaced=[], used_area_m2=.12,
                total_board_area_m2=1, waste_area_m2=.88)
    plan = enrich_plan_metrics(plan, plan["method_key"], "CNC Router")
    assert not validate_plan(plan, sources, 100, 100, kerf_cm=.5)
    result = align_regular_cut_lines(
        plan, sources, 100, 100, .5,
        machine_type="CNC Router", mirroring_allowed=False,
        metric_kwargs=dict(min_remnant_width_cm=30, min_remnant_length_cm=30,
                           min_remnant_area_m2=.09),
    )
    positions = {p["id"]: p for p in result["sheets"][0]["pieces"]}
    assert positions[1]["x"] == pytest.approx(3)  # cannot break Glass shared contact
    assert positions[3]["x"] == pytest.approx(23.5)
    assert not validate_plan(result, sources, 100, 100, kerf_cm=.5)
