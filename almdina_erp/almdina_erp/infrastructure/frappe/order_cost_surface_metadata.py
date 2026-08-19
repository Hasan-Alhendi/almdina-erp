from __future__ import annotations

import frappe


DOCTYPE = "Door Cutting Order"
COST_INPUT_FIELDS = (
    "board_rate_usd",
    "cutting_cost_per_board_usd",
)


def _remove_stale_required_property_setters() -> None:
    """Remove site-local mandatory overrides from Cost workspace fields."""

    if not frappe.db.exists("DocType", "Property Setter"):
        return

    names = frappe.get_all(
        "Property Setter",
        filters={
            "doc_type": DOCTYPE,
            "field_name": ["in", COST_INPUT_FIELDS],
            "property": "reqd",
        },
        pluck="name",
    )
    for name in names:
        frappe.delete_doc(
            "Property Setter",
            name,
            ignore_permissions=True,
            force=True,
        )


def _repair_standard_docfields() -> None:
    """Keep initial DCO creation independent from Cost workspace completion."""

    if not frappe.db.exists("DocType", DOCTYPE):
        return

    placeholders = ", ".join(["%s"] * len(COST_INPUT_FIELDS))
    frappe.db.sql(
        f"""
        update `tabDocField`
           set reqd = 0
         where parent = %s
           and fieldname in ({placeholders})
           and coalesce(reqd, 0) != 0
        """,
        (DOCTYPE, *COST_INPUT_FIELDS),
    )


def order_cost_surface_metadata_state() -> dict[str, object]:
    """Return effective required flags and surviving local overrides."""

    if not frappe.db.exists("DocType", DOCTYPE):
        return {
            "doctype": DOCTYPE,
            "fields": {},
            "property_setters": [],
        }

    meta = frappe.get_meta(DOCTYPE)
    fields: dict[str, int | None] = {}
    for fieldname in COST_INPUT_FIELDS:
        field = meta.get_field(fieldname)
        fields[fieldname] = None if field is None else int(field.reqd or 0)

    property_setters = frappe.get_all(
        "Property Setter",
        filters={
            "doc_type": DOCTYPE,
            "field_name": ["in", COST_INPUT_FIELDS],
            "property": "reqd",
        },
        fields=["name", "field_name", "property", "value"],
    )
    property_setters.sort(
        key=lambda row: (
            str(row.get("field_name", "")),
            str(row.get("name", "")),
        )
    )
    return {
        "doctype": DOCTYPE,
        "fields": fields,
        "property_setters": [dict(row) for row in property_setters],
    }


def _assert_order_cost_surface_metadata() -> None:
    state = order_cost_surface_metadata_state()
    invalid = {
        fieldname: required
        for fieldname, required in state["fields"].items()
        if required != 0
    }
    setters = state["property_setters"]
    if not invalid and not setters:
        return

    raise RuntimeError(
        "Order Cost metadata repair failed: "
        f"invalid required flags={invalid}, property_setters={setters}"
    )


def sync_order_cost_surface_metadata() -> None:
    """Make Cost fields optional on the DCO document, not in Cost workflow.

    Board rate and cutting fee are required when the dedicated Cost workspace is
    saved. They must not be native mandatory fields on Door Cutting Order,
    otherwise Frappe blocks the first order save before the Cost tab can be
    completed. Long-lived sites may still carry Property Setter or DocField
    metadata from the pre-workspace implementation, so migration repairs both.
    """

    if not frappe.db.exists("DocType", DOCTYPE):
        return

    _remove_stale_required_property_setters()
    _repair_standard_docfields()
    frappe.clear_cache(doctype=DOCTYPE)
    _assert_order_cost_surface_metadata()


__all__ = [
    "COST_INPUT_FIELDS",
    "order_cost_surface_metadata_state",
    "sync_order_cost_surface_metadata",
]
