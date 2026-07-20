from __future__ import annotations

import frappe
from frappe.utils import flt


def execute() -> None:
    # Re-apply required roles, MDF Item custom fields, edge masters, routing and
    # settings defaults without recalculating any historical approved order.
    from almdina_erp.install import sync_setup

    sync_setup()
    _backfill_cutting_plan_source_identity()
    _backfill_validation_timestamps()


def _backfill_cutting_plan_source_identity() -> None:
    if not frappe.db.table_exists("tabCutting Plan Source"):
        return

    rows = frappe.get_all(
        "Cutting Plan Source",
        fields=["name", "parent", "source_type", "remnant", "material", "color", "thickness_mm"],
    )
    order_cache: dict[str, object] = {}

    for row in rows:
        if row.material or row.color or flt(row.thickness_mm):
            continue

        identity = None
        if row.source_type == "Remnant" and row.remnant:
            identity = frappe.db.get_value(
                "Board Remnant",
                row.remnant,
                ["material", "color", "thickness_mm"],
                as_dict=True,
            )

        if not identity:
            order_name = frappe.db.get_value("Cutting Plan", row.parent, "door_cutting_order")
            if order_name:
                identity = order_cache.get(order_name)
                if not identity:
                    identity = frappe.db.get_value(
                        "Door Cutting Order",
                        order_name,
                        ["board_material", "board_color", "board_thickness_mm"],
                        as_dict=True,
                    )
                    order_cache[order_name] = identity
                if identity:
                    identity = frappe._dict(
                        material=identity.board_material,
                        color=identity.board_color,
                        thickness_mm=identity.board_thickness_mm,
                    )

        if identity:
            frappe.db.set_value(
                "Cutting Plan Source",
                row.name,
                {
                    "material": identity.material or "",
                    "color": identity.color or "",
                    "thickness_mm": flt(identity.thickness_mm),
                },
                update_modified=False,
            )


def _backfill_validation_timestamps() -> None:
    if not frappe.db.table_exists("tabCutting Plan"):
        return

    frappe.db.sql(
        """
        update `tabCutting Plan`
        set validated_on = coalesce(approved_on, modified)
        where validation_status in ('Valid', 'Invalid')
          and validated_on is null
        """
    )
