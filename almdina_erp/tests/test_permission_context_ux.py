from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HOOKS_PATH = REPOSITORY_ROOT / "almdina_erp/hooks.py"
BOOT_PATH = REPOSITORY_ROOT / "almdina_erp/boot.py"
PERMISSION_JS_PATH = REPOSITORY_ROOT / "almdina_erp/public/js/permission_context.js"
PLAN_TABS_PATH = (
    REPOSITORY_ROOT
    / "almdina_erp/public/js/door_cutting_order_plan_tabs_ux.js"
)


def test_permission_context_loads_before_global_presenters() -> None:
    hooks_source = HOOKS_PATH.read_text(encoding="utf-8")
    permission_index = hooks_source.index("/assets/almdina_erp/js/permission_context.js")
    operator_index = hooks_source.index("/assets/almdina_erp/js/arabic_operator_ui.js")
    assert permission_index < operator_index


def test_boot_exposes_application_permission_context() -> None:
    source = BOOT_PATH.read_text(encoding="utf-8")
    assert "build_permission_context" in source
    assert 'bootinfo["almdina_permissions"]' in source


def test_frontend_permission_api_is_boot_backed_and_fail_closed() -> None:
    source = PERMISSION_JS_PATH.read_text(encoding="utf-8")
    assert "frappe.boot.almdina_permissions" in source
    assert "window.AlmdinaPermissions" in source
    assert '=== true' in source
    assert "frappe.user_roles" not in source


def test_cutting_plan_tabs_use_capability_not_role_names() -> None:
    source = PLAN_TABS_PATH.read_text(encoding="utf-8")
    assert 'context.can("view_cutting_plan")' in source
    assert "frappe.user_roles" not in source
    assert "DUAL_ROLES" not in source
    for role in ("Order Entry", "Production Manager", "System Manager", "عامل رسم"):
        assert role not in source
