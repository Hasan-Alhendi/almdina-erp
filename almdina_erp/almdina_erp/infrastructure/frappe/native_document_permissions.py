from __future__ import annotations

from typing import Any, Callable

import frappe

from almdina_erp import permissions as base_permissions
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_command_context import (
    is_authorized_plan_command,
)


_NATIVE_MUTATING_PERMISSION_TYPES = (
    "create",
    "write",
    "delete",
    "submit",
    "cancel",
    "amend",
)
_NATIVE_COMMAND_ONLY_PERMISSION_TYPES = (
    "delete",
    "submit",
    "cancel",
    "amend",
)


def _permission_type(
    ptype: str | None,
    permission_type: str | None,
) -> str | None:
    return ptype if ptype is not None else permission_type


def _user(user: str | None) -> str:
    return str(user or frappe.session.user)


def door_cutting_order_has_permission(
    doc: Any,
    user: str | None = None,
    ptype: str | None = None,
    permission_type: str | None = None,
) -> bool:
    """Protect native DCO access without replacing the capability model.

    Canonical workflow commands own submit/cancel/revision-like mutations. Native
    create/write remain available only where the business capability permits it,
    and floor workers may write only an order that is inside their assigned scope.
    """

    resolved_type = _permission_type(ptype, permission_type)
    resolved_user = _user(user)

    if resolved_user == "Administrator":
        return True
    if resolved_type in _NATIVE_COMMAND_ONLY_PERMISSION_TYPES:
        return False
    if not base_permissions.door_cutting_order_has_permission(
        doc,
        user=resolved_user,
        ptype=resolved_type,
    ):
        return False
    if resolved_type == "write" and base_permissions._requires_assigned_scope(
        resolved_user
    ):
        return base_permissions.worker_can_view_order(
            resolved_user,
            getattr(doc, "name", None),
        )
    return True


def _command_owned_document_permission(
    delegate: Callable[..., bool],
    doc: Any,
    *,
    user: str | None,
    ptype: str | None,
    permission_type: str | None,
) -> bool:
    resolved_type = _permission_type(ptype, permission_type)
    resolved_user = _user(user)
    if resolved_user == "Administrator":
        return True
    if resolved_type in _NATIVE_MUTATING_PERMISSION_TYPES:
        return False
    return delegate(doc, user=resolved_user, ptype=resolved_type)


def production_stage_has_permission(
    doc: Any,
    user: str | None = None,
    ptype: str | None = None,
    permission_type: str | None = None,
) -> bool:
    return _command_owned_document_permission(
        base_permissions.production_stage_has_permission,
        doc,
        user=user,
        ptype=ptype,
        permission_type=permission_type,
    )


def production_incident_has_permission(
    doc: Any,
    user: str | None = None,
    ptype: str | None = None,
    permission_type: str | None = None,
) -> bool:
    return _command_owned_document_permission(
        base_permissions.production_incident_has_permission,
        doc,
        user=user,
        ptype=ptype,
        permission_type=permission_type,
    )


def cutting_plan_has_permission(
    doc: Any,
    user: str | None = None,
    ptype: str | None = None,
    permission_type: str | None = None,
) -> bool:
    """Keep Cutting Plan CRUD closed except inside authorized command services.

    A command service must first authorize the related Door Cutting Order, then
    set the ephemeral command flag on the in-memory Cutting Plan document. This
    allows normal ``insert``/``save`` permission enforcement without granting
    unrestricted Desk write access and without using ``ignore_permissions``.
    """

    resolved_type = _permission_type(ptype, permission_type)
    resolved_user = _user(user)
    if resolved_user == "Administrator":
        return True
    if resolved_type in {"create", "write"} and is_authorized_plan_command(doc):
        return True
    return _command_owned_document_permission(
        base_permissions.cutting_plan_has_permission,
        doc,
        user=resolved_user,
        ptype=resolved_type,
        permission_type=resolved_type,
    )


def replacement_piece_has_permission(
    doc: Any,
    user: str | None = None,
    ptype: str | None = None,
    permission_type: str | None = None,
) -> bool:
    return _command_owned_document_permission(
        base_permissions.replacement_piece_has_permission,
        doc,
        user=user,
        ptype=ptype,
        permission_type=permission_type,
    )


__all__ = [
    "cutting_plan_has_permission",
    "door_cutting_order_has_permission",
    "production_incident_has_permission",
    "production_stage_has_permission",
    "replacement_piece_has_permission",
]
