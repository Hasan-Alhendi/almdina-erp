from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IGNORE_RE = re.compile(r"ignore_permissions\s*=\s*True")

# Production call sites reviewed during the Frappe-native permission cutover.
# SAFE — preceding service/command already enforced capability + document scope.
# MIGRATION — install/sync/metadata path not exposed as an end-user RPC grant.
# LEGACY_INACTIVE — boarded/retired product surfaces kept for migrate compatibility.
#
# Adding a new production ignore_permissions=True requires an entry here and a
# short justification in the PR. Do not delete bypasses automatically.
_REVIEWED_SITES: dict[str, str] = {
    "install.py": "MIGRATION",
    "almdina_erp/doctype/board_remnant/board_remnant.py": "LEGACY_INACTIVE",
    "almdina_erp/infrastructure/frappe/canonical_permission_state_repository.py": "MIGRATION",
    "almdina_erp/infrastructure/frappe/cutting_plan_surface_metadata.py": "SAFE",
    "almdina_erp/infrastructure/frappe/master_data_audit.py": "SAFE",
    "almdina_erp/infrastructure/frappe/notes_repository.py": "SAFE",
    "almdina_erp/infrastructure/frappe/order_cost_surface_metadata.py": "SAFE",
    "almdina_erp/infrastructure/frappe/order_status_metadata.py": "SAFE",
    "almdina_erp/infrastructure/frappe/permission_matrix_repository.py": "SAFE",
    "almdina_erp/infrastructure/frappe/permission_type_sync.py": "MIGRATION",
    "almdina_erp/infrastructure/frappe/production_event_repository.py": "SAFE",
    "almdina_erp/infrastructure/frappe/production_routing_management_repository.py": "SAFE",
    "almdina_erp/infrastructure/frappe/production_stage_definition_repository.py": "SAFE",
    "almdina_erp/infrastructure/frappe/production_stage_repository.py": "SAFE",
    "almdina_erp/infrastructure/frappe/supporting_doctype_permission_repository.py": "SAFE",
    "almdina_erp/infrastructure/frappe/workforce_repository.py": "SAFE",
    "almdina_erp/services/archive_service.py": "SAFE",
    "almdina_erp/services/cost_permission_service.py": "SAFE",
    "almdina_erp/services/order_lifecycle_permission_service.py": "SAFE",
    "almdina_erp/services/order_lifecycle_service.py": "SAFE",
    "almdina_erp/services/order_revision_activation.py": "SAFE",
    "almdina_erp/services/order_revision_service.py": "SAFE",
    "almdina_erp/services/production_settings_service.py": "SAFE",
    "almdina_erp/services/production_stage_bootstrap_service.py": "SAFE",
    "almdina_erp/services/special_shape_service.py": "SAFE",
}


def _iter_production_python() -> list[Path]:
    skip_parts = {"tests", "__pycache__", "patches"}
    return sorted(
        path
        for path in ROOT.rglob("*.py")
        if not any(part in skip_parts for part in path.parts)
    )


class TestIgnorePermissionsAuditContract(unittest.TestCase):
    def test_production_ignore_permissions_sites_are_reviewed(self) -> None:
        found: set[str] = set()
        for path in _iter_production_python():
            if IGNORE_RE.search(path.read_text(encoding="utf-8")):
                found.add(path.relative_to(ROOT).as_posix())

        self.assertEqual(
            found,
            set(_REVIEWED_SITES),
            "ignore_permissions inventory drifted.\n"
            f"new={sorted(found - set(_REVIEWED_SITES))}\n"
            f"removed={sorted(set(_REVIEWED_SITES) - found)}",
        )
        self.assertTrue(set(_REVIEWED_SITES.values()) <= {"SAFE", "MIGRATION", "LEGACY_INACTIVE"})

    def test_permission_persistence_bypass_is_not_capability_authority(self) -> None:
        source = (
            ROOT
            / "almdina_erp"
            / "infrastructure"
            / "frappe"
            / "permission_matrix_repository.py"
        ).read_text(encoding="utf-8")
        self.assertIn("ignore_permissions=True", source)
        self.assertIn("CustomDocPermCapabilityReader", source)
        self.assertNotIn("CanonicalPermissionStateRepository", source)
        self.assertNotIn("has_permission(", source.split("def role_state(")[1].split("def role_states(")[0])


if __name__ == "__main__":
    unittest.main()
