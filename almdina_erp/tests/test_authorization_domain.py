from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.security.permission_context import (
    PERMISSION_CONTEXT_VERSION,
    build_permission_context,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    ALL_CAPABILITIES,
    CAPABILITY_CATALOG,
    CUSTOM_PERMISSION_DEFINITIONS,
    Capability,
    capability_definition,
    capability_flags,
    has_capability,
    is_order_entry_profile,
    is_shop_floor_only,
    normalize_capabilities,
)


class TestAuthorizationDomain(unittest.TestCase):
    def test_catalog_contains_every_capability_once(self) -> None:
        self.assertEqual(set(CAPABILITY_CATALOG), ALL_CAPABILITIES)
        self.assertEqual(
            len({definition.permission_type for definition in CUSTOM_PERMISSION_DEFINITIONS}),
            len(CUSTOM_PERMISSION_DEFINITIONS),
        )

    def test_standard_rights_reuse_frappe_permissions(self) -> None:
        create = capability_definition(Capability.CREATE_ORDER)
        edit = capability_definition(Capability.EDIT_ORDER)
        self.assertEqual(create.permission_type, "create")
        self.assertEqual(edit.permission_type, "write")
        self.assertFalse(create.custom)
        self.assertFalse(edit.custom)

    def test_drawing_capabilities_are_custom_and_order_scoped(self) -> None:
        for capability in (
            Capability.RECALCULATE_PLAN,
            Capability.EXPORT_DXF,
            Capability.UPLOAD_DXF,
            Capability.REPLACE_DXF,
            Capability.APPROVE_DXF,
        ):
            with self.subTest(capability=capability):
                definition = capability_definition(capability)
                self.assertTrue(definition.custom)
                self.assertEqual(definition.applies_to, "Door Cutting Order")
                expected_category = (
                    "cutting_plan"
                    if capability == Capability.RECALCULATE_PLAN
                    else "drawing"
                )
                self.assertEqual(definition.category, expected_category)

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

    def test_permission_context_uses_resolved_grants(self) -> None:
        context = build_permission_context(
            {"عامل رسم"},
            {Capability.UPLOAD_DXF, Capability.APPROVE_DXF},
        )
        self.assertEqual(context["version"], PERMISSION_CONTEXT_VERSION)
        self.assertEqual(context["profile"], "shop_floor")
        self.assertTrue(context["capabilities"][Capability.UPLOAD_DXF])
        self.assertTrue(context["capabilities"][Capability.APPROVE_DXF])
        self.assertFalse(context["capabilities"][Capability.VIEW_COSTS])
        self.assertNotIn("roles", context)

    def test_profiles_share_the_same_capability_contract(self) -> None:
        contexts = [
            build_permission_context({"Order Entry"}, {Capability.CREATE_ORDER}),
            build_permission_context({"عامل CNC"}, {Capability.EXPORT_DXF}),
            build_permission_context({"Production Manager"}, {Capability.VIEW_COSTS}),
        ]
        self.assertEqual(
            [context["profile"] for context in contexts],
            ["order_entry", "shop_floor", "full"],
        )
        for context in contexts:
            self.assertEqual(set(context["capabilities"]), ALL_CAPABILITIES)

    def test_navigation_profiles_remain_role_based_only(self) -> None:
        self.assertTrue(is_order_entry_profile({"Order Entry"}))
        self.assertFalse(is_order_entry_profile({"Order Entry", "System Manager"}))
        self.assertTrue(is_shop_floor_only({"عامل رسم"}))
        self.assertFalse(is_shop_floor_only({"عامل رسم", "Production Manager"}))

    def test_unknown_capability_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown capability"):
            capability_definition("unknown")
        with self.assertRaisesRegex(ValueError, "Unknown capability"):
            has_capability(set(), "unknown")


if __name__ == "__main__":
    unittest.main()
