from __future__ import annotations

import json
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
FORM_JSON = APP_ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
UX_JS = APP_ROOT / "public" / "js" / "door_cutting_order_operator_ux.js"
HOOKS = APP_ROOT / "hooks.py"


def test_order_form_uses_operator_first_tabs_and_dedicated_fast_measurements_surface():
    payload = json.loads(FORM_JSON.read_text(encoding="utf-8"))
    fields = {field["fieldname"]: field for field in payload["fields"]}

    assert fields["order_tab"]["fieldtype"] == "Tab Break"
    assert fields["results_tab"]["fieldtype"] == "Tab Break"
    assert fields["operator_status_strip"]["fieldtype"] == "HTML"
    assert fields["board_summary_html"]["fieldtype"] == "HTML"
    assert fields["pieces_fast_entry"]["fieldtype"] == "HTML"

    # The native Frappe editable grid is kept only as the authoritative child-table
    # storage surface. Operators use the dedicated HTML editor, avoiding active-row
    # semantics, delayed control creation and checkbox double-click behaviour.
    assert fields["pieces"]["fieldtype"] == "Table"
    assert fields["pieces"].get("hidden") == 1
    assert fields["pieces"].get("reqd") == 1

    for fieldname in (
        "status",
        "revision",
        "approved_plan",
        "board_material",
        "board_color",
        "board_thickness_mm",
        "full_board_length_mm",
        "full_board_width_mm",
    ):
        assert fields[fieldname].get("hidden") == 1, fieldname

    order = payload["field_order"]
    assert order.index("customer") < order.index("board_item") < order.index("pieces_fast_entry")
    assert order.index("pieces_fast_entry") < order.index("pieces") < order.index("results_tab")


def test_measurement_keyboard_flow_is_plain_dom_width_tab_length_enter_next_width():
    source = UX_JS.read_text(encoding="utf-8")
    required_fragments = [
        'class="dco-fast-input" type="number"',
        'data-field="width_cm"',
        'data-field="length_cm"',
        'event.key === "Tab" && !event.shiftKey && fieldname === "width_cm"',
        "the browser moves directly to Length with zero Frappe row activation",
        'event.key === "Enter" && fieldname === "length_cm"',
        "moveToNextWidth(frm, tr)",
        "focusWidth(next)",
        'input.focus({ preventScroll:true })',
        "DOM insertion and focus are both synchronous",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in source]
    assert not missing, f"Missing fast keyboard UX fragments: {missing}"

    tab_block = source.split('if (event.key === "Tab" && !event.shiftKey && fieldname === "width_cm")', 1)[1]
    tab_block = tab_block.split('if (event.key === "Enter" && fieldname === "width_cm")', 1)[0]
    assert "preventDefault" not in tab_block
    assert "setTimeout" not in tab_block
    assert "toggle_editable_row" not in tab_block
    assert ".click(" not in tab_block


def test_fast_measurements_editor_does_not_depend_on_frappe_active_grid_row():
    source = UX_JS.read_text(encoding="utf-8")
    forbidden = [
        "gridRow.toggle_editable_row",
        "frappe.ui.form.editable_row",
        "grid.add_new_row",
        "dco-fast-check",
        "toggle_editable_row(true)",
    ]
    leaked = [fragment for fragment in forbidden if fragment in source]
    assert not leaked, f"Native editable-grid dependency leaked back into fast editor: {leaked}"

    required = [
        'frappe.model.add_child(frm.doc, "Door Cutting Order Detail", "pieces")',
        "materializeVirtualRow(frm, tr)",
        "ensureSingleVirtualRow(frm)",
        "row[fieldname] = value",
        "frm.dirty()",
    ]
    missing = [fragment for fragment in required if fragment not in source]
    assert not missing, f"Missing direct model synchronization fragments: {missing}"


def test_edge_and_rotation_controls_are_true_one_click_buttons_outside_native_grid():
    source = UX_JS.read_text(encoding="utf-8")
    for fieldname in (
        "allow_rotation",
        "edge_long_right",
        "edge_long_left",
        "edge_width_top",
        "edge_width_bottom",
    ):
        assert f'"{fieldname}"' in source

    required = [
        'class="dco-check-toggle',
        'data-check-field="${field}"',
        "toggleCheck(frm, check)",
        "row[fieldname] = next",
        'button.classList.toggle("is-checked"',
        'root.addEventListener("pointerdown"',
        "event.stopPropagation()",
    ]
    missing = [fragment for fragment in required if fragment not in source]
    assert not missing, f"Missing one-click toggle fragments: {missing}"


def test_fast_editor_keeps_background_recalculation_separate_from_input_focus():
    source = UX_JS.read_text(encoding="utf-8")
    assert "triggerChildField" in source
    assert "frm.script_manager.trigger(fieldname, row.doctype, row.name)" in source
    assert "syncInputToModel(frm, input, false)" in source
    assert "setTimeout(() => focus" not in source
    assert "frm.refresh_field(\"pieces\")" not in source


def test_operator_ux_bundle_is_loaded():
    hooks = HOOKS.read_text(encoding="utf-8")
    assert '"/assets/almdina_erp/js/door_cutting_order_operator_ux.js"' in hooks
