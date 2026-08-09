from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCHES = ROOT / "patches.txt"
RESET_PATCH = (
    ROOT
    / "patches"
    / "v1_0"
    / "reset_canonical_permission_states.py"
)
LOOKUP_CLEANUP_PATCH = (
    ROOT
    / "patches"
    / "v1_0"
    / "clean_order_lookup_business_grants.py"
)


class TestCanonicalPermissionResetPatch(unittest.TestCase):
    def test_reset_patch_is_registered_post_model_sync_once(self) -> None:
        registry = PATCHES.read_text(encoding="utf-8")
        entry = "almdina_erp.patches.v1_0.reset_canonical_permission_states"
        self.assertEqual(registry.count(entry), 1)
        post = registry[registry.index("[post_model_sync]"):]
        self.assertIn(entry, post)

    def test_reset_patch_resets_only_existing_editable_canonical_roles(self) -> None:
        source = RESET_PATCH.read_text(encoding="utf-8")
        self.assertIn("STATE_DOCTYPE", source)
        self.assertIn("PROTECTED_SYSTEM_ROLES", source)
        self.assertIn("frappe.db.exists(\"Role\", role)", source)
        self.assertIn("role: {}", source)
        self.assertIn("ProjectedPermissionMatrixRepository().save_role_states(prepared)", source)
        self.assertNotIn("latest_audited_state", source)
        self.assertNotIn("DocPerm", source)
        self.assertNotIn("Custom DocPerm", source)

    def test_lookup_business_cleanup_is_registered_after_canonical_reset(self) -> None:
        registry = PATCHES.read_text(encoding="utf-8")
        reset = "almdina_erp.patches.v1_0.reset_canonical_permission_states"
        cleanup = "almdina_erp.patches.v1_0.clean_order_lookup_business_grants"
        self.assertEqual(registry.count(cleanup), 1)
        self.assertGreater(registry.index(cleanup), registry.index(reset))

    def test_lookup_cleanup_preserves_technical_projection_boundary(self) -> None:
        source = LOOKUP_CLEANUP_PATCH.read_text(encoding="utf-8")
        self.assertIn("Capability.VIEW_CUSTOMERS", source)
        self.assertIn("Capability.VIEW_EDGE_BANDING_TYPES", source)
        self.assertIn("Capability.CREATE_ORDER", source)
        self.assertIn("Capability.CREATE_EDGE_BANDING_TYPES", source)
        self.assertIn("Capability.CREATE_CUSTOMERS", source)
        self.assertIn("repository.save_role_state(role, state)", source)
        self.assertNotIn("Custom DocPerm", source)
        self.assertNotIn("DocPerm", source)


if __name__ == "__main__":
    unittest.main()
