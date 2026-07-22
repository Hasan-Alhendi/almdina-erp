from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
DOCTYPE = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
UX = ROOT / "public" / "js" / "door_cutting_order_cost_invoice_ux.js"
HOOKS = ROOT / "hooks.py"


def _ux() -> str:
    return UX.read_text(encoding="utf-8")


def test_order_cost_tab_is_between_order_and_cutting_plan():
    doc = json.loads(DOCTYPE.read_text(encoding="utf-8"))
    order = doc["field_order"].index("order_tab")
    cost = doc["field_order"].index("cost_tab")
    plan = doc["field_order"].index("results_tab")
    assert order < cost < plan
    fields = {row["fieldname"]: row for row in doc["fields"]}
    assert fields["cost_tab"]["fieldtype"] == "Tab Break"
    assert fields["order_cost_invoice_html"]["fieldtype"] == "HTML"


def test_cost_tab_contains_measurements_and_edge_length_column():
    src = _ux()
    assert "جدول قياسات الطلب" in src
    assert "طول القشاط (م)" in src
    assert "row.edge_meters" in src
    assert "جهات القشاط" in src
    assert "نوع القشاط" in src


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
    assert "window.print()" in src
    assert "فاتورة تكلفة الطلب" in src


def test_cost_invoice_script_is_loaded_for_door_cutting_order():
    hooks = HOOKS.read_text(encoding="utf-8")
    assert '"public/js/door_cutting_order_cost_invoice_ux.js"' in hooks
