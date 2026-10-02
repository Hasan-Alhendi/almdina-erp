from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.application.security.legacy_permission_bootstrap import (
    legacy_role_state,
)
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
from almdina_erp.patches.v1_0.retire_canonical_permission_runtime import (
    execute as retire_canonical_permission_runtime,
)


ROLE = "Almdina Cutover Hardening Role"
SETTINGS_ROLE = "Almdina Explicit Settings Sync Test"
MIGRATION_PERSONAS = (
    "Order Entry",
    "Production Manager",
    "Accounts Management",
    "Cutting Operator",
    "Edge Operator",
    "عامل رسم",
)


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
        for role in MIGRATION_PERSONAS:
            self._clear_role(role)
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

    def test_deny_all_survives_sync_and_migrate_despite_privileged_canonical_mirror(
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
        # Explicit post-cutover revoke: live DocPerm is deny-all while the
        # retired mirror still holds privileged historical grants.
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
        self.assertTrue(canonical.read(ROLE)[Capability.VIEW_COSTS])
        self.assertTrue(canonical.read(ROLE)[Capability.EDIT_COST_SETTINGS])

        sync_permission_types()
        self._assert_deny_all(ROLE)

        sync_permission_types()
        self._assert_deny_all(ROLE)

        _sync_security_foundation()
        self._assert_deny_all(ROLE)

    def test_one_time_retire_bridge_then_live_docperm_wins_permanently(self) -> None:
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

        # Historical mirror still has grants, but recurring paths must ignore it.
        self.assertTrue(canonical.read(ROLE)[Capability.VIEW_COSTS])

    def test_legacy_persona_expected_sets_migrate_once_into_docperm(self) -> None:
        canonical = CanonicalPermissionStateRepository()
        reader = CustomDocPermCapabilityReader()

        for role in MIGRATION_PERSONAS:
            self._ensure_role(role)
            self._clear_role(role)
            expected = legacy_role_state(role)
            canonical.save(role, expected)

        retire_canonical_permission_runtime()

        for role in MIGRATION_PERSONAS:
            expected = legacy_role_state(role)
            actual = reader.role_capabilities(role)
            mismatched = sorted(
                key
                for key in sorted(expected)
                if bool(expected[key]) != bool(actual.get(key))
            )
            self.assertEqual(
                mismatched,
                [],
                f"migration parity failed for {role}: {mismatched}",
            )

        # After cutover, mutating live DocPerm must stick across sync.
        ProjectedPermissionMatrixRepository().save_role_state("Order Entry", {})
        sync_permission_types()
        self._assert_deny_all("Order Entry")
        self.assertTrue(
            canonical.read("Order Entry")[Capability.VIEW_ORDERS],
            "canonical history must remain untouched after live deny-all",
        )


__all__ = ["TestCanonicalPermissionCutoverHardeningIntegration"]
