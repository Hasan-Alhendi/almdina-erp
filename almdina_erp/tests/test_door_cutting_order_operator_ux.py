from __future__ import annotations

import json
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
FORM_JSON = APP_ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
UX_JS = APP_ROOT / "public" / "js" / "door_cutting_order_operator_ux.js"
HOOKS = APP_ROOT / "hooks.py"


def test_order_form_uses_operator_first_tabs_and_summary_blocks():
    payload = json.loads(FORM_JSON.read_text(encoding="utf-8"))
    fields = {field["fieldname"]: field for field in payload["fields"]}

    assert fields["order_tab"]["fieldtype"] == "Tab Break"
    assert fields["results_tab"]["fieldtype"] == "Tab Break"
    assert fields["operator_status_strip"]["fieldtype"] == "HTML"
    assert fields["board_summary_html"]["fieldtype"] == "HTML"

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
    assert order.index("customer") < order.index("board_item") < order.index("pieces")
    assert order.index("pieces") < order.index("results_tab") < order.index("cutting_plan_html")


def test_measurement_keyboard_flow_uses_native_tab_and_direct_row_activation():
    source = UX_JS.read_text(encoding="utf-8")
    required_fragments = [
        'event.key === "Tab" && !event.shiftKey && fieldname === "width_cm"',
        "Do not preventDefault and do not trigger a click. Native Tab is instant.",
        'event.key === "Enter" && fieldname === "length_cm"',
        "target = grid.add_new_row(null, null, false, null, true)",
        'focusGridFieldFast(frm, target.name, "width_cm"',
        "gridRow.toggle_editable_row(true)",
        "inputForGridField(gridRow, fieldname)",
        '$gridWrapper.off("keydown.dco_enter_add_row")',
    ]
    missing = [fragment for fragment in required_fragments if fragment not in source]
    assert not missing, f"Missing keyboard UX fragments: {missing}"

    # Regression: the former implementation prevented Tab, clicked the next cell,
    # and waited on setTimeout. That caused the visible pause reported by operators.
    tab_block = source.split('if (event.key === "Tab" && !event.shiftKey && fieldname === "width_cm")', 1)[1]
    tab_block = tab_block.split('if (event.key === "Enter" && fieldname === "length_cm")', 1)[0]
    assert "preventDefault" not in tab_block
    assert ".trigger(\"click\")" not in tab_block
    assert "setTimeout" not in tab_block


def test_edge_and_rotation_checks_are_persistent_one_click_buttons():
    source = UX_JS.read_text(encoding="utf-8")
    for fieldname in (
        "allow_rotation",
        "edge_long_right",
        "edge_long_left",
        "edge_width_top",
        "edge_width_bottom",
    ):
        assert f'"{fieldname}"' in source

    required_fragments = [
        'class: "dco-fast-check"',
        'column.field_area && column.field_area.hide()',
        'column.static_area.show()',
        '$button.on("click.dco_fast_check"',
        "event.stopImmediatePropagation()",
        "setFastCheckVisual($button, nextValue)",
        "frappe.model.set_value",
        "gridRow.toggle_editable_row = function (...args)",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in source]
    assert not missing, f"Missing one-click checkbox UX fragments: {missing}"


def test_operator_ux_avoids_slow_timer_based_focus_navigation():
    source = UX_JS.read_text(encoding="utf-8")
    assert "requestAnimationFrame" in source
    assert "focusGridFieldFast" in source
    assert "focusGridFieldNow" in source
    assert "setTimeout(() => focusGridField" not in source


def test_operator_ux_bundle_is_loaded():
    hooks = HOOKS.read_text(encoding="utf-8")
    assert '"/assets/almdina_erp/js/door_cutting_order_operator_ux.js"' in hooks
