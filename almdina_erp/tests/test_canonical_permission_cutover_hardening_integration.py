from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.canonical_permission_state_repository import (
    CanonicalPermissionStateRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.custom_docperm_capability_reader import (
    CustomDocPermCapabilityReader,
)
from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)
from almdina_erp.almdina_erp.infrastructure.frappe.projected_permission_matrix_repository import (
    ProjectedPermissionMatrixRepository,
)
from almdina_erp.lifecycle import _sync_security_foundation
from almdina_erp.patches.v1_0.reset_canonical_permission_states import (
    execute as reset_canonical_permission_states,
)
from almdina_erp.patches.v1_0.retire_canonical_permission_runtime import (
    execute as retire_canonical_permission_runtime,
)


ROLE = "Almdina Cutover Hardening Role"
SETTINGS_ROLE = "Almdina Explicit Settings Sync Test"


class TestCanonicalPermissionCutoverHardeningIntegration(FrappeTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        sync_permission_types()
        self._ensure_role(ROLE)
        self._clear_role(ROLE)
        self._ensure_role(SETTINGS_ROLE)
        self._clear_role(SETTINGS_ROLE)

    def tearDown(self):
        frappe.set_user("Administrator")
        self._clear_role(ROLE)
        self._clear_role(SETTINGS_ROLE)
        for role in (ROLE, SETTINGS_ROLE):
            if frappe.db.exists("Role", role):
                frappe.delete_doc("Role", role, force=True, ignore_permissions=True)
        frappe.clear_cache()
        super().tearDown()

    @staticmethod
    def _ensure_role(role: str) -> None:
        if not frappe.db.exists("Role", role):
            frappe.get_doc(
                {"doctype": "Role", "role_name": role, "desk_access": 1}
            ).insert(ignore_permissions=True)

    @staticmethod
    def _clear_role(role: str) -> None:
        frappe.db.delete("Custom DocPerm", {"role": role})
        frappe.db.delete("Almdina Role Capability State", {"role": role})

    def _assert_deny_all(self, role: str) -> None:
        state = CustomDocPermCapabilityReader().role_capabilities(role)
        self.assertFalse(
            any(state.values()),
            f"expected deny-all for {role}, got {[k for k, v in state.items() if v]}",
        )

    def _assert_explicit_settings_view_survives_recurring_sync(
        self, companion_capability: str
    ) -> None:
        repository = ProjectedPermissionMatrixRepository()
        reader = CustomDocPermCapabilityReader()
        repository.save_role_state(
            SETTINGS_ROLE,
            {
                companion_capability: True,
                Capability.VIEW_FACTORY_SETTINGS: True,
            },
        )

        def assert_preserved() -> None:
            state = reader.role_capabilities(SETTINGS_ROLE)
            self.assertTrue(state[companion_capability], companion_capability)
            self.assertTrue(
                state[Capability.VIEW_FACTORY_SETTINGS],
                Capability.VIEW_FACTORY_SETTINGS,
            )

        assert_preserved()
        sync_permission_types()
        assert_preserved()
        sync_permission_types()
        assert_preserved()
        _sync_security_foundation()
        assert_preserved()

    def test_explicit_settings_view_survives_sync_with_manage_permissions(self) -> None:
        self._assert_explicit_settings_view_survives_recurring_sync(
            Capability.MANAGE_PERMISSIONS
        )

    def test_explicit_settings_view_survives_sync_with_workforce_capability(self) -> None:
        self._assert_explicit_settings_view_survives_recurring_sync(
            Capability.VIEW_USERS
        )

    def test_deny_all_survives_recurring_sync_despite_privileged_canonical_mirror(
        self,
    ) -> None:
        repository = ProjectedPermissionMatrixRepository()
        canonical = CanonicalPermissionStateRepository()

        repository.save_role_state(
            ROLE,
            {
                Capability.VIEW_COSTS: True,
                Capability.EDIT_COST_SETTINGS: True,
                Capability.VIEW_ORDERS: True,
            },
        )
        repository.save_role_state(ROLE, {})
        canonical.save(
            ROLE,
            {
                Capability.VIEW_COSTS: True,
                Capability.EDIT_COST_SETTINGS: True,
                Capability.VIEW_ORDERS: True,
            },
        )
        self._assert_deny_all(ROLE)

        sync_permission_types()
        self._assert_deny_all(ROLE)
        sync_permission_types()
        self._assert_deny_all(ROLE)
        _sync_security_foundation()
        self._assert_deny_all(ROLE)

    def test_one_time_retire_bridge_is_role_name_agnostic(self) -> None:
        canonical = CanonicalPermissionStateRepository()
        repository = ProjectedPermissionMatrixRepository()
        reader = CustomDocPermCapabilityReader()

        expected = {
            Capability.VIEW_ORDERS: True,
            Capability.VIEW_COSTS: True,
            Capability.EDIT_COST_SETTINGS: True,
            Capability.DISPATCH_ORDER: True,
        }
        canonical.save(ROLE, expected)
        frappe.db.delete("Custom DocPerm", {"role": ROLE})

        retire_canonical_permission_runtime()

        bridged = reader.role_capabilities(ROLE)
        for capability, enabled in expected.items():
            self.assertEqual(bool(bridged.get(capability)), enabled, capability)

        repository.save_role_state(ROLE, {})
        self._assert_deny_all(ROLE)
        sync_permission_types()
        self._assert_deny_all(ROLE)
        _sync_security_foundation()
        self._assert_deny_all(ROLE)

        self.assertTrue(canonical.read(ROLE)[Capability.VIEW_COSTS])

    def test_reset_then_retire_cannot_resurrect_historical_grants(self) -> None:
        canonical = CanonicalPermissionStateRepository()
        repository = ProjectedPermissionMatrixRepository()
        privileged = {
            Capability.VIEW_ORDERS: True,
            Capability.VIEW_COSTS: True,
            Capability.EDIT_COST_SETTINGS: True,
            Capability.DISPATCH_ORDER: True,
        }
        canonical.save(ROLE, privileged)
        repository.save_role_state(ROLE, privileged)

        self.assertTrue(any(canonical.read(ROLE).values()))
        self.assertTrue(
            any(CustomDocPermCapabilityReader().role_capabilities(ROLE).values())
        )

        reset_canonical_permission_states()

        self.assertFalse(any(canonical.read(ROLE).values()))
        self._assert_deny_all(ROLE)

        retire_canonical_permission_runtime()

        self.assertFalse(any(canonical.read(ROLE).values()))
        self._assert_deny_all(ROLE)


__all__ = ["TestCanonicalPermissionCutoverHardeningIntegration"]
