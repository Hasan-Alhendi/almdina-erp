from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


AVAILABILITY_EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class MaterialRequirement:
    item_code: str
    required_qty: float
    kind: str
    planned_unit: str
    planned_qty: float
    edge_type: str = ""
    stock_uom: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StockPosition:
    item_code: str
    actual_qty: float
    reserved_qty: float


@dataclass(frozen=True, slots=True)
class AvailabilityLine:
    requirement: MaterialRequirement
    warehouse: str
    actual_qty: float
    reserved_qty: float
    available_qty: float
    shortage_qty: float

    @property
    def is_shortage(self) -> bool:
        return self.available_qty + AVAILABILITY_EPSILON < self.requirement.required_qty

    def as_dict(self) -> dict[str, Any]:
        row: dict[str, Any] = {
            **dict(self.requirement.metadata),
            "item_code": self.requirement.item_code,
            "qty": self.requirement.required_qty,
            "kind": self.requirement.kind,
            "planned_unit": self.requirement.planned_unit,
            "planned_qty": self.requirement.planned_qty,
        }
        if self.requirement.edge_type:
            row["edge_type"] = self.requirement.edge_type
        if self.requirement.stock_uom:
            row["stock_uom"] = self.requirement.stock_uom
        row.update(
            {
                "warehouse": self.warehouse,
                "actual_qty": self.actual_qty,
                "reserved_by_other_reservations": self.reserved_qty,
                "available_qty": self.available_qty,
                "required_qty": self.requirement.required_qty,
                "shortage_qty": self.shortage_qty,
            }
        )
        return row


@dataclass(frozen=True, slots=True)
class AvailabilityReport:
    warehouse: str | None
    lines: tuple[AvailabilityLine, ...]
    excluded_reservation: str | None = None
    stock_control_disabled: bool = False
    no_stock_linked_materials: bool = False

    @property
    def shortages(self) -> tuple[AvailabilityLine, ...]:
        return tuple(line for line in self.lines if line.is_shortage)

    @property
    def is_available(self) -> bool:
        return not self.shortages

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "warehouse": self.warehouse,
            "materials": [line.as_dict() for line in self.lines],
            "shortages": [line.as_dict() for line in self.shortages],
            "is_available": self.is_available,
            "excluded_reservation": self.excluded_reservation,
        }
        if self.stock_control_disabled:
            result["stock_control_disabled"] = True
        if self.no_stock_linked_materials:
            result["no_stock_linked_materials"] = True
        return result


def evaluate_stock_availability(
    *,
    requirements: Iterable[MaterialRequirement],
    positions: Mapping[str, StockPosition],
    warehouse: str,
    excluded_reservation: str | None = None,
) -> AvailabilityReport:
    lines: list[AvailabilityLine] = []
    for requirement in requirements:
        position = positions.get(requirement.item_code) or StockPosition(
            item_code=requirement.item_code,
            actual_qty=0.0,
            reserved_qty=0.0,
        )
        actual_qty = float(position.actual_qty or 0)
        reserved_qty = float(position.reserved_qty or 0)
        available_qty = max(0.0, actual_qty - reserved_qty)
        required_qty = max(0.0, float(requirement.required_qty or 0))
        normalized_requirement = MaterialRequirement(
            item_code=requirement.item_code,
            required_qty=required_qty,
            kind=requirement.kind,
            planned_unit=requirement.planned_unit,
            planned_qty=requirement.planned_qty,
            edge_type=requirement.edge_type,
            stock_uom=requirement.stock_uom,
            metadata=requirement.metadata,
        )
        lines.append(
            AvailabilityLine(
                requirement=normalized_requirement,
                warehouse=warehouse,
                actual_qty=actual_qty,
                reserved_qty=reserved_qty,
                available_qty=available_qty,
                shortage_qty=max(0.0, required_qty - available_qty),
            )
        )

    return AvailabilityReport(
        warehouse=warehouse,
        lines=tuple(lines),
        excluded_reservation=excluded_reservation,
    )


__all__ = [
    "AVAILABILITY_EPSILON",
    "AvailabilityLine",
    "AvailabilityReport",
    "MaterialRequirement",
    "StockPosition",
    "evaluate_stock_availability",
]
