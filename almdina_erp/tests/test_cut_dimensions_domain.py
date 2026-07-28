from __future__ import annotations

import math
import unittest

from almdina_erp.almdina_erp.domain.orders.cut_dimensions import (
    CutDimensionError,
    CutDimensionInput,
    calculate_cut_dimensions,
)


class TestCutDimensionsDomain(unittest.TestCase):
    def test_one_long_edge_deducts_thickness_from_width(self) -> None:
        result = calculate_cut_dimensions(
            CutDimensionInput(
                final_width_cm=30,
                final_length_cm=50,
                edge_thickness_mm=1,
                edge_long_right=1,
            )
        )

        self.assertEqual(result.cut_width_cm, 29.9)
        self.assertEqual(result.cut_length_cm, 50)
        self.assertEqual(result.width_deduction_mm, 1)
        self.assertEqual(result.length_deduction_mm, 0)

    def test_one_width_edge_deducts_thickness_from_length(self) -> None:
        result = calculate_cut_dimensions(
            CutDimensionInput(
                final_width_cm=30,
                final_length_cm=50,
                edge_thickness_mm=1,
                edge_width_top=1,
            )
        )

        self.assertEqual(result.cut_width_cm, 30)
        self.assertEqual(result.cut_length_cm, 49.9)

    def test_all_edges_deduct_twice_from_each_dimension(self) -> None:
        result = calculate_cut_dimensions(
            CutDimensionInput(
                final_width_cm=30,
                final_length_cm=50,
                edge_thickness_mm=2,
                edge_long_right=1,
                edge_long_left=1,
                edge_width_top=1,
                edge_width_bottom=1,
            )
        )

        self.assertEqual(result.cut_width_cm, 29.6)
        self.assertEqual(result.cut_length_cm, 49.6)
        self.assertEqual(result.width_deduction_mm, 4)
        self.assertEqual(result.length_deduction_mm, 4)

    def test_no_selected_edges_preserves_finished_size(self) -> None:
        result = calculate_cut_dimensions(
            CutDimensionInput(
                final_width_cm=30,
                final_length_cm=50,
                edge_thickness_mm=2,
            )
        )

        self.assertEqual(result.cut_width_cm, 30)
        self.assertEqual(result.cut_length_cm, 50)

    def test_invalid_results_are_rejected(self) -> None:
        with self.assertRaisesRegex(CutDimensionError, "cut_width_not_positive"):
            calculate_cut_dimensions(
                CutDimensionInput(
                    final_width_cm=0.1,
                    final_length_cm=50,
                    edge_thickness_mm=1,
                    edge_long_right=1,
                )
            )

        with self.assertRaisesRegex(CutDimensionError, "edge_thickness_not_finite"):
            calculate_cut_dimensions(
                CutDimensionInput(
                    final_width_cm=30,
                    final_length_cm=50,
                    edge_thickness_mm=math.inf,
                )
            )


if __name__ == "__main__":
    unittest.main()
