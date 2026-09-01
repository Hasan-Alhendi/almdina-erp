from __future__ import annotations

import unittest
from collections import Counter
from pathlib import Path
from typing import Any

from almdina_erp.almdina_erp.application.shop_floor import order_list_query
from almdina_erp.almdina_erp.domain.orders.production_routing import (
    ProductionRoute,
    RoutingStage,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "order_list_query_repository.py"
)
SERVICE_PATH = ROOT / "almdina_erp" / "services" / "shop_floor_query_service.py"


class BulkRepository:
    def __init__(self, count: int = 20) -> None:
        self.calls: Counter[str] = Counter()
        self.user = "drawing@example.com"
        self.admin = False
        self.roles = ("عامل رسم",)
        self.capabilities = frozenset(
            {
                Capability.START_ASSIGNED_STAGE,
                Capability.HANDOFF_ASSIGNED_STAGE,
            }
        )
        self.names = [f"DCO-{index:03d}" for index in range(1, count + 1)]
        self.hidden = "DCO-HIDDEN"
        self.orders: dict[str, Any] = {}
        self.stages: dict[str, Any] = {}
        self.timings: dict[str, Any] = {}
        for index, name in enumerate(self.names, start=1):
            stage_name = f"PST-{index:03d}"
            status = "Pending" if index % 2 else "In Progress"
            self.orders[name] = {
                "name": name,
                "status": "At Drawing",
                "production_path": "Drawing",
                "current_production_stage": stage_name,
                "cutting_plan_json": "{}",
                "plan_needs_recalculation": 0,
            }
            self.stages[stage_name] = {
                "name": stage_name,
                "stage_type": "Drawing",
                "status": status,
                "assigned_to": self.user,
                "operational_role": "عامل رسم",
            }
            self.timings[name] = {
                "assignment_time": f"2026-08-17 10:{index % 60:02d}:00",
                "completion_time": None,
            }
        self.routes = {
            "Drawing": ProductionRoute(
                "Drawing",
                "رسم وCNC",
                (
                    RoutingStage(10, "Drawing", "رسم", "عامل رسم", True),
                    RoutingStage(20, "CNC", "CNC", "عامل CNC"),
                ),
            )
        }

    def current_user(self) -> str:
        self.calls["current_user"] += 1
        return self.user

    def is_admin(self) -> bool:
        self.calls["is_admin"] += 1
        return self.admin

    def actor_roles(self, user: str | None = None) -> tuple[str, ...]:
        self.calls["actor_roles"] += 1
        return self.roles

    def global_capabilities(self) -> frozenset[str]:
        self.calls["global_capabilities"] += 1
        return self.capabilities

    def visible_order_names(self, order_names):
        self.calls["visible_order_names"] += 1
        return frozenset(name for name in order_names if name != self.hidden)

    def order_summaries(self, order_names):
        self.calls["order_summaries"] += 1
        return {name: self.orders[name] for name in order_names if name in self.orders}

    def stage_summaries(self, stage_names):
        self.calls["stage_summaries"] += 1
        return {name: self.stages[name] for name in stage_names if name in self.stages}

    def personal_order_stage_timings(self, order_names, *, user: str):
        self.calls["personal_order_stage_timings"] += 1
        return {name: self.timings.get(name, {}) for name in order_names}

    def production_routes(self, route_names):
        self.calls["production_routes"] += 1
        return {name: self.routes[name] for name in route_names if name in self.routes}


class TestOrderListBulkQuery(unittest.TestCase):
    def test_twenty_rows_use_one_bulk_read_per_projection(self) -> None:
        repository = BulkRepository(count=20)

        payload = order_list_query.get_order_operational_role_flags(
            repository,
            [*repository.names, repository.hidden],
        )

        self.assertTrue(payload["personal_view"])
        self.assertEqual(len(payload["orders"]), 20)
        self.assertNotIn(repository.hidden, payload["orders"])
        for operation in (
            "visible_order_names",
            "order_summaries",
            "stage_summaries",
            "personal_order_stage_timings",
            "production_routes",
            "actor_roles",
            "global_capabilities",
        ):
            self.assertEqual(repository.calls[operation], 1, operation)

        first = payload["orders"]["DCO-001"]
        second = payload["orders"]["DCO-002"]
        self.assertEqual(first["assignment_state"], "assigned")
        self.assertTrue(first["can_start_stage"])
        self.assertFalse(first["can_handoff_stage"])
        self.assertFalse(second["can_start_stage"])
        self.assertTrue(second["can_handoff_stage"])

    def test_visibility_is_resolved_before_any_order_data_projection(self) -> None:
        repository = BulkRepository(count=1)
        repository.hidden = repository.names[0]

        payload = order_list_query.get_order_operational_role_flags(
            repository,
            repository.names,
        )

        self.assertEqual(payload["orders"], {})
        self.assertEqual(repository.calls["visible_order_names"], 1)
        self.assertEqual(repository.calls["order_summaries"], 0)
        self.assertEqual(repository.calls["stage_summaries"], 0)
        self.assertEqual(repository.calls["personal_order_stage_timings"], 0)

    def test_foreign_assignee_never_gets_worker_actions(self) -> None:
        repository = BulkRepository(count=1)
        stage_name = repository.orders[repository.names[0]]["current_production_stage"]
        repository.stages[stage_name]["assigned_to"] = "other@example.com"
        repository.stages[stage_name]["status"] = "In Progress"

        row = order_list_query.get_order_operational_role_flags(
            repository,
            repository.names,
        )["orders"][repository.names[0]]

        self.assertFalse(row["is_current_assignee"])
        self.assertEqual(row["assignment_state"], "completed")
        self.assertFalse(row["can_start_stage"])
        self.assertFalse(row["can_handoff_stage"])

    def test_invalid_route_stage_hides_handoff_without_changing_authorization(self) -> None:
        repository = BulkRepository(count=1)
        stage_name = repository.orders[repository.names[0]]["current_production_stage"]
        repository.stages[stage_name]["stage_type"] = "Unknown"
        repository.stages[stage_name]["status"] = "In Progress"
        repository.stages[stage_name]["operational_role"] = "عامل رسم"

        row = order_list_query.get_order_operational_role_flags(
            repository,
            repository.names,
        )["orders"][repository.names[0]]

        self.assertFalse(row["can_handoff_stage"])


class TestOrderListFrappeAdapterContract(unittest.TestCase):
    def test_adapter_uses_bulk_permission_and_stage_reads_without_documents(self) -> None:
        source = ADAPTER_PATH.read_text(encoding="utf-8")
        self.assertIn("frappe.get_list(", source)
        self.assertIn("frappe.get_all(", source)
        self.assertIn('filters={"name": ["in", names]}', source)
        self.assertNotIn("frappe.get_doc", source)
        self.assertNotIn("document_has_capability", source)
        self.assertNotIn("frappe.has_permission", source)

    def test_endpoint_uses_focused_bulk_query_instead_of_legacy_row_loop(self) -> None:
        source = SERVICE_PATH.read_text(encoding="utf-8")
        self.assertIn("FrappeOrderListQueryRepository", source)
        self.assertIn("order_list_query.get_order_operational_role_flags", source)
        self.assertNotIn(
            "return _execute(queries.get_order_operational_role_flags, order_names)",
            source,
        )
        self.assertIn("order_list_query.get_department_filter_options", source)
        self.assertIn("require_doctype_capability", source)
        self.assertIn("Capability.VIEW_ORDERS", source)


class DepartmentFilterRepository:
    def __init__(self) -> None:
        self.user = "supervisor@example.com"
        self.admin = False
        self.capabilities = frozenset({Capability.VIEW_ORDERS})
        self.rows = [
            {"stage_type": "Sanding", "department_label": "التقشيط"},
            {"stage_type": "Sanding", "department_label": "تقشيط"},
            {"stage_type": "Edge Banding", "department_label": "قشاط"},
            {"stage_type": "", "department_label": "ignored"},
        ]

    def current_user(self) -> str:
        return self.user

    def is_admin(self) -> bool:
        return self.admin

    def actor_roles(self, user: str | None = None) -> tuple[str, ...]:
        return ()

    def global_capabilities(self) -> frozenset[str]:
        return self.capabilities

    def visible_order_names(self, order_names):
        return frozenset()

    def order_summaries(self, order_names):
        return {}

    def stage_summaries(self, stage_names):
        return {}

    def personal_order_stage_timings(self, order_names, *, user: str):
        return {}

    def production_routes(self, route_names):
        return {}

    def department_filter_options(self):
        return list(self.rows)


class TestDepartmentFilterOptions(unittest.TestCase):
    def test_options_are_unique_stage_types_with_visible_labels(self) -> None:
        payload = order_list_query.get_department_filter_options(
            DepartmentFilterRepository()
        )
        self.assertEqual(
            payload,
            [
                {"stage_type": "Sanding", "department_label": "التقشيط"},
                {"stage_type": "Edge Banding", "department_label": "قشاط"},
            ],
        )

    def test_missing_view_orders_returns_no_catalog(self) -> None:
        repository = DepartmentFilterRepository()
        repository.capabilities = frozenset()
        self.assertEqual(
            order_list_query.get_department_filter_options(repository),
            [],
        )

    def test_guest_returns_no_catalog(self) -> None:
        repository = DepartmentFilterRepository()
        repository.user = "Guest"
        self.assertEqual(
            order_list_query.get_department_filter_options(repository),
            [],
        )

    def test_adapter_reads_enabled_routing_stages_without_financial_fields(self) -> None:
        source = ADAPTER_PATH.read_text(encoding="utf-8")
        self.assertIn("def department_filter_options", source)
        self.assertIn('"Production Routing Stage"', source)
        self.assertIn('"stage_type"', source)
        self.assertIn('"department_label"', source)
        self.assertNotIn("rate_usd", source)
        self.assertNotIn("operational_role", source.split("def department_filter_options", 1)[1])


if __name__ == "__main__":
    unittest.main()
