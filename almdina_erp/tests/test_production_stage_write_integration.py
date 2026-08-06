from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.infrastructure.frappe.production_stage_write_guard import (
    internal_stage_write,
    is_internal_stage_write,
)


class TestProductionStageWriteIntegration(FrappeTestCase):
    @staticmethod
    def _stage():
        stage = frappe.new_doc("Production Stage")
        stage.sequence = 10
        stage.status = "Pending"
        return stage

    def test_direct_document_validation_is_rejected(self) -> None:
        stage = self._stage()

        with self.assertRaisesRegex(frappe.PermissionError, "system-managed"):
            stage.run_method("validate")

    def test_ignore_permissions_does_not_bypass_the_application_boundary(self) -> None:
        stage = self._stage()
        stage.flags.ignore_permissions = True

        with self.assertRaisesRegex(frappe.PermissionError, "system-managed"):
            stage.run_method("validate")

    def test_authorized_repository_context_is_transient(self) -> None:
        stage = self._stage()

        with internal_stage_write(stage):
            self.assertTrue(is_internal_stage_write(stage))
            stage.run_method("validate")
            stage.run_method("before_trash")

        self.assertFalse(is_internal_stage_write(stage))
        with self.assertRaisesRegex(frappe.PermissionError, "system-managed"):
            stage.run_method("validate")

    def test_authority_is_revoked_when_validation_fails(self) -> None:
        stage = self._stage()
        stage.sequence = 0

        with self.assertRaisesRegex(Exception, "sequence must be greater than zero"):
            with internal_stage_write(stage):
                stage.run_method("validate")

        self.assertFalse(is_internal_stage_write(stage))


if __name__ == "__main__":
    import unittest

    unittest.main()
