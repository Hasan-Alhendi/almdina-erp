from types import SimpleNamespace

from almdina_erp.almdina_erp.doctype.door_cutting_order.door_cutting_order import DoorCuttingOrder


class FakeOrder:
    def __init__(self, **values):
        self.values = dict(values)
        self.revision = values.get("revision")

    def get(self, fieldname):
        return self.values.get(fieldname)

    def set(self, fieldname, value):
        self.values[fieldname] = value
        setattr(self, fieldname, value)


def _settings():
    return SimpleNamespace(
        default_kerf_mm=4,
        default_trim_margin_mm=8,
        default_cutting_cost_per_board_usd=2.25,
        default_packing_mode="MaxRects Best Area",
    )


def test_before_insert_applies_factory_settings_when_missing(monkeypatch):
    monkeypatch.setattr(
        "almdina_erp.almdina_erp.doctype.door_cutting_order.door_cutting_order.frappe.get_single",
        lambda doctype: _settings(),
    )
    order = FakeOrder()
    DoorCuttingOrder.before_insert(order)
    assert order.values["kerf_mm"] == 4
    assert order.values["trim_margin_mm"] == 8
    assert order.values["cutting_cost_per_board_usd"] == 2.25
    assert order.values["packing_mode"] == "MaxRects Best Area"
    assert order.revision == 1


def test_before_insert_preserves_explicit_zero(monkeypatch):
    monkeypatch.setattr(
        "almdina_erp.almdina_erp.doctype.door_cutting_order.door_cutting_order.frappe.get_single",
        lambda doctype: _settings(),
    )
    order = FakeOrder(
        kerf_mm=0,
        trim_margin_mm=0,
        cutting_cost_per_board_usd=0,
        packing_mode="Auto",
        revision=3,
    )
    DoorCuttingOrder.before_insert(order)
    assert order.values["kerf_mm"] == 0
    assert order.values["trim_margin_mm"] == 0
    assert order.values["cutting_cost_per_board_usd"] == 0
    assert order.values["packing_mode"] == "Auto"
    assert order.revision == 3
