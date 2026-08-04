from pathlib import Path
import json

from almdina_erp.almdina_erp.application.orders.plan_payloads import (
    PlanBoardInput,
    PlanCutInput,
    PlanOptimizerSettings,
    PlanPieceInput,
    build_plan_input_payload,
)


ROOT = Path(__file__).resolve().parents[1]
DOCTYPE = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
FAST_CONTROLLER = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order_fast.py"
ACTIVE_CONTROLLER = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order_controller.py"
DOCUMENT_ACCESS = ROOT / "almdina_erp" / "infrastructure" / "frappe" / "orders" / "document_access.py"
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


def test_active_controller_preserves_fast_save_and_free_text_board_contracts():
    hooks = HOOKS.read_text(encoding="utf-8")
    controller = ACTIVE_CONTROLLER.read_text(encoding="utf-8")
    access = DOCUMENT_ACCESS.read_text(encoding="utf-8")

    assert "override_doctype_class" in hooks
    assert '"Door Cutting Order"' in hooks
    assert "door_cutting_order_controller.DoorCuttingOrderController" in hooks
    assert "class DoorCuttingOrderController(DoorCuttingOrder)" in controller
    assert "process_order_save(self._gateway())" in controller
    assert "class FrappeOrderDocumentAccess" in access
    assert 'getattr(self.document, "board_description", "")' in access
    assert "self.document.full_board_length_mm = length_cm * 10" in access
    assert "self.document.full_board_width_mm = width_cm * 10" in access


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
    assert 'old_row.special_shape_status == "Documented"' in block


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
    payload = build_plan_input_payload(
        version=1,
        board=PlanBoardInput(item="MDF أبيض 18 مم", width_mm=1220, length_mm=2440),
        cut=PlanCutInput(
            kerf_mm=3,
            trim_margin_mm=5,
            packing_mode="Auto Pro",
            machine_type="Auto",
            time_limit_sec=10,
        ),
        optimizer=PlanOptimizerSettings(
            exact_piece_limit=40,
            min_remnant_width_mm=0,
            min_remnant_length_mm=0,
            min_remnant_area_m2=0,
        ),
        pieces=[
            PlanPieceInput(
                index=1,
                width_cm=60,
                length_cm=80,
                qty=1,
                allow_rotation=1,
                piece_type="Clipped Corner",
                clipped_corner_position="Top Right",
                clipped_corner_width_cm=12,
                clipped_corner_length_cm=18,
            )
        ],
    )
    piece = payload["pieces"][0]
    assert piece["piece_type"] == "Clipped Corner"
    assert piece["clipped_corner_position"] == "Top Right"
    assert piece["clipped_corner_width_cm"] == 12
    assert piece["clipped_corner_length_cm"] == 18


def test_post_save_dom_layer_reuses_unchanged_measurement_table():
    source = SAVE_RENDER_UX.read_text(encoding="utf-8")
    assert "sameRows(frm, root)" in source
    assert "syncExistingTable(frm, root)" in source
    assert "return originalHtml.apply(this, arguments)" in source
    assert "dco-fast-entry-shell" in source
    assert "wrapper._dcoFastHtmlGuardForm = frm" in source
    assert "root._dcoDeferredRenderForm = frm" in source
    assert 'window.AlmdinaOrderCostUX.render(currentFrm)' in source
    # Edit-session unlock must replace HTML; value-only sync leaves disabled inputs.
    assert "htmlLooksEditable(value) !== currentShellEditable(root)" in source
    assert "_dcoForceHtmlReplace" in source
    assert "dco-fast-readonly-note" in source


def test_post_save_dom_layer_loads_after_table_and_invoice_renderers():
    hooks = HOOKS.read_text(encoding="utf-8")
    operator = '"public/js/door_cutting_order_operator_ux.js"'
    table = '"public/js/door_cutting_order_table_performance_ux.js"'
    invoice = '"public/js/door_cutting_order_cost_invoice_ux.js"'
    performance = '"public/js/door_cutting_order_save_render_performance_ux.js"'
    assert hooks.index(operator) < hooks.index(performance)
    assert hooks.index(table) < hooks.index(performance)
    assert hooks.index(invoice) < hooks.index(performance)
