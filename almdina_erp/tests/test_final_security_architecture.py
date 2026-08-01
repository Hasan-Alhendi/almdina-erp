from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"
SERVICES = APP / "services"
PAGES = APP / "page"
PUBLIC_JS = ROOT / "public" / "js"
REPORTS = APP / "report"
DOCTYPES = APP / "doctype"
PERMISSION_SERVICE = SERVICES / "permission_management_service.py"
PERMISSION_PAGE = PAGES / "factory_permissions" / "factory_permissions.js"
CUTTING_PLAN_SERVICE = SERVICES / "cutting_plan_service.py"
SHOP_FLOOR_FACADE = SERVICES / "shop_floor_service.py"
GATEWAY_FACADE = APP / "infrastructure" / "frappe" / "shop_floor_gateway.py"
TEMPLATE_POLICY = APP / "application" / "security" / "permission_templates.py"
HOOKS = ROOT / "hooks.py"
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


def _active_authorization_sources() -> list[Path]:
    paths = sorted(SERVICES.glob("*.py"))
    paths += sorted(PAGES.rglob("*.js"))
    paths += sorted(PUBLIC_JS.glob("*.js"))
    paths += sorted(REPORTS.rglob("*.py"))
    paths += sorted(DOCTYPES.rglob("*.py"))
    paths += [
        path
        for path in (
            ROOT / "permissions.py",
            ROOT / "boot.py",
            ROOT / "lifecycle.py",
        )
        if path.exists()
    ]
    return sorted(set(paths))


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
    def test_active_services_and_ui_have_no_fixed_business_role_gates(self) -> None:
        offenders: list[str] = []
        for path in _active_authorization_sources():
            source = path.read_text(encoding="utf-8")
            for role in _FIXED_BUSINESS_ROLES:
                if role in source:
                    offenders.append(
                        f"{path.relative_to(ROOT)}: fixed role {role}"
                    )
            for pattern in _ROLE_GATE_PATTERNS:
                if re.search(pattern, source):
                    offenders.append(
                        f"{path.relative_to(ROOT)}: role gate {pattern}"
                    )
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_legacy_shop_floor_facade_exposes_no_role_authorization_symbols(self) -> None:
        service = SHOP_FLOOR_FACADE.read_text(encoding="utf-8")
        gateway = GATEWAY_FACADE.read_text(encoding="utf-8")
        self.assertIn("Backward-compatible shop-floor API facade", service)
        self.assertIn("_public_delegate", service)
        for removed_symbol in (
            "require_any_role",
            "_require_stage_assignee_or_admin",
            "DISPATCH_ROLES",
            "ADMIN_ROLES",
            "SHOP_FLOOR_ROLES",
        ):
            self.assertNotIn(removed_symbol, service)
        self.assertNotIn("frappe.db.sql", service)
        self.assertNotIn("frappe.get_doc", service)
        # The isolated gateway keeps old imports fail-closed only; active code
        # neither imports nor publishes those symbols.
        self.assertIn("_legacy_role_gate_removed()", gateway)
        self.assertIn("raise PermissionError", gateway)
        self.assertNotIn("frappe.get_roles", gateway)

    def test_cutting_plan_legacy_endpoints_delegate_to_canonical_services(self) -> None:
        source = CUTTING_PLAN_SERVICE.read_text(encoding="utf-8")
        self.assertNotIn("def require_any_role", source)
        self.assertNotIn("frappe.get_roles", source)
        for canonical_service in (
            "order_lifecycle_permission_service",
            "order_approval_service",
            "order_dispatch_service",
            "drawing_approval_service",
            "order_review_service",
        ):
            self.assertIn(canonical_service, source)
        for endpoint in (
            "submit_order_for_review",
            "approve_order",
            "send_order_to_production",
            "lock_cutting_plan",
            "reject_order",
        ):
            self.assertIn(f"def {endpoint}", source)

    def test_permission_transfer_is_preview_first_and_server_authorized(self) -> None:
        service = PERMISSION_SERVICE.read_text(encoding="utf-8")
        page = PERMISSION_PAGE.read_text(encoding="utf-8")
        for endpoint in (
            "get_permission_console",
            "preview_permission_template",
            "export_role_permissions",
            "export_permission_bundle",
            "preview_permission_import",
            "preview_permission_bundle_import",
            "import_permission_bundle",
            "update_role_permissions",
        ):
            self.assertIn(
                "_require_permission_management",
                _function_calls(service, endpoint),
            )
        self.assertIn("confirm_sensitive", service)
        self.assertIn("confirm_self_lockout", service)
        self.assertIn("save_role_states", service)
        self.assertIn("preview_permission_template", page)
        self.assertIn("preview_permission_import", page)
        self.assertIn("export_role_permissions", page)
        self.assertIn("لن يتم الحفظ تلقائيًا", page)
        template_source = TEMPLATE_POLICY.read_text(encoding="utf-8")
        self.assertIn("build_permission_bundle", template_source)
        self.assertIn("parse_permission_bundle", template_source)
        self.assertIn("checksum", template_source)
        self.assertNotIn("frappe.user_roles", page)

    def test_hooks_keep_old_api_paths_on_protected_services(self) -> None:
        source = HOOKS.read_text(encoding="utf-8")
        for service in (
            "order_lifecycle_permission_service.submit_order_for_review",
            "order_approval_service.approve_order",
            "order_review_service.reject_order",
            "order_dispatch_service.validate_order_for_dispatch",
            "drawing_approval_service.approve_production_dxf",
            "shop_floor_query_service.get_shop_floor_context",
        ):
            self.assertIn(service, source)

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


if __name__ == "__main__":
    unittest.main()
