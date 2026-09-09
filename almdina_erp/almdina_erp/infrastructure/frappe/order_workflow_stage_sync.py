from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.domain.orders.intake_lifecycle import (
    INTAKE_WORKFLOW_STAGES,
)


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


def repair_started_orders_with_intake_stage() -> int:
    """Clear only stale intake markers from orders already in real production.

    Early ALMADINA-162 deployments could still expose the legacy immediate-dispatch
    action. Those orders may have a real production path/stage while retaining
    DATA_ENTRY or READY_TO_DISPATCH. Runtime production is authoritative, so the
    safest repair is to remove only the contradictory pre-production marker and
    preserve the production path, Production Stage, worker, and audit history.
    """

    if not frappe.db.exists("DocType", "Door Cutting Order"):
        return 0

    rows = frappe.get_all(
        "Door Cutting Order",
        filters={"workflow_stage": ["in", sorted(INTAKE_WORKFLOW_STAGES)]},
        fields=["name", "production_path", "current_production_stage"],
    )
    names = [
        row.name
        for row in rows
        if str(row.production_path or "").strip()
        or str(row.current_production_stage or "").strip()
    ]
    for name in names:
        frappe.db.set_value(
            "Door Cutting Order",
            name,
            "workflow_stage",
            None,
            update_modified=False,
        )
    return len(names)


__all__ = [
    "repair_started_orders_with_intake_stage",
    "sync_order_workflow_stages",
]
