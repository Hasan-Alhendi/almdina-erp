from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from almdina_erp.almdina_erp.domain.security.role_management import (
    PROTECTED_ROLE_NAMES,
    RoleAction,
    RoleDefinition,
    RoleFacts,
    action_context,
    decide_role_action,
    new_role_definition,
    normalize_role_description,
    normalize_role_name,
)


class RoleAdministrationRepository(Protocol):
    """Persistence port used by the framework-independent role use cases."""

    def role_exists(self, role: str) -> bool: ...

    def lock_role(self, role: str) -> None: ...

    def list_roles(
        self,
        *,
        search: str = "",
        enabled: bool | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]: ...

    def get_role(self, role: str) -> dict[str, Any]: ...

    def create_role(self, definition: RoleDefinition) -> dict[str, Any]: ...

    def update_role(
        self,
        role: str,
        *,
        name: str,
        description: str,
    ) -> dict[str, Any]: ...

    def set_role_enabled(self, role: str, enabled: bool) -> dict[str, Any]: ...

    def delete_role(self, role: str) -> None: ...

    def record_audit(
        self,
        *,
        role_name: str,
        action: str,
        before: Mapping[str, Any] | None,
        after: Mapping[str, Any] | None,
        summary: str,
        changed_by: str,
    ) -> str: ...

    def list_audit(
        self,
        *,
        role_name: str,
        role_uid: str = "",
        limit: int = 30,
    ) -> list[dict[str, Any]]: ...


class RoleAdministrationError(ValueError):
    """Expected role-management validation failure."""

    def __init__(self, message: str, *, code: str = "validation_error"):
        super().__init__(message)
        self.code = code


def _facts(snapshot: Mapping[str, Any], *, actor: str = "") -> RoleFacts:
    return RoleFacts(
        actor=str(actor or ""),
        role_name=str(snapshot.get("name") or ""),
        role_exists=bool(snapshot.get("role_exists", True)),
        role_enabled=bool(snapshot.get("enabled", True)),
        assigned_users=int(snapshot.get("assigned_users") or 0),
        production_routing_references=int(
            snapshot.get("production_routing_references") or 0
        ),
        workflow_references=int(snapshot.get("workflow_references") or 0),
        production_stage_references=int(
            snapshot.get("production_stage_references") or 0
        ),
        active_stage_references=int(
            snapshot.get("active_stage_references") or 0
        ),
        permission_count=int(snapshot.get("permission_count") or 0),
    )


def _require(action: RoleAction, facts: RoleFacts) -> None:
    decision = decide_role_action(action=action, facts=facts)
    if decision.allowed:
        return
    raise RoleAdministrationError(decision.reason, code=decision.code)


def _present(snapshot: Mapping[str, Any], *, actor: str) -> dict[str, Any]:
    row = dict(snapshot)
    row["actions"] = action_context(_facts(row, actor=actor))
    return row


class RoleAdministration:
    """Use cases for roles created and maintained by factory administrators."""

    def __init__(self, repository: RoleAdministrationRepository):
        self.repository = repository

    def console(
        self,
        *,
        actor: str,
        search: str = "",
        enabled: bool | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        rows = self.repository.list_roles(
            search=str(search or "").strip(),
            enabled=enabled,
            limit=limit,
        )
        roles = [_present(row, actor=actor) for row in rows]
        return {
            "roles": roles,
            "summary": {
                "total": len(roles),
                "enabled": sum(1 for role in roles if role["enabled"]),
                "disabled": sum(1 for role in roles if not role["enabled"]),
                "assigned_users": sum(
                    int(role.get("assigned_users") or 0) for role in roles
                ),
                "permission_rows": sum(
                    int(role.get("permission_count") or 0) for role in roles
                ),
                "production_references": sum(
                    int(role.get("production_routing_references") or 0)
                    + int(role.get("production_stage_references") or 0)
                    for role in roles
                ),
            },
        }

    def get(self, *, actor: str, role: str) -> dict[str, Any]:
        snapshot = self.repository.get_role(normalize_role_name(role))
        return _present(snapshot, actor=actor)

    def create(
        self,
        *,
        actor: str,
        name: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        definition = new_role_definition(
            name=name,
            description=description,
            enabled=True,
        )
        _require(
            RoleAction.CREATE,
            RoleFacts(
                actor=actor,
                role_name=definition.name,
                role_exists=self.repository.role_exists(definition.name),
                role_enabled=True,
            ),
        )
        created = self.repository.create_role(definition)
        audit = self.repository.record_audit(
            role_name=created["name"],
            action="Created",
            before=None,
            after=created,
            summary="Created an empty role with no implicit permissions.",
            changed_by=actor,
        )
        return {
            "role": _present(created, actor=actor),
            "audit": audit,
        }

    def update(
        self,
        *,
        actor: str,
        role: str,
        name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        current_name = normalize_role_name(role)
        self.repository.lock_role(current_name)
        before = self.repository.get_role(current_name)
        _require(RoleAction.EDIT, _facts(before, actor=actor))

        target_name = (
            normalize_role_name(name)
            if name is not None
            else str(before["name"])
        )
        target_description = (
            normalize_role_description(description)
            if description is not None
            else str(before.get("description") or "")
        )
        if target_name in PROTECTED_ROLE_NAMES:
            raise RoleAdministrationError(
                "This framework role name is protected.",
                code="protected_role",
            )
        if (
            target_name != before["name"]
            and self.repository.role_exists(target_name)
        ):
            raise RoleAdministrationError(
                "Role already exists.",
                code="already_exists",
            )
        if (
            target_name == before["name"]
            and target_description == before.get("description", "")
        ):
            return {
                "role": _present(before, actor=actor),
                "changed": False,
                "audit": None,
            }

        after = self.repository.update_role(
            current_name,
            name=target_name,
            description=target_description,
        )
        changes: list[str] = []
        if before["name"] != after["name"]:
            changes.append("name")
        if before.get("description", "") != after.get("description", ""):
            changes.append("description")
        audit = self.repository.record_audit(
            role_name=after["name"],
            action="Updated",
            before=before,
            after=after,
            summary="Updated role " + " and ".join(changes) + ".",
            changed_by=actor,
        )
        return {
            "role": _present(after, actor=actor),
            "changed": True,
            "audit": audit,
        }

    def set_enabled(
        self,
        *,
        actor: str,
        role: str,
        enabled: bool,
    ) -> dict[str, Any]:
        role_name = normalize_role_name(role)
        self.repository.lock_role(role_name)
        before = self.repository.get_role(role_name)
        action = RoleAction.ENABLE if enabled else RoleAction.DISABLE
        _require(action, _facts(before, actor=actor))
        after = self.repository.set_role_enabled(role_name, bool(enabled))
        audit_action = "Enabled" if enabled else "Disabled"
        audit = self.repository.record_audit(
            role_name=after["name"],
            action=audit_action,
            before=before,
            after=after,
            summary=f"{audit_action} role.",
            changed_by=actor,
        )
        return {
            "role": _present(after, actor=actor),
            "audit": audit,
        }

    def delete(self, *, actor: str, role: str) -> dict[str, Any]:
        role_name = normalize_role_name(role)
        self.repository.lock_role(role_name)
        before = self.repository.get_role(role_name)
        _require(RoleAction.DELETE, _facts(before, actor=actor))
        self.repository.delete_role(role_name)
        audit = self.repository.record_audit(
            role_name=role_name,
            action="Deleted",
            before=before,
            after=None,
            summary="Deleted an unused role after validating all references.",
            changed_by=actor,
        )
        return {
            "deleted": True,
            "role": role_name,
            "audit": audit,
        }

    def audit(
        self,
        *,
        actor: str,
        role: str,
        limit: int = 30,
    ) -> dict[str, Any]:
        snapshot = self.repository.get_role(normalize_role_name(role))
        return {
            "role": _present(snapshot, actor=actor),
            "events": self.repository.list_audit(
                role_name=snapshot["name"],
                role_uid=str(snapshot.get("role_uid") or ""),
                limit=limit,
            ),
        }


__all__ = [
    "RoleAdministration",
    "RoleAdministrationError",
    "RoleAdministrationRepository",
]
