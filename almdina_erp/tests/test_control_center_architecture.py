from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"


class TestControlCenterArchitecture(unittest.TestCase):
    def test_active_control_center_services_have_no_role_gates(self) -> None:
        paths = [
            APP / "services" / "archive_service.py",
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

    def test_archive_page_has_no_fixed_roles_and_reports_are_absent(self) -> None:
        archive = APP / "page" / "factory_plan_archive" / "factory_plan_archive.json"
        self.assertEqual(json.loads(archive.read_text(encoding="utf-8"))["roles"], [])
        for report in (
            "factory_operations_summary",
            "production_stage_performance",
            "production_incidents_and_replacements",
        ):
            self.assertFalse((APP / "report" / report).exists(), report)

    def test_archive_uses_permission_aware_list_and_order_attachment(self) -> None:
        source = (APP / "services" / "archive_service.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("frappe.get_list", source)
        self.assertIn('"attached_to_doctype": "Door Cutting Order"', source)
        self.assertIn("ARCHIVE_APPROVED_PLAN", source)
        self.assertNotIn("frappe.get_all", source)

    def test_retired_approval_endpoints_are_thin_fail_closed_compatibility(self) -> None:
        queue = (APP / "services" / "approval_queue_service.py").read_text(
            encoding="utf-8"
        )
        review = (APP / "services" / "order_review_service.py").read_text(
            encoding="utf-8"
        )
        combined = f"{queue}\n{review}"
        self.assertEqual(queue.count("reject_retired_approval_workflow("), 4)
        self.assertEqual(review.count("reject_retired_approval_workflow("), 1)
        self.assertNotIn("frappe.db", combined)
        self.assertNotIn("frappe.get_list", combined)
        self.assertNotIn("frappe.get_doc", combined)
        self.assertNotIn("set_value", combined)

    def test_legacy_review_routes_and_document_scopes_are_registered(self) -> None:
        hooks = (ROOT / "hooks.py").read_text(encoding="utf-8")
        self.assertIn("order_review_service.reject_order", hooks)
        self.assertIn("order_lifecycle_permission_service.submit_order_for_review", hooks)
        self.assertNotIn("replacement_piece_query", hooks)
        self.assertNotIn("replacement_piece_has_permission", hooks)
        self.assertIn("door_cutting_order_has_permission", hooks)
        self.assertIn("cutting_plan_has_permission", hooks)
        self.assertIn("production_stage_has_permission", hooks)

    def test_direct_document_access_is_capability_and_assignment_scoped(self) -> None:
        source = (ROOT / "permissions.py").read_text(encoding="utf-8")
        self.assertIn("_scoped_read_decision", source)
        self.assertIn("required_capability", source)
        self.assertIn("_assigned_order_exists", source)
        self.assertIn('return "1=0"', source)
        self.assertNotIn("replacement_piece_has_permission", source)
        self.assertIn("door_cutting_order_has_permission", source)
        self.assertIn("production_stage_has_permission", source)
        self.assertIn("cutting_plan_has_permission", source)

    def test_order_cancel_does_not_depend_on_replacement_pieces(self) -> None:
        lifecycle = (APP / "services" / "order_lifecycle_service.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("cancel_replacement", lifecycle)
        self.assertNotIn("Replacement Piece", lifecycle)


if __name__ == "__main__":
    unittest.main()
