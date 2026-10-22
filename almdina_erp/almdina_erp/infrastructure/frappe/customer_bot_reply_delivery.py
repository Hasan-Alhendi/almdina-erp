"""Production entry for reply delivery and scheduled recovery.

Live sending stays off. The scheduled tick always recovers abandoned claims
and always looks at pending rows. While the flag is off it does not construct
a gateway client and does not send.
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
    queue job. Recovery of abandoned claims does not need a port.
    """

    if not LIVE_REPLY_DELIVERY_ENABLED or port is None:
        return 0
    from almdina_erp.almdina_erp.application.customer_bot.deliver_reply_intents import (
        deliver_pending_replies,
    )
    from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_reply_repository import (
        FrappeCustomerBotReplyRepository,
    )

    steps = deliver_pending_replies(
        FrappeCustomerBotReplyRepository(),
        port,
        limit=limit,
        now=now,
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
