from __future__ import annotations

import frappe


_ROUTE_STAGE_DOCTYPE = "Production Routing Stage"
_STAGE_DEFINITION_DOCTYPE = "Production Stage Definition"


def _legacy_rows() -> list[object]:
    columns = set(frappe.db.get_table_columns(_ROUTE_STAGE_DOCTYPE) or ())
    required = {"stage_definition", "stage_type", "department_label"}
    if not required.issubset(columns):
        return []
    return frappe.db.sql(
        """
        select name, stage_type, department_label
          from `tabProduction Routing Stage`
         where ifnull(stage_definition, '') = ''
           and ifnull(stage_type, '') != ''
         order by parent asc, idx asc
        """,
        as_dict=True,
    )


def _definition_for(stage_code: str, stage_label: str) -> str:
    existing = frappe.db.get_value(
        _STAGE_DEFINITION_DOCTYPE,
        {"stage_code": stage_code},
        "name",
    )
    if existing:
        return str(existing)

    by_label = frappe.db.get_value(
        _STAGE_DEFINITION_DOCTYPE,
        {"stage_label": stage_label},
        ["name", "stage_code"],
        as_dict=True,
    )
    if by_label:
        return str(by_label.name)

    definition = frappe.get_doc(
        {
            "doctype": _STAGE_DEFINITION_DOCTYPE,
            "stage_code": stage_code,
            "stage_label": stage_label,
            "disabled": 0,
        }
    )
    definition.insert(ignore_permissions=True)
    return str(definition.name)


def execute() -> None:
    """Backfill the new Link without assuming a fixed factory stage catalog."""

    if not frappe.db.exists("DocType", _STAGE_DEFINITION_DOCTYPE):
        return
    for row in _legacy_rows():
        stage_code = str(row.stage_type or "").strip()
        stage_label = str(row.department_label or stage_code).strip()
        if not stage_code or not stage_label:
            continue
        frappe.db.set_value(
            _ROUTE_STAGE_DOCTYPE,
            row.name,
            "stage_definition",
            _definition_for(stage_code, stage_label),
            update_modified=False,
        )
