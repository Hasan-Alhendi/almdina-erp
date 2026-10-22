"""Production entry for reply delivery and scheduled recovery.

Live sending stays off. The scheduled tick always recovers abandoned claims
and always looks at pending rows. While the flag is off it does not construct
a gateway client, does not read API keys, and does not send.
"""

from __future__ import annotations

from datetime import datetime

from almdina_erp.almdina_erp.application.customer_bot.ports import BotTextReplyPort

LIVE_REPLY_DELIVERY_ENABLED = False


def deliver_customer_bot_replies(
    *,
    port: BotTextReplyPort | None = None,
    limit: int = 20,
    now: datetime | None = None,
) -> int:
    """Hand pending replies to ``port`` only when live delivery is enabled.

    The durable guarantee is the outbox row plus the scheduled tick, not a
    queue job. Recovery of abandoned claims does not need a port. When the
    live flag is off this returns immediately without building OpenWA ports.
    """

    if not LIVE_REPLY_DELIVERY_ENABLED:
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
    steps = deliver_pending_replies(
        FrappeCustomerBotReplyRepository(),
        port,
        limit=limit,
        now=now,
        deps=deps,
    )
    return len(steps)


def scheduled_customer_bot_reply_tick() -> dict[str, int]:
    """Durable scan: abandon stale claims, then try live delivery if enabled.

    Registered under ``scheduler_events``. When live delivery is off this
    recovers abandoned ``processing`` rows to ``unknown`` and returns without
    building an OpenWA client or reading credentials.
    """

    from almdina_erp.almdina_erp.application.customer_bot.deliver_reply_intents import (
        recover_abandoned_reply_claims,
    )
    from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_reply_repository import (
        FrappeCustomerBotReplyRepository,
    )

    outbox = FrappeCustomerBotReplyRepository()
    abandoned = recover_abandoned_reply_claims(outbox)
    sent = deliver_customer_bot_replies()
    return {"abandoned": abandoned, "sent": sent}


__all__ = [
    "LIVE_REPLY_DELIVERY_ENABLED",
    "deliver_customer_bot_replies",
    "scheduled_customer_bot_reply_tick",
]
