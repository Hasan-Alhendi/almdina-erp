from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "native_document_permissions.py"
)
BASE_MODULE = "almdina_erp.permissions"


def load_native_permissions():
    fake_frappe = types.ModuleType("frappe")
    fake_frappe.session = SimpleNamespace(user="worker@example.com")

    fake_base = types.ModuleType(BASE_MODULE)
    fake_base.door_cutting_order_has_permission = lambda *_args, **_kwargs: True
    fake_base.production_stage_has_permission = lambda *_args, **_kwargs: True
    fake_base.production_incident_has_permission = lambda *_args, **_kwargs: True
    fake_base.cutting_plan_has_permission = lambda *_args, **_kwargs: True
    fake_base.replacement_piece_has_permission = lambda *_args, **_kwargs: True
    fake_base._requires_assigned_scope = lambda _user: True
    fake_base.worker_can_view_order = lambda _user, _order: False

    previous_frappe = sys.modules.get("frappe")
    previous_base = sys.modules.get(BASE_MODULE)
    sys.modules["frappe"] = fake_frappe
    sys.modules[BASE_MODULE] = fake_base
    try:
        spec = importlib.util.spec_from_file_location(
            "_almdina_native_document_permissions_test",
            MODULE_PATH,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("Could not load native document permission boundary")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # A real Bench may already have almdina_erp.permissions cached as a
        # package attribute. Bind the test double directly so the same harness
        # is deterministic both with and without an initialized Frappe app.
        module.base_permissions = fake_base
        module._test_base = fake_base
        return module
    finally:
        if previous_frappe is None:
            sys.modules.pop("frappe", None)
        else:
            sys.modules["frappe"] = previous_frappe
        if previous_base is None:
            sys.modules.pop(BASE_MODULE, None)
        else:
            sys.modules[BASE_MODULE] = previous_base


native_permissions = load_native_permissions()


class TestNativeDocumentPermissions(unittest.TestCase):
    def test_unassigned_floor_worker_cannot_write_known_order_id(self) -> None:
        order = SimpleNamespace(name="DCO-OTHER")
        base = native_permissions._test_base
        with (
            patch.object(base, "door_cutting_order_has_permission", return_value=True),
            patch.object(base, "_requires_assigned_scope", return_value=True),
            patch.object(base, "worker_can_view_order", return_value=False),
        ):
            self.assertFalse(
                native_permissions.door_cutting_order_has_permission(
                    order,
                    user="worker@example.com",
                    ptype="write",
                )
            )

    def test_assigned_floor_worker_can_write_authorized_order(self) -> None:
        order = SimpleNamespace(name="DCO-MINE")
        base = native_permissions._test_base
        with (
            patch.object(base, "door_cutting_order_has_permission", return_value=True),
            patch.object(base, "_requires_assigned_scope", return_value=True),
            patch.object(base, "worker_can_view_order", return_value=True),
        ):
            self.assertTrue(
                native_permissions.door_cutting_order_has_permission(
                    order,
                    user="worker@example.com",
                    ptype="write",
                )
            )

    def test_order_author_can_create_without_existing_assignment(self) -> None:
        order = SimpleNamespace(name=None)
        base = native_permissions._test_base
        with (
            patch.object(base, "door_cutting_order_has_permission", return_value=True),
            patch.object(base, "_requires_assigned_scope", return_value=True),
            patch.object(base, "worker_can_view_order") as scope_check,
        ):
            self.assertTrue(
                native_permissions.door_cutting_order_has_permission(
                    order,
                    user="entry@example.com",
                    ptype="create",
                )
            )
            scope_check.assert_not_called()

    def test_native_order_lifecycle_mutations_are_command_only(self) -> None:
        order = SimpleNamespace(name="DCO-TEST")
        for ptype in ("delete", "submit", "cancel", "amend"):
            with self.subTest(ptype=ptype):
                self.assertFalse(
                    native_permissions.door_cutting_order_has_permission(
                        order,
                        user="manager@example.com",
                        ptype=ptype,
                    )
                )

    def test_supporting_documents_deny_all_native_mutations(self) -> None:
        doc = SimpleNamespace(name="ROW-1")
        delegates = (
            native_permissions.production_stage_has_permission,
            native_permissions.production_incident_has_permission,
            native_permissions.cutting_plan_has_permission,
            native_permissions.replacement_piece_has_permission,
        )
        for permission in delegates:
            for ptype in ("create", "write", "delete", "submit", "cancel", "amend"):
                with self.subTest(permission=permission.__name__, ptype=ptype):
                    self.assertFalse(
                        permission(doc, user="worker@example.com", ptype=ptype)
                    )

    def test_read_still_delegates_to_existing_scoped_policy(self) -> None:
        doc = SimpleNamespace(name="ROW-1")
        base = native_permissions._test_base
        with patch.object(
            base,
            "cutting_plan_has_permission",
            return_value=False,
        ) as delegate:
            self.assertFalse(
                native_permissions.cutting_plan_has_permission(
                    doc,
                    user="worker@example.com",
                    ptype="read",
                )
            )
            delegate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
