from __future__ import annotations

from collections.abc import Iterable

import frappe


ORDER_DOCTYPE = "Door Cutting Order"
STAGE_DEFINITION_DOCTYPE = "Production Stage Definition"
STATUS_FIELDNAME = "status"

# These values are lifecycle/business states, not production stages. Production
# stage values are projected from Production Stage Definition at runtime.
FIXED_ORDER_STATUS_OPTIONS: tuple[str, ...] = (
    "Draft",
    "Pending Review",
    "Approved",
    "Ready for Delivery",
    "Delivered",
    "Completed",
    "Rejected",
    "On Hold",
    "Cancelled",
    "Replacement Required",
    "Partially Completed",
)


def _unique_nonempty(values: Iterable[object]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _stage_labels() -> list[str]:
    if not frappe.db.exists("DocType", STAGE_DEFINITION_DOCTYPE):
        return []
    rows = frappe.get_all(
        STAGE_DEFINITION_DOCTYPE,
        filters={"disabled": 0},
        fields=["stage_label"],
        order_by="stage_label asc",
    )
    return _unique_nonempty(row.stage_label for row in rows)


def _in_flight_status_values() -> list[str]:
    """Keep snapshot labels valid while an already-dispatched order uses them.

    Disabling or renaming a library stage must not invalidate the status of an
    execution stage that was created earlier. Runtime Production Stage is the
    snapshot boundary, so current order values stay in the Select metadata until
    those orders leave production.
    """

    if not frappe.db.exists("DocType", ORDER_DOCTYPE):
        return []
    rows = frappe.db.sql(
        """
        select distinct status
        from `tabDoor Cutting Order`
        where ifnull(current_production_stage, '') != ''
          and ifnull(status, '') != ''
        order by status asc
        """,
        as_list=True,
    )
    return _unique_nonempty(row[0] for row in rows)


def build_order_status_options() -> tuple[str, ...]:
    """Build the Select projection consumed by native List/Kanban surfaces."""

    return tuple(
        _unique_nonempty(
            (*FIXED_ORDER_STATUS_OPTIONS, *_stage_labels(), *_in_flight_status_values())
        )
    )


def sync_order_status_options() -> tuple[str, ...]:
    """Materialize dynamic stage labels into the app-owned status Select field.

    Frappe's native Kanban reads Select options from DocField metadata. Keeping
    this projection synchronized lets the existing Kanban remain completely
    native while production stages stay data-driven.
    """

    if not frappe.db.exists("DocType", ORDER_DOCTYPE):
        return ()

    field_name = frappe.db.get_value(
        "DocField",
        {"parent": ORDER_DOCTYPE, "fieldname": STATUS_FIELDNAME},
        "name",
    )
    if not field_name:
        return ()

    options = build_order_status_options()
    frappe.db.set_value(
        "DocField",
        field_name,
        "options",
        "\n".join(options),
        update_modified=False,
    )
    frappe.clear_cache(doctype=ORDER_DOCTYPE)
    return options


__all__ = [
    "FIXED_ORDER_STATUS_OPTIONS",
    "build_order_status_options",
    "sync_order_status_options",
]
