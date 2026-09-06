from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from almdina_erp.almdina_erp.services.notes_service import _customer_has_read_access


class TestNotesPermissionProbeRuntime(IntegrationTestCase):
    def test_customer_probe_suppresses_nested_permission_messages_and_restores_flag(self) -> None:
        original_messages = list(frappe.local.message_log)
        original_mute = frappe.flags.get("mute_messages", False)
        captured_kwargs: list[dict] = []

        def noisy_permission_check(*args, **kwargs):
            captured_kwargs.append(dict(kwargs))
            # Reproduce the Frappe v16 failure mode: an internal permission branch
            # emits a user-facing message even though the outer probe requested
            # print_logs=False.
            frappe.msgprint("permission-probe-noise")
            return False

        try:
            frappe.flags.mute_messages = False
            with patch("frappe.permissions.has_permission", side_effect=noisy_permission_check):
                self.assertFalse(_customer_has_read_access(frappe._dict(name="TEST-CUSTOMER")))

            self.assertEqual(frappe.local.message_log, original_messages)
            self.assertFalse(frappe.flags.mute_messages)
            self.assertEqual(len(captured_kwargs), 1)
            self.assertIs(captured_kwargs[0].get("print_logs"), False)
        finally:
            frappe.flags.mute_messages = original_mute
            frappe.local.message_log = original_messages
