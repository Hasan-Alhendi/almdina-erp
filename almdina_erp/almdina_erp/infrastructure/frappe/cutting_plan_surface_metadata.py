from __future__ import annotations

import frappe


DOCTYPE = "Door Cutting Order"

# These fields form the non-financial Cutting Plan surface. They must always
# remain on Frappe permission level 0. Cost visibility is projected separately
# to permission level 1 and must never control whether the plan UI exists.
CUTTING_PLAN_SURFACE_FIELDS = (
    "results_tab",
    "cut_geometry_section",
    "kerf_mm",
    "cut_geometry_column",
    "trim_margin_mm",
    "optimizer_section",
    "packing_mode",
    "cutting_machine_type",
    "optimizer_column",
    "optimization_time_limit_sec",
    "plan_actions_section",
    "plan_control_actions",
    "plan_result_section",
    "plan_controls_intro",
    "plan_section",
    "cutting_plan_html",
    "totals_section",
    "total_area_m2",
    "total_edge_meters",
    "required_boards",
    "waste_area_m2",
    "waste_percent",
    "technical_section",
    "packing_method",
    "packing_score",
    "engine_version",
    "cutting_plan_json",
    "system_plan_json",
    "custom_plan_json",
    "approved_plan_source",
)

# These structural controls are always present for a user who can open the
# Cutting Plan tab. Business capabilities decide the content rendered inside
# them; site-local metadata must not hide the containers themselves.
VISIBLE_PLAN_SURFACE_FIELDS = (
    "results_tab",
    "cut_geometry_section",
    "optimizer_section",
    "plan_actions_section",
    "plan_control_actions",
    "plan_section",
    "cutting_plan_html",
)


def _remove_stale_property_setters() -> None:
    """Remove site-local overrides that can hide protected plan containers."""

    if not frappe.db.exists("DocType", "Property Setter"):
        return

    names: list[str] = []
    for property_name, fieldnames in (
        ("permlevel", CUTTING_PLAN_SURFACE_FIELDS),
        ("hidden", VISIBLE_PLAN_SURFACE_FIELDS),
        ("depends_on", VISIBLE_PLAN_SURFACE_FIELDS),
    ):
        names.extend(
            frappe.get_all(
                "Property Setter",
                filters={
                    "doc_type": DOCTYPE,
                    "field_name": ["in", fieldnames],
                    "property": property_name,
                },
                pluck="name",
            )
        )
    for name in names:
        frappe.delete_doc(
            "Property Setter",
            name,
            ignore_permissions=True,
            force=True,
        )


def _repair_standard_docfields() -> None:
    """Make the database metadata explicit even on long-lived migrated sites."""

    if not frappe.db.exists("DocType", DOCTYPE):
        return

    placeholders = ", ".join(["%s"] * len(CUTTING_PLAN_SURFACE_FIELDS))
    frappe.db.sql(
        f"""
        update `tabDocField`
           set permlevel = 0
         where parent = %s
           and fieldname in ({placeholders})
           and coalesce(permlevel, 0) != 0
        """,
        (DOCTYPE, *CUTTING_PLAN_SURFACE_FIELDS),
    )

    visible_placeholders = ", ".join(["%s"] * len(VISIBLE_PLAN_SURFACE_FIELDS))
    frappe.db.sql(
        f"""
        update `tabDocField`
           set hidden = 0,
               depends_on = null
         where parent = %s
           and fieldname in ({visible_placeholders})
           and (
                coalesce(hidden, 0) != 0
                or coalesce(depends_on, '') != ''
           )
        """,
        (DOCTYPE, *VISIBLE_PLAN_SURFACE_FIELDS),
    )


def cutting_plan_surface_metadata_state() -> dict[str, object]:
    """Return the effective field levels and any surviving local overrides."""

    if not frappe.db.exists("DocType", DOCTYPE):
        return {
            "doctype": DOCTYPE,
            "fields": {},
            "visibility": {},
            "property_setters": [],
        }

    meta = frappe.get_meta(DOCTYPE)
    fields: dict[str, int | None] = {}
    for fieldname in CUTTING_PLAN_SURFACE_FIELDS:
        field = meta.get_field(fieldname)
        fields[fieldname] = None if field is None else int(field.permlevel or 0)

    visibility: dict[str, dict[str, object] | None] = {}
    for fieldname in VISIBLE_PLAN_SURFACE_FIELDS:
        field = meta.get_field(fieldname)
        visibility[fieldname] = None if field is None else {
            "hidden": int(field.hidden or 0),
            "depends_on": str(field.depends_on or ""),
        }

    property_setters = frappe.get_all(
        "Property Setter",
        filters={
            "doc_type": DOCTYPE,
            "field_name": ["in", CUTTING_PLAN_SURFACE_FIELDS],
            "property": "permlevel",
        },
        fields=["name", "field_name", "property", "value"],
    )
    property_setters.extend(
        frappe.get_all(
            "Property Setter",
            filters={
                "doc_type": DOCTYPE,
                "field_name": ["in", VISIBLE_PLAN_SURFACE_FIELDS],
                "property": ["in", ("hidden", "depends_on")],
            },
            fields=["name", "field_name", "property", "value"],
        )
    )
    property_setters.sort(
        key=lambda row: (
            str(row.get("field_name", "")),
            str(row.get("property", "")),
            str(row.get("name", "")),
        )
    )
    return {
        "doctype": DOCTYPE,
        "fields": fields,
        "visibility": visibility,
        "property_setters": [dict(row) for row in property_setters],
    }


def _assert_cutting_plan_surface_metadata() -> None:
    state = cutting_plan_surface_metadata_state()
    invalid = {
        fieldname: permlevel
        for fieldname, permlevel in state["fields"].items()
        if permlevel != 0
    }
    invalid_visibility = {
        fieldname: values
        for fieldname, values in state["visibility"].items()
        if not values
        or values["hidden"] != 0
        or values["depends_on"]
    }
    setters = state["property_setters"]
    if not invalid and not invalid_visibility and not setters:
        return

    raise RuntimeError(
        "Cutting Plan metadata repair failed: "
        f"invalid permlevels={invalid}, invalid visibility={invalid_visibility}, "
        f"property_setters={setters}"
    )


def sync_cutting_plan_surface_metadata() -> None:
    """Enforce the plan/cost metadata boundary after model synchronization.

    ``view_costs`` intentionally controls Frappe permission level 1. The
    Cutting Plan surface is controlled by Almdina's ``view_cutting_plan``
    capability instead, so its fields must stay at permission level 0.

    A site-local Property Setter or stale DocField value can otherwise make
    Frappe omit ``plan_control_actions`` and ``cutting_plan_html`` whenever the
    role has no level-1 cost read permission. That produces an apparently empty
    Board Layout while the ordinary level-0 plan fields remain visible.
    """

    if not frappe.db.exists("DocType", DOCTYPE):
        return

    _remove_stale_property_setters()
    _repair_standard_docfields()
    frappe.clear_cache(doctype=DOCTYPE)
    _assert_cutting_plan_surface_metadata()


__all__ = [
    "CUTTING_PLAN_SURFACE_FIELDS",
    "VISIBLE_PLAN_SURFACE_FIELDS",
    "cutting_plan_surface_metadata_state",
    "sync_cutting_plan_surface_metadata",
]
