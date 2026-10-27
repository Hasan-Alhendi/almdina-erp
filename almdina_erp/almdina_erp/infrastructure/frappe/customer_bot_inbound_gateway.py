"""Wire a verified inbound event into the existing accept/outbox path.

This module does not send WhatsApp replies inside the webhook request. Live
delivery stays gated by server-side ops mode plus transport arm /
``customer_bot_transport_live``. Durable reply intents are inserted inside the
same accept transaction used by the session store. After that commit succeeds,
a background job is enqueued (``enqueue_after_commit``) to run the shared
outbox delivery path; enqueue failure leaves pending rows for the scheduled
recovery tick.

Ops mode:

- ``off``: no operational accept and no transport (terminal ``not_accepting``).
- ``pilot``: only the configured E.164 may reach the conversation engine.
- ``production``: every trusted gateway phone may reach the engine; identity
  still resolves from ``Customer.mobile_no`` only.

Authentication, HMAC, and session matching stay in the HTTP service.
"""

from __future__ import annotations

from datetime import datetime, timezone

from almdina_erp.almdina_erp.application.customer_bot.accept_inbound_message import (
    InboundAcceptance,
    accept_inbound_customer_message,
)
from almdina_erp.almdina_erp.domain.customer_bot.inbound_message import InboundCustomerMessage
from almdina_erp.almdina_erp.domain.customer_bot.session_admission import (
    IGNORED,
    NOT_ACCEPTING,
    event_fingerprint,
    with_fitted_session_keys,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_operation_runtime import (
    current_operation_generation,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_ops import (
    load_customer_bot_ops,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_order_reader import (
    FrappeCustomerOrderReader,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_reply_delivery import (
    enqueue_customer_bot_reply_delivery,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_services import (
    build_customer_bot_services,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_session_repository import (
    FrappeCustomerBotSessionRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_settings_repository import (
    FrappeCustomerBotSettingsRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_phone_directory import (
    FrappeCustomerPhoneDirectory,
)
from almdina_erp.almdina_erp.infrastructure.whatsapp.customer_bot_ops_config import (
    OPS_MODE_OFF,
)


def accept_verified_customer_bot_inbound(message: InboundCustomerMessage) -> InboundAcceptance:
    """Persist one trusted inbound event through the existing acceptance use case."""

    message = with_fitted_session_keys(message)
    sessions = FrappeCustomerBotSessionRepository()
    ops = load_customer_bot_ops()

    if ops.mode == OPS_MODE_OFF or not ops.is_ready:
        outcome = sessions.note_terminal(
            connection_ref=message.connection_ref,
            provider_event_id=message.provider_event_id,
            fingerprint=event_fingerprint(message),
            outcome=NOT_ACCEPTING,
            now=datetime.now(timezone.utc),
        )
        return InboundAcceptance(outcome)

    if not ops.admits_inbound_phone(message.normalized_phone):
        # Fail closed: no engine, no order reads, no reply intents, no new
        # conversation lease. Event row only (terminal ignore).
        outcome = sessions.note_terminal(
            connection_ref=message.connection_ref,
            provider_event_id=message.provider_event_id,
            fingerprint=event_fingerprint(message),
            outcome=IGNORED,
            now=datetime.now(timezone.utc),
        )
        return InboundAcceptance(outcome)

    connection_ref = message.connection_ref
    provider_event_id = message.provider_event_id

    def _after_replies_committed(_count: int) -> None:
        # Intents are already committed by complete_turn. Enqueue is best-effort;
        # never raise into the webhook after a successful accept.
        enqueue_customer_bot_reply_delivery(
            connection_ref=connection_ref,
            provider_event_id=provider_event_id,
        )

    orders = FrappeCustomerOrderReader()
    return accept_inbound_customer_message(
        message,
        sessions=sessions,
        settings=FrappeCustomerBotSettingsRepository(),
        directory=FrappeCustomerPhoneDirectory(),
        headers=orders,
        stages=orders,
        routes=orders,
        services=build_customer_bot_services(),
        operation_generation=current_operation_generation(),
        on_replies_committed=_after_replies_committed,
    )


__all__ = ["accept_verified_customer_bot_inbound"]
