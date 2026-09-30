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
GATEWAY = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "authorization_gateway.py"
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

    def test_matrix_and_gateway_read_custom_docperm_grant_reader(self) -> None:
        matrix = MATRIX_REPOSITORY.read_text(encoding="utf-8")
        gateway = GATEWAY.read_text(encoding="utf-8")
        role_state = matrix[
            matrix.index("    def role_state(") : matrix.index("    def role_states(")
        ]
        self.assertIn("self._grant_reader.role_state", role_state)
        self.assertNotIn("self._canonical.read", role_state)
        self.assertIn("CustomDocPermCapabilityReader", matrix)
        self.assertIn("dual-write", matrix)
        self.assertIn("_capability_grant_reader", gateway)
        self.assertIn("reader.role_capabilities", gateway)
        self.assertNotIn('repository.role_state(role)["capabilities"]', gateway)

    def test_missing_canonical_state_bootstraps_deny_all_only(self) -> None:
        canonical = CANONICAL_REPOSITORY.read_text(encoding="utf-8")
        sync = SYNC.read_text(encoding="utf-8")
        self.assertIn("latest_audited_state", canonical)
        self.assertIn("historical inspection only", canonical)
        self.assertIn("bootstrap_fail_closed", canonical)
        start = canonical.index("    def bootstrap_fail_closed(")
        end = canonical.index("\n\n__all__", start)
        bootstrap = canonical[start:end]
        self.assertIn("return self.save(resolved, {})", bootstrap)
        self.assertNotIn("latest_audited_state", bootstrap)
        self.assertNotIn("AUDIT_DOCTYPE", bootstrap)
        self.assertNotIn('frappe.get_all("DocPerm"', bootstrap)
        self.assertNotIn('frappe.get_all("Custom DocPerm"', bootstrap)
        self.assertNotIn('frappe.db.get_value("DocPerm"', bootstrap)
        self.assertNotIn('frappe.db.get_value("Custom DocPerm"', bootstrap)
        self.assertIn("canonical.bootstrap_fail_closed", sync)
        self.assertIn("save_role_states(prepared)", sync)

    def test_standard_baseline_cannot_import_custom_business_fields(self) -> None:
        source = MATRIX_REPOSITORY.read_text(encoding="utf-8")
        self.assertIn("_BUSINESS_PERMISSION_FIELDS", source)
        self.assertIn("payload[fieldname] = 0", source)
        self.assertIn("Copy native Frappe rights while dropping legacy business fields", source)


if __name__ == "__main__":
    unittest.main()
