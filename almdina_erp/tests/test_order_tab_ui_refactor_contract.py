from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCTYPE = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
MANIFEST = ROOT / "frontend_assets.py"
LAYOUT = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "door_cutting_order_order_tab_layout_ux.js"
)
DEFAULTS = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "door_cutting_order_defaults.js"
)
SHOP_FLOOR = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "production"
    / "shop_floor_order_ux.js"
)


def test_order_schema_removes_external_reference_and_requires_edge_defaults() -> None:
    payload = json.loads(DOCTYPE.read_text(encoding="utf-8"))
    fields = {field["fieldname"]: field for field in payload["fields"]}
    order = payload["field_order"]

    assert "external_reference" not in fields
    assert "external_reference" not in order
    assert "cutting_settings_section" not in fields
    assert "cutting_settings_section" not in order
    assert "cutting_machine_type" not in fields
    assert fields["default_edge_type"].get("reqd") == 1
    assert fields["edge_color"].get("reqd") == 1


def test_order_cutting_machine_is_optional_on_server_and_radio_on_form() -> None:
    payload = json.loads(DOCTYPE.read_text(encoding="utf-8"))
    fields = {field["fieldname"]: field for field in payload["fields"]}
    order = payload["field_order"]
    machine = fields["order_cutting_machine"]

    assert machine["fieldtype"] == "Select"
    assert machine["label"] == "Cutting Machine"
    assert machine["options"] == "\nCNC\nمشرحة"
    assert "reqd" not in machine
    assert "in_list_view" not in machine
    assert "default" not in machine
    assert order.index("order_cutting_machine") == order.index("important_note_comment") + 1
    assert order.index("important_note_preview") == order.index("order_notes") + 1
    assert order.index("board_section") == order.index("order_cutting_machine") + 1


def test_board_and_edge_inputs_share_one_material_section() -> None:
    payload = json.loads(DOCTYPE.read_text(encoding="utf-8"))
    order = payload["field_order"]
    material_slice = order[
        order.index("board_section") : order.index("pieces_section")
    ]

    assert material_slice == [
        "board_section",
        "board_description",
        "board_length_column",
        "board_length_cm",
        "board_width_cm",
        "board_width_column",
        "default_edge_type",
        "edge_color",
    ]


def test_order_layout_presenter_is_presentation_only_and_loaded_after_operator_owner() -> None:
    manifest = MANIFEST.read_text(encoding="utf-8")
    layout = LAYOUT.read_text(encoding="utf-8")

    operator_asset = '"public/js/door_cutting_order/order_entry/door_cutting_order_operator_ux.js"'
    layout_asset = '"public/js/door_cutting_order/order_entry/door_cutting_order_order_tab_layout_ux.js"'
    machine_asset = '"public/js/door_cutting_order/order_entry/door_cutting_order_cutting_machine_ux.js"'
    keyboard_asset = '"public/js/door_cutting_order/order_entry/measurements/door_cutting_order_fast_entry_keyboard_ux.js"'

    assert layout_asset in manifest
    assert machine_asset in manifest
    assert manifest.index(operator_asset) < manifest.index(layout_asset) < manifest.index(machine_asset) < manifest.index(keyboard_asset)
    assert "frappe.call" not in layout
    assert "frm.save" not in layout
    assert "frm.set_value" not in layout
    assert "AlmdinaOrderEdgeOptions" in layout
    assert "AlmdinaOrderCuttingMachineUX" in layout
    assert "dco-order-intake-card" in layout
    assert "dco-material-edge-card" in layout
    assert "dco-measurements-card" in layout
    assert "autoGrowNotes" in layout


def test_order_and_material_controls_follow_exact_requested_rows() -> None:
    layout = LAYOUT.read_text(encoding="utf-8")

    assert "operator_status_strip" in layout
    assert "dco-order-status-shell" in layout
    assert "function ensureStatusShell" in layout
    assert "border-bottom: none !important" in layout
    assert "margin-block: 6px 10px !important" in layout
    assert "padding-block: 14px 16px !important" in layout
    assert "padding-inline: 44px !important" in layout
    assert "dco-measurements-mobile-scroll" in layout
    assert "padding-inline: 20px !important" in layout
    assert "grid-template-columns: minmax(0, 2fr) minmax(220px, 1fr)" in layout
    assert "dco-order-intake-card > .section-body" in layout
    assert 'dco-order-intake-card [data-fieldname="customer"]' in layout
    assert 'dco-order-intake-card [data-fieldname="order_date"]' in layout
    assert 'dco-order-intake-card [data-fieldname="order_notes"]' in layout
    assert 'dco-order-intake-card [data-fieldname="order_cutting_machine"]' in layout
    assert "grid-column: 1 / -1" in layout
    assert "grid-row: 4" in layout
    assert "section-body > .dco-order-section-heading" in layout
    assert "max-width: none !important" in layout
    assert "height: 38px !important" in layout
    assert "max-width: none !important" in layout

    # Material controls must be placed into two explicit visual rows using the
    # original Frappe wrappers, not left to Column Break nesting.
    assert "const MATERIAL_ROWS = Object.freeze" in layout
    assert '"board_description"' in layout
    assert '"board_length_cm"' in layout
    assert '"board_width_cm"' in layout
    assert '"default_edge_type"' in layout
    assert '"edge_color"' in layout
    assert "function ensureMaterialRows(frm)" in layout
    assert 'ensureMaterialRow(body, "primary")' in layout
    assert 'ensureMaterialRow(body, "edge")' in layout
    assert "primary.appendChild(node)" in layout
    assert "edge.appendChild(node)" in layout
    assert "dco-material-row--primary" in layout
    assert "grid-template-columns: minmax(0,2fr) minmax(140px,1fr) minmax(140px,1fr)" in layout
    assert "dco-material-row--edge" in layout
    assert "grid-template-columns: repeat(2,minmax(0,1fr))" in layout


def test_order_tracking_strip_exposes_layout_hook_class() -> None:
    source = SHOP_FLOOR.read_text(encoding="utf-8")

    assert "dco-order-tracking-strip" in source
    assert "margin-bottom:10px" not in source


def test_notes_and_edge_color_never_disappear_when_empty() -> None:
    layout = LAYOUT.read_text(encoding="utf-8")

    assert 'order_notes: "أضف ملاحظة للطلب…"' in layout
    assert 'order_cutting_machine: "اختر آلة القص"' in layout
    assert 'edge_color: "أدخل لون القشاط"' in layout
    assert "function keepFieldVisible" in layout
    assert 'wrapper.classList.add("dco-keep-empty-field")' in layout
    assert 'wrapper.classList.remove("hide-control")' in layout
    assert 'wrapper.removeAttribute("hidden")' in layout
    assert 'input.setAttribute("placeholder", __(placeholder))' in layout
    assert "dco-empty-display:empty::before" in layout
    assert "removeLegacyRequiredHint" in layout
    assert "ensureRequiredHint" not in layout


def test_order_notes_are_disabled_outside_order_edit_session() -> None:
    layout = LAYOUT.read_text(encoding="utf-8")

    assert "function isOrderNotesEditable" in layout
    assert "function syncOrderNotesAccess" in layout
    assert "function syncLockedInput" in layout
    assert "api.isEditableDraft" in layout
    assert "textarea.disabled = !editable" in layout
    assert "textarea.readOnly = !editable" in layout
    assert 'syncLockedInput(frm, "order_cutting_machine")' in layout
    assert "dco-order-notes-locked" in layout
    assert "dco-order-notes-locked select:disabled" in layout
    assert "dco-order-notes-locked input[type=\"radio\"]:disabled" in layout
    assert "almdina_edit_session_changed(frm) { schedule(frm); }" in layout


def test_cutting_machine_radios_are_client_required_and_server_optional() -> None:
    machine = (
        ROOT
        / "public"
        / "js"
        / "door_cutting_order"
        / "order_entry"
        / "door_cutting_order_cutting_machine_ux.js"
    ).read_text(encoding="utf-8")

    assert 'input.type = "radio"' in machine
    assert 'value: "CNC"' in machine
    assert 'value: "مشرحة"' in machine
    assert 'set_value("order_cutting_machine"' in machine
    assert 'validate(frm) { validateSelection(frm); }' in machine
    assert "frappe.throw" in machine
    assert "يجب اختيار نوع آلة القص" in machine
    assert 'content: " *"' in machine
    assert ".control-label::after" in machine
    assert ".form-group label::after" not in machine
    assert ".dco-cutting-machine-option::after" in machine
    assert "content: none !important" in machine
    assert ".dco-cutting-machine-host .control-input-wrapper" in machine
    assert ".dco-cutting-machine-host .control-input" in machine
    assert "display: none !important" in machine
    assert "dco-cutting-machine-row" in machine
    assert "function ensureInlineRow" in machine
    assert "row.insertBefore(labelHost, row.firstChild)" in machine
    assert "row.appendChild(group)" in machine
    assert "flex-direction: row !important" in machine
    assert "flex-wrap: nowrap !important" in machine
    assert "white-space: nowrap" in machine
    assert "input-max-width" in machine
    assert "new MutationObserver" in machine
    assert 'querySelector(".form-group")' in machine
    assert "after_save(frm) { schedule(frm); }" in machine
    assert "isEditableDraft" in machine
    assert "frappe.call" not in machine
    assert "frm.save" not in machine


def test_arabic_labels_reflect_the_new_information_hierarchy() -> None:
    defaults = DEFAULTS.read_text(encoding="utf-8")

    assert 'order_details_section: "بيانات الطلب"' in defaults
    assert 'board_section: "المادة والقشاط"' in defaults
    assert 'default_edge_type: "نوع القشاط الافتراضي"' in defaults
    assert 'edge_color: "لون القشاط"' in defaults
    assert 'order_cutting_machine: "نوع آلة القص"' in defaults
    assert "cutting_settings_section" not in defaults


FORM_TAB_LAYOUT_CSS = ROOT / "public" / "css" / "door_cutting_order_form_tab_layout.css"
PLAN_VISUAL = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "core"
    / "door_cutting_order_plan_cost_workspace_visual_ux.js"
)


PLAN_CONTENT_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "cutting_plan"
    / "door_cutting_order_plan_content_ux.js"
)


def test_form_tab_layout_css_centers_order_and_plan_surfaces() -> None:
    css = FORM_TAB_LAYOUT_CSS.read_text(encoding="utf-8")
    visual = PLAN_VISUAL.read_text(encoding="utf-8")
    plan_content = PLAN_CONTENT_UX.read_text(encoding="utf-8")
    manifest = MANIFEST.read_text(encoding="utf-8")

    assert 'door_cutting_order_form_tab_layout.css' in manifest
    assert "--dco-tab-shell-max: 1440px" in css
    assert "--dco-tab-content-gutter:" in css
    assert "order_tab_layout_ux.js" in css
    assert "padding-inline: 20px !important" in visual
    assert ".dco-plan-section-card.dco-layout-card > .section-body" in visual
    assert "dco-plan-settings-readonly[data-almdina-plan-settings-summary-owner=\"stable\"]" in visual
    assert "--dco-plan-card-inset-inline" in visual
    assert "max-width: none !important" in visual
    assert ".dco-plan-section-card.dco-layout-card .form-column" in visual
    assert "border-bottom: none !important" in visual
    assert "dco-plan-settings-readonly[data-almdina-plan-settings-summary-owner=\"stable\"]" in visual
    assert "dco-plan-cost-workspace-visual-ux-v2" in visual
    assert ".dco-operator-form .dco-plan-section-card.dco-layout-card > .section-body" in visual
    assert "hide-border" in plan_content
