from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.domain.cnc.machine_profile import (
    SAMPLE_MACHINE_PROFILE,
    machine_profile_seed_updates,
)


def execute() -> None:
    """Fill empty machine-profile sample fields. Later edits stay in place."""

    if not frappe.db.exists("DocType", "Almdina ERP Settings"):
        return
    current = {
        field: frappe.db.get_single_value("Almdina ERP Settings", field)
        for field in SAMPLE_MACHINE_PROFILE
    }
    updates = machine_profile_seed_updates(current)
    if not updates:
        return
    settings = frappe.get_single("Almdina ERP Settings")
    for field, value in updates.items():
        settings.set(field, value)
    settings.flags.ignore_permissions = True
    settings.flags.ignore_mandatory = True
    settings.save(ignore_permissions=True)
