from __future__ import annotations

import json
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
DETAIL_JSON = APP_ROOT / "almdina_erp" / "doctype" / "door_cutting_order_detail" / "door_cutting_order_detail.json"
ORDER_JSON = APP_ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
SETTINGS_JSON = APP_ROOT / "almdina_erp" / "doctype" / "almdina_erp_settings" / "almdina_erp_settings.json"
ORDER_PY = APP_ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.py"
PIECE_POLICY = APP_ROOT / "almdina_erp" / "infrastructure" / "frappe" / "orders" / "piece_policy_adapter.py"
COSTING_ADAPTER = APP_ROOT / "almdina_erp" / "infrastructure" / "frappe" / "orders" / "costing_adapter.py"
COSTING_DOMAIN = APP_ROOT / "almdina_erp" / "domain" / "orders" / "costing.py"
OPTIMIZE_APPLICATION = APP_ROOT / "almdina_erp" / "application" / "cutting" / "optimize_order_plan.py"
PLAN_RENDERER = APP_ROOT / "public" / "js" / "door_cutting_order" / "cutting_plan" / "door_cutting_order_cutting_plan_renderer.js"
SERVICE_PY = APP_ROOT / "almdina_erp" / "services" / "special_shape_service.py"
OPERATOR_UX = (
    APP_ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "door_cutting_order_operator_ux.js"
)
EDITOR_ENTRY = APP_ROOT / "public" / "js" / "door_cutting_order" / "drawing" / "special_shape_facade.js"
V4_SHELL = APP_ROOT / "public" / "js" / "door_drawing_v4" / "presentation" / "editor_shell.js"
V4_CONTROLLER = APP_ROOT / "public" / "js" / "door_drawing_v4" / "presentation" / "editor_controller.js"
V4_INTERACTION = APP_ROOT / "public" / "js" / "door_drawing_v4" / "application" / "interaction_engine.js"
V4_GEOMETRY = APP_ROOT / "public" / "js" / "door_drawing_v4" / "domain" / "geometry.js"
V4_CSS = APP_ROOT / "public" / "css" / "door_drawing_v4.css"
COST_PRESENTER = APP_ROOT / "public" / "js" / "door_cutting_order" / "costing" / "door_cutting_order_cost_presenter.js"
COST_PERMISSIONS = APP_ROOT / "public" / "js" / "door_cutting_order" / "costing" / "door_cutting_order_cost_permissions_ux.js"
CUTTING_PLAN_SERVICE = APP_ROOT / "almdina_erp" / "services" / "cutting_plan_snapshot_service.py"
REMNANT_PLANNING = APP_ROOT / "almdina_erp" / "services" / "remnant_planning.py"
CUTTING_PLAN_PIECE_JSON = APP_ROOT / "almdina_erp" / "doctype" / "cutting_plan_piece" / "cutting_plan_piece.json"
HOOKS = APP_ROOT / "frontend_assets.py"


def _fields(path: Path) -> dict[str, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {field["fieldname"]: field for field in payload["fields"]}


def test_special_piece_schema_keeps_documentation_and_accounting_price_separate():
    fields = _fields(DETAIL_JSON)
    assert fields["piece_type"]["options"] == "Regular\nClipped Corner\nSpecial"
    assert fields["special_shape_drawing_json"]["fieldtype"] == "Long Text"
    assert fields["special_shape_status"]["read_only"] == 1
    for fieldname in (
        "special_shape_estimated_unit_price_usd",
        "special_shape_custom_unit_price_usd",
        "special_shape_final_unit_price_usd",
        "special_shape_price_status",
        "special_shape_price_note",
        "special_shape_price_approved_by",
        "special_shape_price_approved_on",
    ):
        assert fields[fieldname]["permlevel"] == 1
        assert fields[fieldname]["read_only"] == 1


def test_order_schema_has_customer_quote_separate_from_internal_planned_cost():
    fields = _fields(ORDER_JSON)
    assert fields["total_cost_usd"]["label"] == "Planned Total Cost USD"
    assert fields["customer_quote_total_usd"]["label"] == "Customer Quote Total USD"
    assert "Estimated" in fields["customer_quote_status"]["options"]
    assert "Approved" in fields["customer_quote_status"]["options"]


def test_special_estimate_defaults_are_configurable_and_start_at_zero():
    fields = _fields(SETTINGS_JSON)
    for fieldname in (
        "default_special_design_fee_usd",
        "default_special_cnc_fee_usd",
        "default_special_manual_edge_fee_usd",
        "default_special_margin_percent",
    ):
        assert fields[fieldname]["default"] == "0"
        assert fields[fieldname]["non_negative"] == 1


def test_operator_opens_only_clean_v4_editor_runtime():
    operator = OPERATOR_UX.read_text(encoding="utf-8")
    entry = EDITOR_ENTRY.read_text(encoding="utf-8")
    shell = V4_SHELL.read_text(encoding="utf-8")
    controller = V4_CONTROLLER.read_text(encoding="utf-8")
    interaction = V4_INTERACTION.read_text(encoding="utf-8")
    geometry = V4_GEOMETRY.read_text(encoding="utf-8")
    css = V4_CSS.read_text(encoding="utf-8")
    hooks = HOOKS.read_text(encoding="utf-8")

    assert 'data-field="piece_type"' in operator
    assert "dco-special-sketch-button" in operator
    assert "AlmdinaSpecialShapeEditor.open" in operator
    assert '"public/js/door_cutting_order/drawing/special_shape_facade.js"' in hooks
    assert "__doorDrawingV4: true" in entry
    assert "__canonicalMmGeometry: true" in entry
    assert "door_drawing_v4/domain/geometry.js" in entry
    assert "door_drawing_v4/presentation/editor_shell.js" in entry
    assert "door_drawing_v4/presentation/editor_controller.js" in entry
    assert "AlmdinaSketchEngine" not in entry
    for tool in ("select", "node", "pen", "dimension", "hand"):
        assert f'toolButton("{tool}"' in shell
    assert 'inputmode="decimal"' in shell
    assert 'aria-label="القيمة بالميليمتر"' in shell
    assert 'placeholder="القيمة mm"' in shell
    assert "function worldPoint(" in controller
    assert "screenToleranceToMm" in controller
    assert "engine.inputLength(lengthMm)" in controller
    assert "engine.inputDimensionValue(valueMm)" in controller
    assert "engine.undo()" in controller
    assert "engine.redo()" in controller
    assert "function beginNodeDrag(" in interaction
    assert "function finishNodeDrag(" in interaction
    assert 'const EPSILON_MM = 0.001' in geometry
    assert ".ald-v4-editor-host" in css
    assert ".ald-v4-dialog-actions" in css
    for retired in (
        "door_cutting_order_sketch_engine.js",
        "door_cutting_order_exact_line_ux.js",
        "door_cutting_order_figma_editor_ux.js",
        "door_cutting_order_drawing_workspace_ux.js",
    ):
        assert retired not in hooks


def test_drawing_validation_and_preliminary_edge_cost_policy_remain_server_authoritative():
    service = SERVICE_PY.read_text(encoding="utf-8")
    policy = PIECE_POLICY.read_text(encoding="utf-8")
    costing = COSTING_DOMAIN.read_text(encoding="utf-8")
    adapter = COSTING_ADAPTER.read_text(encoding="utf-8")
    operator = OPERATOR_UX.read_text(encoding="utf-8")
    assert "validate_special_shape_drawing" in service
    assert "MAX_DRAWING_BYTES" in service
    assert "MAX_DRAWING_ELEMENTS" in service
    assert "MAX_DRAWING_POINTS" in service
    assert 'ALLOWED_DRAWING_TOOLS = {"pen", "line", "rectangle", "ellipse", "dimension", "note"}' in service
    assert "validate_special_shape_drawing(current_raw)" in policy
    assert '"long_right": (' in costing
    assert "bool(piece.edge_long_right)" in costing
    assert '"width_top": (' in costing
    assert "bool(piece.edge_width_top)" in costing
    assert "long_meters = right_meters + left_meters" in costing
    assert "width_meters = top_meters + bottom_meters" in costing
    assert "summary = calculate_piece_costs(" in adapter
    assert 'if ((row.piece_type || "Regular") === "Special") return 0' not in operator


def test_price_approval_is_capability_checked_audited_and_invalidated_by_geometry_changes():
    service = SERVICE_PY.read_text(encoding="utf-8")
    policy = PIECE_POLICY.read_text(encoding="utf-8")
    permissions = COST_PERMISSIONS.read_text(encoding="utf-8")

    assert "SPECIAL_PRICE_APPROVAL_CAPABILITIES" in service
    assert "doctype_has_any_capability" in service
    assert "SPECIAL_PRICE_APPROVER_ROLES" not in service
    assert "special_shape_price_approved_by = frappe.session.user" in service
    assert "special_shape_price_approved_on = now_datetime()" in service
    assert "order.save(ignore_permissions=True)" in service

    assert "function canEditInlinePiecePrice(frm, piece)" in permissions
    assert '"approve_special_price"' in permissions
    assert "function applyInlinePriceToPiece(piece, kind, rawValue)" in permissions
    assert "function flushPendingPriceEdits(frm)" in permissions
    assert "special_shape_service.approve_special_piece_price" in permissions
    assert 'note: piece.special_shape_price_note || ""' in permissions

    assert "old_special_geometry != special_geometry" in policy
    assert "decision = evaluate_special_shape(" in policy
    assert "if decision.reset_price:" in policy
    assert "document_has_capability(" in policy


def test_customer_quote_uses_full_board_and_cutting_costs_with_special_price():
    costing = COSTING_DOMAIN.read_text(encoding="utf-8")
    adapter = COSTING_ADAPTER.read_text(encoding="utf-8")
    presenter = COST_PRESENTER.read_text(encoding="utf-8")
    permissions = COST_PERMISSIONS.read_text(encoding="utf-8")

    assert "invoice_base_total = board_and_cutting_cost + regular_edge_total" in costing
    assert "customer_quote_total_usd=round_value(invoice_base_total + final_total, 3)" in costing
    assert "total_cost_usd=round_value(mdf_cost + cutting_cost + edge_cost, 3)" in costing
    assert "self.document.customer_quote_total_usd = (" in adapter
    assert "self.document.total_cost_usd = summary.total_cost_usd" in adapter
    assert "boardCount * boardRate" in presenter
    assert "boardCount * cuttingRate" in presenter
    assert "function quoteTotal(frm)" in presenter
    assert "special_shape_service.approve_special_piece_price" in permissions
    assert "frm.doc.customer_quote_total_usd = costUx.quoteTotal(frm)" in permissions


def test_review_and_production_approval_gate_special_documentation_and_price():
    order = ORDER_PY.read_text(encoding="utf-8")
    service = CUTTING_PLAN_SERVICE.read_text(encoding="utf-8")
    placed_piece_fields = _fields(CUTTING_PLAN_PIECE_JSON)
    assert "def ensure_special_shapes_documented" in order
    assert "def ensure_special_prices_approved" in order
    assert "order.ensure_special_shapes_documented()" in service
    assert "order.ensure_special_prices_approved()" in service
    assert placed_piece_fields["piece_type"]["options"] == "Regular\nClipped Corner\nSpecial"
    assert '"piece_type": piece.get("piece_type") or "Regular"' in service


def test_cutting_plan_visually_audits_every_special_raw_piece():
    order_js = PLAN_RENDERER.read_text(encoding="utf-8")
    optimization = OPTIMIZE_APPLICATION.read_text(encoding="utf-8")
    remnant_planning = REMNANT_PLANNING.read_text(encoding="utf-8")
    assert "render_special_raw_coverage(frm, plan)" in order_js
    assert "dco-special-raw-piece" in order_js
    assert "✦ درفة خاصة · خام CNC" in order_js
    assert "render_piece_edge_lines(piece)" in order_js
    assert '"special_shape_raw_summary": summarize_special_shapes(expanded, plan)' in optimization
    assert '"piece_type": row.piece_type or "Regular"' in remnant_planning
