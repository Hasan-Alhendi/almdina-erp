from types import SimpleNamespace

from almdina_erp.almdina_erp.services.order_creation_service import apply_factory_defaults


def _settings():
    return SimpleNamespace(
        default_kerf_mm=4,
        default_trim_margin_mm=7,
        default_cutting_cost_per_board_usd=1.75,
        default_packing_mode="Skyline Best Fit",
    )


def test_missing_values_receive_factory_defaults(monkeypatch):
    monkeypatch.setattr(
        "almdina_erp.almdina_erp.services.order_creation_service.frappe.get_single",
        lambda doctype: _settings(),
    )
    values = apply_factory_defaults({"customer": "CUST-001"})
    assert values["kerf_mm"] == 4
    assert values["trim_margin_mm"] == 7
    assert values["cutting_cost_per_board_usd"] == 1.75
    assert values["packing_mode"] == "Skyline Best Fit"


def test_explicit_zero_is_not_replaced(monkeypatch):
    monkeypatch.setattr(
        "almdina_erp.almdina_erp.services.order_creation_service.frappe.get_single",
        lambda doctype: _settings(),
    )
    values = apply_factory_defaults(
        {
            "kerf_mm": 0,
            "trim_margin_mm": 0,
            "cutting_cost_per_board_usd": 0,
            "packing_mode": "Auto",
        }
    )
    assert values["kerf_mm"] == 0
    assert values["trim_margin_mm"] == 0
    assert values["cutting_cost_per_board_usd"] == 0
    assert values["packing_mode"] == "Auto"
