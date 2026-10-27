"""Customer-bot use case for an approved customer price and its invoice PDF.

``execute`` reads eligibility, amount, and fingerprint once and returns a
descriptor with no PDF bytes. ``materialize`` renders one PDF for a send
attempt, then reads the same facts again and discards the bytes when they no
longer match. Neither method sends a document or stores one.
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
        """Describe the current approved invoice without rendering a PDF."""

        rejected = self._other_service(request)
        if rejected is not None:
            return rejected
        first = self._ready_snapshot(request)
        if isinstance(first, CustomerServiceResult):
            return first
        return self._ready(request, first, content=None)

    def materialize(self, request: CustomerServiceRequest) -> CustomerServiceResult:
        """Render one invoice PDF, then keep it only if the approval still matches."""

        rejected = self._other_service(request)
        if rejected is not None:
            return rejected
        first = self._ready_snapshot(request)
        if isinstance(first, CustomerServiceResult):
            return first
        try:
            content = self._pdf.render(request.order_name, first.invoice_payload or {})
        except Exception:
            return CustomerServiceResult(ServiceResultCode.INVOICE_FAILED)
        if not isinstance(content, bytes) or not content:
            return CustomerServiceResult(ServiceResultCode.INVOICE_FAILED)
        second = self._reader.read(request.phone, request.order_name)
        if not _same_price(first, second):
            return CustomerServiceResult(ServiceResultCode.PRICE_DATA_CHANGED)
        return self._ready(request, first, content=content)

    def _other_service(self, request: CustomerServiceRequest) -> CustomerServiceResult | None:
        if request.service_id != BotService.FINAL_COST:
            return CustomerServiceResult(ServiceResultCode.UNAVAILABLE)
        return None

    def _ready_snapshot(
        self, request: CustomerServiceRequest
    ) -> CustomerBotFinalPriceSnapshot | CustomerServiceResult:
        first = self._reader.read(request.phone, request.order_name)
        if first is None or not first.available or first.cancelled:
            return CustomerServiceResult(ServiceResultCode.PRICE_UNAVAILABLE)
        return first

    def _ready(
        self,
        request: CustomerServiceRequest,
        snapshot: CustomerBotFinalPriceSnapshot,
        *,
        content: bytes | None,
    ) -> CustomerServiceResult:
        document = CustomerBotDocument(
            document_type="customer_invoice",
            filename=_invoice_filename(request.order_name),
            mime_type="application/pdf",
            content=content,
            order_name=request.order_name,
            consistency_key=snapshot.consistency_key,
            service_id=BotService.FINAL_COST,
            amount=str(snapshot.amount),
            currency=str(snapshot.currency or ""),
        )
        return CustomerServiceResult(
            ServiceResultCode.READY,
            amount=snapshot.amount,
            currency=snapshot.currency,
            documents=(document,),
        )


def _same_price(
    first: CustomerBotFinalPriceSnapshot,
    second: CustomerBotFinalPriceSnapshot | None,
) -> bool:
    return not (
        second is None
        or not second.available
        or second.cancelled
        or second.consistency_key != first.consistency_key
        or second.amount != first.amount
        or second.currency != first.currency
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
