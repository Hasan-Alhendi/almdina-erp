from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from almdina_erp.almdina_erp.domain.orders.price_approval import (
    PRICE_APPROVAL_FINGERPRINT_FORMULA_VERSION,
    PRICE_APPROVAL_VALIDITY_ACTIVE,
    PriceApprovalRecordMutationError,
    assert_price_approval_record_immutable,
)


class DoorCuttingPriceApproval(Document):
    """Historical final-price approval event for one Door Cutting Order.

    This document is an audit/history record, not a costing engine. Ordinary Desk
    users must not create, edit, or delete rows; phase-2 commands own mutations.
    """

    def before_insert(self) -> None:
        self.validity_status = self.validity_status or PRICE_APPROVAL_VALIDITY_ACTIVE
        self.currency = str(self.currency or "USD").strip() or "USD"
        self.fingerprint_formula_version = (
            str(self.fingerprint_formula_version or "").strip()
            or PRICE_APPROVAL_FINGERPRINT_FORMULA_VERSION
        )
        if not self.flags.get("price_approval_action"):
            frappe.throw(
                _("Door Cutting Price Approval records can only be created by an authorized command."),
                frappe.PermissionError,
            )

    def validate(self) -> None:
        self._validate_plan_scope()
        self._enforce_history_integrity()

    def on_trash(self) -> None:
        frappe.throw(
            _("Door Cutting Price Approval records cannot be deleted."),
            frappe.PermissionError,
        )

    def _validate_plan_scope(self) -> None:
        if not self.cutting_plan or not self.door_cutting_order:
            return
        plan_order = frappe.db.get_value(
            "Cutting Plan",
            self.cutting_plan,
            "door_cutting_order",
        )
        if not plan_order:
            frappe.throw(_("The selected Cutting Plan does not exist."))
        if str(plan_order) != str(self.door_cutting_order):
            frappe.throw(_("The selected Cutting Plan belongs to another order."))

    def _enforce_history_integrity(self) -> None:
        if self.is_new():
            return
        old = self.get_doc_before_save()
        if not old:
            return
        allow_invalidate = bool(self.flags.get("allow_price_approval_invalidate"))
        try:
            assert_price_approval_record_immutable(
                is_new=False,
                allow_status_transition=allow_invalidate,
                previous_validity=old.validity_status,
                incoming_validity=self.validity_status,
            )
        except PriceApprovalRecordMutationError as exc:
            frappe.throw(str(exc))

        if not allow_invalidate:
            return

        protected = (
            "door_cutting_order",
            "cutting_plan",
            "approved_amount",
            "currency",
            "approved_by",
            "approved_on",
            "pricing_basis_fingerprint",
            "fingerprint_formula_version",
        )
        for fieldname in protected:
            if self.get(fieldname) != old.get(fieldname):
                frappe.throw(
                    _("Invalidating a price approval cannot rewrite historical approval details.")
                )


__all__ = ["DoorCuttingPriceApproval"]
