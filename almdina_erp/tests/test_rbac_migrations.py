from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCHES = ROOT / "patches.txt"
MIGRATE_WORKFORCE = ROOT / "patches" / "v1_0" / "migrate_dynamic_workforce_roles.py"
MIGRATE_ADMIN = ROOT / "patches" / "v1_0" / "migrate_granular_administration_permissions.py"
MATERIALIZE = ROOT / "patches" / "v1_0" / "materialize_permission_prerequisites.py"
MATERIALIZE_ROLE_ADMIN = ROOT / "patches" / "v1_0" / "materialize_role_administration_prerequisites.py"
HELPERS = ROOT / "patches" / "v1_0" / "permission_migration_helpers.py"
SYNC = ROOT / "almdina_erp" / "infrastructure" / "frappe" / "permission_type_sync.py"
LEGACY_BOOTSTRAP = ROOT / "almdina_erp" / "infrastructure" / "frappe" / "legacy_permission_bootstrap.py"


class TestRbacMigrations(unittest.TestCase):
    def test_post_model_migration_order_is_safe(self) -> None:
        source = PATCHES.read_text(encoding="utf-8")
        workforce = source.index("migrate_dynamic_workforce_roles")
        administration = source.index("migrate_granular_administration_permissions")
        prerequisites = source.index("materialize_permission_prerequisites")
        role_administration = source.index("materialize_role_administration_prerequisites")
        self.assertLess(workforce, administration)
        self.assertLess(administration, prerequisites)
        self.assertLess(prerequisites, role_administration)

    def test_workforce_migration_adopts_before_bootstrapping_and_never_creates_roles(self) -> None:
        source = MIGRATE_WORKFORCE.read_text(encoding="utf-8")
        execute = source.split("def execute()", 1)[1]
        self.assertLess(execute.index("_adopt_existing_workforce_roles()"), execute.index("bootstrap_legacy_role_permissions()"))
        self.assertIn("ensure_permission_types(ALL_CAPABILITIES)", execute)
        self.assertIn("_roles_with_almdina_capability_grants", source)
        self.assertIn("_roles_with_permission_audit", source)
        self.assertIn('"assign_workforce_profile"', source)
        self.assertNotIn('"doctype": "Role"', source)

    def test_legacy_administration_grants_are_materialized_without_full_sync(self) -> None:
        source = MIGRATE_ADMIN.read_text(encoding="utf-8")
        self.assertIn("ensure_permission_types", source)
        self.assertIn('"manage_users"', source)
        self.assertIn('"manage_factory_settings"', source)
        self.assertNotIn("sync_permission_types", source)
        self.assertNotIn('"doctype": "Role"', source)

    def test_permission_type_helper_has_no_role_reconciliation(self) -> None:
        source = HELPERS.read_text(encoding="utf-8")
        self.assertIn("ensure_permission_types", source)
        self.assertNotIn("save_role_state", source)
        self.assertNotIn("reconcile_custom_permission_projections", source)

    def test_normal_permission_sync_does_not_rewrite_role_matrices(self) -> None:
        source = SYNC.read_text(encoding="utf-8")
        function = source.split("def sync_permission_types()", 1)[1]
        self.assertNotIn("reconcile_custom_permission_projections()", function)
        self.assertIn("ensure_custom_permission_baseline", function)

    def test_prerequisite_materialization_reconciles_managed_roles_last(self) -> None:
        source = MATERIALIZE.read_text(encoding="utf-8")
        self.assertIn("required_capabilities", source)
        self.assertIn("managed_role_names", source)
        self.assertIn("repository.save_role_state(role, explicit)", source)
        self.assertNotIn('"doctype": "Role"', source)

    def test_role_administration_migration_adds_visibility_only(self) -> None:
        source = MATERIALIZE_ROLE_ADMIN.read_text(encoding="utf-8")
        self.assertIn("Capability.VIEW_ROLES", source)
        self.assertIn("Capability.ASSIGN_USER_ROLES", source)
        self.assertIn("Capability.MANAGE_PERMISSIONS", source)
        self.assertIn("Capability.CREATE_ROLES", source)
        self.assertIn("Capability.EDIT_ROLES", source)
        self.assertIn("Capability.DELETE_ROLES", source)
        self.assertIn("explicit[Capability.VIEW_ROLES] = True", source)
        self.assertNotIn("explicit[Capability.CREATE_ROLES] = True", source)
        self.assertNotIn("explicit[Capability.EDIT_ROLES] = True", source)
        self.assertNotIn("explicit[Capability.DELETE_ROLES] = True", source)
        self.assertNotIn('"doctype": "Role"', source)

    def test_early_legacy_bootstrap_skips_unregistered_roles(self) -> None:
        source = LEGACY_BOOTSTRAP.read_text(encoding="utf-8")
        self.assertIn("registered = managed_role_names()", source)
        self.assertIn("if role not in registered", source)
        self.assertNotIn('"doctype": "Role"', source)


if __name__ == "__main__":
    unittest.main()
