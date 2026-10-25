from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class ProductionStage(Document):
    def validate(self) -> None:
        from almdina_erp.almdina_erp.infrastructure.frappe.production_stage_command_context import (
            is_authorized_stage_activation,
        )

        if cint(self.sequence) <= 0:
            frappe.throw(_("Production Stage sequence must be greater than zero."))
        if self.status == "In Progress" and (not self.started_by or not self.start_time):
            frappe.throw(_("An In Progress stage must have a worker and a start time."))
        if self.status == "Completed" and not self.finish_time:
            frappe.throw(_("A Completed stage must have a finish time."))

        old = self.get_doc_before_save()
        starts_new_work = self.status in {"In Progress", "Paused", "Completed"} and (
            old is None or old.status not in {"In Progress", "Paused", self.status}
        )
        if starts_new_work and not is_authorized_stage_activation(self):
            frappe.throw(
                _("Use the Start or Handoff action to activate a production stage."),
                frappe.ValidationError,
            )
