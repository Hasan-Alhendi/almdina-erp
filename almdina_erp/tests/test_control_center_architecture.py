from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"


class TestControlCenterArchitecture(unittest.TestCase):
    def test_active_control_center_services_have_no_role_gates(self) -> None:
        paths = [
            APP / "services" / "approval_queue_service.py",
            APP / "services" / "archive_service.py",
            APP / "services" / "order_review_service.py",
            APP / "services" / "replacement_creation_service.py",
            APP / "services" / "replacement_approval.py",
            APP / "services" / "replacement_execution.py",
            APP / "services" / "replacement_completion.py",
            APP / "services" / "replacement_permission_service.py",
            APP / "services" / "report_permission_service.py",
        ]
        source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        self.assertNotIn("require_any_role", source)
        self.assertNotIn("frappe.get_roles", source)
        for role in (
            "Production Manager",
            "Accounts Management",
            "Cutting Operator",
            "Edge Operator",
            "System Manager",
        ):
            self.assertNotIn(role, source)

    def test_replacement_ui_uses_server_context_not_roles(self) -> None:
        source = (ROOT / "public" / "js" / "replacement_piece.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("get_replacement_context", source)
        self.assertIn("actionAllowed", source)
        self.assertIn("__almdinaReplacementRequest", source)
        self.assertNotIn("frappe.user_roles", source)
        self.assertNotIn("has_role", source)

    def test_pages_reports_and_replacement_doctype_have_no_fixed_roles(self) -> None:
        paths = [
            APP / "page" / "factory_approval_queue" / "factory_approval_queue.json",
            APP / "page" / "factory_plan_archive" / "factory_plan_archive.json",
            APP / "report" / "factory_operations_summary" / "factory_operations_summary.json",
            APP / "report" / "production_incidents_and_replacements" / "production_incidents_and_replacements.json",
            APP / "report" / "production_stage_performance" / "production_stage_performance.json",
        ]
        for path in paths:
            with self.subTest(path=path.name):
                self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["roles"], [])

        replacement = json.loads(
            (APP / "doctype" / "replacement_piece" / "replacement_piece.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(replacement["permissions"], [])

    def test_reports_enforce_access_before_querying_and_redact_financial_data(self) -> None:
        summary = (
            APP
            / "report"
            / "factory_operations_summary"
            / "factory_operations_summary.py"
        ).read_text(encoding="utf-8")
        incidents = (
            APP
            / "report"
            / "production_incidents_and_replacements"
            / "production_incidents_and_replacements.py"
        ).read_text(encoding="utf-8")
        performance = (
            APP
            / "report"
            / "production_stage_performance"
            / "production_stage_performance.py"
        ).read_text(encoding="utf-8")
        self.assertIn("require_operational_report_access()", summary)
        self.assertIn("if access.financial", summary)
        self.assertIn("financial_select", incidents)
        self.assertIn("get_columns(include_financial=access.financial)", incidents)
        self.assertIn("require_operational_report_access()", performance)

    def test_archive_uses_permission_aware_list_and_order_attachment(self) -> None:
        source = (APP / "services" / "archive_service.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("frappe.get_list", source)
        self.assertIn('"attached_to_doctype": "Door Cutting Order"', source)
        self.assertIn("ARCHIVE_APPROVED_PLAN", source)
        self.assertNotIn("frappe.get_all", source)

    def test_approval_queue_separates_approve_and_reject(self) -> None:
        service = (APP / "services" / "approval_queue_service.py").read_text(
            encoding="utf-8"
        )
        page = (
            APP / "page" / "factory_approval_queue" / "factory_approval_queue.js"
        ).read_text(encoding="utf-8")
        self.assertIn("APPROVE_ORDER", service)
        self.assertIn("REJECT_ORDER", service)
        self.assertIn("can_approve", page)
        self.assertIn("can_reject", page)
        self.assertNotIn("frappe.user_roles", page)

    def test_legacy_review_routes_and_document_scopes_are_registered(self) -> None:
        hooks = (ROOT / "hooks.py").read_text(encoding="utf-8")
        self.assertIn("order_review_service.reject_order", hooks)
        self.assertIn("order_lifecycle_permission_service.submit_order_for_review", hooks)
        self.assertIn('"Replacement Piece": "almdina_erp.permissions.replacement_piece_query"', hooks)
        self.assertIn("replacement_piece_has_permission", hooks)
        self.assertIn("door_cutting_order_has_permission", hooks)
        self.assertIn("cutting_plan_has_permission", hooks)
        self.assertIn("production_stage_has_permission", hooks)

    def test_direct_document_access_is_capability_and_assignment_scoped(self) -> None:
        source = (ROOT / "permissions.py").read_text(encoding="utf-8")
        self.assertIn("_scoped_read_decision", source)
        self.assertIn("required_capability", source)
        self.assertIn("_assigned_order_exists", source)
        self.assertIn('return "1=0"', source)
        self.assertIn("replacement_piece_has_permission", source)
        self.assertIn("door_cutting_order_has_permission", source)
        self.assertIn("production_stage_has_permission", source)
        self.assertIn("cutting_plan_has_permission", source)

    def test_replacement_context_minimizes_plan_identity(self) -> None:
        source = (
            APP / "services" / "replacement_permission_service.py"
        ).read_text(encoding="utf-8")
        self.assertIn("doctype_has_capability(Capability.VIEW_CUTTING_PLAN)", source)
        self.assertIn("else None", source)

    def test_internal_order_cancel_does_not_require_second_business_grant(self) -> None:
        lifecycle = (APP / "services" / "order_lifecycle_service.py").read_text(
            encoding="utf-8"
        )
        execution = (APP / "services" / "replacement_execution.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("cancel_replacement_for_order_cancellation", lifecycle)
        self.assertIn("def cancel_replacement_for_order_cancellation", execution)
        self.assertNotIn("cancel_replacement(\n                row.name", lifecycle)


if __name__ == "__main__":
    unittest.main()
