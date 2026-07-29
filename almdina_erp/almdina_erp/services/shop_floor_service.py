"""Backward-compatible shop-floor API facade.

New code must use the focused command, query, DXF, or infrastructure modules.
This facade keeps historical Python/API paths valid without eagerly importing
those modules or owning business logic.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any, Callable

import frappe

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


_COMMANDS = "almdina_erp.almdina_erp.services.shop_floor_commands"
_QUERIES = "almdina_erp.almdina_erp.services.shop_floor_query_service"
_DXF = "almdina_erp.almdina_erp.services.shop_floor_dxf_service"
_DISPATCH = "almdina_erp.almdina_erp.services.order_dispatch_service"
_PRODUCTION = "almdina_erp.almdina_erp.services.production_service"


def _delegate(module_path: str, function_name: str, *args: Any, **kwargs: Any) -> Any:
    function = getattr(import_module(module_path), function_name)
    return function(*args, **kwargs)


def _public_delegate(module_path: str, function_name: str) -> Callable[..., Any]:
    def delegated(*args: Any, **kwargs: Any) -> Any:
        return _delegate(module_path, function_name, *args, **kwargs)

    delegated.__name__ = function_name
    delegated.__qualname__ = function_name
    delegated.__doc__ = f"Compatibility delegate to {module_path}.{function_name}."
    return frappe.whitelist()(delegated)


# Public compatibility endpoints. Imports occur only when an endpoint is called,
# preventing legacy imports from coupling test discovery and application startup.
get_dispatch_options = _public_delegate(_QUERIES, "get_dispatch_options")
get_revert_targets = _public_delegate(_QUERIES, "get_revert_targets")
get_my_inbox = _public_delegate(_QUERIES, "get_my_inbox")
get_my_archive = _public_delegate(_QUERIES, "get_my_archive")
get_order_shop_floor_detail = _public_delegate(_QUERIES, "get_order_shop_floor_detail")

mark_dxf_exported = _public_delegate(_DXF, "mark_dxf_exported")
upload_production_dxf = _public_delegate(_DXF, "upload_production_dxf")
recalculate_drawing_plan = _public_delegate(_DXF, "recalculate_drawing_plan")
approve_production_dxf = _public_delegate(_DXF, "approve_production_dxf")

get_handoff_workers = _public_delegate(_COMMANDS, "get_handoff_workers")
start_my_stage = _public_delegate(_COMMANDS, "start_my_stage")
handoff_to_next = _public_delegate(_COMMANDS, "handoff_to_next")
mark_delivered = _public_delegate(_COMMANDS, "mark_delivered")
revert_department = _public_delegate(_COMMANDS, "revert_department")
return_order_to_draft = _public_delegate(_COMMANDS, "return_order_to_draft")
dispatch_order = _public_delegate(_DISPATCH, "dispatch_order")


def assert_order_ready_for_dispatch(order: Any) -> None:
    _delegate(_COMMANDS, "assert_order_ready_for_dispatch", order)


def sync_order_status(order_name: str) -> str:
    return _delegate(_PRODUCTION, "sync_order_status", order_name)


# Compatibility aliases for older Python callers. They delegate to Domain or
# Infrastructure boundaries and intentionally contain no business logic here.
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
    "approve_production_dxf", "assert_order_ready_for_dispatch", "dispatch_order",
    "get_dispatch_options", "get_handoff_workers", "get_my_archive", "get_my_inbox",
    "get_order_shop_floor_detail", "get_revert_targets", "handoff_to_next",
    "mark_delivered", "mark_dxf_exported", "recalculate_drawing_plan",
    "return_order_to_draft", "revert_department", "start_my_stage",
    "sync_order_status", "upload_production_dxf",
]
