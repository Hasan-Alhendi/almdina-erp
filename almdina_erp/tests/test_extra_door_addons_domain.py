from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.domain.orders.extra_addons import (
    ExtraAddonError,
    ExtraAddonPieceInput,
    ExtraAddonRates,
    calculate_extra_addon_pricing,
)


class TestExtraDoorAddonsDomain(unittest.TestCase):
    def setUp(self) -> None:
        self.rates = ExtraAddonRates(
            double_usd=4,
            liner_usd=2.5,
            recessed_handle_cutout_usd=1.25,
        )

    def test_selected_addons_are_itemized_and_multiplied_by_door_quantity(self) -> None:
        summary = calculate_extra_addon_pricing(
            [
                ExtraAddonPieceInput(
                    piece_type="Extra",
                    qty=3,
                    notes="تنفيذ حسب الطلب",
                    double=True,
                    liner=True,
                )
            ],
            rates=self.rates,
        )

        piece = summary.pieces[0]
        self.assertEqual(piece.selected_codes, ("double", "liner"))
        self.assertEqual(piece.double_unit_price_usd, 4)
        self.assertEqual(piece.double_total_usd, 12)
        self.assertEqual(piece.liner_unit_price_usd, 2.5)
        self.assertEqual(piece.liner_total_usd, 7.5)
        self.assertEqual(piece.recessed_handle_cutout_total_usd, 0)
        self.assertEqual(piece.total_usd, 19.5)
        self.assertEqual(summary.total_usd, 19.5)

    def test_extra_requires_at_least_one_addon_and_notes(self) -> None:
        with self.assertRaisesRegex(ExtraAddonError, "extra_addon_required"):
            calculate_extra_addon_pricing(
                [ExtraAddonPieceInput(piece_type="Extra", qty=1, notes="ملاحظة")],
                rates=self.rates,
            )
        with self.assertRaisesRegex(ExtraAddonError, "extra_notes_required"):
            calculate_extra_addon_pricing(
                [ExtraAddonPieceInput(piece_type="Extra", qty=1, liner=True)],
                rates=self.rates,
            )

    def test_special_liner_stays_in_notes_and_never_uses_extra_pricing(self) -> None:
        summary = calculate_extra_addon_pricing(
            [
                ExtraAddonPieceInput(
                    piece_type="Special",
                    qty=1,
                    notes="لاينر — السعر الخاص شامل",
                )
            ],
            rates=self.rates,
        )
        self.assertFalse(summary.pieces[0].applicable)
        self.assertEqual(summary.total_usd, 0)

        with self.assertRaisesRegex(ExtraAddonError, "non_extra_addon_selection"):
            calculate_extra_addon_pricing(
                [
                    ExtraAddonPieceInput(
                        piece_type="Special",
                        qty=1,
                        notes="لاينر",
                        liner=True,
                    )
                ],
                rates=self.rates,
            )

    def test_selected_addon_requires_a_configured_positive_price(self) -> None:
        with self.assertRaisesRegex(ExtraAddonError, "extra_addon_rate_not_configured") as raised:
            calculate_extra_addon_pricing(
                [
                    ExtraAddonPieceInput(
                        piece_type="Extra",
                        qty=1,
                        notes="ملاحظة",
                        liner=True,
                    )
                ],
                rates=ExtraAddonRates(),
            )
        self.assertEqual(raised.exception.addon_code, "liner")

    def test_existing_selected_addon_preserves_its_historical_unit_price(self) -> None:
        summary = calculate_extra_addon_pricing(
            [
                ExtraAddonPieceInput(
                    piece_type="Extra",
                    qty=3,
                    notes="ملاحظة",
                    liner=True,
                    liner_snapshot_unit_price_usd=2.5,
                )
            ],
            rates=ExtraAddonRates(liner_usd=9),
        )

        self.assertEqual(summary.pieces[0].liner_unit_price_usd, 2.5)
        self.assertEqual(summary.pieces[0].liner_total_usd, 7.5)


if __name__ == "__main__":
    unittest.main()
