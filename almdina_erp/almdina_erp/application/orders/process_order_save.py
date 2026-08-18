from __future__ import annotations

from typing import Protocol


class OrderSaveGateway(Protocol):
    """Port used by the order-save use case.

    Door Cutting Order owns customer requirements only. Cutting-plan lifecycle,
    fingerprints, optimization, snapshots, and approval belong to the Cutting
    Plan aggregate and must never be orchestrated from an ordinary order save.
    """

    def enforce_immutability(self) -> None: ...

    def set_piece_numbers(self) -> None: ...

    def validate_piece_inputs(self) -> None: ...

    def validate_piece_policies(self) -> None: ...

    def load_board_snapshot(self) -> None: ...

    def calculate_cut_dimensions(self) -> None: ...

    def calculate_piece_costs(self) -> None: ...


def process_order_save(gateway: OrderSaveGateway) -> None:
    """Validate and prepare one order without touching Cutting Plan state."""

    gateway.enforce_immutability()
    gateway.set_piece_numbers()
    gateway.validate_piece_inputs()
    gateway.validate_piece_policies()
    gateway.load_board_snapshot()
    gateway.calculate_cut_dimensions()
    gateway.calculate_piece_costs()


__all__ = [
    "OrderSaveGateway",
    "process_order_save",
]
