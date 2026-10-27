"""Reply outbox behavior without a site or a network gateway."""

from __future__ import annotations

import inspect
import threading
import unittest
from datetime import timedelta
from unittest.mock import patch

from almdina_erp.almdina_erp.application.customer_bot.accept_inbound_message import (
    accept_inbound_customer_message,
)
from almdina_erp.almdina_erp.application.customer_bot.deliver_reply_intents import (
    deliver_one_reply,
    deliver_pending_replies,
    recover_abandoned_reply_claims,
)
from almdina_erp.almdina_erp.domain.customer_bot.gateway_capabilities import BotGatewayCapabilities
from almdina_erp.almdina_erp.domain.customer_bot.message_templates import render_customer_lines
from almdina_erp.almdina_erp.domain.customer_bot.reply_intent import (
    ABANDONED_CLAIM_REASON,
    PENDING,
    PROCESSING,
    UNKNOWN,
    ReplyIntent,
)
from almdina_erp.almdina_erp.domain.customer_bot.session_admission import DUPLICATE, FAILED, PROCESSED, SUPPRESSED
from almdina_erp.almdina_erp.domain.customer_bot.text_reply import SendDisposition, TextSendResult
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_reply_delivery import (
    LIVE_REPLY_DELIVERY_ENABLED,
    deliver_customer_bot_replies,
    enqueue_customer_bot_reply_delivery,
    run_customer_bot_reply_delivery_job,
    scheduled_customer_bot_reply_tick,
)
import almdina_erp.hooks as almdina_hooks
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
    _message,
)


class _Gateway:
    def __init__(self, disposition: SendDisposition, *, idempotent: bool = False) -> None:
        self.disposition = disposition
        self.calls: list[str] = []
        self._capabilities = BotGatewayCapabilities(
            sends_text=True,
            supports_interactive_options=False,
            supports_idempotent_send=idempotent,
        )

    def capabilities(self) -> BotGatewayCapabilities:
        return self._capabilities

    def send_text_reply(self, request):
        self.calls.append(request.text)
        provider_message_id = "wa-msg-1" if self.disposition is SendDisposition.ACCEPTED else None
        reason = {
            SendDisposition.ACCEPTED: "gateway_accepted",
            SendDisposition.REJECTED: "gateway_http_400",
            SendDisposition.UNKNOWN: "send_timeout",
        }[self.disposition]
        return TextSendResult(
            reply_id=request.reply_id,
            connection_ref=request.connection_ref,
            destination_id=request.destination_id,
            disposition=self.disposition,
            provider_message_id=provider_message_id,
            reason_code=reason,
        )


class ReplyOutboxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = _Clock()
        self.settings = _Settings()
        self.directory = _Directory()
        self.sessions = MemoryCustomerBotSessionStore()
        self.services = _Services()

    def accept(self, message, **kwargs):
        return accept_inbound_customer_message(
            message,
            sessions=self.sessions,
            settings=self.settings,
            directory=self.directory,
            headers=_Orders((_header("DCO-A"), _header("DCO-B"))),
            stages=_Stages(),
            routes=_Routes(),
            services=self.services,
            now=self.clock.now,
            **kwargs,
        )

    def test_commit_stores_ordered_replies_and_a_duplicate_does_not(self) -> None:
        first = self.accept(_message("hello", "e1"))
        self.assertEqual(first.disposition, PROCESSED)
        lines = render_customer_lines(self.settings.published, first.messages)
        stored = self.sessions.replies[("conn-a", "e1", 0)]
        self.assertEqual(stored.intent.body, "\n".join(lines))
        self.assertEqual(stored.intent.sequence, 0)
        self.assertEqual(stored.intent.destination_id, "chat-a")
        self.assertEqual(stored.status, PENDING)
        self.assertNotIn("+963988100101", stored.reply_id)
        self.assertIn("1-", stored.intent.body)
        self.assertIn("4-", stored.intent.body)
        again = self.accept(_message("hello", "e1"))
        self.assertEqual(again.disposition, DUPLICATE)
        self.assertEqual(len(self.sessions.replies), 1)

    def test_an_accepted_message_renews_the_session_and_a_duplicate_does_not(self) -> None:
        self.accept(_message("hello", "e1"))
        key = ("conn-a", "chat-a", "sender-a")
        first_expiry = self.sessions.conversations[key].expires_on
        self.clock.now = self.clock.now + timedelta(minutes=10)
        duplicate = self.accept(_message("hello", "e1"))
        self.assertEqual(duplicate.disposition, DUPLICATE)
        self.assertEqual(self.sessions.conversations[key].expires_on, first_expiry)
        continued = self.accept(_message("0", "e2"))
        self.assertEqual(continued.disposition, PROCESSED)
        self.assertGreater(self.sessions.conversations[key].expires_on, first_expiry)

    def test_failed_render_keeps_the_previous_state_and_stores_no_reply(self) -> None:
        self.accept(_message("hello", "e1"))
        before = self.sessions.conversations[("conn-a", "chat-a", "sender-a")].revision

        def broken(*_args, **_kwargs):
            raise RuntimeError("render failed")

        original = self.sessions.complete_turn

        def fail_inside(**kwargs):
            kwargs["build_replies"] = broken
            return original(**kwargs)

        self.sessions.complete_turn = fail_inside
        failed = self.accept(_message("2", "e2"))
        self.assertEqual(failed.disposition, FAILED)
        self.assertEqual(self.sessions.conversations[("conn-a", "chat-a", "sender-a")].revision, before)
        self.assertNotIn(("conn-a", "e2", 0), self.sessions.replies)
        self.assertNotIn(("conn-a", "e2"), self.sessions.events)

    def test_suppressed_turn_stores_no_reply(self) -> None:
        self.accept(_message("hello", "e1"))

        def flip(customer_id):
            self.settings.enabled = False
            self.settings.enabled = True
            return tuple(row for row in (_header("DCO-A"), _header("DCO-B")) if row.customer_id == customer_id)

        self.services = _Services()
        orders = _Orders((_header("DCO-A"), _header("DCO-B")))
        orders.list_current_headers = flip
        dropped = accept_inbound_customer_message(
            _message("2", "e2"),
            sessions=self.sessions,
            settings=self.settings,
            directory=self.directory,
            headers=orders,
            stages=_Stages(),
            routes=_Routes(),
            services=self.services,
            now=self.clock.now,
        )
        self.assertEqual(dropped.disposition, SUPPRESSED)
        self.assertNotIn(("conn-a", "e2", 0), self.sessions.replies)

    def test_notifier_failure_leaves_the_committed_replies(self) -> None:
        def fail(_count: int) -> None:
            raise RuntimeError("queue unavailable")

        with self.assertRaises(RuntimeError):
            self.accept(_message("hello", "e1"), on_replies_committed=fail)
        self.assertEqual(len(self.sessions.replies), 1)
        replay = self.accept(_message("hello", "e1"))
        self.assertEqual(replay.disposition, DUPLICATE)
        gateway = _Gateway(SendDisposition.ACCEPTED)
        delivered = deliver_pending_replies(self.sessions, gateway, now=NOW)
        self.assertEqual([step.status for step in delivered], ["accepted"])
        self.assertEqual(len(gateway.calls), 1)

    def test_gateway_results_and_unknown_is_not_retried(self) -> None:
        self.directory.matches = {}
        self.accept(_message("hello", "e1"))
        unknown = _Gateway(SendDisposition.UNKNOWN, idempotent=True)
        step = deliver_one_reply(self.sessions, unknown, now=NOW)
        self.assertEqual(step.status, "unknown")
        self.assertIsNone(deliver_one_reply(self.sessions, unknown, now=NOW))
        self.assertEqual(len(unknown.calls), 1)
        self.assertTrue(unknown.capabilities().supports_idempotent_send)

        self.accept(_message("hello", "e2"))
        rejected = _Gateway(SendDisposition.REJECTED)
        self.assertEqual(deliver_one_reply(self.sessions, rejected, now=NOW).status, "rejected")
        row = self.sessions.replies[("conn-a", "e2", 0)]
        self.assertIsNone(row.provider_message_id)
        self.assertEqual(row.reason_code, "gateway_http_400")

        self.accept(_message("hello", "e3"))
        accepted = _Gateway(SendDisposition.ACCEPTED)
        self.assertEqual(deliver_one_reply(self.sessions, accepted, now=NOW).status, "accepted")
        stored = self.sessions.replies[("conn-a", "e3", 0)]
        self.assertEqual(stored.provider_message_id, "wa-msg-1")
        self.assertEqual(stored.status, "accepted")

    def test_crash_after_acceptance_does_not_return_the_row_to_pending(self) -> None:
        self.directory.matches = {}
        self.accept(_message("hello", "e1"))
        gateway = _Gateway(SendDisposition.ACCEPTED)

        def explode(**_kwargs):
            raise RuntimeError("died before save")

        self.sessions.record_result = explode
        step = deliver_one_reply(self.sessions, gateway, now=NOW)
        self.assertEqual(step.status, PROCESSING)
        row = self.sessions.replies[("conn-a", "e1", 0)]
        self.assertEqual(row.status, PROCESSING)
        self.assertEqual(row.attempt_count, 1)
        lost_token = row.claim_token
        self.sessions.record_result = MemoryCustomerBotSessionStore.record_result.__get__(
            self.sessions, MemoryCustomerBotSessionStore
        )
        self.assertIsNone(deliver_one_reply(self.sessions, gateway, now=NOW))
        self.assertEqual(len(gateway.calls), 1)
        recovered = recover_abandoned_reply_claims(
            self.sessions,
            now=NOW + timedelta(minutes=3),
            claim_ttl=timedelta(minutes=2),
        )
        self.assertEqual(recovered, 1)
        self.assertEqual(row.status, UNKNOWN)
        self.assertEqual(row.reason_code, ABANDONED_CLAIM_REASON)
        late = TextSendResult(
            reply_id=row.reply_id,
            connection_ref="conn-a",
            destination_id="chat-a",
            disposition=SendDisposition.ACCEPTED,
            provider_message_id="wa-late",
            reason_code="gateway_accepted",
        )
        self.assertFalse(
            self.sessions.record_result(
                reply_id=row.reply_id,
                claim_token=lost_token,
                result=late,
                now=NOW + timedelta(minutes=3),
            )
        )
        self.assertEqual(row.status, UNKNOWN)
        self.assertIsNone(row.provider_message_id)

    def test_rejected_or_unknown_blocks_later_sequences(self) -> None:
        self._store_two_parts("conn-a", "e1")
        rejected = _Gateway(SendDisposition.REJECTED)
        self.assertEqual(deliver_one_reply(self.sessions, rejected, now=NOW).status, "rejected")
        self.assertIsNone(deliver_one_reply(self.sessions, rejected, now=NOW))
        self.assertEqual(self.sessions.replies[("conn-a", "e1", 1)].status, PENDING)
        self.assertEqual(len(rejected.calls), 1)

        other = MemoryCustomerBotSessionStore()
        self._store_two_parts("conn-b", "e2", store=other)
        unknown = _Gateway(SendDisposition.UNKNOWN)
        self.assertEqual(deliver_one_reply(other, unknown, now=NOW).status, "unknown")
        self.assertIsNone(deliver_one_reply(other, unknown, now=NOW))
        self.assertEqual(other.replies[("conn-b", "e2", 1)].status, PENDING)
        self.assertEqual(len(unknown.calls), 1)

    def _store_two_parts(self, connection: str, event: str, store=None) -> None:
        target = self.sessions if store is None else store
        intents = tuple(
            ReplyIntent(
                connection_ref=connection,
                provider_event_id=event,
                conversation_id="chat-a",
                destination_id="chat-a",
                sequence=sequence,
                body=body,
            )
            for sequence, body in ((0, "first part"), (1, "second part"))
        )
        target._store_replies(intents, now=NOW)

    def test_two_workers_claim_one_row(self) -> None:
        self.directory.matches = {}
        self.accept(_message("hello", "e1"))
        release = threading.Event()
        entered = threading.Event()
        gateway = _Gateway(SendDisposition.ACCEPTED)
        original = gateway.send_text_reply

        def blocking(request):
            entered.set()
            self.assertTrue(release.wait(5))
            return original(request)

        gateway.send_text_reply = blocking
        errors: list[BaseException] = []
        results: list[object] = []

        def run() -> None:
            try:
                results.append(deliver_one_reply(self.sessions, gateway, now=NOW))
            except BaseException as exc:
                errors.append(exc)

        first = threading.Thread(target=run)
        first.start()
        self.assertTrue(entered.wait(5))
        second = threading.Thread(target=run)
        second.start()
        second.join(5)
        release.set()
        first.join(5)
        self.assertEqual(errors, [])
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        sent = [item for item in results if item is not None]
        self.assertEqual(len(sent), 1)
        self.assertEqual(len(gateway.calls), 1)

    def test_replies_are_sent_in_sequence(self) -> None:
        first = self.accept(_message("hello", "e1"))
        gateway = _Gateway(SendDisposition.ACCEPTED)
        deliver_pending_replies(self.sessions, gateway, now=NOW)
        lines = render_customer_lines(self.settings.published, first.messages)
        self.assertEqual(gateway.calls, ["\n".join(lines)])

    def test_live_delivery_stays_off(self) -> None:
        gateway = _Gateway(SendDisposition.ACCEPTED)
        self.assertFalse(LIVE_REPLY_DELIVERY_ENABLED)
        self.assertEqual(deliver_customer_bot_replies(port=gateway, now=NOW), 0)
        self.assertEqual(gateway.calls, [])

    def test_scheduled_tick_is_registered_and_does_not_send_while_disabled(self) -> None:
        cron = almdina_hooks.scheduler_events["cron"]["* * * * *"]
        self.assertIn(
            "almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_reply_delivery.scheduled_customer_bot_reply_tick",
            cron,
        )
        tick_source = inspect.getsource(scheduled_customer_bot_reply_tick)
        self.assertIn("run_customer_bot_reply_delivery_job", tick_source)
        job_source = inspect.getsource(run_customer_bot_reply_delivery_job)
        self.assertIn("recover_abandoned_reply_claims", job_source)
        self.assertIn("deliver_customer_bot_replies", job_source)
        self.assertNotIn("OpenWAClient", job_source)
        self.assertNotIn("OPENWA_API_KEY", job_source)
        enqueue_source = inspect.getsource(enqueue_customer_bot_reply_delivery)
        self.assertIn("enqueue_after_commit", enqueue_source)
        self.assertIn("frappe.enqueue", enqueue_source)
        with patch(
            "almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_reply_delivery.deliver_customer_bot_replies",
            return_value=0,
        ) as deliver:
            with patch(
                "almdina_erp.almdina_erp.application.customer_bot.deliver_reply_intents.recover_abandoned_reply_claims",
                return_value=2,
            ) as recover:
                with patch(
                    "almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_reply_repository.FrappeCustomerBotReplyRepository",
                ):
                    result = scheduled_customer_bot_reply_tick()
        self.assertEqual(result, {"abandoned": 2, "sent": 0})
        recover.assert_called_once()
        deliver.assert_called_once_with()
        self.assertFalse(LIVE_REPLY_DELIVERY_ENABLED)

    def test_notifier_enqueue_failure_leaves_committed_replies_for_scheduler(self) -> None:
        """Gateway-style notifier must not erase durable intents when enqueue fails."""

        def fail_enqueue(_count: int) -> None:
            # Simulate enqueue_customer_bot_reply_delivery returning False / logging only.
            return None

        accepted = self.accept(_message("hello", "e-enq"), on_replies_committed=fail_enqueue)
        self.assertEqual(accepted.disposition, PROCESSED)
        self.assertEqual(len(self.sessions.replies), 1)
        self.assertTrue(
            all(row.status == PENDING for row in self.sessions.replies.values())
        )
