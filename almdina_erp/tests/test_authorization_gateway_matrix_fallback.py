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

        permission_type_module = types.ModuleType(
            "frappe.core.doctype.permission_type.permission_type"
        )
        permission_type_module.get_doctype_ptype_map = lambda: {}

        class FakeRepository:
            @staticmethod
            def user_roles(_user):
                return frozenset({"Arbitrary Operational Role"})

            @staticmethod
            def role_state(_role):
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
            "frappe.core": types.ModuleType("frappe.core"),
            "frappe.core.doctype": types.ModuleType("frappe.core.doctype"),
            "frappe.core.doctype.permission_type": types.ModuleType(
                "frappe.core.doctype.permission_type"
            ),
            "frappe.core.doctype.permission_type.permission_type": (
                permission_type_module
            ),
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
            module._registered_permission_types = lambda: {}
            module._matrix_repository = lambda: (
                FakeRepository(),
                repository_module.PROTECTED_ROLES,
            )
            return module
        finally:
            for name, original in previous.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original

    def test_console_matrix_is_runtime_fallback_for_any_role(self) -> None:
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

    def test_document_fallback_keeps_native_read_scope(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
