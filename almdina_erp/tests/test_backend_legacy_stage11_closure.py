from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "almdina_erp"
INVENTORY_PATH = APP_ROOT / "backend_legacy_inventory.json"
MIGRATIONS_PATH = APP_ROOT / "backend_legacy_migrations.json"

RETAINED_STAGE10_BOUNDARIES = {
    "almdina_erp/almdina_erp/doctype/door_cutting_order/door_cutting_order.py",
    "almdina_erp/almdina_erp/services/cutting_plan_service.py",
    "almdina_erp/almdina_erp/services/production_service.py",
    "almdina_erp/almdina_erp/services/order_creation_service.py",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _stage10_legacy_paths() -> set[str]:
    return {
        entry["path"]
        for entry in _load(INVENTORY_PATH)["classifications"]["legacy"]
    }


def _removed_paths() -> set[str]:
    return {
        path
        for migration in _load(MIGRATIONS_PATH)["migrations"]
        if migration["status"] == "removed"
        for path in migration["paths"]
    }


def _stage11_discoveries() -> set[str]:
    return {
        path
        for migration in _load(MIGRATIONS_PATH)["migrations"]
        for path in migration.get("stage11_discoveries", [])
    }


class TestBackendLegacyStage11Closure(unittest.TestCase):
    def test_stage10_legacy_inventory_is_fully_partitioned(self) -> None:
        legacy = _stage10_legacy_paths()
        removed = _removed_paths()
        removed_stage10 = legacy & removed

        self.assertEqual(len(legacy), 16)
        self.assertEqual(len(removed_stage10), 12)
        self.assertTrue(removed_stage10.isdisjoint(RETAINED_STAGE10_BOUNDARIES))
        self.assertEqual(
            legacy,
            removed_stage10 | RETAINED_STAGE10_BOUNDARIES,
        )

        for path in sorted(removed_stage10):
            with self.subTest(removed=path):
                self.assertFalse((REPO_ROOT / path).exists())
        for path in sorted(RETAINED_STAGE10_BOUNDARIES):
            with self.subTest(retained=path):
                self.assertTrue((REPO_ROOT / path).is_file())

    def test_stage11_discoveries_are_recorded_and_absent(self) -> None:
        legacy = _stage10_legacy_paths()
        removed = _removed_paths()
        discoveries = _stage11_discoveries()
        expected = {
            "almdina_erp/almdina_erp/doctype/door_cutting_order/door_cutting_order_costing.py",
            "almdina_erp/almdina_erp/doctype/door_cutting_order/door_cutting_order_plan.py",
            "almdina_erp/almdina_erp/infrastructure/frappe/stock_execution_gateway.py",
            "almdina_erp/almdina_erp/infrastructure/frappe/remnant_execution_gateway.py",
        }
        self.assertEqual(discoveries, expected)
        for path in discoveries:
            self.assertNotIn(path, legacy)
            self.assertIn(path, removed)
            self.assertFalse((REPO_ROOT / path).exists())

    def test_final_batch_evidence_is_frozen_in_migration_ledger(self) -> None:
        migrations = {
            migration["batch"]: migration
            for migration in _load(MIGRATIONS_PATH)["migrations"]
        }
        self.assertEqual(set(migrations), set(range(1, 9)))
        self.assertEqual(
            migrations[6]["final_sha"],
            "a593a46d636d349e416b74d1162837b885e21cbb",
        )
        self.assertEqual(
            migrations[7]["final_sha"],
            "6417c554f50b6caf2a1352bbb8c6c5fc74c62c90",
        )
        self.assertEqual(
            migrations[8]["final_sha"],
            "6cb20b00abdd92434a2f2ca5f5d4c3fd65753a79",
        )
        self.assertEqual(
            migrations[7]["status"],
            "migrated_compatibility_preserved",
        )
        self.assertEqual(
            migrations[8]["status"],
            "migrated_compatibility_preserved",
        )

    def test_retained_dco_base_is_framework_and_delegate_only(self) -> None:
        source = (
            APP_ROOT
            / "almdina_erp"
            / "doctype"
            / "door_cutting_order"
            / "door_cutting_order.py"
        ).read_text(encoding="utf-8")
        self.assertLess(len(source.splitlines()), 190)
        self.assertIn("class DoorCuttingOrder(Document)", source)
        self.assertIn("process_order_save(self._gateway())", source)
        self.assertIn("FrappeOrderPlanAdapter", source)
        self.assertNotIn("from almdina_erp.almdina_erp.domain.cutting import", source)
        self.assertNotIn("frappe.db", source)
        self.assertNotIn("optimize_plan(", source)

    def test_retained_cutting_plan_boundary_is_only_a_compatibility_facade(self) -> None:
        source = (
            APP_ROOT / "almdina_erp" / "services" / "cutting_plan_service.py"
        ).read_text(encoding="utf-8")
        self.assertIn("Backward-compatible Cutting Plan lifecycle facade", source)
        self.assertIn("_snapshot.create_plan_from_order", source)
        self.assertIn("order_lifecycle_permission_service", source)
        self.assertIn("order_approval_service", source)
        self.assertNotIn("frappe.new_doc", source)
        self.assertNotIn("frappe.db", source)

    def test_retained_production_boundary_is_only_a_compatibility_facade(self) -> None:
        source = (
            APP_ROOT / "almdina_erp" / "services" / "production_service.py"
        ).read_text(encoding="utf-8")
        self.assertIn("Backward-compatible production-service facade", source)
        self.assertIn("production_stage_bootstrap_service", source)
        self.assertIn("order_status_sync_service", source)
        self.assertIn("legacy_endpoint_service", source)
        self.assertNotIn("frappe.db", source)
        self.assertNotIn("frappe.get_doc", source)

    def test_retained_order_creation_boundary_is_a_logic_free_tombstone(self) -> None:
        source = (
            APP_ROOT / "almdina_erp" / "services" / "order_creation_service.py"
        ).read_text(encoding="utf-8")
        self.assertIn("Retired historical order-creation module", source)
        self.assertIn("__all__: list[str] = []", source)
        self.assertNotIn("import frappe", source)
        self.assertNotIn("\ndef ", source)
        self.assertNotIn("frappe.get_doc", source)


if __name__ == "__main__":
    unittest.main()
