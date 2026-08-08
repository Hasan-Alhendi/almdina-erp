from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.application.security.workforce_management import (
    normalize_identity,
    normalize_role_selection,
    validate_temporary_password,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    WORKFORCE_CAPABILITIES,
    Capability,
)
from almdina_erp.almdina_erp.domain.security.workforce import (
    ACTION_CAPABILITIES,
    WorkforceAction,
    WorkforceFacts,
    action_context,
    decide_workforce_action,
)
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    granted_capabilities,
)
from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
    FrappePermissionMatrixRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.workforce_repository import (
    FrappeWorkforceRepository,
)


_repository = FrappeWorkforceRepository()
_permission_repository = FrappePermissionMatrixRepository()


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = frappe.parse_json(value)
    return dict(value or {})


def _bool_value(value: Any) -> bool:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
        raise ValueError("Invalid boolean value.")
    return bool(value)


def _granted() -> frozenset[str]:
    return granted_capabilities()


def _raise_value_error(error: ValueError) -> None:
    frappe.throw(_(str(error)), frappe.ValidationError)


def _require_any_action_capability(*actions: WorkforceAction) -> None:
    granted = _granted()
    if any(ACTION_CAPABILITIES[action] in granted for action in actions):
        return
    frappe.throw(
        _("You do not have permission for this workforce action."),
        frappe.PermissionError,
    )


def _require_action(
    action: WorkforceAction,
    *,
    facts: WorkforceFacts | None = None,
) -> None:
    decision = decide_workforce_action(
        _granted(),
        action=action,
        facts=facts or WorkforceFacts(actor=str(frappe.session.user)),
    )
    if decision.allowed:
        return
    exception = (
        frappe.PermissionError
        if decision.code == "missing_capability"
        else frappe.ValidationError
    )
    frappe.throw(_(decision.reason), exception)


def _facts(snapshot: dict[str, Any]) -> WorkforceFacts:
    return WorkforceFacts(
        actor=str(frappe.session.user),
        target_user=str(snapshot.get("email") or ""),
        target_enabled=bool(snapshot.get("enabled")),
        target_is_almdina=bool(snapshot.get("is_almdina")),
        active_assignments=int(snapshot.get("active_assignments") or 0),
    )


def _present_user(snapshot: dict[str, Any]) -> dict[str, Any]:
    row = dict(snapshot)
    row["roles"] = list(normalize_role_selection(row.get("roles") or ()))
    row["actions"] = action_context(_granted(), facts=_facts(row))
    row.pop("is_almdina", None)
    return row


def _present_available_user(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Expose only identity/status fields for accounts outside workforce scope."""

    return {
        "email": str(snapshot.get("email") or ""),
        "first_name": str(snapshot.get("first_name") or ""),
        "last_name": str(snapshot.get("last_name") or ""),
        "full_name": str(snapshot.get("full_name") or snapshot.get("email") or ""),
        "enabled": bool(snapshot.get("enabled")),
        "language": str(snapshot.get("language") or "ar"),
        "default_workspace": str(snapshot.get("default_workspace") or ""),
        "default_app": str(snapshot.get("default_app") or ""),
        "last_active": str(snapshot.get("last_active") or ""),
    }


def _validated_roles(values: Any) -> tuple[str, ...]:
    try:
        selected = normalize_role_selection(values)
        return _repository.validate_roles(selected)
    except ValueError as error:
        _raise_value_error(error)
    raise AssertionError("frappe.throw must interrupt execution")


def _guard_privileged_roles(roles: tuple[str, ...]) -> None:
    """Prevent workforce administration from escalating into permission admin."""

    actor = str(frappe.session.user)
    if actor == "Administrator" or Capability.MANAGE_PERMISSIONS in _granted():
        return
    privileged: list[str] = []
    for role in roles:
        try:
            state = _permission_repository.role_state(role)["capabilities"]
        except ValueError:
            continue
        if state.get(Capability.MANAGE_PERMISSIONS) is True:
            privileged.append(role)
    if privileged:
        frappe.throw(
            _(
                "Only a permission administrator can assign roles that manage permissions: {0}"
            ).format(", ".join(sorted(privileged))),
            frappe.PermissionError,
        )


@frappe.whitelist()
def get_workforce_console(
    search: str = "",
    enabled: int | str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    _require_action(WorkforceAction.VIEW)
    try:
        enabled_filter = (
            None if enabled in (None, "", "all") else _bool_value(enabled)
        )
    except ValueError as error:
        _raise_value_error(error)
        raise AssertionError("frappe.throw must interrupt execution")
    users = _repository.list_users(
        search=str(search or ""),
        enabled=enabled_filter,
        limit=limit,
    )
    granted = _granted()
    available_users = (
        _repository.list_available_users(
            search=str(search or ""),
            enabled=enabled_filter,
            limit=limit,
        )
        if Capability.CREATE_USERS in granted
        else []
    )
    return {
        "roles": _repository.list_assignable_roles(),
        "users": [_present_user(user) for user in users],
        "available_users": [
            _present_available_user(user) for user in available_users
        ],
        "permissions": {
            capability: capability in granted
            for capability in sorted(WORKFORCE_CAPABILITIES)
        },
        "summary": {
            "total": len(users),
            "enabled": sum(1 for user in users if user["enabled"]),
            "disabled": sum(1 for user in users if not user["enabled"]),
            "active_assignments": sum(
                int(user.get("active_assignments") or 0) for user in users
            ),
            "available": len(available_users),
        },
    }


@frappe.whitelist()
def create_workforce_user(data: Any) -> dict[str, Any]:
    _require_action(WorkforceAction.CREATE)
    values = _payload(data)
    try:
        identity = normalize_identity(
            email=values.get("email"),
            first_name=values.get("first_name"),
            last_name=values.get("last_name"),
            language=values.get("language") or "ar",
        )
        roles = _validated_roles(values.get("roles") or ())
        password = validate_temporary_password(
            values.get("temporary_password"),
            email=identity.email,
        )
    except ValueError as error:
        _raise_value_error(error)
        raise AssertionError("frappe.throw must interrupt execution")

    if roles:
        _require_action(
            WorkforceAction.ASSIGN_ROLES,
            facts=WorkforceFacts(
                actor=str(frappe.session.user),
                target_user=identity.email,
                target_is_almdina=True,
            ),
        )
        _guard_privileged_roles(roles)

    try:
        created = _repository.create_user(
            identity=identity,
            roles=roles,
            temporary_password=password,
        )
    except ValueError as error:
        _raise_value_error(error)
        raise AssertionError("frappe.throw must interrupt execution")

    audit_name = _repository.record_audit(
        user_name=identity.email,
        action="Created",
        before=None,
        after=created,
        summary=_("Created Almdina workforce account with {0} assigned role(s).").format(
            len(roles)
        ),
        changed_by=str(frappe.session.user),
    )
    return {"user": _present_user(created), "audit": audit_name}


@frappe.whitelist(methods=["POST"])
def adopt_workforce_user(user: str) -> dict[str, Any]:
    """Explicitly add an existing Frappe System User to Almdina workforce."""

    _require_action(WorkforceAction.CREATE)
    user_name = str(user or "").strip().lower()
    if not user_name:
        _raise_value_error(ValueError("User is required."))
        raise AssertionError("frappe.throw must interrupt execution")

    _repository.lock_user(user_name)
    try:
        before = _repository.get_user(user_name, require_almdina=False)
        if before.get("is_almdina"):
            return {"user": _present_user(before), "audit": ""}
        after = _repository.adopt_user(user_name)
    except ValueError as error:
        _raise_value_error(error)
        raise AssertionError("frappe.throw must interrupt execution")

    audit_name = _repository.record_audit(
        user_name=user_name,
        action="Added to Workforce",
        before=before,
        after=after,
        summary=_(
            "Added existing Frappe System User to Almdina workforce without granting a factory role."
        ),
        changed_by=str(frappe.session.user),
    )
    return {"user": _present_user(after), "audit": audit_name}


@frappe.whitelist()
def update_workforce_user(user: str, data: Any) -> dict[str, Any]:
    _require_any_action_capability(
        WorkforceAction.EDIT,
        WorkforceAction.ASSIGN_ROLES,
    )
    user_name = str(user or "").strip().lower()
    values = _payload(data)
    _repository.lock_user(user_name)
    try:
        before = _repository.get_user(user_name)
        identity = normalize_identity(
            email=user_name,
            first_name=values.get("first_name", before["first_name"]),
            last_name=values.get("last_name", before["last_name"]),
            language=values.get("language", before["language"]),
        )
        roles_supplied = "roles" in values and values.get("roles") is not None
        roles = (
            _validated_roles(values.get("roles") or ())
            if roles_supplied
            else tuple(before.get("roles") or ())
        )
    except ValueError as error:
        _raise_value_error(error)
        raise AssertionError("frappe.throw must interrupt execution")

    identity_changed = any(
        (
            identity.first_name != before["first_name"],
            identity.last_name != before["last_name"],
            identity.language != before["language"],
        )
    )
    roles_changed = roles_supplied and tuple(roles) != tuple(before.get("roles") or ())
    facts = _facts(before)
    if identity_changed:
        _require_action(WorkforceAction.EDIT, facts=facts)
    if roles_changed:
        _require_action(WorkforceAction.ASSIGN_ROLES, facts=facts)
        _guard_privileged_roles(roles)
    if not identity_changed and not roles_changed:
        return {"user": _present_user(before), "audits": []}

    current = before
    audits: list[str] = []
    try:
        if identity_changed:
            current = _repository.update_identity(user_name, identity)
            audits.append(
                _repository.record_audit(
                    user_name=user_name,
                    action="Identity Updated",
                    before=before,
                    after=current,
                    summary=_("Updated workforce identity and language."),
                    changed_by=str(frappe.session.user),
                )
            )
        if roles_changed:
            roles_before = current
            current = _repository.assign_roles(user_name, roles)
            audits.append(
                _repository.record_audit(
                    user_name=user_name,
                    action="Roles Changed",
                    before=roles_before,
                    after=current,
                    summary=_("Changed assigned roles to: {0}").format(
                        ", ".join(roles) if roles else _("none")
                    ),
                    changed_by=str(frappe.session.user),
                )
            )
    except ValueError as error:
        _raise_value_error(error)
        raise AssertionError("frappe.throw must interrupt execution")

    return {"user": _present_user(current), "audits": audits}


@frappe.whitelist()
def set_workforce_user_enabled(user: str, enabled: int | bool | str) -> dict[str, Any]:
    user_name = str(user or "").strip().lower()
    try:
        target_enabled = _bool_value(enabled)
    except ValueError as error:
        _raise_value_error(error)
        raise AssertionError("frappe.throw must interrupt execution")

    action = WorkforceAction.ENABLE if target_enabled else WorkforceAction.DISABLE
    _require_any_action_capability(action)
    _repository.lock_user(user_name)
    try:
        before = _repository.get_user(user_name)
    except ValueError as error:
        _raise_value_error(error)
        raise AssertionError("frappe.throw must interrupt execution")

    _require_action(action, facts=_facts(before))
    after = _repository.set_enabled(user_name, target_enabled)
    audit_action = "Enabled" if target_enabled else "Disabled"
    audit_name = _repository.record_audit(
        user_name=user_name,
        action=audit_action,
        before=before,
        after=after,
        summary=_("Workforce account {0}.").format(audit_action.lower()),
        changed_by=str(frappe.session.user),
    )
    return {"user": _present_user(after), "audit": audit_name}


@frappe.whitelist()
def reset_workforce_password(user: str, temporary_password: str) -> dict[str, Any]:
    _require_any_action_capability(WorkforceAction.RESET_PASSWORD)
    user_name = str(user or "").strip().lower()
    _repository.lock_user(user_name)
    try:
        snapshot = _repository.get_user(user_name)
        password = validate_temporary_password(
            temporary_password,
            email=user_name,
        )
    except ValueError as error:
        _raise_value_error(error)
        raise AssertionError("frappe.throw must interrupt execution")

    _require_action(WorkforceAction.RESET_PASSWORD, facts=_facts(snapshot))
    _repository.reset_password(user_name, password)
    audit_name = _repository.record_audit(
        user_name=user_name,
        action="Password Reset",
        before=snapshot,
        after=snapshot,
        summary=_("Assigned a new temporary password. Password value was not logged."),
        changed_by=str(frappe.session.user),
    )
    return {"user": user_name, "audit": audit_name, "password_logged": False}


@frappe.whitelist()
def get_workforce_user_audit(user: str, limit: int = 30) -> dict[str, Any]:
    _require_action(WorkforceAction.VIEW)
    user_name = str(user or "").strip().lower()
    try:
        snapshot = _repository.get_user(user_name)
    except ValueError as error:
        _raise_value_error(error)
        raise AssertionError("frappe.throw must interrupt execution")
    return {
        "user": _present_user(snapshot),
        "events": _repository.list_audit(user_name, limit=limit),
    }


__all__ = [
    "adopt_workforce_user",
    "create_workforce_user",
    "get_workforce_console",
    "get_workforce_user_audit",
    "reset_workforce_password",
    "set_workforce_user_enabled",
    "update_workforce_user",
]
