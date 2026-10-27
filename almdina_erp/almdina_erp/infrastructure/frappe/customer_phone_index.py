"""Server-owned normalized copy of ``Customer.mobile_no``.

``Customer.mobile_no`` stays the source of truth. The hidden field is only an
index so a lookup can match the current normalization rules without reading
every customer. It is not unique: two customers with the same number stay a
conflict. Nothing here caches which customer owns a number.

Supported writes keep the index inside the same database transaction:

- Customer insert and save, including Desk, ``frappe.client.set_value``,
  POS ``customer_doc.save()``, and Data Import ``insert_record`` /
  ``update_record``. ``before_save`` puts the index on the document, so the
  ORM writes both columns in that statement.
- ``Document.db_set``, including ERPNext ``Customer.create_primary_contact``
  which calls ``db_set("mobile_no", ...)`` and skips ``before_save``.
  ``on_change`` writes the index before the request commits.
- ``assign_customer_primary_mobile`` updates both columns in one
  ``frappe.db.set_value`` because that call does not run document hooks.

Unsupported, and not repaired by a per-message scan: a raw SQL ``UPDATE`` of
``mobile_no``, or ``frappe.db.set_value`` of ``mobile_no`` alone. The index
stays stale until the next supported write or the idempotent backfill.
Re-reading only the customers the index already returned cannot see another
customer who now holds the same number with an old index value. Lookup does
not fall back to reading every ``mobile_no``.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from almdina_erp.almdina_erp.domain.customer_bot.phone_number import (
    CustomerPhoneError,
    normalize_customer_phone,
)


NORMALIZED_MOBILE_FIELD = "custom_almdina_normalized_mobile"


def normalized_mobile_for_storage(raw: object) -> str | None:
    """Return the indexed E.164 value, or None when the raw phone is unusable."""

    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return normalize_customer_phone(text)
    except CustomerPhoneError:
        return None


def sync_customer_normalized_mobile(doc, method: str | None = None) -> None:
    """Put the index on the document so insert/save writes it with ``mobile_no``."""

    del method
    desired = _desired_index_value(doc)
    if desired is None:
        return
    doc.set(NORMALIZED_MOBILE_FIELD, desired)


def sync_customer_normalized_mobile_after_value_change(doc, method: str | None = None) -> None:
    """Align the index after ``Document.db_set``, which skips ``before_save``.

    The follow-up write stays in the open transaction. It does not commit.
    """

    del method
    desired = _desired_index_value(doc)
    if desired is None or not getattr(doc, "name", None):
        return
    stored = frappe.db.get_value("Customer", doc.name, NORMALIZED_MOBILE_FIELD) or ""
    if str(stored) == desired:
        doc.set(NORMALIZED_MOBILE_FIELD, desired)
        return
    frappe.db.set_value(
        "Customer",
        doc.name,
        NORMALIZED_MOBILE_FIELD,
        desired,
        update_modified=False,
    )
    doc.set(NORMALIZED_MOBILE_FIELD, desired)


def _desired_index_value(doc) -> str | None:
    if getattr(doc, "doctype", None) != "Customer":
        return None
    if not frappe.get_meta("Customer").has_field(NORMALIZED_MOBILE_FIELD):
        return None
    return normalized_mobile_for_storage(getattr(doc, "mobile_no", None)) or ""


def assign_customer_primary_mobile(
    customer_id: str,
    mobile_no: str | None,
    *,
    update_modified: bool = True,
) -> None:
    """Write the primary phone and its normalized index in one server update."""

    stored = "" if mobile_no is None else str(mobile_no)
    values = {"mobile_no": stored}
    if frappe.db.has_column("Customer", NORMALIZED_MOBILE_FIELD):
        values[NORMALIZED_MOBILE_FIELD] = normalized_mobile_for_storage(stored) or ""
    frappe.db.set_value("Customer", customer_id, values, update_modified=update_modified)


def sync_customer_normalized_mobile_index() -> int:
    """Create the non-unique index and backfill it. Safe to run more than once.

    When the column and its non-unique index already exist, the custom field
    document is left untouched. Unchanged customer rows are not rewritten.
    """

    if not frappe.db.exists("DocType", "Customer"):
        return 0
    if not frappe.db.has_column("Customer", NORMALIZED_MOBILE_FIELD):
        create_custom_fields(
            {
                "Customer": [
                    {
                        "fieldname": NORMALIZED_MOBILE_FIELD,
                        "label": "Normalized Mobile",
                        "fieldtype": "Data",
                        "length": 20,
                        "hidden": 1,
                        "read_only": 1,
                        "no_copy": 1,
                        "search_index": 1,
                        "unique": 0,
                        "description": "Server-owned lookup key for Customer.mobile_no. Not a second phone.",
                    }
                ]
            },
            update=True,
        )
        frappe.clear_cache(doctype="Customer")
        frappe.client_cache.delete_value("table_columns::tabCustomer")
    elif not frappe.db.has_index("tabCustomer", f"{NORMALIZED_MOBILE_FIELD}_index"):
        frappe.db.add_index(
            "Customer",
            [NORMALIZED_MOBILE_FIELD],
            f"{NORMALIZED_MOBILE_FIELD}_index",
        )
    return backfill_customer_normalized_mobiles()


def backfill_customer_normalized_mobiles() -> int:
    """Set the index from current ``mobile_no`` values. Unchanged rows are left alone."""

    if not frappe.db.has_column("Customer", NORMALIZED_MOBILE_FIELD):
        return 0
    rows = frappe.db.sql(
        f"""select name, mobile_no, `{NORMALIZED_MOBILE_FIELD}` as normalized
            from `tabCustomer`""",
        as_dict=True,
    )
    changed = 0
    for row in rows:
        desired = normalized_mobile_for_storage(row.mobile_no) or ""
        if str(row.normalized or "") == desired:
            continue
        frappe.db.set_value(
            "Customer",
            row.name,
            NORMALIZED_MOBILE_FIELD,
            desired,
            update_modified=False,
        )
        changed += 1
    return changed


def customer_ids_for_indexed_phone(normalized_phone: str) -> tuple[str, ...]:
    """Return every customer id stored under this normalized phone.

    An unknown column fails closed. This does not read ``mobile_no`` and does
    not cache the result.
    """

    if not isinstance(normalized_phone, str) or not normalized_phone.startswith("+"):
        return ()
    if not frappe.db.has_column("Customer", NORMALIZED_MOBILE_FIELD):
        return ()
    rows = frappe.db.sql(
        f"""select name
            from `tabCustomer`
            where `{NORMALIZED_MOBILE_FIELD}`=%s
            order by name asc""",
        (normalized_phone,),
        as_dict=True,
    )
    matches: list[str] = []
    for row in rows:
        customer_id = str(row.name or "")
        if customer_id and customer_id not in matches:
            matches.append(customer_id)
    return tuple(matches)


__all__ = [
    "NORMALIZED_MOBILE_FIELD",
    "assign_customer_primary_mobile",
    "backfill_customer_normalized_mobiles",
    "customer_ids_for_indexed_phone",
    "normalized_mobile_for_storage",
    "sync_customer_normalized_mobile",
    "sync_customer_normalized_mobile_after_value_change",
    "sync_customer_normalized_mobile_index",
]
