from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIFECYCLE = ROOT / "lifecycle.py"
PATCHES = ROOT / "patches.txt"
LEGACY_PATCH = "almdina_erp.patches.v1_0.bootstrap_legacy_role_capabilities"


class TestSecurityLifecycleMigration(unittest.TestCase):
    def test_runtime_lifecycle_repairs_security_without_seeding_role_permissions(self) -> None:
        source = LIFECYCLE.read_text(encoding="utf-8")

        self.assertIn("sync_permission_types()", source)
        self.assertIn(
            "revoke_hidden_system_manager_from_almdina_workforce()",
            source,
        )
        self.assertNotIn("bootstrap_legacy_role_permissions", source)
        self.assertNotIn("legacy_permission_bootstrap", source)

    def test_legacy_role_bootstrap_remains_one_time_patch_only(self) -> None:
        patches = PATCHES.read_text(encoding="utf-8")

        self.assertIn(LEGACY_PATCH, patches)


if __name__ == "__main__":
    unittest.main()
