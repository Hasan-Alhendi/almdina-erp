from __future__ import annotations

import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HOOKS_PATH = REPOSITORY_ROOT / "almdina_erp/frontend_assets.py"
BOOT_PATH = REPOSITORY_ROOT / "almdina_erp/boot.py"
PERMISSIONS_PATH = REPOSITORY_ROOT / "almdina_erp/permissions.py"
PERMISSION_JS_PATH = REPOSITORY_ROOT / "almdina_erp/public/js/permission_context.js"
SHARED_SHELL_PATH = REPOSITORY_ROOT / "almdina_erp/public/js/shared_shell.js"
SHOP_FLOOR_PAGE_PATH = (
    REPOSITORY_ROOT
    / "almdina_erp/almdina_erp/page/shop_floor_inbox/shop_floor_inbox.js"
)
SHOP_FLOOR_PAGE_JSON_PATH = SHOP_FLOOR_PAGE_PATH.with_suffix(".json")
SHOP_FLOOR_WORKSPACE_PATH = (
    REPOSITORY_ROOT
    / "almdina_erp/almdina_erp/workspace/shop_floor/shop_floor.json"
)
PLAN_TABS_PATH = (
    REPOSITORY_ROOT
    / "almdina_erp/public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_tabs_ux.js"
)


def test_permission_context_and_shared_shell_load_before_global_presenters() -> None:
    hooks_source = HOOKS_PATH.read_text(encoding="utf-8")
    permission_index = hooks_source.index("/assets/almdina_erp/js/permission_context.js")
    shell_index = hooks_source.index("/assets/almdina_erp/js/shared_shell.js")
    operator_index = hooks_source.index("/assets/almdina_erp/js/arabic_operator_ui.js")
    assert permission_index < shell_index < operator_index
    assert "shop_floor_desk.js" not in hooks_source
    assert "order_entry_desk.js" not in hooks_source


def test_boot_exposes_capability_navigation_without_roles() -> None:
    source = BOOT_PATH.read_text(encoding="utf-8")
    assert "build_permission_context" in source
    assert 'bootinfo["almdina_permissions"]' in source
    assert 'bootinfo["almdina_navigation"]' in source
    assert 'bootinfo["almdina_shared_shell"]' in source
    assert 'if not navigation.get("shared_shell")' in source
    assert "frappe.get_roles" not in source
    for legacy in ("almdina_shop_floor_only", "almdina_order_entry_only"):
        assert legacy not in source


def test_frontend_permission_api_is_boot_backed_and_fail_closed() -> None:
    source = PERMISSION_JS_PATH.read_text(encoding="utf-8")
    assert "frappe.boot.almdina_permissions" in source
    assert "window.AlmdinaPermissions" in source
    assert "navigation()" in source
    assert "section(sectionName)" in source
    assert 'shared_shell: false' in source
    assert '=== true' in source
    assert "canDocument(frm, capability)" in source
    assert "nativeDocumentPermission" in source
    assert "frappe.user_roles" not in source


def test_shared_shell_keeps_desk_and_uses_navigation_context() -> None:
    source = SHARED_SHELL_PATH.read_text(encoding="utf-8")
    assert "AlmdinaPermissions" in source
    assert "navigation()" in source
    assert "shared_shell" in source
    assert "!nav.shared_shell || !nav.home_page || !routeIsRoot()" in source
    assert "frappe.user_roles" not in source
    assert "frappe.set_route = function" not in source
    assert "frappe.set_route = (" not in source
    assert "frappe.set_route(home)" in source

    # Frappe renders workspace shortcuts asynchronously. The observer is deliberately
    # narrow: it only reacts to added child nodes, then runs the debounced permission
    # visibility scan. It must never become a general DOM mutation watcher.
    assert "MutationObserver" in source
    assert "schedulePermissionScan" in source
    assert "observer.observe(document.body, { childList: true, subtree: true })" in source
    assert "attributes: true" not in source
    assert "characterData: true" not in source

    for hidden_chrome in (".awesomebar", ".body-sidebar", ".notifications-icon"):
        assert hidden_chrome not in source


def test_shop_floor_page_uses_server_context_and_shared_order_form() -> None:
    source = SHOP_FLOOR_PAGE_PATH.read_text(encoding="utf-8")
    assert "get_shop_floor_context" in source
    assert "get_my_inbox" in source
    assert "can_start_stage" in source
    assert "can_handoff_stage" in source
    assert 'frappe.set_route("Form", "Door Cutting Order", context.order)' in source
    assert "requestId !== listRequest" in source
    assert "document_capabilities" not in source
    assert "buildPlanTabsHtml" not in source
    assert "renderDetail" not in source
    assert "frappe.user_roles" not in source
    for role in ("Production Manager", "System Manager", "عامل رسم", "عامل CNC"):
        assert role not in source


def test_shop_floor_workspace_and_page_have_no_fixed_roles() -> None:
    page = json.loads(SHOP_FLOOR_PAGE_JSON_PATH.read_text(encoding="utf-8"))
    workspace = json.loads(SHOP_FLOOR_WORKSPACE_PATH.read_text(encoding="utf-8"))
    assert page["roles"] == []
    assert workspace["roles"] == []


def test_permission_queries_use_capabilities_and_assignment_not_role_names() -> None:
    source = PERMISSIONS_PATH.read_text(encoding="utf-8")
    assert "doctype_has_capability" in source
    assert "assigned_to" in source
    assert "frappe.get_roles" not in source
    assert "apply_shop_floor_user_restrictions" not in source
    assert "apply_order_entry_user_restrictions" not in source
    for role in ("Production Manager", "System Manager", "Order Entry", "عامل رسم"):
        assert role not in source


def test_cutting_plan_tabs_use_capability_not_role_names() -> None:
    source = PLAN_TABS_PATH.read_text(encoding="utf-8")
    assert 'context.canDocument(frm, capability)' in source or 'canDocument(frm, capability)' in source
    assert "view_system_cutting_plan" in source
    assert "view_uploaded_cutting_plan" in source
    assert "view_approved_cutting_plan" in source
    assert "الخطة المعتمدة" in source
    assert "frappe.user_roles" not in source
    assert "DUAL_ROLES" not in source
    for role in ("Order Entry", "Production Manager", "System Manager", "عامل رسم"):
        assert role not in source
