from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
DOCTYPE = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
DEFAULTS = ROOT / "public" / "js" / "door_cutting_order_defaults.js"
EDGE_COLOR_UX = ROOT / "public" / "js" / "door_cutting_order_edge_color_ux.js"
EDGE_CONTROLS_UX = ROOT / "public" / "js" / "door_cutting_order_edge_profile_controls_ux.js"
EDGE_DOUBLE_CLICK_GUARD = ROOT / "public" / "js" / "door_cutting_order_edge_profile_double_click_guard.js"
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


def test_customer_print_uses_single_invoice_renderer_from_cost_tab():
    cost = _source(ROOT / "public" / "js" / "door_cutting_order_cost_invoice_ux.js")
    edge = _source(EDGE_COLOR_UX)
    assert "function invoiceTotal(frm)" in cost
    assert "invoiceLines(frm).reduce" in cost
    assert "board_rate_usd(frm) { scheduleRender(frm); }" in cost
    assert "cutting_cost_per_board_usd(frm) { scheduleRender(frm); }" in cost
    assert "printInvoice," in cost
    assert "function printHtml(frm)" not in edge
    assert "event.stopImmediatePropagation()" not in edge


def test_measurement_print_and_standalone_header_contain_edge_color():
    source = _source(MEASUREMENT_UX)
    assert "function orderEdgeColor(frm)" in source
    assert 'const edgeColor = orderEdgeColor(frm)' in source
    assert '<div><b>لون القشاط</b>${esc(edgeColor)}</div>' in source
    assert "grid-template-columns:repeat(5" in source


def test_edge_profiles_use_compact_double_click_popover_without_extra_row():
    controls = _source(EDGE_CONTROLS_UX)
    guard = _source(EDGE_DOUBLE_CLICK_GUARD)
    hooks = _source(HOOKS)

    assert "removeSideDropdownRows" in controls
    assert 'root.addEventListener("dblclick"' in controls
    assert "openSidePopover" in controls
    assert "dco-edge-profile-popover" in controls
    assert "is-edge-custom" in controls
    assert "tbody td{vertical-align:middle!important;" in controls
    assert "function ensureSideGrid" not in controls
    assert 'select.className = "dco-side-profile-select"' not in controls
    assert "new frappe.ui.Dialog" not in controls

    assert "const CLICK_DELAY_MS = 260" in guard
    assert 'document.addEventListener("click"' in guard
    assert 'document.addEventListener("dblclick"' in guard
    assert "replayingSingleClick" in guard
    assert "toggle.click()" in guard
    assert "controls.openSidePopover" in guard

    controls_script = '"public/js/door_cutting_order_edge_profile_controls_ux.js"'
    guard_script = '"public/js/door_cutting_order_edge_profile_double_click_guard.js"'
    cut_script = '"public/js/door_cutting_order_cut_dimensions_ux.js"'
    assert controls_script in hooks
    assert guard_script in hooks
    assert cut_script in hooks
    assert hooks.index(controls_script) < hooks.index(guard_script) < hooks.index(cut_script)


def test_edge_profile_lists_are_custom_and_scrollable():
    controls = _source(EDGE_CONTROLS_UX)

    assert "dco-all-sides-profile-button" in controls
    assert "ensureBulkButton" in controls
    assert "openBulkPopover" in controls
    assert "bulkPopoverOptionsHtml" in controls
    assert "overflow-y:auto" in controls
    assert "scrollbar-gutter:stable" in controls
    assert "touch-action:pan-y" in controls
    assert 'popover.addEventListener("wheel"' in controls
    assert "activePopover.element.contains(event.target)" in controls
    assert 'select = document.createElement("select")' not in controls


def test_edge_color_layer_loads_after_invoice_renderer():
    hooks = HOOKS.read_text(encoding="utf-8")
    invoice = '"public/js/door_cutting_order_cost_invoice_ux.js"'
    edge_color = '"public/js/door_cutting_order_edge_color_ux.js"'
    assert invoice in hooks
    assert edge_color in hooks
    assert hooks.index(invoice) < hooks.index(edge_color)
