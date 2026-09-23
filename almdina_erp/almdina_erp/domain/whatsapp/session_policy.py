from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


FACTORY_SESSION_NAME = "almdina-factory"
WORKING_STATUS = "ready"
QR_STATUSES = frozenset(
    {"created", "initializing", "qr_ready", "authenticating"}
)


@dataclass(frozen=True, slots=True)
class CreateSessionDecision:
    allowed: bool
    code: str
    reason: str


def _name_of(session: Mapping[str, object]) -> str:
    return str(session.get("name") or "").strip()


def is_working(status: object) -> bool:
    return str(status or "").strip() == WORKING_STATUS


def needs_qr(status: object) -> bool:
    return str(status or "").strip() in QR_STATUSES


def select_factory_session(
    sessions: Sequence[Mapping[str, object]] | None,
) -> Mapping[str, object] | None:
    """Bind to the factory session, or to the only existing OpenWA session."""

    rows = tuple(session for session in (sessions or ()) if session)
    if not rows:
        return None
    for session in rows:
        if _name_of(session) == FACTORY_SESSION_NAME:
            return session
    return rows[0]


def should_create_session(
    sessions: Sequence[Mapping[str, object]] | None,
) -> CreateSessionDecision:
    if tuple(sessions or ()):
        return CreateSessionDecision(
            False,
            "session_already_exists",
            "توجد جلسة WhatsApp واحدة بالفعل. لا يمكن إنشاء جلسة ثانية.",
        )
    return CreateSessionDecision(True, "allowed", "Allowed.")


__all__ = [
    "FACTORY_SESSION_NAME",
    "QR_STATUSES",
    "WORKING_STATUS",
    "CreateSessionDecision",
    "is_working",
    "needs_qr",
    "select_factory_session",
    "should_create_session",
]
