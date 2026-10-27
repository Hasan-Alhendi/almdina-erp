"""Site-local customer-bot operation store and OpenWA webhook registration.

Status reads do not write ``site_config``. Transport flags change only on
start, stop, or a recovery check for a saved running decision. The OpenWA
routes match the gateway in this workspace: webhook create/list/update require
an OPERATOR key, and responses omit ``secret`` and ``headers``.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import frappe
from frappe.utils.password import get_decrypted_password, set_encrypted_password

from almdina_erp.almdina_erp.application.customer_bot.operate_customer_bot import (
    ActivityObservation,
    SessionObservation,
    WebhookObservation,
    check_customer_bot,
    read_operation_status,
    start_customer_bot,
    stop_customer_bot,
)
from almdina_erp.almdina_erp.application.whatsapp.errors import WhatsAppTransportError
from almdina_erp.almdina_erp.domain.customer_bot.operation import (
    DECISION_RUNNING,
    DECISION_STOPPED,
    SESSION_LOGIN_REQUIRED,
    SESSION_MISSING,
    SESSION_READY,
    SESSION_UNREACHABLE,
    STATE_STOPPED,
    STATES,
    WEBHOOK_EVENTS,
    WEBHOOK_RETRY_COUNT,
    REASON_WEBHOOK_ROLE,
    OperationRecord,
    callback_url,
    classify_gateway_session,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_callback import (
    CUSTOMER_BOT_CALLBACK_PATH,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_settings_records import (
    SERVICE_FLAG,
)
from almdina_erp.almdina_erp.infrastructure.whatsapp.openwa_client import OpenWAClient

DOCTYPE = "Customer Bot Settings"
INGEST_USER = "customer-bot-ingest@almdina.invalid"
INGEST_ROLE = "Customer Bot Ingest"
PUBLIC_BASE_KEY = "customer_bot_public_base_url"
_LOCK = "almdina_customer_bot_operation"
_PROBE_PREFIX = "almdina_customer_bot_queue_probe"
_PROBE_WAIT_SEC = 2.0
_GATEWAY_TIMEOUT_SEC = 3.0


class FrappeCustomerBotOperation:
    """Collaborators for the operation use case. One instance per call."""

    def __init__(self) -> None:
        self.store = self
        self.lock = _GateLock()
        self.gates = _TransportGates()
        self.acceptance = _AcceptanceSwitch()
        self.replies = _PendingReplies()

    def load(self) -> OperationRecord:
        if not _has_operation_columns():
            return OperationRecord()
        decision = str(_single("operation_decision") or DECISION_STOPPED)
        if decision not in {DECISION_STOPPED, DECISION_RUNNING}:
            decision = DECISION_STOPPED
        state = str(_single("operation_state") or STATE_STOPPED)
        if state not in STATES:
            state = STATE_STOPPED
        try:
            generation = int(_single("operation_generation") or 0)
        except (TypeError, ValueError):
            generation = 0
        checked = _single("operation_queue_checked_on")
        parsed = None
        if checked:
            try:
                parsed = datetime.fromisoformat(str(checked).replace("Z", "+00:00"))
            except ValueError:
                parsed = None
        return OperationRecord(
            decision=decision,
            state=state if state else STATE_STOPPED,
            generation=generation,
            reason=str(_single("operation_reason") or ""),
            webhook_id=str(_single("operation_webhook_id") or ""),
            ingest_user=str(_single("operation_ingest_user") or ""),
            queue_ok=str(_single("operation_queue_ok") or "0") in {"1", "True"},
            queue_checked_at=parsed,
            last_error=str(_single("operation_last_error") or ""),
        )

    def begin_activation(self, expected_generation: int) -> OperationRecord | None:
        current = self.load()
        if current.generation != expected_generation:
            return None
        _write_operation(operation_state="activating", operation_reason="")
        return self.load()

    def fail(self, expected_generation: int, reason: str) -> OperationRecord | None:
        current = self.load()
        if current.generation != expected_generation:
            return None
        _write_operation(
            operation_decision=DECISION_STOPPED,
            operation_state="needs_setup",
            operation_generation=str(current.generation + 1),
            operation_reason=reason,
            operation_last_error=reason,
        )
        return self.load()

    def mark_ready(
        self,
        expected_generation: int,
        *,
        webhook_id: str,
        ingest_user: str,
        queue_checked_at: datetime,
    ) -> OperationRecord | None:
        current = self.load()
        if current.generation != expected_generation:
            return None
        _write_operation(
            operation_decision=DECISION_RUNNING,
            operation_state="ready",
            operation_reason="",
            operation_last_error="",
            operation_webhook_id=webhook_id or current.webhook_id,
            operation_ingest_user=ingest_user or current.ingest_user,
            operation_queue_ok="1",
            operation_queue_checked_on=_stamp(queue_checked_at),
        )
        return self.load()

    def mark_degraded(self, expected_generation: int, reason: str) -> OperationRecord | None:
        current = self.load()
        if current.generation != expected_generation:
            return None
        _write_operation(
            operation_decision=DECISION_RUNNING,
            operation_state="degraded",
            operation_reason=reason,
            operation_last_error=reason,
        )
        return self.load()

    def stop(self) -> OperationRecord:
        current = self.load()
        _write_operation(
            operation_decision=DECISION_STOPPED,
            operation_state=STATE_STOPPED,
            operation_generation=str(current.generation + 1),
            operation_reason="",
            operation_last_error="",
        )
        return self.load()

    def note_queue(self, expected_generation: int, *, ok: bool, checked_at: datetime) -> None:
        if self.load().generation != expected_generation:
            return
        _write_operation(
            operation_queue_ok="1" if ok else "0",
            operation_queue_checked_on=_stamp(checked_at),
        )

    def texts_valid(self) -> bool:
        from almdina_erp.almdina_erp.domain.customer_bot.message_templates import validate_texts
        from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_settings_repository import (
            FrappeCustomerBotSettingsRepository,
        )

        try:
            snapshot = FrappeCustomerBotSettingsRepository().load()
        except Exception:
            return False
        return not validate_texts(snapshot.published)

    def factory_session_id(self) -> str:
        try:
            from almdina_erp.almdina_erp.infrastructure.whatsapp.session_store import (
                FrappeWhatsAppSessionStore,
            )

            return str(FrappeWhatsAppSessionStore().get_session_id() or "").strip()
        except Exception:
            return ""

    def public_base_url(self) -> str:
        return str(frappe.conf.get(PUBLIC_BASE_KEY) or "").strip()

    def public_callback_url(self) -> str:
        return callback_url(self.public_base_url(), CUSTOMER_BOT_CALLBACK_PATH)

    def inspect_session(self, session_id: str) -> SessionObservation:
        if not session_id:
            return SessionObservation(SESSION_MISSING)
        try:
            session = _client().get_session(session_id, timeout=_GATEWAY_TIMEOUT_SEC)
        except Exception:
            return SessionObservation(SESSION_UNREACHABLE, session_id=session_id)
        kind = classify_gateway_session(session.status)
        if kind == SESSION_READY and session.id == session_id:
            return SessionObservation(SESSION_READY, session_id=session.id, matches_factory=True)
        if kind == SESSION_LOGIN_REQUIRED:
            return SessionObservation(SESSION_LOGIN_REQUIRED, session_id=session.id or session_id)
        return SessionObservation(SESSION_UNREACHABLE, session_id=session.id or session_id)

    def ensure_ingest_user(self) -> str:
        _ensure_ingest_account()
        return INGEST_USER

    def ensure_webhook_secret(self) -> None:
        existing = get_decrypted_password(
            DOCTYPE,
            DOCTYPE,
            "openwa_webhook_secret",
            raise_exception=False,
        )
        if existing and len(str(existing)) >= 16:
            return
        secret = frappe.generate_hash(length=32)
        previous = getattr(frappe.flags, SERVICE_FLAG, False)
        setattr(frappe.flags, SERVICE_FLAG, True)
        try:
            set_encrypted_password(DOCTYPE, DOCTYPE, secret, fieldname="openwa_webhook_secret")
            frappe.db.commit()
        finally:
            setattr(frappe.flags, SERVICE_FLAG, previous)

    def ensure_webhook(self, *, session_id: str, url: str, webhook_id: str) -> WebhookObservation:
        client = _client()
        try:
            rows = client.list_webhooks(session_id, timeout=_GATEWAY_TIMEOUT_SEC)
        except WhatsAppTransportError as error:
            if error.status_code == 403:
                raise PermissionError(REASON_WEBHOOK_ROLE) from error
            raise
        match = _match_webhook(rows, session_id=session_id, url=url, webhook_id=webhook_id)
        secret, authorization = _webhook_credentials()
        if match is not None and webhook_id and _visible_match(match, session_id=session_id, url=url):
            return _observation(match, created=False, corrected=False)
        if match is not None:
            updated = client.update_webhook(
                session_id,
                str(match["id"]),
                url=url,
                secret=secret,
                authorization=authorization,
                events=WEBHOOK_EVENTS,
                retry_count=WEBHOOK_RETRY_COUNT,
                timeout=_GATEWAY_TIMEOUT_SEC,
            )
            return _observation(updated, created=False, corrected=True)
        created = client.create_webhook(
            session_id,
            url=url,
            secret=secret,
            authorization=authorization,
            events=WEBHOOK_EVENTS,
            retry_count=WEBHOOK_RETRY_COUNT,
            timeout=_GATEWAY_TIMEOUT_SEC,
        )
        return _observation(created, created=True, corrected=False)

    def list_webhook(self, *, session_id: str, webhook_id: str, url: str) -> WebhookObservation | None:
        del url
        if not session_id or not webhook_id:
            return None
        try:
            rows = _client().list_webhooks(session_id, timeout=_GATEWAY_TIMEOUT_SEC)
        except Exception:
            return None
        for row in rows:
            if str(row.get("id") or "") == webhook_id:
                return _observation(row, created=False, corrected=False)
        return None

    def queue_proven(self, now: datetime) -> bool:
        del now
        token = frappe.generate_hash(length=16)
        key = f"{_PROBE_PREFIX}:{token}"
        try:
            frappe.enqueue(
                "almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_operation_runtime.mark_customer_bot_queue_probe",
                queue="short",
                timeout=30,
                enqueue_after_commit=False,
                token=token,
            )
        except Exception:
            return False
        deadline = time.monotonic() + _PROBE_WAIT_SEC
        while time.monotonic() < deadline:
            if queue_probe_is_done(key):
                return True
            time.sleep(0.05)
        return False

    def pdf_ready(self) -> bool:
        from pathlib import Path

        import shutil

        configured = str(frappe.get_common_site_config().get("chromium_path") or "").strip()
        if configured and (shutil.which(configured) or Path(configured).is_file()):
            return True
        for name in ("chromium", "chromium-browser", "google-chrome"):
            if shutil.which(name):
                return True
        bench = Path(frappe.utils.get_bench_path()) / "chromium" / "chrome-linux"
        return (bench / "headless_shell").is_file() or (bench / "chrome").is_file()

    def scheduler_enabled(self) -> bool:
        try:
            return bool(frappe.utils.cint(frappe.db.get_single_value("System Settings", "enable_scheduler")))
        except Exception:
            return False

    def activity(self) -> ActivityObservation:
        inbound = _max_timestamp(
            "tabCustomer Bot Inbound Event",
            "creation",
            "status='processed'",
        )
        accepted = _max_timestamp(
            "tabCustomer Bot Reply Intent",
            "modified",
            "status='accepted'",
        )
        return ActivityObservation(
            last_accepted_inbound_at=inbound,
            last_gateway_accept_at=accepted,
        )


def queue_probe_is_done(key: str) -> bool:
    """Read the worker's marker from Redis.

    ``frappe.cache.set_value`` also stores the value on ``frappe.local.cache``,
    and ``get_value`` returns that copy first. A marker written by this process
    would hide the worker's later update, so the poll skips the local copy.
    A missing marker is not cached.
    """

    value = frappe.cache.get_value(key, expires=True, use_local_cache=False)
    return value == "done"


def mark_customer_bot_queue_probe(token: str) -> None:
    """Short worker heartbeat. The token is not a credential."""

    if token and len(str(token)) <= 64:
        frappe.cache.set_value(f"{_PROBE_PREFIX}:{token}", "done", expires_in_sec=30)


def run_start() -> dict[str, object]:
    return start_customer_bot(FrappeCustomerBotOperation())


def run_stop() -> dict[str, object]:
    return stop_customer_bot(FrappeCustomerBotOperation())


def run_status() -> dict[str, object]:
    return read_operation_status(FrappeCustomerBotOperation())


def run_check() -> dict[str, object]:
    return check_customer_bot(FrappeCustomerBotOperation())


def reconcile_if_running() -> None:
    """Scheduler recovery. A stopped decision does not touch site_config or the gateway."""

    if not _has_operation_columns():
        return
    if str(_single("operation_decision") or "") != DECISION_RUNNING:
        return
    check_customer_bot(FrappeCustomerBotOperation())


def current_operation_generation() -> int:
    """The saved run cycle. A missing column is generation 0 and does not resume a newer one."""

    try:
        if not _has_operation_columns():
            return 0
        return int(_single("operation_generation") or 0)
    except Exception:
        return 0


def operation_decision_is_running() -> bool:
    try:
        if not _has_operation_columns():
            return False
        return str(_single("operation_decision") or "") == DECISION_RUNNING
    except Exception:
        return False


class _GateLock:
    def try_acquire(self) -> bool:
        row = frappe.db.sql("SELECT GET_LOCK(%s, 0)", (_LOCK,))
        return bool(row and row[0] and int(row[0][0] or 0) == 1)

    def release(self) -> None:
        frappe.db.sql("SELECT RELEASE_LOCK(%s)", (_LOCK,))


class _TransportGates:
    def disarm(self) -> None:
        from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_ops import (
            disarm_customer_bot_transport,
        )

        disarm_customer_bot_transport()

    def open_production(self) -> None:
        from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_ops import (
            set_customer_bot_ops_mode,
        )

        set_customer_bot_ops_mode("production", arm_transport=True)

    def rearm(self) -> None:
        from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_ops import (
            arm_customer_bot_transport,
        )

        arm_customer_bot_transport()

    def transport_armed(self) -> bool:
        from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_ops import (
            load_customer_bot_ops,
        )

        return bool(load_customer_bot_ops().transport_armed)


class _AcceptanceSwitch:
    def disable(self) -> None:
        _set_enabled(False)

    def enable(self) -> None:
        _set_enabled(True)


class _PendingReplies:
    def cancel_pending(self) -> int:
        if not frappe.db.table_exists("Customer Bot Reply Intent"):
            return 0
        frappe.db.sql(
            """update `tabCustomer Bot Reply Intent`
               set status='cancelled', modified=%s
               where status='pending'""",
            (frappe.utils.now(),),
        )
        frappe.db.commit()
        return 0


def _set_enabled(enabled: bool) -> None:
    from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_settings_repository import (
        FrappeCustomerBotSettingsRepository,
    )

    repository = FrappeCustomerBotSettingsRepository()
    snapshot = repository.load()
    repository.set_enabled(
        enabled,
        snapshot.revision,
        frappe.session.user or "Administrator",
        frappe.utils.now(),
    )


def _client() -> OpenWAClient:
    from almdina_erp.almdina_erp.infrastructure.whatsapp.config import load_openwa_config

    return OpenWAClient(load_openwa_config(), timeout=_GATEWAY_TIMEOUT_SEC)


def _ensure_ingest_account() -> None:
    if not frappe.db.exists("Role", INGEST_ROLE):
        frappe.get_doc(
            {"doctype": "Role", "role_name": INGEST_ROLE, "desk_access": 1}
        ).insert(ignore_permissions=True)
    if frappe.db.exists("User", INGEST_USER):
        user = frappe.get_doc("User", INGEST_USER)
    else:
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": INGEST_USER,
                "first_name": "Customer Bot Ingest",
                "enabled": 1,
                "send_welcome_email": 0,
                "user_type": "System User",
            }
        ).insert(ignore_permissions=True)
    if INGEST_ROLE not in {row.role for row in (user.roles or [])}:
        user.append("roles", {"role": INGEST_ROLE})
        user.save(ignore_permissions=True)
    if not frappe.db.exists(
        "Custom DocPerm",
        {"parent": DOCTYPE, "role": INGEST_ROLE, "permlevel": 0},
    ):
        frappe.get_doc(
            {
                "doctype": "Custom DocPerm",
                "parent": DOCTYPE,
                "parenttype": "DocType",
                "parentfield": "permissions",
                "role": INGEST_ROLE,
                "permlevel": 0,
                "ingest_customer_bot_inbound": 1,
            }
        ).insert(ignore_permissions=True)
    else:
        frappe.db.set_value(
            "Custom DocPerm",
            {"parent": DOCTYPE, "role": INGEST_ROLE, "permlevel": 0},
            "ingest_customer_bot_inbound",
            1,
            update_modified=False,
        )
    if not user.api_key:
        user.api_key = frappe.generate_hash(length=15)
        user.api_secret = frappe.generate_hash(length=15)
        user.save(ignore_permissions=True)
    frappe.db.commit()


def _webhook_credentials() -> tuple[str, str]:
    secret = str(
        get_decrypted_password(
            DOCTYPE,
            DOCTYPE,
            "openwa_webhook_secret",
            raise_exception=False,
        )
        or ""
    )
    user = frappe.get_doc("User", INGEST_USER)
    api_secret = str(
        get_decrypted_password("User", user.name, "api_secret", raise_exception=False) or ""
    )
    if not secret or not user.api_key or not api_secret:
        raise RuntimeError("webhook_credentials_missing")
    return secret, f"token {user.api_key}:{api_secret}"


def _match_webhook(
    rows: list[dict[str, object]],
    *,
    session_id: str,
    url: str,
    webhook_id: str,
) -> dict[str, object] | None:
    if webhook_id:
        for row in rows:
            if str(row.get("id") or "") == webhook_id and str(row.get("sessionId") or "") == session_id:
                return row
    for row in rows:
        if str(row.get("sessionId") or "") == session_id and str(row.get("url") or "") == url:
            return row
    return None


def _visible_match(row: dict[str, object], *, session_id: str, url: str) -> bool:
    events = tuple(str(item) for item in row.get("events") or [])
    return bool(
        str(row.get("sessionId") or "") == session_id
        and str(row.get("url") or "") == url
        and events == WEBHOOK_EVENTS
        and bool(row.get("active", True))
        and int(row.get("retryCount") or 0) == WEBHOOK_RETRY_COUNT
    )


def _observation(row: dict[str, object], *, created: bool, corrected: bool) -> WebhookObservation:
    return WebhookObservation(
        id=str(row.get("id") or ""),
        url=str(row.get("url") or ""),
        events=tuple(str(item) for item in row.get("events") or []),
        active=bool(row.get("active", True)),
        retry_count=int(row.get("retryCount") or 0),
        session_id=str(row.get("sessionId") or ""),
        created=created,
        corrected=corrected,
    )


def _has_operation_columns() -> bool:
    """Singles live in tabSingles, so a table-column check would always fail closed."""

    try:
        if not frappe.db.exists("DocType", DOCTYPE):
            return False
        return bool(frappe.get_meta(DOCTYPE).has_field("operation_decision"))
    except Exception:
        return False


def _single(field: str) -> object:
    return frappe.db.get_single_value(DOCTYPE, field)


def _write_operation(**fields: str) -> None:
    previous = getattr(frappe.flags, SERVICE_FLAG, False)
    setattr(frappe.flags, SERVICE_FLAG, True)
    try:
        for field, value in fields.items():
            frappe.db.set_single_value(DOCTYPE, field, value)
        frappe.db.commit()
    finally:
        setattr(frappe.flags, SERVICE_FLAG, previous)


def _stamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _max_timestamp(table: str, column: str, where: str) -> datetime | None:
    if not frappe.db.table_exists(table[3:] if table.startswith("tab") else table):
        return None
    try:
        row = frappe.db.sql(f"select max(`{column}`) from `{table}` where {where}")
    except Exception:
        return None
    if not row or not row[0] or not row[0][0]:
        return None
    value = row[0][0]
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return None


__all__ = [
    "FrappeCustomerBotOperation",
    "INGEST_ROLE",
    "INGEST_USER",
    "PUBLIC_BASE_KEY",
    "mark_customer_bot_queue_probe",
    "operation_decision_is_running",
    "reconcile_if_running",
    "run_check",
    "run_start",
    "run_status",
    "run_stop",
]
