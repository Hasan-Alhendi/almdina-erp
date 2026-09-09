from __future__ import annotations

from dataclasses import dataclass


DATA_ENTRY = "DATA_ENTRY"
READY_TO_DISPATCH = "READY_TO_DISPATCH"
INTAKE_WORKFLOW_STAGES = frozenset({DATA_ENTRY, READY_TO_DISPATCH})


class IntakeLifecycleError(ValueError):
    """Raised when an order cannot move through the pre-production intake flow."""


class IntakePermissionError(PermissionError):
    """Raised when the current actor does not own the intake responsibility."""


@dataclass(frozen=True, slots=True)
class IntakeFacts:
    workflow_stage: str
    production_path: str
    current_production_stage: str
    current_assignee: str
    owner: str


def should_initialize_data_entry(facts: IntakeFacts) -> bool:
    """Return whether a persisted, never-dispatched order needs DATA_ENTRY."""

    return bool(
        not facts.workflow_stage
        and not facts.production_path
        and not facts.current_production_stage
    )


def assert_pending_dispatch_editable(
    facts: IntakeFacts,
    *,
    actor: str,
    is_admin: bool,
) -> None:
    """Validate the boundary between intake and real production execution."""

    if facts.workflow_stage not in INTAKE_WORKFLOW_STAGES:
        raise IntakeLifecycleError(
            "يمكن إنهاء إدخال البيانات أو تعديل خطة الإرسال فقط قبل بدء الإنتاج."
        )
    if facts.production_path or facts.current_production_stage:
        raise IntakeLifecycleError(
            "بدأ الإنتاج لهذا الطلب بالفعل؛ لا يمكن تعديل خطة الإرسال المعلقة."
        )
    if not is_admin and facts.current_assignee != actor:
        raise IntakePermissionError(
            "خطة الإرسال المعلقة تبقى تحت مسؤولية مدخل البيانات الحالي."
        )


def assert_ready_to_dispatch(
    facts: IntakeFacts,
    *,
    actor: str,
    is_admin: bool,
) -> None:
    """Validate the exact intake boundary for the real production-start command."""

    if facts.workflow_stage != READY_TO_DISPATCH:
        raise IntakeLifecycleError(
            "يمكن إرسال الطلب إلى الإنتاج فقط عندما يكون جاهزًا للإرسال."
        )
    if facts.production_path or facts.current_production_stage:
        raise IntakeLifecycleError("بدأ الإنتاج لهذا الطلب بالفعل.")
    if not is_admin and facts.current_assignee != actor:
        raise IntakePermissionError(
            "إرسال الطلب إلى الإنتاج يبقى تحت مسؤولية مدخل البيانات الحالي."
        )


def assert_legacy_dispatch_allowed(facts: IntakeFacts) -> None:
    """Fail closed when the retired dispatch path targets an intake-managed order.

    ALMADINA-162 owns DATA_ENTRY and READY_TO_DISPATCH as pre-production states.
    The legacy dispatch command creates a Production Stage immediately, so allowing
    it here would create an impossible mixed state (intake + active production).
    Legacy orders without an intake workflow stage remain backward compatible.
    """

    if facts.workflow_stage in INTAKE_WORKFLOW_STAGES:
        raise IntakeLifecycleError(
            "هذا الطلب ضمن دورة إدخال البيانات الجديدة؛ لا يمكن استخدام إرسال الإنتاج القديم."
        )


__all__ = [
    "DATA_ENTRY",
    "READY_TO_DISPATCH",
    "INTAKE_WORKFLOW_STAGES",
    "IntakeFacts",
    "IntakeLifecycleError",
    "IntakePermissionError",
    "assert_legacy_dispatch_allowed",
    "assert_pending_dispatch_editable",
    "assert_ready_to_dispatch",
    "should_initialize_data_entry",
]
