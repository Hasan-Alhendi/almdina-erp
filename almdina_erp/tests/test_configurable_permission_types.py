from __future__ import annotations

import runpy
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
AUTHORIZATION_PATH = REPOSITORY_ROOT / "almdina_erp/almdina_erp/domain/security/authorization.py"
SYNC_PATH = REPOSITORY_ROOT / "almdina_erp/almdina_erp/infrastructure/frappe/permission_type_sync.py"
GATEWAY_PATH = REPOSITORY_ROOT / "almdina_erp/almdina_erp/infrastructure/frappe/authorization_gateway.py"
DXF_SERVICE_PATH = REPOSITORY_ROOT / "almdina_erp/almdina_erp/services/shop_floor_dxf_service.py"
SHOP_FLOOR_UI_PATH = REPOSITORY_ROOT / "almdina_erp/public/js/shop_floor_order_ux.js"
DRAWING_UI_PATH = REPOSITORY_ROOT / "almdina_erp/public/js/door_cutting_order_drawing_plan_ux.js"
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


def test_dxf_server_actions_use_capabilities_and_assigned_designer_policy() -> None:
    source = DXF_SERVICE_PATH.read_text(encoding="utf-8")
    assert "require_document_capability" in source
    assert "validate_assigned_drawing_action" in source
    assert "DXF_ROLES" not in source
    assert "require_roles" not in source
    for capability in (
        "EXPORT_DXF",
        "UPLOAD_DXF",
        "REPLACE_DXF",
        "RECALCULATE_PLAN",
        "APPROVE_DXF",
    ):
        assert capability in source


def test_drawing_presenters_do_not_read_role_names() -> None:
    combined = SHOP_FLOOR_UI_PATH.read_text(encoding="utf-8") + DRAWING_UI_PATH.read_text(encoding="utf-8")
    assert "frappe.user_roles" not in combined
    assert "has_role" not in combined
    assert "hasRole" not in combined
    assert "AlmdinaPermissions" in combined
    assert 'can("approve_dxf")' in combined
    assert 'can("recalculate_plan")' in combined
    assert "current_assignee === frappe.session.user" in combined


def test_legacy_plan_lock_endpoint_is_redirected_to_secure_service() -> None:
    hooks = runpy.run_path(str(HOOKS_PATH))
    overrides = hooks["override_whitelisted_methods"]
    assert overrides[
        "almdina_erp.almdina_erp.services.cutting_plan_service.lock_cutting_plan"
    ] == "almdina_erp.almdina_erp.services.shop_floor_dxf_service.approve_production_dxf"
