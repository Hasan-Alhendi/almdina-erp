from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHOP_FLOOR = ROOT / "almdina_erp" / "services" / "shop_floor_service.py"
DRAWING_UX = ROOT / "public" / "js" / "door_cutting_order_drawing_plan_ux.js"
SHOP_FLOOR_UX = ROOT / "public" / "js" / "shop_floor_order_ux.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_recalculate_drawing_plan_api_uses_configurable_capability():
    src = _source(SHOP_FLOOR)
    assert "shop_floor_dxf_service" in src
    assert 'recalculate_drawing_plan = _public_delegate(_DXF, "recalculate_drawing_plan")' in src
    dxf = _source(ROOT / "almdina_erp" / "services" / "shop_floor_dxf_service.py")
    assert "Capability.RECALCULATE_PLAN" in dxf
    assert "_get_recalculation_order" in dxf
    assert "user_can_recalculate_drawing_system_plan" in dxf
    assert "force_cutting_plan_recalculation" in dxf


def test_drawing_recalc_uses_shared_immutability_bypass():
    policy = _source(ROOT / "almdina_erp" / "services" / "order_edit_policy.py")
    assert "is_order_at_drawing_stage" in policy
    assert "Capability.RECALCULATE_PLAN" in policy
    assert "frappe.get_roles" not in policy


def test_drawing_optimizer_ui_calls_recalculate_api():
    src = _source(DRAWING_UX)
    assert "recalculate_drawing_plan" in src
    assert "canUseDrawingOptimizer" in src
    assert "renderInboxPanel" in src
    assert "محرك خطة الرسم" in src
    assert "Auto Pro" in src


def test_drawing_form_exposes_dual_approval_and_print_actions():
    ux = _source(SHOP_FLOOR_UX)
    assert "خطة النظام" in ux
    assert "الخطة المرفوعة" in ux
    assert "اعتماد الرسم" in ux
    assert "طباعة خطة القص" in ux
    assert "plan_source: source" in ux
