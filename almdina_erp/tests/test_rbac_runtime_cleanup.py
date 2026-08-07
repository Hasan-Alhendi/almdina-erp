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
# These sources are intentionally retained only to make historical endpoints
# fail closed or to preserve old browser assets for rollback. They are not
# loaded by the current hooks/UI; test_final_security_architecture.py verifies
# that boundary independently. Historical role-name scanning must therefore
# target active runtime, not these retired files.
RETIRED_ROLE_NAME_SOURCES = frozenset(
    {
        "almdina_erp/services/export_validation_service.py",
        "almdina_erp/services/preflight_service.py",
        "almdina_erp/services/remnant_service.py",
        "almdina_erp/services/actual_consumption_service.py",
        "public/js/production_stage.js",
        "public/js/door_cutting_order_cost_invoice_ux.js",
        "public/js/material_consumption_log.js",
        "public/js/door_cutting_order_workflow.js",
    }
)
RETIRED_RUNTIME_TOKENS = (
    "OperationalProfile",
    "PermissionTemplate",
    "permission_template_catalog",
    "preview_permission_template",
    "assign_workforce_profile",
    "ASSIGN_WORKFORCE_PROFILE",
    "MANAGE_USERS",
    "MANAGE_FACTORY_SETTINGS",
    "permission_transfer",
    "export_role_permissions",
    "export_permission_bundle",
    "preview_permission_import",
    "preview_permission_bundle_import",
    "import_permission_bundle",
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

    def test_historical_business_role_names_exist_only_in_migration_or_retired_sources(self) -> None:
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
            relative = path.relative_to(ROOT).as_posix()
            if relative in RETIRED_ROLE_NAME_SOURCES:
                continue
            source = path.read_text(encoding="utf-8")
            for role in role_names:
                if role in source:
                    offenders.append(f"{relative} -> {role}")
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_retired_role_name_sources_are_explicit_and_still_present(self) -> None:
        missing = [
            relative
            for relative in sorted(RETIRED_ROLE_NAME_SOURCES)
            if not (ROOT / relative).exists()
        ]
        self.assertEqual(missing, [])

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
