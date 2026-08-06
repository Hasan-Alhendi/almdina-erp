from __future__ import annotations

import frappe


ROUTING_STAGE_DOCTYPE = "Production Routing Stage"


def execute() -> None:
    """Remove unsupported optional-stage state without changing route contents."""

    if not frappe.db.exists("DocType", ROUTING_STAGE_DOCTYPE):
        return
    meta = frappe.get_meta(ROUTING_STAGE_DOCTYPE)
    if not meta.has_field("required"):
        return

    values: dict[str, int] = {"required": 1}
    if meta.has_field("auto_complete_if_not_applicable"):
        values["auto_complete_if_not_applicable"] = 0

    rows = frappe.get_all(
        ROUTING_STAGE_DOCTYPE,
        fields=["name", *values],
        limit_page_length=0,
    )
    for row in rows:
        changed = {
            fieldname: expected
            for fieldname, expected in values.items()
            if int(row.get(fieldname) or 0) != expected
        }
        if changed:
            frappe.db.set_value(
                ROUTING_STAGE_DOCTYPE,
                row.name,
                changed,
                update_modified=False,
            )


__all__ = ["execute"]
