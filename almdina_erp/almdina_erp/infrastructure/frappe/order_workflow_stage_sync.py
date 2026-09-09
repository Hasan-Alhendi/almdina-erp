from __future__ import annotations

import frappe


_SYSTEM_STAGES = (
    ("DATA_ENTRY", "المسودة / إدخال البيانات", 10),
    ("READY_TO_DISPATCH", "جاهز للإرسال", 20),
)


def sync_order_workflow_stages() -> None:
    """Ensure shared pre-production stages exist without overwriting user labels."""

    if not frappe.db.exists("DocType", "Production Workflow Stage"):
        return

    for code, label, kanban_order in _SYSTEM_STAGES:
        existing = frappe.db.get_value(
            "Production Workflow Stage",
            {"stage_code": code},
            ["name", "stage_label", "disabled"],
            as_dict=True,
        )
        if existing:
            updates = {}
            if not str(existing.stage_label or "").strip():
                updates["stage_label"] = label
            if int(existing.disabled or 0):
                updates["disabled"] = 0
            if updates:
                frappe.db.set_value(
                    "Production Workflow Stage",
                    existing.name,
                    updates,
                    update_modified=False,
                )
            continue

        document = frappe.new_doc("Production Workflow Stage")
        document.stage_code = code
        document.stage_label = label
        document.kanban_order = kanban_order
        document.disabled = 0
        document.insert(ignore_permissions=True)


__all__ = ["sync_order_workflow_stages"]
