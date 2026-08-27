from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / "almdina_erp" / "services" / "cost_document_service.py"
APPLICATION_PATH = (
    ROOT / "almdina_erp" / "application" / "costing" / "financial_documents.py"
)
UX_PATH = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "costing"
    / "door_cutting_order_financial_documents_ux.js"
)
PRESENTER_PATH = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "costing"
    / "door_cutting_order_cost_presenter.js"
)
DOCUMENT_PRINT_PATH = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "printing"
    / "door_cutting_order_document_print_presenter.js"
)
COMPACTNESS_PATH = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "printing"
    / "door_cutting_order_document_compactness_ux.js"
)
REGISTRY_PATH = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "core"
    / "door_cutting_order_workspace_asset_registry.js"
)


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
    assert 'can(frm, "view_costs")' in source
    assert 'can(frm, "print_customer_invoice")' in source
    assert 'visible: !frm.is_new() && can(frm, "print_customer_invoice")' in source
    presenter = PRESENTER_PATH.read_text(encoding="utf-8")
    permissions = (
        ROOT
        / "public"
        / "js"
        / "door_cutting_order"
        / "costing"
        / "door_cutting_order_cost_permissions_ux.js"
    ).read_text(encoding="utf-8")
    assert "dco-cost-hero" not in presenter
    assert "dco-cost-actions-bar" in presenter
    assert '<div class="dco-cost-kpis">' not in presenter
    assert "تسعير الدرفات الخاصة" in presenter
    assert "تسعير قشاط درف الزاوية المقصوصة" in presenter
    assert "specialPricingHtml(frm)" in presenter
    assert "cutCornerPricingHtml(frm)" in presenter
    assert "درفة خاصة رقم" in presenter
    assert "درفة زاوية مقصوصة" in presenter
    assert "specialDoorLabel(row)" in presenter
    assert "cutCornerDoorLabel(row)" in presenter
    assert "dco-invoice-total-card" in presenter
    assert "الإجمالي النهائي للفاتورة" in presenter
    assert "الإجمالي الحالي قبل الأسعار غير المسعرة" in presenter
    assert "invoiceTotalCardHtml(frm)" in presenter
    assert "#Custom-" not in presenter
    assert "#CutCorner-" not in presenter
    assert "pendingCustomEdgePriceLabels" in presenter
    assert "pending: !ready" in presenter
    assert "عرض الرسم" in presenter
    assert "غير مسعّر" in presenter
    assert "السعر الخاص الشامل" in presenter
    assert "dco-view-cut-corner-sketch" in presenter
    assert '__("تعديل السعر")' in permissions
    assert "السعر الخاص الشامل للدرفة" in permissions
    assert "update_clipped_corner_edge_price" in permissions
    assert "تكلفة معالجة قشاط الزاوية المقصوصة" in permissions
    assert "orderIsEditable(frm)" in permissions
    assert "frappe.almdina.orderCanEdit" in permissions
    assert "almdina_edit_session_changed(frm)" in permissions
    # Pricing remains a financial-document gate below, but it must not block
    # persisting a Special/CutCorner measurement row itself.
    assert "أدخل أسعار قشاط" not in permissions
    assert "before_save(frm)" not in permissions
    assert "frappe.validated = false" not in permissions
    assert "pendingCustomEdgePriceLabels" in source
    assert "لا يمكن طباعة فاتورة غير مكتملة" in source
    assert "assert_order_editable(order)" in (
        ROOT / "almdina_erp" / "services" / "cost_permission_service.py"
    ).read_text(encoding="utf-8")
    assert "ensure_custom_edge_prices" in (
        ROOT / "almdina_erp" / "infrastructure" / "frappe" / "orders" / "piece_policy_adapter.py"
    ).read_text(encoding="utf-8")
    assert "pending_custom_edge_price_labels" in (
        ROOT / "almdina_erp" / "domain" / "orders" / "piece_policy.py"
    ).read_text(encoding="utf-8")
    assert "_require_custom_edge_prices" in (
        ROOT / "almdina_erp" / "services" / "cost_document_service.py"
    ).read_text(encoding="utf-8")
    service = (
        ROOT / "almdina_erp" / "services" / "cost_permission_service.py"
    ).read_text(encoding="utf-8")
    assert "def update_clipped_corner_edge_price" in service
    assert "clipped_corner_edge_price_usd" in service
    detail = json.loads(
        (
            ROOT / "almdina_erp" / "doctype" / "door_cutting_order_detail" / "door_cutting_order_detail.json"
        ).read_text(encoding="utf-8")
    )
    detail_fields = {row["fieldname"]: row for row in detail["fields"]}
    assert detail_fields["clipped_corner_edge_price_usd"]["fieldtype"] == "Currency"
    assert detail_fields["clipped_corner_edge_price_status"]["options"] == "Unpriced\nPriced"
    clipped_ux = (
        ROOT
        / "public"
        / "js"
        / "door_cutting_order"
        / "drawing"
        / "door_cutting_order_clipped_corner_ux.js"
    ).read_text(encoding="utf-8")
    assert "function view(frm, row)" in clipped_ux
    assert "view," in clipped_ux
    assert 'can(frm, "print_customer_invoice")' in presenter
    assert 'can(frm, "print_internal_cost_report")' in source
    assert "canDocument" in source
    assert "Customer invoice HTML is server-authorized" in source
    assert "AlmdinaOrderCostUX" in source
    assert 'typeof costApi.pendingCustomEdgePriceLabels === "function"' in source
    assert "costApi.pendingCustomEdgePriceLabels(frm)" in source
    assert "costApi.printInvoice =" not in source
    assert "AlmdinaOrderDocumentPrint" in source
    assert "presenter.printAuthorizedInvoice(frm, payload)" in source
    assert "dco-print-customer-invoice" in source
    assert "dco-secure-print-customer-invoice" in source
    assert "dco-secure-print-internal-cost-report" in source
    assert "buildPrintHtml" not in source
    assert "invoiceLines(frm)" not in source
    assert "function measurementsHtml" not in source
    assert "function invoiceLinesHtml" not in source


def test_invoice_waits_for_edge_profiles_before_final_screen_render() -> None:
    source = COMPACTNESS_PATH.read_text(encoding="utf-8")
    assert "function refreshInvoiceAfterProfiles(frm)" in source
    assert "edgeApi.ensureProfiles(frm)" in source
    assert "AlmdinaOrderCostUX.render(frm)" in source
    assert "AlmdinaMultiEdgeDocuments.patch(frm)" in source
    assert "requestAnimationFrame(refresh)" in source


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
    assert "root.find(`.${CUSTOMER_CLASS},${INTERNAL_CLASS}`).remove()" not in source


def test_customer_invoice_delegates_layout_and_internal_report_stays_distinct() -> None:
    source = UX_PATH.read_text(encoding="utf-8")
    customer_print = DOCUMENT_PRINT_PATH.read_text(encoding="utf-8")

    # The confidential internal report owns its landscape layout here.
    assert "@page{size:A4 landscape;margin:11mm}" in source
    assert "financial-summary.internal" in source

    # Customer invoice layout is not duplicated in the financial adapter.
    assert "presenter.printAuthorizedInvoice(frm, payload)" in source
    assert 'throw new Error("Customer invoice layout belongs to AlmdinaOrderDocumentPrint")' in source
    assert "function measurementsHtml" not in source
    assert "function invoiceLinesHtml" not in source
    assert "financial-summary.customer" not in source

    # Customer invoice inherits the exact measurement print theme/body.
    assert 'theme.css("measurements", shapePrintCss())' in customer_print
    assert "function measurementDocumentBody(frm)" in customer_print
    assert "function measurementDocumentBodyWithPayload(frm, payload)" in customer_print
    assert "function quoteDetailsHtml(payload)" in customer_print


def test_secure_financial_presenter_loads_after_cost_permission_ui() -> None:
    registry = REGISTRY_PATH.read_text(encoding="utf-8")
    cost = registry.split("cost: Object.freeze({", 1)[1].split(
        "});\n\n    function descriptor", 1
    )[0]
    permissions = "door_cutting_order_cost_permissions_ux.js"
    financial = "door_cutting_order_financial_documents_ux.js"

    # These are one lazy Cost feature chain; preserve adjacency there rather than
    # forcing either module back into the first-open DCO manifest.
    assert permissions in cost
    assert financial in cost
    assert cost.index(financial) > cost.index(permissions)


def test_internal_report_is_clearly_marked_confidential() -> None:
    application = APPLICATION_PATH.read_text(encoding="utf-8")
    ux = UX_PATH.read_text(encoding="utf-8")
    assert "داخلي — لا يسلّم للزبون" in application
    assert "classification" in ux