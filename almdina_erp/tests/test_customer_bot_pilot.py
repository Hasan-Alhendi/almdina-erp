"""Pilot phone gate and transport cutoff without live WhatsApp."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from almdina_erp.almdina_erp.application.customer_bot.deliver_reply_intents import (
    deliver_pending_replies,
)
from almdina_erp.almdina_erp.domain.customer_bot.reply_intent import PENDING
from almdina_erp.almdina_erp.domain.customer_bot.gateway_capabilities import BotGatewayCapabilities
from almdina_erp.almdina_erp.domain.customer_bot.inbound_message import (
    InboundMessageKind,
    build_inbound_customer_message,
)
from almdina_erp.almdina_erp.domain.customer_bot.phone_number import CustomerPhoneError
from almdina_erp.almdina_erp.domain.customer_bot.session_admission import IGNORED, PROCESSED
from almdina_erp.almdina_erp.domain.customer_bot.text_reply import SendDisposition, TextSendResult
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_pilot import (
    REASON_PILOT_PHONE_MISMATCH,
    REASON_PILOT_TOO_OLD,
    intent_pilot_cancel_reason,
    pilot_transport_may_run,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_reply_delivery import (
    LIVE_REPLY_DELIVERY_ENABLED,
    deliver_customer_bot_replies,
)
from almdina_erp.almdina_erp.infrastructure.whatsapp.customer_bot_pilot_config import (
    CustomerBotPilotConfig,
    parse_pilot_phone,
)
from almdina_erp.tests.customer_bot_session_memory import MemoryCustomerBotSessionStore
from almdina_erp.tests.test_customer_bot_inbound_session import (
    NOW,
    _Clock,
    _Directory,
    _Orders,
    _Routes,
    _Services,
    _Settings,
    _Stages,
    _header,
)
from almdina_erp.almdina_erp.application.customer_bot.accept_inbound_message import (
    accept_inbound_customer_message,
)

PILOT_PHONE = "+963944000001"
OTHER_PHONE = "+963944000002"
FRESH = datetime.now(timezone.utc).replace(microsecond=0)


def _msg(*, phone: str | None, event: str, text: str = "مرحبا", when: datetime | None = None):
    stamp = when if when is not None else FRESH
    return build_inbound_customer_message(
        connection_ref="pilot-conn",
        provider_event_id=event,
        conversation_id="chat-1",
        sender_id="sender-1",
        occurred_at=stamp,
        kind=InboundMessageKind.TEXT,
        text=text,
        from_own_account=False,
        is_group=False,
        trusted_normalized_phone=phone,
    )


class _Gateway:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self._capabilities = BotGatewayCapabilities(
            sends_text=True,
            supports_interactive_options=False,
            supports_idempotent_send=False,
        )

    def capabilities(self) -> BotGatewayCapabilities:
        return self._capabilities

    def send_text_reply(self, request):
        self.calls.append(request.text)
        return TextSendResult(
            reply_id=request.reply_id,
            connection_ref=request.connection_ref,
            destination_id=request.destination_id,
            disposition=SendDisposition.ACCEPTED,
            provider_message_id="wa-1",
            reason_code="gateway_accepted",
        )


class PilotConfigTests(unittest.TestCase):
    def test_parse_requires_valid_e164(self) -> None:
        self.assertEqual(parse_pilot_phone("0944000001"), PILOT_PHONE)
        with self.assertRaises(CustomerPhoneError):
            parse_pilot_phone("not-a-phone")
        with self.assertRaises(CustomerPhoneError):
            parse_pilot_phone("123@c.us")

    def test_admits_only_configured_phone_when_ready(self) -> None:
        started = FRESH
        ready = CustomerBotPilotConfig(
            enabled=True,
            phone_e164=PILOT_PHONE,
            started_at=started,
            transport_armed=True,
        )
        self.assertTrue(ready.is_ready)
        self.assertTrue(ready.admits_phone(PILOT_PHONE))
        self.assertFalse(ready.admits_phone(OTHER_PHONE))
        self.assertFalse(ready.admits_phone(None))
        self.assertTrue(
            ready.admits_intent(normalized_phone=PILOT_PHONE, created_on=started + timedelta(seconds=1))
        )
        self.assertFalse(
            ready.admits_intent(normalized_phone=PILOT_PHONE, created_on=started - timedelta(seconds=1))
        )

    def test_enabled_without_phone_admits_nobody(self) -> None:
        broken = CustomerBotPilotConfig(
            enabled=True,
            phone_e164=None,
            started_at=FRESH,
            transport_armed=True,
        )
        self.assertFalse(broken.is_ready)
        self.assertFalse(broken.admits_phone(PILOT_PHONE))

    def test_live_module_alone_does_not_arm_transport(self) -> None:
        with patch(
            "almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_pilot.load_customer_bot_pilot",
            return_value=CustomerBotPilotConfig(
                enabled=False,
                phone_e164=None,
                started_at=None,
                transport_armed=False,
            ),
        ):
            self.assertFalse(pilot_transport_may_run(live_module_enabled=True))

    def test_armed_without_ready_pilot_does_not_run(self) -> None:
        with patch(
            "almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_pilot.load_customer_bot_pilot",
            return_value=CustomerBotPilotConfig(
                enabled=True,
                phone_e164=None,
                started_at=None,
                transport_armed=True,
            ),
        ):
            self.assertFalse(pilot_transport_may_run(live_module_enabled=False))


class PilotInboundGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = _Clock(FRESH)
        self.sessions = MemoryCustomerBotSessionStore()
        self.settings = _Settings()
        self.directory = _Directory()
        self.directory.matches = {PILOT_PHONE: ("CUST-PILOT",)}

    def test_pilot_phone_reaches_engine_via_gateway_helper(self) -> None:
        from almdina_erp.almdina_erp.infrastructure.frappe import customer_bot_inbound_gateway as gateway

        message = _msg(phone=PILOT_PHONE, event="e-pilot", when=FRESH)
        pilot = CustomerBotPilotConfig(
            enabled=True,
            phone_e164=PILOT_PHONE,
            started_at=FRESH - timedelta(minutes=1),
            transport_armed=False,
        )
        with patch.object(gateway, "load_customer_bot_pilot", return_value=pilot):
            with patch.object(gateway, "FrappeCustomerBotSessionRepository", return_value=self.sessions):
                with patch.object(gateway, "FrappeCustomerBotSettingsRepository", return_value=self.settings):
                    with patch.object(gateway, "FrappeCustomerPhoneDirectory", return_value=self.directory):
                        with patch.object(gateway, "FrappeCustomerOrderReader") as orders_cls:
                            orders = _Orders((_header("DCO-A"),))
                            orders_cls.return_value = orders
                            with patch.object(gateway, "build_customer_bot_services", return_value=_Services()):
                                result = gateway.accept_verified_customer_bot_inbound(message)
        self.assertEqual(result.disposition, PROCESSED)
        self.assertTrue(self.sessions.replies)

    def test_other_phone_is_ignored_without_replies_or_conversation(self) -> None:
        from almdina_erp.almdina_erp.infrastructure.frappe import customer_bot_inbound_gateway as gateway

        message = _msg(phone=OTHER_PHONE, event="e-other", when=FRESH)
        pilot = CustomerBotPilotConfig(
            enabled=True,
            phone_e164=PILOT_PHONE,
            started_at=FRESH - timedelta(minutes=1),
            transport_armed=False,
        )
        with patch.object(gateway, "load_customer_bot_pilot", return_value=pilot):
            with patch.object(gateway, "FrappeCustomerBotSessionRepository", return_value=self.sessions):
                result = gateway.accept_verified_customer_bot_inbound(message)
        self.assertEqual(result.disposition, IGNORED)
        self.assertEqual(self.sessions.conversations, {})
        self.assertEqual(self.sessions.replies, {})
        self.assertIn(("pilot-conn", "e-other"), self.sessions.events)

    def test_untrusted_phone_is_ignored_while_pilot_enabled(self) -> None:
        from almdina_erp.almdina_erp.infrastructure.frappe import customer_bot_inbound_gateway as gateway

        message = _msg(phone=None, event="e-none", when=FRESH)
        pilot = CustomerBotPilotConfig(
            enabled=True,
            phone_e164=PILOT_PHONE,
            started_at=FRESH - timedelta(minutes=1),
            transport_armed=False,
        )
        with patch.object(gateway, "load_customer_bot_pilot", return_value=pilot):
            with patch.object(gateway, "FrappeCustomerBotSessionRepository", return_value=self.sessions):
                result = gateway.accept_verified_customer_bot_inbound(message)
        self.assertEqual(result.disposition, IGNORED)
        self.assertEqual(self.sessions.replies, {})


class PilotDeliveryFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = _Clock(FRESH)
        self.sessions = MemoryCustomerBotSessionStore()
        self.settings = _Settings()
        self.directory = _Directory()
        self.directory.matches = {
            PILOT_PHONE: ("CUST-PILOT",),
            OTHER_PHONE: ("CUST-OTHER",),
        }

    def _seed(self, phone: str, event: str, when: datetime) -> None:
        self.clock.now = when
        outcome = accept_inbound_customer_message(
            _msg(phone=phone, event=event, when=when),
            sessions=self.sessions,
            settings=self.settings,
            directory=self.directory,
            headers=_Orders((_header("DCO-A"),)),
            stages=_Stages(),
            routes=_Routes(),
            services=_Services(),
            now=when,
        )
        self.assertEqual(outcome.disposition, PROCESSED, event)

    def test_claim_skips_other_phone_and_older_intents(self) -> None:
        started = FRESH
        self._seed(OTHER_PHONE, "old-other", started - timedelta(minutes=5))
        self._seed(PILOT_PHONE, "old-pilot", started - timedelta(minutes=5))
        self._seed(PILOT_PHONE, "new-pilot", started + timedelta(minutes=1))
        gateway = _Gateway()
        pilot = CustomerBotPilotConfig(
            enabled=True,
            phone_e164=PILOT_PHONE,
            started_at=started,
            transport_armed=True,
        )

        def cancel_reason(claimed):
            return intent_pilot_cancel_reason(
                pilot,
                normalized_phone=claimed.normalized_phone,
                created_on=claimed.created_on,
            )

        delivered = deliver_pending_replies(
            self.sessions,
            gateway,
            now=started + timedelta(minutes=2),
            eligible_phone=PILOT_PHONE,
            created_not_before=started,
            after_claim_cancel_reason=cancel_reason,
        )
        self.assertTrue(delivered)
        self.assertTrue(gateway.calls)
        # Older / other-phone rows remain pending.
        pending = [row for row in self.sessions.replies.values() if row.status == PENDING]
        self.assertGreaterEqual(len(pending), 1)
        phones = {row.intent.normalized_phone for row in pending}
        self.assertIn(OTHER_PHONE, phones)

    def test_phone_change_blocks_previous_number_intents(self) -> None:
        started = FRESH
        self._seed(PILOT_PHONE, "prev", started + timedelta(seconds=1))
        gateway = _Gateway()
        new_pilot = CustomerBotPilotConfig(
            enabled=True,
            phone_e164=OTHER_PHONE,
            started_at=started,
            transport_armed=True,
        )
        delivered = deliver_pending_replies(
            self.sessions,
            gateway,
            now=started + timedelta(minutes=1),
            eligible_phone=OTHER_PHONE,
            created_not_before=started,
            after_claim_cancel_reason=lambda claimed: intent_pilot_cancel_reason(
                new_pilot,
                normalized_phone=claimed.normalized_phone,
                created_on=claimed.created_on,
            ),
        )
        self.assertEqual(delivered, ())
        self.assertEqual(gateway.calls, [])

    def test_disable_stops_new_transport_claims(self) -> None:
        self.assertFalse(LIVE_REPLY_DELIVERY_ENABLED)
        with patch(
            "almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_pilot.pilot_transport_may_run",
            return_value=False,
        ):
            with patch(
                "almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_openwa_outbound.try_build_customer_bot_openwa_outbound"
            ) as build:
                self.assertEqual(deliver_customer_bot_replies(), 0)
        build.assert_not_called()

    def test_reactivate_does_not_revive_pre_start_intents(self) -> None:
        started = FRESH
        self._seed(PILOT_PHONE, "before", started - timedelta(minutes=10))
        gateway = _Gateway()
        pilot = CustomerBotPilotConfig(
            enabled=True,
            phone_e164=PILOT_PHONE,
            started_at=started,
            transport_armed=True,
        )
        claimed = self.sessions.claim_next(
            now=started + timedelta(seconds=1),
            eligible_phone=PILOT_PHONE,
            created_not_before=started,
        )
        self.assertIsNone(claimed)
        delivered = deliver_pending_replies(
            self.sessions,
            gateway,
            now=started + timedelta(seconds=2),
            eligible_phone=PILOT_PHONE,
            created_not_before=started,
            after_claim_cancel_reason=lambda row: intent_pilot_cancel_reason(
                pilot,
                normalized_phone=row.normalized_phone,
                created_on=row.created_on,
            ),
        )
        self.assertEqual(delivered, ())
        self.assertEqual(gateway.calls, [])
        pending = [row for row in self.sessions.replies.values() if row.status == PENDING]
        self.assertTrue(pending)
        self.assertEqual(
            intent_pilot_cancel_reason(
                pilot,
                normalized_phone=OTHER_PHONE,
                created_on=started + timedelta(seconds=1),
            ),
            REASON_PILOT_PHONE_MISMATCH,
        )
        self.assertEqual(
            intent_pilot_cancel_reason(
                pilot,
                normalized_phone=PILOT_PHONE,
                created_on=started - timedelta(minutes=10),
            ),
            REASON_PILOT_TOO_OLD,
        )


class LegacySendIsolationTests(unittest.TestCase):
    def test_factory_whatsapp_modules_do_not_import_pilot(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        paths = [
            root / "almdina_erp/services/whatsapp_service.py",
            root / "almdina_erp/infrastructure/whatsapp/openwa_client.py",
        ]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("customer_bot_pilot", text)
            self.assertNotIn("LIVE_REPLY_DELIVERY_ENABLED", text)


if __name__ == "__main__":
    unittest.main()
