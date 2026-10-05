from __future__ import annotations

import unittest
import math

from almdina_erp.almdina_erp.domain.orders.costing import (
    BreakEdgeCostInput,
    calculate_break_edge_cost,
)


class TestBreakEdgeCosting(unittest.TestCase):
    def test_clipped_corner_pythagorean_geometry(self) -> None:
        """Clipped Corner: remnant sides + diagonal hypotenuse."""
        result = calculate_break_edge_cost(
            BreakEdgeCostInput(
                piece_type="Clipped Corner",
                width_cm=100,
                length_cm=80,
                corner_width_cm=30,
                corner_length_cm=25,
                qty=1,
                edge_break=1,
                break_edge_rate_usd=2.0,
            )
        )

        # length = (100-30) + sqrt(30²+25²) + (80-25)
        #        = 70 + sqrt(1525) + 55
        #        = 70 + 39.051 + 55 = 164.051
        diagonal = math.sqrt(30**2 + 25**2)
        expected_length = 70 + diagonal + 55

        self.assertAlmostEqual(result.break_edge_length_cm, expected_length, places=2)
        self.assertEqual(result.break_edge_meters, 1.641)  # 164.051 / 100 rounded
        self.assertEqual(result.break_edge_rate_usd, 2.0)
        self.assertEqual(result.break_edge_cost_usd, 6.562)  # 1.641 * 2.0 * 2
        self.assertEqual(result.break_edge_unit_price_usd, 6.562)  # cost / qty when qty=1

    def test_l_shaped_corner_inner_notch(self) -> None:
        """L-Shaped Corner: inner notch = two orthogonal segments."""
        result = calculate_break_edge_cost(
            BreakEdgeCostInput(
                piece_type="L-Shaped Corner",
                width_cm=100,
                length_cm=80,
                corner_width_cm=30,
                corner_length_cm=25,
                qty=1,
                edge_break=1,
                break_edge_rate_usd=2.0,
            )
        )

        # length = 30 + 25 = 55
        self.assertEqual(result.break_edge_length_cm, 55)
        self.assertEqual(result.break_edge_meters, 0.55)  # 55 / 100
        self.assertEqual(result.break_edge_rate_usd, 2.0)
        self.assertEqual(result.break_edge_cost_usd, 2.2)  # 0.55 * 2.0 * 2
        self.assertEqual(result.break_edge_unit_price_usd, 2.2)

    def test_rate_doubling(self) -> None:
        """Break edge rate is multiplied by 2."""
        result = calculate_break_edge_cost(
            BreakEdgeCostInput(
                piece_type="L-Shaped Corner",
                width_cm=100,
                length_cm=80,
                corner_width_cm=20,
                corner_length_cm=20,
                qty=1,
                edge_break=1,
                break_edge_rate_usd=1.0,
            )
        )

        # length = 20 + 20 = 40
        # meters = 40 / 100 = 0.4
        # cost = 0.4 * 1.0 * 2 = 0.8
        self.assertEqual(result.break_edge_length_cm, 40)
        self.assertEqual(result.break_edge_cost_usd, 0.8)

    def test_quantity_multiplication(self) -> None:
        """Quantity multiplies the total meters."""
        result = calculate_break_edge_cost(
            BreakEdgeCostInput(
                piece_type="L-Shaped Corner",
                width_cm=100,
                length_cm=80,
                corner_width_cm=30,
                corner_length_cm=25,
                qty=5,
                edge_break=1,
                break_edge_rate_usd=2.0,
            )
        )

        # length per unit = 30 + 25 = 55
        # meters = 55 * 5 / 100 = 2.75
        # cost = 2.75 * 2.0 * 2 = 11.0
        # unit_price = 11.0 / 5 = 2.2
        self.assertEqual(result.break_edge_length_cm, 55)  # per unit
        self.assertEqual(result.break_edge_meters, 2.75)
        self.assertEqual(result.break_edge_cost_usd, 11.0)
        self.assertEqual(result.break_edge_unit_price_usd, 2.2)

    def test_edge_break_off_returns_zeros(self) -> None:
        """When edge_break=0, all values are zero."""
        result = calculate_break_edge_cost(
            BreakEdgeCostInput(
                piece_type="Clipped Corner",
                width_cm=100,
                length_cm=80,
                corner_width_cm=30,
                corner_length_cm=25,
                qty=1,
                edge_break=0,
                break_edge_rate_usd=2.0,
            )
        )

        self.assertEqual(result.break_edge_length_cm, 0)
        self.assertEqual(result.break_edge_meters, 0)
        self.assertEqual(result.break_edge_rate_usd, 0)
        self.assertEqual(result.break_edge_cost_usd, 0)
        self.assertEqual(result.break_edge_unit_price_usd, 0)

    def test_non_corner_piece_returns_zeros(self) -> None:
        """Regular pieces return all zeros even if edge_break=1."""
        result = calculate_break_edge_cost(
            BreakEdgeCostInput(
                piece_type="Regular",
                width_cm=100,
                length_cm=80,
                corner_width_cm=30,
                corner_length_cm=25,
                qty=1,
                edge_break=1,
                break_edge_rate_usd=2.0,
            )
        )

        self.assertEqual(result.break_edge_cost_usd, 0)

    def test_zero_corner_dimensions_returns_zeros(self) -> None:
        """Zero corner dimensions return zeros gracefully."""
        result = calculate_break_edge_cost(
            BreakEdgeCostInput(
                piece_type="Clipped Corner",
                width_cm=100,
                length_cm=80,
                corner_width_cm=0,
                corner_length_cm=0,
                qty=1,
                edge_break=1,
                break_edge_rate_usd=2.0,
            )
        )

        self.assertEqual(result.break_edge_cost_usd, 0)

    def test_zero_quantity_returns_zeros(self) -> None:
        """Zero quantity returns zeros."""
        result = calculate_break_edge_cost(
            BreakEdgeCostInput(
                piece_type="L-Shaped Corner",
                width_cm=100,
                length_cm=80,
                corner_width_cm=30,
                corner_length_cm=25,
                qty=0,
                edge_break=1,
                break_edge_rate_usd=2.0,
            )
        )

        self.assertEqual(result.break_edge_cost_usd, 0)
        self.assertEqual(result.break_edge_unit_price_usd, 0)

    def test_unit_price_calculation(self) -> None:
        """Unit price = total cost / quantity."""
        result = calculate_break_edge_cost(
            BreakEdgeCostInput(
                piece_type="Clipped Corner",
                width_cm=100,
                length_cm=80,
                corner_width_cm=30,
                corner_length_cm=25,
                qty=3,
                edge_break=1,
                break_edge_rate_usd=1.5,
            )
        )

        # length = 70 + sqrt(1525) + 55 ≈ 164.051
        # meters = 164.051 * 3 / 100 ≈ 4.921
        # cost = 4.921 * 1.5 * 2 ≈ 14.763
        # unit_price = 14.763 / 3 ≈ 4.921
        expected_unit_price = result.break_edge_cost_usd / 3
        self.assertAlmostEqual(result.break_edge_unit_price_usd, expected_unit_price, places=2)

    def test_l_shaped_adjacent_sides_reduce_on_corner_dimension(self) -> None:
        """For L-Shaped: adjacent sides are reduced by corner dimensions.

        L-Shaped at Top Right:
        - edge_width_top reduced by corner_width: 100 - 30 = 70 cm
        - edge_long_right reduced by corner_length: 80 - 25 = 55 cm
        """
        # This test documents the expected behavior for remaining edges calculation
        # in the adapter layer. It shows the geometry that should be used.

        # For edge_width_top at rate $1.0:
        # reduced_width = 100 - 30 = 70 cm
        # meters = 70 * 1 / 100 = 0.7 m
        # cost = 0.7 * 1.0 = 0.7 USD

        # For edge_long_right at rate $1.0:
        # reduced_length = 80 - 25 = 55 cm
        # meters = 55 * 1 / 100 = 0.55 m
        # cost = 0.55 * 1.0 = 0.55 USD

        # Total for adjacent sides: 0.7 + 0.55 = 1.25 USD
        # This will be calculated by the adapter, not by domain logic

        # Domain break edge calculation for L-shaped remains unchanged
        result = calculate_break_edge_cost(
            BreakEdgeCostInput(
                piece_type="L-Shaped Corner",
                width_cm=100,
                length_cm=80,
                corner_width_cm=30,
                corner_length_cm=25,
                qty=1,
                edge_break=1,
                break_edge_rate_usd=1.0,
            )
        )

        # L-shaped break edge: 30 + 25 = 55 cm
        self.assertEqual(result.break_edge_length_cm, 55)
        self.assertEqual(result.break_edge_cost_usd, 1.1)  # 0.55 * 1.0 * 2


if __name__ == "__main__":
    unittest.main()
