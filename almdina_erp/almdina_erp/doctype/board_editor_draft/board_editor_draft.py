"""Internal board-editor draft. Desk writes stay fail-closed to a valid shape."""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.model.document import Document

from almdina_erp.almdina_erp.domain.cutting.board_editor_draft import (
    SCHEMA,
    contains_forbidden_field,
)


class BoardEditorDraft(Document):
    def validate(self) -> None:
        if not str(self.draft_key or "").strip():
            frappe.throw(_("Board editor draft is missing its key."))
        if not self.door_cutting_order or not self.source_plan:
            frappe.throw(_("Board editor draft must belong to an order and a source plan."))
        try:
            layout = json.loads(self.layout_json or "")
        except (TypeError, ValueError):
            frappe.throw(_("Board editor draft layout is not valid JSON."))
        if not isinstance(layout, dict) or layout.get("schema") != SCHEMA:
            frappe.throw(_("Board editor draft layout is not a supported edit document."))
        if contains_forbidden_field(layout):
            frappe.throw(_("Board editor draft layout contains fields that cannot be stored."))
