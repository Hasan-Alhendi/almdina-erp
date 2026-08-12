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
        self.assertTrue(route.requires_approved_plan_before_dispatch)

    def test_planning_stage_is_explicit_and_must_be_first(self) -> None:
        route = ProductionRoute(
            "Planning First",
            "تخطيط ثم CNC",
            (
                RoutingStage(10, "Planner", "تخطيط", "مخطط", True),
                RoutingStage(20, "CNC", "CNC", "عامل CNC"),
            ),
        )
        self.assertTrue(route.starts_with_planning)
        self.assertFalse(route.requires_approved_plan_before_dispatch)

        with self.assertRaisesRegex(ValueError, "مرحلة التخطيط يجب أن تكون أول"):
            ProductionRoute(
                "Invalid Planning",
                "غير صالح",
                (
                    RoutingStage(10, "Cutting", "قص", "عامل قص"),
                    RoutingStage(20, "Planner", "تخطيط", "مخطط", True),
                ),
            )
        with self.assertRaisesRegex(ValueError, "مرحلة تخطيط واحدة"):
            ProductionRoute(
                "Two Planning",
                "غير صالح",
                (
                    RoutingStage(10, "P1", "تخطيط 1", "مخطط", True),
                    RoutingStage(20, "P2", "تخطيط 2", "مخطط", True),
                ),
            )

    def test_route_rejects_missing_role_department_and_duplicate_sequences(self) -> None:
        with self.assertRaisesRegex(ValueError, "الدور التشغيلي"):
            ProductionRoute(
                "Invalid",
                "غير صالح",
                (RoutingStage(10, "CNC", "CNC", ""),),
            )
        with self.assertRaisesRegex(ValueError, "الاسم الظاهر"):
            ProductionRoute(
                "Invalid",
                "غير صالح",
                (RoutingStage(10, "CNC", "", "عامل CNC"),),
            )
        with self.assertRaisesRegex(ValueError, "تكرار"):
            ProductionRoute(
                "Invalid",
                "غير صالح",
                (
                    RoutingStage(10, "Cutting", "قص", "عامل قص"),
                    RoutingStage(10, "PVC", "PVC", "عامل PVC"),
                ),
            )

    def test_route_schema_runtime_and_role_selection_are_configuration_driven(self) -> None:
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
        self.assertIn("is_planning_stage", route_fields)
        self.assertNotIn("auto_complete_if_not_applicable", route_fields)

        commands = (
            root / "almdina_erp" / "application" / "shop_floor" / "commands.py"
        ).read_text(encoding="utf-8")
        queries = (
            root / "almdina_erp" / "application" / "shop_floor" / "queries.py"
        ).read_text(encoding="utf-8")
        order_ux = (root / "public" / "js" / "shop_floor_order_ux.js").read_text(
            encoding="utf-8"
        )
        routing_ux = (root / "public" / "js" / "production_routing_ux.js").read_text(
            encoding="utf-8"
        )
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
        controller = (
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

        self.assertIn("get_production_route", commands)
        self.assertIn("list_active_routes", queries)
        self.assertIn("is_planning_stage", commands)
        self.assertIn("starts_with_planning", queries)
        self.assertNotIn('options: "Sharyoun\\nDrawing"', order_ux)
        self.assertNotIn('frappe.db.get_value("Production Stage"', order_ux)
        self.assertNotIn("Production Manager", routing_ux)
        self.assertIn("search_operational_roles", routing_ux)
        self.assertIn("معاينة سير الإنتاج", routing_ux)
        self.assertIn("Capability.VIEW_PRODUCTION_ROUTINGS", master_data)
        self.assertIn("PROTECTED_SYSTEM_ROLES", master_data)
        self.assertNotIn("STAGE_ROLE_BY_TYPE", repository)
        self.assertNotIn("shop_floor_authorization", repository)
        self.assertNotIn("department_for_stage_type", repository)
        self.assertIn('getattr(row, "operational_role", None)', repository)
        self.assertIn("is_protected_system_role", controller)
        self.assertIn("ALMDINA_APP", authorization)
        self.assertIn("default_app", authorization)

    def test_migrations_preserve_legacy_data_without_seeding_clean_sites(self) -> None:
        root = Path(__file__).resolve().parents[1]
        activate_patch = "almdina_erp.patches.v1_0.activate_configurable_production_routings"
        planning_patch = "almdina_erp.patches.v1_0.mark_route_planning_stages"
        patches = (root / "patches.txt").read_text(encoding="utf-8")
        activation = (
            root / "patches" / "v1_0" / "activate_configurable_production_routings.py"
        ).read_text(encoding="utf-8")
        planning = (
            root / "patches" / "v1_0" / "mark_route_planning_stages.py"
        ).read_text(encoding="utf-8")

        self.assertIn(activate_patch, patches)
        self.assertIn(planning_patch, patches)
        self.assertIn("_has_legacy_production_data", activation)
        self.assertIn("if not _has_legacy_production_data():", activation)
        self.assertIn("return", activation)
        self.assertNotIn("for _, role in STAGE_DEFAULTS.values()", activation)
        self.assertNotIn("auto_complete_if_not_applicable", activation)
        self.assertIn("_backfill_production_stages", activation)
        self.assertIn("operational_role", activation)
        self.assertIn('!= "Drawing"', planning)
        self.assertIn('"is_planning_stage"', planning)


if __name__ == "__main__":
    unittest.main()
