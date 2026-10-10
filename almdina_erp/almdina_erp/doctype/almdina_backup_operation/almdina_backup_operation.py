from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class AlmdinaBackupOperation(Document):
    """Service-owned audit row; direct Desk mutation is never granted."""

    def validate(self) -> None:
        if not self.is_new() and not getattr(self.flags, "backup_service_update", False):
            frappe.throw(_("Backup operation records are service-managed."), frappe.PermissionError)


__all__ = ["AlmdinaBackupOperation"]
