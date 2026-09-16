from __future__ import annotations

import importlib
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PERMISSIONS_PATH = Path(__file__).resolve().parents[1] / "permissions.py"
GATEWAY_MODULE = (
    "almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway"
)
_MISSING_MODULE = object()


def _real_frappe_is_available() -> bool:
    try:
        return importlib.util.find_spec("frappe") is not None
    except (ImportError, ValueError):
        return False


def _load_permissions_with_fakes():
    fake_frappe = types.ModuleType("frappe")
    fake_frappe.session = SimpleNamespace(user="test@example.com")
    fake_frappe.db = SimpleNamespace()

    fake_gateway = types.ModuleType(GATEWAY_MODULE)
    fake_gateway.doctype_has_capability = lambda *_args, **_kwargs: False

    module_overrides = {
        "frappe": fake_frappe,
        GATEWAY_MODULE: fake_gateway,
    }
    previous_modules = {
        name: sys.modules.get(name, _MISSING_MODULE) for name in module_overrides
    }
    sys.modules.update(module_overrides)
    try:
        spec = importlib.util.spec_from_file_location(
            "_almdina_frappe_v16_permission_hook_contract",
            PERMISSIONS_PATH,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("Could not load permission hooks")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, previous in previous_modules.items():
            if previous is _MISSING_MODULE:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


def load_permissions_module():
    if _real_frappe_is_available():
        return importlib.import_module("almdina_erp.permissions")
    return _load_permissions_with_fakes()


permissions = load_permissions_module()


class TestFrappeV16PermissionHookContract(unittest.TestCase):
    def test_broad_scope_document_hooks_return_explicit_true(self) -> None:
        order = SimpleNamespace(name="DCO-TEST")
        stage = SimpleNamespace(assigned_to="other@example.com")

        with (
            patch.object(permissions, "_has", return_value=True),
            patch.object(permissions, "_has_any", return_value=True),
            patch.object(permissions, "_requires_assigned_scope", return_value=False),
        ):
            self.assertIs(
                permissions.door_cutting_order_has_permission(
                    order,
                    user="order@example.com",
                    ptype="read",
                ),
                True,
            )
            self.assertIs(
                permissions.door_cutting_order_has_permission(
                    order,
                    user="order@example.com",
                    ptype="write",
                ),
                True,
            )
            self.assertIs(
                permissions.production_stage_has_permission(
                    stage,
                    user="order@example.com",
                    ptype="read",
                ),
                True,
            )

    def test_empty_role_fails_closed_for_all_protected_surfaces(self) -> None:
        order = SimpleNamespace(name="DCO-TEST")
        plan = SimpleNamespace(door_cutting_order="DCO-TEST")
        stage = SimpleNamespace(assigned_to="empty@example.com")
        replacement = SimpleNamespace(door_cutting_order="DCO-TEST")

        with (
            patch.object(permissions, "_has", return_value=False),
            patch.object(permissions, "_has_any", return_value=False),
        ):
            for ptype in ("read", "create", "write", "delete", "view_costs"):
                with self.subTest(ptype=ptype):
                    self.assertFalse(
                        permissions.door_cutting_order_has_permission(
                            order,
                            user="empty@example.com",
                            ptype=ptype,
                        )
                    )
            for ptype in ("read", "recalculate_plan", "view_costs"):
                with self.subTest(plan_ptype=ptype):
                    self.assertFalse(
                        permissions.cutting_plan_has_permission(
                            plan,
                            user="empty@example.com",
                            ptype=ptype,
                        )
                    )
            self.assertFalse(
                permissions.production_stage_has_permission(
                    stage,
                    user="empty@example.com",
                    ptype="read",
                )
            )
            self.assertFalse(
                permissions.replacement_piece_has_permission(
                    replacement,
                    user="empty@example.com",
                    ptype="read",
                )
            )
            self.assertEqual(
                permissions.door_cutting_order_query("empty@example.com"),
                "1=0",
            )
            self.assertEqual(
                permissions.cutting_plan_query("empty@example.com"),
                "1=0",
            )
            self.assertEqual(
                permissions.production_stage_query("empty@example.com"),
                "1=0",
            )
            self.assertEqual(
                permissions.replacement_piece_query("empty@example.com"),
                "1=0",
            )

    def test_order_delete_is_denied_even_when_other_capabilities_exist(self) -> None:
        with patch.object(permissions, "_has", return_value=True):
            self.assertFalse(
                permissions.door_cutting_order_has_permission(
                    SimpleNamespace(name="DCO-TEST"),
                    user="manager@example.com",
                    ptype="delete",
                )
            )

    def test_assigned_scope_still_denies_unassigned_documents(self) -> None:
        order = SimpleNamespace(name="DCO-TEST")

        with (
            patch.object(permissions, "_has", return_value=True),
            patch.object(permissions, "_requires_assigned_scope", return_value=True),
            patch.object(permissions, "_assigned_order_exists", return_value=False),
        ):
            self.assertIs(
                permissions.door_cutting_order_has_permission(
                    order,
                    user="worker@example.com",
                    ptype="read",
                ),
                False,
            )

    def test_completed_worker_list_scope_requires_history_capability(self) -> None:
        with (
            patch.object(
                permissions,
                "_worker_actionable_orders_subquery",
                return_value="active-orders",
            ),
            patch.object(
                permissions,
                "_worker_completed_orders_subquery",
                return_value="completed-orders",
            ) as completed,
            patch.object(permissions, "_has", return_value=False),
        ):
            self.assertEqual(
                permissions._worker_visible_orders_subquery("worker@example.com"),
                "active-orders",
            )
            completed.assert_not_called()

        with (
            patch.object(
                permissions,
                "_worker_actionable_orders_subquery",
                return_value="active-orders",
            ),
            patch.object(
                permissions,
                "_worker_completed_orders_subquery",
                return_value="completed-orders",
            ),
            patch.object(permissions, "_has", return_value=True),
        ):
            self.assertEqual(
                permissions._worker_visible_orders_subquery("worker@example.com"),
                "active-orders union completed-orders",
            )

    def test_actionable_worker_query_requires_active_current_stage(self) -> None:
        source = PERMISSIONS_PATH.read_text(encoding="utf-8")
        self.assertIn("ACTIVE_STAGE_STATUSES", source)
        self.assertIn("and ps.status in ({active_stage_sql})", source)
        self.assertIn("not in ACTIVE_STAGE_STATUSES", source)

        with (
            patch.object(
                permissions.frappe.db,
                "escape",
                side_effect=lambda value: f"'{value}'",
                create=True,
            ),
            patch.object(
                permissions,
                "_worker_operational_roles",
                return_value=("عامل تقشيط",),
            ),
        ):
            sql = permissions._worker_actionable_orders_subquery("sanding@example.com")
        self.assertIn("ps.status in", sql)
        self.assertIn("'Pending'", sql)
        self.assertIn("'In Progress'", sql)
        self.assertIn("'Paused'", sql)
        self.assertNotIn("'Completed'", sql)

    def test_supporting_list_scopes_preserve_completed_assignments(self) -> None:
        granted = {
            permissions.Capability.VIEW_ORDERS,
            permissions.Capability.VIEW_CUTTING_PLAN,
            permissions.Capability.VIEW_REPLACEMENTS,
        }
        with (
            patch.object(
                permissions,
                "_worker_actionable_orders_subquery",
                return_value="active-orders",
            ),
            patch.object(
                permissions,
                "_worker_completed_orders_subquery",
                return_value="completed-orders",
            ),
            patch.object(
                permissions,
                "_has",
                side_effect=lambda _user, capability: capability in granted,
            ),
            patch.object(permissions, "_requires_assigned_scope", return_value=True),
        ):
            self.assertEqual(
                permissions.door_cutting_order_query("worker@example.com"),
                "`tabDoor Cutting Order`.name in (active-orders)",
            )
            self.assertIn(
                "active-orders union completed-orders",
                permissions.cutting_plan_query("worker@example.com"),
            )
            self.assertIn(
                "active-orders union completed-orders",
                permissions.replacement_piece_query("worker@example.com"),
            )

    def test_supporting_document_reads_preserve_completed_assignments(self) -> None:
        granted = {
            permissions.Capability.VIEW_ORDERS,
            permissions.Capability.VIEW_CUTTING_PLAN,
            permissions.Capability.VIEW_REPLACEMENTS,
        }
        with (
            patch.object(
                permissions,
                "_has",
                side_effect=lambda _user, capability: capability in granted,
            ),
            patch.object(permissions, "_requires_assigned_scope", return_value=True),
            patch.object(permissions, "_assigned_order_exists", return_value=False),
            patch.object(permissions, "_supporting_order_exists", return_value=True),
        ):
            self.assertFalse(
                permissions.door_cutting_order_has_permission(
                    SimpleNamespace(name="DCO-COMPLETED"),
                    user="worker@example.com",
                    ptype="read",
                )
            )
            self.assertTrue(
                permissions.cutting_plan_has_permission(
                    SimpleNamespace(door_cutting_order="DCO-COMPLETED"),
                    user="worker@example.com",
                    ptype="read",
                )
            )
            self.assertTrue(
                permissions.replacement_piece_has_permission(
                    SimpleNamespace(door_cutting_order="DCO-COMPLETED"),
                    user="worker@example.com",
                    ptype="read",
                )
            )

    def test_completed_document_read_requires_history_capability(self) -> None:
        with (
            patch.object(permissions, "_requires_assigned_scope", return_value=True),
            patch.object(
                permissions,
                "_dispatched_order_row",
                return_value={
                    "status": "Delivered",
                    "current_production_stage": None,
                },
            ),
            patch.object(permissions, "_has", return_value=False),
            patch.object(
                permissions.frappe.db,
                "exists",
                return_value=True,
                create=True,
            ) as completed_exists,
        ):
            self.assertFalse(
                permissions.worker_can_view_order(
                    "worker@example.com",
                    "DCO-COMPLETED",
                )
            )
            completed_exists.assert_not_called()

        with (
            patch.object(permissions, "_requires_assigned_scope", return_value=True),
            patch.object(
                permissions,
                "_dispatched_order_row",
                return_value={
                    "status": "Delivered",
                    "current_production_stage": None,
                },
            ),
            patch.object(permissions, "_has", return_value=True),
            patch.object(
                permissions.frappe.db,
                "exists",
                return_value=True,
                create=True,
            ),
        ):
            self.assertTrue(
                permissions.worker_can_view_order(
                    "worker@example.com",
                    "DCO-COMPLETED",
                )
            )

    def test_completed_current_stage_read_requires_history_capability(self) -> None:
        with (
            patch.object(permissions, "_requires_assigned_scope", return_value=True),
            patch.object(
                permissions,
                "_dispatched_order_row",
                return_value={
                    "status": "Ready for Delivery",
                    "current_production_stage": "PST-SAND",
                },
            ),
            patch.object(permissions, "_has", return_value=False),
            patch.object(
                permissions.frappe.db,
                "get_value",
                return_value={
                    "assigned_to": "worker@example.com",
                    "operational_role": "عامل تقشيط",
                    "stage_type": "Sanding",
                    "status": "Completed",
                },
                create=True,
            ),
            patch.object(
                permissions,
                "_worker_operational_roles",
                return_value=("عامل تقشيط",),
            ),
        ):
            self.assertFalse(
                permissions.worker_can_view_order(
                    "worker@example.com",
                    "DCO-LAST-STAGE",
                )
            )

        with (
            patch.object(permissions, "_requires_assigned_scope", return_value=True),
            patch.object(
                permissions,
                "_dispatched_order_row",
                return_value={
                    "status": "Ready for Delivery",
                    "current_production_stage": "PST-SAND",
                },
            ),
            patch.object(permissions, "_has", return_value=True),
            patch.object(
                permissions.frappe.db,
                "exists",
                return_value=True,
                create=True,
            ),
        ):
            self.assertTrue(
                permissions.worker_can_view_order(
                    "worker@example.com",
                    "DCO-LAST-STAGE",
                )
            )

    def test_custom_actions_require_their_owner_and_explicit_capability(self) -> None:
        order = SimpleNamespace(name="DCO-TEST")
        plan = SimpleNamespace(door_cutting_order="DCO-TEST")

        with (
            patch.object(
                permissions,
                "_has",
                side_effect=lambda _user, capability: capability == "recalculate_plan",
            ),
            patch.object(permissions, "_requires_assigned_scope", return_value=False),
        ):
            self.assertFalse(
                permissions.door_cutting_order_has_permission(
                    order,
                    user="worker@example.com",
                    ptype="recalculate_plan",
                )
            )
            self.assertTrue(
                permissions.cutting_plan_has_permission(
                    plan,
                    user="worker@example.com",
                    ptype="recalculate_plan",
                )
            )
            self.assertFalse(
                permissions.cutting_plan_has_permission(
                    plan,
                    user="worker@example.com",
                    ptype="view_costs",
                )
            )

    def test_legacy_permission_type_keyword_remains_compatible(self) -> None:
        order = SimpleNamespace(name="DCO-TEST")

        with (
            patch.object(permissions, "_has", return_value=True),
            patch.object(permissions, "_requires_assigned_scope", return_value=False),
        ):
            self.assertIs(
                permissions.door_cutting_order_has_permission(
                    order,
                    user="order@example.com",
                    permission_type="read",
                ),
                True,
            )

    def test_guest_read_is_denied_explicitly(self) -> None:
        order = SimpleNamespace(name="DCO-TEST")

        self.assertIs(
            permissions.door_cutting_order_has_permission(
                order,
                user="Guest",
                ptype="read",
            ),
            False,
        )


if __name__ == "__main__":
    unittest.main()
