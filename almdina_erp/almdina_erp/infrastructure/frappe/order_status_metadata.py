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
    "Delivered",
    "Cancelled",
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
        select distinct ps.department_label
          from `tabDoor Cutting Order` dco
          inner join `tabProduction Stage` ps
                  on ps.name = dco.current_production_stage
         where ifnull(ps.department_label, '') != ''
         order by ps.department_label asc
        """,
        as_list=True,
    )
    return _unique_nonempty(row[0] for row in rows)


def build_order_status_options() -> tuple[str, ...]:
    """Build the Select projection consumed by native List/Kanban surfaces."""

    production_stages = _unique_nonempty(
        (*_stage_labels(), *_in_flight_status_values())
    )
    return tuple(
        _unique_nonempty(
            (
                FIXED_ORDER_STATUS_OPTIONS[0],
                *production_stages,
                *FIXED_ORDER_STATUS_OPTIONS[1:],
            )
        )
    )


def _sync_kanban_boards(options: tuple[str, ...]) -> None:
    """Replace persisted DCO Status board columns with the canonical projection."""

    if not frappe.db.exists("DocType", "Kanban Board"):
        return
    board_names = frappe.get_all(
        "Kanban Board",
        filters={
            "reference_doctype": ORDER_DOCTYPE,
            "field_name": STATUS_FIELDNAME,
        },
        pluck="name",
    )
    for board_name in board_names:
        board = frappe.get_doc("Kanban Board", board_name)
        existing = {
            str(column.column_name): {
                "indicator": column.indicator,
                "order": column.order,
            }
            for column in board.columns
        }
        board.set("columns", [])
        for option in options:
            preserved = existing.get(option, {})
            board.append(
                "columns",
                {
                    "column_name": option,
                    "indicator": preserved.get("indicator") or "Gray",
                    "order": preserved.get("order") or "[]",
                },
            )
        board.save(ignore_permissions=True)


def sync_order_status_options() -> tuple[str, ...]:
    """Synchronize the app-owned Status Select and persisted Kanban columns."""

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
    _sync_kanban_boards(options)
    frappe.clear_cache(doctype=ORDER_DOCTYPE)
    return options


__all__ = [
    "FIXED_ORDER_STATUS_OPTIONS",
    "build_order_status_options",
    "sync_order_status_options",
]
