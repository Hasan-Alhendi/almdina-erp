from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import flt


def order_board_material(order: Any) -> str:
    material = getattr(order, "board_material", None)
    if material not in (None, ""):
        return str(material)
    return str(getattr(order, "board_description", "") or "").strip()


def order_board_color(order: Any) -> str:
    color = getattr(order, "board_color", None)
    if color not in (None, ""):
        return str(color)
    board_item = str(getattr(order, "board_item", "") or "").strip()
    if board_item:
        return str(frappe.db.get_value("Item", board_item, "custom_board_color") or "")
    return ""


def order_board_thickness_mm(order: Any) -> float:
    thickness = getattr(order, "board_thickness_mm", None)
    if thickness not in (None, ""):
        return flt(thickness)
    board_item = str(getattr(order, "board_item", "") or "").strip()
    if board_item:
        return flt(frappe.db.get_value("Item", board_item, "custom_board_thickness_mm"))
    return 0.0
