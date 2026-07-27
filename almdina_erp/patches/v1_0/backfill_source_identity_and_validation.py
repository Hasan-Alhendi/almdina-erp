from __future__ import annotations

import frappe
from frappe.utils import flt


def execute() -> None:
    # Re-apply required roles, edge masters, routing and settings defaults without
    # recalculating any historical approved order.
    from almdina_erp.install import sync_setup

    sync_setup()
    _backfill_cutting_plan_source_identity()
    _backfill_validation_timestamps()


def _backfill_cutting_plan_source_identity() -> None:
    if not frappe.db.table_exists("tabCutting Plan Source"):
        return

    rows = frappe.get_all(
        "Cutting Plan Source",
        fields=["name", "source_type", "remnant", "material", "color", "thickness_mm"],
    )

    for row in rows:
        if row.material or row.color or flt(row.thickness_mm):
            continue
        if row.source_type != "Remnant" or not row.remnant:
            continue

        identity = frappe.db.get_value(
            "Board Remnant",
            row.remnant,
            ["material", "color", "thickness_mm"],
            as_dict=True,
        )
        if not identity:
            continue

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
