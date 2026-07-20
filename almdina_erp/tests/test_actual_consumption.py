from types import SimpleNamespace

from almdina_erp.almdina_erp.services.actual_consumption_service import _variance_cost_usd


def test_board_material_variance_uses_approved_board_rate():
    plan = SimpleNamespace(board_rate_usd=42)
    material = {
        "kind": "Board",
        "required_qty": 3,
        "planned_unit": "Board",
        "planned_qty": 3,
    }
    assert _variance_cost_usd(material, 1, plan) == 42
    assert _variance_cost_usd(material, -1, plan) == -42


def test_zero_material_variance_has_zero_cost():
    plan = SimpleNamespace(board_rate_usd=42)
    material = {"kind": "Board", "required_qty": 3, "planned_qty": 3}
    assert _variance_cost_usd(material, 0, plan) == 0
