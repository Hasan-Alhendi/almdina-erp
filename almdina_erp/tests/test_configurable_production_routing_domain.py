from __future__ import annotations

import json
import unittest
from pathlib import Path

from almdina_erp.almdina_erp.domain.orders.production_routing import (
    ProductionRoute,
    RoutingStage,
)


class TestConfigurableProductionRoutingDomain(unittest.TestCase):
    def test_arbitrary_route_resolves_first_and_next_stage_with_role(self) -> None:
        route = ProductionRoute(
            name="PVC Route",
            label="مسار PVC",
            stages=(
                RoutingStage(10, "Cutting", "قص", "عامل قص مخصص"),
                RoutingStage(20, "PVC", "تلبيس PVC", "عامل PVC"),
                RoutingStage(30, "Packing", "تغليف", "عامل تغليف"),
            ),
        )

        self.assertEqual(route.first_stage.operational_role, "عامل قص مخصص")
        self.assertEqual(route.next_stage("Cutting").stage_type, "PVC")
        self.assertEqual(route.next_stage("PVC").department_label, "تغليف")
        self.assertIsNone(route.next_stage("Packing"))
        self.assertTrue(route.contains("PVC"))

    def test_route_rejects_missing_role_and_duplicate_sequences(self) -> None:
        with self.assertRaisesRegex(ValueError, "operational role"):
            ProductionRoute(
                "Invalid",
                "غير صالح",
                (RoutingStage(10, "CNC", "CNC", ""),),
            )
        with self.assertRaisesRegex(ValueError, "sequences must be unique"):
            ProductionRoute(
                "Invalid",
                "غير صالح",
                (
                    RoutingStage(10, "Cutting", "قص", "عامل قص"),
                    RoutingStage(10, "PVC", "PVC", "عامل PVC"),
                ),
            )

    def test_route_schema_and_runtime_are_configuration_driven(self) -> None:
        root = Path(__file__).resolve().parents[1]
        order_schema = json.loads(
            (
                root
                / "almdina_erp"
                / "doctype"
                / "door_cutting_order"
                / "door_cutting_order.json"
            ).read_text(encoding="utf-8")
        )
        route_stage_schema = json.loads(
            (
                root
                / "almdina_erp"
                / "doctype"
                / "production_routing_stage"
                / "production_routing_stage.json"
            ).read_text(encoding="utf-8")
        )
        order_fields = {row["fieldname"]: row for row in order_schema["fields"]}
        route_fields = {row["fieldname"]: row for row in route_stage_schema["fields"]}
        self.assertEqual(order_fields["production_path"]["fieldtype"], "Link")
        self.assertEqual(order_fields["production_path"]["options"], "Production Routing")
        self.assertEqual(route_fields["stage_type"]["fieldtype"], "Data")
        self.assertEqual(route_fields["operational_role"]["options"], "Role")

        commands = (
            root / "almdina_erp" / "application" / "shop_floor" / "commands.py"
        ).read_text(encoding="utf-8")
        queries = (
            root / "almdina_erp" / "application" / "shop_floor" / "queries.py"
        ).read_text(encoding="utf-8")
        order_ux = (root / "public" / "js" / "shop_floor_order_ux.js").read_text(
            encoding="utf-8"
        )
        routing_ux = (
            root / "public" / "js" / "production_routing_ux.js"
        ).read_text(encoding="utf-8")
        master_data = (
            root / "almdina_erp" / "services" / "master_data_service.py"
        ).read_text(encoding="utf-8")
        repository = (
            root
            / "almdina_erp"
            / "infrastructure"
            / "frappe"
            / "production_routing_repository.py"
        ).read_text(encoding="utf-8")
        self.assertIn("get_production_route", commands)
        self.assertIn("list_active_routes", queries)
        self.assertNotIn('options: "Sharyoun\\nDrawing"', order_ux)
        self.assertNotIn('frappe.db.get_value("Production Stage"', order_ux)
        self.assertNotIn("Production Manager", routing_ux)
        self.assertIn("search_operational_roles", routing_ux)
        self.assertIn("Capability.VIEW_PRODUCTION_ROUTINGS", master_data)
        self.assertNotIn("STAGE_ROLE_BY_TYPE", repository)
        self.assertNotIn("shop_floor_authorization", repository)
        self.assertIn('getattr(row, "operational_role", None)', repository)

    def test_migration_preserves_legacy_routes_and_backfills_stage_snapshots(self) -> None:
        root = Path(__file__).resolve().parents[1]
        patch_name = "almdina_erp.patches.v1_0.activate_configurable_production_routings"
        patches = (root / "patches.txt").read_text(encoding="utf-8")
        migration = (
            root / "patches" / "v1_0" / "activate_configurable_production_routings.py"
        ).read_text(encoding="utf-8")
        self.assertIn(patch_name, patches)
        self.assertIn('"Sharyoun": ("Sharyoun", "Sanding")', migration)
        self.assertIn('"Drawing": ("Drawing", "CNC", "Sanding")', migration)
        self.assertIn("_backfill_production_stages", migration)
        self.assertIn("operational_role", migration)


if __name__ == "__main__":
    unittest.main()
