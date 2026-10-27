"""Customer-bot run decision and operational state.

The manager decision is ``stopped`` or ``running``. The operational state is
derived from that decision plus the latest readiness result. A technical
failure does not clear a saved ``running`` decision. Migrate and a stopped
decision never arm transport.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

DECISION_STOPPED = "stopped"
DECISION_RUNNING = "running"
DECISIONS = frozenset({DECISION_STOPPED, DECISION_RUNNING})

STATE_STOPPED = "stopped"
STATE_NEEDS_SETUP = "needs_setup"
STATE_ACTIVATING = "activating"
STATE_READY = "ready"
STATE_DEGRADED = "degraded"
STATES = frozenset(
    {
        STATE_STOPPED,
        STATE_NEEDS_SETUP,
        STATE_ACTIVATING,
        STATE_READY,
        STATE_DEGRADED,
    }
)

SESSION_READY = "ready"
SESSION_LOGIN_REQUIRED = "login_required"
SESSION_MISSING = "missing"
SESSION_UNREACHABLE = "unreachable"

# Gateway statuses that mean the factory must link WhatsApp again.
# ``disconnected`` is a temporary drop, not confirmed login loss.
_LOGIN_REQUIRED_GATEWAY_STATUSES = frozenset({"created", "qr_ready", "action_required"})


def classify_gateway_session(status: str) -> str:
    """Map one gateway session status onto the bot's session observation.

    ``ready`` is connected. ``created``, ``qr_ready``, and ``action_required``
    are confirmed needs to link again. ``disconnected``, ``failed``,
    ``initializing``, and ``authenticating`` stay a connection fault so a
    saved run decision and the session id can recover.
    """

    value = str(status or "").strip().lower()
    if value == SESSION_READY:
        return SESSION_READY
    if value in _LOGIN_REQUIRED_GATEWAY_STATUSES:
        return SESSION_LOGIN_REQUIRED
    return SESSION_UNREACHABLE

DEFAULT_REPLY_VALIDITY = timedelta(minutes=5)
WEBHOOK_EVENTS = ("message.received",)
WEBHOOK_RETRY_COUNT = 3

REASON_TEXTS = "texts_invalid"
REASON_SESSION_MISSING = "session_missing"
REASON_SESSION_LOGIN = "session_login_required"
REASON_SESSION_UNREACHABLE = "session_unreachable"
REASON_SESSION_MISMATCH = "session_mismatch"
REASON_PUBLIC_URL = "public_base_url_missing"
REASON_INGEST = "ingest_user_failed"
REASON_SECRET = "webhook_secret_failed"
REASON_WEBHOOK = "webhook_failed"
REASON_WEBHOOK_ROLE = "gateway_key_role_insufficient"
REASON_QUEUE = "queue_unproven"
REASON_PDF = "pdf_unavailable"
REASON_SCHEDULER = "scheduler_disabled"
REASON_BUSY = "operation_busy"
REASON_SUPERSEDED = "superseded"
REASON_REPLY_EXPIRED = "reply_expired"


@dataclass(frozen=True, slots=True)
class OperationRecord:
    decision: str = DECISION_STOPPED
    state: str = STATE_STOPPED
    generation: int = 0
    reason: str = ""
    webhook_id: str = ""
    ingest_user: str = ""
    queue_ok: bool = False
    queue_checked_at: datetime | None = None
    last_error: str = ""

    def __post_init__(self) -> None:
        if self.decision not in DECISIONS:
            raise ValueError("invalid operation decision")
        if self.state not in STATES:
            raise ValueError("invalid operation state")
        if type(self.generation) is not int or self.generation < 0:
            raise ValueError("generation must be a non-negative integer")


def callback_url(public_base: str, callback_path: str) -> str:
    """Join a trusted public base with a caller-supplied callback path.

    The path belongs to the adapter that owns the inbound method. This check
    only rejects a base or path that is not a plain site URL.
    """

    base = str(public_base or "").strip().rstrip("/")
    path = str(callback_path or "").strip()
    if not base.startswith(("https://", "http://")) or "://" not in base[1:]:
        raise ValueError(REASON_PUBLIC_URL)
    host = base.split("://", 1)[1]
    if not host or "@" in host or host.startswith("/") or " " in base:
        raise ValueError(REASON_PUBLIC_URL)
    if (
        not path.startswith("/")
        or path.startswith("//")
        or "\\" in path
        or "://" in path
        or " " in path
        or ".." in path
    ):
        raise ValueError(REASON_PUBLIC_URL)
    return f"{base}{path}"


def reply_validity_cancel_reason(
    created_on: datetime | None,
    now: datetime,
    *,
    validity: timedelta = DEFAULT_REPLY_VALIDITY,
) -> str | None:
    """Cancel a pending reply that is older than the central validity window.

    ``None`` means the row has no creation time and is not expired by this
    rule. Unknown gateway outcomes are not selected here.
    """

    if created_on is None:
        return None
    if created_on.tzinfo is None:
        created_on = created_on.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if now - created_on > validity:
        return REASON_REPLY_EXPIRED
    return None


__all__ = [
    "DECISION_RUNNING",
    "DECISION_STOPPED",
    "DEFAULT_REPLY_VALIDITY",
    "OperationRecord",
    "REASON_BUSY",
    "REASON_INGEST",
    "REASON_PDF",
    "REASON_PUBLIC_URL",
    "REASON_QUEUE",
    "REASON_REPLY_EXPIRED",
    "REASON_SCHEDULER",
    "REASON_SECRET",
    "REASON_SESSION_LOGIN",
    "REASON_SESSION_MISMATCH",
    "REASON_SESSION_MISSING",
    "REASON_SESSION_UNREACHABLE",
    "REASON_SUPERSEDED",
    "REASON_TEXTS",
    "REASON_WEBHOOK",
    "REASON_WEBHOOK_ROLE",
    "SESSION_LOGIN_REQUIRED",
    "SESSION_MISSING",
    "SESSION_READY",
    "SESSION_UNREACHABLE",
    "STATE_ACTIVATING",
    "STATE_DEGRADED",
    "STATE_NEEDS_SETUP",
    "STATE_READY",
    "STATE_STOPPED",
    "WEBHOOK_EVENTS",
    "WEBHOOK_RETRY_COUNT",
    "callback_url",
    "classify_gateway_session",
    "reply_validity_cancel_reason",
]
