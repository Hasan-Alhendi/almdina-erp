"""Internal board-editor drawing. Desk writes stay fail-closed to a valid shape."""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.model.document import Document

from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing import (
    DrawingDocumentError,
    normalize_document,
)


class BoardEditorDrawingDraft(Document):
    def validate(self) -> None:
        if not str(self.drawing_key or "").strip():
            frappe.throw(_("Board editor drawing is missing its key."))
        if not self.door_cutting_order or not self.source_plan or not self.piece_instance_id:
            frappe.throw(_("Board editor drawing must belong to an order, a source plan, and a piece."))
        try:
            document = json.loads(self.drawing_json or "")
        except (TypeError, ValueError):
            frappe.throw(_("Board editor drawing is not valid JSON."))
        if not isinstance(document, dict):
            frappe.throw(_("Board editor drawing is not a supported drawing document."))
        try:
            normalize_document(document)
        except DrawingDocumentError:
            frappe.throw(_("Board editor drawing is not a supported drawing document."))
        _validate_archive(self.prior_drawing_archive_json)


def _validate_archive(raw: str | None) -> None:
    if raw in (None, ""):
        return
    try:
        archive = json.loads(raw)
    except (TypeError, ValueError):
        frappe.throw(_("Board editor drawing archive is not valid JSON."))
    if not isinstance(archive, list):
        frappe.throw(_("Board editor drawing archive is not a supported archive."))
    for entry in archive:
        if not isinstance(entry, dict):
            frappe.throw(_("Board editor drawing archive is not a supported archive."))
        drawing = entry.get("drawing")
        if drawing is None:
            continue
        if not isinstance(drawing, dict):
            frappe.throw(_("Board editor drawing archive is not a supported archive."))
        try:
            normalize_document(drawing)
        except DrawingDocumentError:
            frappe.throw(_("Board editor drawing archive is not a supported archive."))
