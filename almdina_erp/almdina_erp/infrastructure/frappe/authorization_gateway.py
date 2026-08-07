from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.domain.security.authorization import (
    ALL_CAPABILITIES,
    CAPABILITY_CATALOG,
    Capability,
    capability_definition,
)


def _registered_permission_types() -> dict[str, frozenset[str]]:
    from frappe.core.doctype.permission_type.permission_type import get_doctype_ptype_map

    return {
        doctype: frozenset(permission_types)
        for doctype, permission_types in get_doctype_ptype_map().items()
    }


def _matrix_repository() -> tuple[Any, frozenset[str]]:
    from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
        FrappePermissionMatrixRepository,
        PROTECTED_ROLES,
    )

    return FrappePermissionMatrixRepository(), PROTECTED_ROLES


def _permission_type_is_available(capability: str) -> bool:
    definition = capability_definition(capability)
    if not definition.custom:
        return True
    return definition.permission_type in _registered_permission_types().get(
        definition.applies_to,
        frozenset(),
    )


def _raw_doctype_capability(capability: str, user: str) -> bool:
    definition = capability_definition(capability)
    if not _permission_type_is_available(capability):
        return False
    return bool(
        frappe.has_permission(
            definition.applies_to,
            definition.permission_type,
            user=user,
        )
    )


def _matrix_granted_capabilities(user: str) -> frozenset[str]:
    cache = getattr(frappe.local, "almdina_matrix_capabilities", None)
    if cache is None:
        cache = {}
        frappe.local.almdina_matrix_capabilities = cache
    if user in cache:
        return cache[user]

    repository, protected_roles = _matrix_repository()
    granted: set[str] = set()
    for role in repository.user_roles(user):
        if role in protected_roles:
            continue
        try:
            state = repository.role_state(role)["capabilities"]
        except ValueError:
            continue
        granted.update(
            capability
            for capability, enabled in state.items()
            if enabled is True
        )
    resolved = frozenset(granted)
    cache[user] = resolved
    return resolved


def granted_capabilities(user: str | None = None) -> frozenset[str]:
    """Resolve the exact union of explicit grants from all user roles."""

    resolved_user = user or frappe.session.user
    if resolved_user == "Administrator":
        return ALL_CAPABILITIES

    registered = _registered_permission_types()
    granted: set[str] = set(_matrix_granted_capabilities(resolved_user))
    for capability, definition in CAPABILITY_CATALOG.items():
        if definition.custom and definition.permission_type not in registered.get(
            definition.applies_to,
            frozenset(),
        ):
            continue
        if frappe.has_permission(
            definition.applies_to,
            definition.permission_type,
            user=resolved_user,
        ):
            granted.add(capability)
    return frozenset(granted)


def doctype_has_capability(
    capability: str,
    *,
    user: str | None = None,
) -> bool:
    resolved_user = user or frappe.session.user
    if resolved_user == "Administrator":
        return True
    if _raw_doctype_capability(capability, resolved_user):
        return True
    return capability in _matrix_granted_capabilities(resolved_user)


def doctype_has_any_capability(
    capabilities: Iterable[str],
    *,
    user: str | None = None,
) -> bool:
    return any(
        doctype_has_capability(capability, user=user)
        for capability in tuple(capabilities)
    )


def require_doctype_capability(
    capability: str,
    *,
    user: str | None = None,
    message: str | None = None,
) -> None:
    if doctype_has_capability(capability, user=user):
        return
    frappe.throw(
        message or _("You do not have permission for this operation."),
        frappe.PermissionError,
    )


def require_any_doctype_capability(
    capabilities: Iterable[str],
    *,
    user: str | None = None,
    message: str | None = None,
) -> None:
    requested = tuple(capabilities)
    if requested and doctype_has_any_capability(requested, user=user):
        return
    frappe.throw(
        message or _("You do not have permission for this operation."),
        frappe.PermissionError,
    )


def document_has_capability(
    document: Any,
    capability: str,
    *,
    user: str | None = None,
) -> bool:
    definition = capability_definition(capability)
    if getattr(document, "doctype", None) != definition.applies_to:
        return False
    resolved_user = user or frappe.session.user
    if resolved_user == "Administrator":
        return True
    if _permission_type_is_available(capability) and frappe.has_permission(
        document,
        definition.permission_type,
        user=resolved_user,
    ):
        return True
    return bool(
        definition.custom
        and definition.applies_to in {"Door Cutting Order", "Replacement Piece"}
        and capability in _matrix_granted_capabilities(resolved_user)
        and frappe.has_permission(document, "read", user=resolved_user)
    )


def document_has_any_capability(
    document: Any,
    capabilities: Iterable[str],
    *,
    user: str | None = None,
) -> bool:
    return any(
        document_has_capability(document, capability, user=user)
        for capability in tuple(capabilities)
    )


def require_document_capability(
    document: Any,
    capability: str,
    *,
    user: str | None = None,
    message: str | None = None,
) -> None:
    if document_has_capability(document, capability, user=user):
        return
    frappe.throw(
        message or _("You do not have permission for this operation."),
        frappe.PermissionError,
    )


def require_any_document_capability(
    document: Any,
    capabilities: Iterable[str],
    *,
    user: str | None = None,
    message: str | None = None,
) -> None:
    requested = tuple(capabilities)
    if requested and document_has_any_capability(document, requested, user=user):
        return
    frappe.throw(
        message or _("You do not have permission for this operation."),
        frappe.PermissionError,
    )


__all__ = [
    "doctype_has_any_capability",
    "doctype_has_capability",
    "document_has_any_capability",
    "document_has_capability",
    "granted_capabilities",
    "require_any_doctype_capability",
    "require_any_document_capability",
    "require_doctype_capability",
    "require_document_capability",
]
