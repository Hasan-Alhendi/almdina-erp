from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.security.navigation_context import (
    WORKSPACE_SHOP_FLOOR,
    build_navigation_context,
)
from almdina_erp.almdina_erp.application.security.permission_matrix import (
    normalize_capability_state,
    standard_permission_projection,
)
from almdina_erp.almdina_erp.application.security.shop_floor_history_migration import (
    legacy_history_state_updates,
)
from almdina_erp.almdina_erp.application.shop_floor.history_policy import (
    visible_archive_rows,
)
from almdina_erp.almdina_erp.application.shop_floor.queries import (
    ShopFloorPermissionDenied,
    get_my_archive,
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


class TestShopFloorHistoryPermission(unittest.TestCase):
    def test_history_capability_is_visibility_only(self) -> None:
        definition = CAPABILITY_CATALOG[Capability.VIEW_SHOP_FLOOR_HISTORY]
        self.assertEqual(definition.category, "shop_floor")
        self.assertNotIn(Capability.VIEW_SHOP_FLOOR_HISTORY, SHOP_FLOOR_ACCESS_CAPABILITIES)
        self.assertNotIn(Capability.VIEW_SHOP_FLOOR_HISTORY, PRODUCTION_OPERATOR_CAPABILITIES)
        self.assertNotIn(Capability.VIEW_SHOP_FLOOR_HISTORY, PRODUCTION_SUPERVISOR_CAPABILITIES)

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

    def test_history_filter_preserves_only_current_ready_for_delivery_row(self) -> None:
        rows = [
            {
                "name": "stage-current",
                "current_production_stage": "stage-current",
                "door_cutting_order": "DCO-READY",
                "order_status": "Ready for Delivery",
            },
            {
                "name": "stage-old",
                "current_production_stage": "stage-current",
                "door_cutting_order": "DCO-READY",
                "order_status": "Ready for Delivery",
            },
            {
                "name": "stage-completed",
                "current_production_stage": "stage-next",
                "door_cutting_order": "DCO-HISTORY",
                "order_status": "In Production",
            },
        ]

        denied = visible_archive_rows(rows, set())
        self.assertEqual([row["name"] for row in denied], ["stage-current"])

        allowed = visible_archive_rows(
            rows,
            {Capability.VIEW_SHOP_FLOOR_HISTORY},
        )
        self.assertEqual(allowed, rows)

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
