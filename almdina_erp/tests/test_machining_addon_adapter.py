from __future__ import annotations

from types import SimpleNamespace

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.domain.cutting.machining_overlay import MACHINING_ADDONS
from almdina_erp.almdina_erp.infrastructure.frappe.orders.piece_policy_adapter import (
    FrappeOrderPiecePolicyAdapter,
)


class FakeOrderAccess:
    @staticmethod
    def old_piece_map():
        return {}


class TestMachiningAddonAdapter(FrappeTestCase):
    def _adapter(self, **updates: object) -> tuple[FrappeOrderPiecePolicyAdapter, SimpleNamespace]:
        values = {
            "name": "PIECE-1",
            "piece_type": "Regular",
            "width_cm": 40,
            "length_cm": 60,
            "cut_width_cm": 20,
            "cut_length_cm": 60,
            "extra_liner": 0,
            "liner_reference_side": "",
            "liner_offset_cm": 0,
            "liner_width_cm": 0,
            "liner_start_cm": 0,
            "liner_length_cm": 0,
            "extra_back_groove": 0,
            "back_groove_reference_side": "",
            "back_groove_offset_cm": 0,
            "back_groove_width_cm": 0,
            "back_groove_start_cm": 0,
            "back_groove_length_cm": 0,
            "extra_recessed_handle_cutout": 0,
            "recessed_handle_reference_side": "",
            "recessed_handle_offset_cm": 0,
            "recessed_handle_width_cm": 0,
            "recessed_handle_start_cm": 0,
            "recessed_handle_length_cm": 0,
            "edge_long_right": 0,
            "edge_long_left": 0,
            "edge_width_top": 0,
            "edge_width_bottom": 0,
            "edge_long_thickness_mm": 0,
            "edge_width_thickness_mm": 0,
            "edge_break": 0,
            "edge_break_thickness_mm": 0,
            "clipped_corner_position": "Top Right",
            "clipped_corner_width_cm": 0,
            "clipped_corner_length_cm": 0,
        }
        values.update(updates)
        row = SimpleNamespace(**values)
        document = SimpleNamespace(pieces=[row])
        return FrappeOrderPiecePolicyAdapter(document, FakeOrderAccess()), row

    def test_all_addons_use_the_current_calculated_piece_dimensions(self) -> None:
        for addon in MACHINING_ADDONS:
            with self.subTest(addon=addon.kind):
                adapter, _row = self._adapter(
                    **{
                        addon.enabled_field: 1,
                        addon.side_field: "edge_long_right",
                        addon.offset_field: 18,
                        addon.width_field: 3,
                        addon.start_field: 0,
                        addon.length_field: 0,
                    }
                )
                with self.assertRaises(frappe.ValidationError) as raised:
                    adapter.validate_machining_rows()
                self.assertIn("Row 1", str(raised.exception))
                self.assertIn(addon.kind.replace("_", " ").split()[0].title(), str(raised.exception))

    def test_all_addons_accept_valid_current_geometry(self) -> None:
        for addon in MACHINING_ADDONS:
            with self.subTest(addon=addon.kind):
                adapter, row = self._adapter(
                    **{
                        addon.enabled_field: 1,
                        addon.side_field: "edge_long_right",
                        addon.offset_field: 2,
                        addon.width_field: 1,
                        addon.start_field: 3,
                        addon.length_field: 10,
                    }
                )
                adapter.validate_machining_rows()
                self.assertEqual(getattr(row, addon.length_field), 10)

    def test_non_finite_machining_values_are_rejected(self) -> None:
        addon = MACHINING_ADDONS[0]
        for field, value, expected in (
            (addon.offset_field, float("nan"), "Offset"),
            (addon.width_field, float("nan"), "Width"),
            (addon.start_field, float("nan"), "Start position"),
            (addon.length_field, float("nan"), "Length"),
        ):
            with self.subTest(field=field):
                adapter, _row = self._adapter(
                    **{
                        addon.enabled_field: 1,
                        addon.side_field: "edge_width_top",
                        addon.offset_field: 2,
                        addon.width_field: 1,
                        addon.start_field: 0,
                        addon.length_field: 10,
                        field: value,
                    }
                )
                with self.assertRaises(frappe.ValidationError) as raised:
                    adapter.validate_machining_rows()
                self.assertIn(expected, str(raised.exception))

    def test_overlong_span_reports_available_and_maximum_lengths(self) -> None:
        addon = MACHINING_ADDONS[1]
        adapter, _row = self._adapter(
            **{
                addon.enabled_field: 1,
                addon.side_field: "edge_width_top",
                addon.offset_field: 2,
                addon.width_field: 1,
                addon.start_field: 5,
                addon.length_field: 16,
            }
        )
        with self.assertRaises(frappe.ValidationError) as raised:
            adapter.validate_machining_rows()
        message = str(raised.exception)
        self.assertIn("Row 1", message)
        self.assertIn("20 cm", message)
        self.assertIn("5 cm", message)
        self.assertIn("16 cm", message)
        self.assertIn("15 cm", message)

    def test_l_corner_span_ending_on_bend_is_rejected(self) -> None:
        addon = MACHINING_ADDONS[0]
        adapter, _row = self._adapter(
            piece_type="L-Shaped Corner",
            clipped_corner_width_cm=5,
            clipped_corner_length_cm=10,
            **{
                addon.enabled_field: 1,
                addon.side_field: "edge_break",
                addon.offset_field: 2,
                addon.width_field: 1,
                addon.start_field: 0,
                addon.length_field: 10,
            },
        )
        with self.assertRaises(frappe.ValidationError) as raised:
            adapter.validate_machining_rows()
        self.assertIn("bend", str(raised.exception).lower())

    def test_zero_length_remains_the_full_reference_side_sentinel(self) -> None:
        addon = MACHINING_ADDONS[0]
        adapter, row = self._adapter(
            **{
                addon.enabled_field: 1,
                addon.side_field: "edge_width_top",
                addon.offset_field: 2,
                addon.width_field: 1,
                addon.start_field: 5,
                addon.length_field: 0,
            }
        )
        adapter.validate_machining_rows()
        self.assertEqual(getattr(row, addon.length_field), 0)

    def test_l_inner_span_limit_matches_nominal_finished_notch_for_all_addons(self) -> None:
        for addon in MACHINING_ADDONS:
            for length, expected_error in (
                (60, False),
                (60.001, True),
                (60.01, True),
                (60.025, True),
                (60.1, True),
                (60.2, True),
            ):
                with self.subTest(addon=addon.kind, length=length):
                    adapter, _row = self._adapter(
                        piece_type="L-Shaped Corner",
                        width_cm=60,
                        length_cm=60,
                        cut_width_cm=60,
                        cut_length_cm=60,
                        clipped_corner_width_cm=30,
                        clipped_corner_length_cm=30,
                        edge_break=1,
                        edge_break_thickness_mm=1,
                        **{
                            addon.enabled_field: 1,
                            addon.side_field: "edge_break",
                            addon.offset_field: 1,
                            addon.width_field: 1,
                            addon.start_field: 0,
                            addon.length_field: length,
                        },
                    )
                    if expected_error:
                        with self.assertRaises(frappe.ValidationError) as raised:
                            adapter.validate_machining_rows()
                        self.assertIn("available 60 cm", str(raised.exception))
                        self.assertIn("maximum 60 cm", str(raised.exception))
                    else:
                        adapter.validate_machining_rows()
