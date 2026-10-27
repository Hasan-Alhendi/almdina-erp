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
    BotMessage,
    BotMessageKey,
    BotService,
    ServiceResultCode,
)
from almdina_erp.almdina_erp.domain.customer_bot.message_templates import (
    DOCUMENT_CAPTION_MAX,
    CustomerTextRenderError,
    customer_outbound_text,
    document_description_messages,
    document_failure_message,
    render_customer_lines,
)
from almdina_erp.almdina_erp.domain.customer_bot.reply_intent import CAPTION_TOO_LONG
from almdina_erp.almdina_erp.domain.customer_bot.phone_number import (
    CustomerPhoneError,
    normalize_customer_phone,
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
REASON_DOCUMENT_RENDER_FAILED = "document_render_failed"
REASON_CAPTION_MISMATCH = "caption_mismatch"
REASON_MISSING_SPEC = "missing_document_spec"
REASON_UNSUPPORTED_PART = "unsupported_part_kind"
REASON_DESTINATION_MISMATCH = "destination_mismatch"
REASON_PUBLIC_GUIDANCE_REJECTED = "public_guidance_rejected"
PUBLIC_GUIDANCE_MESSAGE_KEY = BotMessageKey.UNREGISTERED_PHONE


@dataclass(frozen=True, slots=True)
class ReplyPreflightResult:
    action: str
    reason_code: str
    document: CustomerBotDocument | None = None
    customer_error_key: str | None = None

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

    The unregistered-phone guidance is the only reply that may leave without a
    customer id, and only when its stored key and published text still match.
    Every other reply needs one current customer. Document checks read
    eligibility and fingerprints. They do not render a PDF.
    """

    runtime = read_customer_bot_runtime(settings)
    runtime_block = runtime_still_accepts(claimed, settings, runtime=runtime)
    if runtime_block is not None:
        return runtime_block
    if not claimed.destination_id or claimed.destination_id != claimed.conversation_id:
        return ReplyPreflightResult(CANCEL, REASON_DESTINATION_MISMATCH)
    if claimed.message_key == PUBLIC_GUIDANCE_MESSAGE_KEY:
        return _verify_public_guidance(claimed, runtime.published or {})

    if not claimed.customer_id or not claimed.normalized_phone:
        return ReplyPreflightResult(CANCEL, REASON_IDENTITY_CHANGED)
    identity_check = _verify_identity(claimed, directory)
    if identity_check is not None:
        return identity_check

    for spec in claimed.group_document_specs:
        group_check = _verify_document_spec(spec, services)
        if group_check.action == CANCEL:
            return group_check

    if claimed.part_kind == PART_TEXT:
        return ReplyPreflightResult(SEND, "preflight_ok")

    if claimed.part_kind != PART_DOCUMENT:
        return ReplyPreflightResult(CANCEL, REASON_UNSUPPORTED_PART)
    if claimed.document_spec is None:
        return ReplyPreflightResult(CANCEL, REASON_MISSING_SPEC)
    caption_check = _verify_document_caption(claimed.document_spec, runtime.published or {})
    if caption_check is not None:
        return caption_check
    return _verify_document_spec(claimed.document_spec, services)


def runtime_still_accepts(claimed: ClaimedReply, settings: CustomerBotSettingsStore, *, runtime=None):
    """Return a cancel result when the bot or its acceptance cycle changed."""

    current = runtime if runtime is not None else read_customer_bot_runtime(settings)
    if not current.accepting_messages:
        return ReplyPreflightResult(CANCEL, REASON_BOT_DISABLED)
    if claimed.acceptance_epoch is not None and current.acceptance_epoch != claimed.acceptance_epoch:
        return ReplyPreflightResult(CANCEL, REASON_EPOCH_CHANGED)
    return None


def prepare_document_for_send(
    claimed: ClaimedReply,
    services: CustomerBotServicePort,
) -> ReplyPreflightResult:
    """Render the claimed document once and keep the bytes only when they still match."""

    spec = claimed.document_spec
    if spec is None:
        return ReplyPreflightResult(CANCEL, REASON_MISSING_SPEC)
    materialize = getattr(services, "materialize", None)
    if materialize is None:
        return ReplyPreflightResult(CANCEL, REASON_DOCUMENT_UNAVAILABLE)
    try:
        result = materialize(
            CustomerServiceRequest(
                phone=spec.normalized_phone,
                service_id=spec.service_id,
                order_name=spec.order_name,
            )
        )
    except Exception:
        return ReplyPreflightResult(CANCEL, REASON_DOCUMENT_UNAVAILABLE)
    return _assess_service_result(spec, result, require_bytes=True)


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


def _verify_public_guidance(claimed: ClaimedReply, published: dict[str, str]) -> ReplyPreflightResult:
    """Allow only the published unregistered-phone sentence, with no customer facts."""

    if (
        claimed.part_kind != PART_TEXT
        or claimed.customer_id
        or claimed.document_spec is not None
        or claimed.group_document_specs
        or not claimed.normalized_phone
    ):
        return ReplyPreflightResult(CANCEL, REASON_PUBLIC_GUIDANCE_REJECTED)
    try:
        normalized = normalize_customer_phone(claimed.normalized_phone)
    except CustomerPhoneError:
        return ReplyPreflightResult(CANCEL, REASON_PUBLIC_GUIDANCE_REJECTED)
    if normalized != claimed.normalized_phone:
        return ReplyPreflightResult(CANCEL, REASON_PUBLIC_GUIDANCE_REJECTED)
    try:
        lines = render_customer_lines(
            published,
            (BotMessage(BotMessageKey.UNREGISTERED_PHONE),),
        )
    except CustomerTextRenderError:
        return ReplyPreflightResult(CANCEL, REASON_PUBLIC_GUIDANCE_REJECTED)
    if lines != (claimed.body,):
        return ReplyPreflightResult(CANCEL, REASON_PUBLIC_GUIDANCE_REJECTED)
    return ReplyPreflightResult(SEND, "preflight_ok")


def _verify_document_caption(spec: DocumentReplySpec, published: dict[str, str]) -> ReplyPreflightResult | None:
    """The stored caption must still be the current description of this document."""

    if len(spec.caption) > DOCUMENT_CAPTION_MAX:
        try:
            failure = document_failure_message(spec.service_id)
        except ValueError:
            return ReplyPreflightResult(CANCEL, CAPTION_TOO_LONG)
        return ReplyPreflightResult(
            CANCEL,
            CAPTION_TOO_LONG,
            customer_error_key=failure.key,
        )
    if not spec.caption:
        return ReplyPreflightResult(CANCEL, REASON_CAPTION_MISMATCH)
    try:
        expected = customer_outbound_text(
            published,
            document_description_messages(
                spec.service_id,
                spec.order_name,
                spec.amount,
                spec.currency,
            ),
        )
    except (CustomerTextRenderError, ValueError):
        return ReplyPreflightResult(CANCEL, REASON_CAPTION_MISMATCH)
    if expected != spec.caption:
        return ReplyPreflightResult(CANCEL, REASON_CAPTION_MISMATCH)
    return None


def _verify_document_spec(
    spec: DocumentReplySpec,
    services: CustomerBotServicePort,
) -> ReplyPreflightResult:
    result = services.execute(
        CustomerServiceRequest(
            phone=spec.normalized_phone,
            service_id=spec.service_id,
            order_name=spec.order_name,
        )
    )
    return _assess_service_result(spec, result, require_bytes=False)


def _assess_service_result(
    spec: DocumentReplySpec,
    result,
    *,
    require_bytes: bool,
) -> ReplyPreflightResult:
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
        failed = {
            ServiceResultCode.INVOICE_FAILED: BotMessageKey.INVOICE_FAILED,
            ServiceResultCode.PLAN_PDF_FAILED: BotMessageKey.PLAN_PDF_FAILED,
            ServiceResultCode.MEASUREMENTS_PDF_FAILED: BotMessageKey.MEASUREMENTS_PDF_FAILED,
        }.get(result.code)
        if failed:
            return ReplyPreflightResult(
                CANCEL,
                REASON_DOCUMENT_RENDER_FAILED,
                customer_error_key=failed,
            )
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
        if not document.content:
            return ReplyPreflightResult(CANCEL, REASON_DOCUMENT_UNAVAILABLE)
        return ReplyPreflightResult(SEND, "preflight_ok", document=document)
    return ReplyPreflightResult(SEND, "preflight_ok")


__all__ = [
    "CANCEL",
    "REASON_AMOUNT_MISMATCH",
    "REASON_APPROVAL_STALE",
    "REASON_BOT_DISABLED",
    "REASON_CAPTION_MISMATCH",
    "REASON_DOCUMENT_RENDER_FAILED",
    "REASON_DOCUMENT_UNAVAILABLE",
    "REASON_EPOCH_CHANGED",
    "REASON_IDENTITY_CHANGED",
    "REASON_DESTINATION_MISMATCH",
    "REASON_MISSING_SPEC",
    "REASON_ORDER_INELIGIBLE",
    "REASON_PUBLIC_GUIDANCE_REJECTED",
    "REASON_UNSUPPORTED_PART",
    "ReplyPreflightResult",
    "SEND",
    "prepare_document_for_send",
    "runtime_still_accepts",
    "verify_reply_before_send",
]
