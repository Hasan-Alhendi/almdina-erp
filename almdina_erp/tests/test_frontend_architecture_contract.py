from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT.parent / "docs" / "reference"
FRONTEND_ARCH = REFERENCE / "13_FRONTEND_ARCHITECTURE.md"
GLOBAL_ARCH = REFERENCE / "02_ARCHITECTURE.md"
REFERENCE_INDEX = REFERENCE / "README.md"
DCO_FRONTEND_ARCH = ROOT / "public" / "js" / "door_cutting_order" / "ARCHITECTURE.md"
FRONTEND_ASSET_MANIFEST = ROOT / "frontend_assets.py"
DOCUMENTATION = ROOT / "public" / "js" / "special_shape_documentation"

REQUIRED_RULE_IDS = tuple(f"FE-ARCH-{index:03d}" for index in range(1, 16))
DOCUMENTATION_LAYERS = ("domain", "application", "infrastructure", "presentation")


class TestFrontendArchitectureContract(unittest.TestCase):
    def test_frontend_reference_is_canonical_and_discoverable(self) -> None:
        self.assertTrue(FRONTEND_ARCH.is_file())
        frontend = FRONTEND_ARCH.read_text(encoding="utf-8")
        architecture = GLOBAL_ARCH.read_text(encoding="utf-8")
        index = REFERENCE_INDEX.read_text(encoding="utf-8")

        self.assertIn("13_FRONTEND_ARCHITECTURE.md", architecture)
        self.assertIn("13_FRONTEND_ARCHITECTURE.md", index)
        self.assertIn("Canonical frontend specialization", frontend)
        self.assertIn("02 — Architecture", frontend)
        self.assertIn("Architecture Freeze", frontend)

    def test_all_normative_frontend_rules_are_present_once(self) -> None:
        source = FRONTEND_ARCH.read_text(encoding="utf-8")

        for rule_id in REQUIRED_RULE_IDS:
            self.assertEqual(
                source.count(f"`{rule_id}`"),
                1,
                f"Frontend architecture rule must exist exactly once: {rule_id}",
            )

    def test_contract_keeps_server_authority_and_role_names_out_of_ui_authorization(self) -> None:
        source = FRONTEND_ARCH.read_text(encoding="utf-8")

        self.assertIn("Server authorization is authoritative", source)
        self.assertIn("إخفاء زر في المتصفح UX فقط وليس Security boundary", source)
        self.assertIn("frappe.user_roles", source)
        self.assertIn("System Manager", source)
        self.assertIn("لا يقرر lifecycle أو authorization", source)
        self.assertIn("لا تنسخ قواعد lifecycle أو authorization", source)

    def test_contract_requires_state_async_and_lifecycle_ownership(self) -> None:
        source = FRONTEND_ARCH.read_text(encoding="utf-8")

        for marker in (
            "مالك واحد",
            "requestId",
            "latest-wins",
            "AlmdinaDocumentContext",
            "MutationObserver",
            "idempotent",
            "dispose",
            "stale-response",
        ):
            self.assertIn(marker, source)

    def test_contract_requires_professional_arabic_responsive_accessible_ux(self) -> None:
        source = FRONTEND_ARCH.read_text(encoding="utf-8")

        for marker in (
            "Arabic-first",
            "RTL",
            "keyboard",
            "touch",
            "responsive",
            "prefers-reduced-motion",
            "loading/error/empty/disabled/dirty",
            "Input safety",
        ):
            self.assertIn(marker, source)

    def test_structural_refactor_is_separated_from_visual_and_business_changes(self) -> None:
        source = FRONTEND_ARCH.read_text(encoding="utf-8")

        self.assertIn("Structural refactors are visually neutral first", source)
        self.assertIn("refactor + redesign + business change", source)
        self.assertIn("extraction أولًا", source)
        self.assertIn("behavior/security/lifecycle contracts بقيت دون تغيير", source)

    def test_existing_dco_frontend_boundary_remains_the_owner_contract(self) -> None:
        self.assertTrue(DCO_FRONTEND_ARCH.is_file())
        self.assertTrue(FRONTEND_ASSET_MANIFEST.is_file())

        source = FRONTEND_ARCH.read_text(encoding="utf-8")
        dco = DCO_FRONTEND_ARCH.read_text(encoding="utf-8")

        self.assertIn("public/js/door_cutting_order/ARCHITECTURE.md", source)
        self.assertIn("almdina_erp/frontend_assets.py", source)
        self.assertIn("Asset ordering is runtime-significant", dco)
        self.assertIn("Explicit dual-load allowlist", dco)
        self.assertIn("Put new behavior under exactly one feature owner", dco)

    def test_special_shape_documentation_stays_a_bounded_layered_subsystem(self) -> None:
        source = FRONTEND_ARCH.read_text(encoding="utf-8")

        self.assertIn("Special Shape Documentation", source)
        self.assertIn("domain/application/infrastructure/presentation", source)
        for layer in DOCUMENTATION_LAYERS:
            self.assertTrue(
                (DOCUMENTATION / layer).is_dir(),
                f"Special Shape Documentation layer disappeared: {layer}",
            )

    def test_contract_does_not_turn_file_size_into_an_architecture_rule(self) -> None:
        source = FRONTEND_ARCH.read_text(encoding="utf-8")

        self.assertIn("cohesion + ownership + testability", source)
        self.assertNotIn("300 lines", source)
        self.assertNotIn("500 lines", source)

    def test_migration_sequence_is_explicit_and_progressive(self) -> None:
        source = FRONTEND_ARCH.read_text(encoding="utf-8")

        positions = [source.index(f"**F{stage} —") for stage in range(2, 8)]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("Minimal Shared Foundation", source)
        self.assertIn("Admin Frontend Family", source)
        self.assertIn("Shop Floor", source)
        self.assertIn("DCO Targeted Cleanup", source)
        self.assertIn("Frontend Quality Gate", source)


if __name__ == "__main__":
    unittest.main()
