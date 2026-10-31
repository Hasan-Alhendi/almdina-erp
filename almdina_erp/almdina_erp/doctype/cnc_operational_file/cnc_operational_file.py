from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from almdina_erp.almdina_erp.domain.cnc.operational_file import OPERATIONAL_FILE_STATUSES


class CNCOperationalFile(Document):
    def validate(self) -> None:
        if str(self.status or "") not in OPERATIONAL_FILE_STATUSES:
            frappe.throw(_("Operational file status is not valid."), frappe.ValidationError)
        order_name = str(self.door_cutting_order or "").strip()
        plan_name = str(self.cutting_plan or "").strip()
        sheet_no = int(self.sheet_no or 0)
        revision = int(self.plan_revision or 0)
        if not order_name or not plan_name or sheet_no <= 0 or revision <= 0:
            frappe.throw(_("Operational file identity is incomplete."), frappe.ValidationError)
        self.identity_key = f"{order_name}::{plan_name}::{revision}::{sheet_no}"
        self.sheet_key = f"sheet:{sheet_no}"
        existing = frappe.db.exists(
            "CNC Operational File",
            {"identity_key": self.identity_key},
        )
        if existing and existing != self.name:
            frappe.throw(
                _("An operational file already exists for this approved sheet."),
                frappe.ValidationError,
            )


__all__ = ["CNCOperationalFile"]
