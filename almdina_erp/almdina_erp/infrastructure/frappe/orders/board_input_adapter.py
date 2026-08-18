from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.domain.orders.numeric_input import default_if_missing

from .document_access import FrappeOrderDocumentAccess


class FrappeOrderBoardInputAdapter:
    """Validate and normalize customer-order board requirements only.

    Kerf, trim margin, usable board geometry, optimizer settings, and rates are
    Cutting Plan concerns and intentionally do not participate in DCO save.
    """

    def __init__(self, document: Any, access: FrappeOrderDocumentAccess) -> None:
        self.document = document
        self.access = access

    def load_snapshot(self) -> None:
        description = str(getattr(self.document, "board_description", "") or "").strip()
        if not description:
            frappe.throw(_("Board description is required."))

        length_cm = self.access.finite(
            default_if_missing(getattr(self.document, "board_length_cm", None), 244),
            _("Board Length (CM)"),
        )
        width_cm = self.access.finite(
            default_if_missing(getattr(self.document, "board_width_cm", None), 122),
            _("Board Width (CM)"),
        )
        if length_cm <= 0:
            frappe.throw(_("Board Length (CM) must be greater than zero."))
        if width_cm <= 0:
            frappe.throw(_("Board Width (CM) must be greater than zero."))

        self.document.board_description = description
        self.document.board_length_cm = length_cm
        self.document.board_width_cm = width_cm
        self.document.full_board_length_mm = length_cm * 10
        self.document.full_board_width_mm = width_cm * 10


__all__ = ["FrappeOrderBoardInputAdapter"]
