from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"
SERVICES = APP / "services"
PAGES = APP / "page"
REPORTS = APP / "report"
PERMISSION_SERVICE = SERVICES / "permission_management_service.py"
PERMISSION_PAGE = PAGES / "factory_permissions" / "factory_permissions.js"
PERMISSION_API = ROOT / "public" / "js" / "factory_permissions" / "api.js"
PERMISSION_STATE = ROOT / "public" / "js" / "factory_permissions" / "state.js"
PERMISSION_VIEW_MODEL = ROOT / "public" / "js" / "factory_permissions" / "view_model.js"
PERMISSION_RENDERER = ROOT / "public" / "js" / "factory_permissions" / "renderer.js"
PERMISSION_INTERACTIONS = ROOT / "public" / "js" / "factory_permissions" / "interactions.js"
PERMISSION_CONTROLLER = ROOT / "public" / "js" / "factory_permissions" / "controller.js"
PERMISSION_FRONTEND_MODULES = (
    PERMISSION_API,
    PERMISSION_STATE,
    PERMISSION_VIEW_MODEL,
    PERMISSION_RENDERER,
    PERMISSION_INTERACTIONS,
    PERMISSION_CONTROLLER,
)
CUTTING_PLAN_SERVICE = SERVICES / "cutting_plan_service.py"
SHOP_FLOOR_FACADE = SERVICES / "shop_floor_service.py"
GATEWAY_FACADE = APP / "infrastructure" / "frappe" / "shop_floor_gateway.py"
TRANSFER_POLICY = APP / "application" / "security" / "permission_transfer.py"
HOOKS = ROOT / "hooks.py"
MANIFEST = ROOT / "frontend_assets.py"
ROLLOUT = ROOT.parent / "docs" / "permission-rollout-checklist.md"

_FIXED_BUSINESS_ROLES = (
    "Production Manager",
    "System Manager",
    "Accounts Manager",
    "Accounts Management",
    "Accounts User",
    "Order Entry",
    "Sales Manager",
)
_ROLE_GATE_PATTERNS = (
    r"frappe\.get_roles\(",
    r"frappe\.user_roles",
    r"require_any_role(?:\s*=|\()",
    r"require_roles\(",
    r"has_role\(",
)
_RETIRED_PRODUCT_MODULES = frozenset(
    {
        "actual_consumption_reversal",
        "actual_consumption_service",
        "performance_service",
        "preflight_service",
        "remnant_service",
        "settings_access_service",
        "stock_availability_service",
        "stock_service",
    }
)
_RETIRED_TARGET = (
    "almdina_erp.almdina_erp.services.legacy_endpoint_service."
    "retired_product_endpoint"
)


def _literal_assignment(name: str, source_path: Path = HOOKS) -> Any:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"Missing assignment in {source_path.name}: {name}")


def _loaded_javascript_paths() -> list[Path]:
    paths: set[Path] = set()
    for asset in _literal_assignment("app_include_js", MANIFEST):
        paths.add(ROOT / "public" / "js" / str(asset).rsplit("/", 1)[-1])
    for configured in _literal_assignment("doctype_js", MANIFEST).values():
        values = configured if isinstance(configured, list) else [configured]
        for value in values:
            paths.add(ROOT / "public" / str(value).removeprefix("public/"))
    paths.update(PAGES.rglob("*.js"))
    # Factory Permissions modules are page-local assets loaded through
    # frappe.require(), so they must remain inside the browser security scan
    # even though they are intentionally absent from the global asset manifest.
    paths.update(PERMISSION_FRONTEND_MODULES)
    return sorted(path for path in paths if path.exists())


def _override_methods() -> dict[str, str]:
    return dict(_literal_assignment("override_whitelisted_methods"))


def _module_name(path: Path) -> str:
    relative = path.relative_to(ROOT).with_suffix("")
    return ".".join((ROOT.name, *relative.parts))


def _whitelisted_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    functions: set[str] = set()
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "frappe"
                and target.attr == "whitelist"
            ):
                functions.add(node.name)
    return functions


def _contains_role_gate(source: str) -> list[str]:
    markers = [f"fixed role {role}" for role in _FIXED_BUSINESS_ROLES if role in source]
    markers.extend(
        f"role gate {pattern}"
        for pattern in _ROLE_GATE_PATTERNS
        if re.search(pattern, source)
    )
    return markers


def _function_calls(source: str, function_name: str) -> set[str]:
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    )
    calls: set[str] = set()
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            calls.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            calls.add(node.func.attr)
    return calls


class TestFinalSecurityArchitecture(unittest.TestCase):
    def test_loaded_browser_surfaces_have_no_role_name_gates(self) -> None:
        offenders = [
            f"{path.relative_to(ROOT)}: {marker}"
            for path in _loaded_javascript_paths()
            for marker in _contains_role_gate(path.read_text(encoding="utf-8"))
        ]
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_every_exposed_legacy_role_endpoint_is_overridden(self) -> None:
        overrides = _override_methods()
        offenders: list[str] = []
        for path in sorted(SERVICES.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            markers = _contains_role_gate(source)
            if not markers:
                continue
            module = _module_name(path)
            unprotected = sorted(
                function
                for function in _whitelisted_functions(path)
                if f"{module}.{function}" not in overrides
            )
            if unprotected:
                offenders.append(
                    f"{path.relative_to(ROOT)} exposes {', '.join(unprotected)} "
                    f"with {'; '.join(markers)}"
                )
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_canonical_authorization_boundaries_are_role_free(self) -> None:
        names = (
            "permission_management_service.py",
            "order_lifecycle_permission_service.py",
            "order_approval_service.py",
            "order_review_service.py",
            "order_dispatch_service.py",
            "drawing_approval_service.py",
            "dxf_export_service.py",
            "shop_floor_commands.py",
            "shop_floor_query_service.py",
            "cost_permission_service.py",
            "workforce_management_service.py",
            "factory_settings_service.py",
            "factory_master_data_service.py",
            "order_creation_service.py",
            "replacement_cancellation_service.py",
            "order_edit_policy.py",
        )
        candidates = [
            path
            for name in names
            for path in (SERVICES / name, APP / "infrastructure" / "frappe" / name)
            if path.exists()
        ]
        offenders = [
            f"{path.relative_to(ROOT)}: {marker}"
            for path in candidates
            for marker in _contains_role_gate(path.read_text(encoding="utf-8"))
        ]
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_retired_product_endpoints_are_fail_closed_and_not_loaded(self) -> None:
        overrides = _override_methods()
        loaded_js = "\n".join(str(path.relative_to(ROOT)) for path in _loaded_javascript_paths())
        for module in _RETIRED_PRODUCT_MODULES:
            prefix = f"almdina_erp.almdina_erp.services.{module}."
            mappings = {source: target for source, target in overrides.items() if source.startswith(prefix)}
            self.assertTrue(mappings, f"Missing retired mapping for {module}")
            self.assertTrue(all(target == _RETIRED_TARGET for target in mappings.values()), mappings)
            self.assertNotIn(module, loaded_js)
        for legacy_js in (
            "material_consumption_log.js",
            "production_stage.js",
            "door_cutting_order_workflow.js",
            "door_cutting_order_cost_invoice_ux.js",
        ):
            self.assertNotIn(legacy_js, loaded_js)

    def test_active_controller_and_reports_have_no_role_gates(self) -> None:
        candidates = [
            APP / "doctype" / "door_cutting_order" / "door_cutting_order_controller.py",
            ROOT / "permissions.py",
            *REPORTS.rglob("*.py"),
        ]
        offenders = [
            f"{path.relative_to(ROOT)}: {marker}"
            for path in candidates
            for marker in _contains_role_gate(path.read_text(encoding="utf-8"))
        ]
        self.assertEqual(offenders, [], "\n".join(offenders))
        hooks = HOOKS.read_text(encoding="utf-8")
        self.assertIn("door_cutting_order_controller.DoorCuttingOrderController", hooks)
        self.assertNotIn("door_cutting_order_fast.DoorCuttingOrder", hooks)
        self.assertNotIn("door_cutting_order_domain.DoorCuttingOrder", hooks)

    def test_legacy_shop_floor_facade_exposes_no_role_authorization_symbols(self) -> None:
        service = SHOP_FLOOR_FACADE.read_text(encoding="utf-8")
        gateway = GATEWAY_FACADE.read_text(encoding="utf-8")
        self.assertIn("Backward-compatible shop-floor API facade", service)
        self.assertIn("_public_delegate", service)
        for symbol in (
            "require_any_role",
            "_require_stage_assignee_or_admin",
            "DISPATCH_ROLES",
            "ADMIN_ROLES",
            "SHOP_FLOOR_ROLES",
        ):
            self.assertNotIn(symbol, service)
        self.assertNotIn("frappe.db.sql", service)
        self.assertNotIn("frappe.get_doc", service)
        self.assertIn("_legacy_role_gate_removed()", gateway)
        self.assertIn("raise PermissionError", gateway)
        self.assertNotIn("frappe.get_roles", gateway)

    def test_cutting_plan_legacy_endpoints_delegate_to_canonical_services(self) -> None:
        source = CUTTING_PLAN_SERVICE.read_text(encoding="utf-8")
        self.assertNotIn("def require_any_role", source)
        self.assertNotIn("frappe.get_roles", source)
        for service in (
            "order_lifecycle_permission_service",
            "order_approval_service",
            "order_dispatch_service",
            "drawing_approval_service",
            "order_review_service",
        ):
            self.assertIn(service, source)

    def test_permission_transfer_is_preview_first_and_server_authorized(self) -> None:
        service = PERMISSION_SERVICE.read_text(encoding="utf-8")
        page = PERMISSION_PAGE.read_text(encoding="utf-8")
        frontend_modules = [path.read_text(encoding="utf-8") for path in PERMISSION_FRONTEND_MODULES]
        api = PERMISSION_API.read_text(encoding="utf-8")
        controller = PERMISSION_CONTROLLER.read_text(encoding="utf-8")
        browser_surface = "\n".join((page, *frontend_modules))
        for endpoint in (
            "get_permission_console",
            "export_role_permissions",
            "export_permission_bundle",
            "preview_permission_import",
            "preview_permission_bundle_import",
            "import_permission_bundle",
            "update_role_permissions",
        ):
            self.assertIn("_require_permission_management", _function_calls(service, endpoint))
        self.assertIn("confirm_sensitive", service)
        self.assertIn("confirm_self_lockout", service)
        self.assertIn("save_role_states", service)
        self.assertNotIn("preview_permission_template", service)
        self.assertNotIn("preview_permission_template", browser_surface)
        self.assertNotIn("apc-template", browser_surface)
        self.assertIn("preview_permission_import", api)
        self.assertIn("export_role_permissions", api)
        self.assertIn("previewImport", controller)
        self.assertIn("previewExternal", controller)
        self.assertIn("updateRole", controller)
        self.assertIn("لن يتم الحفظ تلقائيًا", browser_surface)
        policy = TRANSFER_POLICY.read_text(encoding="utf-8")
        self.assertIn("build_permission_bundle", policy)
        self.assertIn("parse_permission_bundle", policy)
        self.assertIn("checksum", policy)
        self.assertNotIn("PermissionTemplate", policy)
        self.assertNotIn("frappe.user_roles", browser_surface)

    def test_hooks_keep_old_api_paths_on_protected_services(self) -> None:
        hooks = HOOKS.read_text(encoding="utf-8")
        for service in (
            "order_lifecycle_permission_service.submit_order_for_review",
            "order_approval_service.approve_order",
            "order_review_service.reject_order",
            "order_dispatch_service.validate_order_for_dispatch",
            "drawing_approval_service.approve_production_dxf",
            "dxf_export_service.get_validated_dxf_plan",
            "shop_floor_query_service.get_shop_floor_context",
            "legacy_endpoint_service.retired_product_endpoint",
        ):
            self.assertIn(service, hooks)

    def test_rollout_checklist_covers_backup_validation_and_rollback(self) -> None:
        source = ROLLOUT.read_text(encoding="utf-8")
        for heading in (
            "نسخة احتياطية",
            "بيئة Develop",
            "اختبارات الشخصيات",
            "فحص تسريب البيانات",
            "خطة الرجوع",
            "قرار الإطلاق",
        ):
            self.assertIn(heading, source)
        self.assertIn("update-almdina", source)
        self.assertIn("لا يتم الدمج", source)
        self.assertIn("Checksum", source)
        self.assertIn("API", source)
        self.assertIn("preview_permission_bundle_import", source)
        self.assertIn("Role واحد غير موجود", source)


if __name__ == "__main__":
    unittest.main()
