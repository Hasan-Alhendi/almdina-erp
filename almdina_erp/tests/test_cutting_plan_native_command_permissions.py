from __future__ import annotations

from pathlib import Path

from almdina_erp.almdina_erp.application.security.supporting_doctype_permissions import (
    supporting_standard_permission_projection,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


ROOT = Path(__file__).resolve().parents[1]


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_optimizer_edit_projects_minimum_native_create_and_write_rights() -> None:
    rights = supporting_standard_permission_projection(
        "Cutting Plan",
        {Capability.EDIT_OPTIMIZER_SETTINGS: True},
    )
    assert rights == {
        "read": True,
        "select": True,
        "create": True,
        "write": True,
        "delete": False,
    }


def test_cost_and_dxf_draft_commands_receive_native_persistence_bridge() -> None:
    for capability in (
        Capability.EDIT_COST_SETTINGS,
        Capability.RECALCULATE_PLAN,
        Capability.UPLOAD_DXF,
        Capability.REPLACE_DXF,
    ):
        rights = supporting_standard_permission_projection(
            "Cutting Plan",
            {capability: True},
        )
        assert rights["create"] is True
        assert rights["write"] is True
        assert rights["delete"] is False


def test_approval_needs_write_but_does_not_gain_create_or_delete() -> None:
    rights = supporting_standard_permission_projection(
        "Cutting Plan",
        {Capability.APPROVE_DXF: True},
    )
    assert rights["read"] is True
    assert rights["create"] is False
    assert rights["write"] is True
    assert rights["delete"] is False


def test_view_only_plan_permission_stays_native_read_only() -> None:
    rights = supporting_standard_permission_projection(
        "Cutting Plan",
        {Capability.VIEW_CUTTING_PLAN: True},
    )
    assert rights == {
        "read": True,
        "select": True,
        "create": False,
        "write": False,
        "delete": False,
    }


def test_native_grant_does_not_bypass_cutting_plan_command_guard() -> None:
    permissions = source("almdina_erp/infrastructure/frappe/native_document_permissions.py")
    command_context = source(
        "almdina_erp/infrastructure/frappe/cutting_plan_command_context.py"
    )
    repository = source(
        "almdina_erp/infrastructure/frappe/cutting_plan_command_repository.py"
    )

    assert "is_authorized_plan_command(doc)" in permissions
    assert "if action in {\"create\", \"write\", \"cancel\", \"delete\", \"amend\"}" in permissions
    assert "return False" in permissions
    assert "PLAN_COMMAND_FLAG" in command_context
    assert "cutting_plan_capability_allowed" in command_context
    assert "plan.flags[PLAN_COMMAND_FLAG] = self.capability" in repository
    assert "ignore_permissions" not in repository


def test_migrate_reconciles_existing_canonical_roles_without_role_names() -> None:
    lifecycle = source("lifecycle.py")
    reconciliation = source(
        "almdina_erp/infrastructure/frappe/supporting_permission_reconciliation.py"
    )

    assert "reconcile_supporting_permission_projections()" in lifecycle
    assert "STATE_DOCTYPE" in reconciliation
    assert "CanonicalPermissionStateRepository" in reconciliation
    assert "SupportingDoctypePermissionRepository" in reconciliation
    assert "PROTECTED_SYSTEM_ROLES" in reconciliation
    assert 'frappe.db.exists("Role", role)' in reconciliation
    assert "order-entry" not in reconciliation
    assert "ignore_permissions" not in reconciliation
