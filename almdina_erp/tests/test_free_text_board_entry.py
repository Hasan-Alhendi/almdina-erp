from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCTYPE = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
BOARD_UX = ROOT / "public" / "js" / "door_cutting_order" / "order_entry" / "door_cutting_order_board_text_ux.js"
DEFAULTS_UX = ROOT / "public" / "js" / "door_cutting_order" / "order_entry" / "door_cutting_order_defaults.js"
COST_UX = ROOT / "public" / "js" / "door_cutting_order" / "costing" / "door_cutting_order_cost_presenter.js"
DOCUMENT_PRINT_PRESENTER = (
    ROOT / "public" / "js" / "door_cutting_order" / "printing" / "door_cutting_order_document_print_presenter.js"
)
PLAN_CONTROLS = ROOT / "public" / "js" / "door_cutting_order" / "cutting_plan" / "door_cutting_order_plan_controls_ux.js"
FAST_SAVE_UX = ROOT / "public" / "js" / "door_cutting_order" / "cutting_plan" / "door_cutting_order_fast_save_ux.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_order_uses_free_text_board_description_and_dimensions():
    payload = json.loads(DOCTYPE.read_text(encoding="utf-8"))
    fields = {field["fieldname"]: field for field in payload["fields"]}

    assert fields["board_description"]["fieldtype"] == "Data"
    assert fields["board_description"].get("reqd") == 1
    assert fields["board_length_cm"]["fieldtype"] == "Float"
    assert fields["board_width_cm"]["fieldtype"] == "Float"
    assert fields["board_length_cm"].get("default") is None
    assert fields["board_width_cm"].get("default") is None
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
    assert "frappe.model.set_value(targetDoc, updates)" in source
    assert "before_save(frm) { return syncInputs(frm); }" in source
    assert "syncInputs," in source


def test_board_text_ux_keeps_hidden_mm_snapshot_in_sync_without_new_order_defaults():
    source = _source(DEFAULTS_UX)
    assert "frm.doc.board_length_cm = 244" not in source
    assert "frm.doc.board_width_cm = 122" not in source
    assert "New orders intentionally start blank." in source
    assert "frm.doc.full_board_length_mm = length * 10" in source
    assert "frm.doc.full_board_width_mm = width * 10" in source


def test_board_form_labels_and_help_are_operator_friendly():
    source = _source(DEFAULTS_UX)
    assert "const label = __(message);" in source
    for message_id in (
        'board_description: "Board Item"',
        'board_length_cm: "Board length (cm)"',
        'board_width_cm: "Board width (cm)"',
    ):
        assert message_id in source
    assert '__("Write the type, thickness, and color in one line, for example: white MDF 18 mm.")' in source


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
    assert 'getattr(self.document, "board_length_cm", None)' in source
    assert 'getattr(self.document, "board_width_cm", None)' in source
    assert "default_if_missing" in source
    assert 'getattr(self.document, "board_length_cm", None) or 244' not in source
    assert 'getattr(self.document, "board_width_cm", None) or 122' not in source
    assert "self.document.full_board_length_mm = length_cm * 10" in source
    assert "self.document.full_board_width_mm = width_cm * 10" in source
    assert "self.document.board_item.item_name" not in source
    assert "frappe.get_doc(\"Item\", self.document.board_item)" not in source


def test_board_dimension_defaults_are_removed_from_all_active_input_adapters():
    access_source = _source(
        ROOT / "almdina_erp" / "infrastructure" / "frappe" / "orders" / "document_access.py"
    )
    adapter_source = _source(
        ROOT / "almdina_erp" / "infrastructure" / "frappe" / "orders" / "board_input_adapter.py"
    )
    assert "default_if_missing" not in adapter_source
    assert "self.access.board_dimensions()" in adapter_source
    assert "def board_dimensions(self) -> tuple[float, float]:" in access_source
    assert "piece_fits_board(" in access_source


def test_dimension_validation_is_live_localized_and_save_guarded():
    defaults_source = _source(DEFAULTS_UX)
    operator_source = _source(
        ROOT / "public" / "js" / "door_cutting_order" / "order_entry" / "door_cutting_order_operator_ux.js"
    )
    translations = _source(ROOT / "translations" / "ar.csv")
    for fragment in (
        "bindBoardDimensionInputs(frm)",
        "refreshBoardDimensionValidation(frm)",
        "Please enter board length and width first.",
    ):
        assert fragment in defaults_source
    for fragment in (
        "function pieceDimensionIssues(frm, row, values = {})",
        "refreshValidation: refreshDimensionValidation",
        "validateDimensionsBeforeSave(frm)",
        'if (length !== null && length > board.length) issues.length_cm = __("Exceeds length");',
        'if (width !== null && width > board.width) issues.width_cm = __("Exceeds width");',
        "entered axes independently. Rotation",
    ):
        assert fragment in operator_source
    assert "const rotated" not in operator_source
    assert "Piece dimensions exceed the board, even after allowed rotation." not in operator_source
    assert "يرجى إدخال طول وعرض اللوح أولاً." in translations
    assert "Exceeds board length,يتجاوز طول اللوح" in translations
    assert "Exceeds board width,يتجاوز عرض اللوح" in translations
    assert "Exceeds width,يتجاوز العرض" in translations
    assert "Exceeds length,يتجاوز الطول" in translations
    assert "Invalid dimension,قياس غير صالح" in translations


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
    board_source = _source(BOARD_UX)
    assert 'String(frm.doc.board_description || "")' in board_source
    assert "ألواح MDF — ${label}" in board_source
    assert "frm.doc.board_item" not in board_source
    assert "PRINT_TRIGGER_SELECTOR" not in board_source

    for path in (COST_UX, DOCUMENT_PRINT_PRESENTER):
        source = _source(path)
        assert "frm.doc.board_description" in source
        assert "frm.doc.board_description || frm.doc.board_item" not in source


def test_fast_save_and_plan_controls_use_free_text_board_validation():
    fast_save = _source(FAST_SAVE_UX)
    plan_controls = _source(PLAN_CONTROLS)
    board_ux = _source(BOARD_UX)
    assert "function canCalculatePlan(frm)" in board_ux
    for source in (fast_save, plan_controls):
        assert "const boardUX = window.AlmdinaBoardTextUX" in source
        assert "boardUX.canCalculatePlan(frm)" in source
        assert "!frm.doc.board_item" not in source
        assert "اختر اللوح وأدخل القياسات" not in source


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
