from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime


class BoardRemnant(Document):
    def validate(self) -> None:
        self._validate_dimensions()
        self._load_board_identity()
        self.area_m2 = flt(self.length_mm) * flt(self.width_mm) / 1_000_000
        self._validate_reservation_state()

    def _validate_dimensions(self) -> None:
        if flt(self.length_mm) <= 0 or flt(self.width_mm) <= 0:
            frappe.throw(_("Remnant length and width must be greater than zero."))

    def _load_board_identity(self) -> None:
        board = frappe.db.get_value(
            "Item",
            self.board_item,
            [
                "custom_is_mdf",
                "custom_board_material",
                "custom_board_color",
                "custom_board_thickness_mm",
            ],
            as_dict=True,
        )
        if not board or not board.custom_is_mdf:
            frappe.throw(_("Board Remnant must reference an Item marked as MDF/cutting board."))

        self.material = board.custom_board_material or ""
        self.color = board.custom_board_color or ""
        if not flt(self.thickness_mm):
            self.thickness_mm = flt(board.custom_board_thickness_mm)

    def _validate_reservation_state(self) -> None:
        if self.status == "Reserved" and not self.reserved_for_order:
            frappe.throw(_("A Reserved remnant must be linked to the order that reserved it."))
        if self.status != "Reserved":
            self.reserved_for_order = None
            self.reservation_timestamp = None

    def reserve(self, order_name: str) -> None:
        if self.status != "Available":
            frappe.throw(_("Remnant {0} is not available.").format(self.name))
        self.status = "Reserved"
        self.reserved_for_order = order_name
        self.reservation_timestamp = now_datetime()
        self.save(ignore_permissions=True)

    def release(self, order_name: str | None = None) -> None:
        if self.status != "Reserved":
            return
        if order_name and self.reserved_for_order != order_name:
            frappe.throw(_("Remnant {0} is reserved for another order.").format(self.name))
        self.status = "Available"
        self.reserved_for_order = None
        self.reservation_timestamp = None
        self.save(ignore_permissions=True)

    def consume(self, order_name: str | None = None) -> None:
        if self.status not in {"Available", "Reserved"}:
            frappe.throw(_("Remnant {0} cannot be consumed from status {1}.").format(self.name, self.status))
        if self.status == "Reserved" and order_name and self.reserved_for_order != order_name:
            frappe.throw(_("Remnant {0} is reserved for another order.").format(self.name))
        self.status = "Consumed"
        self.reserved_for_order = None
        self.reservation_timestamp = None
        self.save(ignore_permissions=True)
