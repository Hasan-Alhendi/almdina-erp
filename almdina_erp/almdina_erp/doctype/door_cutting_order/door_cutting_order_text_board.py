from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import flt

from .door_cutting_order_fast import FastDoorCuttingOrder


class TextBoardDoorCuttingOrder(FastDoorCuttingOrder):
    """Door Cutting Order using a free-text board description.

    The operator enters the board description and dimensions directly. Centimeter
    dimensions are synchronized to the internal millimeter snapshot fields used
    by the optimizer. ``board_item`` remains an optional internal stock mapping;
    it is not part of order-entry UX.
    """

    def _load_board_snapshot(self) -> None:
        description = str(getattr(self, "board_description", "") or "").strip()
        if not description:
            frappe.throw(_("Board description is required."))

        length_cm = self._finite(
            getattr(self, "board_length_cm", None) or 244,
            _("Board Length (CM)"),
        )
        width_cm = self._finite(
            getattr(self, "board_width_cm", None) or 122,
            _("Board Width (CM)"),
        )
        if length_cm <= 0:
            frappe.throw(_("Board Length (CM) must be greater than zero."))
        if width_cm <= 0:
            frappe.throw(_("Board Width (CM) must be greater than zero."))

        self.board_description = description
        self.board_length_cm = length_cm
        self.board_width_cm = width_cm
        self.full_board_length_mm = length_cm * 10
        self.full_board_width_mm = width_cm * 10

        trim_mm = flt(self.trim_margin_mm)
        usable_length_mm = self.full_board_length_mm - (trim_mm * 2)
        usable_width_mm = self.full_board_width_mm - (trim_mm * 2)
        if usable_length_mm <= 0 or usable_width_mm <= 0:
            frappe.throw(_("Trim Margin leaves no usable board area."))

    def _plan_input_payload(self, settings: Any, source: Any | None = None) -> dict[str, Any]:
        payload = super()._plan_input_payload(settings, source)
        source = source or self
        description = str(getattr(source, "board_description", "") or "").strip()
        payload.setdefault("board", {})["item"] = description
        payload["board"]["description"] = description
        return payload
