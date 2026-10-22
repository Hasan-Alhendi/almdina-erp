"""Production entry for reply delivery, immediate enqueue, and scheduled recovery.

Live sending stays off by default. After inbound acceptance commits reply intents,
``enqueue_customer_bot_reply_delivery`` schedules the same delivery path on a
background worker (``frappe.enqueue`` + ``enqueue_after_commit``). The minute
cron tick remains the durable recovery / backlog drain: Frappe's default
scheduler wake interval is four minutes, so the cron alone is not the primary
send path.

While transport is not armed the delivery entry does not construct a gateway
client, does not read API keys, and does not send. Transport also requires a
ready server-side ops mode (pilot phone + start cutoff, or production start
cutoff). The module constant ``LIVE_REPLY_DELIVERY_ENABLED`` stays ``False``;
use site ``customer_bot_transport_live`` or the transport arm flag instead.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from almdina_erp.almdina_erp.application.customer_bot.ports import BotTextReplyPort
from almdina_erp.almdina_erp.application.customer_bot.reply_outbox import ClaimedReply

# Deprecated code kill-switch. Keep False; prefer site_config transport flags.
LIVE_REPLY_DELIVERY_ENABLED = False

_DELIVERY_JOB_METHOD = (
    "almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_reply_delivery"
    ".run_customer_bot_reply_delivery_job"
)
_DELIVERY_QUEUE = "default"
_DELIVERY_TIMEOUT_SEC = 300


def deliver_customer_bot_replies(
    *,
    port: BotTextReplyPort | None = None,
    limit: int = 20,
    now: datetime | None = None,
) -> int:
    """Hand pending replies to ``port`` only when live delivery is armed.

    Used by the immediate RQ job and by the scheduled recovery tick. Claim
    locking + sequence gates prevent duplicate sends when both run together.
    When the ops/transport gate is off this returns immediately without
    building OpenWA ports.
    """

    from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_ops import (
        intent_ops_cancel_reason,
        load_customer_bot_ops,
        ops_transport_may_run,
    )

    if not ops_transport_may_run(live_module_enabled=LIVE_REPLY_DELIVERY_ENABLED):
        return 0
    ops = load_customer_bot_ops()
    if not ops.is_ready or ops.started_at is None:
        return 0

    from almdina_erp.almdina_erp.application.customer_bot.deliver_reply_intents import (
        ReplyDeliveryDeps,
        deliver_pending_replies,
    )
    from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_openwa_outbound import (
        try_build_customer_bot_openwa_outbound,
    )
    from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_reply_repository import (
        FrappeCustomerBotReplyRepository,
    )
    from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_services import (
        build_customer_bot_services,
    )
    from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_settings_repository import (
        FrappeCustomerBotSettingsRepository,
    )
    from almdina_erp.almdina_erp.infrastructure.frappe.customer_phone_directory import (
        FrappeCustomerPhoneDirectory,
    )

    deps: ReplyDeliveryDeps | None = None
    if port is None:
        bundle = try_build_customer_bot_openwa_outbound(live_enabled=True)
        if bundle is None:
            return 0
        port = bundle.reply
        deps = ReplyDeliveryDeps(
            settings=FrappeCustomerBotSettingsRepository(),
            directory=FrappeCustomerPhoneDirectory(),
            services=build_customer_bot_services(),
            document_port=bundle.reply,
        )

    def _ops_recheck(claimed: ClaimedReply) -> str | None:
        from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_ops import (
            REASON_OPS_INACTIVE,
        )

        if not ops_transport_may_run(live_module_enabled=LIVE_REPLY_DELIVERY_ENABLED):
            return REASON_OPS_INACTIVE
        current = load_customer_bot_ops()
        return intent_ops_cancel_reason(
            current,
            normalized_phone=claimed.normalized_phone,
            created_on=claimed.created_on,
        )

    steps = deliver_pending_replies(
        FrappeCustomerBotReplyRepository(),
        port,
        limit=limit,
        now=now,
        deps=deps,
        eligible_phone=ops.claim_eligible_phone,
        created_not_before=ops.started_at,
        after_claim_cancel_reason=_ops_recheck,
    )
    return len(steps)


def run_customer_bot_reply_delivery_job() -> dict[str, int]:
    """RQ worker entry: recover abandoned claims, then deliver if transport may run."""

    from almdina_erp.almdina_erp.application.customer_bot.deliver_reply_intents import (
        recover_abandoned_reply_claims,
    )
    from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_reply_repository import (
        FrappeCustomerBotReplyRepository,
    )

    abandoned = recover_abandoned_reply_claims(FrappeCustomerBotReplyRepository())
    sent = deliver_customer_bot_replies()
    return {"abandoned": abandoned, "sent": sent}


def enqueue_customer_bot_reply_delivery(
    *,
    connection_ref: str,
    provider_event_id: str,
) -> bool:
    """Queue immediate delivery after the surrounding DB transaction commits.

    Must not run inside the webhook request body or inside the accept
    transaction. Call only after reply intents are durable. Returns ``False``
    when enqueue fails; pending rows stay for the scheduled tick. Never raises
    for Redis/queue errors so inbound acceptance stays ``processed``.
    """

    ref = str(connection_ref or "").strip()
    event_id = str(provider_event_id or "").strip()
    if not ref or not event_id:
        return False

    import frappe

    job_id = _delivery_job_id(ref, event_id)
    try:
        frappe.enqueue(
            _DELIVERY_JOB_METHOD,
            queue=_DELIVERY_QUEUE,
            timeout=_DELIVERY_TIMEOUT_SEC,
            enqueue_after_commit=True,
            job_id=job_id,
            deduplicate=True,
        )
    except Exception:
        try:
            frappe.log_error(
                title="customer bot reply delivery enqueue failed",
                message=f"connection_ref={ref!r} provider_event_id_len={len(event_id)}",
            )
        except Exception:
            pass
        return False
    return True


def scheduled_customer_bot_reply_tick() -> dict[str, int]:
    """Durable recovery tick: abandon stale claims, then drain pending if armed.

    Not the primary send path after inbound accept (see
    ``enqueue_customer_bot_reply_delivery``). Keeps backlog moving when enqueue
    fails or the worker was down. When transport is off this recovers abandoned
    ``processing`` rows to ``unknown`` without building an OpenWA client.
    """

    return run_customer_bot_reply_delivery_job()


def _delivery_job_id(connection_ref: str, provider_event_id: str) -> str:
    material = f"{connection_ref}\n{provider_event_id}".encode("utf-8")
    digest = hashlib.sha256(material).hexdigest()[:24]
    return f"almdina-cbot-reply-{digest}"


__all__ = [
    "LIVE_REPLY_DELIVERY_ENABLED",
    "deliver_customer_bot_replies",
    "enqueue_customer_bot_reply_delivery",
    "run_customer_bot_reply_delivery_job",
    "scheduled_customer_bot_reply_tick",
]
