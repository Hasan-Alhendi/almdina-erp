from __future__ import annotations

from typing import Any

from almdina_erp.almdina_erp.domain.security.authorization import Capability


PLAN_COMMAND_FLAG = "almdina_cutting_plan_command_capability"
REPLACEMENT_PLAN_COMMAND_FLAG = "almdina_replacement_plan_command"
PLAN_COMMAND_CAPABILITIES = frozenset(
    {
        Capability.RECALCULATE_PLAN,
        Capability.EDIT_OPTIMIZER_SETTINGS,
        Capability.EDIT_COST_SETTINGS,
        Capability.UPLOAD_DXF,
        Capability.REPLACE_DXF,
        Capability.APPROVE_DXF,
    }
)


def _flag_value(doc: Any, flag: str) -> Any:
    flags = getattr(doc, "flags", None)
    if not flags:
        return None
    getter = getattr(flags, "get", None)
    return getter(flag) if callable(getter) else getattr(flags, flag, None)


def command_capability(doc: Any) -> str:
    return str(_flag_value(doc, PLAN_COMMAND_FLAG) or "").strip()


def is_authorized_plan_command(doc: Any) -> bool:
    """Return True only for a server-created, scoped plan command context.

    Browser payloads cannot persist either flag. Normal order-plan commands carry
    a plan-owned capability. Replacement approval uses a separate internal flag
    so its Replacement Piece capability never becomes an implicit Cutting Plan
    grant in the canonical permission catalog.
    """

    if command_capability(doc) in PLAN_COMMAND_CAPABILITIES:
        return True
    return _flag_value(doc, REPLACEMENT_PLAN_COMMAND_FLAG) is True


__all__ = [
    "PLAN_COMMAND_CAPABILITIES",
    "PLAN_COMMAND_FLAG",
    "REPLACEMENT_PLAN_COMMAND_FLAG",
    "command_capability",
    "is_authorized_plan_command",
]
