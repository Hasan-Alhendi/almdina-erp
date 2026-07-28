"""Backward-compatible shop-floor API facade.

New code should import the focused command, query, DXF, or infrastructure modules
instead of adding business logic here. Existing API paths remain valid through
this module and Frappe's whitelisted-method overrides.
"""

from __future__ import annotations

from almdina_erp.almdina_erp.domain.orders.lifecycle import (
    CUTTING_LIKE_STAGE_TYPES,
    DEPARTMENT_STATUS_BY_STAGE_STATUS,
    PRODUCTION_PATHS,
    SHOP_FLOOR_ORDER_STATUSES,
    SHOP_FLOOR_STAGE_TYPES,
    STAGE_DEPARTMENTS,
    next_stage_type,
    production_path_sequence,
    resolve_shop_floor_stage_type,
    stage_sequence,
)
from almdina_erp.almdina_erp.infrastructure.frappe import shop_floor_gateway
from almdina_erp.almdina_erp.services.production_service import sync_order_status
from almdina_erp.almdina_erp.services.shop_floor_commands import (
    assert_order_ready_for_dispatch,
    dispatch_order,
    get_handoff_workers,
    handoff_to_next,
    mark_delivered,
    return_order_to_draft,
    revert_department,
    start_my_stage,
)
from almdina_erp.almdina_erp.services.shop_floor_dxf_service import (
    approve_production_dxf,
    mark_dxf_exported,
    recalculate_drawing_plan,
    upload_production_dxf,
)
from almdina_erp.almdina_erp.services.shop_floor_query_service import (
    get_dispatch_options,
    get_my_archive,
    get_my_inbox,
    get_order_shop_floor_detail,
    get_revert_targets,
)


# Compatibility aliases for older Python callers. They delegate to the new
# Domain or Infrastructure boundaries and intentionally contain no logic here.
PATH_SEQUENCE = PRODUCTION_PATHS
STAGE_ROLE = shop_floor_gateway.STAGE_ROLE_BY_TYPE
STAGE_DEPARTMENT = STAGE_DEPARTMENTS
STAGE_ORDER_STATUS = SHOP_FLOOR_ORDER_STATUSES
DEPARTMENT_STATUS_MAP = DEPARTMENT_STATUS_BY_STAGE_STATUS
CUTTING_LIKE_STAGES = CUTTING_LIKE_STAGE_TYPES
SHOP_FLOOR_ROLES = tuple(STAGE_ROLE.values())
DISPATCH_ROLES = shop_floor_gateway.DISPATCH_ROLES
ADMIN_ROLES = shop_floor_gateway.ADMIN_ROLES

require_any_role = shop_floor_gateway.require_roles
get_users_for_role = shop_floor_gateway.get_users_for_role
_set_order_tracking = shop_floor_gateway.set_order_tracking
_create_stage = shop_floor_gateway.create_stage
_require_stage_assignee_or_admin = shop_floor_gateway.require_stage_assignee_or_admin
_maybe_consume_stock = shop_floor_gateway.maybe_consume_stock
_maybe_register_remnants = shop_floor_gateway.maybe_register_remnants
_required_piece_qty = shop_floor_gateway.required_piece_qty
_log_event = shop_floor_gateway.log_event


def _path_sequence(path: str) -> tuple[str, ...]:
    return production_path_sequence(path)


def _next_stage_type(path: str, current_stage_type: str) -> str | None:
    return next_stage_type(path, current_stage_type)


def _sequence_for_stage(path: str, stage_type: str) -> int:
    return stage_sequence(path, stage_type)


def _resolve_revert_stage_type(value: str | None) -> str:
    return resolve_shop_floor_stage_type(value)


__all__ = [
    "approve_production_dxf",
    "assert_order_ready_for_dispatch",
    "dispatch_order",
    "get_dispatch_options",
    "get_handoff_workers",
    "get_my_archive",
    "get_my_inbox",
    "get_order_shop_floor_detail",
    "get_revert_targets",
    "handoff_to_next",
    "mark_delivered",
    "mark_dxf_exported",
    "recalculate_drawing_plan",
    "return_order_to_draft",
    "revert_department",
    "start_my_stage",
    "sync_order_status",
    "upload_production_dxf",
]
