from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from almdina_erp.almdina_erp.domain.inventory import (
    AvailabilityReport,
    MaterialDemand,
    MaterialRequirement,
    PieceMaterialInput,
    StockPosition,
    build_material_demand,
    evaluate_stock_availability,
)


@dataclass(frozen=True, slots=True)
class CheckOrderStockCommand:
    order_name: str
    throw_on_shortage: bool = True
    exclude_own_reservation: bool = True


@dataclass(frozen=True, slots=True)
class OrderStockContext:
    order_name: str
    plan_name: str
    stock_control_enabled: bool
    warehouse: str | None
    board_item: str
    full_board_count: int
    default_edge_type: str
    pieces: tuple[PieceMaterialInput, ...]


class StockAvailabilityRepository(Protocol):
    def load_context(self, order_name: str) -> OrderStockContext: ...

    def resolve_requirements(
        self,
        demand: MaterialDemand,
    ) -> tuple[MaterialRequirement, ...]: ...

    def find_active_order_reservation(
        self,
        order_name: str,
        plan_name: str,
    ) -> str | None: ...

    def get_stock_position(
        self,
        item_code: str,
        warehouse: str,
        *,
        exclude_reservation: str | None,
    ) -> StockPosition: ...


class MissingWarehouseError(RuntimeError):
    pass


class InsufficientStockError(RuntimeError):
    def __init__(self, report: AvailabilityReport) -> None:
        super().__init__("insufficient_stock")
        self.report = report


def check_order_stock(
    command: CheckOrderStockCommand,
    repository: StockAvailabilityRepository,
) -> AvailabilityReport:
    context = repository.load_context(command.order_name)
    if not context.stock_control_enabled:
        return AvailabilityReport(
            warehouse=context.warehouse,
            lines=(),
            stock_control_disabled=True,
        )

    demand = build_material_demand(
        board_item=context.board_item,
        full_board_count=context.full_board_count,
        default_edge_type=context.default_edge_type,
        pieces=context.pieces,
    )
    requirements = repository.resolve_requirements(demand)
    if not requirements:
        return AvailabilityReport(
            warehouse=context.warehouse,
            lines=(),
            no_stock_linked_materials=True,
        )

    if not context.warehouse:
        raise MissingWarehouseError("default_warehouse_required")

    excluded_reservation = (
        repository.find_active_order_reservation(
            context.order_name,
            context.plan_name,
        )
        if command.exclude_own_reservation
        else None
    )
    positions = {
        requirement.item_code: repository.get_stock_position(
            requirement.item_code,
            context.warehouse,
            exclude_reservation=excluded_reservation,
        )
        for requirement in requirements
    }
    report = evaluate_stock_availability(
        requirements=requirements,
        positions=positions,
        warehouse=context.warehouse,
        excluded_reservation=excluded_reservation,
    )
    if command.throw_on_shortage and not report.is_available:
        raise InsufficientStockError(report)
    return report


__all__ = [
    "CheckOrderStockCommand",
    "InsufficientStockError",
    "MissingWarehouseError",
    "OrderStockContext",
    "StockAvailabilityRepository",
    "check_order_stock",
]
