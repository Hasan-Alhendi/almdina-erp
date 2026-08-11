from __future__ import annotations

import json
import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / "almdina_erp" / "services" / "cost_document_service.py"
APPLICATION_PATH = (
    ROOT / "almdina_erp" / "application" / "costing" / "financial_documents.py"
)
UX_PATH = ROOT / "public" / "js" / "door_cutting_order_financial_documents_ux.js"
PRESENTER_PATH = ROOT / "public" / "js" / "door_cutting_order_cost_presenter.js"
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
    assert 'can(frm, "view_costs")' in source
    assert 'can(frm, "print_customer_invoice")' in source
    assert 'visible: !frm.is_new() && can(frm, "print_customer_invoice")' in source
    presenter = PRESENTER_PATH.read_text(encoding="utf-8")
    permissions = (
        ROOT / "public" / "js" / "door_cutting_order_cost_permissions_ux.js"
    ).read_text(encoding="utf-8")
    assert "dco-cost-hero" not in presenter
    assert "dco-cost-actions-bar" in presenter
    assert '<div class="dco-cost-kpis">' not in presenter
    assert "تسعير قشط الدرفات الخاصة" in presenter
    assert "تسعير قشاط درف الزاوية المقصوصة" in presenter
    assert "specialPricingHtml(frm)" in presenter
    assert "cutCornerPricingHtml(frm)" in presenter
    assert "درفة خاصة رقم" in presenter
    assert "درفة زاوية مقصوصة" in presenter
    assert "specialDoorLabel(row)" in presenter
    assert "cutCornerDoorLabel(row)" in presenter
    assert "dco-invoice-total-card" in presenter
    assert "الإجمالي النهائي للفاتورة" in presenter
    assert "invoiceTotalCardHtml(frm)" in presenter
    assert "#Custom-" not in presenter
    assert "#CutCorner-" not in presenter
    assert "pendingCustomEdgePriceLabels" in presenter
    assert "عرض الرسم" in presenter
    assert "غير مسعّر" in presenter
    assert "سعر القشاط" in presenter
    assert "dco-view-cut-corner-sketch" in presenter
    assert '__("تعديل السعر")' in permissions
    assert "إجمالي تكلفة قشاط الدرفة الخاصة" in permissions
    assert "update_clipped_corner_edge_price" in permissions
    assert "تكلفة معالجة قشاط الزاوية المقصوصة" in permissions
    assert "orderIsEditable(frm)" in permissions
    assert "frappe.almdina.orderCanEdit" in permissions
    assert "almdina_edit_session_changed(frm)" in permissions
    # Pricing is a financial-document gate, not a prerequisite for persisting
    # measurement edits. Saving a Special/CutCorner piece must therefore remain
    # possible before its edge price is entered.
    assert "أدخل أسعار قشاط" not in permissions
    assert "before_save(frm)" not in permissions
    assert "frappe.validated = false" not in permissions
    assert "pendingCustomEdgePriceLabels" in source
    assert "أدخل أسعار قشاط" in source
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
        ROOT / "public" / "js" / "door_cutting_order_clipped_corner_ux.js"
    ).read_text(encoding="utf-8")
    assert "clipped_corner_edge_price_usd" in clipped_ux


def test_financial_document_payloads_are_redacted_by_kind() -> None:
    namespace = runpy.run_path(str(APPLICATION_PATH))
    customer_builder = namespace["build_customer_invoice_document"]
    internal_builder = namespace["build_internal_cost_report_document"]

    summary = {
        "order_name": "DCO-TEST",
        "customer": "Customer",
        "order_date": "2026-01-01",
        "board_description": "MDF 18 mm White",
        "board_length_cm": 244,
        "board_width_cm": 122,
        "boards_used": 2,
        "total_pieces": 4,
        "total_area_m2": 5.1,
        "edge_meters": 13.2,
        "customer_quote_total_usd": 500,
        "total_cost_usd": 400,
        "mdf_cost_usd": 250,
        "cutting_cost_usd": 50,
        "edge_cost_usd": 70,
        "special_shapes_final_total_usd": 30,
        "actual_cost_usd": 410,
        "material_variance_cost_usd": 4,
        "internal_loss_cost_usd": 6,
    }
    pieces = [
        {
            "name": "ROW-1",
            "width_cm": 50,
            "length_cm": 100,
            "qty": 1,
            "piece_type": "Normal",
            "notes": "",
            "edge_long_right": 1,
            "edge_long_left": 0,
            "edge_width_top": 0,
            "edge_width_bottom": 0,
        }
    ]

    customer = customer_builder(summary=summary, pieces=pieces)
    internal = internal_builder(summary=summary, pieces=pieces)

    assert customer["kind"] == "customer_invoice"
    assert "cost_breakdown" not in customer
    assert "special_prices" not in customer
    assert "operations" not in customer
    assert internal["kind"] == "internal_cost_report"
    assert "cost_breakdown" in internal
    assert "operations" in internal


def test_customer_invoice_summary_uses_door_count_not_board_count() -> None:
    source = APPLICATION_PATH.read_text(encoding="utf-8")
    customer = source.split("def build_customer_invoice_document", 1)[1].split(
        "def build_internal_cost_report_document", 1
    )[0]
    assert '"عدد الدرف"' in customer
    assert 'summary.get("total_pieces"' in customer
    assert '"عدد الألواح"' not in customer
