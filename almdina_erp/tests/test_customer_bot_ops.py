"""Ops modes off/pilot/production for accept and transport gates."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from almdina_erp.almdina_erp.application.customer_bot.accept_inbound_message import (
    accept_inbound_customer_message,
)
from almdina_erp.almdina_erp.application.customer_bot.deliver_reply_intents import (
    ReplyDeliveryDeps,
    deliver_pending_replies,
)
from almdina_erp.almdina_erp.application.customer_bot.verify_reply_before_send import (
    REASON_BOT_DISABLED,
)
from almdina_erp.almdina_erp.domain.customer_bot.gateway_capabilities import BotGatewayCapabilities
from almdina_erp.almdina_erp.domain.customer_bot.inbound_message import (
    InboundMessageKind,
    build_inbound_customer_message,
)
from almdina_erp.almdina_erp.domain.customer_bot.conversation import BotMessageKey
from almdina_erp.almdina_erp.domain.customer_bot.reply_intent import CANCELLED, PENDING
from almdina_erp.almdina_erp.domain.customer_bot.session_admission import (
    IGNORED,
    NOT_ACCEPTING,
    PROCESSED,
)
from almdina_erp.almdina_erp.domain.customer_bot.text_reply import SendDisposition, TextSendResult
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_ops import (
    intent_ops_cancel_reason,
    load_customer_bot_ops,
    ops_transport_may_run,
    resolve_ops_mode,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_reply_delivery import (
    LIVE_REPLY_DELIVERY_ENABLED,
    deliver_customer_bot_replies,
)
from almdina_erp.almdina_erp.infrastructure.whatsapp.customer_bot_ops_config import (
    OPS_MODE_OFF,
    OPS_MODE_PILOT,
    OPS_MODE_PRODUCTION,
    CustomerBotOpsConfig,
)
from almdina_erp.tests.customer_bot_session_memory import MemoryCustomerBotSessionStore
from almdina_erp.tests.test_customer_bot_inbound_session import (
    _Clock,
    _Directory,
    _Orders,
    _Routes,
    _Services,
    _Settings,
    _Stages,
    _header,
)

PHONE_A = "+963944000001"
PHONE_B = "+963944000002"
UNKNOWN = "+963944000099"
FRESH = datetime.now(timezone.utc).replace(microsecond=0)


def _msg(
    *,
    phone: str | None,
    event: str,
    text: str = "مرحبا",
    when: datetime | None = None,
    conversation_id: str | None = None,
    sender_id: str | None = None,
):
    stamp = when if when is not None else FRESH
    chat = conversation_id or f"chat-{phone or 'none'}"
    sender = sender_id or f"sender-{phone or 'none'}"
    return build_inbound_customer_message(
        connection_ref="ops-conn",
        provider_event_id=event,
        conversation_id=chat,
        sender_id=sender,
        occurred_at=stamp,
        kind=InboundMessageKind.TEXT,
        text=text,
        from_own_account=False,
        is_group=False,
        trusted_normalized_phone=phone,
    )


def _ops(
    *,
    mode: str,
    phone: str | None = PHONE_A,
    started: datetime | None = None,
    armed: bool = False,
    live: bool = False,
) -> CustomerBotOpsConfig:
    return CustomerBotOpsConfig(
        mode=mode,
        pilot_phone_e164=phone,
        started_at=started if started is not None else FRESH - timedelta(minutes=1),
        transport_armed=armed,
        transport_live=live,
    )


class _Gateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self._capabilities = BotGatewayCapabilities(
            sends_text=True,
            supports_interactive_options=False,
            supports_idempotent_send=False,
        )

    def capabilities(self) -> BotGatewayCapabilities:
        return self._capabilities

    def send_text_reply(self, request):
        self.calls.append((request.destination_id, request.text))
        return TextSendResult(
            reply_id=request.reply_id,
            connection_ref=request.connection_ref,
            destination_id=request.destination_id,
            disposition=SendDisposition.ACCEPTED,
            provider_message_id="wa-1",
            reason_code="gateway_accepted",
        )


class ResolveModeTests(unittest.TestCase):
    def test_missing_defaults_to_off(self) -> None:
        self.assertEqual(resolve_ops_mode({}), OPS_MODE_OFF)

    def test_legacy_pilot_enabled_maps_to_pilot(self) -> None:
        self.assertEqual(
            resolve_ops_mode({"customer_bot_pilot_enabled": 1}),
            OPS_MODE_PILOT,
        )

    def test_incomplete_pilot_does_not_become_production(self) -> None:
        self.assertEqual(
            resolve_ops_mode(
                {
                    "customer_bot_pilot_enabled": 1,
                    "customer_bot_pilot_phone_e164": "",
                }
            ),
            OPS_MODE_PILOT,
        )
        self.assertNotEqual(resolve_ops_mode({}), OPS_MODE_PRODUCTION)

    def test_explicit_mode_wins(self) -> None:
        self.assertEqual(
            resolve_ops_mode(
                {
                    "customer_bot_ops_mode": "off",
                    "customer_bot_pilot_enabled": 1,
                }
            ),
            OPS_MODE_OFF,
        )

    def test_invalid_ops_mode_fails_closed_to_off_not_production(self) -> None:
        for raw in ("", "prod", "live", "all", "1", "true", "PRODUCTION_OPEN"):
            self.assertEqual(resolve_ops_mode({"customer_bot_ops_mode": raw}), OPS_MODE_OFF, raw)
            self.assertNotEqual(resolve_ops_mode({"customer_bot_ops_mode": raw}), OPS_MODE_PRODUCTION)

    def test_production_without_started_at_is_not_ready(self) -> None:
        ops = CustomerBotOpsConfig(
            mode=OPS_MODE_PRODUCTION,
            pilot_phone_e164=None,
            started_at=None,
            transport_armed=True,
            transport_live=True,
        )
        self.assertFalse(ops.is_ready)
        self.assertFalse(ops.admits_inbound_phone(PHONE_A))
        with patch(
            "almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_ops.load_customer_bot_ops",
            return_value=ops,
        ):
            self.assertFalse(ops_transport_may_run(live_module_enabled=True))

    def test_load_ops_production_without_stamp_stays_unready(self) -> None:
        conf = {
            "customer_bot_ops_mode": "production",
            "customer_bot_pilot_started_at": "2020-01-01T00:00:00Z",
            "customer_bot_transport_armed": 1,
        }
        with patch(
            "almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_ops._conf_mapping",
            return_value=conf,
        ):
            ops = load_customer_bot_ops()
        self.assertEqual(ops.mode, OPS_MODE_PRODUCTION)
        self.assertIsNone(ops.started_at)
        self.assertFalse(ops.is_ready)


class TransportGateTests(unittest.TestCase):
    def test_off_blocks_transport(self) -> None:
        with patch(
            "almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_ops.load_customer_bot_ops",
            return_value=_ops(mode=OPS_MODE_OFF, armed=True, live=True),
        ):
            self.assertFalse(ops_transport_may_run(live_module_enabled=True))

    def test_pilot_requires_ready_and_arm(self) -> None:
        with patch(
            "almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_ops.load_customer_bot_ops",
            return_value=_ops(mode=OPS_MODE_PILOT, phone=None, armed=True),
        ):
            self.assertFalse(ops_transport_may_run(live_module_enabled=False))
        with patch(
            "almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_ops.load_customer_bot_ops",
            return_value=_ops(mode=OPS_MODE_PILOT, armed=False, live=False),
        ):
            self.assertFalse(ops_transport_may_run(live_module_enabled=False))
        with patch(
            "almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_ops.load_customer_bot_ops",
            return_value=_ops(mode=OPS_MODE_PILOT, armed=True),
        ):
            self.assertTrue(ops_transport_may_run(live_module_enabled=False))

    def test_production_ready_with_server_arm(self) -> None:
        self.assertFalse(LIVE_REPLY_DELIVERY_ENABLED)
        with patch(
            "almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_ops.load_customer_bot_ops",
            return_value=_ops(mode=OPS_MODE_PRODUCTION, phone=None, armed=True),
        ):
            self.assertTrue(ops_transport_may_run(live_module_enabled=False))

    def test_transport_live_site_flag_arms_without_code_edit(self) -> None:
        with patch(
            "almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_ops.load_customer_bot_ops",
            return_value=_ops(mode=OPS_MODE_PRODUCTION, phone=None, armed=False, live=True),
        ):
            self.assertTrue(ops_transport_may_run(live_module_enabled=False))


class OpsInboundGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = _Clock(FRESH)
        self.sessions = MemoryCustomerBotSessionStore()
        self.settings = _Settings()
        self.directory = _Directory()
        self.directory.matches = {
            PHONE_A: ("CUST-A",),
            PHONE_B: ("CUST-B",),
        }

    def _run(self, message, ops: CustomerBotOpsConfig):
        from almdina_erp.almdina_erp.infrastructure.frappe import customer_bot_inbound_gateway as gateway

        with patch.object(gateway, "load_customer_bot_ops", return_value=ops):
            with patch.object(gateway, "FrappeCustomerBotSessionRepository", return_value=self.sessions):
                with patch.object(
                    gateway, "FrappeCustomerBotSettingsRepository", return_value=self.settings
                ):
                    with patch.object(
                        gateway, "FrappeCustomerPhoneDirectory", return_value=self.directory
                    ):
                        with patch.object(gateway, "FrappeCustomerOrderReader") as orders_cls:
                            orders = _Orders((_header("DCO-A"),))
                            orders_cls.return_value = orders
                            with patch.object(
                                gateway, "build_customer_bot_services", return_value=_Services()
                            ):
                                return gateway.accept_verified_customer_bot_inbound(message)

    def test_off_rejects_accept_and_creates_no_replies(self) -> None:
        result = self._run(_msg(phone=PHONE_A, event="e-off"), _ops(mode=OPS_MODE_OFF, armed=True))
        self.assertEqual(result.disposition, NOT_ACCEPTING)
        self.assertEqual(self.sessions.replies, {})
        self.assertEqual(self.sessions.conversations, {})

    def test_pilot_stays_single_phone(self) -> None:
        ops = _ops(mode=OPS_MODE_PILOT, phone=PHONE_A)
        ok = self._run(_msg(phone=PHONE_A, event="e-pilot-a"), ops)
        self.assertEqual(ok.disposition, PROCESSED)
        ignored = self._run(_msg(phone=PHONE_B, event="e-pilot-b"), ops)
        self.assertEqual(ignored.disposition, IGNORED)

    def test_production_two_customers_own_orders_only_foreign_hidden(self) -> None:
        """Each trusted phone sees only its Customer.mobile_no orders; foreign name leaks nothing."""

        shared = _Orders(
            (
                _header("DCO-A1", customer="CUST-A"),
                _header("DCO-A2", customer="CUST-A"),
                _header("DCO-OWN-B", customer="CUST-B"),
            )
        )
        when = FRESH

        def _turn(phone: str, event: str, text: str, sessions):
            return accept_inbound_customer_message(
                _msg(phone=phone, event=event, text=text, when=when),
                sessions=sessions,
                settings=self.settings,
                directory=self.directory,
                headers=shared,
                stages=_Stages(),
                routes=_Routes(),
                services=_Services(),
                now=when,
            )

        sessions_a = MemoryCustomerBotSessionStore()
        welcome_a = _turn(PHONE_A, "iso-a-hi", "مرحبا", sessions_a)
        menu_a = _turn(PHONE_A, "iso-a-1", "1", sessions_a)
        self.assertEqual(welcome_a.disposition, PROCESSED)
        self.assertEqual(menu_a.disposition, PROCESSED)
        self.assertEqual(menu_a.messages[-1].key, BotMessageKey.ASK_ORDER_NUMBER)
        listed = repr(menu_a.messages)
        self.assertIn("DCO-A1", listed)
        self.assertIn("DCO-A2", listed)
        self.assertNotIn("DCO-OWN-B", listed)
        self.assertNotIn("CUST-B", listed)

        foreign = _turn(PHONE_A, "iso-a-foreign", "DCO-OWN-B", sessions_a)
        self.assertEqual(foreign.disposition, PROCESSED)
        self.assertEqual(foreign.messages[0].key, BotMessageKey.ORDER_NOT_FOUND)
        self.assertEqual(foreign.documents, ())
        self.assertNotIn("CUST-B", repr(foreign.messages))

        own = _turn(PHONE_A, "iso-a-own", "DCO-A1", sessions_a)
        self.assertEqual(own.messages[0].key, BotMessageKey.ORDER_STATUS)
        self.assertEqual(dict(own.messages[0].parameters)["order_name"], "DCO-A1")
        self.assertNotIn("DCO-OWN-B", repr(own.messages))

        sessions_b = MemoryCustomerBotSessionStore()
        welcome_b = _turn(PHONE_B, "iso-b-hi", "مرحبا", sessions_b)
        status_b = _turn(PHONE_B, "iso-b-1", "1", sessions_b)
        self.assertEqual(welcome_b.disposition, PROCESSED)
        self.assertEqual(status_b.messages[0].key, BotMessageKey.ORDER_STATUS)
        self.assertEqual(dict(status_b.messages[0].parameters)["order_name"], "DCO-OWN-B")
        self.assertNotIn("DCO-A1", repr(status_b.messages))
        self.assertNotIn("DCO-A2", repr(status_b.messages))

    def test_unknown_gets_general_reply_without_order_data(self) -> None:
        ops = _ops(mode=OPS_MODE_PRODUCTION, phone=None)
        result = self._run(_msg(phone=UNKNOWN, event="e-unknown"), ops)
        self.assertEqual(result.disposition, PROCESSED)
        self.assertEqual(result.messages[0].key, BotMessageKey.UNREGISTERED_PHONE)
        self.assertEqual(result.messages[0].parameters, ())
        self.assertEqual(result.documents, ())
        self.assertTrue(self.sessions.replies)
        for row in self.sessions.replies.values():
            self.assertIsNone(row.intent.customer_id)
            self.assertNotIn("DCO-", row.intent.body)

    def test_untrusted_phone_is_ignored_not_general_reply(self) -> None:
        """No trusted senderPhone → ignore. Never invent identity from @lid / contact."""

        ops = _ops(mode=OPS_MODE_PRODUCTION, phone=None)
        result = self._run(_msg(phone=None, event="e-no-phone"), ops)
        self.assertEqual(result.disposition, IGNORED)
        self.assertEqual(result.messages, ())
        self.assertEqual(self.sessions.replies, {})

    def test_lab_disabled_blocks_engine_in_production(self) -> None:
        self.settings.enabled = False
        ops = _ops(mode=OPS_MODE_PRODUCTION, phone=None)
        result = self._run(_msg(phone=PHONE_A, event="e-lab-off"), ops)
        self.assertEqual(result.disposition, NOT_ACCEPTING)
        self.assertEqual(self.sessions.replies, {})


class OpsDeliveryFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = _Clock(FRESH)
        self.sessions = MemoryCustomerBotSessionStore()
        self.settings = _Settings()
        self.directory = _Directory()
        self.directory.matches = {
            PHONE_A: ("CUST-A",),
            PHONE_B: ("CUST-B",),
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

    def _deliver(self, ops: CustomerBotOpsConfig, gateway: _Gateway, *, deps=None):
        return deliver_pending_replies(
            self.sessions,
            gateway,
            now=(ops.started_at or FRESH) + timedelta(minutes=1),
            limit=20,
            deps=deps,
            eligible_phone=ops.claim_eligible_phone,
            created_not_before=ops.started_at,
            after_claim_cancel_reason=lambda claimed: intent_ops_cancel_reason(
                ops,
                normalized_phone=claimed.normalized_phone,
                created_on=claimed.created_on,
            ),
        )

    def test_pilot_to_production_blocks_prior_pilot_intents(self) -> None:
        pilot_start = FRESH - timedelta(hours=1)
        self._seed(PHONE_A, "pilot-era", pilot_start + timedelta(minutes=1))
        gateway = _Gateway()
        production = _ops(mode=OPS_MODE_PRODUCTION, phone=None, started=FRESH, armed=True)
        delivered = self._deliver(production, gateway)
        self.assertEqual(delivered, ())
        self.assertEqual(gateway.calls, [])
        pending = [row for row in self.sessions.replies.values() if row.status == PENDING]
        self.assertTrue(pending)
        self.assertIsNotNone(
            intent_ops_cancel_reason(
                production,
                normalized_phone=PHONE_A,
                created_on=pilot_start + timedelta(minutes=1),
            )
        )

    def test_connection_change_cutoff_blocks_prior_intents(self) -> None:
        before = FRESH - timedelta(minutes=5)
        self._seed(PHONE_A, "pre-conn", before)
        gateway = _Gateway()
        after_reconnect = _ops(mode=OPS_MODE_PRODUCTION, phone=None, started=FRESH, armed=True)
        delivered = self._deliver(after_reconnect, gateway)
        self.assertEqual(delivered, ())
        self.assertEqual(gateway.calls, [])

    def test_stop_then_restart_blocks_intents_from_previous_cycle(self) -> None:
        first_cycle = FRESH - timedelta(minutes=30)
        self._seed(PHONE_A, "pre-stop", first_cycle)
        gateway = _Gateway()
        restarted = _ops(mode=OPS_MODE_PRODUCTION, phone=None, started=FRESH, armed=True, live=True)
        delivered = self._deliver(restarted, gateway)
        self.assertEqual(delivered, ())
        self.assertEqual(gateway.calls, [])

    def test_lab_ui_disable_cancels_send_despite_transport_live_or_armed(self) -> None:
        started = FRESH
        self._seed(PHONE_A, "lab-live", started + timedelta(seconds=1))
        self.settings.enabled = False
        gateway = _Gateway()
        ops = _ops(mode=OPS_MODE_PRODUCTION, phone=None, started=started, armed=True, live=True)
        with patch(
            "almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_ops.load_customer_bot_ops",
            return_value=ops,
        ):
            self.assertTrue(ops_transport_may_run(live_module_enabled=False))
        deps = ReplyDeliveryDeps(
            settings=self.settings,
            directory=self.directory,
            services=_Services(),
        )
        delivered = self._deliver(ops, gateway, deps=deps)
        self.assertTrue(delivered)
        self.assertEqual(gateway.calls, [])
        cancelled = [row for row in self.sessions.replies.values() if row.status == CANCELLED]
        self.assertTrue(cancelled)
        self.assertEqual(cancelled[0].reason_code, REASON_BOT_DISABLED)

    def test_production_delivers_two_phones_via_fake_port(self) -> None:
        started = FRESH
        self._seed(PHONE_A, "prod-a", started + timedelta(seconds=1))
        self._seed(PHONE_B, "prod-b", started + timedelta(seconds=2))
        gateway = _Gateway()
        ops = _ops(mode=OPS_MODE_PRODUCTION, phone=None, started=started, armed=True)
        delivered = self._deliver(ops, gateway)
        self.assertGreaterEqual(len(delivered), 2)
        self.assertTrue(gateway.calls)

    def test_disable_transport_stops_outbound_build(self) -> None:
        with patch(
            "almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_ops.ops_transport_may_run",
            return_value=False,
        ):
            with patch(
                "almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_openwa_outbound.try_build_customer_bot_openwa_outbound"
            ) as build:
                self.assertEqual(deliver_customer_bot_replies(), 0)
        build.assert_not_called()


class LegacySendIsolationTests(unittest.TestCase):
    def test_factory_whatsapp_modules_do_not_import_ops(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        paths = [
            root / "almdina_erp/services/whatsapp_service.py",
            root / "almdina_erp/infrastructure/whatsapp/openwa_client.py",
            root / "almdina_erp/application/whatsapp/send_invoice.py",
            root / "almdina_erp/application/whatsapp/send_measurements.py",
            root / "almdina_erp/application/whatsapp/send_stage_completion.py",
        ]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("customer_bot_ops", text)
            self.assertNotIn("customer_bot_pilot", text)
            self.assertNotIn("LIVE_REPLY_DELIVERY_ENABLED", text)
            self.assertNotIn("customer_bot_ops_mode", text)


class PatchIdempotencyTests(unittest.TestCase):
    def test_patch_never_writes_production(self) -> None:
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1]
            / "patches/v1_0/install_customer_bot_ops_mode.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"pilot"', source)
        self.assertIn('"off"', source)
        self.assertNotIn('"production"', source)
        self.assertIn("customer_bot_ops_mode", source)


if __name__ == "__main__":
    unittest.main()
