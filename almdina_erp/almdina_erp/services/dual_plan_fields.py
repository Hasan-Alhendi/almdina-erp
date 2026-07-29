from __future__ import annotations

from typing import Any

import frappe


def has_dual_plan_field(fieldname: str) -> bool:
    try:
        return bool(frappe.get_meta("Door Cutting Order").has_field(fieldname))
    except Exception:
        return False


def get_order_field(order: Any, fieldname: str, default: Any = None) -> Any:
    value = getattr(order, fieldname, None)
    if value not in (None, ""):
        return value
    if isinstance(order, dict):
        value = order.get(fieldname)
        if value not in (None, ""):
            return value
    name = getattr(order, "name", None) if not isinstance(order, dict) else order.get("name")
    if name and has_dual_plan_field(fieldname):
        try:
            value = frappe.db.get_value("Door Cutting Order", name, fieldname)
            if value not in (None, ""):
                return value
        except Exception:
            pass
    return default


def get_system_plan_json(order: Any) -> str:
    return get_order_field(order, "system_plan_json") or get_order_field(order, "cutting_plan_json") or ""


def get_custom_plan_json(order: Any) -> str:
    return get_order_field(order, "custom_plan_json") or ""


def get_approved_plan_source(order: Any, default: str = "System") -> str:
    return get_order_field(order, "approved_plan_source", default) or default


def set_system_plan_json_if_available(order: Any, payload: str) -> None:
    if has_dual_plan_field("system_plan_json"):
        order.system_plan_json = payload


def set_custom_plan_json_if_available(order: Any, payload: str) -> None:
    if has_dual_plan_field("custom_plan_json"):
        order.custom_plan_json = payload
