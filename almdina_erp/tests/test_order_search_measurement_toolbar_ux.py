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
PRINT_PRESENTER = ROOT / "public" / "js" / "door_cutting_order_document_print_presenter.js"
EDGE_COLOR_UX = ROOT / "public" / "js" / "door_cutting_order_edge_color_ux.js"
TOOLBAR_UX = ROOT / "public" / "js" / "door_cutting_order" / "core" / "door_cutting_order_toolbar_stability_ux.js"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_order_search_includes_customer_and_explains_id_or_customer_search():
    doctype = json.loads(text(DOCTYPE_JSON))
    search_fields = {value.strip() for value in doctype["search_fields"].split(",") if value.strip()}
    assert {"customer", "board_description"}.issubset(search_fields)
    source = text(LIST_UX)
    assert "ابحث باسم العميل أو رقم الطلب (ID)" in source
    assert "اسم العميل أو رقم الطلب" in source
    assert '"customer", "order_date", "status"' in source


def test_visible_id_filter_is_replaced_with_combined_name_or_customer_search():
    source = text(LIST_UX)
    assert "const originalGetArgs = listview.get_args.bind(listview)" in source
    assert "listview.get_args = function dcoCombinedSearchArgs()" in source
    assert "args.filters = (args.filters || []).filter" in source
    assert '[this.doctype, "name", "like", pattern]' in source
    assert '[this.doctype, "customer", "like", pattern]' in source
    assert "args.or_filters = [" in source
    assert "listview._dcoCombinedSearchInstalled = true" in source


def test_measurement_table_has_print_and_editable_full_screen_actions():
    source = text(MEASUREMENT_UX)
    assert 'class="btn btn-default btn-sm dco-print-measurements"' in source
    assert "فتح جدول الإدخال في نافذة مستقلة" in source
    assert "openEditableMeasurements(frm)" in source
    assert "dco-measurement-entry-window" in source
    assert "host.appendChild(root)" in source
    assert "placeholder.parentNode.insertBefore(state.root, state.placeholder)" in source
    assert "window.open(" not in source
    assert "window.AlmdinaOrderDocumentPrint" in source
    assert "return Promise.resolve(documents.printMeasurements(frm))" in source
    assert "dco-measurements-print-frame" not in source


def test_full_screen_entry_reuses_live_grid_and_preserves_all_existing_editing_behaviour():
    source = text(MEASUREMENT_UX)
    assert 'root.querySelector(".dco-fast-entry-shell")' in source
    assert "dco-entry-window-save" in source
    assert "await Promise.resolve(frm.save())" in source
    assert "dco-entry-window-print" in source
    assert "dco-entry-window-close" in source
    assert "إغلاق والعودة" in source
    assert "توجد تعديلات غير محفوظة" in source
    assert "جميع التعديلات محفوظة" in source
    assert "height:100%;display:flex;flex-direction:column" in source
    assert "max-height:none!important" in source


def test_measurement_print_is_the_shared_base_and_invoice_only_appends_quote():
    source = text(PRINT_PRESENTER)
    for label in ("النوع", "العرض", "الطول", "العدد", "القشاط المخصص", "ملاحظات"):
        assert label in source
    assert "function measurementTable(frm)" in source
    assert "function measurementDocumentBody(frm)" in source
    assert 'printHtml(documentHtml(frm, "measurements", printIdentity))' in source
    assert "function quoteDetailsHtml(payload)" in source
    assert "${measurementDocumentBody(frm)}" in source
    assert '${invoice ? quoteDetailsHtml(quotePayload || {}) : ""}' in source
    assert source.index("${measurementDocumentBody(frm)}") < source.index(
        '${invoice ? quoteDetailsHtml(quotePayload || {}) : ""}'
    )
    assert "function invoiceSummary" not in source
    assert "function invoiceLines(frm)" not in source


def test_customer_invoice_keeps_edge_color_once_in_shared_measurement_header():
    print_source = text(PRINT_PRESENTER)
    edge_color_patch = text(EDGE_COLOR_UX)

    assert print_source.count("<b>لون القشاط</b>") == 1
    assert "<th>لون القشاط</th>" not in print_source
    assert "<b>نوع القشاط</b>" in print_source
    assert "patchMeasurementTable" not in edge_color_patch
    assert "patchInvoiceLines" not in edge_color_patch
    assert "patchInvoiceMeta" not in edge_color_patch
    assert "removeLegacyColorDuplicates" in edge_color_patch


def test_toolbar_removes_legacy_edge_button_measurement_duplicate_and_dedupes_actions():
    source = text(TOOLBAR_UX)
    assert "إلغاء تخصيص قشاط الدرف" in source
    assert "طباعة جدول القياسات" in source
    assert "dedupeButtons(head)" in source
    assert "max-height:none!important" in source
    assert "overflow:visible!important" in source
    assert "MutationObserver" in source


def test_all_new_ux_layers_are_loaded_in_the_required_order():
    hooks = text(HOOKS)
    measurement = '"public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_actions_ux.js"'
    secure_dxf = '"public/js/secure_dxf_export.js"'
    toolbar = '"public/js/door_cutting_order/core/door_cutting_order_toolbar_stability_ux.js"'
    assert "doctype_list_js = {" in hooks
    assert '"Door Cutting Order": "public/js/door_cutting_order_list.js"' in hooks
    assert measurement in hooks
    assert secure_dxf in hooks
    assert toolbar in hooks
    assert hooks.index(measurement) < hooks.index(secure_dxf) < hooks.index(toolbar)
