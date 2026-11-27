from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DRAFT = "Draft"
APPROVED = "Approved"
SUPERSEDED = "Superseded"
CANCELLED = "Cancelled"
SYSTEM = "System"
UPLOADED_DXF = "Uploaded DXF"
# Manual layout copy from Board Editor Draft. Not an optimizer result and not an
# uploaded DXF file. Approve/export reuse the manufacturing lifecycle after
# posed geometry is re-validated.
BOARD_EDITOR = "Board Editor"

EDITABLE_STATUSES = frozenset({DRAFT})
TERMINAL_STATUSES = frozenset({SUPERSEDED, CANCELLED})
SUPPORTED_SOURCES = frozenset({SYSTEM, UPLOADED_DXF, BOARD_EDITOR})
# Board Editor copies reuse the same approve/export lifecycle after posed
# geometry is re-validated. CUT_PATH remains manufacturing-only after approval.
MANUFACTURING_EXPORT_SOURCES = frozenset({SYSTEM, UPLOADED_DXF, BOARD_EDITOR})


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


def is_board_editor_source(value: str | None) -> bool:
    return str(value or "").strip() == BOARD_EDITOR


def select_board_editor_surface_plan(
    rows: list[Any] | tuple[Any, ...],
    *,
    approved_plan_name: str | None,
) -> Any | None:
    """Pick the Edited-tab Board Editor copy by explicit revision tracking.

    Candidates are Draft Board Editor copies plus the order's current Approved
    plan when that approval is itself Board Editor. Highest revision wins so
    approving the tip does not fall back to an older leftover Draft.
    """

    approved = str(approved_plan_name or "").strip()
    candidates: list[Any] = []
    for row in rows or ():
        source = (
            row.get("source_type")
            if isinstance(row, dict)
            else getattr(row, "source_type", None)
        )
        if str(source or "").strip() != BOARD_EDITOR:
            continue
        status = str(
            (row.get("status") if isinstance(row, dict) else getattr(row, "status", None))
            or ""
        ).strip()
        name = str(
            (row.get("name") if isinstance(row, dict) else getattr(row, "name", None))
            or ""
        ).strip()
        if status == DRAFT:
            candidates.append(row)
        elif status == APPROVED and approved and name == approved:
            candidates.append(row)
    if not candidates:
        return None

    def _sort_key(row: Any) -> tuple[int, str, str]:
        if isinstance(row, dict):
            return (
                int(row.get("revision") or 0),
                str(row.get("modified") or ""),
                str(row.get("name") or ""),
            )
        return (
            int(getattr(row, "revision", 0) or 0),
            str(getattr(row, "modified", "") or ""),
            str(getattr(row, "name", "") or ""),
        )

    return max(candidates, key=_sort_key)


def manufacturing_actions_allowed(source_type: str | None) -> bool:
    """Whether approve/export are open for this Cutting Plan source type."""

    return normalize_source_type(source_type) in MANUFACTURING_EXPORT_SOURCES


def ensure_draft_editable(status: str | None) -> None:
    normalized = str(status or DRAFT).strip() or DRAFT
    if normalized not in EDITABLE_STATUSES:
        raise CuttingPlanLifecycleError(f"plan_not_editable:{normalized}")


def is_current_manufacturing_candidate(
    *,
    status: str | None,
    belongs_to_order: bool,
    is_linked_approval: bool,
) -> bool:
    """Whether a revision can supply geometry for new manufacturing work.

    A Draft is the current working candidate; an Approved revision is current
    only while its owning order still points to that exact approval. Terminal,
    detached, and unrelated revisions remain readable as history only.
    """

    normalized = str(status or "").strip()
    if not belongs_to_order:
        return False
    return normalized == DRAFT or (normalized == APPROVED and is_linked_approval)


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


def revision_from_lineage_source(
    *,
    current_name: str,
    current_revision: int,
    current_status: str,
    source_type: str,
    next_revision_number: int | None = None,
) -> CuttingPlanRevision:
    """Build a Draft revision from an Approved tip or a Cancelled recovery source.

    Normal cancel-reapprove copies while the tip is still Approved. Historical
    orders that were cancelled before that copy existed may recover from the
    Cancelled revision without mutating it. ``next_revision_number`` must be the
    order-wide tip (``next_revision``), not merely ``current_revision + 1``.
    """

    normalized = str(current_status or "").strip()
    if normalized not in {APPROVED, CANCELLED}:
        raise CuttingPlanLifecycleError("revision_source_must_be_approved_or_cancelled")
    if normalized == APPROVED and next_revision_number is None:
        return revision_from_approved(
            current_name=current_name,
            current_revision=current_revision,
            current_status=normalized,
            source_type=source_type,
        )
    revision = (
        max(1, int(next_revision_number or 0))
        if next_revision_number is not None
        else max(1, int(current_revision or 1)) + 1
    )
    if revision <= int(current_revision or 0):
        raise CuttingPlanLifecycleError("revision_must_be_newer_than_source")
    return CuttingPlanRevision(
        revision=revision,
        status=DRAFT,
        source_type=normalize_source_type(source_type),
        based_on_plan=str(current_name or "").strip() or None,
    )


def select_newer_draft_of_source(
    rows: list[Any] | tuple[Any, ...],
    *,
    source_type: str,
    min_revision: int,
) -> Any | None:
    """Return the tip Draft of ``source_type`` when it is already newer than ``min_revision``."""

    wanted = normalize_source_type(source_type)
    floor = max(0, int(min_revision or 0))
    candidates: list[Any] = []
    for row in rows or ():
        if isinstance(row, dict):
            row_source = row.get("source_type")
            row_status = row.get("status")
            row_revision = row.get("revision")
        else:
            row_source = getattr(row, "source_type", None)
            row_status = getattr(row, "status", None)
            row_revision = getattr(row, "revision", None)
        if str(row_source or "").strip() != wanted:
            continue
        if str(row_status or "").strip() != DRAFT:
            continue
        if int(row_revision or 0) <= floor:
            continue
        candidates.append(row)
    if not candidates:
        return None

    def _sort_key(row: Any) -> tuple[int, str, str]:
        if isinstance(row, dict):
            return (
                int(row.get("revision") or 0),
                str(row.get("modified") or ""),
                str(row.get("name") or ""),
            )
        return (
            int(getattr(row, "revision", 0) or 0),
            str(getattr(row, "modified", "") or ""),
            str(getattr(row, "name", "") or ""),
        )

    return max(candidates, key=_sort_key)


def prefer_plan_tab_for_source(source_type: str | None) -> str:
    normalized = str(source_type or SYSTEM).strip() or SYSTEM
    if normalized == UPLOADED_DXF:
        return "Custom"
    if normalized == BOARD_EDITOR:
        return "BoardEditor"
    return "System"


def approval_transition(status: str | None) -> tuple[str, str]:
    ensure_draft_editable(status)
    return DRAFT, APPROVED


def supersede_transition(status: str | None) -> tuple[str, str]:
    normalized = str(status or "").strip()
    if normalized != APPROVED:
        raise CuttingPlanLifecycleError("only_approved_plan_can_be_superseded")
    return APPROVED, SUPERSEDED


def cancel_approval_transition(status: str | None) -> tuple[str, str]:
    """Cancel one approved production revision without reviving it as editable.

    Approval cancellation is historical: the immutable approved revision becomes
    ``Cancelled`` and future work must happen in a new Draft revision. This keeps
    audit history intact and avoids mutating production geometry back into a draft.
    """

    normalized = str(status or "").strip()
    if normalized != APPROVED:
        raise CuttingPlanLifecycleError("only_approved_plan_can_be_cancelled")
    return APPROVED, CANCELLED


__all__ = [
    "APPROVED",
    "BOARD_EDITOR",
    "CANCELLED",
    "DRAFT",
    "EDITABLE_STATUSES",
    "MANUFACTURING_EXPORT_SOURCES",
    "SYSTEM",
    "SUPERSEDED",
    "SUPPORTED_SOURCES",
    "TERMINAL_STATUSES",
    "UPLOADED_DXF",
    "CuttingPlanLifecycleError",
    "CuttingPlanRevision",
    "approval_transition",
    "cancel_approval_transition",
    "ensure_draft_editable",
    "is_board_editor_source",
    "is_current_manufacturing_candidate",
    "manufacturing_actions_allowed",
    "next_revision",
    "normalize_source_type",
    "prefer_plan_tab_for_source",
    "revision_from_approved",
    "revision_from_lineage_source",
    "select_board_editor_surface_plan",
    "select_newer_draft_of_source",
    "supersede_transition",
]
