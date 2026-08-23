from __future__ import annotations

from typing import Any

from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_command_context import (
    REPLACEMENT_PLAN_COMMAND_FLAG,
)


def _persist(
    plan: Any,
    operation: str,
    *,
    allow_status_transition: bool = False,
) -> Any:
    """Persist a replacement-owned Cutting Plan through normal Frappe checks.

    Replacement approval authorizes its business action before reaching this
    adapter. The ephemeral flag lets the Cutting Plan native permission hook
    recognize that server-owned command context without granting Desk CRUD and
    without bypassing Frappe permissions.
    """

    plan.flags[REPLACEMENT_PLAN_COMMAND_FLAG] = True
    if allow_status_transition:
        plan.flags.allow_status_transition = True
    try:
        if operation == "insert":
            plan.insert()
        elif operation == "save":
            plan.save()
        else:
            raise ValueError(f"Unsupported replacement plan operation: {operation}")
    finally:
        plan.flags.pop(REPLACEMENT_PLAN_COMMAND_FLAG, None)
        if allow_status_transition:
            plan.flags.pop("allow_status_transition", None)
    return plan


def insert_replacement_plan(plan: Any) -> Any:
    return _persist(plan, "insert")


def approve_replacement_plan(plan: Any) -> Any:
    return _persist(plan, "save", allow_status_transition=True)


__all__ = ["approve_replacement_plan", "insert_replacement_plan"]
