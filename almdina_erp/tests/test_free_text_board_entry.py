import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCTYPE = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
DEFAULTS = ROOT / "public" / "js" / "door_cutting_order_defaults.js"
BOARD_UX = ROOT / "public" / "js" / "door_cutting_order_board_text_ux.js"
CONTROLLER = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order_text_board.py"
REMNANT_PLANNING = ROOT / "almdina_erp" / "services" / "remnant_planning.py"
DROP_PATCH = ROOT / "patches" / "v1_0" / "drop_obsolete_order_board_columns.py"
PATCHES_TXT = ROOT / "patches.txt"
HOOKS = ROOT / "hooks.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_order_uses_required_free_text_board_description_instead_of_item_picker():
    doc = json.loads(_source(DOCTYPE))
    fields = {row["fieldname"]: row for row in doc["fields"]}
    assert fields["board_description"]["fieldtype"] == "Data"
    assert fields["board_description"]["reqd"] == 1
    assert fields["board_description"]["label"] == "Board Item"
    assert fields["board_item"]["fieldtype"] == "Link"
    assert fields["board_item"]["hidden"] == 1
    assert not fields["board_item"].get("reqd")
    assert "board_summary_html" not in fields


def test_board_length_and_width_are_visible_cm_fields_with_requested_defaults():
    doc = json.loads(_source(DOCTYPE))
    fields = {row["fieldname"]: row for row in doc["fields"]}
    assert fields["board_length_cm"]["fieldtype"] == "Float"
    assert fields["board_length_cm"]["default"] == "244"
    assert fields["board_length_cm"]["reqd"] == 1
    assert fields["board_width_cm"]["fieldtype"] == "Float"
    assert fields["board_width_cm"]["default"] == "122"
    assert fields["board_width_cm"]["reqd"] == 1


def test_obsolete_board_snapshot_fields_are_deleted_not_merely_hidden():
    doc = json.loads(_source(DOCTYPE))
    fields = {row["fieldname"]: row for row in doc["fields"]}
    for obsolete in ("board_material", "board_color", "board_thickness_mm"):
        assert obsolete not in fields
        assert obsolete not in doc["field_order"]


def test_database_cleanup_patch_drops_retired_columns_idempotently():
    source = _source(DROP_PATCH)
    for obsolete in ("board_material", "board_color", "board_thickness_mm"):
        assert f'"{obsolete}"' in source
    assert 'doctype = "Door Cutting Order"' in source
    assert "frappe.db.table_exists(doctype)" in source
    assert "frappe.db.has_column(doctype, column)" in source
    assert 'drop column `{column}`' in source
    assert "almdina_erp.patches.v1_0.drop_obsolete_order_board_columns" in _source(PATCHES_TXT)


def test_client_defaults_do_not_query_item_master_or_read_legacy_snapshot_fields():
    source = _source(DEFAULTS)
    assert "get_board_defaults" not in source
    assert "apply_board_defaults" not in source
    assert "board_material" not in source
    assert "board_color" not in source
    assert "board_thickness_mm" not in source
    assert "frm.doc.board_item" not in source
    assert "frm.doc.full_board_length_mm || 0" not in source
    assert "frm.doc.full_board_width_mm || 0" not in source
    assert "board_description: \"صنف اللوح\"" in source
    assert "board_length_cm: \"طول اللوح (سم)\"" in source
    assert "board_width_cm: \"عرض اللوح (سم)\"" in source
    assert "frm.doc.full_board_length_mm = length * 10" in source
    assert "frm.doc.full_board_width_mm = width * 10" in source


def test_server_controller_validates_only_new_board_inputs_and_converts_for_optimizer():
    source = _source(CONTROLLER)
    assert "class TextBoardDoorCuttingOrder(FastDoorCuttingOrder)" in source
    assert 'description = str(getattr(self, "board_description", "")' in source
    assert "self.full_board_length_mm = length_cm * 10" in source
    assert "self.full_board_width_mm = width_cm * 10" in source
    assert "legacy_item" not in source
    assert "board_material" not in source
    assert "board_color" not in source
    assert "board_thickness_mm" not in source
    assert "frappe.db.get_value(" not in source
    assert 'payload["board"]["description"]' in source


def test_remnant_planning_uses_only_optional_stock_item_identity():
    source = _source(REMNANT_PLANNING)
    assert "def _stock_board_item(order" in source
    assert "if not board_item:" in source
    assert "if stock_board_item and cint(settings.prefer_remnants_before_full_boards):" in source
    assert "order.board_material" not in source
    assert "order.board_color" not in source
    assert "order.board_thickness_mm" not in source
    assert 'full_sheet["board_description"] = board_description' in source


def test_invoice_and_measurement_prints_use_only_board_description_as_visible_label():
    source = _source(BOARD_UX)
    assert 'String(frm.doc.board_description || "")' in source
    assert "frm.doc.board_description || frm.doc.board_item" not in source
    assert "ألواح MDF — ${label}" in source
    assert "PRINT_TRIGGER_SELECTOR" in source


def test_free_text_board_layers_are_loaded_after_invoice_renderers():
    hooks = _source(HOOKS)
    invoice = '"public/js/door_cutting_order_cost_invoice_ux.js"'
    edge_color = '"public/js/door_cutting_order_edge_color_ux.js"'
    board_text = '"public/js/door_cutting_order_board_text_ux.js"'
    assert hooks.index(invoice) < hooks.index(edge_color) < hooks.index(board_text)
    assert "door_cutting_order_text_board.TextBoardDoorCuttingOrder" in hooks
