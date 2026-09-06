from __future__ import annotations

import re
from typing import Any

import frappe

from almdina_erp.almdina_erp.application.notes.contracts import (
    ORDER_DOCTYPE,
    plain_text_preview,
)


_TAG_RE = re.compile(r"<[^>]*>")


def _plain_text(value: object) -> str:
    """Return safe display text for both plain and native Timeline comments."""

    raw = str(value or "")
    strip_html_tags = getattr(frappe.utils, "strip_html_tags", None)
    if callable(strip_html_tags):
        raw = str(strip_html_tags(raw) or "")
    else:
        raw = _TAG_RE.sub(" ", raw)
    return " ".join(raw.replace("&nbsp;", " ").split())


class FrappeNotesRepository:
    """Frappe adapter for native Comment-backed Almadina collaboration notes."""

    comment_fields = (
        "name",
        "owner",
        "comment_by",
        "comment_email",
        "creation",
        "content",
        "subject",
        "reference_doctype",
        "reference_name",
        "comment_type",
    )

    def list_notes(
        self,
        reference_doctype: str,
        reference_name: str,
        *,
        important_comment: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = frappe.get_all(
            "Comment",
            filters={
                "comment_type": "Comment",
                "reference_doctype": reference_doctype,
                "reference_name": reference_name,
            },
            fields=list(self.comment_fields),
            order_by="creation desc, name desc",
            limit_page_length=50,
        )
        important = str(important_comment or "").strip()
        return [self.serialize_note(row, important_comment=important) for row in rows]

    def get_note(self, comment_name: str) -> dict[str, Any] | None:
        resolved = str(comment_name or "").strip()
        if not resolved:
            return None
        row = frappe.db.get_value(
            "Comment",
            resolved,
            list(self.comment_fields),
            as_dict=True,
        )
        return dict(row) if row else None

    def find_by_request_subject(
        self,
        reference_doctype: str,
        reference_name: str,
        subject: str,
    ) -> dict[str, Any] | None:
        row = frappe.db.get_value(
            "Comment",
            {
                "comment_type": "Comment",
                "reference_doctype": reference_doctype,
                "reference_name": reference_name,
                "subject": subject,
            },
            list(self.comment_fields),
            as_dict=True,
            order_by="creation asc",
        )
        return dict(row) if row else None

    def create_note(
        self,
        *,
        reference_doctype: str,
        reference_name: str,
        content: str,
        subject: str,
        user: str,
    ) -> dict[str, Any]:
        author = frappe.db.get_value("User", user, "full_name") or user
        document = frappe.get_doc(
            {
                "doctype": "Comment",
                "comment_type": "Comment",
                "comment_email": user,
                "comment_by": author,
                "reference_doctype": reference_doctype,
                "reference_name": reference_name,
                "content": content,
                # Native Comment has a subject field. Almadina reserves a
                # namespaced value here as the retry/idempotency operation key.
                "subject": subject,
                "published": 0,
            }
        ).insert(ignore_permissions=True)
        row = self.get_note(str(document.name))
        if not row:
            raise RuntimeError("Created Comment could not be reloaded.")
        return row

    @staticmethod
    def lock_reference(reference_doctype: str, reference_name: str) -> None:
        # Callers validate the doctype against the application allowlist before
        # reaching this adapter, so table interpolation cannot be user-controlled.
        rows = frappe.db.sql(
            f"select name from `tab{reference_doctype}` where name = %s for update",
            (reference_name,),
        )
        if not rows:
            raise frappe.DoesNotExistError(reference_name)

    @staticmethod
    def order_projection(order_name: str) -> dict[str, str]:
        row = frappe.db.get_value(
            ORDER_DOCTYPE,
            order_name,
            ["important_note_comment", "important_note_preview"],
            as_dict=True,
        )
        if not row:
            raise frappe.DoesNotExistError(order_name)
        return {
            "comment": str(row.get("important_note_comment") or "").strip(),
            "preview": str(row.get("important_note_preview") or "").strip(),
        }

    @staticmethod
    def set_order_projection(
        order_name: str,
        *,
        comment_name: str | None,
        preview: str | None,
    ) -> None:
        # This is a list/read projection only. update_modified=False is a hard
        # invariant: pinning a collaboration note must not reorder DCOs or enter
        # the official document/revision lifecycle.
        frappe.db.set_value(
            ORDER_DOCTYPE,
            order_name,
            {
                "important_note_comment": str(comment_name or "").strip() or None,
                "important_note_preview": str(preview or "").strip() or None,
            },
            update_modified=False,
        )

    @staticmethod
    def serialize_note(
        row: Any,
        *,
        important_comment: str | None = None,
    ) -> dict[str, Any]:
        note = dict(row or {})
        content = _plain_text(note.get("content"))
        comment_name = str(note.get("name") or "")
        return {
            "name": comment_name,
            "author": str(note.get("comment_by") or note.get("owner") or "").strip(),
            "author_user": str(note.get("comment_email") or note.get("owner") or "").strip(),
            "creation": note.get("creation"),
            "content": content,
            "preview": plain_text_preview(content),
            "is_important": bool(
                important_comment and comment_name == str(important_comment)
            ),
        }

    @staticmethod
    def plain_text(row: Any) -> str:
        return _plain_text(dict(row or {}).get("content"))


__all__ = ["FrappeNotesRepository"]
