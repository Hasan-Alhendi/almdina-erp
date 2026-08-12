from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

from almdina_erp.almdina_erp.domain.security.authorization import Capability


GATEWAY_PATH = (
    Path(__file__).resolve().parents[1]
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "authorization_gateway.py"
)
REPOSITORY_MODULE = (
    "almdina_erp.almdina_erp.infrastructure.frappe."
    "permission_matrix_repository"
)


class TestAuthorizationGatewayMatrixFallback(unittest.TestCase):
    def _load_gateway(self):
        fake_frappe = types.ModuleType("frappe")
        fake_frappe.session = types.SimpleNamespace(user="role.user@example.com")
        fake_frappe.local = types.SimpleNamespace()
        fake_frappe.PermissionError = PermissionError
        fake_frappe._ = lambda value: value
        fake_frappe.throw = lambda message, *_args: (_ for _ in ()).throw(
            PermissionError(message)
        )
        fake_frappe.has_permission = lambda target, permission_type, user=None: (
            permission_type == "read" and not isinstance(target, str)
        )

        class FakeRepository:
            @staticmethod
            def user_roles(_user):
                return frozenset(
                    {
                        "Arbitrary Operational Role",
                        "System Manager",
                        "Desk User",
                        "All",
                    }
                )

            @staticmethod
            def role_state(role):
                if role == "System Manager":
                    raise AssertionError("protected System Manager must never be resolved")
                return {
                    "capabilities": {
                        Capability.VIEW_ORDERS: True,
                        Capability.VIEW_COSTS: True,
                        Capability.VIEW_CUTTING_PLAN: True,
                    }
                }

        repository_module = types.ModuleType(REPOSITORY_MODULE)
        repository_module.FrappePermissionMatrixRepository = FakeRepository
        repository_module.PROTECTED_ROLES = frozenset({"All", "Guest", "Desk User"})

        replacements = {
            "frappe": fake_frappe,
            REPOSITORY_MODULE: repository_module,
        }
        previous = {name: sys.modules.get(name) for name in replacements}
        sys.modules.update(replacements)
        try:
            spec = importlib.util.spec_from_file_location(
                "_almdina_authorization_gateway_matrix_test",
                GATEWAY_PATH,
            )
            if spec is None or spec.loader is None:
                raise RuntimeError("Could not load authorization gateway")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module._matrix_repository = lambda: (
                FakeRepository(),
                module.PROTECTED_SYSTEM_ROLES,
            )
            return module
        finally:
            for name, original in previous.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original

    def test_console_matrix_is_runtime_authority_for_any_editable_role(self) -> None:
        gateway = self._load_gateway()

        granted = gateway.granted_capabilities("role.user@example.com")

        self.assertIn(Capability.VIEW_COSTS, granted)
        self.assertIn(Capability.VIEW_CUTTING_PLAN, granted)
        self.assertTrue(
            gateway.doctype_has_capability(
                Capability.VIEW_CUTTING_PLAN,
                user="role.user@example.com",
            )
        )

    def test_system_manager_is_never_a_factory_authority_source(self) -> None:
        gateway = self._load_gateway()

        class SystemManagerOnlyRepository:
            @staticmethod
            def user_roles(_user):
                return frozenset({"System Manager", "Desk User", "All"})

            @staticmethod
            def role_state(_role):
                raise AssertionError("protected platform roles must be skipped")

        gateway._matrix_repository = lambda: (
            SystemManagerOnlyRepository(),
            gateway.PROTECTED_SYSTEM_ROLES,
        )
        gateway.frappe.local.almdina_matrix_capabilities = {}

        self.assertEqual(
            gateway.granted_capabilities("system.manager@example.com"),
            frozenset(),
        )

    def test_document_capability_keeps_native_read_as_narrowing_scope(self) -> None:
        gateway = self._load_gateway()
        order = types.SimpleNamespace(doctype="Door Cutting Order")

        self.assertTrue(
            gateway.document_has_capability(
                order,
                Capability.VIEW_COSTS,
                user="role.user@example.com",
            )
        )
        self.assertFalse(
            gateway.document_has_capability(
                types.SimpleNamespace(doctype="Replacement Piece"),
                Capability.VIEW_COSTS,
                user="role.user@example.com",
            )
        )

    def test_stale_native_permission_cannot_authorize_an_empty_matrix(self) -> None:
        gateway = self._load_gateway()
        gateway.frappe.has_permission = lambda *_args, **_kwargs: True
        gateway._matrix_granted_capabilities = lambda _user: frozenset()

        self.assertEqual(
            gateway.granted_capabilities("empty@example.com"),
            frozenset(),
        )
        self.assertFalse(
            gateway.doctype_has_capability(
                Capability.VIEW_ORDERS,
                user="empty@example.com",
            )
        )
        self.assertFalse(
            gateway.document_has_capability(
                types.SimpleNamespace(doctype="Door Cutting Order"),
                Capability.VIEW_COSTS,
                user="empty@example.com",
            )
        )


if __name__ == "__main__":
    unittest.main()
