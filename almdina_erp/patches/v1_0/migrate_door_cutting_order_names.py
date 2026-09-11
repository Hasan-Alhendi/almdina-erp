from __future__ import annotations

from collections import defaultdict

import frappe
from frappe.model.naming import NamingSeries
from frappe.model.rename_doc import rename_doc

from almdina_erp.almdina_erp.domain.orders.order_identity import (
    compact_legacy_order_name,
    compact_order_sequence,
)


DOCTYPE = "Door Cutting Order"


def _rename_legacy_orders(names: list[str]) -> None:
    existing_names = set(names)
    planned_targets: set[str] = set()
    renames: list[tuple[str, str]] = []

    for old_name in names:
        new_name = compact_legacy_order_name(old_name)
        if not new_name:
            continue
        if new_name in existing_names or new_name in planned_targets:
            frappe.throw(
                f"Cannot migrate {old_name} to {new_name}: the compact order ID already exists."
            )
        planned_targets.add(new_name)
        renames.append((old_name, new_name))

    for old_name, new_name in renames:
        rename_doc(
            doctype=DOCTYPE,
            old=old_name,
            new=new_name,
            force=True,
            ignore_permissions=True,
            show_alert=False,
            rebuild_search=False,
        )


def _synchronize_compact_series() -> None:
    max_sequence_by_year: defaultdict[str, int] = defaultdict(int)
    for name in frappe.get_all(DOCTYPE, pluck="name"):
        parsed = compact_order_sequence(name)
        if not parsed:
            continue
        year, sequence = parsed
        max_sequence_by_year[year] = max(max_sequence_by_year[year], sequence)

    for year, sequence in max_sequence_by_year.items():
        NamingSeries(f"{year}-.#####").update_counter(sequence)


def execute() -> None:
    if not frappe.db.table_exists(DOCTYPE):
        return

    names = frappe.get_all(DOCTYPE, pluck="name", order_by="name asc")
    if not names:
        return

    _rename_legacy_orders(names)
    _synchronize_compact_series()
