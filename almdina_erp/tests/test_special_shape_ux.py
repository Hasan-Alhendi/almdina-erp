from __future__ import annotations

import json
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
DETAIL_JSON = (
    APP_ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order_detail"
    / "door_cutting_order_detail.json"
)
ORDER_JSON = (
    APP_ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order"
    / "door_cutting_order.json"
)
SETTINGS_JSON = (
    APP_ROOT
    / "almdina_erp"
    / "doctype"
    / "almdina_erp_settings"
    / "almdina_erp_settings.json"
)
ORDER_PY = (
    APP_ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order"
    / "door_cutting_order.py"
)
ORDER_JS = (
    APP_ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order"
    / "door_cutting_order.js"
)
SERVICE_PY = APP_ROOT / "almdina_erp" / "services" / "special_shape_service.py"
OPERATOR_UX = APP_ROOT / "public" / "js" / "door_cutting_order_operator_ux.js"
SKETCH_UX = APP_ROOT / "public" / "js" / "door_cutting_order_special_shape_ux.js"
COST_UX = APP_ROOT / "public" / "js" / "door_cutting_order_cost_invoice_ux.js"
CUTTING_PLAN_SERVICE = APP_ROOT / "almdina_erp" / "services" / "cutting_plan_service.py"
REMNANT_PLANNING = APP_ROOT / "almdina_erp" / "services" / "remnant_planning.py"
CUTTING_PLAN_PIECE_JSON = (
    APP_ROOT
    / "almdina_erp"
    / "doctype"
    / "cutting_plan_piece"
    / "cutting_plan_piece.json"
)
HOOKS = APP_ROOT / "hooks.py"


def _fields(path: Path) -> dict[str, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {field["fieldname"]: field for field in payload["fields"]}


def test_special_piece_schema_keeps_documentation_and_accounting_price_separate():
    fields = _fields(DETAIL_JSON)
    assert fields["piece_type"]["options"] == "Regular\nSpecial"
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


def test_operator_editor_adds_special_type_and_paper_like_sketch_action():
    operator = OPERATOR_UX.read_text(encoding="utf-8")
    sketch = SKETCH_UX.read_text(encoding="utf-8")
    hooks = HOOKS.read_text(encoding="utf-8")

    assert 'data-field="piece_type"' in operator
    assert "dco-special-sketch-button" in operator
    assert "AlmdinaSpecialShapeEditor.open" in operator
    assert '"public/js/door_cutting_order_special_shape_ux.js"' in hooks

    for tool in ("pen", "line", "rectangle", "ellipse", "dimension", "note", "eraser"):
        assert f'key: "{tool}"' in sketch
    assert "pointerdown" in sketch
    assert "pointermove" in sketch
    assert "pointerup" in sketch
    assert "dco-sketch-undo" in sketch
    assert "dco-sketch-redo" in sketch
    assert "purpose: \"operator_documentation_only\"" in sketch


def test_sketch_is_documentation_while_selected_raw_edges_drive_preliminary_cost():
    service = SERVICE_PY.read_text(encoding="utf-8")
    order = ORDER_PY.read_text(encoding="utf-8")
    operator = OPERATOR_UX.read_text(encoding="utf-8")

    assert "validate_special_shape_drawing" in service
    assert "MAX_DRAWING_BYTES" in service
    assert "MAX_DRAWING_ELEMENTS" in service
    assert "MAX_DRAWING_POINTS" in service
    assert 'ALLOWED_DRAWING_TOOLS = {"pen", "line", "rectangle", "ellipse", "dimension", "note"}' in service

    assert "long_edges = cint(row.edge_long_right) + cint(row.edge_long_left)" in order
    assert "width_edges = cint(row.edge_width_top) + cint(row.edge_width_bottom)" in order
    assert '"edge_long_right": cint(row.edge_long_right)' in order
    assert '"edge_width_bottom": cint(row.edge_width_bottom)' in order
    assert "expand_piece_groups(piece_rows)" in order
    assert "special_shape_raw_summary" in order

    assert 'if ((row.piece_type || "Regular") === "Special") return 0' not in operator
    assert 'fieldname === "piece_type" && value === "Special"' not in operator
    assert "جهات القشاط مبدئية وتدخل مباشرة في التكلفة التقديرية" in operator


def test_accounting_approval_is_role_checked_audited_and_invalidated_by_geometry_changes():
    service = SERVICE_PY.read_text(encoding="utf-8")
    order = ORDER_PY.read_text(encoding="utf-8")
    cost = COST_UX.read_text(encoding="utf-8")

    assert 'SPECIAL_PRICE_APPROVER_ROLES = {"Accounts Management", "System Manager"}' in service
    assert "has_special_price_approval_role()" in service
    assert "special_shape_price_approved_by = frappe.session.user" in service
    assert "special_shape_price_approved_on = now_datetime()" in service
    assert "order.save(ignore_permissions=True)" in service
    assert "note: str | None = None" in service
    assert "Write a short pricing note before approving the custom price." not in service
    assert 'label: "ملاحظة التسعير (اختياري)"' in cost
    assert 'note: values.note || ""' in cost
    assert 'row.special_shape_price_status === "Approved"' in cost
    assert "? n(row.special_shape_custom_unit_price_usd)" in cost

    assert "row.special_shape_drawing_json" in order
    for fieldname in (
        "allow_rotation",
        "edge_long_right",
        "edge_long_left",
        "edge_width_top",
        "edge_width_bottom",
    ):
        assert f'"{fieldname}"' in order
    assert "old_row.edge_type" in order
    assert "row.edge_type" in order
    assert "default_edge_changed = bool(" in order
    assert "pricing_basis_changed = bool(" in order
    assert "math.isclose(" in order
    assert "cint(getattr(old_row, fieldname, 0))" in order
    assert "old_drawing != drawing" in order
    assert "if pricing_basis_changed and not approval_action" in order
    assert 'row.special_shape_price_status = (' in order
    assert 'row.special_shape_price_approved_by = ""' in order


def test_customer_quote_replaces_special_baseline_instead_of_mutating_internal_cost():
    order = ORDER_PY.read_text(encoding="utf-8")
    cost = COST_UX.read_text(encoding="utf-8")

    assert "regular_automatic_total = max(0.0, flt(self.total_cost_usd) - baseline_total)" in order
    assert "self.customer_quote_total_usd = round_value(regular_automatic_total + final_total, 3)" in order
    assert "self.total_cost_usd = round_value(total_cost, 3)" in order

    assert "استبعاد الحساب الآلي للدرف الخاصة" not in cost
    assert "حصة خام MDF للدرف العادية" in cost
    assert "حصة قص وتجهيز الدرف العادية" in cost
    assert "درفة خاصة رقم" in cost
    assert "سعر معتمد شامل" in cost
    assert "approve_special_piece_price" in cost
    assert "سعر شامل" in cost
    assert "التكلفة الداخلية المخططة" in cost
    assert "القشاط المبدئي" in cost
    assert "${qty(row.edge_meters)} م · $ ${money(row.edge_cost_usd)}" in cost
    assert "ملاحظة السعر:" in cost


def test_saved_special_price_and_read_only_sketch_survive_refresh():
    order = ORDER_PY.read_text(encoding="utf-8")
    cost = COST_UX.read_text(encoding="utf-8")
    sketch = SKETCH_UX.read_text(encoding="utf-8")

    assert "flt(old_row.width_cm)" in order
    assert "cint(old_row.qty) != cint(row.qty)" in order
    assert 'row.special_shape_price_status === "Approved"' in cost
    assert 'root.style.gridTemplateColumns = "minmax(0,1fr) 230px"' in sketch
    assert 'root.querySelector(".dco-special-sketch-shell").style.gridTemplateColumns' not in sketch


def test_review_and_production_approval_gate_special_documentation_and_price():
    order = ORDER_PY.read_text(encoding="utf-8")
    service = CUTTING_PLAN_SERVICE.read_text(encoding="utf-8")
    placed_piece_fields = _fields(CUTTING_PLAN_PIECE_JSON)

    assert "def ensure_special_shapes_documented" in order
    assert "def ensure_special_prices_approved" in order
    assert "order.ensure_special_shapes_documented()" in service
    assert "order.ensure_special_prices_approved()" in service
    assert placed_piece_fields["piece_type"]["options"] == "Regular\nSpecial"
    assert '"piece_type": piece.get("piece_type") or "Regular"' in service


def test_cutting_plan_visually_audits_every_special_raw_piece():
    order_js = ORDER_JS.read_text(encoding="utf-8")
    order_py = ORDER_PY.read_text(encoding="utf-8")
    remnant_planning = REMNANT_PLANNING.read_text(encoding="utf-8")

    assert "render_special_raw_coverage(frm, plan)" in order_js
    assert "dco-special-raw-piece" in order_js
    assert "✦ درفة خاصة · خام CNC" in order_js
    assert "قشاط مبدئي:" in order_js
    assert '"special_shape_raw_summary": self._special_shape_raw_summary(' in order_py
    assert '"complete": requested_ids.issubset(placed_ids) and not unplaced_ids' in order_py
    assert '"piece_type": row.piece_type or "Regular"' in remnant_planning
    assert '"special_shape_raw_summary": order._special_shape_raw_summary(' in remnant_planning
