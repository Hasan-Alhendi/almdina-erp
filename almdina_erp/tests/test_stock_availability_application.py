from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.inventory import (
    CheckOrderStockCommand,
    InsufficientStockError,
    MissingWarehouseError,
    OrderStockContext,
    check_order_stock,
)
from almdina_erp.almdina_erp.domain.inventory import (
    MaterialRequirement,
    PieceMaterialInput,
    StockPosition,
)


class FakeRepository:
    def __init__(
        self,
        *,
        context: OrderStockContext,
        requirements: tuple[MaterialRequirement, ...] = (),
        positions: dict[str, StockPosition] | None = None,
        reservation: str | None = None,
    ) -> None:
        self.context = context
        self.requirements = requirements
        self.positions = positions or {}
        self.reservation = reservation
        self.excluded_values: list[str | None] = []

    def load_context(self, order_name: str) -> OrderStockContext:
        self.loaded_order = order_name
        return self.context

    def resolve_requirements(self, demand):
        self.demand = demand
        return self.requirements

    def find_active_order_reservation(self, order_name: str, plan_name: str):
        self.reservation_lookup = (order_name, plan_name)
        return self.reservation

    def get_stock_position(
        self,
        item_code: str,
        warehouse: str,
        *,
        exclude_reservation: str | None,
    ) -> StockPosition:
        self.excluded_values.append(exclude_reservation)
        return self.positions[item_code]


def context(
    *,
    enabled: bool = True,
    warehouse: str | None = "Main - AC",
) -> OrderStockContext:
    return OrderStockContext(
        order_name="ORD-1",
        plan_name="PLAN-1",
        stock_control_enabled=enabled,
        warehouse=warehouse,
        board_item="BOARD-1",
        full_board_count=2,
        default_edge_type="EDGE-TYPE",
        pieces=(PieceMaterialInput(edge_type="", edge_meters=4),),
    )


class TestStockAvailabilityApplication(unittest.TestCase):
    def test_disabled_stock_control_returns_compatible_report(self) -> None:
        repository = FakeRepository(context=context(enabled=False))
        report = check_order_stock(CheckOrderStockCommand("ORD-1"), repository)
        payload = report.as_dict()
        self.assertTrue(payload["stock_control_disabled"])
        self.assertTrue(payload["is_available"])
        self.assertEqual(payload["materials"], [])

    def test_no_linked_requirements_is_available(self) -> None:
        repository = FakeRepository(context=context(), requirements=())
        report = check_order_stock(CheckOrderStockCommand("ORD-1"), repository)
        self.assertTrue(report.no_stock_linked_materials)
        self.assertTrue(report.is_available)

    def test_warehouse_is_required_only_when_materials_exist(self) -> None:
        requirement = MaterialRequirement(
            item_code="BOARD-1",
            required_qty=2,
            kind="Board",
            planned_unit="Board",
            planned_qty=2,
        )
        repository = FakeRepository(
            context=context(warehouse=None),
            requirements=(requirement,),
        )
        with self.assertRaises(MissingWarehouseError):
            check_order_stock(CheckOrderStockCommand("ORD-1"), repository)

    def test_own_reservation_is_excluded_from_other_reserved_qty(self) -> None:
        requirement = MaterialRequirement(
            item_code="BOARD-1",
            required_qty=2,
            kind="Board",
            planned_unit="Board",
            planned_qty=2,
        )
        repository = FakeRepository(
            context=context(),
            requirements=(requirement,),
            positions={
                "BOARD-1": StockPosition(
                    item_code="BOARD-1",
                    actual_qty=5,
                    reserved_qty=2,
                )
            },
            reservation="RES-OWN",
        )
        report = check_order_stock(
            CheckOrderStockCommand("ORD-1", exclude_own_reservation=True),
            repository,
        )
        self.assertTrue(report.is_available)
        self.assertEqual(report.excluded_reservation, "RES-OWN")
        self.assertEqual(repository.excluded_values, ["RES-OWN"])

    def test_shortage_can_be_returned_or_raised(self) -> None:
        requirement = MaterialRequirement(
            item_code="BOARD-1",
            required_qty=4,
            kind="Board",
            planned_unit="Board",
            planned_qty=4,
        )
        repository = FakeRepository(
            context=context(),
            requirements=(requirement,),
            positions={
                "BOARD-1": StockPosition(
                    item_code="BOARD-1",
                    actual_qty=3,
                    reserved_qty=1,
                )
            },
        )
        report = check_order_stock(
            CheckOrderStockCommand("ORD-1", throw_on_shortage=False),
            repository,
        )
        self.assertFalse(report.is_available)
        self.assertEqual(report.shortages[0].shortage_qty, 2)

        with self.assertRaises(InsufficientStockError) as raised:
            check_order_stock(
                CheckOrderStockCommand("ORD-1", throw_on_shortage=True),
                repository,
            )
        self.assertEqual(raised.exception.report.shortages[0].shortage_qty, 2)


if __name__ == "__main__":
    unittest.main()
