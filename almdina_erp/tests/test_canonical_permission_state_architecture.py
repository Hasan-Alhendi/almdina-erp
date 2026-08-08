from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_REPOSITORY = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "canonical_permission_state_repository.py"
)
MATRIX_REPOSITORY = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "permission_matrix_repository.py"
)
SYNC = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "permission_type_sync.py"
)
STATE_DOCTYPE = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "almdina_role_capability_state"
    / "almdina_role_capability_state.json"
)


class TestCanonicalPermissionStateArchitecture(unittest.TestCase):
    def test_internal_state_doctype_is_not_exposed_to_desk_roles(self) -> None:
        metadata = json.loads(STATE_DOCTYPE.read_text(encoding="utf-8"))
        self.assertEqual(metadata["name"], "Almdina Role Capability State")
        self.assertEqual(metadata["permissions"], [])
        self.assertEqual(metadata["autoname"], "field:role")
        fields = {row["fieldname"]: row for row in metadata["fields"]}
        self.assertTrue(fields["role"]["unique"])
        self.assertTrue(fields["capabilities_json"]["read_only"])

    def test_matrix_role_state_reads_canonical_store_only(self) -> None:
        source = MATRIX_REPOSITORY.read_text(encoding="utf-8")
        role_state = source[source.index("    def role_state("):source.index("    def role_states(")]
        self.assertIn("self._canonical.read", role_state)
        self.assertIn("self._canonical.exists", role_state)
        self.assertNotIn("DocPerm", role_state)
        self.assertNotIn("Custom DocPerm", role_state)
        self.assertNotIn("_effective_rows", source)
        self.assertIn("DocPerm and Custom DocPerm are write-only projections", source)

    def test_legacy_projection_bootstrap_uses_audit_or_deny_all(self) -> None:
        canonical = CANONICAL_REPOSITORY.read_text(encoding="utf-8")
        sync = SYNC.read_text(encoding="utf-8")
        self.assertIn("latest_audited_state", canonical)
        self.assertIn("bootstrap_fail_closed", canonical)
        self.assertIn("audited if audited is not None else {}", canonical)
        bootstrap = canonical[canonical.index("    def bootstrap_fail_closed"):]
        self.assertNotIn('frappe.get_all("DocPerm"', bootstrap)
        self.assertNotIn('frappe.get_all("Custom DocPerm"', bootstrap)
        self.assertNotIn('frappe.db.get_value("DocPerm"', bootstrap)
        self.assertNotIn('frappe.db.get_value("Custom DocPerm"', bootstrap)
        self.assertIn("canonical.bootstrap_fail_closed", sync)
        self.assertIn("Project", sync)
        self.assertIn("save_role_states(prepared)", sync)

    def test_standard_baseline_cannot_import_custom_business_fields(self) -> None:
        source = MATRIX_REPOSITORY.read_text(encoding="utf-8")
        self.assertIn("_BUSINESS_PERMISSION_FIELDS", source)
        self.assertIn("payload[fieldname] = 0", source)
        self.assertIn("Copy native Frappe rights while dropping legacy business fields", source)


if __name__ == "__main__":
    unittest.main()
