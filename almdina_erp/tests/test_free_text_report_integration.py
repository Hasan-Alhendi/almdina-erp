from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.report.board_usage_analysis import (
    board_usage_analysis,
)
from almdina_erp.almdina_erp.report.factory_operations_summary import (
    factory_operations_summary,
)
from almdina_erp.almdina_erp.report.factory_order_analysis import (
    factory_order_analysis,
)
from almdina_erp.almdina_erp.report.piece_size_usage_analysis import (
    piece_size_usage_analysis,
)
from almdina_erp.almdina_erp.report.production_incidents_and_replacements import (
    production_incidents_and_replacements,
)


class TestFreeTextReportIntegration(FrappeTestCase):
    def test_operational_reports_compile_against_the_installed_schema(self) -> None:
        filters = frappe._dict(
            {
                "from_date": "2099-01-01",
                "to_date": "2099-01-02",
                "customer": "",
                "status": "",
                "board_description": "",
            }
        )
        for report in (
            factory_order_analysis,
            piece_size_usage_analysis,
            board_usage_analysis,
            factory_operations_summary,
            production_incidents_and_replacements,
        ):
            with self.subTest(report=report.__name__):
                columns, rows = report.execute(filters)
                self.assertTrue(columns)
                self.assertIsInstance(rows, list)


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
