from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class OrderSaveGateway(Protocol):
    """Port used by the order-save use case.

    The Application layer owns only orchestration. Frappe document access,
    validation messages, persistence details, and framework exceptions remain in
    the outer gateway implementation.
    """

    def enforce_immutability(self) -> None: ...

    def set_piece_numbers(self) -> None: ...

    def validate_numeric_inputs(self) -> None: ...

    def validate_piece_inputs(self) -> None: ...

    def validate_piece_policies(self) -> None: ...

    def load_board_snapshot(self) -> None: ...

    def calculate_cut_dimensions(self) -> None: ...

    def calculate_piece_costs(self) -> None: ...

    def plan_input_fingerprint(self) -> str: ...

    def force_recalculation_requested(self) -> bool: ...

    def can_reuse_current_plan(self, input_fingerprint: str) -> bool: ...

    def calculate_cutting_plan(self, input_fingerprint: str) -> None: ...

    def refresh_current_plan(self, input_fingerprint: str) -> None: ...

    def invalidate_current_plan(self) -> None: ...


@dataclass(frozen=True)
class OrderSaveOutcome:
    plan_action: str
    input_fingerprint: str


def process_order_save(gateway: OrderSaveGateway) -> OrderSaveOutcome:
    """Validate and refresh one order without importing Frappe.

    Expensive optimization runs only when explicitly requested. Ordinary saves
    either refresh metadata/costs on a reusable plan or invalidate stale output.
    """

    gateway.enforce_immutability()
    gateway.set_piece_numbers()
    gateway.validate_numeric_inputs()
    gateway.validate_piece_inputs()
    gateway.validate_piece_policies()
    gateway.load_board_snapshot()
    gateway.calculate_cut_dimensions()
    gateway.calculate_piece_costs()

    input_fingerprint = gateway.plan_input_fingerprint()
    if gateway.force_recalculation_requested():
        gateway.calculate_cutting_plan(input_fingerprint)
        action = "recalculated"
    elif gateway.can_reuse_current_plan(input_fingerprint):
        gateway.refresh_current_plan(input_fingerprint)
        action = "reused"
    else:
        gateway.invalidate_current_plan()
        action = "invalidated"

    return OrderSaveOutcome(
        plan_action=action,
        input_fingerprint=input_fingerprint,
    )


__all__ = [
    "OrderSaveGateway",
    "OrderSaveOutcome",
    "process_order_save",
]
