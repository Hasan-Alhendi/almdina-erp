from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCTYPE = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
BOARD_UX = ROOT / "public" / "js" / "door_cutting_order_board_text_ux.js"
DEFAULTS_UX = ROOT / "public" / "js" / "door_cutting_order_defaults.js"
COST_UX = ROOT / "public" / "js" / "door_cutting_order_cost_invoice_ux.js"
MEASUREMENT_UX = ROOT / "public" / "js" / "door_cutting_order_measurement_actions_ux.js"
PLAN_UX = ROOT / "public" / "js" / "door_cutting_order_plan_ux.js"
FAST_SAVE_UX = ROOT / "public" / "js" / "door_cutting_order_fast_save_ux.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_order_uses_free_text_board_description_and_dimensions():
    payload = json.loads(DOCTYPE.read_text(encoding="utf-8"))
    fields = {field["fieldname"]: field for field in payload["fields"]}

    assert fields["board_description"]["fieldtype"] == "Data"
    assert fields["board_description"].get("reqd") == 1
    assert fields["board_length_cm"]["fieldtype"] == "Float"
    assert fields["board_width_cm"]["fieldtype"] == "Float"
    assert fields["board_length_cm"].get("default") == "244"
    assert fields["board_width_cm"].get("default") == "122"
    assert fields["board_item"].get("hidden") == 1
    assert fields["board_item"].get("reqd") != 1


def test_removed_board_attributes_do_not_return_to_order_form():
    payload = json.loads(DOCTYPE.read_text(encoding="utf-8"))
    fieldnames = {field["fieldname"] for field in payload["fields"]}
    for removed in ("board_material", "board_color", "board_thickness_mm"):
        assert removed not in fieldnames
        assert removed not in payload["field_order"]


def test_board_text_ux_syncs_visible_controls_before_save():
    source = _source(BOARD_UX)
    assert "function controlValue(frm, fieldname)" in source
    assert 'field.$input.val()' in source
    assert "async function syncInputs(frm)" in source
    assert "await frm.set_value(updates)" in source
    assert "before_save(frm) { return syncInputs(frm); }" in source
    assert "syncInputs," in source


def test_board_text_ux_keeps_default_dimensions_and_hidden_mm_snapshot_in_sync():
    source = _source(DEFAULTS_UX)
    assert "frm.doc.board_length_cm = 244" in source
    assert "frm.doc.board_width_cm = 122" in source
    assert "frm.doc.full_board_length_mm = Number(frm.doc.board_length_cm) * 10" in source
    assert "frm.doc.full_board_width_mm = Number(frm.doc.board_width_cm) * 10" in source


def test_board_form_labels_and_help_are_operator_friendly():
    source = _source(DEFAULTS_UX)
    for text in (
        "صنف اللوح",
        "طول اللوح (سم)",
        "عرض اللوح (سم)",
        "MDF أبيض 18 مم",
    ):
        assert text in source


def test_native_stock_board_fields_are_not_required_by_order_save_pipeline():
    source = _source(
        ROOT
        / "almdina_erp"
        / "infrastructure"
        / "frappe"
        / "orders"
        / "document_access.py"
    )
    assert 'getattr(self.document, "board_description", "")' in source
    assert "Board description is required" in source
    assert 'getattr(self.document, "board_length_cm", None) or 244' in source
    assert 'getattr(self.document, "board_width_cm", None) or 122' in source
    assert "self.document.full_board_length_mm = length_cm * 10" in source
    assert "self.document.full_board_width_mm = width_cm * 10" in source
    assert "self.document.board_item.item_name" not in source
    assert "frappe.get_doc(\"Item\", self.document.board_item)" not in source


def test_plan_payload_uses_board_description_not_stock_item():
    source = _source(
        ROOT
        / "almdina_erp"
        / "infrastructure"
        / "frappe"
        / "orders"
        / "plan_adapter.py"
    )
    assert 'getattr(source, "board_description", "")' in source
    assert 'payload["board"]["description"] = description' in source
    assert "source.board_item" not in source


def test_invoice_and_measurement_prints_use_only_board_description_as_visible_label():
    source = _source(BOARD_UX)
    assert 'String(frm.doc.board_description || "")' in source
    assert "frm.doc.board_description || frm.doc.board_item" not in source
    assert "ألواح MDF — ${label}" in source
    assert "PRINT_TRIGGER_SELECTOR" in source


def test_fast_save_and_plan_controls_use_free_text_board_validation():
    fast_save = _source(FAST_SAVE_UX)
    plan_ux = _source(PLAN_UX)
    board_ux = _source(BOARD_UX)
    assert "function canCalculatePlan(frm)" in board_ux
    assert "const boardUX = window.AlmdinaBoardTextUX" in fast_save
    assert "boardUX.canCalculatePlan(frm)" in fast_save
    assert "AlmdinaBoardTextUX.canCalculatePlan" in plan_ux
    assert "!frm.doc.board_item" not in fast_save
    assert "!frm.doc.board_item" not in plan_ux
    assert "اختر اللوح وأدخل القياسات" not in fast_save
    assert "اختر اللوح وأدخل القياسات" not in plan_ux


def test_preview_api_serializes_free_text_board_fields_only():
    source = _source(ROOT / "almdina_erp" / "api.py")
    preview_block = source.split("def _serialize_order_preview", 1)[1].split(
        "def _approved_order_plan_name", 1
    )[0]
    assert '"board_description"' in preview_block
    assert '"board_length_cm"' in preview_block
    assert '"board_width_cm"' in preview_block
    assert '"board_item":' not in preview_block
    assert '"board_material":' not in preview_block
    assert '"board_color":' not in preview_block
    assert '"board_thickness_mm":' not in preview_block
