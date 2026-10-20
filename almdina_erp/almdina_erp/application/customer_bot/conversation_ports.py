"""Port for a customer-bot service that runs after an owned order is selected.

The request carries the trusted phone and the full order name. An adapter
must resolve that phone again and check ownership. The order name alone is
not access.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable

from almdina_erp.almdina_erp.domain.customer_bot.conversation import (
    ServiceResultCode,
    later_service_ids,
)
from almdina_erp.almdina_erp.domain.customer_bot.documents import CustomerBotDocument


@dataclass(frozen=True, slots=True)
class CustomerServiceRequest:
    phone: str
    service_id: str
    order_name: str

    def __post_init__(self) -> None:
        if not isinstance(self.phone, str) or not self.phone.strip():
            raise ValueError("a service request needs the trusted phone")
        if self.service_id not in later_service_ids():
            raise ValueError("order status is not dispatched through this port")
        if not isinstance(self.order_name, str) or not self.order_name.strip():
            raise ValueError("a service request needs the full order name")


@dataclass(frozen=True, slots=True)
class CustomerServiceResult:
    code: str
    amount: Decimal | None = None
    currency: str | None = None
    documents: tuple[CustomerBotDocument, ...] = ()

    def __post_init__(self) -> None:
        if self.code == ServiceResultCode.READY:
            if self.amount is None or self.amount < 0 or not self.currency:
                raise ValueError("a ready result needs a non-negative amount and currency")
            if len(self.documents) != 1:
                raise ValueError("a ready result needs exactly one document")
            return
        if self.amount is not None or self.currency is not None or self.documents:
            raise ValueError("a non-ready result cannot carry price or document data")


@runtime_checkable
class CustomerBotServicePort(Protocol):
    def execute(self, request: CustomerServiceRequest) -> CustomerServiceResult: ...


class UnavailableCustomerBotServices:
    """Default binding until cost, cutting-plan, and measurement reads exist."""

    def execute(self, request: CustomerServiceRequest) -> CustomerServiceResult:
        return CustomerServiceResult(ServiceResultCode.UNAVAILABLE)


__all__ = [
    "CustomerBotServicePort",
    "CustomerServiceRequest",
    "CustomerServiceResult",
    "UnavailableCustomerBotServices",
]
