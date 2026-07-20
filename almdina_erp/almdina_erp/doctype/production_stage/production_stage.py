from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class ProductionStage(Document):
    def validate(self) -> None:
        if cint(self.sequence) <= 0:
            frappe.throw(_("Production Stage sequence must be greater than zero."))
        if self.status == "In Progress" and (not self.started_by or not self.start_time):
            frappe.throw(_("An In Progress stage must have a worker and a start time."))
        if self.status == "Completed" and not self.finish_time:
            frappe.throw(_("A Completed stage must have a finish time."))
