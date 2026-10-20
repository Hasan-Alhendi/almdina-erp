"""Customer-bot use case for an approved customer price and its invoice PDF.

The use case owns the two-read consistency check. It never sends a document and
never stores one in conversation state; a provider-neutral document is returned
to the caller for a later delivery step.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from almdina_erp.almdina_erp.domain.customer_bot.conversation import (
    BotService,
    ServiceResultCode,
)
from almdina_erp.almdina_erp.domain.customer_bot.documents import CustomerBotDocument

from .conversation_ports import CustomerBotServicePort, CustomerServiceRequest, CustomerServiceResult


@dataclass(frozen=True, slots=True)
class CustomerBotFinalPriceSnapshot:
    """One verified, read-only customer invoice projection."""

    available: bool
    cancelled: bool = False
    amount: Decimal | None = None
    currency: str | None = None
    invoice_payload: Mapping[str, Any] | None = None
    consistency_key: str = ""

    def __post_init__(self) -> None:
        if not self.available:
            if any(value is not None for value in (self.amount, self.currency, self.invoice_payload)):
                raise ValueError("an unavailable snapshot cannot carry invoice data")
            return
        if self.cancelled or self.amount is None or not self.currency or self.invoice_payload is None:
            raise ValueError("an available snapshot needs a live invoice projection")
        if not self.consistency_key:
            raise ValueError("an available snapshot needs a consistency key")


@runtime_checkable
class CustomerBotFinalPriceReader(Protocol):
    def read(self, phone: str, order_name: str) -> CustomerBotFinalPriceSnapshot | None: ...


@runtime_checkable
class CustomerBotInvoicePdfPort(Protocol):
    def render(self, order_name: str, invoice_payload: Mapping[str, Any]) -> bytes: ...


class CustomerBotFinalPriceService(CustomerBotServicePort):
    def __init__(self, reader: CustomerBotFinalPriceReader, pdf: CustomerBotInvoicePdfPort) -> None:
        self._reader = reader
        self._pdf = pdf

    def execute(self, request: CustomerServiceRequest) -> CustomerServiceResult:
        if request.service_id != BotService.FINAL_COST:
            return CustomerServiceResult(ServiceResultCode.UNAVAILABLE)

        first = self._reader.read(request.phone, request.order_name)
        if first is None or not first.available or first.cancelled:
            return CustomerServiceResult(ServiceResultCode.PRICE_UNAVAILABLE)

        try:
            content = self._pdf.render(request.order_name, first.invoice_payload or {})
            document = CustomerBotDocument(
                document_type="customer_invoice",
                filename=_invoice_filename(request.order_name),
                mime_type="application/pdf",
                content=content,
            )
        except Exception:
            return CustomerServiceResult(ServiceResultCode.INVOICE_FAILED)

        second = self._reader.read(request.phone, request.order_name)
        if (
            second is None
            or not second.available
            or second.cancelled
            or second.consistency_key != first.consistency_key
            or second.amount != first.amount
            or second.currency != first.currency
        ):
            return CustomerServiceResult(ServiceResultCode.PRICE_DATA_CHANGED)

        return CustomerServiceResult(
            ServiceResultCode.READY,
            amount=first.amount,
            currency=first.currency,
            documents=(document,),
        )


def _invoice_filename(order_name: str) -> str:
    safe = "".join(
        character if character.isalnum() or character in "-_" else "_"
        for character in str(order_name or "").strip()
    ) or "order"
    return f"فاتورة-{safe}.pdf"


__all__ = [
    "CustomerBotFinalPriceReader",
    "CustomerBotFinalPriceService",
    "CustomerBotFinalPriceSnapshot",
    "CustomerBotInvoicePdfPort",
]
