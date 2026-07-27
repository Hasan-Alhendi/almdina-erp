from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
DOCTYPE = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
FAST_CONTROLLER = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order_fast.py"
SAVE_RENDER_UX = ROOT / "public" / "js" / "door_cutting_order_save_render_performance_ux.js"
HOOKS = ROOT / "hooks.py"


def _fast_source() -> str:
    return FAST_CONTROLLER.read_text(encoding="utf-8")


def test_plan_metadata_fingerprint_is_persisted_outside_large_json():
    doc = json.loads(DOCTYPE.read_text(encoding="utf-8"))
    fields = {field["fieldname"]: field for field in doc["fields"]}
    field = fields["calculated_plan_metadata_hash"]
    assert field["fieldtype"] == "Data"
    assert field["hidden"] == 1
    assert field["read_only"] == 1


def test_fast_controller_is_the_configured_doctype_override():
    hooks = HOOKS.read_text(encoding="utf-8")
    assert "override_doctype_class" in hooks
    assert '"Door Cutting Order"' in hooks
    assert "door_cutting_order_fast.FastDoorCuttingOrder" in hooks


def test_modern_plan_reuse_does_not_parse_the_plan_json():
    source = _fast_source()
    block = source.split("def _can_reuse_current_plan", 1)[1].split(
        "def _refresh_costs_from_stored_summary", 1
    )[0]
    assert "self.calculated_plan_input_hash" in block
    assert "return str(self.calculated_plan_input_hash) == input_fingerprint" in block
    assert "_parse_plan_snapshot" not in block


def test_unchanged_metadata_skips_plan_parse_expand_and_reserialize():
    source = _fast_source()
    block = source.split("def _refresh_current_plan_without_optimization", 1)[1].split(
        "def _calculate_cutting_plan", 1
    )[0]
    fast_path = block.split("snapshot = self._parse_plan_snapshot()", 1)[0]
    assert "calculated_plan_metadata_hash" in fast_path
    assert "_refresh_costs_from_stored_summary(settings)" in fast_path
    assert "frappe.as_json" not in fast_path
    assert "_sync_snapshot_piece_metadata" not in fast_path


def test_unchanged_drawings_are_not_revalidated_point_by_point():
    source = _fast_source()
    block = source.split("def _validate_special_shape_rows", 1)[1].split(
        "def _plan_input_payload", 1
    )[0]
    assert "if current_raw and drawing_changed" in block
    assert "validate_special_shape_drawing(current_raw)" in block
    assert "elif current_raw" in block
    assert "old_row.special_shape_status == \"Documented\"" in block


def test_old_order_data_is_loaded_with_targeted_queries_not_whole_doc():
    source = _fast_source()
    immutability = source.split("def _enforce_approved_immutability", 1)[1].split(
        "def _drawing_token", 1
    )[0]
    assert "self._old_header()" in immutability
    assert "get_doc_before_save" not in immutability
    assert 'frappe.db.get_value(' in source
    assert 'frappe.get_all(' in source


def test_clipped_corner_geometry_is_part_of_layout_fingerprint():
    source = _fast_source()
    block = source.split("def _plan_input_payload", 1)[1].split(
        "def _plan_metadata_payload", 1
    )[0]
    assert '"piece_type"' in block
    assert '"clipped_corner_position"' in block
    assert '"clipped_corner_width_cm"' in block
    assert '"clipped_corner_length_cm"' in block


def test_post_save_dom_layer_reuses_unchanged_measurement_table():
    source = SAVE_RENDER_UX.read_text(encoding="utf-8")
    assert "sameRows(frm, root)" in source
    assert "syncExistingTable(frm, root)" in source
    assert "return originalHtml.apply(this, arguments)" in source
    assert "dco-fast-entry-shell" in source
    assert 'window.AlmdinaOrderCostUX.render(frm)' in source


def test_post_save_dom_layer_loads_after_table_and_invoice_renderers():
    hooks = HOOKS.read_text(encoding="utf-8")
    operator = '"public/js/door_cutting_order_operator_ux.js"'
    table = '"public/js/door_cutting_order_table_performance_ux.js"'
    invoice = '"public/js/door_cutting_order_cost_invoice_ux.js"'
    performance = '"public/js/door_cutting_order_save_render_performance_ux.js"'
    assert hooks.index(operator) < hooks.index(performance)
    assert hooks.index(table) < hooks.index(performance)
    assert hooks.index(invoice) < hooks.index(performance)
