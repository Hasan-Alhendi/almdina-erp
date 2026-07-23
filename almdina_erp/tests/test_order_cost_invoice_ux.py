from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
DOCTYPE = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
EDGE_TYPE = ROOT / "almdina_erp" / "doctype" / "edge_banding_type" / "edge_banding_type.json"
UX = ROOT / "public" / "js" / "door_cutting_order_cost_invoice_ux.js"
HEADER_UX = ROOT / "public" / "js" / "door_cutting_order_header_ux.js"
HOOKS = ROOT / "hooks.py"


def _ux() -> str:
    return UX.read_text(encoding="utf-8")


def test_primary_tabs_are_order_cutting_plan_then_order_cost():
    doc = json.loads(DOCTYPE.read_text(encoding="utf-8"))
    order = doc["field_order"].index("order_tab")
    plan = doc["field_order"].index("results_tab")
    cost = doc["field_order"].index("cost_tab")
    assert order < plan < cost
    fields = {row["fieldname"]: row for row in doc["fields"]}
    assert fields["cost_tab"]["fieldtype"] == "Tab Break"
    assert fields["order_cost_invoice_html"]["fieldtype"] == "HTML"


def test_primary_tab_bar_is_sticky_and_labels_are_arabic():
    src = HEADER_UX.read_text(encoding="utf-8")
    assert ".dco-sticky-tabs" in src
    assert "position: sticky !important" in src
    assert 'frm.set_df_property("order_tab", "label", "الطلب")' in src
    assert 'frm.set_df_property("results_tab", "label", "خطة القص")' in src
    assert 'frm.set_df_property("cost_tab", "label", "تكلفة الطلب")' in src


def test_cost_measurements_remove_edge_length_and_keep_visual_directions():
    src = _ux()
    assert "جدول قياسات الطلب" in src
    assert "<th>طول القشاط (م)</th>" not in src
    assert "<th>طول القشاط م</th>" not in src
    assert "نوع القشاط" in src
    assert "dco-notes-col" in src
    assert "جهات القشاط" not in src
    assert "طول يمين" not in src
    assert "طول يسار" not in src
    assert "عرض أعلى" not in src
    assert "عرض أسفل" not in src


def test_width_and_length_show_one_or_two_visual_edge_lines():
    src = _ux()
    assert "width_edge_count" in src
    assert "length_edge_count" in src
    assert "row.edge_width_top" in src
    assert "row.edge_width_bottom" in src
    assert "row.edge_long_right" in src
    assert "row.edge_long_left" in src
    assert "dimensionMark(row.width_cm, row.width_edge_count)" in src
    assert "dimensionMark(row.length_cm, row.length_edge_count)" in src
    assert "dco-dimension-edge-line" in src
    assert "Array.from({ length: count }" in src
    assert "خط واحد أسفل البعد = جهة قشاط واحدة، خطان = جهتان" in src


def test_edge_color_exists_in_master_and_replaces_top_edge_meter_summary():
    edge_doc = json.loads(EDGE_TYPE.read_text(encoding="utf-8"))
    fields = {row["fieldname"]: row for row in edge_doc["fields"]}
    assert fields["edge_color"]["fieldtype"] == "Data"
    src = _ux()
    assert 'frappe.db.get_value("Edge Banding Type", type, "edge_color")' in src
    assert "لون القشاط" in src
    assert '<span class="label">إجمالي القشاط</span>' not in src
    assert '<div><b>إجمالي القشاط</b>' not in src


def test_customer_invoice_breaks_down_boards_cutting_and_edge_banding():
    src = _ux()
    assert "ألواح MDF" in src
    assert "أجور قص وتجهيز الألواح" in src
    assert "قشاط —" in src
    assert "frm.doc.mdf_cost_usd" in src
    assert "frm.doc.cutting_cost_usd" in src
    assert "frm.doc.edge_cost_usd" in src
    assert "frm.doc.total_cost_usd" in src


def test_invoice_has_customer_print_action_and_a4_print_css():
    src = _ux()
    assert "طباعة فاتورة الزبون" in src
    assert "@page{size:A4 portrait" in src
    assert "فاتورة تكلفة الطلب" in src
    assert "dimensionMark(row.width_cm,row.width_edge_count,true)" in src
    assert "dimensionMark(row.length_cm,row.length_edge_count,true)" in src
    assert 'class="notes-col">ملاحظات' in src


def test_invoice_printing_uses_isolated_iframe_not_popup_window():
    src = _ux()
    assert 'document.createElement("iframe")' in src
    assert 'frame.srcdoc = buildPrintHtml(frm)' in src
    assert 'printWindow.print()' in src
    assert 'printWindow.addEventListener("afterprint", cleanup' in src
    assert 'window.open(' not in src
    assert "اسمح بالنوافذ المنبثقة" not in src


def test_cost_invoice_script_is_loaded_for_door_cutting_order():
    hooks = HOOKS.read_text(encoding="utf-8")
    assert '"public/js/door_cutting_order_cost_invoice_ux.js"' in hooks
