"""Backward-compatible facade for focused shop-floor Frappe adapters.

New infrastructure code must depend on the focused modules directly. This module
keeps historical imports working while owning no database or business logic.
Legacy role-based action gates are retained only as fail-closed symbols so an
old import cannot silently bypass the configurable capability policy.
"""

from __future__ import annotations

from typing import Any, NoReturn

from almdina_erp.almdina_erp.infrastructure.frappe import (
    order_tracking_repository,
    production_event_repository,
    production_stage_repository,
    shop_floor_authorization,
)


STAGE_ROLE_BY_TYPE = shop_floor_authorization.STAGE_ROLE_BY_TYPE

# Compatibility symbols only. Production authorization no longer consumes role
# tuples; every business action is resolved through document capabilities.
DISPATCH_ROLES: tuple[str, ...] = ()
ADMIN_ROLES: tuple[str, ...] = ()
STAGE_ADMIN_ROLES: tuple[str, ...] = ()

current_user = shop_floor_authorization.current_user
assert_enabled_user_has_stage_role = (
    shop_floor_authorization.assert_enabled_user_has_stage_role
)
get_users_for_stage = shop_floor_authorization.get_users_for_stage
get_users_for_role = shop_floor_authorization.get_users_for_role

get_order = order_tracking_repository.get_order
get_order_path = order_tracking_repository.get_order_path
get_order_status = order_tracking_repository.get_order_status
set_order_tracking = order_tracking_repository.set_order_tracking
required_piece_qty = order_tracking_repository.required_piece_qty

get_stage = production_stage_repository.get_stage
stage_exists = production_stage_repository.stage_exists
cancel_active_order_stages = production_stage_repository.cancel_active_order_stages
cancel_non_shop_floor_active_stages = cancel_active_order_stages
get_revert_stage_candidates = (
    production_stage_repository.list_revert_stage_candidates
)
get_later_stages = production_stage_repository.list_later_stages

log_event = production_event_repository.log_event


def _legacy_role_gate_removed() -> NoReturn:
    raise PermissionError(
        "Legacy role-based shop-floor authorization was removed. "
        "Use the configurable production capability policy."
    )


def require_roles(*roles: str) -> NoReturn:
    """Fail closed for historical imports of the removed role gate."""

    del roles
    _legacy_role_gate_removed()


def require_stage_assignee_or_admin(stage: Any) -> NoReturn:
    """Fail closed for the removed assignment/admin override helper."""

    del stage
    _legacy_role_gate_removed()


def create_stage(
    order_name: str,
    stage_type: str,
    assignee: str,
    sequence: int,
) -> Any:
    """Preserve the historical implicit Created event for legacy callers."""

    stage = production_stage_repository.create_stage(
        order_name,
        stage_type,
        assignee,
        sequence,
    )
    production_event_repository.log_event(
        stage,
        "Created",
        {"sequence": sequence, "assigned_to": assignee, "shop_floor": True},
    )
    return stage


def close_open_pause(stage: Any, resumed_by: str) -> None:
    """Preserve the historical document-based pause helper signature."""

    production_stage_repository.close_open_pause(stage, resumed_by, save=False)


__all__ = [
    "ADMIN_ROLES",
    "DISPATCH_ROLES",
    "STAGE_ADMIN_ROLES",
    "STAGE_ROLE_BY_TYPE",
    "assert_enabled_user_has_stage_role",
    "cancel_active_order_stages",
    "cancel_non_shop_floor_active_stages",
    "close_open_pause",
    "create_stage",
    "current_user",
    "get_later_stages",
    "get_order",
    "get_order_path",
    "get_order_status",
    "get_revert_stage_candidates",
    "get_stage",
    "get_users_for_role",
    "get_users_for_stage",
    "log_event",
    "require_roles",
    "require_stage_assignee_or_admin",
    "required_piece_qty",
    "set_order_tracking",
    "stage_exists",
]
