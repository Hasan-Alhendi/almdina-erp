from __future__ import annotations

import math

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from almdina_erp.almdina_erp.infrastructure.frappe.master_data_audit import (
    audit_deleted_document,
    audit_saved_document,
)
from almdina_erp.almdina_erp.infrastructure.frappe.master_data_references import (
    find_link_references,
    reference_summary,
)


class EdgeBandingType(Document):
    def validate(self) -> None:
        self._validate_thickness()
        self._validate_non_negative_number("width_cm", _("Edge width"), precision=3)
        self._validate_non_negative_number("rate_usd_per_meter", _("Edge rate"), precision=6)

    def _validate_thickness(self) -> None:
        try:
            thickness_mm = float(self.thickness_mm or 0)
        except (TypeError, ValueError) as error:
            raise frappe.ValidationError(_("Edge thickness must be a valid number.")) from error
        if not math.isfinite(thickness_mm) or thickness_mm <= 0:
            frappe.throw(_("Edge thickness must be greater than zero."), frappe.ValidationError)
        self.thickness_mm = flt(thickness_mm, 3)

    def _validate_non_negative_number(
        self,
        fieldname: str,
        label: str,
        *,
        precision: int,
    ) -> None:
        raw = self.get(fieldname)
        try:
            value = float(raw or 0)
        except (TypeError, ValueError) as error:
            raise frappe.ValidationError(_("{0} must be a valid number.").format(label)) from error
        if not math.isfinite(value) or value < 0:
            frappe.throw(_("{0} must be zero or greater.").format(label), frappe.ValidationError)
        self.set(fieldname, flt(value, precision))

    def before_trash(self) -> None:
        references = find_link_references(self.doctype, self.name)
        if references:
            frappe.throw(
                _("This edge banding type is in use and cannot be deleted: {0}").format(
                    reference_summary(references)
                ),
                frappe.ValidationError,
            )

    def on_update(self) -> None:
        audit_saved_document(self)

    def on_trash(self) -> None:
        audit_deleted_document(self)


__all__ = ["EdgeBandingType"]
