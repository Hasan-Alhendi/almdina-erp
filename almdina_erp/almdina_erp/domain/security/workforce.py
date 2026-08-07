from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from .authorization import Capability, WORKFORCE_CAPABILITIES, normalize_capabilities


PROTECTED_USERS = frozenset({"Administrator", "Guest"})


class WorkforceAction(str, Enum):
    VIEW = "view"
    CREATE = "create"
    EDIT = "edit"
    ASSIGN_ROLES = "assign_roles"
    ENABLE = "enable"
    DISABLE = "disable"
    RESET_PASSWORD = "reset_password"


ACTION_CAPABILITIES = MappingProxyType(
    {
        WorkforceAction.VIEW: Capability.VIEW_USERS,
        WorkforceAction.CREATE: Capability.CREATE_USERS,
        WorkforceAction.EDIT: Capability.EDIT_USERS,
        # Keep the persisted capability key for backward compatibility with
        # existing Custom DocPerm rows. The product concept is now direct role
        # assignment; there is no operational-profile layer anymore.
        WorkforceAction.ASSIGN_ROLES: Capability.ASSIGN_WORKFORCE_PROFILE,
        WorkforceAction.ENABLE: Capability.ENABLE_USERS,
        WorkforceAction.DISABLE: Capability.DISABLE_USERS,
        WorkforceAction.RESET_PASSWORD: Capability.RESET_USER_PASSWORD,
    }
)


@dataclass(frozen=True, slots=True)
class WorkforceFacts:
    actor: str
    target_user: str = ""
    target_enabled: bool = True
    target_is_almdina: bool = True
    active_assignments: int = 0


@dataclass(frozen=True, slots=True)
class WorkforceDecision:
    allowed: bool
    code: str
    reason: str


def expand_workforce_capabilities(
    capabilities: Iterable[str] | None,
) -> frozenset[str]:
    granted = set(normalize_capabilities(capabilities))
    if Capability.MANAGE_USERS in granted:
        granted.update(WORKFORCE_CAPABILITIES)
    return frozenset(granted)


def decide_workforce_action(
    capabilities: Iterable[str] | None,
    *,
    action: WorkforceAction,
    facts: WorkforceFacts,
) -> WorkforceDecision:
    granted = expand_workforce_capabilities(capabilities)
    required = ACTION_CAPABILITIES[action]
    if required not in granted:
        return WorkforceDecision(
            False,
            "missing_capability",
            "You do not have permission for this workforce action.",
        )

    if action in {WorkforceAction.VIEW, WorkforceAction.CREATE}:
        return WorkforceDecision(True, "allowed", "Allowed.")

    if facts.target_user in PROTECTED_USERS:
        return WorkforceDecision(
            False,
            "protected_user",
            "Administrator and Guest cannot be changed from the Almdina workforce console.",
        )
    if not facts.target_is_almdina:
        return WorkforceDecision(
            False,
            "outside_scope",
            "This account is outside the Almdina workforce scope.",
        )
    if action == WorkforceAction.ASSIGN_ROLES and facts.active_assignments > 0:
        return WorkforceDecision(
            False,
            "active_assignments",
            "Reassign the user's active production stages before changing roles.",
        )
    if action == WorkforceAction.DISABLE:
        if facts.target_user == facts.actor:
            return WorkforceDecision(
                False,
                "self_disable",
                "You cannot disable your own account.",
            )
        if not facts.target_enabled:
            return WorkforceDecision(False, "already_disabled", "User is already disabled.")
        if facts.active_assignments > 0:
            return WorkforceDecision(
                False,
                "active_assignments",
                "Reassign the user's active production stages before disabling the account.",
            )
    if action == WorkforceAction.ENABLE and facts.target_enabled:
        return WorkforceDecision(False, "already_enabled", "User is already enabled.")

    return WorkforceDecision(True, "allowed", "Allowed.")


def action_context(
    capabilities: Iterable[str] | None,
    *,
    facts: WorkforceFacts,
) -> dict[str, dict[str, object]]:
    return {
        action.value: {
            "allowed": decision.allowed,
            "code": decision.code,
            "reason": decision.reason,
        }
        for action in WorkforceAction
        for decision in [
            decide_workforce_action(capabilities, action=action, facts=facts)
        ]
    }


__all__ = [
    "ACTION_CAPABILITIES",
    "PROTECTED_USERS",
    "WorkforceAction",
    "WorkforceDecision",
    "WorkforceFacts",
    "action_context",
    "decide_workforce_action",
    "expand_workforce_capabilities",
]
