from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from almdina_erp.almdina_erp.infrastructure.frappe.production_stage_write_guard import (
    is_internal_stage_write,
)


class ProductionStage(Document):
    def _require_internal_write(self) -> None:
        if is_internal_stage_write(self):
            return
        frappe.throw(
            _(
                "Production stages are system-managed. Use the authorized production actions to assign, start, hand off, cancel, or reopen a stage."
            ),
            frappe.PermissionError,
        )

    def validate(self) -> None:
        self._require_internal_write()
        if cint(self.sequence) <= 0:
            frappe.throw(_("Production Stage sequence must be greater than zero."))
        if self.status == "In Progress" and (not self.started_by or not self.start_time):
            frappe.throw(_("An In Progress stage must have a worker and a start time."))
        if self.status == "Completed" and not self.finish_time:
            frappe.throw(_("A Completed stage must have a finish time."))

    def before_trash(self) -> None:
        self._require_internal_write()


__all__ = ["ProductionStage"]
