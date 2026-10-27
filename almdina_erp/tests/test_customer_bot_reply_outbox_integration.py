"""MariaDB proof for the reply outbox. The gateway is a fake and nothing is sent."""

from __future__ import annotations

import threading
from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.application.customer_bot.accept_inbound_message import (
    accept_inbound_customer_message,
)
from almdina_erp.almdina_erp.application.customer_bot.deliver_reply_intents import (
    ReplyDeliveryDeps,
    deliver_one_reply,
    deliver_pending_replies,
    recover_abandoned_reply_claims,
)
from almdina_erp.almdina_erp.domain.customer_bot.conversation import BotMessageKey
from almdina_erp.almdina_erp.domain.customer_bot.gateway_capabilities import BotGatewayCapabilities
from almdina_erp.almdina_erp.domain.customer_bot.message_templates import render_customer_lines
from almdina_erp.almdina_erp.domain.customer_bot.reply_intent import (
    ABANDONED_CLAIM_REASON,
    ReplyIntent,
)
from almdina_erp.almdina_erp.domain.customer_bot.session_admission import (
    DUPLICATE,
    FAILED,
    PROCESSED,
)
from almdina_erp.almdina_erp.domain.customer_bot.text_reply import SendDisposition, TextSendResult
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_reply_delivery import (
    LIVE_REPLY_DELIVERY_ENABLED,
    scheduled_customer_bot_reply_tick,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_reply_repository import (
    FrappeCustomerBotReplyRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_session_records import (
    REPLY_DOCTYPE,
    customer_bot_reply_intent_has_permission,
    customer_bot_reply_intent_query,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_session_repository import (
    FrappeCustomerBotSessionRepository,
    _insert_replies,
)
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
from almdina_erp.tests.test_customer_bot_inbound_session_integration import _Thread

PREFIX = "cbot-reply-"


class _Gateway:
    def __init__(self, disposition: SendDisposition) -> None:
        self.disposition = disposition
        self.calls: list[str] = []

    def capabilities(self) -> BotGatewayCapabilities:
        return BotGatewayCapabilities(
            sends_text=True,
            supports_interactive_options=False,
            supports_idempotent_send=False,
        )

    def send_text_reply(self, request):
        self.calls.append(request.text)
        return TextSendResult(
            reply_id=request.reply_id,
            connection_ref=request.connection_ref,
            destination_id=request.destination_id,
            disposition=self.disposition,
            provider_message_id="wa-msg-1" if self.disposition is SendDisposition.ACCEPTED else None,
            reason_code="gateway_accepted" if self.disposition is SendDisposition.ACCEPTED else "gateway_http_400",
        )


class TestCustomerBotReplyOutboxIntegration(FrappeTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self.clock = _Clock()
        self.settings = _Settings()
        self.directory = _Directory()
        self.sessions = FrappeCustomerBotSessionRepository()
        self.outbox = FrappeCustomerBotReplyRepository()
        self._settings_before = _settings_rows()
        self._cleanup()

    def tearDown(self):
        frappe.set_user("Administrator")
        self._cleanup()
        self.assertEqual(_settings_rows(), self._settings_before)
        super().tearDown()

    def test_state_event_and_replies_commit_or_roll_back_together(self) -> None:
        connection = PREFIX + "atom"
        first = self._accept(_message("hello", "e1", connection_ref=connection))
        self.assertEqual(first.disposition, PROCESSED)
        before = _conversation(connection)
        self.assertEqual(_reply_count(connection, "e1"), 1)

        def fail(*_args, **_kwargs):
            raise RuntimeError("intent insert failed")

        with patch(
            "almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_session_repository._insert_replies",
            fail,
        ):
            failed = self._accept(_message("2", "e2", connection_ref=connection))
        self.assertEqual(failed.disposition, FAILED)
        after = _conversation(connection)
        self.assertEqual(after["state_json"], before["state_json"])
        self.assertEqual(int(after["revision"]), int(before["revision"]))
        self.assertEqual(_event_count(connection, "e2"), 0)
        self.assertEqual(_reply_count(connection, "e2"), 0)
        self.assertEqual(_reply_count(connection, "e1"), 1)

    def test_duplicate_and_concurrent_events_store_one_reply_set(self) -> None:
        connection = PREFIX + "dup"
        self._accept(_message("hello", "e1", connection_ref=connection))
        replay = self._accept(_message("hello", "e1", connection_ref=connection))
        self.assertEqual(replay.disposition, DUPLICATE)
        self.assertEqual(replay.messages, ())
        self.assertEqual(_reply_count(connection, "e1"), 1)
        raced = PREFIX + "race"
        left = self._start(lambda: self._accept(_message("hello", "e1", connection_ref=raced)))
        right = self._start(lambda: self._accept(_message("hello", "e1", connection_ref=raced)))
        outcomes = [left.join_result().disposition, right.join_result().disposition]
        frappe.db.rollback()
        self.assertEqual(outcomes.count(PROCESSED), 1)
        self.assertEqual(_reply_count(raced, "e1"), 1)

    def test_unique_intent_key_rejects_a_second_copy(self) -> None:
        connection = PREFIX + "key"
        self._accept(_message("hello", "e1", connection_ref=connection))
        row = _reply_rows(connection, "e1")[0]
        with self.assertRaises(Exception) as caught:
            frappe.db.sql(
                """insert into `tabCustomer Bot Reply Intent`
                   (name, creation, modified, modified_by, owner, docstatus,
                    reply_id, connection_ref, provider_event_id, conversation_id,
                    destination_id, sequence, body, status, attempt_count)
                   values ('cbot-reply-dup', now(), now(), 'Administrator', 'Administrator', 0,
                           %s, %s, %s, %s, %s, %s, 'again', 'pending', 0)""",
                (
                    row.reply_id,
                    row.connection_ref,
                    row.provider_event_id,
                    row.conversation_id,
                    row.destination_id,
                    row.sequence,
                ),
            )
        self.assertEqual(caught.exception.args[0], 1062)
        frappe.db.rollback()
        self.assertEqual(_reply_count(connection, "e1"), 1)

    def test_two_workers_and_recovery_and_crash(self) -> None:
        connection = PREFIX + "send"
        self.directory.matches = {}
        accepted = self._accept(_message("hello", "e1", connection_ref=connection))
        self.assertEqual(accepted.disposition, PROCESSED)
        self.assertEqual(_reply_count(connection, "e1"), 1)
        release = threading.Event()
        entered = threading.Event()
        gateway = _Gateway(SendDisposition.ACCEPTED)
        original = gateway.send_text_reply

        def blocking(request):
            entered.set()
            self.assertTrue(release.wait(10))
            return original(request)

        gateway.send_text_reply = blocking
        holder = self._start(lambda: deliver_one_reply(FrappeCustomerBotReplyRepository(), gateway, now=NOW))
        self.assertTrue(entered.wait(10))
        missed = self._in_thread(lambda: deliver_one_reply(FrappeCustomerBotReplyRepository(), gateway, now=NOW))
        self.assertIsNone(missed)
        release.set()
        sent = holder.join_result()
        frappe.db.rollback()
        self.assertEqual(sent.status, "accepted")
        self.assertEqual(len(gateway.calls), 1)
        self.assertEqual(_status(connection, "e1"), "accepted")
        self.assertEqual(_provider_message_id(connection, "e1"), "wa-msg-1")

        ordered = PREFIX + "order"
        self.directory.matches = {"+963988100101": ("CUST-A",)}
        welcome = self._accept(_message("hello", "e1", connection_ref=ordered))
        lines = render_customer_lines(self.settings.published, welcome.messages)
        recovered = deliver_pending_replies(FrappeCustomerBotReplyRepository(), _Gateway(SendDisposition.ACCEPTED), now=NOW)
        self.assertEqual([step.status for step in recovered], ["accepted"])
        self.assertEqual([row.body for row in _reply_rows(ordered, "e1")], ["\n".join(lines)])

        crashed = PREFIX + "crash"
        self.directory.matches = {}
        self._accept(_message("hello", "e1", connection_ref=crashed))
        crashing = _Gateway(SendDisposition.ACCEPTED)

        def explode(**_kwargs):
            raise RuntimeError("died before save")

        outbox = FrappeCustomerBotReplyRepository()
        outbox.record_result = explode
        step = deliver_one_reply(outbox, crashing, now=NOW)
        self.assertEqual(step.status, "processing")
        self.assertEqual(_status(crashed, "e1"), "processing")
        lost_token = _claim_token(crashed, "e1")
        self.assertEqual(deliver_one_reply(FrappeCustomerBotReplyRepository(), crashing, now=NOW), None)
        self.assertEqual(len(crashing.calls), 1)
        abandoned = recover_abandoned_reply_claims(
            FrappeCustomerBotReplyRepository(),
            now=NOW + timedelta(minutes=3),
            claim_ttl=timedelta(minutes=2),
        )
        self.assertEqual(abandoned, 1)
        self.assertEqual(_status(crashed, "e1"), "unknown")
        self.assertEqual(_reason_code(crashed, "e1"), ABANDONED_CLAIM_REASON)
        late = TextSendResult(
            reply_id=_reply_rows(crashed, "e1")[0].reply_id,
            connection_ref=crashed,
            destination_id="chat-a",
            disposition=SendDisposition.ACCEPTED,
            provider_message_id="wa-late",
            reason_code="gateway_accepted",
        )
        self.assertFalse(
            FrappeCustomerBotReplyRepository().record_result(
                reply_id=late.reply_id,
                claim_token=lost_token,
                result=late,
                now=NOW + timedelta(minutes=3),
            )
        )
        self.assertEqual(_status(crashed, "e1"), "unknown")
        self.assertIsNone(_provider_message_id(crashed, "e1"))

        blocked = PREFIX + "block"
        _insert_replies(
            (
                ReplyIntent(
                    connection_ref=blocked,
                    provider_event_id="e1",
                    conversation_id="chat-a",
                    destination_id="chat-a",
                    sequence=0,
                    body="first part",
                    acceptance_epoch=0,
                ),
                ReplyIntent(
                    connection_ref=blocked,
                    provider_event_id="e1",
                    conversation_id="chat-a",
                    destination_id="chat-a",
                    sequence=1,
                    body="second part",
                    acceptance_epoch=0,
                ),
            ),
            frappe.utils.now(),
        )
        self.assertEqual(
            deliver_one_reply(
                FrappeCustomerBotReplyRepository(),
                _Gateway(SendDisposition.REJECTED),
                now=NOW,
            ).status,
            "rejected",
        )
        self.assertIsNone(
            deliver_one_reply(
                FrappeCustomerBotReplyRepository(),
                _Gateway(SendDisposition.ACCEPTED),
                now=NOW,
            )
        )
        rows = _reply_rows(blocked, "e1")
        self.assertEqual(rows[0].status, "rejected")
        self.assertEqual(rows[1].status, "pending")

    def test_unregistered_intent_round_trips_and_reaches_the_fake_gateway(self) -> None:
        connection = PREFIX + "public"
        self.directory.matches = {}
        accepted = self._accept(_message("hello", "e1", connection_ref=connection))
        self.assertEqual(accepted.disposition, PROCESSED)
        row = frappe.db.sql(
            """select customer_id, normalized_phone, message_key, body, document_spec
               from `tabCustomer Bot Reply Intent`
               where connection_ref=%s and provider_event_id=%s""",
            (connection, "e1"),
            as_dict=True,
        )[0]
        self.assertFalse(row.customer_id)
        self.assertEqual(row.message_key, BotMessageKey.UNREGISTERED_PHONE)
        self.assertFalse(row.document_spec)
        guidance = render_customer_lines(
            self.settings.published,
            accepted.messages,
        )
        self.assertEqual((row.body,), guidance)
        gateway = _Gateway(SendDisposition.ACCEPTED)
        delivered = deliver_one_reply(
            FrappeCustomerBotReplyRepository(),
            gateway,
            now=NOW,
            deps=ReplyDeliveryDeps(
                settings=self.settings,
                directory=self.directory,
                services=_Services(),
            ),
        )
        self.assertEqual(delivered.status, "accepted")
        self.assertEqual(gateway.calls, [row.body])
        self.assertNotIn("CUST-", gateway.calls[0])
        self.assertNotIn("DCO-", gateway.calls[0])

        conflict = PREFIX + "conflict"
        self.directory.matches = {"+963988100101": ("CUST-1", "CUST-2")}
        conflicted = self._accept(_message("hello", "e1", connection_ref=conflict))
        self.assertEqual(conflicted.disposition, PROCESSED)
        stored = frappe.db.sql(
            """select customer_id, message_key, body
               from `tabCustomer Bot Reply Intent`
               where connection_ref=%s and provider_event_id=%s""",
            (conflict, "e1"),
            as_dict=True,
        )[0]
        self.assertFalse(stored.customer_id)
        self.assertEqual(stored.message_key, BotMessageKey.UNREGISTERED_PHONE)
        self.assertNotIn("CUST-", stored.body)

    def test_scheduled_tick_recovers_without_sending(self) -> None:
        from datetime import datetime, timezone

        self.assertFalse(LIVE_REPLY_DELIVERY_ENABLED)
        connection = PREFIX + "tick"
        self.directory.matches = {}
        self._accept(_message("hello", "e1", connection_ref=connection))
        live_now = datetime.now(timezone.utc)
        claimed = FrappeCustomerBotReplyRepository().claim_next(now=live_now)
        self.assertIsNotNone(claimed)
        self.assertEqual(_status(connection, "e1"), "processing")
        result = scheduled_customer_bot_reply_tick()
        self.assertEqual(result["sent"], 0)
        self.assertEqual(_status(connection, "e1"), "processing")
        with patch(
            "almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_reply_repository.claim_is_abandoned",
            return_value=True,
        ):
            abandoned = scheduled_customer_bot_reply_tick()
        self.assertGreaterEqual(abandoned["abandoned"], 1)
        self.assertEqual(abandoned["sent"], 0)
        self.assertEqual(_status(connection, "e1"), "unknown")

    def test_records_stay_closed(self) -> None:
        self.assertFalse(customer_bot_reply_intent_has_permission(user="Guest", ptype="read"))
        self.assertEqual(customer_bot_reply_intent_query(), "1=0")
        with self.assertRaises(frappe.PermissionError):
            frappe.get_doc(
                {
                    "doctype": REPLY_DOCTYPE,
                    "reply_id": "cbot-reply-desk",
                    "connection_ref": PREFIX + "desk",
                    "provider_event_id": "event",
                    "conversation_id": "chat",
                    "destination_id": "chat",
                    "sequence": 0,
                    "body": "hello",
                    "status": "pending",
                    "attempt_count": 0,
                }
            ).insert(ignore_permissions=True)

    def _accept(self, message):
        return accept_inbound_customer_message(
            message,
            sessions=self.sessions,
            settings=self.settings,
            directory=self.directory,
            headers=_Orders((_header("DCO-A"), _header("DCO-B"))),
            stages=_Stages(),
            routes=_Routes(),
            services=_Services(),
            now=self.clock.now,
        )

    def _start(self, fn):
        return _Thread(fn, frappe.local.site, frappe.local.sites_path)

    def _in_thread(self, fn):
        return self._start(fn).join_result()

    def _cleanup(self) -> None:
        frappe.db.rollback()
        frappe.db.sql(
            "delete from `tabCustomer Bot Reply Intent` where connection_ref like %s",
            (PREFIX + "%",),
        )
        frappe.db.sql(
            "delete from `tabCustomer Bot Conversation` where connection_ref like %s",
            (PREFIX + "%",),
        )
        frappe.db.sql(
            "delete from `tabCustomer Bot Inbound Event` where connection_ref like %s",
            (PREFIX + "%",),
        )
        frappe.db.commit()


def _settings_rows():
    return tuple(
        (row.field, row.value)
        for row in frappe.db.sql(
            "select field, value from `tabSingles` where doctype='Customer Bot Settings' order by field",
            as_dict=True,
        )
    )


def _conversation(connection_ref: str):
    return frappe.db.sql(
        """select state_json, revision from `tabCustomer Bot Conversation`
           where connection_ref=%s""",
        (connection_ref,),
        as_dict=True,
    )[0]


def _event_count(connection_ref: str, event_id: str) -> int:
    return int(
        frappe.db.sql(
            """select count(*) from `tabCustomer Bot Inbound Event`
               where connection_ref=%s and provider_event_id=%s""",
            (connection_ref, event_id),
        )[0][0]
    )


def _reply_count(connection_ref: str, event_id: str) -> int:
    return int(
        frappe.db.sql(
            """select count(*) from `tabCustomer Bot Reply Intent`
               where connection_ref=%s and provider_event_id=%s""",
            (connection_ref, event_id),
        )[0][0]
    )


def _reply_rows(connection_ref: str, event_id: str):
    return frappe.db.sql(
        """select reply_id, connection_ref, provider_event_id, conversation_id,
                  destination_id, sequence, body, status
           from `tabCustomer Bot Reply Intent`
           where connection_ref=%s and provider_event_id=%s
           order by sequence asc""",
        (connection_ref, event_id),
        as_dict=True,
    )


def _status(connection_ref: str, event_id: str) -> str:
    return _reply_rows(connection_ref, event_id)[0].status


def _provider_message_id(connection_ref: str, event_id: str):
    row = frappe.db.sql(
        """select provider_message_id from `tabCustomer Bot Reply Intent`
           where connection_ref=%s and provider_event_id=%s order by sequence asc""",
        (connection_ref, event_id),
    )
    return row[0][0]


def _claim_token(connection_ref: str, event_id: str) -> str:
    row = frappe.db.sql(
        """select claim_token from `tabCustomer Bot Reply Intent`
           where connection_ref=%s and provider_event_id=%s order by sequence asc""",
        (connection_ref, event_id),
    )
    return row[0][0]


def _reason_code(connection_ref: str, event_id: str) -> str | None:
    row = frappe.db.sql(
        """select reason_code from `tabCustomer Bot Reply Intent`
           where connection_ref=%s and provider_event_id=%s order by sequence asc""",
        (connection_ref, event_id),
    )
    return row[0][0]
