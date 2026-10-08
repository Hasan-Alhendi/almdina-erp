from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.domain.orders.extra_addons import (
    EXTRA_ADDON_FIELD_BY_CODE,
    ExtraAddonError,
    ExtraAddonPieceInput,
    ExtraAddonRates,
    apply_extra_double_text_flags_to_snapshot,
    calculate_extra_addon_pricing,
    extra_double_text_flags,
    extra_overlay_kind_for_layer,
    extra_overlay_layer_for_kind,
    physical_cut_quantity,
)


PIECE_TYPES = ("Regular", "Clipped Corner", "L-Shaped Corner", "Special")


class TestExtraDoorAddonsDomain(unittest.TestCase):
    def setUp(self) -> None:
        self.rates = ExtraAddonRates(
            double_usd=4,
            full_door_double_usd=6,
            liner_usd=2.5,
            back_groove_usd=3,
            recessed_handle_cutout_usd=1.25,
        )

    def test_addons_are_independent_of_all_four_piece_types(self) -> None:
        summary = calculate_extra_addon_pricing(
            [
                ExtraAddonPieceInput(
                    piece_type=piece_type,
                    qty=2,
                    liner=True,
                    back_groove=True,
                    recessed_handle_cutout=True,
                )
                for piece_type in PIECE_TYPES
            ],
            rates=self.rates,
        )
        self.assertEqual(summary.total_usd, 54)
        for piece in summary.pieces:
            self.assertTrue(piece.applicable)
            self.assertEqual(
                piece.selected_codes,
                ("liner", "back_groove", "recessed_handle_cutout"),
            )
            self.assertEqual(piece.total_usd, 13.5)

    def test_no_addon_and_no_notes_are_valid_for_every_type(self) -> None:
        summary = calculate_extra_addon_pricing(
            [ExtraAddonPieceInput(piece_type=piece_type, qty=1) for piece_type in PIECE_TYPES],
            rates=self.rates,
        )
        self.assertEqual(summary.total_usd, 0)
        self.assertTrue(all(not piece.applicable for piece in summary.pieces))

    def test_double_options_are_mutually_exclusive_server_side(self) -> None:
        with self.assertRaisesRegex(ExtraAddonError, "mutually_exclusive_double_addons"):
            calculate_extra_addon_pricing(
                [
                    ExtraAddonPieceInput(
                        piece_type="Special",
                        qty=1,
                        double=True,
                        full_door_double=True,
                    )
                ],
                rates=self.rates,
            )

    def test_selected_addon_requires_a_configured_positive_price(self) -> None:
        with self.assertRaisesRegex(ExtraAddonError, "extra_addon_rate_not_configured") as raised:
            calculate_extra_addon_pricing(
                [ExtraAddonPieceInput(piece_type="Regular", qty=1, liner=True)],
                rates=ExtraAddonRates(),
            )
        self.assertEqual(raised.exception.addon_code, "liner")

    def test_historical_snapshot_is_preserved_independently_of_piece_type(self) -> None:
        summary = calculate_extra_addon_pricing(
            [
                ExtraAddonPieceInput(
                    piece_type="L-Shaped Corner",
                    qty=3,
                    liner=True,
                    liner_snapshot_unit_price_usd=2.5,
                )
            ],
            rates=ExtraAddonRates(liner_usd=9),
        )
        self.assertEqual(summary.pieces[0].liner_unit_price_usd, 2.5)
        self.assertEqual(summary.pieces[0].liner_total_usd, 7.5)

    def test_full_door_double_fee_uses_original_quantity(self) -> None:
        summary = calculate_extra_addon_pricing(
            [
                ExtraAddonPieceInput(
                    piece_type="Clipped Corner",
                    qty=3,
                    full_door_double=True,
                    liner=True,
                )
            ],
            rates=self.rates,
        )
        piece = summary.pieces[0]
        self.assertEqual(piece.full_door_double_total_usd, 18)
        self.assertEqual(piece.liner_total_usd, 7.5)
        self.assertEqual(piece.total_usd, 25.5)

    def test_physical_quantity_doubles_only_for_full_door_double(self) -> None:
        self.assertEqual(physical_cut_quantity(3, full_door_double=True), 6)
        self.assertEqual(physical_cut_quantity(3, full_door_double=False), 3)
        self.assertEqual(physical_cut_quantity(0, full_door_double=True), 0)

    def test_overlay_layer_mapping_is_stable(self) -> None:
        self.assertEqual(extra_overlay_kind_for_layer(" liner "), "liner")
        self.assertEqual(extra_overlay_kind_for_layer("Rear Groove"), "back_groove")
        self.assertEqual(extra_overlay_kind_for_layer("HANDLE RECESS"), "recessed_handle_cutout")
        self.assertIsNone(extra_overlay_kind_for_layer("CUT_PATH"))
        self.assertEqual(extra_overlay_layer_for_kind("liner"), "Liner")
        self.assertEqual(EXTRA_ADDON_FIELD_BY_CODE["liner"], "extra_liner")

    def test_double_text_flags_apply_to_any_piece_type(self) -> None:
        self.assertEqual(
            extra_double_text_flags(extra_double=True, extra_full_door_double=False),
            {"extra_double": 1},
        )
        snapshot = apply_extra_double_text_flags_to_snapshot(
            {
                "sheets": [
                    {
                        "pieces": [
                            {"label": "1.1", "piece_type": "Special"},
                            {"label": "2.1", "piece_type": "Regular"},
                        ]
                    }
                ]
            },
            [
                {"piece_type": "Special", "extra_double": 1},
                {"piece_type": "Regular", "extra_full_door_double": 1},
            ],
        )
        first, second = snapshot["sheets"][0]["pieces"]
        self.assertEqual(first["extra_double"], 1)
        self.assertEqual(second["extra_full_door_double"], 1)


if __name__ == "__main__":
    unittest.main()
