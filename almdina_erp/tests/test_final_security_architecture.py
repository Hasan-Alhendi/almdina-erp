from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"
SERVICES = APP / "services"
PAGES = APP / "page"
PUBLIC_JS = ROOT / "public" / "js"
PERMISSION_SERVICE = SERVICES / "permission_management_service.py"
PERMISSION_PAGE = PAGES / "factory_permissions" / "factory_permissions.js"
SHOP_FLOOR_FACADE = SERVICES / "shop_floor_service.py"
GATEWAY_FACADE = APP / "infrastructure" / "frappe" / "shop_floor_gateway.py"
ROLLOUT = ROOT.parent / "docs" / "permission-rollout-checklist.md"


_FIXED_BUSINESS_ROLES = (
    "Production Manager",
    "System Manager",
    "Accounts Manager",
    "Accounts User",
    "Order Entry",
    "Sales Manager",
)


def _active_authorization_sources() -> list[Path]:
    paths = sorted(SERVICES.glob("*.py"))
    paths += sorted(PAGES.rglob("*.js"))
    paths += sorted(PUBLIC_JS.glob("*.js"))
    return [path for path in paths if path.name != "shop_floor_service.py"]


class TestFinalSecurityArchitecture(unittest.TestCase):
    def test_active_services_and_ui_have_no_fixed_business_role_gates(self) -> None:
        offenders: list[str] = []
        for path in _active_authorization_sources():
            source = path.read_text(encoding="utf-8")
            for role in _FIXED_BUSINESS_ROLES:
                if role in source:
                    offenders.append(f"{path.relative_to(ROOT)}: fixed role {role}")
            for pattern in (
                r"frappe\.get_roles\(",
                r"frappe\.user_roles",
                r"require_any_role\(",
                r"has_role\(",
            ):
                if re.search(pattern, source):
                    offenders.append(
                        f"{path.relative_to(ROOT)}: role gate {pattern}"
                    )
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_legacy_shop_floor_role_symbols_are_fail_closed_only(self) -> None:
        service = SHOP_FLOOR_FACADE.read_text(encoding="utf-8")
        gateway = GATEWAY_FACADE.read_text(encoding="utf-8")
        self.assertIn("Backward-compatible shop-floor API facade", service)
        self.assertIn("_public_delegate", service)
        self.assertIn("require_any_role = shop_floor_gateway.require_roles", service)
        self.assertIn("DISPATCH_ROLES: tuple[str, ...] = ()", gateway)
        self.assertIn("ADMIN_ROLES: tuple[str, ...] = ()", gateway)
        self.assertIn("_legacy_role_gate_removed()", gateway)
        self.assertIn("raise PermissionError", gateway)
        self.assertNotIn("frappe.db.sql", service)
        self.assertNotIn("frappe.get_doc", service)
        self.assertNotIn("frappe.get_roles", gateway)

    def test_permission_transfer_is_preview_first_and_server_authorized(self) -> None:
        service = PERMISSION_SERVICE.read_text(encoding="utf-8")
        page = PERMISSION_PAGE.read_text(encoding="utf-8")
        for endpoint in (
            "get_permission_console",
            "preview_permission_template",
            "export_role_permissions",
            "preview_permission_import",
            "update_role_permissions",
        ):
            function = service.split(f"def {endpoint}", 1)[1].split("\n\n", 1)[0]
            self.assertIn("_require_permission_management()", function)
        self.assertNotIn("import_role_permissions", service)
        self.assertIn("preview_permission_template", page)
        self.assertIn("preview_permission_import", page)
        self.assertIn("export_role_permissions", page)
        self.assertIn("لن يتم الحفظ تلقائيًا", page)
        self.assertIn("Checksum", (APP / "application" / "security" / "permission_templates.py").read_text(encoding="utf-8").replace("checksum", "Checksum"))
        self.assertNotIn("frappe.user_roles", page)

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


if __name__ == "__main__":
    unittest.main()
