from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "public" / "js" / "door_cutting_order_workflow.js"
PLAN_SERVICE = ROOT / "almdina_erp" / "services" / "cutting_plan_service.py"
SHOP_FLOOR = ROOT / "almdina_erp" / "services" / "shop_floor_service.py"
SHOP_FLOOR_UX = ROOT / "public" / "js" / "shop_floor_order_ux.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_order_creator_dispatches_without_locking_cutting_plan():
    workflow = _source(WORKFLOW)
    assert 'frm.add_custom_button(__("إرسال للإنتاج")' in workflow
    assert "open_dispatch_dialog" in workflow
    assert "approve_order" not in workflow
    assert "دون تثبيت خطة القص" in workflow
    assert "return_order_to_draft" in workflow
    assert "frappe.almdina.orderCanEdit" in workflow


def test_dispatch_accepts_draft_orders_with_calculated_plan_only():
    shop_floor = _source(SHOP_FLOOR)
    dispatch = shop_floor.split("def dispatch_order", 1)[1].split("@frappe.whitelist()", 1)[0]
    ready = shop_floor.split("def assert_order_ready_for_dispatch", 1)[1].split(
        "@frappe.whitelist()\ndef dispatch_order", 1
    )[0]
    assert "assert_order_ready_for_dispatch(order)" in dispatch
    assert 'order.status != "Approved"' not in dispatch
    assert "cutting_plan_json" in ready
    assert "plan_needs_recalculation" in ready


def test_drawing_worker_locks_plan_without_resetting_shop_floor_status():
    plan_service = _source(PLAN_SERVICE)
    lock_block = plan_service.split("def lock_cutting_plan", 1)[1].split(
        "def _lock_order_for_production", 1
    )[0]
    lock_impl = plan_service.split("def _lock_order_for_production", 1)[1].split(
        "@frappe.whitelist()\ndef reject_order", 1
    )[0]
    assert 'require_any_role("عامل رسم", "Production Manager")' in lock_block
    assert "preserve_status=True" in lock_block
    assert "if preserve_status:" in lock_impl
    assert '"status": "Approved"' in lock_impl


def test_drawing_form_exposes_lock_plan_action_for_drawing_path():
    ux = _source(SHOP_FLOOR_UX)
    assert "lock_cutting_plan" in ux
    assert 'frm.add_custom_button(__("اعتماد خطة النظام")' in ux
    assert 'plan_source: "System"' in ux
