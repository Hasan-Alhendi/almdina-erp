from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path


REPOSITORY_PATH = (
    Path(__file__).resolve().parents[1]
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "canonical_permission_state_repository.py"
)


def load_repository_class():
    fake_frappe = types.ModuleType("frappe")
    previous_frappe = sys.modules.get("frappe")
    sys.modules["frappe"] = fake_frappe
    try:
        spec = importlib.util.spec_from_file_location(
            "_almdina_legacy_audit_migration_repository",
            REPOSITORY_PATH,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("Could not load canonical permission repository")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.CanonicalPermissionStateRepository
    finally:
        if previous_frappe is None:
            sys.modules.pop("frappe", None)
        else:
            sys.modules["frappe"] = previous_frappe


Repository = load_repository_class()


class TestLegacyAuditCapabilityMigration(unittest.TestCase):
    def test_removed_broad_keys_are_ignored_fail_closed(self) -> None:
        state = Repository._decode_legacy_audit(
            {
                "view_orders": True,
                "manage_users": True,
                "assign_workforce_profile": True,
                "manage_factory_settings": True,
            }
        )

        self.assertTrue(state["view_orders"])
        self.assertFalse(state["view_users"])
        self.assertFalse(state["create_users"])
        self.assertFalse(state["assign_user_roles"])
        self.assertFalse(state["view_factory_settings"])
        self.assertFalse(state["edit_factory_cutting_defaults"])
        self.assertFalse(state["edit_factory_cost_defaults"])
        self.assertFalse(state["edit_factory_production_controls"])
        self.assertNotIn("manage_users", state)
        self.assertNotIn("assign_workforce_profile", state)
        self.assertNotIn("manage_factory_settings", state)

    def test_current_canonical_decoder_remains_strict(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown capabilities"):
            Repository._decode({"manage_users": True})

    def test_removed_keys_only_produce_deny_all(self) -> None:
        state = Repository._decode_legacy_audit(
            {
                "manage_users": True,
                "assign_workforce_profile": True,
                "manage_factory_settings": True,
            }
        )
        self.assertFalse(any(state.values()))


if __name__ == "__main__":
    unittest.main()
