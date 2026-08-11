from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "almdina_erp" / "services" / "cost_document_service.py"
TOOLBAR = ROOT / "public" / "js" / "door_cutting_order_customer_invoice_toolbar_ux.js"
FINANCIAL = ROOT / "public" / "js" / "door_cutting_order_financial_documents_ux.js"
PERMISSION_CONTEXT = ROOT / "public" / "js" / "permission_context.js"
HOOKS = ROOT / "hooks.py"


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
        toolbar = TOOLBAR.read_text(encoding="utf-8")
        financial = FINANCIAL.read_text(encoding="utf-8")

        self.assertIn(
            'permissions.canDocument(frm, "print_customer_invoice")', toolbar
        )
        self.assertNotIn('permissions.canDocument(frm, "view_costs")', toolbar)
        self.assertIn("AlmdinaFinancialDocuments", toolbar)
        self.assertIn("documents.printCustomerInvoice(frm)", toolbar)
        self.assertIn("get_customer_invoice_document", financial)

    def test_toolbar_keeps_secure_cost_tab_action_across_rerenders(self) -> None:
        source = TOOLBAR.read_text(encoding="utf-8")

        self.assertIn("printCustomerInvoice", source)
        self.assertIn("dco-secure-print-customer-invoice", source)
        self.assertIn("function ensureCostButton", source)
        self.assertIn("function observeCostActions", source)
        self.assertIn("MutationObserver", source)
        self.assertIn("function wrapCostPresenter", source)
        self.assertIn("const result = original.render(frm)", source)
        self.assertIn("requestAnimationFrame(() => ensureCostButton(frm))", source)
        self.assertNotIn("frm.add_custom_button", source)
        self.assertNotIn("get_customer_invoice_document", source)

    def test_order_form_loads_customer_invoice_toolbar_from_source(self) -> None:
        source = PERMISSION_CONTEXT.read_text(encoding="utf-8")
        hooks = HOOKS.read_text(encoding="utf-8")

        self.assertIn(
            '"public/js/door_cutting_order_customer_invoice_toolbar_ux.js"',
            hooks,
        )
        self.assertIn("AlmdinaCustomerInvoiceToolbarUX", source)


if __name__ == "__main__":
    unittest.main()
