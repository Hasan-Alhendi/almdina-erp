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


def test_edge_color_appears_in_cost_measurements_invoice_and_fast_entry_context():
    source = _source(EDGE_COLOR_UX)
    assert "patchMeasurementTable(frm, root)" in source
    assert 'header.textContent = "لون القشاط"' in source
    assert "patchInvoiceLines(frm, root)" in source
    assert "patchInvoiceMeta(frm, root)" in source
    assert "patchFastEntryContext(frm)" in source
    assert "لون القشاط:" in source


def test_customer_print_contains_edge_color_in_header_measurements_and_invoice():
    source = _source(EDGE_COLOR_UX)
    assert "printCustomerInvoice(frm)" in source
    assert "measurementTable.outerHTML" in source
    assert "invoiceTable.outerHTML" in source
    assert '<div><b>لون القشاط</b>${esc(color)}</div>' in source
    assert 'document.createElement("iframe")' in source
    assert 'event.stopImmediatePropagation()' in source


def test_edge_color_layer_loads_after_invoice_renderer():
    hooks = HOOKS.read_text(encoding="utf-8")
    invoice = '"public/js/door_cutting_order_cost_invoice_ux.js"'
    edge_color = '"public/js/door_cutting_order_edge_color_ux.js"'
    assert invoice in hooks
    assert edge_color in hooks
    assert hooks.index(invoice) < hooks.index(edge_color)
