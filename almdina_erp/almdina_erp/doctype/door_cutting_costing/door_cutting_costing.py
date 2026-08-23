from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, now_datetime


class DoorCuttingCosting(Document):
    """Financial snapshot for one order against one concrete cutting plan.

    Pricing/costing is intentionally separated from Door Cutting Order and
    Cutting Plan. The order owns customer requirements, the plan owns geometry,
    and this document owns money derived from both.
    """

    def before_insert(self) -> None:
        self.generated_by = self.generated_by or frappe.session.user
        self.generated_on = self.generated_on or now_datetime()

    def validate(self) -> None:
        if cint(self.version) < 1:
            frappe.throw(_("Costing version must be at least 1."))
        self._validate_plan_scope()
        self._enforce_immutable_snapshot()

    def _validate_plan_scope(self) -> None:
        if not self.cutting_plan or not self.door_cutting_order:
            return
        plan = frappe.db.get_value(
            "Cutting Plan",
            self.cutting_plan,
            ["door_cutting_order", "status"],
            as_dict=True,
        )
        if not plan:
            frappe.throw(_("The selected Cutting Plan does not exist."))
        if str(plan.door_cutting_order or "") != str(self.door_cutting_order or ""):
            frappe.throw(_("The selected Cutting Plan belongs to another order."))
        if self.status == "Approved" and plan.status != "Approved":
            frappe.throw(_("Approved costing must reference an approved Cutting Plan."))

    def _enforce_immutable_snapshot(self) -> None:
        if self.is_new() or self.flags.get("allow_status_transition"):
            return
        old = self.get_doc_before_save()
        if not old:
            return
        if old.status in {"Approved", "Superseded"}:
            frappe.throw(
                _(
                    "Costing {0} is immutable. Create a new costing version instead of editing it."
                ).format(self.name)
            )


__all__ = ["DoorCuttingCosting"]
