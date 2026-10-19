"""Ports for a customer-scoped order read.

The use case calls each port once per operation. Implementations batch stage
and route lookups. None of these ports accepts a caller-supplied customer id
as proof of identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class CustomerOrderHeader:
    name: str
    customer_id: str
    order_date: str | None
    stored_status: str
    revision_state: str
    production_path: str
    current_stage_name: str


@dataclass(frozen=True, slots=True)
class ProductionStageFacts:
    name: str
    status: str
    stage_type: str


@runtime_checkable
class CustomerOrderHeaderReader(Protocol):
    def list_current_headers(self, customer_id: str) -> tuple[CustomerOrderHeader, ...]: ...

    def get_header_by_exact_name(self, order_name: str) -> CustomerOrderHeader | None: ...


@runtime_checkable
class ProductionStageReader(Protocol):
    def stages_for_orders(
        self, pointers: tuple[tuple[str, str], ...]
    ) -> Mapping[str, ProductionStageFacts]: ...


@runtime_checkable
class ProductionRouteCatalog(Protocol):
    def terminal_by_path_and_stage(
        self, keys: tuple[tuple[str, str], ...]
    ) -> Mapping[tuple[str, str], bool | None]: ...


__all__ = [
    "CustomerOrderHeader",
    "CustomerOrderHeaderReader",
    "ProductionRouteCatalog",
    "ProductionStageFacts",
    "ProductionStageReader",
]
