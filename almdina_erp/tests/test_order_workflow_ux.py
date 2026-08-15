import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCTYPE_JSON = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
HOOKS = ROOT / "hooks.py"
LIST_UX = ROOT / "public" / "js" / "door_cutting_order_list.js"
MEASUREMENT_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "measurements"
    / "door_cutting_order_measurement_actions_ux.js"
)
EDGE_COLOR_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "edge_banding"
    / "door_cutting_order_edge_color_ux.js"
)
PRINT_PRESENTER = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "printing"
    / "door_cutting_order_document_print_presenter.js"
)
TOOLBAR_UX = ROOT / "public" / "js" / "door_cutting_order" / "core" / "door_cutting_order_toolbar_stability_ux.js"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_order_search_includes_customer_and_explains_id_or_customer_search():
    doctype = json.loads(text(DOCTYPE_JSON))
    assert doctype["search_fields"] == "customer,board_description"
    source = text(LIST_UX)
    assert "ابحث باسم العميل أو رقم الطلب (ID)" in source
    assert '"customer", "order_date", "status"' in source


def test_measurement_table_has_print_and_full_window_actions():
    source = text(MEASUREMENT_UX)
    assert 'class="btn btn-default btn-sm dco-print-measurements"' in source
    assert "فتح جدول الإدخال في نافذة مستقلة" in source
    assert "function openEditableMeasurements(frm)" in source
    assert 'const EDITOR_CLASS = "dco-measurement-entry-window"' in source
    assert "window.AlmdinaOrderDocumentPrint" in source
    assert "return Promise.resolve(documents.printMeasurements(frm))" in source
    assert "dco-measurements-print-frame" not in source
    assert "function printDocumentHtml" not in source


def test_measurement_print_is_shared_base_without_quote_details():
    source = text(PRINT_PRESENTER)
    for label in ("النوع", "العرض", "الطول", "العدد", "القشاط المخصص", "ملاحظات"):
        assert label in source
    assert "function measurementTable(frm)" in source
    assert "function measurementDocumentBody(frm)" in source
    assert 'printHtml(documentHtml(frm, "measurements", printIdentity))' in source
    assert "function quoteDetailsHtml(payload)" in source
    assert '${invoice ? quoteDetailsHtml(quotePayload || {}) : ""}' in source
    assert "function invoiceSummary" not in source
    assert "function invoiceLines(frm)" not in source


def test_edge_color_is_kept_in_shared_print_header_without_duplicate_columns():
    edge_source = text(EDGE_COLOR_UX)
    print_source = text(PRINT_PRESENTER)
    measurement_source = text(MEASUREMENT_UX)

    assert "<b>نوع القشاط</b>" in print_source
    assert print_source.count("<b>لون القشاط</b>") == 1
    assert "<th>لون القشاط</th>" not in print_source
    assert "patchMeasurementTable" not in edge_source
    assert "patchInvoiceLines" not in edge_source
    assert "patchInvoiceMeta" not in edge_source
    assert "removeLegacyColorDuplicates" in edge_source

    assert "orderEdgeColor(frm)" in measurement_source
    assert "لون القشاط:" in measurement_source
    assert "function printDocumentHtml" not in measurement_source
    assert "dco-measurements-print-frame" not in measurement_source


def test_toolbar_removes_legacy_edge_button_measurement_duplicate_and_dedupes_actions():
    source = text(TOOLBAR_UX)
    assert "إلغاء تخصيص قشاط الدرف" in source
    assert "طباعة جدول القياسات" in source
    assert "dedupeButtons(head)" in source
    assert "max-height:none!important" in source
    assert "overflow:visible!important" in source
    assert "MutationObserver" in source
    assert "removeEmptyGroups" not in source
    assert '".custom-actions > button,.custom-actions > a"' in source
    assert 'ASYNC_ACTION_GROUPS = new Set(["صالة الإنتاج"])' in source


def test_all_new_ux_layers_are_loaded_in_the_required_order():
    hooks = text(HOOKS)
    measurement = '"public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_actions_ux.js"'
    secure_dxf = '"public/js/door_cutting_order/cutting_plan/secure_dxf_export.js"'
    toolbar = '"public/js/door_cutting_order/core/door_cutting_order_toolbar_stability_ux.js"'
    assert "doctype_list_js = {" in hooks
    assert '"Door Cutting Order": "public/js/door_cutting_order_list.js"' in hooks
    assert measurement in hooks
    assert secure_dxf in hooks
    assert toolbar in hooks
    assert hooks.index(measurement) < hooks.index(secure_dxf) < hooks.index(toolbar)
