from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "almdina_erp" / "services" / "order_edit_policy.py"
ORDER_PY = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.py"
FAST_PY = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order_fast.py"
SHOP_FLOOR = ROOT / "almdina_erp" / "services" / "shop_floor_service.py"
SHOP_FLOOR_QUERIES = ROOT / "almdina_erp" / "application" / "shop_floor" / "queries.py"
WORKFLOW = ROOT / "public" / "js" / "door_cutting_order_workflow.js"
SHOP_FLOOR_UX = ROOT / "public" / "js" / "shop_floor_order_ux.js"
OPERATOR = ROOT / "public" / "js" / "door_cutting_order_operator_ux.js"
PLAN_UX = ROOT / "public" / "js" / "door_cutting_order_plan_ux.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_order_entry_can_edit_after_dispatch_via_shared_policy():
    policy = _source(POLICY)
    assert "Capability.RECALCULATE_PLAN" in policy
    assert "frappe.get_roles" not in policy
    assert "LOCKED_ORDER_STATUSES" in policy
    assert "def user_can_edit_order" in policy
    assert "def user_can_recalculate_drawing_system_plan" in policy
    assert "def enforce_order_immutability_on_save" in policy
    assert "enforce_order_immutability_on_save" in _source(ORDER_PY)
    assert "enforce_order_immutability_on_save" in _source(FAST_PY)
    assert "assert_order_editable(doc)" in _source(ORDER_PY)


def test_drawing_operator_plan_recalc_bypasses_production_immutability():
    policy = _source(POLICY)
    block = policy.split("def enforce_order_immutability_on_save", 1)[1].split("def unlock_frozen_plan_for_editor", 1)[0]
    assert "force_cutting_plan_recalculation" in block
    assert "user_can_recalculate_drawing_system_plan" in block
    fast = _source(FAST_PY)
    assert "assert_order_editable(old)" not in fast


def test_client_editable_checks_use_shared_order_can_edit_helper():
    workflow = _source(WORKFLOW)
    assert "frappe.almdina.orderCanEdit = order_can_edit" in workflow
    assert "is_order_editor()" in workflow
    assert 'frm.add_custom_button(__("إعادة للمسودة")' in workflow
    assert "return_order_to_draft" in workflow
    assert "frappe.almdina.orderCanEdit" in _source(OPERATOR)
    assert "frappe.almdina.orderCanEdit" in _source(PLAN_UX)


def test_revert_targets_expose_stage_labels_not_ids_in_ui():
    shop_floor = _source(SHOP_FLOOR)
    queries = _source(SHOP_FLOOR_QUERIES)
    ux = _source(SHOP_FLOOR_UX)
    inbox = _source(ROOT / "almdina_erp" / "page" / "shop_floor_inbox" / "shop_floor_inbox.js")
    assert '"label": _value(row, "department_label")' in queries
    assert "return_order_to_draft" in shop_floor
    assert "revert_department" in shop_floor
    assert "row.label" in ux
    assert 'options: rows.map((row) => `${row.name}`)' not in ux
    assert "def _filter_active_stages" in queries
    assert "def _active_stage_snapshot" in queries
    assert "can_start_stage" in queries
    assert "can_handoff_stage" in queries
    assert "detail.can_start_stage" in inbox
    assert "detail.can_handoff_stage" in inbox
    assert "get_current_stage_context" in ux
    assert 'frappe.db.get_value("Production Stage"' not in ux
