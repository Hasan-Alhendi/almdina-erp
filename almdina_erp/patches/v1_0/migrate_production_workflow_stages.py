from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint

from almdina_erp.almdina_erp.infrastructure.frappe.production_workflow_stage_repository import (
    ensure_workflow_stage,
)


LEGACY_PHYSICAL_STATUSES = (
    "At Sharyoun",
    "At Drawing",
    "At CNC",
    "At Sanding",
    "Cutting In Progress",
    "Cut Completed",
    "Edge Banding In Progress",
    "Quality Check",
)


def _route_rows() -> list[frappe._dict]:
    return frappe.get_all(
        "Production Routing Stage",
        fields=["name", "parent", "sequence", "stage_type", "department_label", "workflow_stage"],
        order_by="parent asc, sequence asc, idx asc",
    )


def _preflight(rows: list[frappe._dict]) -> dict[str, str]:
    labels: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        code = str(row.stage_type or "").strip()
        label = str(row.department_label or "").strip()
        if not code and not row.workflow_stage:
            frappe.throw(_("تعذر ترحيل مسار الإنتاج {0}: توجد مرحلة بلا رمز قديم ولا تعريف مركزي.").format(row.parent))
        if code:
            labels.setdefault(code, set())
            if label:
                labels[code].add(label)
    conflicts = {code: values for code, values in labels.items() if len(values) > 1}
    if conflicts:
        details = ", ".join(f"{code}: {' / '.join(sorted(values))}" for code, values in sorted(conflicts.items()))
        frappe.throw(_("تعذر ترحيل مراحل الإنتاج بسبب اختلاف الاسم لنفس الرمز: {0}").format(details), frappe.ValidationError)
    return {code: next(iter(values)) if values else code for code, values in labels.items()}


def _normalize_legacy_order_statuses() -> None:
    frappe.db.sql(
        """
        update `tabDoor Cutting Order`
           set status = 'Production In Progress'
         where status in %(statuses)s
           and ifnull(production_path, '') != ''
        """,
        {"statuses": LEGACY_PHYSICAL_STATUSES},
    )


def execute() -> None:
    if not frappe.db.exists("DocType", "Production Workflow Stage"):
        return
    rows = _route_rows()
    if rows:
        labels = _preflight(rows)
        ordered_codes = sorted(
            labels,
            key=lambda code: (
                min(cint(row.sequence) for row in rows if str(row.stage_type or "").strip() == code),
                code,
            ),
        )
        stage_names = {
            code: ensure_workflow_stage(
                code,
                labels.get(code) or code,
                kanban_order=index * 10,
            )
            for index, code in enumerate(ordered_codes, start=1)
        }
        for row in rows:
            if row.workflow_stage:
                continue
            code = str(row.stage_type or "").strip()
            if code:
                frappe.db.set_value(
                    "Production Routing Stage",
                    row.name,
                    "workflow_stage",
                    stage_names[code],
                    update_modified=False,
                )
    _normalize_legacy_order_statuses()


__all__ = ["execute"]
