from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "almdina_erp" / "services" / "cost_document_service.py"
TOOLBAR = ROOT / "public" / "js" / "door_cutting_order_customer_invoice_toolbar_ux.js"
PERMISSION_CONTEXT = ROOT / "public" / "js" / "permission_context.js"


class TestCustomerInvoicePermissionSurface(unittest.TestCase):
    def test_customer_invoice_does_not_require_internal_cost_view(self) -> None:
        source = SERVICE.read_text(encoding="utf-8")
        customer = source.split("def get_customer_invoice_document", 1)[1].split(
            "def get_internal_cost_report_document",
            1,
        )[0]
        internal = source.split("def get_internal_cost_report_document", 1)[1]

        self.assertIn("Capability.PRINT_CUSTOMER_INVOICE", customer)
        self.assertIn("requires_cost_access=False", customer)
        self.assertIn("Capability.PRINT_INTERNAL_COST_REPORT", internal)
        self.assertIn("requires_cost_access=True", internal)

    def test_toolbar_uses_customer_print_capability_without_cost_gate(self) -> None:
        source = TOOLBAR.read_text(encoding="utf-8")

        self.assertIn('permissions.canDocument(frm, "print_customer_invoice")', source)
        self.assertNotIn('permissions.canDocument(frm, "view_costs")', source)
        self.assertIn("get_customer_invoice_document", source)
        self.assertIn("AlmdinaFinancialDocuments", source)

    def test_permission_boot_loads_customer_invoice_toolbar(self) -> None:
        source = PERMISSION_CONTEXT.read_text(encoding="utf-8")

        self.assertIn(
            "/assets/almdina_erp/js/door_cutting_order_customer_invoice_toolbar_ux.js",
            source,
        )
        self.assertIn("AlmdinaCustomerInvoiceToolbarUX", source)


if __name__ == "__main__":
    unittest.main()
