import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCTYPE = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
DEFAULTS = ROOT / "public" / "js" / "door_cutting_order_defaults.js"
BOARD_UX = ROOT / "public" / "js" / "door_cutting_order_board_text_ux.js"
CONTROLLER = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order_text_board.py"
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
    for obsolete in ("board_material", "board_color", "board_thickness_mm"):
        assert fields[obsolete]["hidden"] == 1
        assert obsolete not in doc["field_order"][: doc["field_order"].index("cost_tab")]


def test_client_defaults_do_not_query_item_master_and_sync_cm_to_mm():
    source = _source(DEFAULTS)
    assert "get_board_defaults" not in source
    assert "apply_board_defaults" not in source
    assert "board_description: \"صنف اللوح\"" in source
    assert "board_length_cm: \"طول اللوح (سم)\"" in source
    assert "board_width_cm: \"عرض اللوح (سم)\"" in source
    assert "frm.doc.full_board_length_mm = length * 10" in source
    assert "frm.doc.full_board_width_mm = width * 10" in source


def test_server_controller_validates_text_and_converts_centimeters_for_optimizer():
    source = _source(CONTROLLER)
    assert "class TextBoardDoorCuttingOrder(FastDoorCuttingOrder)" in source
    assert 'description = str(getattr(self, "board_description", "")' in source
    assert "self.full_board_length_mm = length_cm * 10" in source
    assert "self.full_board_width_mm = width_cm * 10" in source
    assert "frappe.db.get_value(" not in source
    assert 'payload["board"]["description"]' in source


def test_invoice_and_measurement_prints_use_board_description_without_saving_it_as_link():
    source = _source(BOARD_UX)
    assert "frm.doc.board_description || frm.doc.board_item" in source
    assert "ألواح MDF — ${label}" in source
    assert "PRINT_TRIGGER_SELECTOR" in source
    assert "frm.doc.board_item = description" in source
    assert "frm.doc.board_item = previous" in source


def test_free_text_board_layers_are_loaded_after_invoice_renderers():
    hooks = _source(HOOKS)
    invoice = '"public/js/door_cutting_order_cost_invoice_ux.js"'
    edge_color = '"public/js/door_cutting_order_edge_color_ux.js"'
    board_text = '"public/js/door_cutting_order_board_text_ux.js"'
    assert hooks.index(invoice) < hooks.index(edge_color) < hooks.index(board_text)
    assert "door_cutting_order_text_board.TextBoardDoorCuttingOrder" in hooks
