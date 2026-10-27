"""Customer-bot operation cycle against an in-memory gateway."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import threading
import unittest
import unittest.mock

from almdina_erp.almdina_erp.application.customer_bot.operate_customer_bot import (
    ActivityObservation,
    SessionObservation,
    WebhookObservation,
    check_customer_bot,
    read_operation_status,
    start_customer_bot,
    stop_customer_bot,
)
from almdina_erp.almdina_erp.domain.customer_bot.operation import (
    DECISION_RUNNING,
    DECISION_STOPPED,
    DEFAULT_REPLY_VALIDITY,
    SESSION_LOGIN_REQUIRED,
    SESSION_MISSING,
    SESSION_READY,
    SESSION_UNREACHABLE,
    STATE_DEGRADED,
    STATE_NEEDS_SETUP,
    STATE_READY,
    STATE_STOPPED,
    OperationRecord,
    REASON_QUEUE,
    REASON_REPLY_EXPIRED,
    REASON_SESSION_LOGIN,
    REASON_SUPERSEDED,
    REASON_WEBHOOK_ROLE,
    callback_url,
    classify_gateway_session,
    reply_validity_cancel_reason,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_callback import (
    CUSTOMER_BOT_CALLBACK_PATH,
)


def hold_short_queue_for_probe() -> None:
    """Block the short queue long enough to outlast the two-second probe."""

    import time

    time.sleep(3)


NOW = datetime(2026, 10, 26, 9, 0, tzinfo=timezone.utc)
SESSION = "factory-session"
URL = "https://erp.example"
CALLBACK = callback_url(URL, CUSTOMER_BOT_CALLBACK_PATH)


@dataclass
class _Webhook:
    id: str
    session_id: str
    url: str
    events: tuple[str, ...]
    active: bool
    retry_count: int
    secret_generation: int
    header_user: str


class _Gateway:
    def __init__(self) -> None:
        self.webhooks: dict[str, _Webhook] = {}
        self.sessions: dict[str, str] = {SESSION: SESSION_READY}
        self.created = 0
        self.updated = 0
        self.deleted = 0
        self.forbidden: list[str] = []
        self.role_blocked = False
        self._seq = 0


class _World:
    def __init__(self, gateway: _Gateway | None = None) -> None:
        self.gateway = gateway or _Gateway()
        self.record = OperationRecord()
        self.locked = False
        self._mutex = threading.Lock()
        self.armed = False
        self.production_opens = 0
        self.rearms = 0
        self.disarms = 0
        self.enabled = False
        self.enable_calls = 0
        self.disable_calls = 0
        self.cancelled = 0
        self.texts = True
        self.session_id = SESSION
        self.base = URL
        self.secret_generations = 0
        self.users = 0
        self.user = "customer-bot-ingest@almdina.invalid"
        self.queue_ok = True
        self.pdf = True
        self.scheduler = True
        self.fail_webhook = False
        self.activity_row = ActivityObservation()
        self.store = self
        self.lock = self
        self.gates = self
        self.acceptance = self
        self.replies = self

    def load(self) -> OperationRecord:
        return self.record

    def begin_activation(self, expected_generation: int) -> OperationRecord | None:
        if self.record.generation != expected_generation:
            return None
        self.record = replace(self.record, state="activating", reason="")
        return self.record

    def fail(self, expected_generation: int, reason: str) -> OperationRecord | None:
        if self.record.generation != expected_generation:
            return None
        self.record = replace(
            self.record,
            decision=DECISION_STOPPED,
            state=STATE_NEEDS_SETUP,
            generation=self.record.generation + 1,
            reason=reason,
            last_error=reason,
        )
        return self.record

    def mark_ready(
        self,
        expected_generation: int,
        *,
        webhook_id: str,
        ingest_user: str,
        queue_checked_at: datetime,
    ) -> OperationRecord | None:
        if self.record.generation != expected_generation:
            return None
        self.record = replace(
            self.record,
            decision=DECISION_RUNNING,
            state=STATE_READY,
            reason="",
            last_error="",
            webhook_id=webhook_id or self.record.webhook_id,
            ingest_user=ingest_user or self.record.ingest_user,
            queue_ok=True,
            queue_checked_at=queue_checked_at,
        )
        return self.record

    def mark_degraded(self, expected_generation: int, reason: str) -> OperationRecord | None:
        if self.record.generation != expected_generation:
            return None
        self.record = replace(
            self.record,
            decision=DECISION_RUNNING,
            state=STATE_DEGRADED,
            reason=reason,
            last_error=reason,
        )
        return self.record

    def stop(self) -> OperationRecord:
        self.record = replace(
            self.record,
            decision=DECISION_STOPPED,
            state=STATE_STOPPED,
            generation=self.record.generation + 1,
            reason="",
            last_error="",
        )
        return self.record

    def note_queue(self, expected_generation: int, *, ok: bool, checked_at: datetime) -> None:
        if self.record.generation != expected_generation:
            return
        self.record = replace(self.record, queue_ok=ok, queue_checked_at=checked_at)

    def try_acquire(self) -> bool:
        if self.locked:
            return False
        return self._mutex.acquire(blocking=False)

    def release(self) -> None:
        if self._mutex.locked():
            self._mutex.release()

    def disarm(self) -> None:
        self.armed = False
        self.disarms += 1

    def open_production(self) -> None:
        self.armed = True
        self.production_opens += 1

    def rearm(self) -> None:
        self.armed = True
        self.rearms += 1

    def transport_armed(self) -> bool:
        return self.armed

    def disable(self) -> None:
        self.enabled = False
        self.disable_calls += 1

    def enable(self) -> None:
        self.enabled = True
        self.enable_calls += 1

    def cancel_pending(self) -> int:
        self.cancelled += 1
        return 1

    def texts_valid(self) -> bool:
        return self.texts

    def factory_session_id(self) -> str:
        return self.session_id

    def public_base_url(self) -> str:
        return self.base

    def public_callback_url(self) -> str:
        return callback_url(self.base, CUSTOMER_BOT_CALLBACK_PATH)

    def inspect_session(self, session_id: str) -> SessionObservation:
        status = self.gateway.sessions.get(session_id, SESSION_MISSING)
        return SessionObservation(
            status,
            session_id=session_id,
            matches_factory=status == SESSION_READY and session_id == self.session_id,
        )

    def ensure_ingest_user(self) -> str:
        if self.users == 0:
            self.users = 1
        return self.user

    def ensure_webhook_secret(self) -> None:
        if self.secret_generations == 0:
            self.secret_generations = 1

    def ensure_webhook(self, *, session_id: str, url: str, webhook_id: str) -> WebhookObservation:
        if self.gateway.role_blocked:
            raise PermissionError("operator role required")
        if self.fail_webhook:
            raise RuntimeError("gateway down")
        existing = self.gateway.webhooks.get(webhook_id) if webhook_id else None
        if existing is None:
            for item in self.gateway.webhooks.values():
                if item.session_id == session_id and item.url == url:
                    existing = item
                    break
        created = False
        corrected = False
        if existing is None:
            self.gateway._seq += 1
            self.gateway.created += 1
            existing = _Webhook(
                id=f"wh-{self.gateway._seq}",
                session_id=session_id,
                url=url,
                events=("message.received",),
                active=True,
                retry_count=3,
                secret_generation=self.secret_generations,
                header_user=self.user,
            )
            self.gateway.webhooks[existing.id] = existing
            created = True
        else:
            desired = (url, ("message.received",), True, 3, session_id)
            actual = (
                existing.url,
                existing.events,
                existing.active,
                existing.retry_count,
                existing.session_id,
            )
            if actual != desired:
                existing.url = url
                existing.events = ("message.received",)
                existing.active = True
                existing.retry_count = 3
                existing.session_id = session_id
                existing.secret_generation = self.secret_generations
                existing.header_user = self.user
                self.gateway.updated += 1
                corrected = True
        return WebhookObservation(
            id=existing.id,
            url=existing.url,
            events=existing.events,
            active=existing.active,
            retry_count=existing.retry_count,
            session_id=existing.session_id,
            created=created,
            corrected=corrected,
        )

    def list_webhook(self, *, session_id: str, webhook_id: str, url: str) -> WebhookObservation | None:
        del url
        item = self.gateway.webhooks.get(webhook_id)
        if item is None or item.session_id != session_id:
            return None
        return WebhookObservation(
            id=item.id,
            url=item.url,
            events=item.events,
            active=item.active,
            retry_count=item.retry_count,
            session_id=item.session_id,
        )

    def queue_proven(self, now: datetime) -> bool:
        del now
        return self.queue_ok

    def pdf_ready(self) -> bool:
        return self.pdf

    def scheduler_enabled(self) -> bool:
        return self.scheduler

    def activity(self) -> ActivityObservation:
        return self.activity_row


class OperationCycleTests(unittest.TestCase):
    def test_connected_factory_without_a_webhook_starts_once(self) -> None:
        world = _World()
        result = start_customer_bot(world, now=NOW)
        self.assertEqual(result["decision"], DECISION_RUNNING)
        self.assertEqual(result["state"], STATE_READY)
        self.assertEqual(result["sending_accepted"], False)
        self.assertEqual(result["customer_receipt_proven"], False)
        self.assertTrue(result["transport_armed"])
        self.assertEqual(world.gateway.created, 1)
        self.assertEqual(world.users, 1)
        self.assertEqual(world.secret_generations, 1)
        self.assertEqual(world.production_opens, 1)
        self.assertNotIn("secret", result)
        self.assertNotIn("api_key", result)

    def test_second_start_does_not_create_resources_or_a_new_production_window(self) -> None:
        world = _World()
        start_customer_bot(world, now=NOW)
        again = start_customer_bot(world, now=NOW + timedelta(minutes=1))
        self.assertEqual(again["state"], STATE_READY)
        self.assertEqual(world.gateway.created, 1)
        self.assertEqual(world.gateway.updated, 0)
        self.assertEqual(world.users, 1)
        self.assertEqual(world.secret_generations, 1)
        self.assertEqual(world.production_opens, 1)
        self.assertEqual(world.cancelled, 0)

    def test_concurrent_start_is_rejected(self) -> None:
        world = _World()
        world.locked = True
        result = start_customer_bot(world, now=NOW)
        self.assertEqual(result["reason"], "operation_busy")
        self.assertEqual(world.gateway.created, 0)
        self.assertFalse(world.armed)

    def test_each_failed_step_stays_disarmed_and_retry_reuses_the_webhook(self) -> None:
        world = _World()
        world.texts = False
        self.assertEqual(start_customer_bot(world, now=NOW)["reason"], "texts_invalid")
        world.texts = True
        world.gateway.sessions[SESSION] = SESSION_LOGIN_REQUIRED
        failed = start_customer_bot(world, now=NOW)
        self.assertEqual(failed["reason"], REASON_SESSION_LOGIN)
        self.assertEqual(failed["decision"], DECISION_STOPPED)
        self.assertFalse(world.armed)
        world.gateway.sessions[SESSION] = SESSION_READY
        world.queue_ok = False
        self.assertEqual(start_customer_bot(world, now=NOW)["reason"], REASON_QUEUE)
        self.assertEqual(world.gateway.created, 1)
        world.queue_ok = True
        world.pdf = False
        self.assertEqual(start_customer_bot(world, now=NOW)["reason"], "pdf_unavailable")
        world.pdf = True
        world.scheduler = False
        self.assertEqual(start_customer_bot(world, now=NOW)["reason"], "scheduler_disabled")
        world.scheduler = True
        ready = start_customer_bot(world, now=NOW)
        self.assertEqual(ready["state"], STATE_READY)
        self.assertEqual(world.gateway.created, 1)
        self.assertEqual(world.secret_generations, 1)

    def test_stop_during_start_blocks_the_late_arm(self) -> None:
        world = _World()
        original = world.ensure_webhook

        def stop_midway(**kwargs: object) -> WebhookObservation:
            webhook = original(**kwargs)
            stop_customer_bot(world, now=NOW)
            return webhook

        world.ensure_webhook = stop_midway  # type: ignore[method-assign]
        result = start_customer_bot(world, now=NOW)
        self.assertEqual(result["decision"], DECISION_STOPPED)
        self.assertEqual(result["reason"], REASON_SUPERSEDED)
        self.assertFalse(world.armed)
        self.assertGreaterEqual(world.disarms, 1)
        self.assertEqual(world.disable_calls, 1)
        self.assertEqual(world.cancelled, 1)

    def test_stop_then_start_cancels_pending_and_opens_a_new_window(self) -> None:
        world = _World()
        start_customer_bot(world, now=NOW)
        stopped = stop_customer_bot(world, now=NOW)
        self.assertEqual(stopped["decision"], DECISION_STOPPED)
        self.assertFalse(world.armed)
        self.assertFalse(world.enabled)
        self.assertEqual(world.cancelled, 1)
        self.assertEqual(world.gateway.deleted, 0)
        start_customer_bot(world, now=NOW + timedelta(minutes=1))
        self.assertEqual(world.production_opens, 2)
        self.assertEqual(world.gateway.created, 1)

    def test_queue_probe_ignores_a_local_wait_marker(self) -> None:
        from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_operation_runtime import (
            queue_probe_is_done,
        )

        class _Cache:
            def get_value(self, key: str, expires: bool = False, use_local_cache: bool = True) -> str:
                del key
                if use_local_cache or not expires:
                    return "wait"
                return "done"

        import frappe

        with unittest.mock.patch.object(frappe, "cache", _Cache()):
            self.assertTrue(queue_probe_is_done("probe-key"))

    def test_queue_loss_degrades_without_clearing_the_run_decision(self) -> None:
        world = _World()
        start_customer_bot(world, now=NOW)
        world.queue_ok = False
        checked = check_customer_bot(world, now=NOW + timedelta(minutes=1))
        self.assertEqual(checked["decision"], DECISION_RUNNING)
        self.assertEqual(checked["state"], STATE_DEGRADED)
        self.assertFalse(world.armed)
        world.queue_ok = True
        recovered = check_customer_bot(world, now=NOW + timedelta(minutes=2))
        self.assertEqual(recovered["state"], STATE_READY)
        self.assertTrue(world.armed)
        self.assertEqual(world.rearms, 1)
        self.assertEqual(world.production_opens, 1)
        self.assertEqual(world.gateway.created, 1)

    def test_status_read_does_not_create_or_arm(self) -> None:
        world = _World()
        status = read_operation_status(world, now=NOW)
        self.assertEqual(status["decision"], DECISION_STOPPED)
        self.assertEqual(world.gateway.created, 0)
        self.assertEqual(world.production_opens, 0)
        self.assertFalse(world.armed)
        self.assertEqual(status["customer_receipt_proven"], False)

    def test_login_loss_does_not_create_a_session(self) -> None:
        world = _World()
        start_customer_bot(world, now=NOW)
        world.gateway.sessions[SESSION] = SESSION_LOGIN_REQUIRED
        checked = check_customer_bot(world, now=NOW)
        self.assertEqual(checked["reason"], REASON_SESSION_LOGIN)
        self.assertEqual(checked["decision"], DECISION_RUNNING)
        self.assertEqual(world.gateway.created, 1)

    def test_two_sites_share_a_gateway_without_deleting_each_other(self) -> None:
        gateway = _Gateway()
        first = _World(gateway)
        second = _World(gateway)
        second.session_id = "other-session"
        gateway.sessions["other-session"] = SESSION_READY
        start_customer_bot(first, now=NOW)
        start_customer_bot(second, now=NOW)
        self.assertEqual(len(gateway.webhooks), 2)
        self.assertEqual(gateway.deleted, 0)
        start_customer_bot(first, now=NOW)
        self.assertEqual(len(gateway.webhooks), 2)

    def test_webhook_role_is_a_blocker_not_a_bypass(self) -> None:
        world = _World()
        world.gateway.role_blocked = True
        result = start_customer_bot(world, now=NOW)
        self.assertEqual(result["reason"], REASON_WEBHOOK_ROLE)
        self.assertEqual(world.gateway.created, 0)
        self.assertFalse(world.armed)

    def test_saved_webhook_is_adopted_when_the_local_id_was_lost(self) -> None:
        world = _World()
        start_customer_bot(world, now=NOW)
        kept = world.record.webhook_id
        world.record = replace(
            world.record,
            webhook_id="",
            decision=DECISION_STOPPED,
            state=STATE_STOPPED,
        )
        world.armed = False
        start_customer_bot(world, now=NOW)
        self.assertEqual(world.gateway.created, 1)
        self.assertEqual(world.record.webhook_id, kept)

    def test_system_zone_creation_expires_after_five_real_minutes(self) -> None:
        from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_reply_repository import (
            _parse_creation,
        )

        with unittest.mock.patch("frappe.utils.get_system_timezone", return_value="Asia/Kolkata"):
            created = _parse_creation("2026-10-26 18:00:00")
        self.assertEqual(created, datetime(2026, 10, 26, 12, 30, tzinfo=timezone.utc))
        later = datetime(2026, 10, 26, 12, 36, tzinfo=timezone.utc)
        earlier = datetime(2026, 10, 26, 12, 34, tzinfo=timezone.utc)
        self.assertEqual(reply_validity_cancel_reason(created, later), REASON_REPLY_EXPIRED)
        self.assertIsNone(reply_validity_cancel_reason(created, earlier))

    def test_reply_older_than_five_minutes_is_expired(self) -> None:
        created = NOW - DEFAULT_REPLY_VALIDITY - timedelta(seconds=1)
        self.assertEqual(reply_validity_cancel_reason(created, NOW), REASON_REPLY_EXPIRED)
        self.assertIsNone(reply_validity_cancel_reason(NOW - timedelta(minutes=4), NOW))
        self.assertIsNone(reply_validity_cancel_reason(None, NOW))

    def test_callback_url_rejects_a_client_shaped_value(self) -> None:
        with self.assertRaises(ValueError):
            callback_url("https://user:pass@erp.example", CUSTOMER_BOT_CALLBACK_PATH)
        with self.assertRaises(ValueError):
            callback_url("ftp://erp.example", CUSTOMER_BOT_CALLBACK_PATH)
        with self.assertRaises(ValueError):
            callback_url(URL, "https://elsewhere.example/hook")
        self.assertTrue(CALLBACK.endswith("receive_openwa_customer_bot_event"))

    def test_disconnected_is_a_connection_fault_not_confirmed_login_loss(self) -> None:
        self.assertEqual(classify_gateway_session("disconnected"), SESSION_UNREACHABLE)
        self.assertEqual(classify_gateway_session("failed"), SESSION_UNREACHABLE)
        self.assertEqual(classify_gateway_session("initializing"), SESSION_UNREACHABLE)
        self.assertEqual(classify_gateway_session("authenticating"), SESSION_UNREACHABLE)
        self.assertEqual(classify_gateway_session("qr_ready"), SESSION_LOGIN_REQUIRED)
        self.assertEqual(classify_gateway_session("action_required"), SESSION_LOGIN_REQUIRED)
        self.assertEqual(classify_gateway_session("created"), SESSION_LOGIN_REQUIRED)
        self.assertEqual(classify_gateway_session("ready"), SESSION_READY)

    def test_operation_capability_is_not_implied_by_settings_or_whatsapp(self) -> None:
        from almdina_erp.almdina_erp.domain.security.authorization import Capability
        from almdina_erp.almdina_erp.domain.security.factory_settings import settings_context

        settings = settings_context([Capability.MANAGE_CUSTOMER_BOT_SETTINGS])
        operation = settings_context([Capability.MANAGE_CUSTOMER_BOT_OPERATION])
        whatsapp = settings_context([Capability.MANAGE_WHATSAPP_SESSION])
        self.assertFalse(settings["can_manage_customer_bot_operation"])
        self.assertTrue(operation["can_manage_customer_bot_operation"])
        self.assertFalse(operation["can_manage_customer_bot_settings"])
        self.assertFalse(whatsapp["can_manage_customer_bot_operation"])


class OperationStatusHttpTests(unittest.TestCase):
    def test_status_accepts_desk_post_and_only_reads(self) -> None:
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1]
            / "almdina_erp"
            / "services"
            / "customer_bot_operation_service.py"
        ).read_text(encoding="utf-8")
        status = source.split("def get_customer_bot_operation_status", 1)[1].split(
            "def check_customer_bot_operation", 1
        )[0]
        self.assertIn('methods=["GET", "POST"]', source.split("def get_customer_bot_operation_status", 1)[0])
        self.assertIn("run_status", status)
        self.assertNotIn("run_start", status)
        self.assertNotIn("run_stop", status)
        self.assertNotIn("run_check", status)


class OperationConcurrencyTests(unittest.TestCase):
    def test_a_second_start_waits_outside_the_held_activation(self) -> None:
        world = _World()
        entered = threading.Event()
        release = threading.Event()
        original = world.begin_activation

        def hold(expected: int) -> OperationRecord | None:
            result = original(expected)
            entered.set()
            self.assertTrue(release.wait(2))
            return result

        world.begin_activation = hold  # type: ignore[method-assign]
        outcome: dict[str, object] = {}

        def run() -> None:
            outcome["first"] = start_customer_bot(world, now=NOW)

        thread = threading.Thread(target=run)
        thread.start()
        self.assertTrue(entered.wait(2))
        second = start_customer_bot(world, now=NOW)
        release.set()
        thread.join()
        self.assertEqual(second["reason"], "operation_busy")
        self.assertEqual(outcome["first"]["state"], STATE_READY)  # type: ignore[index]
        self.assertEqual(world.gateway.created, 1)
