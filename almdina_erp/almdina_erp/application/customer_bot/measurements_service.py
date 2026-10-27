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
        """Describe saved measurements without rendering a PDF."""

        rejected = self._other_service(request)
        if rejected is not None:
            return rejected
        first = self._ready_snapshot(request)
        if isinstance(first, CustomerServiceResult):
            return first
        return self._ready(request, first, content=None)

    def materialize(self, request: CustomerServiceRequest) -> CustomerServiceResult:
        """Render one measurements PDF, then keep it only if the snapshot still matches."""

        rejected = self._other_service(request)
        if rejected is not None:
            return rejected
        first = self._ready_snapshot(request)
        if isinstance(first, CustomerServiceResult):
            return first
        try:
            content = self._pdf.render(request.phone, first.order_name or "")
            if not isinstance(content, bytes) or not content.startswith(b"%PDF"):
                raise ValueError("measurements_pdf_failed")
        except Exception:
            return CustomerServiceResult(ServiceResultCode.MEASUREMENTS_PDF_FAILED)
        second = self._reader.read(request.phone, request.order_name)
        if not _same_measurements(first, second):
            return CustomerServiceResult(ServiceResultCode.MEASUREMENTS_DATA_CHANGED)
        return self._ready(request, first, content=content)

    def _other_service(self, request: CustomerServiceRequest) -> CustomerServiceResult | None:
        if request.service_id != BotService.MEASUREMENTS:
            return CustomerServiceResult(ServiceResultCode.UNAVAILABLE)
        return None

    def _ready_snapshot(
        self, request: CustomerServiceRequest
    ) -> CustomerBotMeasurementsSnapshot | CustomerServiceResult:
        first = self._reader.read(request.phone, request.order_name)
        if first is None or not first.available or first.cancelled:
            return CustomerServiceResult(ServiceResultCode.MEASUREMENTS_UNAVAILABLE)
        return first

    def _ready(
        self,
        request: CustomerServiceRequest,
        snapshot: CustomerBotMeasurementsSnapshot,
        *,
        content: bytes | None,
    ) -> CustomerServiceResult:
        document = CustomerBotDocument(
            document_type="order_measurements",
            filename=_measurements_filename(snapshot.order_name or ""),
            mime_type="application/pdf",
            content=content,
            order_name=snapshot.order_name or request.order_name,
            consistency_key=snapshot.consistency_key,
            service_id=BotService.MEASUREMENTS,
        )
        return CustomerServiceResult(
            ServiceResultCode.MEASUREMENTS_READY,
            documents=(document,),
        )


def _same_measurements(
    first: CustomerBotMeasurementsSnapshot,
    second: CustomerBotMeasurementsSnapshot | None,
) -> bool:
    return not (
        second is None
        or not second.available
        or second.cancelled
        or second.order_name != first.order_name
        or second.consistency_key != first.consistency_key
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
