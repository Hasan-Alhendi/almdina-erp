"""Domain rules for stage-scoped worker mutations via operational role."""

from __future__ import annotations

from collections.abc import Iterable

from almdina_erp.almdina_erp.domain.security.authorization import Capability


# Mutations that a shop-floor worker may only perform while the order sits on a
# production stage whose configured operational role the actor currently holds.
# Capability grants alone are never enough for these actions.
STAGE_SCOPED_MUTATION_CAPABILITIES = frozenset(
    {
        Capability.START_ASSIGNED_STAGE,
        Capability.HANDOFF_ASSIGNED_STAGE,
        Capability.UPLOAD_DXF,
        Capability.REPLACE_DXF,
        Capability.EXPORT_DXF,
        Capability.EDIT_SPECIAL_DRAWING,
        Capability.APPROVE_DXF,
        Capability.RECALCULATE_PLAN,
        Capability.EDIT_OPTIMIZER_SETTINGS,
        Capability.RECORD_INCIDENT,
    }
)


def actor_holds_operational_role(
    actor_roles: Iterable[str] | None,
    operational_role: str | None,
    *,
    is_admin: bool = False,
) -> bool:
    if is_admin:
        return True
    role = str(operational_role or "").strip()
    if not role:
        return False
    return role in {str(value).strip() for value in (actor_roles or ()) if str(value).strip()}


def decide_stage_scoped_mutation(
    *,
    actor_roles: Iterable[str] | None,
    operational_role: str | None,
    has_current_stage: bool,
    is_admin: bool = False,
) -> tuple[bool, str, str]:
    """Return ``(allowed, code, reason)`` for a stage-scoped worker mutation."""

    if is_admin:
        return True, "allowed", ""
    if not has_current_stage:
        return (
            False,
            "no_active_stage",
            "لا يمكن التعديل إلا عندما يكون الطلب في مرحلة إنتاج نشطة ضمن المسار.",
        )
    role = str(operational_role or "").strip()
    if not role:
        return (
            False,
            "missing_stage_role",
            "مرحلة الإنتاج الحالية لا تحتوي على دور تشغيلي مضبوط.",
        )
    if not actor_holds_operational_role(actor_roles, role, is_admin=False):
        return (
            False,
            "missing_operational_role",
            f"هذا الإجراء متاح فقط لمن يملك الدور التشغيلي «{role}» للمرحلة الحالية.",
        )
    return True, "allowed", ""


__all__ = [
    "STAGE_SCOPED_MUTATION_CAPABILITIES",
    "actor_holds_operational_role",
    "decide_stage_scoped_mutation",
]
