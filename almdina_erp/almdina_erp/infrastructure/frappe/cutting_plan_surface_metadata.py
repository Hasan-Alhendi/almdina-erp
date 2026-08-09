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


def _remove_stale_permlevel_property_setters() -> None:
    """Remove site-local overrides that can couple plan UI to cost permlevel 1."""

    if not frappe.db.exists("DocType", "Property Setter"):
        return

    names = frappe.get_all(
        "Property Setter",
        filters={
            "doc_type": DOCTYPE,
            "field_name": ["in", CUTTING_PLAN_SURFACE_FIELDS],
            "property": "permlevel",
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

    _remove_stale_permlevel_property_setters()
    _repair_standard_docfields()
    frappe.clear_cache(doctype=DOCTYPE)


__all__ = ["CUTTING_PLAN_SURFACE_FIELDS", "sync_cutting_plan_surface_metadata"]
