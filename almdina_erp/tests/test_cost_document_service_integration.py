from __future__ import annotations

import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import frappe

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.services import cost_document_service


FIXED_NOW = datetime.datetime(2026, 8, 1, 12, 0, 0)


class TestCostDocumentServiceIntegration(unittest.TestCase):
    @staticmethod
    def _order() -> SimpleNamespace:
        order = SimpleNamespace(
            doctype="Door Cutting Order",
            name="DCO-TEST-SECURE-0001",
            customer="Test Customer",
            order_date="2026-08-01",
            status="Draft",
            revision=1,
            approved_plan=None,
            pieces=[],
        )
        order.check_permission = Mock()
        return order

    def test_customer_invoice_checks_read_and_customer_print_permission(self) -> None:
        order = self._order()
        with (
            patch.object(cost_document_service.frappe, "get_doc", return_value=order),
            patch.object(cost_document_service, "now_datetime", return_value=FIXED_NOW),
            patch.object(
                cost_document_service,
                "require_document_capability",
            ) as require_capability,
            patch.object(
                cost_document_service,
                "build_customer_invoice_document",
                return_value={"kind": "customer_invoice"},
            ) as builder,
        ):
            result = cost_document_service.get_customer_invoice_document(order.name)

        order.check_permission.assert_called_once_with("read")
        self.assertEqual(
            require_capability.call_args_list,
            [call(order, Capability.PRINT_CUSTOMER_INVOICE)],
        )
        builder.assert_called_once()
        self.assertEqual(result["kind"], "customer_invoice")
        self.assertEqual(result["order_name"], order.name)
        self.assertEqual(result["generated_on"], FIXED_NOW)

    def test_internal_report_checks_read_view_and_internal_print_permissions(self) -> None:
        order = self._order()
        with (
            patch.object(cost_document_service.frappe, "get_doc", return_value=order),
            patch.object(cost_document_service, "now_datetime", return_value=FIXED_NOW),
            patch.object(
                cost_document_service,
                "require_document_capability",
            ) as require_capability,
            patch.object(
                cost_document_service,
                "build_internal_cost_report_document",
                return_value={"kind": "internal_cost_report"},
            ),
        ):
            result = cost_document_service.get_internal_cost_report_document(order.name)

        order.check_permission.assert_called_once_with("read")
        self.assertEqual(
            require_capability.call_args_list,
            [
                call(order, Capability.VIEW_COSTS),
                call(order, Capability.PRINT_INTERNAL_COST_REPORT),
            ],
        )
        self.assertEqual(result["kind"], "internal_cost_report")
        self.assertEqual(result["generated_on"], FIXED_NOW)

    def test_customer_invoice_projects_saved_special_shape_documentation(self) -> None:
        order = self._order()
        order.pieces = [
            SimpleNamespace(
                name="ROW-SPECIAL-1",
                special_shape_drawing_json="saved-crop-documentation",
            )
        ]
        with (
            patch.object(cost_document_service.frappe, "get_doc", return_value=order),
            patch.object(cost_document_service, "now_datetime", return_value=FIXED_NOW),
            patch.object(cost_document_service, "require_document_capability"),
            patch.object(cost_document_service, "_require_custom_edge_prices"),
            patch.object(
                cost_document_service,
                "build_customer_invoice_document",
                return_value={"kind": "customer_invoice"},
            ) as builder,
        ):
            cost_document_service.get_customer_invoice_document(order.name)

        pieces = builder.call_args.args[1]
        self.assertEqual(
            pieces[0]["special_shape_drawing_json"],
            "saved-crop-documentation",
        )

    def test_permission_failure_stops_document_building(self) -> None:
        order = self._order()

        def deny_internal_print(_order, capability):
            if capability == Capability.PRINT_INTERNAL_COST_REPORT:
                raise frappe.PermissionError

        with (
            patch.object(cost_document_service.frappe, "get_doc", return_value=order),
            patch.object(
                cost_document_service,
                "require_document_capability",
                side_effect=deny_internal_print,
            ),
            patch.object(
                cost_document_service,
                "build_internal_cost_report_document",
            ) as builder,
        ):
            with self.assertRaises(frappe.PermissionError):
                cost_document_service.get_internal_cost_report_document(order.name)

        builder.assert_not_called()


if __name__ == "__main__":
    unittest.main()
