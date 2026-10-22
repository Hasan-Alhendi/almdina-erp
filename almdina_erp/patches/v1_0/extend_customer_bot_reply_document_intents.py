"""Ensure reply-intent columns for durable document descriptors exist.

DocType sync normally adds the fields. This patch is idempotent for sites that
already created the table before part_kind and document_spec were introduced.
"""

from __future__ import annotations


def execute() -> None:
    import frappe

    doctype = "Customer Bot Reply Intent"
    if not frappe.db.table_exists(doctype):
        return
    wanted = {
        "part_kind": "varchar(140) not null default 'text'",
        "document_spec": "longtext null",
        "customer_id": "varchar(140) null",
        "normalized_phone": "varchar(140) null",
        "acceptance_epoch": "int(11) null",
    }
    for fieldname, ddl in wanted.items():
        if frappe.db.has_column(doctype, fieldname):
            continue
        frappe.db.sql(f"alter table `tab{doctype}` add column `{fieldname}` {ddl}")
    if frappe.db.has_column(doctype, "part_kind"):
        frappe.db.sql(
            f"update `tab{doctype}` set part_kind='text' where part_kind is null or part_kind=''"
        )


__all__ = ["execute"]
