"""Close retired additional-phone grants without dropping schema or rows.

Repeated migrate only zeroes permission bits on the historical DocTypes.
It does not delete tables, columns, Permission Type rows, or stored
requests and access records.
"""

from __future__ import annotations


_DOCTYPES = (
    "Customer Bot Phone Access",
    "Customer Bot Phone Request",
)
_STANDARD_BITS = (
    "read",
    "write",
    "create",
    "delete",
    "submit",
    "cancel",
    "amend",
    "report",
    "export",
    "import",
    "share",
    "print",
    "email",
    "select",
)


def execute() -> None:
    import frappe

    for parent in _DOCTYPES:
        if not frappe.db.exists("DocType", parent):
            continue
        for permission_doctype in ("DocPerm", "Custom DocPerm"):
            if not frappe.db.exists("DocType", permission_doctype):
                continue
            names = frappe.get_all(
                permission_doctype,
                filters={"parent": parent},
                pluck="name",
            )
            for name in names:
                updates = {
                    field: 0
                    for field in _STANDARD_BITS
                    if frappe.db.has_column(permission_doctype, field)
                }
                if frappe.db.has_column(permission_doctype, "manage_customer_bot_access"):
                    updates["manage_customer_bot_access"] = 0
                if updates:
                    frappe.db.set_value(
                        permission_doctype,
                        name,
                        updates,
                        update_modified=False,
                    )
