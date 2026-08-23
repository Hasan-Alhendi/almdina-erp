from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.domain.security.authorization import (
    ALL_CAPABILITIES,
    CUTTING_PLAN_DOCTYPE,
    capability_definition,
)
from almdina_erp.almdina_erp.infrastructure.frappe.system_role_policy import (
    PROTECTED_SYSTEM_ROLES,
)


_TRANSACTIONAL_SCOPE_DOCTYPES = frozenset(
    {"Door Cutting Order", CUTTING_PLAN_DOCTYPE, "Replacement Piece"}
)
_DEFAULT_PERMISSION_MESSAGE = "لا تملك الصلاحية المطلوبة لتنفيذ هذا الإجراء."


def _matrix_repository() -> tuple[Any, frozenset[str]]:
    """Load persistence lazily so adapters import without Frappe DB setup."""

    from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
        FrappePermissionMatrixRepository,
    )

    return FrappePermissionMatrixRepository(), PROTECTED_SYSTEM_ROLES


def _matrix_granted_capabilities(user: str) -> frozenset[str]:
    """Resolve capabilities only from editable roles in the factory matrix."""

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
    """Resolve the union of explicit factory-role capabilities for one user."""

    resolved_user = user or frappe.session.user
    if resolved_user == "Administrator":
        return ALL_CAPABILITIES
    return _matrix_granted_capabilities(resolved_user)


def doctype_has_capability(
    capability: str,
    *,
    user: str | None = None,
) -> bool:
    """Check an Almdina capability without accepting unrelated native grants."""

    capability_definition(capability)
    resolved_user = user or frappe.session.user
    if resolved_user == "Administrator":
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
    """Require one configurable capability without leaking role policy."""

    if doctype_has_capability(capability, user=user):
        return
    frappe.throw(
        message or _(_DEFAULT_PERMISSION_MESSAGE),
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
        message or _(_DEFAULT_PERMISSION_MESSAGE),
        frappe.PermissionError,
    )


def document_has_capability(
    document: Any,
    capability: str,
    *,
    user: str | None = None,
) -> bool:
    """Require explicit capability first, then preserve native document scope.

    The matrix is the authority. Native Frappe permissions are used only as a
    second, narrowing check for concrete transactional documents. Cutting Plan is
    intentionally included: its native read hook narrows access through the
    related Door Cutting Order scope before a plan document can authorize action.
    """

    definition = capability_definition(capability)
    if getattr(document, "doctype", None) != definition.applies_to:
        return False

    resolved_user = user or frappe.session.user
    if resolved_user == "Administrator":
        return True
    if capability not in _matrix_granted_capabilities(resolved_user):
        return False

    if definition.applies_to in _TRANSACTIONAL_SCOPE_DOCTYPES:
        native_permission = "read" if definition.custom else definition.permission_type
        return bool(
            frappe.has_permission(
                document,
                native_permission,
                user=resolved_user,
            )
        )

    return True


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
        message or _(_DEFAULT_PERMISSION_MESSAGE),
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
        message or _(_DEFAULT_PERMISSION_MESSAGE),
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
