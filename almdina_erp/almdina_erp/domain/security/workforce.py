from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from .authorization import Capability, WORKFORCE_CAPABILITIES, normalize_capabilities


@dataclass(frozen=True, slots=True)
class OperationalProfile:
    """Operational eligibility and default navigation, never business grants."""

    key: str
    label: str
    description: str
    roles: tuple[str, ...]
    default_workspace: str
    default_app: str = "almdina_erp"


_PROFILES = (
    OperationalProfile(
        "order_entry",
        "إدخال الطلبات",
        "إدخال الطلبات ومتابعتها من مساحة عمل المدينة.",
        ("Order Entry",),
        "Almdina ERP",
    ),
    OperationalProfile(
        "factory_manager",
        "مدير المعمل",
        "أهلية تشغيلية للإدارة والإنتاج والتكلفة دون منح صلاحيات أعمال تلقائيًا.",
        ("Order Entry", "Production Manager", "Accounts Management"),
        "Almdina ERP",
    ),
    OperationalProfile(
        "production_manager",
        "مشرف الإنتاج",
        "أهلية الإشراف على أقسام الإنتاج دون منح إجراءات إدارية تلقائيًا.",
        ("Production Manager",),
        "Almdina ERP",
    ),
    OperationalProfile(
        "accounts",
        "التكلفة والحسابات",
        "أهلية تشغيلية لقسم التكلفة؛ عرض البيانات المالية تحدده المصفوفة.",
        ("Accounts Management",),
        "Almdina ERP",
    ),
    OperationalProfile(
        "drawing_operator",
        "عامل الرسم",
        "مؤهل للإسناد إلى مرحلة الرسم.",
        ("عامل رسم",),
        "Shop Floor",
    ),
    OperationalProfile(
        "sharyoun_operator",
        "عامل الشريون",
        "مؤهل للإسناد إلى مرحلة الشريون.",
        ("عامل شريون",),
        "Shop Floor",
    ),
    OperationalProfile(
        "cnc_operator",
        "عامل CNC",
        "مؤهل للإسناد إلى مرحلة CNC.",
        ("عامل CNC",),
        "Shop Floor",
    ),
    OperationalProfile(
        "sanding_operator",
        "عامل التقشيط",
        "مؤهل للإسناد إلى مرحلة التقشيط.",
        ("عامل تقشيط",),
        "Shop Floor",
    ),
)

PROFILES = MappingProxyType({profile.key: profile for profile in _PROFILES})
MANAGED_OPERATIONAL_ROLES = frozenset(
    role for profile in _PROFILES for role in profile.roles
)
PROTECTED_USERS = frozenset({"Administrator", "Guest"})


class WorkforceAction(str, Enum):
    VIEW = "view"
    CREATE = "create"
    EDIT = "edit"
    ASSIGN_PROFILE = "assign_profile"
    ENABLE = "enable"
    DISABLE = "disable"
    RESET_PASSWORD = "reset_password"


ACTION_CAPABILITIES = MappingProxyType(
    {
        WorkforceAction.VIEW: Capability.VIEW_USERS,
        WorkforceAction.CREATE: Capability.CREATE_USERS,
        WorkforceAction.EDIT: Capability.EDIT_USERS,
        WorkforceAction.ASSIGN_PROFILE: Capability.ASSIGN_WORKFORCE_PROFILE,
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


def profile_for_key(profile_key: str) -> OperationalProfile:
    key = str(profile_key or "").strip()
    try:
        return PROFILES[key]
    except KeyError as exc:
        raise ValueError(f"Unknown workforce profile: {key}") from exc


def infer_profile(roles: Iterable[str] | None) -> str:
    managed = frozenset(str(role) for role in (roles or ()) if role).intersection(
        MANAGED_OPERATIONAL_ROLES
    )
    for profile in _PROFILES:
        if managed == frozenset(profile.roles):
            return profile.key
    return "custom" if managed else ""


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
    "MANAGED_OPERATIONAL_ROLES",
    "PROFILES",
    "PROTECTED_USERS",
    "OperationalProfile",
    "WorkforceAction",
    "WorkforceDecision",
    "WorkforceFacts",
    "action_context",
    "decide_workforce_action",
    "expand_workforce_capabilities",
    "infer_profile",
    "profile_for_key",
]
