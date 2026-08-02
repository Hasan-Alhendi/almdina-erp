from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.application.security.workforce_management import (
    normalize_identity,
    profile_catalog_payload,
    validate_profile,
    validate_temporary_password,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    WORKFORCE_CAPABILITIES,
)
from almdina_erp.almdina_erp.domain.security.workforce import (
    PROFILES,
    WorkforceAction,
    WorkforceFacts,
    action_context,
    decide_workforce_action,
    expand_workforce_capabilities,
    profile_for_key,
)
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    granted_capabilities,
)
from almdina_erp.almdina_erp.infrastructure.frappe.workforce_repository import (
    FrappeWorkforceRepository,
)


_repository = FrappeWorkforceRepository()


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
    return expand_workforce_capabilities(granted_capabilities())


def _raise_value_error(error: ValueError) -> None:
    frappe.throw(_(str(error)), frappe.ValidationError)


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
    profile_key = str(row.get("profile") or "")
    profile = PROFILES.get(profile_key)
    if profile:
        row["profile_label"] = profile.label
    elif profile_key == "custom":
        row["profile_label"] = _("ملف مخصص")
    else:
        row["profile_label"] = _("غير محدد")
    row["actions"] = action_context(_granted(), facts=_facts(row))
    row.pop("is_almdina", None)
    return row


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
    return {
        "profiles": profile_catalog_payload(),
        "users": [_present_user(user) for user in users],
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
        profile_key = validate_profile(values.get("profile"))
        password = validate_temporary_password(
            values.get("temporary_password"),
            email=identity.email,
        )
        created = _repository.create_user(
            identity=identity,
            profile=profile_for_key(profile_key),
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
        summary=_("Created Almdina workforce account with operational profile {0}.").format(
            profile_key
        ),
        changed_by=str(frappe.session.user),
    )
    return {"user": _present_user(created), "audit": audit_name}


@frappe.whitelist()
def update_workforce_user(user: str, data: Any) -> dict[str, Any]:
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
        profile_supplied = "profile" in values and values.get("profile") not in (None, "")
        profile_key = (
            validate_profile(values.get("profile"))
            if profile_supplied
            else str(before.get("profile") or "")
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
    profile_changed = profile_supplied and profile_key != before["profile"]
    facts = _facts(before)
    if identity_changed:
        _require_action(WorkforceAction.EDIT, facts=facts)
    if profile_changed:
        _require_action(WorkforceAction.ASSIGN_PROFILE, facts=facts)
    if not identity_changed and not profile_changed:
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
        if profile_changed:
            profile_before = current
            current = _repository.assign_profile(
                user_name,
                profile_for_key(profile_key),
            )
            audits.append(
                _repository.record_audit(
                    user_name=user_name,
                    action="Profile Changed",
                    before=profile_before,
                    after=current,
                    summary=_("Changed operational profile to {0}.").format(
                        profile_key
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
    _repository.lock_user(user_name)
    try:
        before = _repository.get_user(user_name)
    except ValueError as error:
        _raise_value_error(error)
        raise AssertionError("frappe.throw must interrupt execution")

    action = WorkforceAction.ENABLE if target_enabled else WorkforceAction.DISABLE
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
    "create_workforce_user",
    "get_workforce_console",
    "get_workforce_user_audit",
    "reset_workforce_password",
    "set_workforce_user_enabled",
    "update_workforce_user",
]
