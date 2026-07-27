import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCTYPE = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
DEFAULTS = ROOT / "public" / "js" / "door_cutting_order_defaults.js"
BOARD_UX = ROOT / "public" / "js" / "door_cutting_order_board_text_ux.js"
CONTROLLER = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order_text_board.py"
REMNANT_PLANNING = ROOT / "almdina_erp" / "services" / "remnant_planning.py"
STOCK_SERVICE = ROOT / "almdina_erp" / "services" / "stock_service.py"
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


def test_stock_service_skips_unmapped_board_stock_but_keeps_edge_stock():
    source = _source(STOCK_SERVICE)
    assert 'board_item = str(getattr(order, "board_item", "") or "").strip()' in source
    assert "if full_board_count and board_item:" in source
    assert "if not materials:" in source
    assert '"no_stock_linked_materials": True' in source
    assert 'frappe.db.get_value(\n            "Edge Banding Type"' in source
    assert "order.board_material" not in source
    assert "order.board_color" not in source
    assert "order.board_thickness_mm" not in source


def test_invoice_and_measurement_prints_use_only_board_description_as_visible_label():
    source = _source(BOARD_UX)
    assert 'String(frm.doc.board_description || "")' in source
    assert "frm.doc.board_description || frm.doc.board_item" not in source
    assert "ألواح MDF — ${label}" in source
    assert "PRINT_TRIGGER_SELECTOR" in source


def test_fast_save_and_plan_controls_use_free_text_board_validation():
    fast_save = _source(ROOT / "public" / "js" / "door_cutting_order_fast_save_ux.js")
    plan_ux = _source(ROOT / "public" / "js" / "door_cutting_order_plan_ux.js")
    board_ux = _source(BOARD_UX)
    assert "function canCalculatePlan(frm)" in board_ux
    assert "AlmdinaBoardTextUX.canCalculatePlan" in fast_save
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
    assert "board_material" not in preview_block
    assert "board_color" not in preview_block
    assert "board_thickness_mm" not in preview_block
    assert "def _board_ready_for_plan" in source
    assert "preview.board_item and has_complete_piece" not in source


def test_free_text_board_layers_are_loaded_after_invoice_renderers():
    hooks = _source(HOOKS)
    invoice = '"public/js/door_cutting_order_cost_invoice_ux.js"'
    edge_color = '"public/js/door_cutting_order_edge_color_ux.js"'
    board_text = '"public/js/door_cutting_order_board_text_ux.js"'
    assert hooks.index(invoice) < hooks.index(edge_color) < hooks.index(board_text)
    assert "door_cutting_order_text_board.TextBoardDoorCuttingOrder" in hooks


def test_cutting_plan_uses_safe_board_identity_helpers():
    cutting_plan = _source(ROOT / "almdina_erp" / "doctype" / "cutting_plan" / "cutting_plan.py")
    identity = _source(ROOT / "almdina_erp" / "services" / "order_board_identity.py")
    assert "order_board_material" in identity
    assert "order_board_color" in identity
    assert "order_board_thickness_mm" in identity
    assert "order.board_material" not in cutting_plan
    assert "order.board_color" not in cutting_plan
    assert "order.board_thickness_mm" not in cutting_plan
    assert "order_board_material(order)" in cutting_plan
