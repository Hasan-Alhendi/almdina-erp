"""Build live customer-bot OpenWA reply ports from server settings only.

Never call this while ``LIVE_REPLY_DELIVERY_ENABLED`` is False. The factory
reads the bot session id and connection ref from Customer Bot Settings and the
gateway URL/API key from process OpenWA config. Client message bodies never
supply those values.
"""

from __future__ import annotations

from dataclasses import dataclass

from almdina_erp.almdina_erp.infrastructure.whatsapp.customer_bot_openwa_reply import (
    OpenWACustomerBotReply,
)


@dataclass(frozen=True, slots=True)
class CustomerBotOpenWAOutboundBundle:
    reply: OpenWACustomerBotReply
    session_id: str
    connection_ref: str


def try_build_customer_bot_openwa_outbound(
    *,
    live_enabled: bool,
) -> CustomerBotOpenWAOutboundBundle | None:
    """Return a ready adapter only when live delivery is explicitly enabled.

    When ``live_enabled`` is False this returns None without reading secrets or
    constructing a transport that can open a socket.
    """

    if not live_enabled:
        return None
    # Frappe and OpenWA loaders stay behind the live gate so unit tests can
    # import this module without a site and without opening a socket.
    from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_inbound_connection import (
        load_openwa_inbound_connection,
    )
    from almdina_erp.almdina_erp.infrastructure.whatsapp.config import load_openwa_config
    from almdina_erp.almdina_erp.infrastructure.whatsapp.customer_bot_openwa_http_transport import (
        UrlOpenCustomerBotOpenWATransport,
    )

    connection = load_openwa_inbound_connection()
    if connection is None:
        return None
    config = load_openwa_config()
    if not config.configured:
        return None
    transport = UrlOpenCustomerBotOpenWATransport(config)
    reply = OpenWACustomerBotReply(
        transport,
        session_id=connection.session_id,
        connection_ref=connection.connection_ref,
    )
    return CustomerBotOpenWAOutboundBundle(
        reply=reply,
        session_id=connection.session_id,
        connection_ref=connection.connection_ref,
    )


__all__ = [
    "CustomerBotOpenWAOutboundBundle",
    "try_build_customer_bot_openwa_outbound",
]
