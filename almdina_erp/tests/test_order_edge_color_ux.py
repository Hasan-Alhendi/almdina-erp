from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
DOCTYPE = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
DEFAULTS = ROOT / "public" / "js" / "door_cutting_order_defaults.js"
EDGE_COLOR_UX = ROOT / "public" / "js" / "door_cutting_order_edge_color_ux.js"
MEASUREMENT_UX = ROOT / "public" / "js" / "door_cutting_order_measurement_actions_ux.js"
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


def test_edge_color_stays_in_cost_kpi_and_fast_entry_context_without_table_duplicates():
    source = _source(EDGE_COLOR_UX)
    assert "updateColorKpi(frm, root)" in source
    assert "patchFastEntryContext(frm)" in source
    assert "لون القشاط:" in source
    assert "removeLegacyColorDuplicates(root)" in source
    assert "patchMeasurementTable" not in source
    assert "patchInvoiceLines" not in source
    assert "patchInvoiceMeta" not in source


def test_customer_print_contains_edge_color_in_header_only():
    source = _source(EDGE_COLOR_UX)
    print_section = source.split("function printHtml(frm)", 1)[1].split(
        "function printCustomerInvoice(frm)", 1
    )[0]
    assert "printCustomerInvoice(frm)" in source
    assert "measurementTable.outerHTML" in source
    assert "invoiceTable.outerHTML" in source
    assert 'const edgeColor = orderEdgeColor(frm)' in print_section
    assert '<div><b>لون القشاط</b>${esc(edgeColor)}</div>' in print_section
    assert "grid-template-columns:repeat(5" in print_section
    assert 'document.createElement("iframe")' in source
    assert 'event.stopImmediatePropagation()' in source


def test_measurement_print_and_standalone_header_contain_edge_color():
    source = _source(MEASUREMENT_UX)
    assert "function orderEdgeColor(frm)" in source
    assert 'const edgeColor = orderEdgeColor(frm)' in source
    assert '<div><b>لون القشاط</b>${esc(edgeColor)}</div>' in source
    assert "grid-template-columns:repeat(5" in source


def test_edge_color_layer_loads_after_invoice_renderer():
    hooks = HOOKS.read_text(encoding="utf-8")
    invoice = '"public/js/door_cutting_order_cost_invoice_ux.js"'
    edge_color = '"public/js/door_cutting_order_edge_color_ux.js"'
    assert invoice in hooks
    assert edge_color in hooks
    assert hooks.index(invoice) < hooks.index(edge_color)
