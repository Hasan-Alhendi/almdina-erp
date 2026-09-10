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


class TestMultipleRouteStatusProjection(unittest.TestCase):
    def test_terminal_readiness_is_scoped_to_each_selected_route(self) -> None:
        route_a = ProductionRoute(
            "Route A",
            "المسار أ",
            (
                RoutingStage(10, "ALPHA", "ألفا", "عامل ألفا"),
                RoutingStage(20, "BETA", "بيتا", "عامل بيتا"),
            ),
        )
        route_b = ProductionRoute(
            "Route B",
            "المسار ب",
            (
                RoutingStage(10, "ALPHA", "ألفا", "عامل ألفا"),
                RoutingStage(20, "GAMMA", "غاما", "عامل غاما"),
            ),
        )
        routes = {route_a.name: route_a, route_b.name: route_b}

        stage_a = {"name": "STAGE-A", "stage_type": "BETA", "status": "Completed"}
        order_a = {
            "status": "بيتا",
            "production_path": route_a.name,
            "current_production_stage": stage_a["name"],
        }
        self.assertEqual(
            order_list_query._effective_order_status(order_a, stage_a, routes),
            "Ready for Delivery",
        )

        stage_b = {"name": "STAGE-B", "stage_type": "ALPHA", "status": "Completed"}
        order_b = {
            "status": "ألفا",
            "production_path": route_b.name,
            "current_production_stage": stage_b["name"],
        }
        self.assertEqual(
            order_list_query._effective_order_status(order_b, stage_b, routes),
            "ألفا",
        )


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
        self.assertIn("order_list_query.get_status_filter_options", source)
        self.assertIn("require_doctype_capability", source)
        self.assertIn("Capability.VIEW_ORDERS", source)


class StatusFilterRepository:
    def __init__(self) -> None:
        self.user = "supervisor@example.com"
        self.admin = False
        self.capabilities = frozenset({Capability.VIEW_ORDERS})
        self.rows = ("Draft", "الرسم", "CNC", "التغليف", "Delivered", "Cancelled")

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

    def status_filter_options(self):
        return self.rows


class TestStatusFilterOptions(unittest.TestCase):
    def test_options_preserve_canonical_values_and_exact_stage_labels(self) -> None:
        payload = order_list_query.get_status_filter_options(StatusFilterRepository())
        self.assertEqual(
            payload,
            [
                {"value": "Draft", "label": "Draft"},
                {"value": "الرسم", "label": "الرسم"},
                {"value": "CNC", "label": "CNC"},
                {"value": "التغليف", "label": "التغليف"},
                {"value": "Delivered", "label": "Delivered"},
                {"value": "Cancelled", "label": "Cancelled"},
            ],
        )

    def test_missing_view_orders_returns_no_catalog(self) -> None:
        repository = StatusFilterRepository()
        repository.capabilities = frozenset()
        self.assertEqual(order_list_query.get_status_filter_options(repository), [])

    def test_guest_returns_no_catalog(self) -> None:
        repository = StatusFilterRepository()
        repository.user = "Guest"
        self.assertEqual(order_list_query.get_status_filter_options(repository), [])

    def test_adapter_uses_shared_status_metadata_projection(self) -> None:
        source = ADAPTER_PATH.read_text(encoding="utf-8")
        self.assertIn("def status_filter_options", source)
        self.assertIn("build_order_status_options", source)
        self.assertNotIn('"stage_type"', source.split("def status_filter_options", 1)[1])
        self.assertNotIn('"department_label"', source.split("def status_filter_options", 1)[1])


class TestOverviewOrderListSort(unittest.TestCase):
    def test_delivered_rank_is_last_and_other_statuses_share_the_active_group(self) -> None:
        self.assertEqual(order_list_query.overview_order_list_delivered_rank("Delivered"), 1)
        self.assertEqual(order_list_query.overview_order_list_delivered_rank("Ready for Delivery"), 0)
        self.assertEqual(order_list_query.overview_order_list_delivered_rank("Cancelled"), 0)
        self.assertEqual(order_list_query.overview_order_list_delivered_rank("At CNC"), 0)
        self.assertEqual(order_list_query.overview_order_list_delivered_rank(None), 0)

    def test_recently_modified_delivered_order_sorts_below_older_active_orders(self) -> None:
        rows = [
            {"name": "DCO-DELIVERED-NEW", "status": "Delivered", "modified": "2026-09-02 11:00:00"},
            {"name": "DCO-ACTIVE-OLD", "status": "At CNC", "modified": "2026-08-01 08:00:00"},
            {"name": "DCO-READY", "status": "Ready for Delivery", "modified": "2026-09-01 09:00:00"},
            {"name": "DCO-DELIVERED-OLD", "status": "Delivered", "modified": "2026-07-01 07:00:00"},
            {"name": "DCO-CANCELLED", "status": "Cancelled", "modified": "2026-09-02 10:00:00"},
        ]
        ordered = order_list_query.sort_overview_order_list(rows)
        self.assertEqual(
            [row["name"] for row in ordered],
            [
                "DCO-CANCELLED",
                "DCO-READY",
                "DCO-ACTIVE-OLD",
                "DCO-DELIVERED-NEW",
                "DCO-DELIVERED-OLD",
            ],
        )


if __name__ == "__main__":
    unittest.main()
