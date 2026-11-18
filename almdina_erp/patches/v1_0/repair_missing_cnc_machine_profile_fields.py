from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.domain.cnc.machine_profile import (
    SAMPLE_MACHINE_PROFILE,
    machine_profile_seed_updates,
)


def execute() -> None:
    """Fill CNC machine-profile fields that are absent or blank.

    ``seed_cnc_machine_profile_sample`` does not run again after it is logged.
    A later save of this Single can also drop rows that were not on the
    document being saved. This patch reads the raw ``tabSingles`` rows and
    fills only those gaps. A stored non-blank value, including an explicit
    production-approval flag, is left unchanged.

    Do not pass ``get_single_value`` results into the seed rule. A missing
    number is cast to 0 and would look like a value the user saved.
    """

    if not frappe.db.exists("DocType", "Almdina ERP Settings"):
        return
    meta = frappe.get_meta("Almdina ERP Settings")
    fields = [name for name in SAMPLE_MACHINE_PROFILE if meta.get_field(name)]
    if not fields:
        return
    rows = frappe.db.sql(
        """
        select field, value
          from `tabSingles`
         where doctype = %s
           and field in %s
        """,
        ("Almdina ERP Settings", tuple(fields)),
        as_dict=True,
    )
    stored = {row.field: row.value for row in rows}
    updates = {
        field: value
        for field, value in machine_profile_seed_updates(stored).items()
        if field in fields
    }
    if not updates:
        return
    frappe.db.set_single_value("Almdina ERP Settings", updates, update_modified=False)
