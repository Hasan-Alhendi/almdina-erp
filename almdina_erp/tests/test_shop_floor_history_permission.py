from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.security.navigation_context import (
    WORKSPACE_SHOP_FLOOR,
    build_navigation_context,
)
from almdina_erp.almdina_erp.application.security.permission_matrix import (
    CAPABILITY_PRESENTATION,
    normalize_capability_state,
    standard_permission_projection,
)
from almdina_erp.almdina_erp.application.security.shop_floor_history_migration import (
    legacy_history_state_updates,
)
from almdina_erp.almdina_erp.application.shop_floor.history_policy import (
    ready_for_delivery_rows,
    visible_archive_rows,
)
from almdina_erp.almdina_erp.application.shop_floor.queries import (
    ShopFloorPermissionDenied,
    get_my_archive,
    get_ready_for_delivery,
)
from almdina_erp.almdina_erp.domain.orders.production_routing import (
    ProductionRoute,
    RoutingStage,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    CAPABILITY_CATALOG,
    PRODUCTION_OPERATOR_CAPABILITIES,
    PRODUCTION_SUPERVISOR_CAPABILITIES,
    SHOP_FLOOR_ACCESS_CAPABILITIES,
    Capability,
)


class _HistoryOnlyRepository:
    def current_user(self) -> str:
        return "history@example.com"

    def global_capabilities(self) -> frozenset[str]:
        return frozenset({Capability.VIEW_SHOP_FLOOR_HISTORY})


class _ArchiveRepository:
    def __init__(self, capabilities: set[str]) -> None:
        self.capabilities = set(capabilities)
        self.user = "worker@example.com"

    def current_user(self) -> str:
        return self.user

    def global_capabilities(self) -> frozenset[str]:
        return frozenset(self.capabilities)

    def is_admin(self) -> bool:
        return Capability.MARK_DELIVERED in self.capabilities

    def list_archive_stages(self, *, user: str, is_admin: bool):
        return [
            {
                "name": "stage-history",
                "door_cutting_order": "DCO-HISTORY",
                "stage_type": "Edge",
                "status": "Completed",
                "assigned_to": self.user,
                "operational_role": "Edge Operator",
            },
            {
                "name": "stage-ready-previous",
                "door_cutting_order": "DCO-READY",
                "stage_type": "Cutting",
                "status": "Completed",
                "assigned_to": self.user,
                "operational_role": "Cutting Operator",
            },
            {
                "name": "stage-ready-terminal",
                "door_cutting_order": "DCO-READY",
                "stage_type": "Edge",
                "status": "Completed",
                "assigned_to": self.user,
                "operational_role": "Edge Operator",
            },
        ]

    def order_summaries(self, order_names):
        return {
            "DCO-HISTORY": {
                "name": "DCO-HISTORY",
                "status": "Delivered",
                "production_path": "route-a",
                "current_production_stage": None,
            },
            "DCO-READY": {
                "name": "DCO-READY",
                "status": "Ready for Delivery",
                "production_path": "route-a",
                "current_production_stage": None,
            },
        }

    def capabilities_for_order(self, order):
        return frozenset()

    def get_stage_summary(self, stage_name: str):
        return None

    def get_production_route(self, route_name: str) -> ProductionRoute:
        return _route_resolver(route_name)


def _production_route() -> ProductionRoute:
    return ProductionRoute(
        name="route-a",
        label="المسار أ",
        stages=(
            RoutingStage(1, "Cutting", "القص", "Cutting Operator"),
            RoutingStage(2, "Edge", "القشاط", "Edge Operator"),
        ),
    )


def _route_resolver(route_name: str) -> ProductionRoute:
    if route_name != "route-a":
        raise ValueError("Unknown route")
    return _production_route()


class TestShopFloorHistoryPermission(unittest.TestCase):
    def test_history_capability_is_visibility_only(self) -> None:
        definition = CAPABILITY_CATALOG[Capability.VIEW_SHOP_FLOOR_HISTORY]
        self.assertEqual(definition.category, "shop_floor")
        self.assertNotIn(Capability.VIEW_SHOP_FLOOR_HISTORY, SHOP_FLOOR_ACCESS_CAPABILITIES)
        self.assertNotIn(Capability.VIEW_SHOP_FLOOR_HISTORY, PRODUCTION_OPERATOR_CAPABILITIES)
        self.assertNotIn(Capability.VIEW_SHOP_FLOOR_HISTORY, PRODUCTION_SUPERVISOR_CAPABILITIES)

    def test_history_permission_keeps_stable_key_and_requested_arabic_label(self) -> None:
        self.assertEqual(Capability.VIEW_SHOP_FLOOR_HISTORY, "view_shop_floor_history")
        self.assertEqual(
            CAPABILITY_PRESENTATION[Capability.VIEW_SHOP_FLOOR_HISTORY]["label"],
            "عرض سجل الطلبات المنجزة",
        )

    def test_history_only_does_not_promote_order_scope_or_shop_floor_entry(self) -> None:
        state = normalize_capability_state({Capability.VIEW_SHOP_FLOOR_HISTORY: True})
        self.assertTrue(state[Capability.VIEW_SHOP_FLOOR_HISTORY])
        self.assertFalse(state[Capability.VIEW_ORDERS])
        self.assertFalse(state[Capability.VIEW_ALL_ORDERS])

        native = standard_permission_projection("Door Cutting Order", state)
        self.assertFalse(native["read"])
        self.assertFalse(native["select"])
        self.assertFalse(native["write"])
        self.assertFalse(native["create"])

        navigation = build_navigation_context({Capability.VIEW_SHOP_FLOOR_HISTORY})
        self.assertNotIn(WORKSPACE_SHOP_FLOOR, navigation["workspaces"])
        self.assertFalse(navigation["sections"]["production"])

        with self.assertRaises(ShopFloorPermissionDenied):
            get_my_archive(_HistoryOnlyRepository())

    def test_archive_endpoint_requires_history_capability(self) -> None:
        repository = _ArchiveRepository({Capability.START_ASSIGNED_STAGE})
        with self.assertRaisesRegex(ShopFloorPermissionDenied, "سجل الطلبات المنجزة"):
            get_my_archive(repository)

        repository.capabilities.add(Capability.VIEW_SHOP_FLOOR_HISTORY)
        rows = get_my_archive(repository)
        self.assertEqual([row["name"] for row in rows], ["stage-history"])

    def test_ready_for_delivery_is_independent_operational_query(self) -> None:
        repository = _ArchiveRepository(
            {Capability.START_ASSIGNED_STAGE, Capability.MARK_DELIVERED}
        )
        rows = get_ready_for_delivery(repository)
        self.assertEqual([row["name"] for row in rows], ["stage-ready-terminal"])

        repository.capabilities.remove(Capability.MARK_DELIVERED)
        with self.assertRaisesRegex(ShopFloorPermissionDenied, "الجاهزة للتسليم"):
            get_ready_for_delivery(repository)

    def test_history_policy_never_falls_back_to_delivery_ready_rows(self) -> None:
        rows = [
            {
                "name": "stage-terminal",
                "order_status": "Ready for Delivery",
                "production_path": "route-a",
                "stage_type": "Edge",
            },
            {
                "name": "stage-history",
                "order_status": "Delivered",
                "production_path": "route-a",
                "stage_type": "Edge",
            },
        ]

        self.assertEqual(visible_archive_rows(rows, set()), [])
        self.assertEqual(
            [
                row["name"]
                for row in visible_archive_rows(
                    rows,
                    {Capability.VIEW_SHOP_FLOOR_HISTORY},
                )
            ],
            ["stage-history"],
        )

    def test_ready_policy_preserves_only_terminal_delivery_row(self) -> None:
        rows = [
            {
                "name": "stage-terminal",
                "order_status": "Ready for Delivery",
                "production_path": "route-a",
                "stage_type": "Edge",
            },
            {
                "name": "stage-previous",
                "order_status": "Ready for Delivery",
                "production_path": "route-a",
                "stage_type": "Cutting",
            },
            {
                "name": "stage-non-ready",
                "order_status": "Delivered",
                "production_path": "route-a",
                "stage_type": "Edge",
            },
        ]
        self.assertEqual(
            [
                row["name"]
                for row in ready_for_delivery_rows(
                    rows,
                    route_resolver=_route_resolver,
                )
            ],
            ["stage-terminal"],
        )

    def test_ready_policy_fails_closed_for_missing_or_invalid_routing(self) -> None:
        rows = [
            {
                "name": "missing-route",
                "order_status": "Ready for Delivery",
                "production_path": "",
                "stage_type": "Edge",
            },
            {
                "name": "unknown-route",
                "order_status": "Ready for Delivery",
                "production_path": "route-missing",
                "stage_type": "Edge",
            },
            {
                "name": "unknown-stage",
                "order_status": "Ready for Delivery",
                "production_path": "route-a",
                "stage_type": "Unknown",
            },
        ]
        self.assertEqual(
            ready_for_delivery_rows(rows, route_resolver=_route_resolver),
            [],
        )
        self.assertEqual(ready_for_delivery_rows(rows), [])

    def test_legacy_migration_is_minimal_and_idempotent(self) -> None:
        states = {
            "Operator": {Capability.START_ASSIGNED_STAGE: True},
            "Supervisor": {Capability.REASSIGN_WORKER: True},
            "Unrelated": {Capability.VIEW_ORDERS: True},
            "Already Migrated": {
                Capability.START_ASSIGNED_STAGE: True,
                Capability.VIEW_SHOP_FLOOR_HISTORY: True,
            },
        }
        updates = legacy_history_state_updates(states)
        self.assertEqual(set(updates), {"Operator", "Supervisor"})
        self.assertTrue(updates["Operator"][Capability.VIEW_SHOP_FLOOR_HISTORY])
        self.assertTrue(updates["Supervisor"][Capability.VIEW_SHOP_FLOOR_HISTORY])
        self.assertNotIn(Capability.VIEW_SHOP_FLOOR_HISTORY, states["Operator"])
        self.assertNotIn("Unrelated", updates)

        migrated = {role: dict(state) for role, state in states.items()}
        migrated.update(updates)
        self.assertEqual(legacy_history_state_updates(migrated), {})


if __name__ == "__main__":
    unittest.main()
