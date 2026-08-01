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
        self._validate_positive_number("thickness_mm", _("Edge thickness"), strictly_positive=True, precision=3)
        self._validate_positive_number("width_cm", _("Edge width"), strictly_positive=False, precision=3)
        self._validate_positive_number("rate_usd_per_meter", _("Edge rate"), strictly_positive=False, precision=6)

    def _validate_positive_number(
        self,
        fieldname: str,
        label: str,
        *,
        strictly_positive: bool,
        precision: int,
    ) -> None:
        raw = self.get(fieldname)
        try:
            value = float(raw or 0)
        except (TypeError, ValueError) as error:
            raise frappe.ValidationError(_("{0} must be a valid number.").format(label)) from error
        invalid = not math.isfinite(value) or value < 0 or (strictly_positive and value <= 0)
        if invalid:
            comparison = _("greater than zero") if strictly_positive else _("zero or greater")
            frappe.throw(_("{0} must be {1}.").format(label, comparison), frappe.ValidationError)
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
