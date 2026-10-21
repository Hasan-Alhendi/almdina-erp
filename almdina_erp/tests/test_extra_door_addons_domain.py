from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.domain.cutting.primitives import expand_piece_groups
from almdina_erp.almdina_erp.domain.orders.extra_addons import (
    EXTRA_ADDON_FIELD_BY_CODE,
    ExtraAddonError,
    ExtraAddonPieceInput,
    ExtraAddonRates,
    apply_extra_double_text_flags_to_snapshot,
    calculate_extra_addon_pricing,
    available_extra_double_sides,
    extra_double_text_flags,
    normalize_extra_double_sides,
    extra_overlay_kind_for_layer,
    extra_overlay_layer_for_kind,
    physical_cut_quantity,
    serialize_extra_double_sides,
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

    def test_full_double_and_all_machining_fees_remain_commercial_qty(self) -> None:
        summary = calculate_extra_addon_pricing(
            [
                ExtraAddonPieceInput(
                    piece_type="Regular", qty=3,
                    full_door_double=True,
                    liner=True, back_groove=True, recessed_handle_cutout=True,
                )
            ],
            rates=ExtraAddonRates(
                full_door_double_usd=0.50, liner_usd=0.50,
                back_groove_usd=0.50, recessed_handle_cutout_usd=0.50,
            ),
        )
        piece = summary.pieces[0]
        self.assertEqual(physical_cut_quantity(3, full_door_double=True), 6)
        self.assertEqual(piece.full_door_double_total_usd, 1.50)
        self.assertEqual(piece.liner_total_usd, 1.50)
        self.assertEqual(piece.back_groove_total_usd, 1.50)
        self.assertEqual(piece.recessed_handle_cutout_total_usd, 1.50)
        self.assertEqual(summary.total_usd, 6.00)

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

    def test_glass_addons_use_the_same_pricing_as_a_regular_piece(self) -> None:
        glass = calculate_extra_addon_pricing(
            [ExtraAddonPieceInput(piece_type="Glass", qty=2, liner=True)],
            rates=self.rates,
        )
        regular = calculate_extra_addon_pricing(
            [ExtraAddonPieceInput(piece_type="Regular", qty=2, liner=True)],
            rates=self.rates,
        )
        self.assertEqual(glass.total_usd, regular.total_usd)
        self.assertEqual(glass.pieces[0].selected_codes, regular.pieces[0].selected_codes)

    def test_double_side_selection_uses_liner_sides_and_legacy_defaults(self) -> None:
        self.assertEqual(
            normalize_extra_double_sides(
                "",
                piece_type="Clipped Corner",
                enabled=True,
            ),
            available_extra_double_sides("Clipped Corner"),
        )
        selected = normalize_extra_double_sides(
            '["edge_long_right", "edge_width_top"]',
            piece_type="Regular",
            enabled=True,
        )
        self.assertEqual(selected, ("edge_width_top", "edge_long_right"))
        self.assertEqual(serialize_extra_double_sides(selected), '["edge_width_top","edge_long_right"]')

    def test_double_side_selection_rejects_explicit_empty_or_unavailable_sides(self) -> None:
        with self.assertRaisesRegex(ExtraAddonError, "double_edge_sides_required"):
            normalize_extra_double_sides([], piece_type="Regular", enabled=True)
        with self.assertRaisesRegex(ExtraAddonError, "double_edge_side_unavailable"):
            normalize_extra_double_sides(
                ["edge_break_only"], piece_type="L-Shaped Corner", enabled=True
            )

    def test_double_side_metadata_does_not_change_pricing(self) -> None:
        base = calculate_extra_addon_pricing(
            [ExtraAddonPieceInput(piece_type="Regular", qty=2, double=True)],
            rates=self.rates,
        )
        selected = calculate_extra_addon_pricing(
            [ExtraAddonPieceInput(piece_type="Regular", qty=2, double=True)],
            rates=self.rates,
        )
        self.assertEqual(base.total_usd, selected.total_usd)

    def test_double_side_metadata_is_carried_into_expanded_plan_pieces(self) -> None:
        pieces = expand_piece_groups([{
            "piece_instance_id": "piece-1",
            "width_cm": 40,
            "length_cm": 60,
            "qty": 1,
            "piece_type": "Regular",
            "extra_double": 1,
            "extra_double_reference_sides": '["edge_width_top"]',
        }])
        self.assertEqual(pieces[0]["extra_double"], 1)
        self.assertEqual(pieces[0]["extra_double_reference_sides"], '["edge_width_top"]')


if __name__ == "__main__":
    unittest.main()
