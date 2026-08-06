from __future__ import annotations

import json
import unittest
from pathlib import Path

from almdina_erp.almdina_erp.domain.orders.production_routing import (
    ProductionRoute,
    RoutingStage,
    normalize_eligible_roles,
)


class TestConfigurableProductionRoutingDomain(unittest.TestCase):
    def test_arbitrary_route_resolves_multiple_eligible_roles(self) -> None:
        route = ProductionRoute(
            name="PVC Route",
            label="مسار PVC",
            stages=(
                RoutingStage(10, "Cutting", "قص", ("عامل قص", "مشرف قص")),
                RoutingStage(20, "PVC", "تلبيس PVC", ("عامل PVC",)),
                RoutingStage(30, "Packing", "تغليف", ("عامل تغليف",)),
            ),
        )

        self.assertEqual(route.first_stage.eligible_roles, ("عامل قص", "مشرف قص"))
        self.assertEqual(route.first_stage.operational_role, "عامل قص")
        self.assertTrue(route.first_stage.accepts_any_role(("مشرف قص",)))
        self.assertFalse(route.first_stage.accepts_any_role(("عامل CNC",)))
        self.assertEqual(route.next_stage("Cutting").stage_type, "PVC")
        self.assertEqual(route.next_stage("PVC").department_label, "تغليف")
        self.assertIsNone(route.next_stage("Packing"))
        self.assertTrue(route.contains("PVC"))

    def test_role_normalization_is_stable_and_deduplicated(self) -> None:
        self.assertEqual(
            normalize_eligible_roles((" عامل قص ", "مشرف قص", "عامل قص", "")),
            ("عامل قص", "مشرف قص"),
        )
        self.assertEqual(normalize_eligible_roles("عامل PVC"), ("عامل PVC",))

    def test_route_rejects_missing_roles_and_duplicate_sequences(self) -> None:
        with self.assertRaisesRegex(ValueError, "eligible role"):
            ProductionRoute(
                "Invalid",
                "غير صالح",
                (RoutingStage(10, "CNC", "CNC", ()),),
            )
        with self.assertRaisesRegex(ValueError, "sequences must be unique"):
            ProductionRoute(
                "Invalid",
                "غير صالح",
                (
                    RoutingStage(10, "Cutting", "قص", ("عامل قص",)),
                    RoutingStage(10, "PVC", "PVC", ("عامل PVC",)),
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
        self.assertEqual(route_fields["eligible_roles_json"]["options"], "JSON")
        self.assertEqual(route_fields["configure_roles"]["fieldtype"], "Button")
        self.assertTrue(route_fields["operational_role"]["hidden"])
        self.assertTrue(route_fields["required"]["hidden"])
        self.assertTrue(route_fields["required"]["read_only"])
        self.assertEqual(route_fields["required"]["default"], "1")
        self.assertTrue(route_fields["auto_complete_if_not_applicable"]["hidden"])
        self.assertTrue(route_fields["auto_complete_if_not_applicable"]["read_only"])
        self.assertEqual(
            route_fields["auto_complete_if_not_applicable"]["default"],
            "0",
        )

        commands = (
            root / "almdina_erp" / "application" / "shop_floor" / "commands.py"
        ).read_text(encoding="utf-8")
        queries = (
            root / "almdina_erp" / "application" / "shop_floor" / "queries.py"
        ).read_text(encoding="utf-8")
        routing_repository = (
            root
            / "almdina_erp"
            / "infrastructure"
            / "frappe"
            / "production_routing_repository.py"
        ).read_text(encoding="utf-8")
        routing_controller = (
            root
            / "almdina_erp"
            / "doctype"
            / "production_routing"
            / "production_routing.py"
        ).read_text(encoding="utf-8")
        authorization = (
            root
            / "almdina_erp"
            / "infrastructure"
            / "frappe"
            / "shop_floor_authorization.py"
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
        self.assertIn("get_production_route", commands)
        self.assertIn("get_users_for_roles", commands)
        self.assertIn("list_active_routes", queries)
        self.assertIn("eligible_roles", queries)
        self.assertIn("if not roles:", routing_controller)
        self.assertIn("row.required = 1", routing_controller)
        self.assertIn("row.auto_complete_if_not_applicable = 0", routing_controller)
        self.assertNotIn('options: "Sharyoun\\nDrawing"', order_ux)
        self.assertNotIn('frappe.db.get_value("Production Stage"', order_ux)
        self.assertNotIn("Production Manager", routing_ux)
        self.assertIn("get_eligible_routing_roles", routing_ux)
        self.assertIn('fieldtype: "MultiSelectList"', routing_ux)
        self.assertIn("search_eligible_roles", master_data)
        self.assertNotIn("STAGE_ROLE_BY_TYPE", routing_repository)
        self.assertIn("STAGE_ROLE_BY_TYPE: dict[str, str] = {}", authorization)

    def test_migrations_preserve_roles_and_normalize_executable_stages(self) -> None:
        root = Path(__file__).resolve().parents[1]
        role_patch = "almdina_erp.patches.v1_0.migrate_routing_stage_eligible_roles"
        executable_patch = (
            "almdina_erp.patches.v1_0.normalize_executable_routing_stages"
        )
        patches = (root / "patches.txt").read_text(encoding="utf-8")
        migration = (
            root / "patches" / "v1_0" / "migrate_routing_stage_eligible_roles.py"
        ).read_text(encoding="utf-8")
        executable = (
            root / "patches" / "v1_0" / "normalize_executable_routing_stages.py"
        ).read_text(encoding="utf-8")
        historical = (
            root / "patches" / "v1_0" / "activate_configurable_production_routings.py"
        ).read_text(encoding="utf-8")
        self.assertIn(role_patch, patches)
        self.assertIn(executable_patch, patches)
        self.assertLess(patches.index(role_patch), patches.index(executable_patch))
        self.assertIn("eligible_roles_json", migration)
        self.assertIn("eligible_roles_display", migration)
        self.assertIn("operational_role", migration)
        self.assertIn("Production Routing Stage", migration)
        self.assertIn("Production Stage", migration)
        self.assertIn('{"required": 1}', executable)
        self.assertIn('values["auto_complete_if_not_applicable"] = 0', executable)
        self.assertNotIn("STAGE_DEFAULTS", historical)
        self.assertNotIn("LEGACY_ROUTES", historical)
        self.assertNotIn("_ensure_role", historical)


if __name__ == "__main__":
    unittest.main()
