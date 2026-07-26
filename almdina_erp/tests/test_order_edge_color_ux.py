from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
DOCTYPE = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
DEFAULTS = ROOT / "public" / "js" / "door_cutting_order_defaults.js"
EDGE_COLOR_UX = ROOT / "public" / "js" / "door_cutting_order_edge_color_ux.js"
HOOKS = ROOT / "hooks.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_order_has_editable_text_edge_color_below_default_edge_type():
    doc = json.loads(DOCTYPE.read_text(encoding="utf-8"))
    fields = {row["fieldname"]: row for row in doc["fields"]}
    assert fields["edge_color"]["fieldtype"] == "Data"
    assert not fields["edge_color"].get("read_only")
    assert doc["field_order"].index("default_edge_type") < doc["field_order"].index("edge_color")
    assert doc["field_order"].index("edge_color") < doc["field_order"].index("cutting_settings_column")


def test_edge_color_is_defaulted_from_selected_edge_type_but_remains_editable():
    source = _source(DEFAULTS)
    assert 'frappe.db.get_value("Edge Banding Type", requestedType, "edge_color")' in source
    assert 'frm.set_value("edge_color", color)' in source
    assert "default_edge_type(frm)" in source
    assert "apply_edge_color_default(frm, true)" in source


def test_edge_color_remains_visible_once_in_cost_summary_and_fast_entry_context():
    source = _source(EDGE_COLOR_UX)
    assert "updateColorKpi(frm, root)" in source
    assert "patchFastEntryContext(frm)" in source
    assert "لون القشاط:" in source
    assert "patchMeasurementTable" not in source
    assert "patchInvoiceLines" not in source
    assert "patchInvoiceMeta" not in source


def test_customer_print_keeps_edge_type_and_removes_duplicate_edge_color():
    source = _source(EDGE_COLOR_UX)
    assert "printCustomerInvoice(frm)" in source
    assert "measurementTable.outerHTML" in source
    assert "invoiceTable.outerHTML" in source
    print_section = source.split("function printHtml(frm)", 1)[1].split(
        "function printCustomerInvoice(frm)", 1
    )[0]
    assert '<div><b>نوع القشاط</b>${esc(frm.doc.default_edge_type || "—")}</div>' in print_section
    assert "<b>لون القشاط</b>" not in print_section
    assert "grid-template-columns:repeat(4" in print_section
    assert 'document.createElement("iframe")' in source
    assert 'event.stopImmediatePropagation()' in source


def test_edge_color_layer_loads_after_invoice_renderer():
    hooks = HOOKS.read_text(encoding="utf-8")
    invoice = '"public/js/door_cutting_order_cost_invoice_ux.js"'
    edge_color = '"public/js/door_cutting_order_edge_color_ux.js"'
    assert invoice in hooks
    assert edge_color in hooks
    assert hooks.index(invoice) < hooks.index(edge_color)
