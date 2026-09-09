from __future__ import annotations

import frappe


def workflow_stage_name(stage_code: str) -> str | None:
    """Resolve a central workflow-stage identity from its stable code."""

    code = str(stage_code or "").strip()
    if not code:
        return None
    existing = frappe.db.get_value(
        "Production Workflow Stage",
        {"stage_code": code},
        "name",
    )
    return str(existing) if existing else None


def ensure_workflow_stage(
    stage_code: str,
    stage_label: str,
    *,
    kanban_order: int,
) -> str:
    """Return the central stage identity, creating it before route persistence."""

    code = str(stage_code or "").strip()
    label = str(stage_label or "").strip() or code
    existing = workflow_stage_name(code)
    if existing:
        return existing

    document = frappe.new_doc("Production Workflow Stage")
    document.stage_code = code
    document.stage_label = label
    document.kanban_order = int(kanban_order)
    document.disabled = 0
    document.insert(ignore_permissions=True)
    return str(document.name)


__all__ = ["ensure_workflow_stage", "workflow_stage_name"]
