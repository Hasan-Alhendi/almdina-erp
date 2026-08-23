from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_operational_workers_keep_assigned_scope_despite_adjacent_grants():
    permissions = source("permissions.py")
    authorization = source(
        "almdina_erp/domain/security/authorization.py"
    )
    matrix = source(
        "almdina_erp/application/security/permission_matrix.py"
    )
    predicate = permissions.split("def _requires_assigned_scope", 1)[1].split(
        "def _pre_production_status_sql", 1
    )[0]

    assert "VIEW_ALL_ORDERS = \"view_all_orders\"" in authorization
    assert "Capability.VIEW_ALL_ORDERS" in matrix
    assert "frozenset({Capability.VIEW_ALL_ORDERS})" in permissions
    assert "PRODUCTION_SUPERVISOR_CAPABILITIES" not in permissions
    assert "REPORTING_CAPABILITIES" not in permissions
    assert "_FLOOR_WORKER_CAPABILITIES | _WORKER_SCOPED_CAPABILITIES" in predicate
    assert predicate.index("_SCOPE_OVERRIDING_CAPABILITIES") < predicate.index(
        "_FLOOR_WORKER_CAPABILITIES | _WORKER_SCOPED_CAPABILITIES"
    )


def test_stage_assignment_time_is_persisted_and_backfilled():
    metadata = json.loads(
        source("almdina_erp/doctype/production_stage/production_stage.json")
    )
    repository = source(
        "almdina_erp/infrastructure/frappe/production_stage_repository.py"
    )
    patches = source("patches.txt")
    backfill = source(
        "patches/v1_0/backfill_production_stage_assignment_time.py"
    )

    fields = {row["fieldname"]: row for row in metadata["fields"]}
    assert fields["assignment_time"]["fieldtype"] == "Datetime"
    assert "stage.assignment_time = now_datetime()" in repository
    assert "backfill_production_stage_assignment_time" in patches
    assert "set assignment_time = creation" in backfill


def test_server_returns_worker_specific_sort_timestamps():
    query_repository = source(
        "almdina_erp/infrastructure/frappe/shop_floor_query_repository.py"
    )
    queries = source("almdina_erp/application/shop_floor/queries.py")

    assert 'order_by="assignment_time asc, creation asc"' in query_repository
    assert 'order_by="finish_time desc, modified desc"' in query_repository
    assert "def personal_order_stage_timings" in query_repository
    assert "ps.name = dco.current_production_stage" in query_repository
    assert "coalesce(ps.finish_time, ps.modified)" in query_repository
    assert '"assignment_state": "assigned" if is_current_assignee else "completed"' in queries
    assert '"assignment_time": _value(timing, "assignment_time")' in queries
    assert '"completion_time": _value(timing, "completion_time")' in queries


def test_shared_list_sorts_by_stage_times_and_colors_only_completed_rows():
    list_source = source("public/js/door_cutting_order_list.js")
    css = source("public/css/door_cutting_order_responsive.css")

    assert '"assignment_time",\n            1' in list_source
    assert '"completion_time",\n            -1' in list_source
    assert "[...assigned, ...completed]" in list_source
    assert "dco-list-row-completed" in list_source
    assert ".list-row-container.dco-list-row-completed" in css
    assert "> .list-row .list-row-col" in css


def test_shop_floor_uses_one_list_without_an_archive_tab():
    inbox = source(
        "almdina_erp/page/shop_floor_inbox/shop_floor_inbox.js"
    )
    css = source("public/css/door_cutting_order_responsive.css")

    assert 'data-sf-mode="archive"' not in inbox
    assert "function mergeVisibleList" in inbox
    assert 'const { assigned, completed } = mergeVisibleList' in inbox
    assert 'listSection(__("الطلبات المنتهية"), completed' in inbox
    assert "almdina-sf-order-card.is-completed" in css


def test_operator_uses_the_same_order_list_route_as_admin():
    navigation = source(
        "almdina_erp/application/security/navigation_context.py"
    )
    shared_shell = source("public/js/shared_shell.js")
    order_form = source("public/js/shop_floor_order_ux.js")

    operator_branch = navigation.split("if operator_only:", 1)[1].split(
        "elif active:", 1
    )[0]
    operator_home = navigation.split("elif operator_only:", 1)[1].split(
        "else:", 1
    )[0]
    assert "workspaces.append(WORKSPACE_MAIN)" in operator_branch
    assert "home_page = ORDER_LIST_ROUTE" in operator_home
    assert 'default_route = f"/desk/{ORDER_LIST_ROUTE}"' in operator_home
    assert 'requested === "door-cutting-order"' in shared_shell
    assert 'frappe.set_route("shop-floor-inbox")' not in order_form
    assert 'add_custom_button(__("العودة إلى الطلبات")' not in order_form
