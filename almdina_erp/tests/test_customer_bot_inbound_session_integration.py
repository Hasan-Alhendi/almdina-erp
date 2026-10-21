"""MariaDB proof for session leases and the real unique event key.

The conversation engine and the four services stay behind fakes. Only the
session tables are written, and those rows are removed afterwards.
"""

from __future__ import annotations

import threading
from datetime import timedelta

import frappe
from frappe.tests.utils import FrappeTestCase
from almdina_erp.almdina_erp.application.customer_bot.accept_inbound_message import (
    accept_inbound_customer_message,
)
from almdina_erp.almdina_erp.application.customer_bot.preview_conversation import (
    preview_customer_bot_turn,
)
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
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_session_records import (
    CONVERSATION_DOCTYPE,
    EVENT_DOCTYPE,
    customer_bot_conversation_has_permission,
    customer_bot_conversation_query,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_session_repository import (
    FrappeCustomerBotSessionRepository,
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

PREFIX = "cbot-sess-"


class TestCustomerBotInboundSessionIntegration(FrappeTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self.clock = _Clock()
        self.settings = _Settings()
        self.directory = _Directory()
        self.orders = _Orders((_header("DCO-A"), _header("DCO-B")))
        self.services = _Services()
        self.sessions = FrappeCustomerBotSessionRepository()
        self._settings_before = _settings_rows()
        self._customers_before = _count("tabCustomer")
        self._orders_before = _count("tabDoor Cutting Order")
        self._cleanup()

    def tearDown(self):
        frappe.set_user("Administrator")
        self._cleanup()
        current = _settings_rows()
        self.assertEqual(current, self._settings_before)
        self.assertEqual(_count("tabCustomer"), self._customers_before)
        self.assertEqual(_count("tabDoor Cutting Order"), self._orders_before)
        super().tearDown()

    def test_flow_dedup_conflict_expiry_and_switch_use_the_database(self) -> None:
        first = self._accept(_message("hello", "e1", connection_ref=PREFIX + "a"))
        self.assertEqual(first.disposition, PROCESSED)
        self._accept(_message("2", "e2", connection_ref=PREFIX + "a"))
        priced = self._accept(_message("DCO-A", "e3", connection_ref=PREFIX + "a"))
        self.assertEqual(priced.disposition, PROCESSED)
        self.assertEqual(self.services.calls, 1)
        replay = self._accept(_message("DCO-A", "e3", connection_ref=PREFIX + "a"))
        self.assertEqual(replay.disposition, DUPLICATE)
        self.assertFalse(replay.sendable)
        self.assertEqual(self.services.calls, 1)
        conflict = self._accept(_message("changed", "e3", connection_ref=PREFIX + "a"))
        self.assertEqual(conflict.disposition, CONFLICT)
        other = self._accept(_message("hello", "e3", connection_ref=PREFIX + "b", conversation_id="chat-b"))
        self.assertEqual(other.disposition, PROCESSED)
        self.clock.now += timedelta(minutes=31)
        restarted = self._accept(_message("2", "e4", connection_ref=PREFIX + "a"))
        self.assertEqual(restarted.messages[0].key, "welcome")
        self.settings.enabled = False
        paused = self._accept(_message("hello", "e5", connection_ref=PREFIX + "a"))
        self.assertEqual(paused.disposition, NOT_ACCEPTING)
        self.settings.enabled = True
        self.assertEqual(self._accept(_message("hello", "e5", connection_ref=PREFIX + "a")).disposition, DUPLICATE)
        self.directory.matches["+963988100101"] = ("CUST-B",)
        changed = self._accept(_message("hello", "e6", connection_ref=PREFIX + "a"))
        self.assertEqual(changed.disposition, PROCESSED)
        self.assertEqual(_customer_id(PREFIX + "a"), "CUST-B")
        ignored = self._accept(_message("hello", "g1", connection_ref=PREFIX + "a", is_group=True))
        self.assertEqual(ignored.disposition, IGNORED)
        self.assertNotIn("%PDF", _stored_text())
        self.assertNotIn("USD", _stored_text())

    def test_failure_releases_the_event_and_a_lost_lease_does_not_commit(self) -> None:
        self._accept(_message("hello", "e1", connection_ref=PREFIX + "fail"))
        self._accept(_message("2", "e2", connection_ref=PREFIX + "fail"))
        self.services.fail = True
        failed = self._accept(_message("DCO-A", "e3", connection_ref=PREFIX + "fail"))
        self.assertEqual(failed.disposition, FAILED)
        self.assertEqual(_event_count(PREFIX + "fail", "e3"), 0)
        self.services.fail = False
        self.assertEqual(self._accept(_message("DCO-A", "e3", connection_ref=PREFIX + "fail")).disposition, PROCESSED)

        self.services.gate = lambda: _steal(PREFIX + "late")
        self._accept(_message("hello", "e1", connection_ref=PREFIX + "late"))
        self._accept(_message("2", "e2", connection_ref=PREFIX + "late"))
        lost = self._accept(_message("DCO-A", "e3", connection_ref=PREFIX + "late"))
        self.assertEqual(lost.disposition, LOST_LEASE)
        self.assertEqual(_event_status(PREFIX + "late", "e3"), "processing")
        self.assertNotIn("%PDF", _stored_text())

    def test_disable_during_processing_suppresses_on_the_database(self) -> None:
        self._accept(_message("hello", "e1", connection_ref=PREFIX + "off"))
        self._accept(_message("2", "e2", connection_ref=PREFIX + "off"))

        def gate():
            self.settings.enabled = False

        self.services.gate = gate
        suppressed = self._accept(_message("DCO-A", "e3", connection_ref=PREFIX + "off"))
        self.assertEqual(suppressed.disposition, SUPPRESSED)
        self.assertEqual(suppressed.documents, ())
        self.assertEqual(_event_status(PREFIX + "off", "e3"), "completed")
        self.assertNotIn("%PDF", _stored_text())

    def test_disable_then_enable_drops_the_old_database_turn(self) -> None:
        self._accept(_message("hello", "e1", connection_ref=PREFIX + "cycle"))
        before = _conversation_row(PREFIX + "cycle")
        original = self.orders.list_current_headers

        def flip(customer_id):
            self.settings.enabled = False
            self.settings.enabled = True
            return original(customer_id)

        self.orders.list_current_headers = flip
        dropped = self._accept(_message("2", "e2", connection_ref=PREFIX + "cycle"))
        self.orders.list_current_headers = original
        self.assertEqual(dropped.disposition, SUPPRESSED)
        self.assertFalse(dropped.sendable)
        self.assertEqual(dropped.messages, ())
        self.assertEqual(dropped.documents, ())
        after = _conversation_row(PREFIX + "cycle")
        self.assertEqual(after["state_json"], before["state_json"])
        self.assertEqual(int(after["revision"]), int(before["revision"]))
        fresh = self._accept(_message("3", "e3", connection_ref=PREFIX + "cycle"))
        self.assertEqual(fresh.disposition, PROCESSED)
        self.assertTrue(fresh.sendable)
        replay = self._accept(_message("2", "e2", connection_ref=PREFIX + "cycle"))
        self.assertEqual(replay.disposition, DUPLICATE)
        self.assertEqual(replay.messages, ())

    def test_failed_worker_does_not_delete_a_newer_database_owner(self) -> None:
        self._accept(_message("hello", "e1", connection_ref=PREFIX + "own"))
        self._accept(_message("2", "e2", connection_ref=PREFIX + "own"))

        def gate():
            _handoff(PREFIX + "own", "e3")
            raise RuntimeError("old worker failed")

        self.services.gate = gate
        lost = self._accept(_message("DCO-A", "e3", connection_ref=PREFIX + "own"))
        self.assertEqual(lost.disposition, LOST_LEASE)
        self.assertFalse(lost.sendable)
        self.assertEqual(_event_status(PREFIX + "own", "e3"), "processing")
        self.assertEqual(_event_token(PREFIX + "own", "e3"), "newer-event")
        self.assertEqual(_conversation_token(PREFIX + "own"), "newer-conversation")

    def test_concurrent_messages_use_independent_connections(self) -> None:
        self._accept(_message("hello", "e-open", connection_ref=PREFIX + "race"))
        started = threading.Event()
        release = threading.Event()
        original = self.orders.list_current_headers

        def blocked(customer_id):
            started.set()
            self.assertTrue(release.wait(10))
            return original(customer_id)

        self.orders.list_current_headers = blocked
        holder = self._start(lambda: self._accept(_message("2", "e-hold", connection_ref=PREFIX + "race")))
        try:
            self.assertTrue(started.wait(10))
            busy = self._in_thread(lambda: self._accept(_message("3", "e-other", connection_ref=PREFIX + "race")))
            same = self._in_thread(lambda: self._accept(_message("2", "e-hold", connection_ref=PREFIX + "race")))
            self.assertEqual(busy.disposition, CONVERSATION_BUSY)
            self.assertEqual(same.disposition, IN_PROGRESS)
            self.assertEqual(_event_count(PREFIX + "race", "e-other"), 0)
        finally:
            release.set()
        held = holder.join_result()
        self.assertEqual(held.disposition, PROCESSED)
        self.assertEqual(_event_count(PREFIX + "race", "e-other"), 0)

    def test_two_conversations_proceed_together(self) -> None:
        barrier = threading.Barrier(2, timeout=10)
        one_order = _Orders((_header("DCO-A"),))
        services = _Services()

        def gate():
            barrier.wait()

        services.gate = gate

        def run(connection, conversation):
            settings = _Settings()
            directory = _Directory()
            clock = _Clock()
            sessions = FrappeCustomerBotSessionRepository()
            accept_inbound_customer_message(
                _message("hello", "e1", connection_ref=connection, conversation_id=conversation),
                sessions=sessions,
                settings=settings,
                directory=directory,
                headers=one_order,
                stages=_Stages(),
                routes=_Routes(),
                services=services,
                now=clock.now,
            )
            return accept_inbound_customer_message(
                _message("2", "e2", connection_ref=connection, conversation_id=conversation),
                sessions=sessions,
                settings=settings,
                directory=directory,
                headers=one_order,
                stages=_Stages(),
                routes=_Routes(),
                services=services,
                now=clock.now,
            )

        left = self._start(lambda: run(PREFIX + "left", "chat-left"))
        right = self._start(lambda: run(PREFIX + "right", "chat-right"))
        try:
            self.assertEqual(left.join_result().disposition, PROCESSED)
            self.assertEqual(right.join_result().disposition, PROCESSED)
        finally:
            barrier.abort()
            left.join_result()
            right.join_result()
        self.assertEqual(services.calls, 2)

    def test_unique_constraint_rejects_a_second_event_row(self) -> None:
        self._accept(_message("hello", "e-unique", connection_ref=PREFIX + "uniq"))
        with self.assertRaises(Exception) as caught:
            frappe.db.sql(
                """insert into `tabCustomer Bot Inbound Event`
                   (name, creation, modified, modified_by, owner, docstatus,
                    connection_ref, provider_event_id, fingerprint, status)
                   values ('dup-event-row', '2026-10-21 00:00:00', '2026-10-21 00:00:00',
                           'Administrator', 'Administrator', 0, %s, 'e-unique', 'f', 'completed')""",
                (PREFIX + "uniq",),
            )
        self.assertEqual(caught.exception.args[0], 1062)
        frappe.db.rollback()

    def test_purge_keeps_a_processing_event_and_a_fresh_key(self) -> None:
        self._accept(_message("hello", "e-old", connection_ref=PREFIX + "purge"))
        frappe.db.sql(
            """insert into `tabCustomer Bot Inbound Event`
               (name, creation, modified, modified_by, owner, docstatus,
                connection_ref, provider_event_id, fingerprint, status, lease_token, lease_expires_on)
               values ('cbot-live-event', '2026-10-21 00:00:00', '2026-10-21 00:00:00',
                       'Administrator', 'Administrator', 0, %s, 'e-live', 'abc', 'processing', 'tok', %s)""",
            (PREFIX + "purge", "9999-01-01T00:00:00+00:00"),
        )
        frappe.db.commit()
        self.clock.now += timedelta(days=8)
        removed_conversations, removed_events = self.sessions.purge(
            now=self.clock.now,
            conversation_retention=timedelta(days=7),
            event_retention=timedelta(days=30),
            limit=20,
        )
        self.assertGreaterEqual(removed_conversations, 1)
        self.assertEqual(removed_events, 0)
        self.assertEqual(_event_status(PREFIX + "purge", "e-old"), "completed")
        self.assertEqual(_event_status(PREFIX + "purge", "e-live"), "processing")

    def test_records_stay_closed_and_preview_does_not_write_them(self) -> None:
        before = _count("tabCustomer Bot Conversation")
        from almdina_erp.almdina_erp.domain.customer_bot.message_defaults import default_texts

        preview_customer_bot_turn(default_texts(), "unknown_number", "hello", None, NOW)
        self.assertEqual(_count("tabCustomer Bot Conversation"), before)
        self.assertFalse(customer_bot_conversation_has_permission(user="Guest", ptype="read"))
        self.assertEqual(customer_bot_conversation_query(), "1=0")
        with self.assertRaises(frappe.PermissionError):
            frappe.get_doc(
                {
                    "doctype": CONVERSATION_DOCTYPE,
                    "connection_ref": PREFIX + "desk",
                    "conversation_id": "chat",
                    "sender_id": "sender",
                    "revision": 1,
                }
            ).insert(ignore_permissions=True)
        with self.assertRaises(frappe.PermissionError):
            frappe.get_doc(
                {
                    "doctype": EVENT_DOCTYPE,
                    "connection_ref": PREFIX + "desk",
                    "provider_event_id": "event",
                    "fingerprint": "abc",
                    "status": "completed",
                }
            ).insert(ignore_permissions=True)

    def _accept(self, message):
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
        )

    def _start(self, fn):
        return _Thread(fn, frappe.local.site, frappe.local.sites_path)

    def _in_thread(self, fn):
        worker = self._start(fn)
        return worker.join_result()

    def _cleanup(self) -> None:
        frappe.db.rollback()
        frappe.db.sql(
            "delete from `tabCustomer Bot Conversation` where connection_ref like %s",
            (PREFIX + "%",),
        )
        frappe.db.sql(
            "delete from `tabCustomer Bot Inbound Event` where connection_ref like %s or name=%s",
            (PREFIX + "%", "cbot-live-event"),
        )
        frappe.db.commit()


class _Thread:
    _connect_lock = threading.Lock()

    def __init__(self, fn, site, sites_path):
        self._box = {}
        self._thread = threading.Thread(target=self._run, args=(fn, site, sites_path))
        self._thread.start()

    def _run(self, fn, site, sites_path):
        with self._connect_lock:
            frappe.init(site=site, sites_path=sites_path)
            frappe.connect()
            frappe.set_user("Administrator")
        try:
            self._box["value"] = fn()
        except Exception as exc:
            self._box["error"] = exc
        finally:
            frappe.destroy()

    def join_result(self, timeout: float = 15):
        self._thread.join(timeout)
        self.assert_finished()
        if "error" in self._box:
            raise self._box["error"]
        return self._box.get("value")

    def assert_finished(self):
        if self._thread.is_alive():
            raise AssertionError("session worker did not finish")


def _handoff(connection_ref: str, event_id: str) -> None:
    frappe.db.sql(
        """update `tabCustomer Bot Conversation`
           set lease_token='newer-conversation', lease_expires_on='9999-01-01T00:00:00+00:00'
           where connection_ref=%s""",
        (connection_ref,),
    )
    frappe.db.sql(
        """update `tabCustomer Bot Inbound Event`
           set lease_token='newer-event', lease_expires_on='9999-01-01T00:00:00+00:00'
           where connection_ref=%s and provider_event_id=%s""",
        (connection_ref, event_id),
    )
    frappe.db.commit()


def _conversation_row(connection_ref: str):
    row = frappe.db.sql(
        """select state_json, revision, lease_token from `tabCustomer Bot Conversation`
           where connection_ref=%s""",
        (connection_ref,),
        as_dict=True,
    )
    return row[0]


def _conversation_token(connection_ref: str) -> str | None:
    return _conversation_row(connection_ref).lease_token


def _event_token(connection_ref: str, event_id: str) -> str | None:
    row = frappe.db.sql(
        """select lease_token from `tabCustomer Bot Inbound Event`
           where connection_ref=%s and provider_event_id=%s""",
        (connection_ref, event_id),
    )
    return row[0][0] if row else None


def _steal(connection_ref: str) -> None:
    frappe.db.sql(
        """update `tabCustomer Bot Conversation`
           set lease_token='stolen', lease_expires_on='9999-01-01T00:00:00+00:00'
           where connection_ref=%s""",
        (connection_ref,),
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


def _count(table: str) -> int:
    return int(frappe.db.sql(f"select count(*) from `{table}`")[0][0])


def _event_count(connection_ref: str, event_id: str) -> int:
    return int(
        frappe.db.sql(
            """select count(*) from `tabCustomer Bot Inbound Event`
               where connection_ref=%s and provider_event_id=%s""",
            (connection_ref, event_id),
        )[0][0]
    )


def _event_status(connection_ref: str, event_id: str) -> str | None:
    row = frappe.db.sql(
        """select status from `tabCustomer Bot Inbound Event`
           where connection_ref=%s and provider_event_id=%s""",
        (connection_ref, event_id),
    )
    return row[0][0] if row else None


def _customer_id(connection_ref: str) -> str | None:
    row = frappe.db.sql(
        "select customer_id from `tabCustomer Bot Conversation` where connection_ref=%s",
        (connection_ref,),
    )
    return row[0][0] if row else None


def _stored_text() -> str:
    conversations = frappe.db.sql(
        "select ifnull(state_json, '') from `tabCustomer Bot Conversation` where connection_ref like %s",
        (PREFIX + "%",),
    )
    events = frappe.db.sql(
        """select ifnull(fingerprint, ''), ifnull(outcome, ''), ifnull(status, '')
           from `tabCustomer Bot Inbound Event` where connection_ref like %s""",
        (PREFIX + "%",),
    )
    return "\n".join(str(value) for row in conversations + events for value in row)

