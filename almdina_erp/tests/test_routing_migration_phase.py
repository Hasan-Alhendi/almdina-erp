from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCHES_FILE = ROOT / "patches.txt"
ROUTING_PATCH = "almdina_erp.patches.v1_0.activate_configurable_production_routings"
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
    def test_routing_activation_runs_after_model_sync(self) -> None:
        self.assertEqual(patch_section(ROUTING_PATCH), "post_model_sync")

    def test_new_route_columns_are_declared_in_both_doctypes(self) -> None:
        required = {"department_label", "operational_role"}
        for path in (ROUTING_STAGE_JSON, PRODUCTION_STAGE_JSON):
            payload = json.loads(path.read_text(encoding="utf-8"))
            fields = {row["fieldname"] for row in payload.get("fields", [])}
            self.assertTrue(required.issubset(fields), f"Missing route fields in {path}")


if __name__ == "__main__":
    unittest.main()
