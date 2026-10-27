"""Session admission without a site, a gateway, or a send."""

from __future__ import annotations

import inspect
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from almdina_erp.almdina_erp.application.customer_bot.accept_inbound_message import (
    accept_inbound_customer_message,
)
from almdina_erp.almdina_erp.application.customer_bot.conversation_ports import (
    CustomerServiceRequest,
    CustomerServiceResult,
)
from almdina_erp.almdina_erp.application.customer_bot.settings_commands import (
    CustomerBotSettingsSnapshot,
)
from almdina_erp.almdina_erp.application.customer_bot.order_followup_ports import CustomerOrderHeader
from almdina_erp.almdina_erp.application.customer_bot.preview_conversation import (
    preview_customer_bot_turn,
)
from almdina_erp.almdina_erp.application.customer_bot.read_runtime import (
    next_acceptance_epoch,
    read_customer_bot_runtime,
)
from almdina_erp.almdina_erp.domain.customer_bot.conversation import (
    BotMessageKey,
    ConversationPhase,
    ServiceResultCode,
)
from almdina_erp.almdina_erp.domain.customer_bot.documents import CustomerBotDocument
from almdina_erp.almdina_erp.domain.customer_bot.inbound_message import (
    InboundMessageKind,
    build_inbound_customer_message,
)
from almdina_erp.almdina_erp.domain.customer_bot.message_defaults import default_texts
from almdina_erp.almdina_erp.domain.customer_bot.session_admission import (
    CONFLICT,
    CONVERSATION_BUSY,
    DUPLICATE,
    FAILED,
    IGNORED,
    IN_PROGRESS,
    LOST_LEASE,
    NOT_ACCEPTING,
    PROCESSED,
    SUPPRESSED,
)
from almdina_erp.almdina_erp.domain.orders.revisions import RevisionState
from almdina_erp.tests.customer_bot_session_memory import MemoryCustomerBotSessionStore

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
PHONE = "+963988100101"
CUSTOMER = "CUST-A"
OTHER = "CUST-B"


class _Clock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now


class _Settings:
    def __init__(self) -> None:
        texts = default_texts()
        self._enabled = True
        self.acceptance_epoch = 4
        self.published = dict(texts)
        self.draft = dict(texts)
        self.revision = 3

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self.acceptance_epoch = next_acceptance_epoch(self._enabled, self.acceptance_epoch, bool(value))
        self._enabled = bool(value)

    def load(self) -> CustomerBotSettingsSnapshot:
        return CustomerBotSettingsSnapshot(
            enabled=self.enabled,
            revision=self.revision,
            draft=dict(self.draft),
            published=dict(self.published),
            published_on=None,
            published_by=None,
            modified=None,
            modified_by=None,
            acceptance_epoch=self.acceptance_epoch,
        )

    def published_if_same_acceptance(self, acceptance_epoch: int) -> dict[str, str] | None:
        runtime = read_customer_bot_runtime(self)
        if not runtime.accepting_messages or runtime.acceptance_epoch != acceptance_epoch:
            return None
        return dict(runtime.published or {})


class _Directory:
    def __init__(self) -> None:
        self.matches = {PHONE: (CUSTOMER,)}
        self.calls = 0

    def find_by_normalized_phone(self, normalized_phone: str) -> tuple[str, ...]:
        self.calls += 1
        return self.matches.get(normalized_phone, ())

    def customer_exists(self, customer_id: str) -> bool:
        return False


class _Orders:
    def __init__(self, rows: tuple[CustomerOrderHeader, ...] = ()) -> None:
        self.rows = rows
        self.list_calls = 0

    def list_current_headers(self, customer_id: str) -> tuple[CustomerOrderHeader, ...]:
        self.list_calls += 1
        return tuple(row for row in self.rows if row.customer_id == customer_id)

    def get_header_by_exact_name(self, order_name: str) -> CustomerOrderHeader | None:
        for row in self.rows:
            if row.name == order_name:
                return row
        return None


class _Stages:
    def stages_for_orders(self, pointers):
        return {}


class _Routes:
    def terminal_by_path_and_stage(self, keys):
        return {key: None for key in keys}


class _Services:
    def __init__(self) -> None:
        self.calls = 0
        self.gate = None
        self.fail = False

    def execute(self, request: CustomerServiceRequest) -> CustomerServiceResult:
        self.calls += 1
        if self.gate is not None:
            self.gate()
        if self.fail:
            raise RuntimeError("renderer failed")
        return self._result(request)

    def materialize(self, request: CustomerServiceRequest) -> CustomerServiceResult:
        return self._result(request)

    def _result(self, request: CustomerServiceRequest) -> CustomerServiceResult:
        return CustomerServiceResult(
            ServiceResultCode.READY,
            amount=1,
            currency="USD",
            documents=(
                CustomerBotDocument(
                    "customer_invoice",
                    "invoice.pdf",
                    "application/pdf",
                    b"%PDF-test",
                    order_name=request.order_name,
                    consistency_key="price-key-1",
                    service_id=request.service_id,
                    amount="1",
                    currency="USD",
                ),
            ),
        )


def _header(name: str, customer: str = CUSTOMER) -> CustomerOrderHeader:
    return CustomerOrderHeader(
        name=name,
        customer_id=customer,
        order_date="2026-10-01",
        stored_status="Draft",
        revision_state=RevisionState.CURRENT,
        production_path="",
        current_stage_name="",
    )


def _message(text: str, event: str, **kwargs):
    values = {
        "connection_ref": "conn-a",
        "provider_event_id": event,
        "conversation_id": "chat-a",
        "sender_id": "sender-a",
        "occurred_at": NOW,
        "kind": InboundMessageKind.TEXT,
        "text": text,
        "from_own_account": False,
        "is_group": False,
        "trusted_normalized_phone": PHONE,
    }
    values.update(kwargs)
    return build_inbound_customer_message(**values)


class InboundSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = _Clock()
        self.settings = _Settings()
        self.directory = _Directory()
        self.orders = _Orders((_header("DCO-A"), _header("DCO-B")))
        self.services = _Services()
        self.sessions = MemoryCustomerBotSessionStore()

    def accept(self, message, **kwargs):
        return accept_inbound_customer_message(
            message,
            sessions=self.sessions,
            settings=self.settings,
            directory=self.directory,
            headers=self.orders,
            stages=_Stages(),
            routes=_Routes(),
            services=self.services,
            now=self.clock.now,
            session_ttl=kwargs.get("session_ttl", timedelta(minutes=30)),
            lease_ttl=kwargs.get("lease_ttl", timedelta(minutes=2)),
        )

    def test_new_conversation_then_service_then_order_are_separate_calls(self) -> None:
        first = self.accept(_message("hello", "e1"))
        self.assertTrue(first.sendable)
        self.assertEqual(first.disposition, PROCESSED)
        self.assertEqual(first.messages[0].key, BotMessageKey.WELCOME)
        self.assertEqual(self.services.calls, 0)
        self.assertEqual(self.sessions.conversations[("conn-a", "chat-a", "sender-a")].customer_id, CUSTOMER)
        second = self.accept(_message("2", "e2"))
        self.assertEqual(second.messages[-1].key, BotMessageKey.ASK_ORDER_NUMBER)
        self.assertEqual(self.services.calls, 0)
        third = self.accept(_message("DCO-A", "e3"))
        self.assertEqual(third.messages[0].key, BotMessageKey.FINAL_PRICE)
        self.assertEqual(self.services.calls, 1)
        self.assertEqual(len(third.documents), 1)
        stored = self.sessions.conversations[("conn-a", "chat-a", "sender-a")].state_json or ""
        self.assertIn(ConversationPhase.AWAITING_ORDER_NUMBER, stored)
        self.assertNotIn("%PDF", stored)
        self.assertNotIn("USD", stored)
        self.assertNotIn("DCO-B", stored)
        event = self.sessions.events[("conn-a", "e3")]
        self.assertEqual(event.outcome, "processed")
        self.assertNotIn("hello", event.fingerprint)

    def test_expired_session_starts_at_the_menu(self) -> None:
        self.accept(_message("hello", "e1"))
        self.accept(_message("2", "e2"))
        self.clock.now += timedelta(minutes=31)
        # Provider timestamp stays fresh; only the conversation TTL expires.
        again = self.accept(
            _message("مرحبا", "e3", occurred_at=self.clock.now),
            session_ttl=timedelta(minutes=30),
        )
        self.assertEqual(again.messages[0].key, BotMessageKey.WELCOME)
        self.assertEqual(self.services.calls, 0)
        self.assertEqual(self.orders.list_calls, 1)
        chosen = self.accept(
            _message("2", "e4", occurred_at=self.clock.now),
            session_ttl=timedelta(minutes=30),
        )
        self.assertEqual(chosen.messages[0].key, BotMessageKey.CURRENT_ORDER_LINE)
        self.assertNotIn(BotMessageKey.WELCOME, [item.key for item in chosen.messages])
        self.assertEqual(self.services.calls, 0)
        self.assertEqual(self.orders.list_calls, 2)

    def test_completed_event_does_not_run_again_or_return_a_sendable_reply(self) -> None:
        self.accept(_message("hello", "e1"))
        self.accept(_message("2", "e2"))
        original = self.accept(_message("DCO-A", "e3"))
        self.assertTrue(original.sendable)
        replay = self.accept(_message("DCO-A", "e3"))
        self.assertEqual(replay.disposition, DUPLICATE)
        self.assertFalse(replay.sendable)
        self.assertFalse(replay.retry_later)
        self.assertEqual(replay.messages, ())
        self.assertEqual(replay.documents, ())
        self.assertEqual(self.services.calls, 1)
        self.assertEqual(len(self.sessions.events), 3)

    def test_same_event_with_different_content_conflicts_without_detail(self) -> None:
        self.accept(_message("hello", "e1"))
        conflict = self.accept(_message("other", "e1"))
        self.assertEqual(conflict.disposition, CONFLICT)
        self.assertFalse(conflict.sendable)
        self.assertFalse(hasattr(conflict, "text"))
        self.assertEqual(self.directory.calls, 1)

    def test_same_event_id_on_two_connections_both_run(self) -> None:
        self.accept(_message("hello", "e1"))
        other = self.accept(_message("hello", "e1", connection_ref="conn-b", conversation_id="chat-b"))
        self.assertEqual(other.disposition, PROCESSED)
        self.assertEqual(len(self.sessions.conversations), 2)
        self.assertIn(("conn-b", "e1"), self.sessions.events)

    def test_second_message_while_leased_is_retryable_and_not_completed(self) -> None:
        self.accept(_message("hello", "e1"))
        self.sessions.steal_lease("conn-a", "chat-a", "sender-a")
        busy = self.accept(_message("2", "e2"))
        self.assertEqual(busy.disposition, CONVERSATION_BUSY)
        self.assertTrue(busy.retry_later)
        self.assertNotIn(("conn-a", "e2"), self.sessions.events)

    def test_in_progress_replay_does_not_call_the_service(self) -> None:
        self.accept(_message("hello", "e1"))
        self.accept(_message("2", "e2"))
        calls = {"count": 0}

        def gate():
            calls["count"] += 1
            replay = self.accept(_message("DCO-A", "e3"))
            self.assertEqual(replay.disposition, IN_PROGRESS)
            self.assertTrue(replay.retry_later)

        self.services.gate = gate
        first = self.accept(_message("DCO-A", "e3"))
        self.assertEqual(first.disposition, PROCESSED)
        self.assertEqual(self.services.calls, 1)
        self.assertEqual(calls["count"], 1)

    def test_renderer_failure_does_not_record_success_and_retry_can_finish(self) -> None:
        self.accept(_message("hello", "e1"))
        self.accept(_message("2", "e2"))
        self.services.fail = True
        failed = self.accept(_message("DCO-A", "e3"))
        self.assertEqual(failed.disposition, FAILED)
        self.assertNotIn(("conn-a", "e3"), self.sessions.events)
        self.assertIsNone(self.sessions.conversations[("conn-a", "chat-a", "sender-a")].lease_token)
        self.services.fail = False
        retried = self.accept(_message("DCO-A", "e3"))
        self.assertEqual(retried.disposition, PROCESSED)
        self.assertEqual(self.services.calls, 2)

    def test_old_worker_cannot_commit_after_the_lease_moves(self) -> None:
        self.accept(_message("hello", "e1"))
        self.accept(_message("2", "e2"))

        def gate():
            self.sessions.steal_lease("conn-a", "chat-a", "sender-a")

        self.services.gate = gate
        lost = self.accept(_message("DCO-A", "e3"))
        self.assertEqual(lost.disposition, LOST_LEASE)
        self.assertFalse(lost.sendable)
        event = self.sessions.events[("conn-a", "e3")]
        self.assertEqual(event.status, "processing")
        stored = self.sessions.conversations[("conn-a", "chat-a", "sender-a")].state_json or ""
        self.assertNotIn("final_price", stored)

    def test_disabled_messages_are_not_replayed_when_the_bot_is_enabled(self) -> None:
        self.settings.enabled = False
        ignored = self.accept(_message("hello", "e1"))
        self.assertEqual(ignored.disposition, NOT_ACCEPTING)
        self.assertEqual(self.directory.calls, 0)
        self.settings.enabled = True
        replay = self.accept(_message("hello", "e1"))
        self.assertEqual(replay.disposition, DUPLICATE)
        self.assertEqual(self.directory.calls, 0)
        fresh = self.accept(_message("hello", "e2"))
        self.assertEqual(fresh.disposition, PROCESSED)

    def test_disable_during_the_renderer_suppresses_without_saving_the_document(self) -> None:
        self.accept(_message("hello", "e1"))
        self.accept(_message("2", "e2"))

        def gate():
            self.settings.enabled = False

        self.services.gate = gate
        suppressed = self.accept(_message("DCO-A", "e3"))
        self.assertEqual(suppressed.disposition, SUPPRESSED)
        self.assertEqual(suppressed.documents, ())
        self.assertEqual(self.sessions.events[("conn-a", "e3")].outcome, "suppressed")
        stored = self.sessions.conversations[("conn-a", "chat-a", "sender-a")].state_json or ""
        self.assertNotIn("%PDF", stored)
        self.settings.enabled = True
        replay = self.accept(_message("DCO-A", "e3"))
        self.assertEqual(replay.disposition, DUPLICATE)
        self.assertEqual(self.services.calls, 1)

    def test_disable_then_enable_before_commit_drops_the_old_turn(self) -> None:
        self.accept(_message("hello", "e1"))
        row = self.sessions.conversations[("conn-a", "chat-a", "sender-a")]
        before_state = row.state_json
        before_revision = row.revision
        original_list = self.orders.list_current_headers
        self.orders.list_current_headers = _flip(original_list, self.settings)
        dropped = self.accept(_message("2", "e2"))
        self.orders.list_current_headers = original_list
        self.assertEqual(dropped.disposition, SUPPRESSED)
        self.assertFalse(dropped.sendable)
        self.assertEqual(dropped.messages, ())
        self.assertEqual(dropped.documents, ())
        self.assertEqual(row.state_json, before_state)
        self.assertEqual(row.revision, before_revision)
        self.assertNotIn("awaiting_order_number", row.state_json or "")
        self.assertEqual(self.sessions.events[("conn-a", "e2")].outcome, SUPPRESSED)
        fresh = self.accept(_message("3", "e3"))
        self.assertEqual(fresh.disposition, PROCESSED)
        self.assertTrue(fresh.sendable)
        replay = self.accept(_message("2", "e2"))
        self.assertEqual(replay.disposition, DUPLICATE)
        self.assertFalse(replay.sendable)
        self.assertEqual(replay.messages, ())

    def test_failed_worker_does_not_release_a_newer_owner(self) -> None:
        self.accept(_message("hello", "e1"))
        self.accept(_message("2", "e2"))

        def gate():
            conversation = self.sessions.conversations[("conn-a", "chat-a", "sender-a")]
            event = self.sessions.events[("conn-a", "e3")]
            conversation.lease_token = "newer-conversation"
            conversation.lease_expires_on = "9999-01-01T00:00:00+00:00"
            event.lease_token = "newer-event"
            event.lease_expires_on = "9999-01-01T00:00:00+00:00"
            raise RuntimeError("old worker failed")

        self.services.gate = gate
        lost = self.accept(_message("DCO-A", "e3"))
        self.assertEqual(lost.disposition, LOST_LEASE)
        self.assertFalse(lost.sendable)
        event = self.sessions.events[("conn-a", "e3")]
        conversation = self.sessions.conversations[("conn-a", "chat-a", "sender-a")]
        self.assertEqual(event.status, "processing")
        self.assertEqual(event.lease_token, "newer-event")
        self.assertEqual(conversation.lease_token, "newer-conversation")
        self.assertNotIn("%PDF", conversation.state_json or "")

    def test_phone_identity_change_restarts_the_menu(self) -> None:
        self.accept(_message("hello", "e1"))
        self.directory.matches[PHONE] = (OTHER,)
        restarted = self.accept(_message("مرحبا", "e2"))
        self.assertEqual(restarted.messages[0].key, BotMessageKey.WELCOME)
        self.assertEqual(self.sessions.conversations[("conn-a", "chat-a", "sender-a")].customer_id, OTHER)
        self.assertEqual(self.services.calls, 0)
        chosen = self.accept(_message("2", "e3"))
        self.assertEqual(chosen.messages[0].key, BotMessageKey.NO_CURRENT_ORDERS)
        self.assertEqual(self.services.calls, 0)

    def test_group_and_own_messages_are_ignored_without_identity_reads(self) -> None:
        group = self.accept(_message("hello", "g1", is_group=True))
        own = self.accept(_message("hello", "o1", from_own_account=True))
        other = self.accept(_message("hello", "u1", kind=InboundMessageKind.OTHER))
        self.assertEqual([group.disposition, own.disposition, other.disposition], [IGNORED, IGNORED, IGNORED])
        self.assertEqual(self.directory.calls, 0)
        self.assertEqual(self.accept(_message("hello", "g1", is_group=True)).disposition, DUPLICATE)

    def test_missing_event_id_never_reaches_the_store(self) -> None:
        with self.assertRaises(ValueError):
            _message("hello", " ")
        self.assertEqual(self.sessions.events, {})

    def test_preview_does_not_use_the_operational_store(self) -> None:
        source = inspect.getsource(preview_customer_bot_turn)
        self.assertNotIn("CustomerBotSessionStore", source)
        self.assertNotIn("accept_inbound_customer_message", source)
        acceptance = inspect.getsource(accept_inbound_customer_message)
        self.assertNotIn("dispatch_text_reply", acceptance)
        self.assertNotIn("import frappe", (ROOT / "almdina_erp/application/customer_bot/accept_inbound_message.py").read_text(encoding="utf-8"))

    def test_purge_keeps_processing_events_and_fresh_dedup_keys(self) -> None:
        self.accept(_message("hello", "e1"))
        self.clock.now += timedelta(days=8)
        self.sessions.events[("conn-a", "live")] = self.sessions.events[("conn-a", "e1")].__class__(
            "abc", "processing", None, "tok", utc(self.clock.now + timedelta(minutes=1)), None
        )
        removed_conversations, removed_events = self.sessions.purge(
            now=self.clock.now,
            conversation_retention=timedelta(days=7),
            event_retention=timedelta(days=30),
            limit=50,
        )
        self.assertEqual(removed_conversations, 1)
        self.assertEqual(removed_events, 0)
        self.assertIn(("conn-a", "e1"), self.sessions.events)
        self.assertIn(("conn-a", "live"), self.sessions.events)

    def test_published_copy_is_returned_and_the_draft_is_not(self) -> None:
        self.settings.draft["welcome"] = "draft only"
        result = self.accept(_message("hello", "e1"))
        self.assertEqual(result.published["welcome"], default_texts()["welcome"])
        self.assertNotEqual(result.published["welcome"], "draft only")


def _flip(method, settings):
    def wrapped(*args, **kwargs):
        settings.enabled = False
        settings.enabled = True
        return method(*args, **kwargs)
    return wrapped


def utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


if __name__ == "__main__":
    unittest.main()
