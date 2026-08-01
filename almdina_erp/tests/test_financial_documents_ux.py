from __future__ import annotations

import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / "almdina_erp" / "services" / "cost_document_service.py"
APPLICATION_PATH = (
    ROOT / "almdina_erp" / "application" / "costing" / "financial_documents.py"
)
UX_PATH = ROOT / "public" / "js" / "door_cutting_order_financial_documents_ux.js"
HOOKS_PATH = ROOT / "hooks.py"


def test_financial_document_endpoints_require_view_and_print_capabilities() -> None:
    source = SERVICE_PATH.read_text(encoding="utf-8")
    assert "Capability.VIEW_COSTS" in source
    assert "Capability.PRINT_CUSTOMER_INVOICE" in source
    assert "Capability.PRINT_INTERNAL_COST_REPORT" in source
    assert "require_document_capability(order, Capability.VIEW_COSTS)" in source
    assert "require_document_capability(order, print_capability)" in source
    assert "order.check_permission(\"read\")" in source


def test_customer_document_model_never_contains_internal_report_sections() -> None:
    source = APPLICATION_PATH.read_text(encoding="utf-8")
    customer = source.split("def build_customer_invoice_document", 1)[1].split(
        "def build_internal_cost_report_document", 1
    )[0]
    assert '"kind": "customer_invoice"' in customer
    assert '"cost_breakdown"' not in customer
    assert '"operations"' not in customer
    assert '"special_prices"' not in customer
    assert '"classification"' not in customer
    assert '"عدد الدرف"' in customer
    assert '"عدد الألواح"' not in customer


def test_financial_print_ui_uses_server_authorized_payloads_only() -> None:
    source = UX_PATH.read_text(encoding="utf-8")
    assert "cost_document_service.get_customer_invoice_document" in source
    assert "cost_document_service.get_internal_cost_report_document" in source
    assert 'can("view_costs")' in source
    assert 'can("print_customer_invoice")' in source
    assert 'can("print_internal_cost_report")' in source
    assert "Customer invoice HTML is server-authorized" in source
    assert "AlmdinaOrderCostUX" in source
    assert "AlmdinaOrderDocumentPrint" in source
    assert "dco-print-customer-invoice" in source
    assert "dco-secure-print-customer-invoice" in source
    assert "dco-secure-print-internal-cost-report" in source
    assert "buildPrintHtml" not in source
    assert "invoiceLines(frm)" not in source


def test_financial_actions_are_idempotent_and_follow_the_active_order() -> None:
    source = UX_PATH.read_text(encoding="utf-8")
    assert "let activeFrm = null" in source
    assert "activeFrm = frm" in source
    assert "function resolvedForm" in source
    assert "function ensureActionButton" in source
    assert "matches.slice(1).remove()" in source
    assert ".off(\"click.almdinaFinancialDocuments\")" in source
    assert "MutationObserver" in source
    assert "__almdina_financial_observer.disconnect()" in source
    assert "root.find(`.${CUSTOMER_CLASS},.${INTERNAL_CLASS}`).remove()" not in source


def test_customer_and_internal_reports_use_distinct_print_layouts() -> None:
    source = UX_PATH.read_text(encoding="utf-8")
    assert '@page{size:A4 ${internal ? "landscape" : "portrait"}' in source
    assert "financial-summary.customer" in source
    assert "financial-summary.internal" in source
    measurements = source.split("function measurementsHtml", 1)[1].split(
        "function invoiceLinesHtml", 1
    )[0]
    assert "متر القشاط" not in measurements


def test_secure_financial_presenter_loads_after_cost_permission_ui() -> None:
    hooks = runpy.run_path(str(HOOKS_PATH))
    scripts = hooks["doctype_js"]["Door Cutting Order"]
    permission_index = scripts.index(
        "public/js/door_cutting_order_cost_permissions_ux.js"
    )
    secure_print_index = scripts.index(
        "public/js/door_cutting_order_financial_documents_ux.js"
    )
    assert secure_print_index == permission_index + 1


def test_internal_report_is_clearly_marked_confidential() -> None:
    application = APPLICATION_PATH.read_text(encoding="utf-8")
    ux = UX_PATH.read_text(encoding="utf-8")
    assert "داخلي — لا يسلّم للزبون" in application
    assert "classification" in ux
    assert "تقرير التكلفة الداخلي" in ux
