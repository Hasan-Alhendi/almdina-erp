from __future__ import annotations

import runpy
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
AUTHORIZATION_PATH = REPOSITORY_ROOT / "almdina_erp/almdina_erp/domain/security/authorization.py"
SYNC_PATH = REPOSITORY_ROOT / "almdina_erp/almdina_erp/infrastructure/frappe/permission_type_sync.py"
GATEWAY_PATH = REPOSITORY_ROOT / "almdina_erp/almdina_erp/infrastructure/frappe/authorization_gateway.py"
DXF_SERVICE_PATH = REPOSITORY_ROOT / "almdina_erp/almdina_erp/services/shop_floor_dxf_service.py"
APPROVAL_SERVICE_PATH = REPOSITORY_ROOT / "almdina_erp/almdina_erp/services/drawing_approval_service.py"
SHOP_FLOOR_UI_PATH = REPOSITORY_ROOT / "almdina_erp/public/js/shop_floor_order_ux.js"
DRAWING_UI_PATH = REPOSITORY_ROOT / "almdina_erp/public/js/door_cutting_order_drawing_plan_ux.js"
APPROVAL_UI_PATH = REPOSITORY_ROOT / "almdina_erp/public/js/door_cutting_order_drawing_approval_ux.js"
HOOKS_PATH = REPOSITORY_ROOT / "almdina_erp/hooks.py"


def test_role_assignments_are_not_hardcoded_in_domain_or_sync() -> None:
    authorization = AUTHORIZATION_PATH.read_text(encoding="utf-8")
    sync = SYNC_PATH.read_text(encoding="utf-8")
    assert "ROLE_CAPABILITIES" not in authorization
    assert "Custom DocPerm" not in sync
    assert "role" not in sync.lower()


def test_frappe_gateway_is_the_only_role_permission_adapter() -> None:
    source = GATEWAY_PATH.read_text(encoding="utf-8")
    assert "frappe.has_permission" in source
    assert "get_doctype_ptype_map" in source
    assert "ROLE_CAPABILITIES" not in source


def test_dxf_file_changes_keep_assignment_while_plan_actions_are_role_managed() -> None:
    dxf_source = DXF_SERVICE_PATH.read_text(encoding="utf-8")
    approval_source = APPROVAL_SERVICE_PATH.read_text(encoding="utf-8")

    assert "require_document_capability" in dxf_source
    assert "require_stage_operational_access" in dxf_source
    assert "require_stage_role=True" in dxf_source
    assert "DXF_ROLES" not in dxf_source
    assert "require_roles" not in dxf_source
    assert "Capability.EXPORT_DXF" in dxf_source

    assert "Capability.APPROVE_DXF" in approval_source
    assert "require_document_capability" in approval_source
    assert "require_stage_operational_access" in approval_source
    assert "validate_drawing_approval" not in approval_source
    assert "current_assignee" not in approval_source
    assert "require_any_role" not in approval_source


def test_drawing_presenters_use_capabilities_not_role_names() -> None:
    combined = (
        SHOP_FLOOR_UI_PATH.read_text(encoding="utf-8")
        + DRAWING_UI_PATH.read_text(encoding="utf-8")
        + APPROVAL_UI_PATH.read_text(encoding="utf-8")
    )
    assert "frappe.user_roles" not in combined
    assert "has_role" not in combined
    assert "hasRole" not in combined
    assert "AlmdinaPermissions" in combined
    assert 'can(frm, "approve_dxf")' in combined or 'canApprove(frm)' in combined
    assert 'can("recalculate_plan", frm)' in combined
    assert "current_assignee === frappe.session.user" in combined

    approval_ui = APPROVAL_UI_PATH.read_text(encoding="utf-8")
    assert "current_assignee" not in approval_ui
    assert "تم اعتماد خطة لهذا الطلب سابقًا" in approval_ui


def test_legacy_plan_lock_endpoint_is_redirected_to_role_managed_approval() -> None:
    hooks = runpy.run_path(str(HOOKS_PATH))
    overrides = hooks["override_whitelisted_methods"]
    assert overrides[
        "almdina_erp.almdina_erp.services.cutting_plan_service.lock_cutting_plan"
    ] == "almdina_erp.almdina_erp.services.drawing_approval_service.approve_production_dxf"
