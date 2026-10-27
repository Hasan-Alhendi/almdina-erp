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
        """Describe the approved plan without rendering a PDF."""

        rejected = self._other_service(request)
        if rejected is not None:
            return rejected
        first = self._ready_snapshot(request)
        if isinstance(first, CustomerServiceResult):
            return first
        return self._ready(request, first, content=None)

    def materialize(self, request: CustomerServiceRequest) -> CustomerServiceResult:
        """Render one plan PDF, then keep it only if the approved identity still matches."""

        rejected = self._other_service(request)
        if rejected is not None:
            return rejected
        first = self._ready_snapshot(request)
        if isinstance(first, CustomerServiceResult):
            return first
        try:
            content = self._pdf.render(request.order_name, first.plan_name or "")
        except Exception:
            return CustomerServiceResult(ServiceResultCode.PLAN_PDF_FAILED)
        if not isinstance(content, bytes) or not content:
            return CustomerServiceResult(ServiceResultCode.PLAN_PDF_FAILED)
        second = self._reader.read(request.phone, request.order_name)
        if not _same_plan(first, second):
            return CustomerServiceResult(ServiceResultCode.PLAN_DATA_CHANGED)
        return self._ready(request, first, content=content)

    def _other_service(self, request: CustomerServiceRequest) -> CustomerServiceResult | None:
        if request.service_id != BotService.APPROVED_CUTTING_PLAN:
            return CustomerServiceResult(ServiceResultCode.UNAVAILABLE)
        return None

    def _ready_snapshot(
        self, request: CustomerServiceRequest
    ) -> CustomerBotApprovedPlanSnapshot | CustomerServiceResult:
        first = self._reader.read(request.phone, request.order_name)
        if first is None or not first.available or first.cancelled:
            return CustomerServiceResult(ServiceResultCode.PLAN_UNAVAILABLE)
        return first

    def _ready(
        self,
        request: CustomerServiceRequest,
        snapshot: CustomerBotApprovedPlanSnapshot,
        *,
        content: bytes | None,
    ) -> CustomerServiceResult:
        document = CustomerBotDocument(
            document_type="approved_cutting_plan",
            filename=_plan_filename(request.order_name, snapshot.revision),
            mime_type="application/pdf",
            content=content,
            order_name=request.order_name,
            consistency_key=snapshot.consistency_key,
            service_id=BotService.APPROVED_CUTTING_PLAN,
            plan_name=snapshot.plan_name,
            plan_revision=snapshot.revision,
            source_type=snapshot.source_type,
        )
        return CustomerServiceResult(ServiceResultCode.PLAN_READY, documents=(document,))


def _same_plan(
    first: CustomerBotApprovedPlanSnapshot,
    second: CustomerBotApprovedPlanSnapshot | None,
) -> bool:
    return not (
        second is None
        or not second.available
        or second.cancelled
        or second.plan_name != first.plan_name
        or second.revision != first.revision
        or second.source_type != first.source_type
        or second.consistency_key != first.consistency_key
    )


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
