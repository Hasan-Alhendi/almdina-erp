from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


SESSION_NAME_PREFIX = "almdina-"
MAX_SESSION_NAME_ATTEMPTS = 8
WORKING_STATUS = "ready"
QR_STATUSES = frozenset(
    {"created", "initializing", "qr_ready", "authenticating"}
)


class SessionNameError(ValueError):
    """Raised when a unique session name cannot be chosen."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class CreateSessionDecision:
    allowed: bool
    code: str
    reason: str


def is_working(status: object) -> bool:
    return str(status or "").strip() == WORKING_STATUS


def needs_qr(status: object) -> bool:
    return str(status or "").strip() in QR_STATUSES


def sessions_named(
    sessions: Sequence[Mapping[str, object]] | None,
    name: object,
) -> tuple[Mapping[str, object], ...]:
    """Return sessions whose name matches exactly. Other projects stay out."""

    target = str(name or "").strip()
    if not target:
        return ()
    return tuple(
        session
        for session in (sessions or ())
        if session and str(session.get("name") or "").strip() == target
    )


def unique_session_name(
    existing_names: Sequence[object] | None,
    draw,
) -> str:
    """Return a random session name that is not already used on the server."""

    taken = {str(name or "").strip() for name in (existing_names or ())}
    taken.discard("")
    for _ in range(MAX_SESSION_NAME_ATTEMPTS):
        suffix = str(draw() or "").strip()
        candidate = f"{SESSION_NAME_PREFIX}{suffix}"
        if suffix and candidate not in taken:
            return candidate
    raise SessionNameError(
        "name_exhausted",
        "تعذر توليد اسم جلسة فريد.",
    )


def should_create_session(
    stored_session_id: object,
    *,
    remote_exists: bool,
) -> CreateSessionDecision:
    """Allow a new session only when this site is not already bound to a live one."""

    stored = str(stored_session_id or "").strip()
    if stored and remote_exists:
        return CreateSessionDecision(
            False,
            "session_already_exists",
            "توجد جلسة WhatsApp واحدة بالفعل. لا يمكن إنشاء جلسة ثانية.",
        )
    return CreateSessionDecision(True, "allowed", "Allowed.")


__all__ = [
    "MAX_SESSION_NAME_ATTEMPTS",
    "QR_STATUSES",
    "SESSION_NAME_PREFIX",
    "WORKING_STATUS",
    "CreateSessionDecision",
    "SessionNameError",
    "is_working",
    "needs_qr",
    "sessions_named",
    "should_create_session",
    "unique_session_name",
]
