from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import frappe


_MAX_PROFILE_ORDER_NAMES = 100


def _normalize_order_names(order_names: Sequence[str] | None) -> tuple[str, ...]:
    if order_names is None:
        return ()
    if isinstance(order_names, str):
        values = [part.strip() for part in order_names.split(",")]
    else:
        values = [str(value or "").strip() for value in order_names]
    normalized = tuple(value for value in values if value)
    if len(normalized) > _MAX_PROFILE_ORDER_NAMES:
        raise ValueError(
            f"Database query profiling accepts at most {_MAX_PROFILE_ORDER_NAMES} order names."
        )
    return normalized


def _select_only(sql: str) -> str:
    normalized = str(sql or "").strip()
    if not normalized.lower().startswith("select "):
        raise ValueError("Only fixed SELECT query shapes may be profiled.")
    return normalized


def _row_mapping(row: Any) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return dict(row)
    keys = (
        "id",
        "select_type",
        "table",
        "partitions",
        "type",
        "possible_keys",
        "key",
        "key_len",
        "ref",
        "rows",
        "filtered",
        "Extra",
    )
    return {
        key: getattr(row, key)
        for key in keys
        if hasattr(row, key)
    }


def _value(row: Mapping[str, Any], *keys: str) -> Any:
    lowered = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        if key.lower() in lowered:
            return lowered[key.lower()]
    return None


def _risk_flags(plan_row: Mapping[str, Any]) -> list[str]:
    access_type = str(_value(plan_row, "type", "access_type") or "").upper()
    selected_key = _value(plan_row, "key")
    extra = str(_value(plan_row, "Extra", "extra") or "")
    flags: list[str] = []
    if access_type == "ALL":
        flags.append("full_scan")
    if not selected_key:
        flags.append("no_selected_key")
    if "using filesort" in extra.lower():
        flags.append("filesort")
    if "using temporary" in extra.lower():
        flags.append("temporary_table")
    return flags


def _normalize_plan(rows: Sequence[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        mapped = _row_mapping(row)
        result.append(
            {
                "table": _value(mapped, "table"),
                "access_type": _value(mapped, "type", "access_type"),
                "possible_keys": _value(mapped, "possible_keys"),
                "selected_key": _value(mapped, "key"),
                "key_length": _value(mapped, "key_len"),
                "ref": _value(mapped, "ref"),
                "estimated_rows": _value(mapped, "rows"),
                "filtered_percent": _value(mapped, "filtered"),
                "extra": _value(mapped, "Extra", "extra"),
                "risk_flags": _risk_flags(mapped),
            }
        )
    return result


def _explain(query_id: str, sql: str, values: Sequence[Any]) -> dict[str, Any]:
    statement = _select_only(sql)
    rows = frappe.db.sql(
        f"EXPLAIN {statement}",
        list(values),
        as_dict=True,
    )
    return {
        "query_id": query_id,
        "plan": _normalize_plan(rows),
    }


def _inbox_sql(*, include_assignee: bool) -> str:
    assignee_clause = "and ps.assigned_to = %s" if include_assignee else ""
    return f"""
        select ps.name,
               ps.door_cutting_order,
               ps.stage_type,
               ps.status,
               ps.assigned_to,
               ps.assignment_time,
               ps.creation
          from `tabProduction Stage` ps
         where ps.status in ('Pending', 'In Progress', 'Paused')
           and ifnull(ps.piece_label, '') = ''
           {assignee_clause}
         order by ps.assignment_time asc, ps.creation asc
    """


def _archive_sql(*, include_assignee: bool) -> str:
    assignee_clause = "and ps.assigned_to = %s" if include_assignee else ""
    return f"""
        select ps.name,
               ps.door_cutting_order,
               ps.stage_type,
               ps.status,
               ps.assigned_to,
               ps.finish_time,
               ps.modified
          from `tabProduction Stage` ps
         where ps.status = 'Completed'
           and ifnull(ps.piece_label, '') = ''
           {assignee_clause}
         order by ps.finish_time desc, ps.modified desc
         limit 100
    """


def _personal_timing_sql(order_count: int) -> str:
    placeholders = ", ".join(["%s"] * order_count)
    return f"""
        select ps.door_cutting_order,
               max(
                   case
                       when ps.name = dco.current_production_stage
                        and ps.status in ('Pending', 'In Progress', 'Paused')
                       then coalesce(ps.assignment_time, ps.creation)
                   end
               ) as assignment_time,
               max(
                   case
                       when ps.status = 'Completed'
                       then coalesce(ps.finish_time, ps.modified)
                   end
               ) as completion_time
          from `tabProduction Stage` ps
          inner join `tabDoor Cutting Order` dco
                  on dco.name = ps.door_cutting_order
         where ps.assigned_to = %s
           and ifnull(ps.piece_label, '') = ''
           and ps.door_cutting_order in ({placeholders})
         group by ps.door_cutting_order
    """


def profile_hot_queries(
    user: str,
    order_names: Sequence[str] | None = None,
) -> dict[str, Any]:
    """EXPLAIN fixed shop-floor query shapes without executing arbitrary SQL.

    This function is intentionally not whitelisted. Run it explicitly with
    ``bench --site <site> execute`` when collecting database evidence.
    """

    actor = str(user or "").strip()
    if not actor:
        raise ValueError("A representative user is required for query profiling.")

    names = _normalize_order_names(order_names)
    profiles = [
        _explain(
            "shop_floor_inbox_worker",
            _inbox_sql(include_assignee=True),
            [actor],
        ),
        _explain(
            "shop_floor_inbox_admin",
            _inbox_sql(include_assignee=False),
            [],
        ),
        _explain(
            "shop_floor_archive_worker",
            _archive_sql(include_assignee=True),
            [actor],
        ),
        _explain(
            "shop_floor_archive_admin",
            _archive_sql(include_assignee=False),
            [],
        ),
    ]

    if names:
        profiles.append(
            _explain(
                "personal_order_stage_timings",
                _personal_timing_sql(len(names)),
                [actor, *names],
            )
        )

    return {
        "read_only": True,
        "profiled_query_count": len(profiles),
        "order_sample_size": len(names),
        "profiles": profiles,
    }
