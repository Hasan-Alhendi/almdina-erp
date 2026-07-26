import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCTYPE_JSON = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
HOOKS = ROOT / "hooks.py"
LIST_UX = ROOT / "public" / "js" / "door_cutting_order_list.js"
MEASUREMENT_UX = ROOT / "public" / "js" / "door_cutting_order_measurement_actions_ux.js"
EDGE_COLOR_UX = ROOT / "public" / "js" / "door_cutting_order_edge_color_ux.js"
TOOLBAR_UX = ROOT / "public" / "js" / "door_cutting_order_toolbar_stability_ux.js"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_order_search_includes_customer_and_explains_id_or_customer_search():
    doctype = json.loads(text(DOCTYPE_JSON))
    assert doctype["search_fields"] == "customer"
    source = text(LIST_UX)
    assert "ابحث باسم العميل أو رقم الطلب (ID)" in source
    assert '"customer", "order_date", "status"' in source


def test_measurement_table_has_print_and_full_window_actions():
    source = text(MEASUREMENT_UX)
    assert 'class="btn btn-default btn-sm dco-print-measurements"' in source
    assert "فتح الجدول في نافذة مستقلة" in source
    assert "window.open(" in source
    assert "dco-measurements-print-frame" in source
    assert "تفاصيل الأسعار والفاتورة" in source
    assert "dco-measurement-print-table" in source


def test_measurement_print_has_invoice_measurement_columns_without_invoice_totals():
    source = text(MEASUREMENT_UX)
    for label in ("النوع", "العرض (سم)", "الطول (سم)", "العدد", "نوع القشاط", "ملاحظات"):
        assert label in source
    assert "الإجمالي النهائي" not in source
    assert "تفاصيل الفاتورة" not in source


def test_customer_invoice_no_longer_prints_duplicate_edge_color_column():
    source = text(EDGE_COLOR_UX)
    print_section = source.split("function printHtml(frm)", 1)[1].split(
        "function printCustomerInvoice(frm)", 1
    )[0]
    assert "grid-template-columns:repeat(4" in print_section
    assert "<b>نوع القشاط</b>" in print_section
    assert "<b>لون القشاط</b>" not in print_section
    assert "patchMeasurementTable" not in source
    assert "patchInvoiceLines" not in source
    assert "patchInvoiceMeta" not in source
    assert "removeLegacyColorDuplicates" in source


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
    measurement = '"public/js/door_cutting_order_measurement_actions_ux.js"'
    secure_dxf = '"public/js/secure_dxf_export.js"'
    toolbar = '"public/js/door_cutting_order_toolbar_stability_ux.js"'
    assert 'doctype_list_js = {' in hooks
    assert '"Door Cutting Order": "public/js/door_cutting_order_list.js"' in hooks
    assert measurement in hooks
    assert secure_dxf in hooks
    assert toolbar in hooks
    assert hooks.index(measurement) < hooks.index(secure_dxf) < hooks.index(toolbar)
