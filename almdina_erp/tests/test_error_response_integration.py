"""Real Frappe serializer/database/logging checks; executed by the Bench gate."""

import json
from pathlib import Path
from uuid import uuid4

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils.response import report_error
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from almdina_erp.almdina_erp.infrastructure.frappe.error_response import attach_error_response


class TestErrorResponseIntegration(FrappeTestCase):
    def test_private_staging_uses_native_file_ownership_without_role_bypass(self):
        from almdina_erp.almdina_erp.services.shop_floor_dxf_service import _validate_dxf_file_metadata

        frappe.set_user("Administrator")
        users = []
        for kind in ("owner", "other"):
            user = frappe.get_doc({
                "doctype": "User", "email": f"diagnostic-{kind}-{uuid4().hex[:10]}@example.invalid",
                "first_name": "Diagnostic " + kind, "send_welcome_email": 0,
                "user_type": "System User", "roles": [{"role": "System Manager"}],
            }).insert(ignore_permissions=True)
            users.append(user.name)
        file = frappe.get_doc({
            "doctype": "File", "file_name": f"diagnostic-{uuid4().hex}.dxf",
            "is_private": 1, "content": f"999\n{uuid4().hex}\n0\nEOF\n".encode(),
        }).insert(ignore_permissions=True)
        frappe.db.set_value("File", file.name, "owner", users[0])
        try:
            frappe.set_user(users[1])
            with self.assertRaises(frappe.PermissionError):
                _validate_dxf_file_metadata(file.file_url)
            frappe.set_user(users[0])
            url, row = _validate_dxf_file_metadata(file.file_url)
            self.assertEqual(url, file.file_url)
            self.assertEqual(row.name, file.name)
            explicit_url, explicit_row = _validate_dxf_file_metadata(file.file_url, file_id=file.name)
            self.assertEqual(explicit_url, file.file_url)
            self.assertEqual(explicit_row.name, file.name)
        finally:
            frappe.set_user("Administrator")
            frappe.delete_doc("File", file.name, ignore_permissions=True)

    def test_public_envelope_survives_native_serialization_and_database_rollback(self):
        savepoint = "error_diagnostics_" + uuid4().hex[:12]
        frappe.db.savepoint(savepoint)
        todo = frappe.get_doc({"doctype": "ToDo", "description": savepoint}).insert(ignore_permissions=True)
        previous_response = frappe.local.response
        previous_request = getattr(frappe.local, "request", None)
        previous_log = frappe.local.message_log
        try:
            frappe.local.response = frappe._dict()
            frappe.local.message_log = []
            frappe.local.request = Request(EnvironBuilder(
                path="/api/method/test.operation", method="POST",
                headers={"Accept": "application/json"},
            ).get_environ())
            attach_error_response(
                operation="test_validation", title="Validation",
                issues=[{"code": "TEST_REJECTION", "problem": "Invalid input", "target": "", "action": "Correct input"}],
                outcome="rejected",
            )
            reference = frappe.local.response["almdina_error"]["request_reference"]
            try:
                frappe.throw("Invalid input")
            except frappe.ValidationError:
                response = report_error(417)
            else:
                self.fail("Frappe must still raise the original validation exception")
            frappe.db.rollback(save_point=savepoint)
            self.assertFalse(frappe.db.exists("ToDo", todo.name))
            payload = json.loads(response.get_data(as_text=True))
            self.assertEqual(response.status_code, 417)
            self.assertEqual(payload["exc_type"], "ValidationError")
            self.assertEqual(payload["almdina_error"]["outcome"], "rejected")
            self.assertEqual(payload["almdina_error"]["request_reference"], reference)
            self.assertTrue(payload["_server_messages"], "older Desk clients retain native feedback")
            self.assertTrue(reference)
            logger = frappe.logger("almdina_errors", allow_site=True)
            files = []
            for handler in logger.handlers:
                handler.flush()
                filename = getattr(handler, "baseFilename", None)
                if filename:
                    files.append(Path(filename))
            self.assertTrue(any(reference in path.read_text() for path in files if path.exists()))
        finally:
            frappe.local.response = previous_response
            frappe.local.message_log = previous_log
            frappe.local.request = previous_request
