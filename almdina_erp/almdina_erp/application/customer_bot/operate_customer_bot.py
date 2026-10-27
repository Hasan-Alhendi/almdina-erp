"""Start, stop, read, and recheck the customer bot without owning transport.

Network calls happen between store writes. A start that began before a stop
cannot arm transport after the generation changes. Status reads do not create
webhooks, users, or secrets and do not change the saved decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from almdina_erp.almdina_erp.domain.customer_bot.operation import (
    DECISION_RUNNING,
    DECISION_STOPPED,
    SESSION_LOGIN_REQUIRED,
    SESSION_MISSING,
    SESSION_READY,
    SESSION_UNREACHABLE,
    STATE_ACTIVATING,
    STATE_DEGRADED,
    STATE_NEEDS_SETUP,
    STATE_READY,
    STATE_STOPPED,
    WEBHOOK_EVENTS,
    WEBHOOK_RETRY_COUNT,
    OperationRecord,
)
from almdina_erp.almdina_erp.domain.customer_bot.operation import (
    REASON_BUSY,
    REASON_INGEST,
    REASON_PDF,
    REASON_PUBLIC_URL,
    REASON_QUEUE,
    REASON_SCHEDULER,
    REASON_SECRET,
    REASON_SESSION_LOGIN,
    REASON_SESSION_MISMATCH,
    REASON_SESSION_MISSING,
    REASON_SESSION_UNREACHABLE,
    REASON_SUPERSEDED,
    REASON_TEXTS,
    REASON_WEBHOOK,
    REASON_WEBHOOK_ROLE,
)


@dataclass(frozen=True, slots=True)
class SessionObservation:
    status: str
    session_id: str = ""
    matches_factory: bool = False


@dataclass(frozen=True, slots=True)
class WebhookObservation:
    id: str
    url: str
    events: tuple[str, ...]
    active: bool
    retry_count: int
    session_id: str
    created: bool = False
    corrected: bool = False


@dataclass(frozen=True, slots=True)
class ActivityObservation:
    last_accepted_inbound_at: datetime | None = None
    last_gateway_accept_at: datetime | None = None


class OperationStore(Protocol):
    def load(self) -> OperationRecord: ...

    def begin_activation(self, expected_generation: int) -> OperationRecord | None: ...

    def fail(self, expected_generation: int, reason: str) -> OperationRecord | None: ...

    def mark_ready(
        self,
        expected_generation: int,
        *,
        webhook_id: str,
        ingest_user: str,
        queue_checked_at: datetime,
    ) -> OperationRecord | None: ...

    def mark_degraded(self, expected_generation: int, reason: str) -> OperationRecord | None: ...

    def stop(self) -> OperationRecord: ...

    def note_queue(self, expected_generation: int, *, ok: bool, checked_at: datetime) -> None: ...


class OperationLock(Protocol):
    def try_acquire(self) -> bool: ...

    def release(self) -> None: ...


class OperationGates(Protocol):
    def disarm(self) -> None: ...

    def open_production(self) -> None: ...

    def rearm(self) -> None: ...

    def transport_armed(self) -> bool: ...


class OperationAcceptance(Protocol):
    def disable(self) -> None: ...

    def enable(self) -> None: ...


class OperationReplies(Protocol):
    def cancel_pending(self) -> int: ...


class OperationChecks(Protocol):
    def texts_valid(self) -> bool: ...

    def factory_session_id(self) -> str: ...

    def public_base_url(self) -> str: ...

    def public_callback_url(self) -> str: ...

    def inspect_session(self, session_id: str) -> SessionObservation: ...

    def ensure_ingest_user(self) -> str: ...

    def ensure_webhook_secret(self) -> None: ...

    def ensure_webhook(self, *, session_id: str, url: str, webhook_id: str) -> WebhookObservation: ...

    def list_webhook(self, *, session_id: str, webhook_id: str, url: str) -> WebhookObservation | None: ...

    def queue_proven(self, now: datetime) -> bool: ...

    def pdf_ready(self) -> bool: ...

    def scheduler_enabled(self) -> bool: ...

    def activity(self) -> ActivityObservation: ...


def start_customer_bot(checks: OperationChecks, *, now: datetime | None = None) -> dict[str, object]:
    clock = _clock(now)
    deps = _require_deps(checks)
    if not deps.lock.try_acquire():
        return _view(deps.store.load(), checks, reason=REASON_BUSY)
    try:
        current = deps.store.load()
        begun = deps.store.begin_activation(current.generation)
        if begun is None:
            return _view(deps.store.load(), checks, reason=REASON_SUPERSEDED)
        captured = begun.generation
        failure = _prerequisites(deps, checks, captured, clock)
        if failure is not None:
            return failure
        if deps.store.load().generation != captured:
            deps.gates.disarm()
            return _view(deps.store.load(), checks, reason=REASON_SUPERSEDED)
        if current.decision != DECISION_RUNNING:
            deps.gates.open_production()
        elif not deps.gates.transport_armed():
            deps.gates.rearm()
        deps.acceptance.enable()
        ready = deps.store.mark_ready(
            captured,
            webhook_id=str(getattr(checks, "_last_webhook_id", "") or deps.store.load().webhook_id),
            ingest_user=str(getattr(checks, "_last_ingest_user", "") or ""),
            queue_checked_at=clock,
        )
        if ready is None:
            deps.gates.disarm()
            return _view(deps.store.load(), checks, reason=REASON_SUPERSEDED)
        return _view(ready, checks)
    finally:
        deps.lock.release()


def stop_customer_bot(checks: OperationChecks, *, now: datetime | None = None) -> dict[str, object]:
    del now
    deps = _require_deps(checks)
    deps.gates.disarm()
    record = deps.store.stop()
    deps.acceptance.disable()
    deps.replies.cancel_pending()
    return _view(record, checks)


def read_operation_status(checks: OperationChecks, *, now: datetime | None = None) -> dict[str, object]:
    del now
    _require_deps(checks)
    return _view(checks.store.load(), checks, live=True)  # type: ignore[attr-defined]


def check_customer_bot(checks: OperationChecks, *, now: datetime | None = None) -> dict[str, object]:
    """Recheck a running bot and re-arm only when the saved decision is running."""

    clock = _clock(now)
    deps = _require_deps(checks)
    current = deps.store.load()
    if current.decision != DECISION_RUNNING:
        return _view(current, checks, live=True)
    if not deps.lock.try_acquire():
        return _view(current, checks, reason=REASON_BUSY, live=True)
    try:
        captured = deps.store.load()
        if captured.decision != DECISION_RUNNING:
            return _view(captured, checks, live=True)
        observed = _observe_running(deps, checks, captured, clock)
        if observed is not None:
            return observed
        if deps.store.load().generation != captured.generation:
            deps.gates.disarm()
            return _view(deps.store.load(), checks, reason=REASON_SUPERSEDED)
        if not deps.gates.transport_armed():
            deps.gates.rearm()
        ready = deps.store.mark_ready(
            captured.generation,
            webhook_id=captured.webhook_id or str(getattr(checks, "_last_webhook_id", "") or ""),
            ingest_user=captured.ingest_user or str(getattr(checks, "_last_ingest_user", "") or ""),
            queue_checked_at=clock,
        )
        if ready is None:
            deps.gates.disarm()
            return _view(deps.store.load(), checks, reason=REASON_SUPERSEDED)
        return _view(ready, checks, live=True)
    finally:
        deps.lock.release()


@dataclass(frozen=True, slots=True)
class _Deps:
    store: OperationStore
    lock: OperationLock
    gates: OperationGates
    acceptance: OperationAcceptance
    replies: OperationReplies


def _require_deps(checks: OperationChecks) -> _Deps:
    return _Deps(
        store=checks.store,  # type: ignore[attr-defined]
        lock=checks.lock,  # type: ignore[attr-defined]
        gates=checks.gates,  # type: ignore[attr-defined]
        acceptance=checks.acceptance,  # type: ignore[attr-defined]
        replies=checks.replies,  # type: ignore[attr-defined]
    )


def _prerequisites(
    deps: _Deps,
    checks: OperationChecks,
    captured: int,
    now: datetime,
) -> dict[str, object] | None:
    if not checks.texts_valid():
        return _fail(deps, checks, captured, REASON_TEXTS)
    session_id = str(checks.factory_session_id() or "").strip()
    if not session_id:
        return _fail(deps, checks, captured, REASON_SESSION_MISSING)
    session = checks.inspect_session(session_id)
    if session.status == SESSION_MISSING:
        return _fail(deps, checks, captured, REASON_SESSION_MISSING)
    if session.status == SESSION_UNREACHABLE:
        return _fail(deps, checks, captured, REASON_SESSION_UNREACHABLE)
    if session.status != SESSION_READY or not session.matches_factory:
        if session.status == SESSION_LOGIN_REQUIRED:
            return _fail(deps, checks, captured, REASON_SESSION_LOGIN)
        return _fail(deps, checks, captured, REASON_SESSION_MISMATCH)
    try:
        ingest_user = checks.ensure_ingest_user()
    except Exception:
        return _fail(deps, checks, captured, REASON_INGEST)
    if not str(ingest_user or "").strip():
        return _fail(deps, checks, captured, REASON_INGEST)
    setattr(checks, "_last_ingest_user", ingest_user)
    try:
        checks.ensure_webhook_secret()
    except Exception:
        return _fail(deps, checks, captured, REASON_SECRET)
    try:
        url = checks.public_callback_url()
    except ValueError:
        return _fail(deps, checks, captured, REASON_PUBLIC_URL)
    try:
        webhook = checks.ensure_webhook(
            session_id=session_id,
            url=url,
            webhook_id=deps.store.load().webhook_id,
        )
    except PermissionError:
        return _fail(deps, checks, captured, REASON_WEBHOOK_ROLE)
    except Exception:
        return _fail(deps, checks, captured, REASON_WEBHOOK)
    if not _webhook_matches(webhook, session_id=session_id, url=url):
        return _fail(deps, checks, captured, REASON_WEBHOOK)
    setattr(checks, "_last_webhook_id", webhook.id)
    if not checks.queue_proven(now):
        deps.store.note_queue(captured, ok=False, checked_at=now)
        return _fail(deps, checks, captured, REASON_QUEUE)
    deps.store.note_queue(captured, ok=True, checked_at=now)
    if not checks.pdf_ready():
        return _fail(deps, checks, captured, REASON_PDF)
    if not checks.scheduler_enabled():
        return _fail(deps, checks, captured, REASON_SCHEDULER)
    return None


def _observe_running(
    deps: _Deps,
    checks: OperationChecks,
    current: OperationRecord,
    now: datetime,
) -> dict[str, object] | None:
    session_id = str(checks.factory_session_id() or "").strip()
    session = checks.inspect_session(session_id) if session_id else SessionObservation(SESSION_MISSING)
    if session.status != SESSION_READY or not session.matches_factory:
        reason = REASON_SESSION_LOGIN if session.status == SESSION_LOGIN_REQUIRED else REASON_SESSION_UNREACHABLE
        if session.status == SESSION_MISSING or not session_id:
            reason = REASON_SESSION_MISSING
        deps.gates.disarm()
        saved = deps.store.mark_degraded(current.generation, reason)
        return _view(saved or deps.store.load(), checks, reason=reason)
    try:
        url = checks.public_callback_url()
        webhook = checks.ensure_webhook(
            session_id=session_id,
            url=url,
            webhook_id=current.webhook_id,
        )
    except Exception:
        deps.gates.disarm()
        saved = deps.store.mark_degraded(current.generation, REASON_WEBHOOK)
        return _view(saved or deps.store.load(), checks, reason=REASON_WEBHOOK)
    if not _webhook_matches(webhook, session_id=session_id, url=url):
        deps.gates.disarm()
        saved = deps.store.mark_degraded(current.generation, REASON_WEBHOOK)
        return _view(saved or deps.store.load(), checks, reason=REASON_WEBHOOK)
    setattr(checks, "_last_webhook_id", webhook.id)
    proven = checks.queue_proven(now)
    deps.store.note_queue(current.generation, ok=proven, checked_at=now)
    if not proven or not checks.pdf_ready() or not checks.scheduler_enabled():
        deps.gates.disarm()
        reason = REASON_QUEUE if not proven else REASON_PDF if not checks.pdf_ready() else REASON_SCHEDULER
        saved = deps.store.mark_degraded(current.generation, reason)
        return _view(saved or deps.store.load(), checks, reason=reason)
    return None


def _webhook_matches(webhook: WebhookObservation, *, session_id: str, url: str) -> bool:
    return bool(
        webhook.id
        and webhook.session_id == session_id
        and webhook.url == url
        and tuple(webhook.events) == WEBHOOK_EVENTS
        and webhook.active
        and webhook.retry_count == WEBHOOK_RETRY_COUNT
    )


def _fail(deps: _Deps, checks: OperationChecks, captured: int, reason: str) -> dict[str, object]:
    deps.gates.disarm()
    saved = deps.store.fail(captured, reason)
    record = saved if saved is not None else deps.store.load()
    code = reason if saved is not None else REASON_SUPERSEDED
    return _view(record, checks, reason=code)


def _view(
    record: OperationRecord,
    checks: OperationChecks,
    *,
    reason: str | None = None,
    live: bool = False,
) -> dict[str, object]:
    shown_reason = record.reason if reason is None else reason
    session = SessionObservation(SESSION_UNREACHABLE)
    webhook_registered = bool(record.webhook_id)
    if live:
        session_id = str(checks.factory_session_id() or "").strip()
        if session_id:
            session = checks.inspect_session(session_id)
        listed = checks.list_webhook(
            session_id=session.session_id or session_id,
            webhook_id=record.webhook_id,
            url="",
        )
        webhook_registered = listed is not None or bool(record.webhook_id and not live)
        if listed is not None:
            webhook_registered = True
    activity = checks.activity()
    settings_ready = record.state == STATE_READY and record.decision == DECISION_RUNNING
    connection_ready = session.status == SESSION_READY and session.matches_factory and webhook_registered
    return {
        "decision": record.decision,
        "state": record.state if reason != REASON_BUSY else record.state,
        "reason": shown_reason,
        "generation": record.generation,
        "session": {
            "status": session.status if live else _saved_session_status(record),
            "matches_factory": session.matches_factory if live else record.state == STATE_READY,
        },
        "webhook_registered": webhook_registered,
        "secret_configured": bool(record.webhook_id) or record.state == STATE_READY,
        "ingest_user_configured": bool(record.ingest_user),
        "queue": {
            "ok": record.queue_ok,
            "checked_at": _iso(record.queue_checked_at),
        },
        "last_accepted_inbound_at": _iso(activity.last_accepted_inbound_at),
        "last_gateway_accept_at": _iso(activity.last_gateway_accept_at),
        "last_error": record.last_error,
        "settings_ready": settings_ready,
        "connection_ready": connection_ready if live else record.state == STATE_READY,
        "transport_armed": _require_deps(checks).gates.transport_armed(),
        "sending_accepted": False,
        "customer_receipt_proven": False,
        "activation_busy": reason == REASON_BUSY,
    }


def _saved_session_status(record: OperationRecord) -> str:
    if record.state == STATE_READY:
        return SESSION_READY
    if record.reason == REASON_SESSION_LOGIN:
        return SESSION_LOGIN_REQUIRED
    if record.reason == REASON_SESSION_MISSING:
        return SESSION_MISSING
    if record.state in {STATE_DEGRADED, STATE_NEEDS_SETUP}:
        return SESSION_UNREACHABLE
    return SESSION_UNREACHABLE if record.decision == DECISION_STOPPED else SESSION_READY


def _clock(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


__all__ = [
    "ActivityObservation",
    "OperationAcceptance",
    "OperationChecks",
    "OperationGates",
    "OperationLock",
    "OperationReplies",
    "OperationStore",
    "SessionObservation",
    "WebhookObservation",
    "check_customer_bot",
    "read_operation_status",
    "start_customer_bot",
    "stop_customer_bot",
]
