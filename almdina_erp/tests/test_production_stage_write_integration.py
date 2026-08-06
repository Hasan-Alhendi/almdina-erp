from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.infrastructure.frappe.production_stage_write_guard import (
    authorize_internal_stage_write,
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

    def test_authorized_repository_context_can_validate_and_delete(self) -> None:
        stage = authorize_internal_stage_write(self._stage())

        stage.run_method("validate")
        stage.run_method("before_trash")


if __name__ == "__main__":
    import unittest

    unittest.main()
