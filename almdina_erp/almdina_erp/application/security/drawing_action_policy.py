from __future__ import annotations

from dataclasses import dataclass

from almdina_erp.almdina_erp.domain.security.authorization import Capability


class DrawingActionDenied(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class DrawingActionState:
    status: str
    production_path: str
    current_department: str
    current_assignee: str
    session_user: str
    approved_plan: str
    production_dxf: str


def is_at_drawing_stage(state: DrawingActionState) -> bool:
    return state.status == "At Drawing" or (
        state.production_path == "Drawing" and state.current_department == "رسم"
    )


def validate_assigned_drawing_action(
    state: DrawingActionState,
    *,
    require_unlocked_plan: bool = True,
) -> None:
    """Enforce the invariant that the assigned designer owns drawing changes."""

    if not is_at_drawing_stage(state):
        raise DrawingActionDenied("not_at_drawing")
    if not state.current_assignee:
        raise DrawingActionDenied("designer_not_assigned")
    if state.current_assignee != state.session_user:
        raise DrawingActionDenied("not_assigned_designer")
    if require_unlocked_plan and state.approved_plan:
        raise DrawingActionDenied("plan_already_approved")


def required_upload_capability(state: DrawingActionState) -> str:
    return Capability.REPLACE_DXF if state.production_dxf else Capability.UPLOAD_DXF


def validate_plan_source(
    plan_source: str,
    *,
    has_system_plan: bool,
    has_custom_plan: bool,
    has_production_dxf: bool,
) -> str:
    source = str(plan_source or "System").strip()
    if source not in {"System", "Custom"}:
        raise DrawingActionDenied("unsupported_plan_source")
    if source == "System" and not has_system_plan:
        raise DrawingActionDenied("system_plan_missing")
    if source == "Custom" and (not has_custom_plan or not has_production_dxf):
        raise DrawingActionDenied("custom_plan_missing")
    return source


__all__ = [
    "DrawingActionDenied",
    "DrawingActionState",
    "is_at_drawing_stage",
    "required_upload_capability",
    "validate_assigned_drawing_action",
    "validate_plan_source",
]
