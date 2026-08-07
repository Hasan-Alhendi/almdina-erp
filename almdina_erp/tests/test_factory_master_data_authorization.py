from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.security.navigation_context import (
    WORKSPACE_GO_LIVE,
    WORKSPACE_REPORTS,
    WORKSPACE_SETTINGS,
    build_navigation_context,
)
from almdina_erp.almdina_erp.application.security.permission_matrix import (
    normalize_capability_state,
    standard_permission_projection,
    validate_capability_dependencies,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.domain.security.factory_settings import (
    decide_settings_update,
    expand_factory_settings_capabilities,
    settings_context,
)


class TestFactoryMasterDataAuthorization(unittest.TestCase):
    def test_granular_settings_update_is_field_scoped(self) -> None:
        cutting = decide_settings_update(
            {Capability.EDIT_FACTORY_CUTTING_DEFAULTS},
            {"default_kerf_mm": 3, "default_packing_mode": "Auto Pro"},
        )
        self.assertTrue(cutting.allowed)

        denied = decide_settings_update(
            {Capability.EDIT_FACTORY_CUTTING_DEFAULTS},
            {"default_cutting_cost_per_board_usd": 2},
        )
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.code, "missing_capability")

    def test_factory_settings_grants_are_exact_and_not_expanded(self) -> None:
        selected = {
            Capability.VIEW_FACTORY_SETTINGS,
            Capability.EDIT_FACTORY_CUTTING_DEFAULTS,
        }
        expanded = expand_factory_settings_capabilities(selected)
        self.assertEqual(expanded, frozenset(selected))
        context = settings_context(expanded)
        self.assertTrue(context["can_view"])
        self.assertTrue(context["sections"]["cutting"]["editable"])
        self.assertFalse(context["sections"]["costing"]["editable"])
        self.assertFalse(context["sections"]["production"]["editable"])

    def test_permission_matrix_dependencies_are_required_but_never_auto_added(self) -> None:
        routing = normalize_capability_state(
            {Capability.DELETE_PRODUCTION_ROUTINGS: True}
        )
        self.assertTrue(routing[Capability.DELETE_PRODUCTION_ROUTINGS])
        self.assertFalse(routing[Capability.VIEW_PRODUCTION_ROUTINGS])
        with self.assertRaisesRegex(ValueError, "Missing required permissions"):
            validate_capability_dependencies(routing)

        edges = normalize_capability_state(
            {Capability.CREATE_EDGE_BANDING_TYPES: True}
        )
        self.assertFalse(edges[Capability.VIEW_EDGE_BANDING_TYPES])
        with self.assertRaisesRegex(ValueError, "Missing required permissions"):
            validate_capability_dependencies(edges)

        production_controls = normalize_capability_state(
            {Capability.EDIT_FACTORY_PRODUCTION_CONTROLS: True}
        )
        self.assertFalse(production_controls[Capability.VIEW_FACTORY_SETTINGS])
        self.assertFalse(production_controls[Capability.VIEW_PRODUCTION_ROUTINGS])
        with self.assertRaisesRegex(ValueError, "Missing required permissions"):
            validate_capability_dependencies(production_controls)

        valid = validate_capability_dependencies(
            {
                Capability.EDIT_FACTORY_PRODUCTION_CONTROLS: True,
                Capability.VIEW_FACTORY_SETTINGS: True,
                Capability.VIEW_PRODUCTION_ROUTINGS: True,
            }
        )
        self.assertTrue(valid[Capability.EDIT_FACTORY_PRODUCTION_CONTROLS])

    def test_standard_permission_projection_is_per_doctype(self) -> None:
        state = {
            Capability.VIEW_PRODUCTION_ROUTINGS: True,
            Capability.EDIT_PRODUCTION_ROUTINGS: True,
            Capability.VIEW_EDGE_BANDING_TYPES: True,
            Capability.DELETE_EDGE_BANDING_TYPES: True,
        }
        routing = standard_permission_projection("Production Routing", state)
        self.assertTrue(routing["read"])
        self.assertTrue(routing["write"])
        self.assertFalse(routing["create"])
        self.assertFalse(routing["delete"])

        edge = standard_permission_projection("Edge Banding Type", state)
        self.assertTrue(edge["read"])
        self.assertTrue(edge["delete"])
        self.assertFalse(edge["write"])

    def test_non_settings_administration_does_not_expose_settings_record(self) -> None:
        workforce = standard_permission_projection(
            "Almdina ERP Settings",
            {Capability.VIEW_USERS: True},
        )
        permissions = standard_permission_projection(
            "Almdina ERP Settings",
            {Capability.MANAGE_PERMISSIONS: True},
        )
        self.assertFalse(workforce["read"])
        self.assertFalse(permissions["read"])
        self.assertFalse(workforce["write"])

    def test_configuration_only_navigation_stays_in_settings_workspace(self) -> None:
        navigation = build_navigation_context(
            {Capability.VIEW_EDGE_BANDING_TYPES}
        )
        self.assertIn(WORKSPACE_SETTINGS, navigation["workspaces"])
        self.assertNotIn(WORKSPACE_REPORTS, navigation["workspaces"])
        self.assertNotIn(WORKSPACE_GO_LIVE, navigation["workspaces"])
        self.assertTrue(navigation["sections"]["master_data"])
        self.assertFalse(navigation["sections"]["administration"])

    def test_unknown_and_empty_settings_updates_fail_closed(self) -> None:
        grants = {Capability.VIEW_FACTORY_SETTINGS}
        unknown = decide_settings_update(
            grants,
            {"unknown_setting": 1},
        )
        self.assertFalse(unknown.allowed)
        self.assertEqual(unknown.code, "unknown_fields")
        empty = decide_settings_update(grants, {})
        self.assertFalse(empty.allowed)
        self.assertEqual(empty.code, "empty_update")


if __name__ == "__main__":
    unittest.main()
