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
                        {"id": 1, "label": "1.1"},
                        {"id": 2, "label": "2.1"},
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

    def test_invalidation_state_resets_all_plan_outputs(self) -> None:
        state = plan_invalidation_state(engine_version="v-test")
        self.assertEqual(state["plan_needs_recalculation"], 1)
        self.assertEqual(state["cutting_plan_json"], "")
        self.assertEqual(state["calculated_plan_input_hash"], "")
        self.assertEqual(state["calculated_plan_metadata_hash"], "")
        self.assertEqual(state["required_boards"], 0)
        self.assertEqual(state["packing_score"], "خطة القص تحتاج إعادة حساب")
        self.assertEqual(state["engine_version"], "v-test")


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
