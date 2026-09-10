from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCHES_FILE = ROOT / "patches.txt"
ROUTING_PATCH = "almdina_erp.patches.v1_0.activate_configurable_production_routings"
STAGE_LIBRARY_PATCH = "almdina_erp.patches.v1_0.migrate_production_stage_library"
ROUTING_STAGE_JSON = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "production_routing_stage"
    / "production_routing_stage.json"
)
PRODUCTION_STAGE_JSON = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "production_stage"
    / "production_stage.json"
)
STAGE_DEFINITION_JSON = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "production_stage_definition"
    / "production_stage_definition.json"
)


def patch_section(target: str) -> str:
    section = "pre_model_sync"
    for raw_line in PATCHES_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if line.split("#", 1)[0].strip() == target:
            return section
    raise AssertionError(f"Patch is not registered: {target}")


class TestRoutingMigrationPhase(unittest.TestCase):
    def test_existing_routing_activation_still_runs_after_model_sync(self) -> None:
        self.assertEqual(patch_section(ROUTING_PATCH), "post_model_sync")

    def test_stage_library_backfill_runs_after_model_sync(self) -> None:
        self.assertEqual(patch_section(STAGE_LIBRARY_PATCH), "post_model_sync")

    def test_routing_configuration_references_stage_library_and_runtime_keeps_snapshot(self) -> None:
        route_payload = json.loads(ROUTING_STAGE_JSON.read_text(encoding="utf-8"))
        runtime_payload = json.loads(PRODUCTION_STAGE_JSON.read_text(encoding="utf-8"))
        definition_payload = json.loads(STAGE_DEFINITION_JSON.read_text(encoding="utf-8"))

        route_fields = {row["fieldname"]: row for row in route_payload.get("fields", [])}
        runtime_fields = {
            row["fieldname"]: row for row in runtime_payload.get("fields", [])
        }
        definition_fields = {
            row["fieldname"]: row for row in definition_payload.get("fields", [])
        }

        self.assertEqual(route_fields["stage_definition"]["fieldtype"], "Link")
        self.assertEqual(
            route_fields["stage_definition"]["options"], "Production Stage Definition"
        )
        self.assertEqual(route_fields["operational_role"]["options"], "Role")
        self.assertNotIn("stage_type", route_fields)
        self.assertNotIn("department_label", route_fields)

        self.assertTrue(
            {"stage_type", "department_label", "operational_role"}.issubset(
                runtime_fields
            )
        )
        self.assertTrue(
            {"stage_code", "stage_label", "disabled"}.issubset(definition_fields)
        )


if __name__ == "__main__":
    unittest.main()
