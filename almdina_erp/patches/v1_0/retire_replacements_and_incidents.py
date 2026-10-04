from __future__ import annotations

import json

import frappe

from almdina_erp.almdina_erp.domain.orders.lifecycle import (
    StageState,
    derive_order_status,
    order_status_for_stage,
)


RETIRED_CAPABILITY_KEYS = (
    "edit_replacement_cost",
    "view_production_incidents",
    "record_incident",
    "create_replacement",
    "view_replacements",
    "approve_replacement",
    "start_replacement",
    "complete_replacement",
    "cancel_replacement",
)
RETIRED_PERMISSION_TYPES = tuple(
    key for key in RETIRED_CAPABILITY_KEYS if key != "view_production_incidents"
)
_CHILD_TABLES = ("Cutting Plan Source", "Cutting Plan Piece")


def execute() -> None:
    """Drop replacement and incident data without touching order production.

    The patch is idempotent. It uses table existence because the DocType modules
    are removed in the same release, and a second migrate finds nothing to do.
    """

    _restore_replacement_required_orders()
    _clear_internal_replacement_loss()
    _delete_replacement_plans()
    _delete_table_rows("Replacement Piece")
    _delete_table_rows("Production Incident")
    _strip_retired_capabilities()
    _delete_retired_permission_types()


def _restore_replacement_required_orders() -> None:
    if not frappe.db.table_exists("Door Cutting Order"):
        return
    if not frappe.db.has_column("Door Cutting Order", "status"):
        return
    orders = frappe.db.sql(
        """
        select name, production_path, current_production_stage
        from `tabDoor Cutting Order`
        where status = 'Replacement Required'
        """,
        as_dict=True,
    )
    for order in orders:
        frappe.db.set_value(
            "Door Cutting Order",
            order.name,
            "status",
            _restored_status(order),
            update_modified=False,
        )


def _restored_status(order) -> str:
    stage_name = str(order.current_production_stage or "").strip()
    if stage_name and frappe.db.table_exists("Production Stage"):
        stage = frappe.db.sql(
            """
            select stage_type, department_label, status
            from `tabProduction Stage`
            where name = %s
            """,
            (stage_name,),
            as_dict=True,
        )
        if stage and stage[0].status != "Cancelled":
            return order_status_for_stage(
                stage[0].stage_type,
                stage[0].department_label,
            )

    stages = _base_stages(order.name)
    if not stages:
        return "Approved"
    derived = derive_order_status(
        current_status="Approved",
        production_path=order.production_path,
        current_stage=None,
        stages=(
            StageState(row.stage_type, row.status, row.department_label)
            for row in stages
        ),
    )
    if derived == "Replacement Required":
        return "Approved"
    return derived


def _base_stages(order_name: str) -> list:
    if not frappe.db.table_exists("Production Stage"):
        return []
    rows = frappe.db.sql(
        """
        select stage_type, department_label, status, piece_label
        from `tabProduction Stage`
        where door_cutting_order = %s
        order by sequence asc
        """,
        (order_name,),
        as_dict=True,
    )
    return [row for row in rows if not (row.piece_label or "")]


def _clear_internal_replacement_loss() -> None:
    if not frappe.db.table_exists("Door Cutting Order"):
        return
    if not frappe.db.has_column("Door Cutting Order", "internal_loss_cost_usd"):
        return
    if not frappe.db.has_column("Door Cutting Order", "actual_cost_usd"):
        return
    if not frappe.db.has_column("Door Cutting Order", "total_cost_usd"):
        return
    frappe.db.sql(
        """
        update `tabDoor Cutting Order`
        set actual_cost_usd = coalesce(total_cost_usd, 0),
            internal_loss_cost_usd = 0
        where coalesce(internal_loss_cost_usd, 0) <> 0
        """
    )


def _delete_replacement_plans() -> None:
    if not frappe.db.table_exists("Cutting Plan"):
        return
    if not frappe.db.has_column("Cutting Plan", "plan_kind"):
        return
    names = [
        row.name
        for row in frappe.db.sql(
            """
            select name
            from `tabCutting Plan`
            where plan_kind = 'Replacement'
            """,
            as_dict=True,
        )
    ]
    if not names:
        return
    names = tuple(names)
    if frappe.db.table_exists("Door Cutting Order") and frappe.db.has_column(
        "Door Cutting Order", "approved_plan"
    ):
        frappe.db.sql(
            """
            update `tabDoor Cutting Order`
            set approved_plan = null
            where approved_plan in %(names)s
            """,
            {"names": names},
        )
    if frappe.db.has_column("Cutting Plan", "based_on_plan"):
        frappe.db.sql(
            """
            update `tabCutting Plan`
            set based_on_plan = null
            where based_on_plan in %(names)s
            """,
            {"names": names},
        )
    for child in _CHILD_TABLES:
        if not frappe.db.table_exists(child):
            continue
        frappe.db.sql(
            f"""
            delete from `tab{child}`
            where parenttype = 'Cutting Plan'
              and parent in %(names)s
            """,
            {"names": names},
        )
    frappe.db.sql(
        """
        delete from `tabCutting Plan`
        where name in %(names)s
        """,
        {"names": names},
    )


def _delete_table_rows(doctype: str) -> None:
    if frappe.db.table_exists(doctype):
        frappe.db.sql(f"delete from `tab{doctype}`")


def _strip_retired_capabilities() -> None:
    if not frappe.db.table_exists("Almdina Role Capability State"):
        return
    if not frappe.db.has_column("Almdina Role Capability State", "capabilities_json"):
        return
    retired = set(RETIRED_CAPABILITY_KEYS)
    rows = frappe.db.sql(
        """
        select name, capabilities_json
        from `tabAlmdina Role Capability State`
        """,
        as_dict=True,
    )
    for row in rows:
        try:
            payload = json.loads(row.capabilities_json or "{}")
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        cleaned = {key: value for key, value in payload.items() if key not in retired}
        if cleaned == payload:
            continue
        frappe.db.set_value(
            "Almdina Role Capability State",
            row.name,
            "capabilities_json",
            json.dumps(cleaned, ensure_ascii=False, sort_keys=True),
            update_modified=False,
        )


def _delete_retired_permission_types() -> None:
    if frappe.db.table_exists("Permission Type"):
        frappe.db.sql(
            """
            delete from `tabPermission Type`
            where name in %(names)s
            """,
            {"names": RETIRED_PERMISSION_TYPES},
        )
    if not frappe.db.table_exists("Custom Field"):
        return
    frappe.db.sql(
        """
        delete from `tabCustom Field`
        where dt in ('DocPerm', 'Custom DocPerm')
          and fieldname in %(names)s
        """,
        {"names": RETIRED_PERMISSION_TYPES},
    )
