from __future__ import annotations

import unittest
from typing import Any

from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
    BoardGeometry,
    OptimizeOrderPlanCommand,
    OptimizerOptions,
    optimize_order_plan,
)


class MarginThresholdEngine:
    def __init__(self, *, one_board_width_cm: float) -> None:
        self.one_board_width_cm = one_board_width_cm
        self.optimize_widths: list[float] = []

    def expand_pieces(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                **row,
                "id": index,
                "label": str(index),
                "piece_type": row.get("piece_type") or "Regular",
            }
            for index, row in enumerate(rows, start=1)
        ]

    def optimize(
        self,
        pieces: list[dict[str, Any]],
        board_width_cm: float,
        board_length_cm: float,
        kerf_cm: float,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del kerf_cm, kwargs
        self.optimize_widths.append(board_width_cm)
        required_boards = (
            1
            if board_width_cm + 1e-9 >= self.one_board_width_cm
            else 2
        )
        sheets = [
            {"sheet_no": index, "pieces": []}
            for index in range(1, required_boards + 1)
        ]
        sheets[0]["pieces"] = [dict(piece) for piece in pieces]
        used_area_m2 = sum(
            float(piece["width_cm"]) * float(piece["length_cm"]) / 10000
            for piece in pieces
        )
        total_board_area_m2 = (
            required_boards * board_width_cm * board_length_cm / 10000
        )
        return {
            "method_key": "MarginThreshold",
            "method_label": "Margin Threshold Test",
            "optimization_mode": "Auto Pro",
            "industrial_metrics": {
                "estimated_cut_count": 4,
                "largest_reusable_free_area_m2": 0,
            },
            "used_area_m2": used_area_m2,
            "total_board_area_m2": total_board_area_m2,
            "waste_area_m2": max(0, total_board_area_m2 - used_area_m2),
            "sheets": sheets,
            "unplaced": [],
        }

    def validate(
        self,
        plan: dict[str, Any],
        pieces: list[dict[str, Any]],
        board_width_cm: float,
        board_length_cm: float,
    ) -> list[str]:
        del plan, pieces, board_width_cm, board_length_cm
        return []


class TestAdaptiveCuttingMargin(unittest.TestCase):
    def _command(self, *, trim_cm: float = 1.0) -> OptimizeOrderPlanCommand:
        return OptimizeOrderPlanCommand(
            engine_version="test",
            input_fingerprint="margin-input",
            board=BoardGeometry(
                full_width_cm=122,
                full_length_cm=244,
                trim_cm=trim_cm,
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
            piece_rows=tuple(
                {"width_cm": 30, "length_cm": 10, "qty": 1}
                for _ in range(4)
            ),
        )

    def test_keeps_largest_trim_that_reaches_better_board_count(self) -> None:
        # 4 x 300 mm plus 3 x 4 mm kerfs needs 1212 mm usable width.
        engine = MarginThresholdEngine(one_board_width_cm=121.2)

        outcome = optimize_order_plan(self._command(trim_cm=1.0), engine=engine)

        self.assertEqual(outcome.required_boards, 1)
        self.assertAlmostEqual(outcome.snapshot["trim_cm"], 0.4, places=7)
        self.assertAlmostEqual(
            outcome.snapshot["usable_board_width_cm"],
            121.2,
            places=7,
        )
        self.assertEqual(outcome.snapshot["configured_trim_cm"], 1.0)
        self.assertTrue(outcome.snapshot["trim_adjusted"])

    def test_does_not_reduce_trim_when_zero_trim_cannot_improve_board_count(self) -> None:
        engine = MarginThresholdEngine(one_board_width_cm=123)

        outcome = optimize_order_plan(self._command(trim_cm=1.0), engine=engine)

        self.assertEqual(outcome.required_boards, 2)
        self.assertEqual(outcome.snapshot["trim_cm"], 1.0)
        self.assertFalse(outcome.snapshot["trim_adjusted"])
        self.assertEqual(len(engine.optimize_widths), 2)

    def test_does_not_probe_when_configured_trim_is_already_optimal(self) -> None:
        engine = MarginThresholdEngine(one_board_width_cm=120)

        outcome = optimize_order_plan(self._command(trim_cm=1.0), engine=engine)

        self.assertEqual(outcome.required_boards, 1)
        self.assertEqual(outcome.snapshot["trim_cm"], 1.0)
        self.assertEqual(engine.optimize_widths, [120.0])

    def test_zero_configured_trim_never_triggers_adaptive_search(self) -> None:
        engine = MarginThresholdEngine(one_board_width_cm=123)

        outcome = optimize_order_plan(self._command(trim_cm=0.0), engine=engine)

        self.assertEqual(outcome.snapshot["trim_cm"], 0.0)
        self.assertEqual(len(engine.optimize_widths), 1)


if __name__ == "__main__":
    unittest.main()
