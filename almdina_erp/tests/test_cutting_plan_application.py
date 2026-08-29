from __future__ import annotations

import copy
import unittest
from typing import Any

from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
    BoardGeometry,
    OptimizeOrderPlanCommand,
    OptimizerOptions,
    optimize_order_plan,
)
from almdina_erp.almdina_erp.application.cutting.plan_reuse import (
    PlanReuseContext,
    decide_plan_reuse,
    plan_invalidation_state,
)
from almdina_erp.almdina_erp.application.cutting.refresh_plan_metadata import (
    refresh_plan_metadata,
)
from almdina_erp.almdina_erp.domain.cutting.adaptive_trim import (
    AppliedTrim,
    PlanQuality,
    resolve_adaptive_trim,
)


class FakeCuttingEngine:
    def __init__(self, validation_errors: list[str] | None = None) -> None:
        self.validation_errors = validation_errors or []
        self.optimize_call: dict[str, Any] | None = None

    def expand_pieces(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "id": 1,
                "label": "1.1",
                "source_piece_no": 1,
                "copy_no": 1,
                "group_qty": 1,
                "width_cm": rows[0]["width_cm"],
                "length_cm": rows[0]["length_cm"],
                "piece_type": "Special",
                "notes": "old",
                "edge_type": "2cm",
            },
            {
                "id": 2,
                "label": "2.1",
                "source_piece_no": 2,
                "copy_no": 1,
                "group_qty": 1,
                "width_cm": rows[1]["width_cm"],
                "length_cm": rows[1]["length_cm"],
                "piece_type": "Regular",
            },
        ]

    def optimize(
        self,
        pieces: list[dict[str, Any]],
        board_width_cm: float,
        board_length_cm: float,
        kerf_cm: float,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.optimize_call = {
            "pieces": pieces,
            "board_width_cm": board_width_cm,
            "board_length_cm": board_length_cm,
            "kerf_cm": kerf_cm,
            **kwargs,
        }
        return {
            "method_key": "Test",
            "method_label": "Test Engine",
            "ordering_strategy": "area_desc",
            "optimization_mode": "Auto Pro",
            "score": 10,
            "industrial_metrics": {
                "estimated_cut_count": 4,
                "largest_reusable_free_area_m2": 0.75,
            },
            "industrial_rank": [1, 2, 3],
            "attempts": 7,
            "search_elapsed_sec": 0.25,
            "search_time_limit_sec": 10,
            "solver_status": "HEURISTIC",
            "solver_wall_time_sec": 0,
            "used_area_m2": 3,
            "total_board_area_m2": 4,
            "waste_area_m2": 1,
            "sheets": [
                {
                    "sheet_no": 1,
                    "pieces": [
                        {"id": 1, "label": "1.1", "piece_type": "Special"},
                        {"id": 2, "label": "2.1", "piece_type": "Regular"},
                    ],
                }
            ],
            "unplaced": [],
        }

    def validate(
        self,
        plan: dict[str, Any],
        pieces: list[dict[str, Any]],
        board_width_cm: float,
        board_length_cm: float,
    ) -> list[str]:
        return list(self.validation_errors)


class AdaptiveTrimGeometryEngine:
    """Small deterministic geometry engine used only for Adaptive Trim regressions."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def expand_pieces(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [dict(row) for row in rows]

    def optimize(
        self,
        pieces: list[dict[str, Any]],
        board_width_cm: float,
        board_length_cm: float,
        kerf_cm: float,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "board_width_cm": board_width_cm,
                "board_length_cm": board_length_cm,
                "kerf_cm": kerf_cm,
                "selected_mode": kwargs["selected_mode"],
            }
        )
        max_length = max((float(piece["length_cm"]) for piece in pieces), default=0.0)
        row_width = sum(float(piece["width_cm"]) for piece in pieces)
        if len(pieces) > 1:
            row_width += kerf_cm * (len(pieces) - 1)
        fits = (
            max_length <= board_length_cm + 1e-9
            and row_width <= board_width_cm + 1e-9
        )
        sheets = [{"sheet_no": 1, "pieces": pieces}] if fits and pieces else []
        unplaced = [] if fits else pieces
        source_area = (
            board_width_cm * board_length_cm / 10_000 if sheets else 0.0
        )
        used_area = (
            sum(
                float(piece["width_cm"]) * float(piece["length_cm"])
                for piece in pieces
            )
            / 10_000
            if fits
            else 0.0
        )
        return {
            "method_key": "geometry-test",
            "method_label": "Geometry Test",
            "optimization_mode": kwargs["selected_mode"],
            "industrial_metrics": {},
            "used_area_m2": used_area,
            "total_board_area_m2": source_area,
            "waste_area_m2": max(0.0, source_area - used_area),
            "sheets": sheets,
            "unplaced": unplaced,
        }

    def validate(
        self,
        plan: dict[str, Any],
        pieces: list[dict[str, Any]],
        board_width_cm: float,
        board_length_cm: float,
    ) -> list[str]:
        return []


class TestOptimizeOrderPlan(unittest.TestCase):
    def _command(self) -> OptimizeOrderPlanCommand:
        return OptimizeOrderPlanCommand(
            engine_version="2.1.0-fast-save",
            input_fingerprint="input-hash",
            board=BoardGeometry(
                full_width_cm=122,
                full_length_cm=244,
                trim_cm=1,
                kerf_cm=0.4,
            ),
            optimizer=OptimizerOptions(
                selected_mode="Auto Pro",
                machine_type="Panel Saw",
                time_limit_sec=10,
                exact_piece_limit=40,
                min_remnant_width_cm=15,
                min_remnant_length_cm=30,
                min_remnant_area_m2=0.08,
            ),
            piece_rows=(
                {"width_cm": 60, "length_cm": 80, "qty": 1},
                {"width_cm": 40, "length_cm": 100, "qty": 1},
            ),
        )

    def test_orchestrates_engine_and_builds_persisted_snapshot(self) -> None:
        engine = FakeCuttingEngine()
        outcome = optimize_order_plan(self._command(), engine=engine)

        self.assertIsNotNone(engine.optimize_call)
        assert engine.optimize_call is not None
        self.assertEqual(engine.optimize_call["board_width_cm"], 120)
        self.assertEqual(engine.optimize_call["board_length_cm"], 242)
        self.assertEqual(engine.optimize_call["kerf_cm"], 0.4)
        self.assertEqual(engine.optimize_call["machine_type"], "Panel Saw")
        self.assertEqual(engine.optimize_call["exact_piece_limit"], 40)

        snapshot = outcome.snapshot
        self.assertEqual(snapshot["engine_version"], "2.1.0-fast-save")
        self.assertEqual(snapshot["input_fingerprint"], "input-hash")
        self.assertEqual(snapshot["full_board_width_cm"], 122)
        self.assertEqual(snapshot["usable_board_width_cm"], 120)
        self.assertEqual(snapshot["full_board_length_cm"], 244)
        self.assertEqual(snapshot["usable_board_length_cm"], 242)
        self.assertEqual(snapshot["method_key"], "Test")
        self.assertTrue(snapshot["validation"]["is_valid"])
        self.assertEqual(snapshot["validation"]["errors"], [])
        self.assertEqual(
            snapshot["special_shape_raw_summary"],
            {"requested": 1, "placed": 1, "unplaced": 0, "complete": True},
        )
        self.assertEqual(outcome.required_boards, 1)
        self.assertEqual(
            outcome.packing_score,
            "ألواح: 1 | هدر: 25.0% | قصات تقديرية: 4 | "
            "أكبر بقايا مفيدة: 0.75 م² | محاولات: 7 | الخوارزمية: Test Engine",
        )

    def test_validation_errors_are_persisted_without_being_hidden(self) -> None:
        outcome = optimize_order_plan(
            self._command(),
            engine=FakeCuttingEngine(["Pieces overlap"]),
        )
        self.assertFalse(outcome.snapshot["validation"]["is_valid"])
        self.assertEqual(outcome.snapshot["validation"]["errors"], ["Pieces overlap"])


class TestAdaptiveTrimBusinessRule(unittest.TestCase):
    @staticmethod
    def _piece(width: float, length: float, piece_id: int = 1) -> dict[str, Any]:
        return {
            "id": piece_id,
            "width_cm": width,
            "length_cm": length,
            "piece_type": "Regular",
        }

    def _command(
        self,
        pieces: tuple[dict[str, Any], ...],
        *,
        mode: str = "maxrects",
        kerf_cm: float = 0.3,
    ) -> OptimizeOrderPlanCommand:
        return OptimizeOrderPlanCommand(
            engine_version="almadina-138-test",
            input_fingerprint="adaptive-trim-contract",
            board=BoardGeometry(
                full_width_cm=122,
                full_length_cm=244,
                trim_cm=0.5,
                kerf_cm=kerf_cm,
            ),
            optimizer=OptimizerOptions(
                selected_mode=mode,
                machine_type="Auto",
                time_limit_sec=10,
                exact_piece_limit=40,
                min_remnant_width_cm=0,
                min_remnant_length_cm=0,
                min_remnant_area_m2=0,
            ),
            piece_rows=pieces,
        )

    def test_preferred_trim_remains_when_it_already_works(self) -> None:
        engine = AdaptiveTrimGeometryEngine()
        outcome = optimize_order_plan(
            self._command((self._piece(30, 100),)),
            engine=engine,
        )

        self.assertEqual(outcome.snapshot["trim_policy"]["mode"], "preferred")
        self.assertEqual(outcome.snapshot["trim_policy"]["relaxed_axes"], [])
        self.assertEqual(outcome.snapshot["trim_policy"]["applied_width_trim_mm"], 5)
        self.assertEqual(outcome.snapshot["trim_policy"]["applied_length_trim_mm"], 5)
        self.assertEqual(len(engine.calls), 1)

    def test_full_length_piece_relaxes_only_length_with_same_mode_and_kerf(self) -> None:
        engine = AdaptiveTrimGeometryEngine()
        outcome = optimize_order_plan(
            self._command((self._piece(30, 244),), mode="maxrects", kerf_cm=0.3),
            engine=engine,
        )

        policy = outcome.snapshot["trim_policy"]
        self.assertEqual(policy["applied_width_trim_mm"], 5)
        self.assertEqual(policy["applied_length_trim_mm"], 0)
        self.assertEqual(policy["relaxed_axes"], ["length"])
        self.assertTrue(engine.calls)
        self.assertTrue(all(call["selected_mode"] == "maxrects" for call in engine.calls))
        self.assertTrue(all(abs(call["kerf_cm"] - 0.3) < 1e-9 for call in engine.calls))

    def test_full_width_piece_relaxes_only_width(self) -> None:
        outcome = optimize_order_plan(
            self._command((self._piece(122, 30),)),
            engine=AdaptiveTrimGeometryEngine(),
        )
        policy = outcome.snapshot["trim_policy"]
        self.assertEqual(policy["applied_width_trim_mm"], 0)
        self.assertEqual(policy["applied_length_trim_mm"], 5)
        self.assertEqual(policy["relaxed_axes"], ["width"])

    def test_full_board_piece_relaxes_both_axes(self) -> None:
        outcome = optimize_order_plan(
            self._command((self._piece(122, 244),)),
            engine=AdaptiveTrimGeometryEngine(),
        )
        policy = outcome.snapshot["trim_policy"]
        self.assertEqual(policy["applied_width_trim_mm"], 0)
        self.assertEqual(policy["applied_length_trim_mm"], 0)
        self.assertEqual(policy["relaxed_axes"], ["width", "length"])

    def test_largest_feasible_three_mm_trim_is_preserved(self) -> None:
        preferred = AppliedTrim(0.5, 0.5)

        def evaluate(trim: AppliedTrim) -> PlanQuality:
            if trim.length_trim_cm <= 0.3 + 1e-9:
                return PlanQuality(0, 1)
            return PlanQuality(1, 0)

        first = resolve_adaptive_trim(
            preferred=preferred,
            preferred_quality=PlanQuality(1, 0),
            evaluate=evaluate,
            has_pieces=True,
            physical_board_lower_bound=1,
        )
        second = resolve_adaptive_trim(
            preferred=preferred,
            preferred_quality=PlanQuality(1, 0),
            evaluate=evaluate,
            has_pieces=True,
            physical_board_lower_bound=1,
        )

        self.assertEqual(first, second)
        self.assertAlmostEqual(first.applied.width_trim_cm, 0.5)
        self.assertAlmostEqual(first.applied.length_trim_cm, 0.3)
        self.assertEqual(first.relaxed_axes, ("length",))

    def test_four_full_length_30cm_pieces_fit_with_real_kerf(self) -> None:
        pieces = tuple(
            self._piece(30, 244, piece_id=index)
            for index in range(1, 5)
        )
        outcome = optimize_order_plan(
            self._command(pieces, kerf_cm=0.3),
            engine=AdaptiveTrimGeometryEngine(),
        )

        self.assertEqual(outcome.required_boards, 1)
        self.assertTrue(outcome.snapshot["validation"]["is_valid"])
        self.assertEqual(outcome.snapshot["trim_policy"]["applied_width_trim_mm"], 5)
        self.assertEqual(outcome.snapshot["trim_policy"]["applied_length_trim_mm"], 0)
        usable_width = outcome.snapshot["usable_board_width_cm"]
        self.assertAlmostEqual(usable_width, 121)
        self.assertLessEqual(4 * 30 + 3 * 0.3, usable_width)


class TestPlanReusePolicy(unittest.TestCase):
    def test_stored_hash_fast_path(self) -> None:
        self.assertTrue(
            decide_plan_reuse(
                PlanReuseContext(
                    has_plan_json=True,
                    has_snapshot_sheets=False,
                    requested_input_fingerprint="same",
                    stored_input_fingerprint="same",
                )
            ).reuse
        )
        changed = decide_plan_reuse(
            PlanReuseContext(
                has_plan_json=True,
                has_snapshot_sheets=True,
                requested_input_fingerprint="new",
                stored_input_fingerprint="old",
            )
        )
        self.assertFalse(changed.reuse)
        self.assertEqual(changed.reason, "stored_hash_changed")

    def test_snapshot_and_legacy_paths(self) -> None:
        snapshot = decide_plan_reuse(
            PlanReuseContext(
                has_plan_json=True,
                has_snapshot_sheets=True,
                requested_input_fingerprint="same",
                snapshot_input_fingerprint="same",
            )
        )
        self.assertTrue(snapshot.reuse)

        probe = decide_plan_reuse(
            PlanReuseContext(
                has_plan_json=True,
                has_snapshot_sheets=True,
                requested_input_fingerprint="same",
                has_legacy_plan=True,
            )
        )
        self.assertTrue(probe.needs_legacy_fingerprint)

        legacy = decide_plan_reuse(
            PlanReuseContext(
                has_plan_json=True,
                has_snapshot_sheets=True,
                requested_input_fingerprint="same",
                has_legacy_plan=True,
                legacy_input_fingerprint="same",
            )
        )
        self.assertTrue(legacy.reuse)

    def test_missing_sheets_never_reuses_plan(self) -> None:
        decision = decide_plan_reuse(
            PlanReuseContext(
                has_plan_json=True,
                has_snapshot_sheets=False,
                requested_input_fingerprint="hash",
            )
        )
        self.assertFalse(decision.reuse)
        self.assertEqual(decision.reason, "missing_snapshot_sheets")

    def test_invalidation_state_resets_plan_geometry_only(self) -> None:
        state = plan_invalidation_state(engine_version="v-test")
        self.assertEqual(state["plan_needs_recalculation"], 1)
        self.assertEqual(state["cutting_plan_json"], "")
        self.assertEqual(state["calculated_plan_input_hash"], "")
        self.assertEqual(state["calculated_plan_metadata_hash"], "")
        self.assertEqual(state["packing_score"], "خطة القص تحتاج إعادة حساب")
        self.assertEqual(state["engine_version"], "v-test")
        # Invoice continuity: last board/cost totals must survive ordinary saves
        # that only invalidate placement geometry.
        for fieldname in (
            "required_boards",
            "waste_area_m2",
            "waste_percent",
            "mdf_cost_usd",
            "cutting_cost_usd",
            "total_cost_usd",
        ):
            self.assertNotIn(fieldname, state)


class TestPlanMetadataRefresh(unittest.TestCase):
    def test_refreshes_metadata_without_mutating_layout_or_source_snapshot(self) -> None:
        original = {
            "input_fingerprint": "old-input",
            "metadata_fingerprint": "old-meta",
            "sheets": [
                {
                    "sheet_no": 1,
                    "pieces": [
                        {
                            "id": 1,
                            "x": 10,
                            "y": 20,
                            "w": 60,
                            "h": 80,
                            "notes": "old",
                            "edge_type": "old-edge",
                        }
                    ],
                }
            ],
        }
        source_copy = copy.deepcopy(original)

        refreshed = refresh_plan_metadata(
            original,
            expanded_pieces=[
                {
                    "id": 1,
                    "label": "1.1",
                    "notes": "new",
                    "edge_type": "2cm",
                    "edge_rate_usd": 0.5,
                    "edge_cost_usd": 1.4,
                }
            ],
            input_fingerprint="new-input",
            metadata_fingerprint="new-meta",
        )

        self.assertEqual(original, source_copy)
        placed = refreshed["sheets"][0]["pieces"][0]
        self.assertEqual((placed["x"], placed["y"], placed["w"], placed["h"]), (10, 20, 60, 80))
        self.assertEqual(placed["notes"], "new")
        self.assertEqual(placed["edge_type"], "2cm")
        self.assertEqual(placed["edge_cost_usd"], 1.4)
        self.assertEqual(refreshed["input_fingerprint"], "new-input")
        self.assertEqual(refreshed["metadata_fingerprint"], "new-meta")


if __name__ == "__main__":
    unittest.main()
