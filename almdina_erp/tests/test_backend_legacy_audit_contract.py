from __future__ import annotations

import json
import runpy
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "almdina_erp"
INVENTORY_PATH = APP_ROOT / "backend_legacy_inventory.json"
MIGRATIONS_PATH = APP_ROOT / "backend_legacy_migrations.json"
HOOKS_PATH = APP_ROOT / "hooks.py"


def _inventory() -> dict:
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


def _migrations() -> dict:
    return json.loads(MIGRATIONS_PATH.read_text(encoding="utf-8"))


def _removed_paths() -> set[str]:
    return {
        path
        for migration in _migrations()["migrations"]
        if migration["status"] == "removed"
        for path in migration["paths"]
    }


class TestBackendLegacyAuditContract(unittest.TestCase):
    def test_inventory_is_explicit_disjoint_and_tracks_migrated_sources(self) -> None:
        audit = _inventory()
        self.assertEqual(audit["version"], 1)
        self.assertEqual(
            audit["baseline_develop_sha"],
            "453c000240b574b9739fc46ba392c17c42b766c9",
        )
        migrations = _migrations()
        self.assertEqual(migrations["version"], 1)
        self.assertEqual(
            migrations["baseline_develop_sha"],
            "9bbd00fd197042991a3e4cc042c5ab668e25431a",
        )
        classifications = audit["classifications"]
        self.assertEqual(
            set(classifications),
            {"active", "compatibility", "legacy", "dead"},
        )

        removed = _removed_paths()
        self.assertTrue(removed)
        seen: dict[str, str] = {}
        for classification in ("active", "compatibility", "legacy"):
            self.assertTrue(classifications[classification], classification)
            for entry in classifications[classification]:
                path = entry["path"]
                self.assertNotIn(path, seen, f"{path} also classified as {seen.get(path)}")
                seen[path] = classification
                self.assertTrue(entry.get("evidence"), path)
                self.assertTrue(entry.get("stage11_action"), path)
                if path in removed:
                    self.assertEqual(classification, "legacy", path)
                    self.assertFalse((REPO_ROOT / path).exists(), path)
                else:
                    self.assertTrue((REPO_ROOT / path).is_file(), path)

        self.assertEqual(classifications["dead"], [])
        for path in removed:
            self.assertIn(path, seen)

    def test_only_thin_controller_is_the_active_frappe_override(self) -> None:
        hooks = runpy.run_path(str(HOOKS_PATH))
        active = (
            "almdina_erp.almdina_erp.doctype.door_cutting_order."
            "door_cutting_order_controller.DoorCuttingOrderController"
        )
        self.assertEqual(
            hooks["override_doctype_class"]["Door Cutting Order"],
            active,
        )
        source = (
            APP_ROOT
            / "almdina_erp"
            / "doctype"
            / "door_cutting_order"
            / "door_cutting_order_controller.py"
        ).read_text(encoding="utf-8")
        self.assertIn("class DoorCuttingOrderController(DoorCuttingOrder)", source)
        self.assertIn("process_order_save(self._gateway())", source)
        for alternate in (
            "FastDoorCuttingOrder",
            "TextBoardDoorCuttingOrder",
            "DomainDoorCuttingOrder",
        ):
            self.assertNotIn(alternate, source)

    def test_removed_controller_chain_has_zero_runtime_python_consumers(self) -> None:
        removed = _removed_paths()
        expected = {
            "almdina_erp/almdina_erp/doctype/door_cutting_order/door_cutting_order_fast.py",
            "almdina_erp/almdina_erp/doctype/door_cutting_order/door_cutting_order_text_board.py",
            "almdina_erp/almdina_erp/doctype/door_cutting_order/door_cutting_order_domain.py",
        }
        self.assertTrue(expected.issubset(removed))
        for relative in expected:
            self.assertFalse((REPO_ROOT / relative).exists(), relative)

        runtime_root = APP_ROOT / "almdina_erp"
        forbidden = (
            "door_cutting_order_fast",
            "door_cutting_order_text_board",
            "door_cutting_order_domain",
            "FastDoorCuttingOrder",
            "TextBoardDoorCuttingOrder",
            "DomainDoorCuttingOrder",
        )
        offenders: list[str] = []
        for path in sorted(runtime_root.rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in source:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {token}")
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_public_compatibility_routes_are_frozen_to_canonical_targets(self) -> None:
        audit = _inventory()
        hooks = runpy.run_path(str(HOOKS_PATH))
        actual = hooks["override_whitelisted_methods"]
        expected = audit["public_api_contract"]["compatibility_overrides"]
        for source, target in expected.items():
            with self.subTest(source=source):
                self.assertEqual(actual.get(source), target)

    def test_retired_product_routes_remain_fail_closed(self) -> None:
        audit = _inventory()
        hooks = runpy.run_path(str(HOOKS_PATH))
        actual = hooks["override_whitelisted_methods"]
        target = audit["public_api_contract"]["retired_target"]
        retired_sources = audit["public_api_contract"]["retired_sources"]
        self.assertGreaterEqual(len(retired_sources), 10)
        for source in retired_sources:
            with self.subTest(source=source):
                self.assertEqual(actual.get(source), target)

        boundary = (
            APP_ROOT / "almdina_erp" / "services" / "legacy_endpoint_service.py"
        ).read_text(encoding="utf-8")
        self.assertIn("def retired_product_endpoint", boundary)
        self.assertIn("frappe.ValidationError", boundary)
        self.assertIn("def start_legacy_stage", boundary)
        self.assertIn("def finish_legacy_stage", boundary)

    def test_known_compatibility_modules_do_not_regain_business_ownership(self) -> None:
        services = APP_ROOT / "almdina_erp" / "services"
        infrastructure = APP_ROOT / "almdina_erp" / "infrastructure"

        cutting = (services / "cutting_engine.py").read_text(encoding="utf-8")
        optimizer = (services / "advanced_cutting_optimizer.py").read_text(
            encoding="utf-8"
        )
        legacy_engine = (
            infrastructure / "cutting" / "legacy_engine.py"
        ).read_text(encoding="utf-8")
        shop_floor = (services / "shop_floor_service.py").read_text(encoding="utf-8")
        gateway = (
            infrastructure / "frappe" / "shop_floor_gateway.py"
        ).read_text(encoding="utf-8")
        replacement = (services / "replacement_service.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("domain.cutting import *", cutting)
        self.assertNotIn("def optimize", cutting)
        self.assertIn("domain.cutting.optimizer import *", optimizer)
        self.assertNotIn("def optimize_plan", optimizer)
        self.assertIn("LegacyCuttingEngineAdapter = DomainCuttingEngineAdapter", legacy_engine)
        self.assertIn("Backward-compatible shop-floor API facade", shop_floor)
        self.assertIn("_public_delegate", shop_floor)
        self.assertNotIn("frappe.db", shop_floor)
        self.assertIn("Backward-compatible facade", gateway)
        self.assertIn("_legacy_role_gate_removed()", gateway)
        self.assertNotIn("frappe.get_roles", gateway)
        self.assertIn("Backward-compatible replacement API facade", replacement)
        self.assertNotIn("frappe.db.", replacement)
        self.assertNotIn("frappe.get_doc", replacement)

    def test_unmigrated_legacy_boundaries_stay_visible_for_stage_11(self) -> None:
        audit = _inventory()
        removed = _removed_paths()
        legacy = {
            entry["path"]
            for entry in audit["classifications"]["legacy"]
            if entry["path"] not in removed
        }
        expected = {
            "almdina_erp/almdina_erp/doctype/door_cutting_order/door_cutting_order.py",
            "almdina_erp/almdina_erp/services/cutting_plan_service.py",
            "almdina_erp/almdina_erp/services/production_service.py",
            "almdina_erp/almdina_erp/services/order_creation_service.py",
            "almdina_erp/almdina_erp/services/replacement_cancellation_service.py",
            "almdina_erp/almdina_erp/services/stock_service.py",
            "almdina_erp/almdina_erp/services/remnant_service.py",
        }
        self.assertTrue(expected.issubset(legacy))

        plan_service = (
            APP_ROOT / "almdina_erp" / "services" / "cutting_plan_service.py"
        ).read_text(encoding="utf-8")
        self.assertIn("def create_plan_from_order", plan_service)
        self.assertIn("def submit_order_for_review", plan_service)
        self.assertIn("order_lifecycle_permission_service", plan_service)
        self.assertIn("order_approval_service", plan_service)

    def test_stage_11_sequence_preserves_compatibility_before_deletion(self) -> None:
        audit = _inventory()
        steps = audit["stage11_order"]
        self.assertGreaterEqual(len(steps), 6)
        joined = "\n".join(steps)
        for boundary in (
            "Controller chain",
            "Cutting imports",
            "Cutting plan",
            "Shop floor",
            "Replacement",
            "Retired product modules",
        ):
            self.assertIn(boundary, joined)
        rules = "\n".join(audit["rules"])
        self.assertIn("Do not delete a compatibility path", rules)
        self.assertIn("fail-closed", rules)
        self.assertIn("DEAD requires positive evidence", rules)


if __name__ == "__main__":
    unittest.main()
