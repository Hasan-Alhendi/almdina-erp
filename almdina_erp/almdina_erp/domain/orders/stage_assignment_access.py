from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StageAssignmentDecision:
    allowed: bool
    code: str
    reason: str


def decide_stage_assignment_access(
    *,
    actor: str | None,
    assigned_to: str | None,
    has_current_stage: bool,
    has_production_path: bool,
    is_admin: bool = False,
) -> StageAssignmentDecision:
    """Authorize a stage-scoped mutation by assignment, never by role name.

    Before a route exists, capabilities and the feature lifecycle are sufficient.
    Once routed, an active stage belongs to its explicit assignee. A route with no
    active stage is already finished/closed and therefore cannot be mutated.
    """

    if is_admin:
        return StageAssignmentDecision(True, "allowed", "")

    if not has_current_stage:
        if has_production_path:
            return StageAssignmentDecision(
                False,
                "no_active_stage",
                "لا يمكن تعديل الطلب بعد مغادرته مراحل الإنتاج النشطة.",
            )
        return StageAssignmentDecision(True, "pre_production", "")

    resolved_actor = str(actor or "").strip()
    resolved_assignee = str(assigned_to or "").strip()
    if not resolved_assignee:
        return StageAssignmentDecision(
            False,
            "stage_unassigned",
            "المرحلة الحالية غير مسندة إلى مستخدم. أسندها أولًا ثم أعد المحاولة.",
        )
    if not resolved_actor or resolved_actor != resolved_assignee:
        return StageAssignmentDecision(
            False,
            "not_assigned",
            "هذا الطلب مسند حاليًا إلى مستخدم آخر. يمكنك عرضه فقط.",
        )
    return StageAssignmentDecision(True, "allowed", "")


__all__ = ["StageAssignmentDecision", "decide_stage_assignment_access"]
