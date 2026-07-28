from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.domain.orders.costing import (
    CostingError,
    PieceCostInput,
    SpecialPricingPieceInput,
    SpecialPricingSettings,
    calculate_order_costs,
    calculate_piece_costs,
    calculate_special_pricing,
    calculate_waste,
    round_value,
)


class TestOrderCostingDomain(unittest.TestCase):
    def test_rounding_preserves_legacy_half_away_from_zero(self) -> None:
        self.assertEqual(round_value(1.2345, 3), 1.235)
        self.assertEqual(round_value(-1.2345, 3), -1.235)

    def test_piece_measurements_and_edge_costs(self) -> None:
        summary = calculate_piece_costs(
            [
                PieceCostInput(
                    width_cm=60,
                    length_cm=80,
                    qty=2,
                    edge_long_right=1,
                    edge_long_left=1,
                    edge_width_top=1,
                    edge_width_bottom=0,
                    edge_type="",
                ),
                PieceCostInput(
                    width_cm=40,
                    length_cm=100,
                    qty=1,
                    edge_long_right=1,
                    edge_long_left=0,
                    edge_width_top=0,
                    edge_width_bottom=0,
                    edge_type="4cm",
                ),
            ],
            default_edge_type="2cm",
            edge_rates={"2cm": 0.5, "4cm": 1.0},
        )

        self.assertEqual(summary.pieces[0].area_m2, 0.96)
        self.assertEqual(summary.pieces[0].edge_meters, 4.4)
        self.assertEqual(summary.pieces[0].edge_rate_usd, 0.5)
        self.assertEqual(summary.pieces[0].edge_cost_usd, 2.2)
        self.assertEqual(summary.pieces[1].area_m2, 0.4)
        self.assertEqual(summary.pieces[1].edge_meters, 1.0)
        self.assertEqual(summary.pieces[1].edge_cost_usd, 1.0)
        self.assertEqual(summary.total_area_m2, 1.36)
        self.assertEqual(summary.total_edge_meters, 5.4)
        self.assertEqual(summary.total_edge_cost_usd, 3.2)

    def test_board_cutting_and_waste_summary(self) -> None:
        costs = calculate_order_costs(
            required_boards=3,
            board_rate_usd=20,
            cutting_cost_per_board_usd=4.5,
            edge_cost_usd=3.2,
        )
        waste = calculate_waste(waste_area_m2=1.25, total_board_area_m2=8.9292)

        self.assertEqual(costs.mdf_cost_usd, 60)
        self.assertEqual(costs.cutting_cost_usd, 13.5)
        self.assertEqual(costs.total_cost_usd, 76.7)
        self.assertEqual(waste.waste_area_m2, 1.25)
        self.assertEqual(waste.waste_percent, 14.0)

    def test_automatic_quote_without_special_pieces(self) -> None:
        summary = calculate_special_pricing(
            [
                SpecialPricingPieceInput(
                    piece_type="Regular",
                    qty=2,
                    area_m2=0.96,
                    edge_cost_usd=2.2,
                )
            ],
            settings=SpecialPricingSettings(),
            total_area_m2=0.96,
            board_and_cutting_cost_usd=30,
            total_cost_usd=32.2,
        )

        self.assertEqual(summary.customer_quote_status, "Automatic")
        self.assertEqual(summary.customer_quote_total_usd, 32.2)
        self.assertFalse(summary.pieces[0].applicable)
        self.assertEqual(summary.pieces[0].price_status, "Not Applicable")

    def test_estimated_special_price_allocates_board_cost_by_area(self) -> None:
        summary = calculate_special_pricing(
            [
                SpecialPricingPieceInput(
                    piece_type="Regular",
                    qty=1,
                    area_m2=1.0,
                    edge_cost_usd=2,
                ),
                SpecialPricingPieceInput(
                    piece_type="Special",
                    qty=2,
                    area_m2=1.0,
                    edge_cost_usd=3,
                    price_status="Estimated",
                ),
            ],
            settings=SpecialPricingSettings(
                design_fee_usd=2,
                cnc_fee_usd=3,
                manual_edge_fee_usd=1,
                margin_percent=10,
            ),
            total_area_m2=2.0,
            board_and_cutting_cost_usd=40,
            total_cost_usd=45,
        )

        special = summary.pieces[1]
        self.assertEqual(special.estimated_unit_price_usd, 19.25)
        self.assertEqual(special.final_unit_price_usd, 19.25)
        self.assertEqual(special.price_status, "Estimated")
        self.assertEqual(summary.baseline_cost_usd, 23)
        self.assertEqual(summary.estimated_total_usd, 38.5)
        self.assertEqual(summary.final_total_usd, 38.5)
        self.assertEqual(summary.customer_quote_total_usd, 80.5)
        self.assertEqual(summary.customer_quote_status, "Estimated")

    def test_approved_special_price_is_preserved(self) -> None:
        summary = calculate_special_pricing(
            [
                SpecialPricingPieceInput(
                    piece_type="Special",
                    qty=2,
                    area_m2=1.0,
                    edge_cost_usd=3,
                    price_status="Approved",
                    approved_by="accounts@example.com",
                    custom_unit_price_usd=25,
                )
            ],
            settings=SpecialPricingSettings(),
            total_area_m2=1.0,
            board_and_cutting_cost_usd=20,
            total_cost_usd=23,
        )

        self.assertTrue(summary.pieces[0].preserve_approval)
        self.assertEqual(summary.pieces[0].final_unit_price_usd, 25)
        self.assertEqual(summary.final_total_usd, 50)
        self.assertEqual(summary.customer_quote_total_usd, 70)
        self.assertEqual(summary.customer_quote_status, "Approved")

    def test_negative_special_defaults_are_rejected(self) -> None:
        with self.assertRaisesRegex(CostingError, "special_shape_defaults_negative"):
            calculate_special_pricing(
                [],
                settings=SpecialPricingSettings(design_fee_usd=-1),
                total_area_m2=0,
                board_and_cutting_cost_usd=0,
                total_cost_usd=0,
            )


if __name__ == "__main__":
    unittest.main()
