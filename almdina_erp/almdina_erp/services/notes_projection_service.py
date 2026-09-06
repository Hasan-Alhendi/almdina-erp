from __future__ import annotations

from typing import Any

import frappe

from almdina_erp.almdina_erp.application.notes.contracts import (
    ORDER_DOCTYPE,
    plain_text_preview,
)
from almdina_erp.almdina_erp.infrastructure.frappe.notes_repository import (
    FrappeNotesRepository,
)


_repository = FrappeNotesRepository()


def _is_order_comment(comment: Any) -> bool:
    return bool(
        comment
        and str(comment.get("comment_type") or "") == "Comment"
        and str(comment.get("reference_doctype") or "") == ORDER_DOCTYPE
        and str(comment.get("reference_name") or "").strip()
        and str(comment.get("name") or "").strip()
    )


def preserve_order_projection_on_save(order: Any, method: str | None = None) -> None:
    """Keep the read projection outside normal DCO authoring state.

    A form opened before another worker pins a Comment may later save unrelated
    order edits. Reloading these two read-only fields immediately before that save
    prevents the stale form payload from overwriting the collaboration projection.
    """

    del method
    if not order or str(order.get("doctype") or "") != ORDER_DOCTYPE:
        return
    if getattr(order, "is_new", lambda: False)():
        return
    name = str(order.get("name") or "").strip()
    if not name or not frappe.db.exists(ORDER_DOCTYPE, name):
        return
    projection = _repository.order_projection(name)
    order.set("important_note_comment", projection["comment"] or None)
    order.set("important_note_preview", projection["preview"] or None)


def refresh_important_projection_from_comment(
    comment: Any,
    method: str | None = None,
) -> None:
    """Refresh the projection if a native Timeline edit changes the pinned note."""

    del method
    if not _is_order_comment(comment):
        return
    order_name = str(comment.get("reference_name") or "").strip()
    if not frappe.db.exists(ORDER_DOCTYPE, order_name):
        return
    projection = _repository.order_projection(order_name)
    if projection["comment"] != str(comment.get("name") or "").strip():
        return
    preview = plain_text_preview(_repository.plain_text(comment.as_dict()))
    _repository.set_order_projection(
        order_name,
        comment_name=str(comment.name),
        preview=preview or None,
    )


def clear_important_projection_for_deleted_comment(
    comment: Any,
    method: str | None = None,
) -> None:
    """Clear the pointer if the canonical pinned Comment is deleted natively."""

    del method
    if not _is_order_comment(comment):
        return
    order_name = str(comment.get("reference_name") or "").strip()
    if not frappe.db.exists(ORDER_DOCTYPE, order_name):
        return
    projection = _repository.order_projection(order_name)
    if projection["comment"] != str(comment.get("name") or "").strip():
        return
    _repository.set_order_projection(
        order_name,
        comment_name=None,
        preview=None,
    )


__all__ = [
    "clear_important_projection_for_deleted_comment",
    "preserve_order_projection_on_save",
    "refresh_important_projection_from_comment",
]
