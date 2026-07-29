from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHOP_FLOOR = ROOT / "almdina_erp" / "services" / "shop_floor_service.py"
DRAWING_UX = ROOT / "public" / "js" / "door_cutting_order_drawing_plan_ux.js"
SHOP_FLOOR_UX = ROOT / "public" / "js" / "shop_floor_order_ux.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_recalculate_drawing_plan_api_exists_for_drawing_role():
    src = _source(SHOP_FLOOR)
    block = src.split("def recalculate_drawing_plan", 1)[1].split("@frappe.whitelist()", 1)[0]
    assert 'require_any_role("عامل رسم", "Production Manager", "System Manager")' in block
    assert "_assert_order_at_drawing(order_name)" in block
    assert "force_cutting_plan_recalculation" in block
    assert "_serialize_order_preview" in block


def test_drawing_recalc_uses_shared_immutability_bypass():
    policy = _source(ROOT / "almdina_erp" / "services" / "order_edit_policy.py")
    assert "is_order_at_drawing_stage" in policy
    assert "DRAWING_OPERATOR_ROLES" in policy


def test_drawing_optimizer_ui_calls_recalculate_api():
    src = _source(DRAWING_UX)
    assert "recalculate_drawing_plan" in src
    assert "canUseDrawingOptimizer" in src
    assert "renderInboxPanel" in src
    assert "محرك خطة الرسم" in src
    assert "Auto Pro" in src


def test_drawing_form_exposes_dual_approval_and_print_actions():
    ux = _source(SHOP_FLOOR_UX)
    assert "اعتماد خطة النظام" in ux
    assert "اعتماد الخطة المرفوعة" in ux
    assert "طباعة خطة القص" in ux
    assert 'plan_source: "System"' in ux
    assert 'plan_source: "Custom"' in ux
