from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.domain.security.role_management import (
    RoleAction,
    RoleFacts,
    decide_role_action,
    effective_capabilities,
    new_role_definition,
    normalize_role_capabilities,
)


class TestRoleManagementDomain(unittest.TestCase):
    def test_new_role_has_no_implicit_permissions(self) -> None:
        role = new_role_definition(
            name="  عامل   الرسم  ",
            description=" مسؤول تجهيز الرسومات وملفات DXF ",
        )
        self.assertEqual(role.name, "عامل الرسم")
        self.assertEqual(
            role.description,
            "مسؤول تجهيز الرسومات وملفات DXF",
        )
        self.assertTrue(role.enabled)
        self.assertTrue(role.is_almdina_role)

        state = normalize_role_capabilities(
            {},
            allowed_capabilities={"view_orders", "upload_dxf"},
        )
        self.assertEqual(
            state,
            {"upload_dxf": False, "view_orders": False},
        )

    def test_role_matrix_never_enables_hidden_dependencies(self) -> None:
        state = normalize_role_capabilities(
            {"upload_dxf": True},
            allowed_capabilities={
                "view_orders",
                "view_drawing_workspace",
                "upload_dxf",
            },
        )
        self.assertTrue(state["upload_dxf"])
        self.assertFalse(state["view_orders"])
        self.assertFalse(state["view_drawing_workspace"])

    def test_unknown_capabilities_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown capabilities"):
            normalize_role_capabilities(
                {"non_existing_action": True},
                allowed_capabilities={"view_orders"},
            )

    def test_user_permissions_are_the_union_of_all_roles(self) -> None:
        granted = effective_capabilities(
            (
                {"view_orders": True, "upload_dxf": False},
                {"upload_dxf": True, "approve_dxf": False},
            )
        )
        self.assertEqual(granted, frozenset({"view_orders", "upload_dxf"}))

    def test_protected_framework_roles_cannot_be_created_or_deleted(self) -> None:
        create = decide_role_action(
            action=RoleAction.CREATE,
            facts=RoleFacts(role_name="System Manager", role_exists=False),
        )
        self.assertFalse(create.allowed)
        self.assertEqual(create.code, "protected_role")

        delete = decide_role_action(
            action=RoleAction.DELETE,
            facts=RoleFacts(role_name="Desk User", role_exists=True),
        )
        self.assertFalse(delete.allowed)
        self.assertEqual(delete.code, "protected_role")

    def test_disabled_role_cannot_be_assigned(self) -> None:
        decision = decide_role_action(
            action=RoleAction.ASSIGN,
            facts=RoleFacts(
                role_name="عامل الرسم",
                role_exists=True,
                role_enabled=False,
            ),
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "disabled_role")

    def test_role_in_use_cannot_be_deleted(self) -> None:
        decision = decide_role_action(
            action=RoleAction.DELETE,
            facts=RoleFacts(
                role_name="عامل CNC",
                assigned_users=1,
                production_routing_references=2,
                permission_count=4,
            ),
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "role_in_use")

    def test_empty_unused_custom_role_can_be_deleted(self) -> None:
        decision = decide_role_action(
            action=RoleAction.DELETE,
            facts=RoleFacts(role_name="دور تجريبي"),
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.code, "allowed")


if __name__ == "__main__":
    unittest.main()
