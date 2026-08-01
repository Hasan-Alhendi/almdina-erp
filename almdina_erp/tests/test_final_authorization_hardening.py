from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "almdina_erp"
SERVICES = PACKAGE / "services"
PAGES = PACKAGE / "page"
PUBLIC_JS = ROOT / "public" / "js"
REPORTS = PACKAGE / "report"
DOCTYPES = PACKAGE / "doctype"
CUTTING_PLAN_SERVICE = SERVICES / "cutting_plan_service.py"
SHOP_FLOOR_FACADE = SERVICES / "shop_floor_service.py"
HOOKS = ROOT / "hooks.py"


FORBIDDEN_AUTHORIZATION_MARKERS = (
    "frappe.user_roles",
    "frappe.get_roles(",
    "require_any_role",
    "require_roles(",
    '"System Manager"',
    '"Production Manager"',
    '"Order Entry"',
    '"Accounts Management"',
)


class TestFinalAuthorizationHardening(unittest.TestCase):
    def _active_files(self) -> list[Path]:
        files: list[Path] = []
        files.extend(SERVICES.glob("*.py"))
        files.extend(PAGES.rglob("*.js"))
        files.extend(PUBLIC_JS.glob("*.js"))
        files.extend(REPORTS.rglob("*.py"))
        files.extend(DOCTYPES.rglob("*.py"))
        files.extend(
            path
            for path in (
                ROOT / "permissions.py",
                ROOT / "boot.py",
                ROOT / "lifecycle.py",
            )
            if path.exists()
        )
        return sorted(set(files))

    def test_active_business_boundaries_contain_no_role_name_gates(self) -> None:
        violations: list[str] = []
        for path in self._active_files():
            source = path.read_text(encoding="utf-8")
            for marker in FORBIDDEN_AUTHORIZATION_MARKERS:
                if marker in source:
                    violations.append(
                        f"{path.relative_to(ROOT)} contains {marker}"
                    )
        self.assertEqual(
            violations,
            [],
            "Business authorization must use configurable capabilities:\n"
            + "\n".join(violations),
        )

    def test_browser_surfaces_never_read_role_arrays(self) -> None:
        violations: list[str] = []
        for path in sorted(
            list(PAGES.rglob("*.js")) + list(PUBLIC_JS.glob("*.js"))
        ):
            source = path.read_text(encoding="utf-8")
            for marker in (
                "frappe.user_roles",
                "user_roles.includes",
                "user_roles.indexOf",
            ):
                if marker in source:
                    violations.append(
                        f"{path.relative_to(ROOT)} contains {marker}"
                    )
        self.assertEqual(violations, [])

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

    def test_shop_floor_facade_keeps_api_compatibility_without_role_gates(self) -> None:
        source = SHOP_FLOOR_FACADE.read_text(encoding="utf-8")
        for removed_symbol in (
            "require_any_role",
            "_require_stage_assignee_or_admin",
            "DISPATCH_ROLES",
            "ADMIN_ROLES",
            "SHOP_FLOOR_ROLES",
        ):
            self.assertNotIn(removed_symbol, source)
        self.assertIn("_public_delegate", source)
        self.assertIn("dispatch_order = _public_delegate", source)
        self.assertIn("start_my_stage = _public_delegate", source)

    def test_hooks_keep_old_api_paths_on_protected_services(self) -> None:
        source = HOOKS.read_text(encoding="utf-8")
        expected = (
            "order_lifecycle_permission_service.submit_order_for_review",
            "order_approval_service.approve_order",
            "order_review_service.reject_order",
            "order_dispatch_service.validate_order_for_dispatch",
            "drawing_approval_service.approve_production_dxf",
            "shop_floor_query_service.get_shop_floor_context",
        )
        for service in expected:
            self.assertIn(service, source)


if __name__ == "__main__":
    unittest.main()
