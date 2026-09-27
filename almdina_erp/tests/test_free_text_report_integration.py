from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestOrderNumericValidation(FrappeTestCase):
    def test_zero_board_dimension_is_rejected_instead_of_defaulted(self) -> None:
        from almdina_erp.almdina_erp.infrastructure.frappe.orders.document_access import (
            FrappeOrderDocumentAccess,
        )

        order = frappe.new_doc("Door Cutting Order")
        order.board_description = "MDF أبيض 18 مم"
        order.board_length_cm = 0
        order.board_width_cm = 122
        order.trim_margin_mm = 5

        with self.assertRaises(frappe.ValidationError):
            FrappeOrderDocumentAccess(order).load_board_snapshot()

    def test_zero_optimizer_time_limit_is_rejected(self) -> None:
        from almdina_erp.almdina_erp.infrastructure.frappe.orders.document_access import (
            FrappeOrderDocumentAccess,
        )

        order = frappe.new_doc("Door Cutting Order")
        order.kerf_mm = 3
        order.trim_margin_mm = 5
        order.board_rate_usd = 0
        order.cutting_cost_per_board_usd = 0
        order.optimization_time_limit_sec = 0

        with self.assertRaises(frappe.ValidationError):
            FrappeOrderDocumentAccess(order).validate_numeric_inputs()
