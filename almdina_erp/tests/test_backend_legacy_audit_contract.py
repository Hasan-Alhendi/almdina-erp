from __future__ import annotations

import json
import runpy
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "almdina_erp"
INVENTORY_PATH = APP_ROOT / "backend_legacy_inventory.json"
HOOKS_PATH = APP_ROOT / "hooks.py"


def _inventory() -> dict:
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


class TestBackendLegacyAuditContract(unittest.TestCase):
    def test_inventory_is_explicit_disjoint_and_points_to_real_sources(self) -> None:
        audit = _inventory()
        self.assertEqual(audit["version"], 1)
        self.assertEqual(
            audit["baseline_develop_sha"],
            "453c000240b574b9739fc46ba392c17c42b766c9",
        )
        classifications = audit["classifications"]
        self.assertEqual(
            set(classifications),
            {"active", "compatibility", "legacy", "dead"},
        )

        seen: dict[str, str] = {}
        for classification in ("active", "compatibility", "legacy"):
            self.assertTrue(classifications[classification], classification)
            for entry in classifications[classification]:
                path = entry["path"]
                self.assertNotIn(path, seen, f"{path} also classified as {seen.get(path)}")
                seen[path] = classification
                self.assertTrue((REPO_ROOT / path).is_file(), path)
                self.assertTrue(entry.get("evidence"), path)
                self.assertTrue(entry.get("stage11_action"), path)

        # No source met the stronger DEAD bar: zero hooks, HTTP, Python imports
        # and tests. Stage 11 may add entries only after proving all four.
        self.assertEqual(classifications["dead"], [])

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

    def test_mixed_legacy_boundaries_stay_visible_for_stage_11(self) -> None:
        audit = _inventory()
        legacy = {entry["path"] for entry in audit["classifications"]["legacy"]}
        expected = {
            "almdina_erp/almdina_erp/doctype/door_cutting_order/door_cutting_order.py",
            "almdina_erp/almdina_erp/doctype/door_cutting_order/door_cutting_order_fast.py",
            "almdina_erp/almdina_erp/doctype/door_cutting_order/door_cutting_order_text_board.py",
            "almdina_erp/almdina_erp/doctype/door_cutting_order/door_cutting_order_domain.py",
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
