from __future__ import annotations

from typing import Any

from almdina_erp.almdina_erp.domain.security.authorization import Capability


PLAN_COMMAND_FLAG = "almdina_cutting_plan_command_capability"
PLAN_COMMAND_CAPABILITIES = frozenset(
    {
        Capability.RECALCULATE_PLAN,
        Capability.EDIT_OPTIMIZER_SETTINGS,
        Capability.UPLOAD_DXF,
        Capability.REPLACE_DXF,
        Capability.APPROVE_DXF,
    }
)


def command_capability(doc: Any) -> str:
    flags = getattr(doc, "flags", None)
    if not flags:
        return ""
    getter = getattr(flags, "get", None)
    value = getter(PLAN_COMMAND_FLAG) if callable(getter) else getattr(flags, PLAN_COMMAND_FLAG, "")
    return str(value or "").strip()


def is_authorized_plan_command(doc: Any) -> bool:
    """Return True only for a server-created, scoped plan command context.

    The flag lives on ``Document.flags`` and is never persisted or accepted from
    a browser payload. Command services set it only after the related order has
    passed capability and lifecycle authorization.
    """

    return command_capability(doc) in PLAN_COMMAND_CAPABILITIES


__all__ = [
    "PLAN_COMMAND_CAPABILITIES",
    "PLAN_COMMAND_FLAG",
    "command_capability",
    "is_authorized_plan_command",
]
