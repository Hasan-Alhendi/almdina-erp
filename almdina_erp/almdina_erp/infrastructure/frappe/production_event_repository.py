from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import now_datetime


def log_event(
    stage: Any,
    event_type: str,
    details: dict[str, Any] | None = None,
) -> None:
    event = frappe.new_doc("Production Stage Event")
    event.door_cutting_order = stage.door_cutting_order
    event.production_stage = stage.name
    event.stage_type = stage.stage_type
    event.event_type = event_type
    event.event_time = now_datetime()
    event.actor = frappe.session.user
    event.details_json = frappe.as_json(details or {})
    event.insert(ignore_permissions=True)


__all__ = ["log_event"]
