from __future__ import annotations

from dataclasses import dataclass


DRAFT = "Draft"
APPROVED = "Approved"
SUPERSEDED = "Superseded"
CANCELLED = "Cancelled"
SYSTEM = "System"
UPLOADED_DXF = "Uploaded DXF"

EDITABLE_STATUSES = frozenset({DRAFT})
TERMINAL_STATUSES = frozenset({SUPERSEDED, CANCELLED})
SUPPORTED_SOURCES = frozenset({SYSTEM, UPLOADED_DXF})


class CuttingPlanLifecycleError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CuttingPlanRevision:
    revision: int
    status: str
    source_type: str
    based_on_plan: str | None = None


def normalize_source_type(value: str | None) -> str:
    source = str(value or SYSTEM).strip() or SYSTEM
    if source not in SUPPORTED_SOURCES:
        raise CuttingPlanLifecycleError(f"unsupported_source_type:{source}")
    return source


def ensure_draft_editable(status: str | None) -> None:
    normalized = str(status or DRAFT).strip() or DRAFT
    if normalized not in EDITABLE_STATUSES:
        raise CuttingPlanLifecycleError(f"plan_not_editable:{normalized}")


def next_revision(existing_revisions: list[int] | tuple[int, ...]) -> int:
    normalized = [int(value) for value in existing_revisions if int(value) > 0]
    return (max(normalized) if normalized else 0) + 1


def revision_from_approved(
    *,
    current_name: str,
    current_revision: int,
    current_status: str,
    source_type: str,
) -> CuttingPlanRevision:
    if str(current_status or "") != APPROVED:
        raise CuttingPlanLifecycleError("revision_source_must_be_approved")
    return CuttingPlanRevision(
        revision=max(1, int(current_revision or 1)) + 1,
        status=DRAFT,
        source_type=normalize_source_type(source_type),
        based_on_plan=str(current_name or "").strip() or None,
    )


def approval_transition(status: str | None) -> tuple[str, str]:
    ensure_draft_editable(status)
    return DRAFT, APPROVED


def supersede_transition(status: str | None) -> tuple[str, str]:
    normalized = str(status or "").strip()
    if normalized != APPROVED:
        raise CuttingPlanLifecycleError("only_approved_plan_can_be_superseded")
    return APPROVED, SUPERSEDED


__all__ = [
    "APPROVED",
    "CANCELLED",
    "DRAFT",
    "EDITABLE_STATUSES",
    "SYSTEM",
    "SUPERSEDED",
    "SUPPORTED_SOURCES",
    "TERMINAL_STATUSES",
    "UPLOADED_DXF",
    "CuttingPlanLifecycleError",
    "CuttingPlanRevision",
    "approval_transition",
    "ensure_draft_editable",
    "next_revision",
    "normalize_source_type",
    "revision_from_approved",
    "supersede_transition",
]
