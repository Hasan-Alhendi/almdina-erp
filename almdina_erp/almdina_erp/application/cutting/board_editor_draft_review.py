"""Application gate for read-only board-editor draft review."""

from __future__ import annotations

from typing import Any, Mapping

from almdina_erp.almdina_erp.domain.cutting.board_editor_draft_review import (
    review_saved_draft,
    trusted_model_from_projection,
)


def draft_review_allowed(*, has_plan_view: bool) -> bool:
    """Review needs plan view. It does not require the draft write capability."""

    return bool(has_plan_view)


def review_editor_draft(
    *,
    draft: Mapping[str, Any] | None,
    projection: Mapping[str, Any],
    machine_type: str,
) -> dict[str, Any]:
    return review_saved_draft(
        draft,
        trusted_model_from_projection(projection, machine_type=machine_type),
    )


__all__ = ["draft_review_allowed", "review_editor_draft"]
