from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint


ROUTING_STAGE_DOCTYPE = "Production Routing Stage"
STAGE_DEFINITION_DOCTYPE = "Production Stage Definition"


def _columns(doctype: str) -> set[str]:
    return {str(column) for column in frappe.db.get_table_columns(doctype)}


def _legacy_rows(columns: set[str]) -> list[Any]:
    department_expression = (
        "department_label" if "department_label" in columns else "'' as department_label"
    )
    planning_expression = (
        "is_planning_stage" if "is_planning_stage" in columns else "0 as is_planning_stage"
    )
    return frappe.db.sql(
        f"""
        select name, stage_type, {department_expression}, {planning_expression}
        from `tabProduction Routing Stage`
        where ifnull(stage_definition, '') = ''
        order by parent asc, idx asc
        """,
        as_dict=True,
    )


def _unique_label(stage_code: str, preferred_label: str) -> str:
    label = preferred_label or stage_code
    existing = frappe.db.get_value(
        STAGE_DEFINITION_DOCTYPE,
        {"stage_label": label},
        "name",
    )
    if not existing or str(existing) == stage_code:
        return label
    return f"{label} ({stage_code})"


def _definition_for(row: Any) -> str:
    stage_code = str(row.stage_type or "").strip()
    if not stage_code:
        frappe.throw(
            "تعذر ترحيل مرحلة قديمة في مسار الإنتاج لأن رمز المرحلة فارغ.",
            frappe.ValidationError,
        )

    existing = frappe.db.get_value(
        STAGE_DEFINITION_DOCTYPE,
        {"stage_code": stage_code},
        "name",
    )
    if existing:
        return str(existing)

    stage_label = _unique_label(
        stage_code,
        str(getattr(row, "department_label", None) or "").strip(),
    )
    document = frappe.get_doc(
        {
            "doctype": STAGE_DEFINITION_DOCTYPE,
            "stage_code": stage_code,
            "stage_label": stage_label,
            "description": "تم ترحيل هذه المرحلة تلقائيًا من مسارات الإنتاج السابقة.",
            "is_planning_default": cint(getattr(row, "is_planning_stage", 0)),
            "disabled": 0,
        }
    )
    document.insert(ignore_permissions=True)
    return str(document.name)


def execute() -> None:
    """Backfill the stage library from legacy routing-stage snapshots.

    Existing route rows keep their stable legacy ``stage_type`` identity. A clean
    site has no rows to migrate, so this patch never seeds production master data.
    """

    if not frappe.db.exists("DocType", ROUTING_STAGE_DOCTYPE):
        return
    if not frappe.db.exists("DocType", STAGE_DEFINITION_DOCTYPE):
        return

    columns = _columns(ROUTING_STAGE_DOCTYPE)
    if "stage_definition" not in columns:
        return

    unresolved_count = frappe.db.count(
        ROUTING_STAGE_DOCTYPE,
        {"stage_definition": ["in", (None, "")]},
    )
    if not unresolved_count:
        return

    if "stage_type" not in columns:
        frappe.throw(
            "تعذر ترحيل مسارات الإنتاج القديمة: عمود stage_type التاريخي غير موجود.",
            frappe.ValidationError,
        )

    for row in _legacy_rows(columns):
        definition_name = _definition_for(row)
        frappe.db.set_value(
            ROUTING_STAGE_DOCTYPE,
            row.name,
            "stage_definition",
            definition_name,
            update_modified=False,
        )


__all__ = ["execute"]
