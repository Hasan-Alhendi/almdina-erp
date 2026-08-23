from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from .authorization import Capability, normalize_capabilities


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
        WorkforceAction.ASSIGN_ROLES: Capability.ASSIGN_USER_ROLES,
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


def decide_workforce_action(
    capabilities: Iterable[str] | None,
    *,
    action: WorkforceAction,
    facts: WorkforceFacts,
) -> WorkforceDecision:
    granted = normalize_capabilities(capabilities)
    required = ACTION_CAPABILITIES[action]
    if required not in granted:
        return WorkforceDecision(
            False,
            "missing_capability",
            "لا تملك الصلاحية المطلوبة لتنفيذ هذا الإجراء على مستخدمي المعمل.",
        )

    if action in {WorkforceAction.VIEW, WorkforceAction.CREATE}:
        return WorkforceDecision(True, "allowed", "مسموح.")

    if facts.target_user in PROTECTED_USERS:
        return WorkforceDecision(
            False,
            "protected_user",
            "لا يمكن تعديل حساب Administrator أو Guest من إدارة مستخدمي المعمل.",
        )
    if not facts.target_is_almdina:
        return WorkforceDecision(
            False,
            "outside_scope",
            "هذا الحساب غير مضاف إلى نطاق مستخدمي معمل Almdina.",
        )
    if action == WorkforceAction.ASSIGN_ROLES:
        if facts.target_user == facts.actor:
            return WorkforceDecision(
                False,
                "self_role_change",
                "لا يمكنك تغيير أدوارك من حسابك الحالي. استخدم حساب مسؤول صلاحيات آخر.",
            )
        if facts.active_assignments > 0:
            return WorkforceDecision(
                False,
                "active_assignments",
                "أعد إسناد مراحل الإنتاج النشطة لهذا المستخدم قبل تغيير أدواره.",
            )
    if action == WorkforceAction.DISABLE:
        if facts.target_user == facts.actor:
            return WorkforceDecision(
                False,
                "self_disable",
                "لا يمكنك تعطيل حسابك الحالي.",
            )
        if not facts.target_enabled:
            return WorkforceDecision(False, "already_disabled", "حساب المستخدم معطّل بالفعل.")
        if facts.active_assignments > 0:
            return WorkforceDecision(
                False,
                "active_assignments",
                "أعد إسناد مراحل الإنتاج النشطة لهذا المستخدم قبل تعطيل حسابه.",
            )
    if action == WorkforceAction.ENABLE and facts.target_enabled:
        return WorkforceDecision(False, "already_enabled", "حساب المستخدم مفعّل بالفعل.")

    return WorkforceDecision(True, "allowed", "مسموح.")


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
        for decision in [decide_workforce_action(capabilities, action=action, facts=facts)]
    }


__all__ = [
    "ACTION_CAPABILITIES",
    "PROTECTED_USERS",
    "WorkforceAction",
    "WorkforceDecision",
    "WorkforceFacts",
    "action_context",
    "decide_workforce_action",
]
