"""Customer-bot use case for the saved order-measurements PDF."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from almdina_erp.almdina_erp.domain.customer_bot.conversation import (
    BotService,
    ServiceResultCode,
)
from almdina_erp.almdina_erp.domain.customer_bot.documents import CustomerBotDocument

from .conversation_ports import CustomerBotServicePort, CustomerServiceRequest, CustomerServiceResult


@dataclass(frozen=True, slots=True)
class CustomerBotMeasurementsSnapshot:
    """One read-only projection of measurements saved on an owned order."""

    available: bool
    cancelled: bool = False
    order_name: str | None = None
    consistency_key: str = ""

    def __post_init__(self) -> None:
        if not self.available:
            if self.order_name is not None or self.consistency_key:
                raise ValueError("an unavailable measurements read cannot carry document data")
            return
        if self.cancelled or not self.order_name or not self.consistency_key:
            raise ValueError("available measurements need the order and a consistency key")


@runtime_checkable
class CustomerBotMeasurementsReader(Protocol):
    def read(self, phone: str, order_name: str) -> CustomerBotMeasurementsSnapshot | None: ...


@runtime_checkable
class CustomerBotMeasurementsPdfPort(Protocol):
    def render(self, phone: str, order_name: str) -> bytes: ...


class CustomerBotMeasurementsService(CustomerBotServicePort):
    def __init__(
        self,
        reader: CustomerBotMeasurementsReader,
        pdf: CustomerBotMeasurementsPdfPort,
    ) -> None:
        self._reader = reader
        self._pdf = pdf

    def execute(self, request: CustomerServiceRequest) -> CustomerServiceResult:
        if request.service_id != BotService.MEASUREMENTS:
            return CustomerServiceResult(ServiceResultCode.UNAVAILABLE)

        first = self._reader.read(request.phone, request.order_name)
        if first is None or not first.available or first.cancelled:
            return CustomerServiceResult(ServiceResultCode.MEASUREMENTS_UNAVAILABLE)

        try:
            content = self._pdf.render(request.phone, first.order_name or "")
            if not content.startswith(b"%PDF"):
                raise ValueError("measurements_pdf_failed")
            document = CustomerBotDocument(
                document_type="order_measurements",
                filename=_measurements_filename(first.order_name or ""),
                mime_type="application/pdf",
                content=content,
                order_name=first.order_name or request.order_name,
                consistency_key=first.consistency_key,
                service_id=BotService.MEASUREMENTS,
            )
        except Exception:
            return CustomerServiceResult(ServiceResultCode.MEASUREMENTS_PDF_FAILED)

        second = self._reader.read(request.phone, request.order_name)
        if (
            second is None
            or not second.available
            or second.cancelled
            or second.order_name != first.order_name
            or second.consistency_key != first.consistency_key
        ):
            return CustomerServiceResult(ServiceResultCode.MEASUREMENTS_DATA_CHANGED)

        return CustomerServiceResult(
            ServiceResultCode.MEASUREMENTS_READY,
            documents=(document,),
        )


def _measurements_filename(order_name: str) -> str:
    safe = "".join(
        character if character.isalnum() or character in "-_" else "_"
        for character in str(order_name or "").strip()
    ) or "order"
    return f"قياسات-{safe}.pdf"


__all__ = [
    "CustomerBotMeasurementsPdfPort",
    "CustomerBotMeasurementsReader",
    "CustomerBotMeasurementsService",
    "CustomerBotMeasurementsSnapshot",
]
