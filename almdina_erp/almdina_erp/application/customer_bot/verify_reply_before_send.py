"""Re-check access before handing a claimed reply to a send port.

Preflight does not freeze provider state for the whole network round-trip.
After this check returns ``send``, ownership or approval may still change
before the gateway acknowledges the request. That limit is intentional:
OpenWA acceptance is not customer delivery, and this module does not claim
otherwise.

Rules live in the existing identity and service use cases. The worker does
not re-implement price or plan approval formulas.
"""

from __future__ import annotations

from dataclasses import dataclass

from almdina_erp.almdina_erp.domain.customer_bot.conversation import (
    BotService,
    ServiceResultCode,
)
from almdina_erp.almdina_erp.domain.customer_bot.document_reply_spec import DocumentReplySpec
from almdina_erp.almdina_erp.domain.customer_bot.documents import CustomerBotDocument
from almdina_erp.almdina_erp.domain.customer_bot.identity import IdentityCode
from almdina_erp.almdina_erp.domain.customer_bot.reply_intent import PART_DOCUMENT, PART_TEXT

from .conversation_ports import CustomerBotServicePort, CustomerServiceRequest
from .phone_access_ports import CustomerPhoneDirectory
from .read_runtime import read_customer_bot_runtime
from .reply_outbox import ClaimedReply
from .resolve_customer_identity import resolve_customer_identity
from .settings_commands import CustomerBotSettingsStore

SEND = "send"
CANCEL = "cancel"

REASON_BOT_DISABLED = "bot_disabled"
REASON_EPOCH_CHANGED = "acceptance_epoch_changed"
REASON_IDENTITY_CHANGED = "identity_changed"
REASON_ORDER_INELIGIBLE = "order_ineligible"
REASON_APPROVAL_STALE = "approval_stale"
REASON_AMOUNT_MISMATCH = "amount_mismatch"
REASON_DOCUMENT_UNAVAILABLE = "document_unavailable"
REASON_MISSING_SPEC = "missing_document_spec"
REASON_UNSUPPORTED_PART = "unsupported_part_kind"


@dataclass(frozen=True, slots=True)
class ReplyPreflightResult:
    action: str
    reason_code: str
    document: CustomerBotDocument | None = None

    @property
    def should_send(self) -> bool:
        return self.action == SEND


def verify_reply_before_send(
    claimed: ClaimedReply,
    *,
    settings: CustomerBotSettingsStore,
    directory: CustomerPhoneDirectory,
    services: CustomerBotServicePort,
) -> ReplyPreflightResult:
    """Decide whether the claimed body/spec may leave the outbox.

    General replies without a pinned customer only need a live accepting bot
    and a matching acceptance epoch when the intent recorded one. Replies that
    pin a customer must still resolve to that customer. Document parts and
    financial siblings re-run the current service use case and cancel when the
    pinned consistency key or amount no longer matches.
    """

    runtime = read_customer_bot_runtime(settings)
    if not runtime.accepting_messages:
        return ReplyPreflightResult(CANCEL, REASON_BOT_DISABLED)
    if claimed.acceptance_epoch is not None and runtime.acceptance_epoch != claimed.acceptance_epoch:
        return ReplyPreflightResult(CANCEL, REASON_EPOCH_CHANGED)

    if claimed.customer_id or claimed.normalized_phone:
        identity_check = _verify_identity(claimed, directory)
        if identity_check is not None:
            return identity_check

    for spec in claimed.group_document_specs:
        group_check = _verify_document_spec(spec, services, require_bytes=False)
        if group_check.action == CANCEL:
            return group_check

    if claimed.part_kind == PART_TEXT:
        return ReplyPreflightResult(SEND, "preflight_ok")

    if claimed.part_kind != PART_DOCUMENT:
        return ReplyPreflightResult(CANCEL, REASON_UNSUPPORTED_PART)
    if claimed.document_spec is None:
        return ReplyPreflightResult(CANCEL, REASON_MISSING_SPEC)
    return _verify_document_spec(claimed.document_spec, services, require_bytes=True)


def _verify_identity(
    claimed: ClaimedReply,
    directory: CustomerPhoneDirectory,
) -> ReplyPreflightResult | None:
    phone = claimed.normalized_phone
    expected = claimed.customer_id
    if not phone or not expected:
        return ReplyPreflightResult(CANCEL, REASON_IDENTITY_CHANGED)
    identity = resolve_customer_identity(directory, phone)
    if identity.code != IdentityCode.ALLOWED or identity.customer_id != expected:
        return ReplyPreflightResult(CANCEL, REASON_IDENTITY_CHANGED)
    return None


def _verify_document_spec(
    spec: DocumentReplySpec,
    services: CustomerBotServicePort,
    *,
    require_bytes: bool,
) -> ReplyPreflightResult:
    result = services.execute(
        CustomerServiceRequest(
            phone=spec.normalized_phone,
            service_id=spec.service_id,
            order_name=spec.order_name,
        )
    )
    ready_codes = {
        BotService.FINAL_COST: ServiceResultCode.READY,
        BotService.APPROVED_CUTTING_PLAN: ServiceResultCode.PLAN_READY,
        BotService.MEASUREMENTS: ServiceResultCode.MEASUREMENTS_READY,
    }
    expected = ready_codes.get(spec.service_id)
    if expected is None or result.code != expected or not result.documents:
        if result.code in {
            ServiceResultCode.PRICE_UNAVAILABLE,
            ServiceResultCode.PLAN_UNAVAILABLE,
            ServiceResultCode.MEASUREMENTS_UNAVAILABLE,
            ServiceResultCode.UNAVAILABLE,
        }:
            return ReplyPreflightResult(CANCEL, REASON_ORDER_INELIGIBLE)
        if result.code in {
            ServiceResultCode.PRICE_DATA_CHANGED,
            ServiceResultCode.PLAN_DATA_CHANGED,
            ServiceResultCode.MEASUREMENTS_DATA_CHANGED,
        }:
            return ReplyPreflightResult(CANCEL, REASON_APPROVAL_STALE)
        return ReplyPreflightResult(CANCEL, REASON_DOCUMENT_UNAVAILABLE)

    document = result.documents[0]
    if document.consistency_key != spec.consistency_key:
        return ReplyPreflightResult(CANCEL, REASON_APPROVAL_STALE)
    if spec.service_id == BotService.FINAL_COST:
        if str(document.amount or "") != str(spec.amount or "") or str(document.currency or "") != str(
            spec.currency or ""
        ):
            return ReplyPreflightResult(CANCEL, REASON_AMOUNT_MISMATCH)
        if result.amount is not None and spec.amount is not None and str(result.amount) != str(spec.amount):
            return ReplyPreflightResult(CANCEL, REASON_AMOUNT_MISMATCH)
        if result.currency is not None and spec.currency is not None and str(result.currency) != str(spec.currency):
            return ReplyPreflightResult(CANCEL, REASON_AMOUNT_MISMATCH)
    if spec.plan_name is not None and document.plan_name != spec.plan_name:
        return ReplyPreflightResult(CANCEL, REASON_APPROVAL_STALE)
    if spec.plan_revision is not None and document.plan_revision != spec.plan_revision:
        return ReplyPreflightResult(CANCEL, REASON_APPROVAL_STALE)
    if require_bytes:
        return ReplyPreflightResult(SEND, "preflight_ok", document=document)
    return ReplyPreflightResult(SEND, "preflight_ok")


__all__ = [
    "CANCEL",
    "REASON_AMOUNT_MISMATCH",
    "REASON_APPROVAL_STALE",
    "REASON_BOT_DISABLED",
    "REASON_DOCUMENT_UNAVAILABLE",
    "REASON_EPOCH_CHANGED",
    "REASON_IDENTITY_CHANGED",
    "REASON_MISSING_SPEC",
    "REASON_ORDER_INELIGIBLE",
    "REASON_UNSUPPORTED_PART",
    "ReplyPreflightResult",
    "SEND",
    "verify_reply_before_send",
]
