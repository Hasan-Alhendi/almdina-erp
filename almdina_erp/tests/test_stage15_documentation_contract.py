from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE = REPO_ROOT / "docs" / "reference"
RUNTIME_BASELINE = "75dba93dd7dd9b21b4aeb4e32113c7e7061e748e"

REQUIRED_REFERENCE_DOCS = (
    "README.md",
    "01_SYSTEM_OVERVIEW.md",
    "02_ARCHITECTURE.md",
    "03_WORKFLOWS.md",
    "04_SECURITY_PERMISSIONS.md",
    "05_CUTTING_DRAWING_DXF.md",
    "06_DATA_UI_MAP.md",
    "07_CHANGE_RULES.md",
    "08_TESTING_QUALITY.md",
    "09_OPERATIONS_RELEASE.md",
    "10_GLOSSARY.md",
    "11_COMMON_TASKS.md",
    "12_TROUBLESHOOTING.md",
    "ARCHITECTURE_FREEZE.md",
)


class TestStage15DocumentationContract(unittest.TestCase):
    def test_canonical_reference_set_exists_and_is_nontrivial(self) -> None:
        missing: list[str] = []
        too_small: list[str] = []
        for name in REQUIRED_REFERENCE_DOCS:
            path = REFERENCE / name
            if not path.exists():
                missing.append(name)
                continue
            if len(path.read_text(encoding="utf-8").strip()) < 500:
                too_small.append(name)
        self.assertEqual(missing, [], f"Missing canonical docs: {missing}")
        self.assertEqual(too_small, [], f"Canonical docs unexpectedly small: {too_small}")

    def test_root_readme_and_agents_route_readers_to_canonical_reference(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        docs_index = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")

        self.assertIn("docs/reference/README.md", readme)
        self.assertIn("docs/PRODUCT_SCOPE_v1.1.md", readme)
        self.assertIn("docs/reference/11_COMMON_TASKS.md", readme)
        self.assertIn("docs/reference/12_TROUBLESHOOTING.md", readme)
        self.assertIn("docs/reference/07_CHANGE_RULES.md", agents)
        self.assertIn("reference/ARCHITECTURE_FREEZE.md", docs_index)

    def test_architecture_reference_names_the_enforced_inward_boundaries(self) -> None:
        source = (REFERENCE / "02_ARCHITECTURE.md").read_text(encoding="utf-8")
        for layer in ("domain/", "application/", "infrastructure/", "services/"):
            self.assertIn(layer, source)
        self.assertIn("Domain Framework-free", source)
        self.assertIn("Application Framework-free", source)

    def test_security_reference_preserves_capability_and_financial_contracts(self) -> None:
        source = (REFERENCE / "04_SECURITY_PERMISSIONS.md").read_text(encoding="utf-8")
        self.assertIn("Capability", source)
        self.assertIn("System Manager", source)
        self.assertIn("Administrator", source)
        self.assertIn("view_costs", source)
        self.assertIn("IDOR", source)
        self.assertIn("fail_closed", source)

    def test_workflow_reference_records_current_dispatch_and_planning_contract(self) -> None:
        source = (REFERENCE / "03_WORKFLOWS.md").read_text(encoding="utf-8")
        for value in ("Draft", "Drawing", "CNC", "Sanding", "Ready for Delivery", "Delivered"):
            self.assertIn(value, source)
        self.assertIn("Review/Approve القديم", source)
        self.assertIn("اعتماد Cutting Plan", source)

    def test_operational_reference_covers_common_admin_and_factory_tasks(self) -> None:
        source = (REFERENCE / "11_COMMON_TASKS.md").read_text(encoding="utf-8")
        for value in (
            "Door Cutting Order",
            "Cutting Plan",
            "dispatch_order",
            "shop_floor_inbox",
            "Production Routing",
            "factory_permissions",
            "factory_workforce",
            "Incident",
            "Replacement",
        ):
            self.assertIn(value, source)

    def test_troubleshooting_reference_requires_evidence_before_broad_fix(self) -> None:
        source = (REFERENCE / "12_TROUBLESHOOTING.md").read_text(encoding="utf-8")
        for value in ("Exact Git SHA", "DCO", "assignee", "IDOR", "view_costs", "DXF"):
            self.assertIn(value, source)
        self.assertIn("لا hard-code", source)
        self.assertIn("Architecture Freeze", source)

    def test_scope_and_freeze_reject_inventory_as_new_active_product_authority(self) -> None:
        overview = (REFERENCE / "01_SYSTEM_OVERVIEW.md").read_text(encoding="utf-8")
        freeze = (REFERENCE / "ARCHITECTURE_FREEZE.md").read_text(encoding="utf-8")
        self.assertIn("PRODUCT_SCOPE_v1.1.md", overview)
        self.assertIn("Board Remnant", freeze)
        self.assertIn("ليس جزءًا من Active Scope", freeze)

    def test_freeze_is_pinned_to_the_stage14_runtime_baseline(self) -> None:
        freeze = (REFERENCE / "ARCHITECTURE_FREEZE.md").read_text(encoding="utf-8")
        root = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(RUNTIME_BASELINE, freeze)
        self.assertIn(RUNTIME_BASELINE, root)
        self.assertIn("Targeted Feature Development", freeze)
        self.assertIn("ADR", freeze)


if __name__ == "__main__":
    unittest.main()
