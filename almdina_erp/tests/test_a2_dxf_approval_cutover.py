from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import SYSTEM, UPLOADED_DXF
from almdina_erp.almdina_erp.services import cutting_plan_command_service as commands
from almdina_erp.almdina_erp.services import shop_floor_dxf_service as dxf_service


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"
DXF_SERVICE = APP / "services" / "shop_floor_dxf_service.py"
APPROVAL_SERVICE = APP / "services" / "drawing_approval_service.py"
COMMAND_SERVICE = APP / "services" / "cutting_plan_command_service.py"
COMMAND_REPOSITORY = (
    APP / "infrastructure" / "frappe" / "cutting_plan_command_repository.py"
)
WORKSPACE = APP / "infrastructure" / "frappe" / "cutting_plan_workspace.py"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def valid_plan(*, source_type: str = SYSTEM) -> SimpleNamespace:
    return SimpleNamespace(
        status="Draft",
        validation_status="Valid",
        snapshot_json='{"validation":{"is_valid":true},"sheets":[{"sheet_no":1}]}',
        plan_needs_recalculation=0,
        input_fingerprint="fresh-fingerprint",
        source_type=source_type,
        dxf_file="/private/files/plan.dxf" if source_type == UPLOADED_DXF else "",
        dxf_status="Validated" if source_type == UPLOADED_DXF else "Draft",
    )


class TestA2DxfApprovalArchitecture(unittest.TestCase):
    def test_dxf_file_is_attached_to_cutting_plan_after_validation_and_plan_save(self) -> None:
        service = source(DXF_SERVICE)
        upload = service.split("def upload_production_dxf", 1)[1].split(
            "\n\n@frappe.whitelist()\ndef recalculate_drawing_plan", 1
        )[0]

        self.assertIn('"attached_to_doctype": "Cutting Plan"', service)
        self.assertIn('"attached_to_name": plan.name', service)
        self.assertIn('"attached_to_field": "dxf_file"', service)
        self.assertNotIn('"attached_to_doctype": order.doctype', service)

        staged = upload.index("_validate_dxf_file_metadata(file_url)")
        authorized = upload.index("_authorize_order(")
        validated = upload.index("parse_production_dxf(")
        persisted = upload.index("save_uploaded_dxf_plan(")
        attached = upload.index("_attach_validated_dxf_file(")
        projected = upload.index("mirror_uploaded_dxf_projection(")
        self.assertLess(staged, authorized)
        self.assertLess(authorized, validated)
        self.assertLess(validated, persisted)
        self.assertLess(persisted, attached)
        self.assertLess(attached, projected)

    def test_approval_boundary_delegates_to_plan_command_without_snapshot_service(self) -> None:
        approval = source(APPROVAL_SERVICE)
        self.assertIn("Capability.APPROVE_DXF", approval)
        self.assertIn("for update", approval)
        self.assertIn("approve_order_plan", approval)
        self.assertNotIn("cutting_plan_snapshot_service", approval)
        self.assertNotIn("lock_order_for_production", approval)
        self.assertNotIn("order.save(", approval)
        self.assertNotIn("ignore_permissions", approval)

    def test_plan_command_approves_existing_draft_and_never_recalculates(self) -> None:
        command = source(COMMAND_SERVICE)
        approval = command.split("def approve_order_plan", 1)[1].split(
            "\n\ndef save_system_plan_settings", 1
        )[0]
        self.assertIn("latest_document(", approval)
        self.assertIn("status=DRAFT", approval)
        self.assertIn("_assert_plan_ready_for_approval(order, plan)", approval)
        self.assertIn("plan.status = APPROVED", approval)
        self.assertIn("repository.save_document(plan, allow_status_transition=True)", approval)
        self.assertNotIn("recalculate_system_plan", approval)
        self.assertNotIn("calculate_system_plan", approval)
        self.assertNotIn("create_plan_from_order", approval)
        self.assertNotIn("order.save(", command)
        self.assertNotIn("ignore_permissions", command)

    def test_repository_status_transitions_stay_inside_scoped_command_persistence(self) -> None:
        repository = source(COMMAND_REPOSITORY)
        self.assertIn("PLAN_COMMAND_FLAG", repository)
        self.assertIn("allow_status_transition", repository)
        self.assertIn("ensure_uploaded_dxf_draft", repository)
        self.assertNotIn("ignore_permissions", repository)

    def test_system_and_dxf_snapshots_share_one_fingerprint_and_mapping_owner(self) -> None:
        workspace = source(WORKSPACE)
        self.assertIn("def plan_input_fingerprint", workspace)
        self.assertIn("def _apply_snapshot", workspace)
        self.assertIn("def apply_calculation_outcome", workspace)
        self.assertIn("def apply_validated_dxf_snapshot", workspace)
        self.assertIn("_apply_snapshot(", workspace)


class TestA2DxfStagingSecurity(unittest.TestCase):
    def test_public_file_is_rejected_before_any_order_authorization(self) -> None:
        public_file = SimpleNamespace(
            name="FILE-PUBLIC",
            file_size=100,
            is_private=0,
            attached_to_doctype=None,
            attached_to_name=None,
            attached_to_field=None,
        )
        with patch.object(dxf_service.frappe.db, "get_value", return_value=public_file):
            with self.assertRaises(frappe.ValidationError):
                dxf_service._validate_dxf_file_metadata("/files/public.dxf")

    def test_preattached_private_file_is_rejected(self) -> None:
        attached_file = SimpleNamespace(
            name="FILE-ATTACHED",
            file_size=100,
            is_private=1,
            attached_to_doctype="Door Cutting Order",
            attached_to_name="DCO-OTHER",
            attached_to_field="production_dxf",
        )
        with patch.object(dxf_service.frappe.db, "get_value", return_value=attached_file):
            with self.assertRaises(frappe.ValidationError):
                dxf_service._validate_dxf_file_metadata("/private/files/attached.dxf")


class TestA2ApprovalFreshness(unittest.TestCase):
    def test_fresh_valid_system_plan_is_approvable_without_recalculation(self) -> None:
        plan = valid_plan(source_type=SYSTEM)
        order = SimpleNamespace(name="DCO-A2-001")
        with patch.object(commands, "plan_input_fingerprint", return_value="fresh-fingerprint"):
            commands._assert_plan_ready_for_approval(order, plan)

    def test_stale_system_plan_is_rejected_instead_of_auto_recalculation(self) -> None:
        plan = valid_plan(source_type=SYSTEM)
        order = SimpleNamespace(name="DCO-A2-002")
        with patch.object(commands, "plan_input_fingerprint", return_value="changed-input"):
            with self.assertRaises(frappe.ValidationError):
                commands._assert_plan_ready_for_approval(order, plan)

    def test_missing_system_snapshot_is_rejected(self) -> None:
        plan = valid_plan(source_type=SYSTEM)
        plan.snapshot_json = ""
        order = SimpleNamespace(name="DCO-A2-003")
        with patch.object(commands, "plan_input_fingerprint", return_value="fresh-fingerprint"):
            with self.assertRaises(frappe.ValidationError):
                commands._assert_plan_ready_for_approval(order, plan)

    def test_uploaded_dxf_plan_requires_validated_file(self) -> None:
        plan = valid_plan(source_type=UPLOADED_DXF)
        plan.dxf_status = "Draft"
        order = SimpleNamespace(name="DCO-A2-004")
        with patch.object(commands, "plan_input_fingerprint", return_value="fresh-fingerprint"):
            with self.assertRaises(frappe.ValidationError):
                commands._assert_plan_ready_for_approval(order, plan)


if __name__ == "__main__":
    unittest.main()
