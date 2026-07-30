from __future__ import annotations

import math

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class EdgeBandingType(Document):
    def validate(self) -> None:
        self._validate_thickness()

    def _validate_thickness(self) -> None:
        try:
            thickness_mm = float(self.thickness_mm)
        except (TypeError, ValueError) as error:
            raise frappe.ValidationError(
                _("Edge thickness must be a valid number.")
            ) from error

        if not math.isfinite(thickness_mm) or thickness_mm <= 0:
            frappe.throw(
                _("Edge thickness must be greater than zero."),
                frappe.ValidationError,
            )
        self.thickness_mm = flt(thickness_mm, 3)
