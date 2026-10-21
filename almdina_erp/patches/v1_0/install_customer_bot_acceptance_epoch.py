"""Add the acceptance cycle counter without rewriting bot settings.

The row is inserted only when it is absent. Enabled, revision, draft texts,
and published texts stay as they are.
"""

from __future__ import annotations


def execute() -> None:
    import frappe

    doctype = "Customer Bot Settings"
    if not frappe.db.sql(
        "select 1 from `tabSingles` where doctype=%s and field='revision' limit 1",
        (doctype,),
    ):
        return
    if frappe.db.sql(
        "select 1 from `tabSingles` where doctype=%s and field='acceptance_epoch' limit 1",
        (doctype,),
    ):
        return
    frappe.db.sql(
        "insert into `tabSingles` (doctype, field, value) values (%s, 'acceptance_epoch', '0')",
        (doctype,),
    )
