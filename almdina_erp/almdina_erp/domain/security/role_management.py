from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum


PROTECTED_ROLE_NAMES = frozenset(
    {
        "Administrator",
        "All",
        "Desk User",
        "Guest",
        "System Manager",
    }
)


class RoleAction(str, Enum):
    """Administrative actions that can be evaluated without Frappe imports."""

    VIEW = "view"
    CREATE = "create"
    EDIT = "edit"
    ENABLE = "enable"
    DISABLE = "disable"
    DELETE = "delete"
    ASSIGN = "assign"
    MANAGE_PERMISSIONS = "manage_permissions"


@dataclass(frozen=True, slots=True)
class RoleDefinition:
    """A role created by an administrator.

    Roles deliberately carry no default capabilities. Business grants are
    persisted separately by the permission matrix and selected explicitly.
    """

    name: str
    description: str = ""
    enabled: bool = True
    is_almdina_role: bool = True


@dataclass(frozen=True, slots=True)
class RoleFacts:
    """State needed to decide one role action.

    Actor is optional at this pure domain boundary because current rules are
    based on the target role and its references. Application services may pass
    it for audit and future actor-aware policies without coupling this module to
    Frappe sessions.
    """

    actor: str = ""
    role_name: str = ""
    role_exists: bool = True
    role_enabled: bool = True
    role_is_custom: bool = True
    assigned_users: int = 0
    production_routing_references: int = 0
    workflow_references: int = 0
    production_stage_references: int = 0
    active_stage_references: int = 0
    permission_count: int = 0


@dataclass(frozen=True, slots=True)
class RoleDecision:
    allowed: bool
    code: str
    reason: str


def normalize_role_name(value: str | None) -> str:
    name = " ".join(str(value or "").split())
    if not name:
        raise ValueError("Role name is required.")
    if len(name) > 140:
        raise ValueError("Role name cannot exceed 140 characters.")
    return name


def normalize_role_description(value: str | None) -> str:
    description = " ".join(str(value or "").split())
    if len(description) > 500:
        raise ValueError("Role description cannot exceed 500 characters.")
    return description


def new_role_definition(
    *,
    name: str,
    description: str | None = None,
    enabled: bool = True,
) -> RoleDefinition:
    """Create a normalized role contract with zero implicit permissions."""

    return RoleDefinition(
        name=normalize_role_name(name),
        description=normalize_role_description(description),
        enabled=bool(enabled),
        is_almdina_role=True,
    )


def normalize_role_capabilities(
    raw: Mapping[str, object] | None,
    *,
    allowed_capabilities: Iterable[str],
) -> dict[str, bool]:
    """Validate an exact role matrix without adding hidden dependencies.

    Dependency validation belongs to the application layer, which can return a
    clear error explaining which explicit grants are still required. This
    function never enables another capability silently.
    """

    allowed = frozenset(str(value) for value in allowed_capabilities)
    supplied = {str(key): value for key, value in dict(raw or {}).items()}
    unknown = set(supplied).difference(allowed)
    if unknown:
        raise ValueError(f"Unknown capabilities: {', '.join(sorted(unknown))}")
    return {
        capability: supplied.get(capability) is True
        for capability in sorted(allowed)
    }


def effective_capabilities(
    role_states: Iterable[Mapping[str, object]] | None,
) -> frozenset[str]:
    """Return the additive union of all capabilities granted by user roles."""

    granted: set[str] = set()
    for state in role_states or ():
        granted.update(
            str(capability)
            for capability, enabled in state.items()
            if enabled is True
        )
    return frozenset(granted)


def _delete_blockers(facts: RoleFacts) -> dict[str, int]:
    return {
        "assigned_users": int(facts.assigned_users or 0),
        "production_routing_references": int(
            facts.production_routing_references or 0
        ),
        "workflow_references": int(facts.workflow_references or 0),
        "production_stage_references": int(
            facts.production_stage_references or 0
        ),
        "active_stage_references": int(facts.active_stage_references or 0),
        "permission_count": int(facts.permission_count or 0),
    }


def decide_role_action(
    *,
    action: RoleAction,
    facts: RoleFacts,
) -> RoleDecision:
    role_name = normalize_role_name(facts.role_name) if facts.role_name else ""

    if action == RoleAction.VIEW:
        return RoleDecision(True, "allowed", "Allowed.")

    if action == RoleAction.CREATE:
        if facts.role_exists:
            return RoleDecision(False, "already_exists", "Role already exists.")
        if role_name in PROTECTED_ROLE_NAMES:
            return RoleDecision(
                False,
                "protected_role",
                "This framework role name is protected.",
            )
        return RoleDecision(True, "allowed", "Allowed.")

    if not facts.role_exists:
        return RoleDecision(False, "missing_role", "Role does not exist.")

    if role_name in PROTECTED_ROLE_NAMES:
        return RoleDecision(
            False,
            "protected_role",
            "This framework role is protected from the Almdina role console.",
        )

    if action in {
        RoleAction.EDIT,
        RoleAction.ENABLE,
        RoleAction.DISABLE,
        RoleAction.DELETE,
    } and not facts.role_is_custom:
        return RoleDecision(
            False,
            "standard_framework_role",
            "Standard framework roles cannot be renamed, disabled or deleted "
            "from the Almdina role console.",
        )

    if action == RoleAction.ASSIGN:
        if not facts.role_enabled:
            return RoleDecision(
                False,
                "disabled_role",
                "Disabled roles cannot be assigned to users.",
            )
        return RoleDecision(True, "allowed", "Allowed.")

    if action == RoleAction.ENABLE:
        if facts.role_enabled:
            return RoleDecision(False, "already_enabled", "Role is already enabled.")
        return RoleDecision(True, "allowed", "Allowed.")

    if action == RoleAction.DISABLE:
        if not facts.role_enabled:
            return RoleDecision(False, "already_disabled", "Role is already disabled.")
        active_references = {
            "assigned_users": int(facts.assigned_users or 0),
            "production_routing_references": int(
                facts.production_routing_references or 0
            ),
            "workflow_references": int(facts.workflow_references or 0),
            "active_stage_references": int(facts.active_stage_references or 0),
        }
        if any(active_references.values()):
            return RoleDecision(
                False,
                "role_in_active_use",
                "Remove assigned users and the role from active production routes, "
                "workflows and active stages before disabling it.",
            )
        return RoleDecision(True, "allowed", "Allowed.")

    if action == RoleAction.DELETE:
        blockers = _delete_blockers(facts)
        if any(blockers.values()):
            return RoleDecision(
                False,
                "role_in_use",
                "Remove role assignments, permissions, workflow references and "
                "production references before deleting the role.",
            )

    return RoleDecision(True, "allowed", "Allowed.")


def action_context(facts: RoleFacts) -> dict[str, dict[str, object]]:
    """Return action availability for a role-management interface."""

    return {
        action.value: {
            "allowed": decision.allowed,
            "code": decision.code,
            "reason": decision.reason,
        }
        for action in RoleAction
        for decision in [decide_role_action(action=action, facts=facts)]
    }


__all__ = [
    "PROTECTED_ROLE_NAMES",
    "RoleAction",
    "RoleDecision",
    "RoleDefinition",
    "RoleFacts",
    "action_context",
    "decide_role_action",
    "effective_capabilities",
    "new_role_definition",
    "normalize_role_capabilities",
    "normalize_role_description",
    "normalize_role_name",
]
