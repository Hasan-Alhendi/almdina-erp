from __future__ import annotations

from dataclasses import dataclass

import frappe


@dataclass(frozen=True, slots=True)
class MasterDataReference:
    doctype: str
    fieldname: str
    count: int


def find_link_references(target_doctype: str, target_name: str) -> list[MasterDataReference]:
    """Return active Link references to one master-data record.

    The implementation discovers Link fields from metadata so new order or child
    fields cannot silently bypass deletion protection.
    """

    rows = frappe.get_all(
        "DocField",
        filters={"fieldtype": "Link", "options": target_doctype},
        fields=["parent", "fieldname"],
        order_by="parent asc, idx asc",
    )
    references: list[MasterDataReference] = []
    for row in rows:
        doctype = str(row.parent)
        fieldname = str(row.fieldname)
        if doctype == target_doctype:
            continue
        try:
            meta = frappe.get_meta(doctype)
        except Exception:
            continue
        if meta.issingle:
            count = int(frappe.db.get_single_value(doctype, fieldname) == target_name)
        elif frappe.db.table_exists(doctype):
            count = int(frappe.db.count(doctype, {fieldname: target_name}) or 0)
        else:
            count = 0
        if count:
            references.append(MasterDataReference(doctype, fieldname, count))
    return references


def reference_summary(references: list[MasterDataReference]) -> str:
    return ", ".join(
        f"{reference.doctype}.{reference.fieldname} ({reference.count})"
        for reference in references
    )


__all__ = ["MasterDataReference", "find_link_references", "reference_summary"]
