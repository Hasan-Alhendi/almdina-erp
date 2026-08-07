from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOTS = (
    ROOT / "almdina_erp" / "domain",
    ROOT / "almdina_erp" / "application",
    ROOT / "almdina_erp" / "infrastructure",
    ROOT / "almdina_erp" / "services",
    ROOT / "almdina_erp" / "page",
    ROOT / "public" / "js",
)
MIGRATION_COMPATIBILITY_FILES = {
    "legacy_permission_bootstrap.py",
}
RETIRED_RUNTIME_TOKENS = (
    "OperationalProfile",
    "PermissionTemplate",
    "permission_template_catalog",
    "preview_permission_template",
    "assign_workforce_profile",
    "ASSIGN_WORKFORCE_PROFILE",
    "MANAGE_USERS",
    "MANAGE_FACTORY_SETTINGS",
)
RETIRED_RUNTIME_STRING_GRANTS = (
    '"manage_users"',
    '"manage_factory_settings"',
)


class TestRbacRuntimeCleanup(unittest.TestCase):
    @staticmethod
    def _runtime_files():
        for root in RUNTIME_ROOTS:
            if not root.exists():
                continue
            for pattern in ("*.py", "*.js"):
                for path in root.rglob(pattern):
                    if path.name in MIGRATION_COMPATIBILITY_FILES:
                        continue
                    yield path

    def test_retired_authorization_concepts_do_not_return_to_runtime(self) -> None:
        offenders: list[str] = []
        for path in self._runtime_files():
            source = path.read_text(encoding="utf-8")
            for token in (*RETIRED_RUNTIME_TOKENS, *RETIRED_RUNTIME_STRING_GRANTS):
                if token in source:
                    offenders.append(f"{path.relative_to(ROOT)} -> {token}")
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_historical_business_role_names_exist_only_in_migration_compatibility(self) -> None:
        role_names = (
            "Production Manager",
            "Cutting Operator",
            "Edge Operator",
            "Order Entry",
            "Accounts Management",
            "عامل رسم",
            "عامل شريون",
            "عامل CNC",
            "عامل تقشيط",
        )
        offenders: list[str] = []
        for path in self._runtime_files():
            source = path.read_text(encoding="utf-8")
            for role in role_names:
                if role in source:
                    offenders.append(f"{path.relative_to(ROOT)} -> {role}")
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_permission_ui_never_auto_enables_prerequisites(self) -> None:
        page = (
            ROOT
            / "almdina_erp"
            / "page"
            / "factory_permissions"
            / "factory_permissions.js"
        ).read_text(encoding="utf-8")
        self.assertIn("localMissingDependencies", page)
        self.assertIn("لن يضيف النظام هذه الصلاحيات تلقائيًا", page)
        self.assertNotIn("state.working.view_orders = true", page)
        self.assertNotIn("orderCapabilityKeys", page)


if __name__ == "__main__":
    unittest.main()
