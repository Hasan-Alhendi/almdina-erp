"""Customer-bot use case for the exact approved cutting-plan PDF."""

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
class CustomerBotApprovedPlanSnapshot:
    """One read-only, customer-owned approved plan projection."""

    available: bool
    cancelled: bool = False
    plan_name: str | None = None
    revision: int | None = None
    source_type: str | None = None
    consistency_key: str = ""

    def __post_init__(self) -> None:
        if not self.available:
            if any(value is not None for value in (self.plan_name, self.revision, self.source_type)):
                raise ValueError("an unavailable plan cannot carry plan data")
            return
        if self.cancelled or not self.plan_name or self.revision is None or not self.source_type:
            raise ValueError("an available plan needs its approved identity")
        if not self.consistency_key:
            raise ValueError("an available plan needs a consistency key")


@runtime_checkable
class CustomerBotApprovedPlanReader(Protocol):
    def read(self, phone: str, order_name: str) -> CustomerBotApprovedPlanSnapshot | None: ...


@runtime_checkable
class CustomerBotCuttingPlanPdfPort(Protocol):
    def render(self, order_name: str, plan_name: str) -> bytes: ...


class CustomerBotApprovedPlanService(CustomerBotServicePort):
    def __init__(
        self,
        reader: CustomerBotApprovedPlanReader,
        pdf: CustomerBotCuttingPlanPdfPort,
    ) -> None:
        self._reader = reader
        self._pdf = pdf

    def execute(self, request: CustomerServiceRequest) -> CustomerServiceResult:
        if request.service_id != BotService.APPROVED_CUTTING_PLAN:
            return CustomerServiceResult(ServiceResultCode.UNAVAILABLE)

        first = self._reader.read(request.phone, request.order_name)
        if first is None or not first.available or first.cancelled:
            return CustomerServiceResult(ServiceResultCode.PLAN_UNAVAILABLE)

        try:
            content = self._pdf.render(request.order_name, first.plan_name or "")
            document = CustomerBotDocument(
                document_type="approved_cutting_plan",
                filename=_plan_filename(request.order_name, first.revision),
                mime_type="application/pdf",
                content=content,
            )
        except Exception:
            return CustomerServiceResult(ServiceResultCode.PLAN_PDF_FAILED)

        second = self._reader.read(request.phone, request.order_name)
        if (
            second is None
            or not second.available
            or second.cancelled
            or second.plan_name != first.plan_name
            or second.revision != first.revision
            or second.source_type != first.source_type
            or second.consistency_key != first.consistency_key
        ):
            return CustomerServiceResult(ServiceResultCode.PLAN_DATA_CHANGED)

        return CustomerServiceResult(ServiceResultCode.PLAN_READY, documents=(document,))


def _plan_filename(order_name: str, revision: int | None) -> str:
    safe = "".join(
        character if character.isalnum() or character in "-_" else "_"
        for character in str(order_name or "").strip()
    ) or "order"
    return f"خطة-قص-{safe}-rev-{int(revision or 1)}.pdf"


__all__ = [
    "CustomerBotApprovedPlanReader",
    "CustomerBotApprovedPlanService",
    "CustomerBotApprovedPlanSnapshot",
    "CustomerBotCuttingPlanPdfPort",
]
