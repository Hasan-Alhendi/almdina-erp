from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.security.navigation_context import (
    WORKSPACE_CONTROL_CENTER,
    WORKSPACE_MAIN,
    WORKSPACE_SETTINGS,
    WORKSPACE_SHOP_FLOOR,
    build_navigation_context,
)
from almdina_erp.almdina_erp.application.security.permission_context import (
    PERMISSION_CONTEXT_VERSION,
    build_permission_context,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    ALL_CAPABILITIES,
    CAPABILITY_CATALOG,
    CUSTOM_PERMISSION_DEFINITIONS,
    PRODUCTION_OPERATOR_CAPABILITIES,
    Capability,
    capability_definition,
    capability_flags,
    has_capability,
    normalize_capabilities,
)


class TestAuthorizationDomain(unittest.TestCase):
    def test_catalog_contains_every_capability_once(self) -> None:
        self.assertEqual(set(CAPABILITY_CATALOG), ALL_CAPABILITIES)
        self.assertEqual(len({definition.permission_type for definition in CUSTOM_PERMISSION_DEFINITIONS}), len(CUSTOM_PERMISSION_DEFINITIONS))

    def test_standard_rights_reuse_frappe_permissions(self) -> None:
        view = capability_definition(Capability.VIEW_ORDERS)
        create = capability_definition(Capability.CREATE_ORDER)
        edit = capability_definition(Capability.EDIT_ORDER)
        self.assertEqual(view.permission_type, "read")
        self.assertEqual(create.permission_type, "create")
        self.assertEqual(edit.permission_type, "write")
        self.assertFalse(view.custom)
        self.assertFalse(create.custom)
        self.assertFalse(edit.custom)

    def test_drawing_capabilities_are_custom_and_order_scoped(self) -> None:
        for capability in (Capability.RECALCULATE_PLAN, Capability.EXPORT_DXF, Capability.UPLOAD_DXF, Capability.REPLACE_DXF, Capability.APPROVE_DXF):
            with self.subTest(capability=capability):
                definition = capability_definition(capability)
                self.assertTrue(definition.custom)
                self.assertEqual(definition.applies_to, "Door Cutting Order")

    def test_capability_flags_are_complete_and_fail_closed(self) -> None:
        flags = capability_flags({Capability.UPLOAD_DXF, Capability.APPROVE_DXF})
        self.assertEqual(list(flags), sorted(ALL_CAPABILITIES))
        self.assertTrue(flags[Capability.UPLOAD_DXF])
        self.assertTrue(flags[Capability.APPROVE_DXF])
        self.assertFalse(flags[Capability.VIEW_COSTS])
        self.assertTrue(all(isinstance(value, bool) for value in flags.values()))

    def test_capabilities_are_grants_not_role_names(self) -> None:
        grants = normalize_capabilities({Capability.UPLOAD_DXF})
        self.assertTrue(has_capability(grants, Capability.UPLOAD_DXF))
        self.assertFalse(has_capability(grants, Capability.APPROVE_DXF))
        with self.assertRaisesRegex(ValueError, "Unknown capabilities"):
            normalize_capabilities({"عامل رسم"})

    def test_permission_context_ignores_roles_and_uses_grants(self) -> None:
        first = build_permission_context({"Role A"}, {Capability.UPLOAD_DXF, Capability.APPROVE_DXF})
        second = build_permission_context({"Completely Different Role"}, {Capability.UPLOAD_DXF, Capability.APPROVE_DXF})
        self.assertEqual(first, second)
        self.assertEqual(first["version"], PERMISSION_CONTEXT_VERSION)
        self.assertEqual(first["profile"], "shop_floor")
        self.assertTrue(first["capabilities"][Capability.UPLOAD_DXF])
        self.assertTrue(first["navigation"]["shared_shell"])
        self.assertNotIn("roles", first)

    def test_operator_navigation_preserves_shared_shell_with_read_grant(self) -> None:
        navigation = build_navigation_context({Capability.VIEW_ORDERS, Capability.START_ASSIGNED_STAGE, Capability.HANDOFF_ASSIGNED_STAGE, Capability.VIEW_CUTTING_PLAN})
        self.assertEqual(navigation["profile"], "shop_floor")
        self.assertEqual(navigation["home_page"], "shop-floor-inbox")
        self.assertEqual(navigation["workspaces"], [WORKSPACE_SHOP_FLOOR])
        self.assertTrue(navigation["shared_shell"])
        self.assertTrue(navigation["sections"]["production"])

    def test_no_grants_leave_other_desk_users_untouched(self) -> None:
        navigation = build_navigation_context(set())
        self.assertEqual(navigation["profile"], "shared")
        self.assertFalse(navigation["shared_shell"])
        self.assertFalse(navigation["app_only"])
        self.assertEqual(navigation["home_page"], "")
        self.assertEqual(navigation["default_route"], "")
        self.assertEqual(navigation["workspaces"], [])

    def test_capabilities_expand_workspaces_without_changing_application(self) -> None:
        navigation = build_navigation_context({Capability.VIEW_ORDERS, Capability.REASSIGN_WORKER, Capability.EDIT_FACTORY_PRODUCTION_CONTROLS})
        self.assertEqual(navigation["profile"], "full")
        self.assertEqual(navigation["home_page"], "")
        self.assertEqual(navigation["default_route"], "/desk")
        self.assertIn(WORKSPACE_MAIN, navigation["workspaces"])
        self.assertIn(WORKSPACE_SHOP_FLOOR, navigation["workspaces"])
        self.assertIn(WORKSPACE_CONTROL_CENTER, navigation["workspaces"])
        self.assertIn(WORKSPACE_SETTINGS, navigation["workspaces"])
        self.assertTrue(navigation["app_only"])

    def test_operator_group_has_no_role_names(self) -> None:
        self.assertTrue(PRODUCTION_OPERATOR_CAPABILITIES)
        for value in PRODUCTION_OPERATOR_CAPABILITIES:
            self.assertIn(value, ALL_CAPABILITIES)
            self.assertNotIn("عامل", value)

    def test_unknown_capability_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown capability"):
            capability_definition("unknown")
        with self.assertRaisesRegex(ValueError, "Unknown capability"):
            has_capability(set(), "unknown")


if __name__ == "__main__":
    unittest.main()
