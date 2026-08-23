from __future__ import annotations

from dataclasses import dataclass


class DrawingApprovalDenied(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class DrawingApprovalState:
    status: str
    production_path: str
    current_department: str
    approved_plan: str


def is_at_drawing_stage(state: DrawingApprovalState) -> bool:
    if state.status == "At Drawing":
        return True
    if str(state.current_department or "").strip() == "رسم":
        return True
    return state.production_path == "Drawing"


def validate_drawing_approval(state: DrawingApprovalState) -> None:
    """Validate workflow state only; role grants are resolved by the adapter.

    Drawing approval intentionally does not depend on the assigned designer and
    does not reject an already-approved order. The administrator can grant the
    approval capability to any role, while a previous approval is presented as
    a warning before a replacement approval is created.
    """

    if not is_at_drawing_stage(state):
        raise DrawingApprovalDenied("not_at_drawing")


def approval_warning(state: DrawingApprovalState) -> str | None:
    return "already_approved" if state.approved_plan else None


__all__ = [
    "DrawingApprovalDenied",
    "DrawingApprovalState",
    "approval_warning",
    "is_at_drawing_stage",
    "validate_drawing_approval",
]
