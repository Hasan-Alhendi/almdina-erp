from __future__ import annotations

import json
import unittest
from pathlib import Path

from almdina_erp.almdina_erp.domain.orders.cancellation_resume import (
    CancelledStageSnapshot,
    StageResumeFact,
    build_cancellation_snapshot,
    can_resume_cancelled_order,
    restore_cancelled_stage,
    resume_from_snapshot,
    resume_without_snapshot,
    select_resume_plan,
    snapshot_from_mapping,
    snapshot_to_mapping,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    PRODUCTION_SUPERVISOR_CAPABILITIES,
    Capability,
)


DOMAIN_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "almdina_erp"
    / "domain"
    / "orders"
    / "cancellation_resume.py"
)


class TestCancellationResumeDomain(unittest.TestCase):
    def test_domain_has_no_framework_dependency(self) -> None:
        source = DOMAIN_SOURCE.read_text(encoding="utf-8")
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)
        self.assertNotIn("frappe.", source)

    def test_resume_is_allowed_only_for_current_cancelled_orders(self) -> None:
        self.assertTrue(can_resume_cancelled_order("Cancelled"))
        self.assertFalse(can_resume_cancelled_order("Cancelled", "Superseded"))
        for status in ("Draft", "At CNC", "Ready for Delivery", "Delivered"):
            with self.subTest(status=status):
                self.assertFalse(can_resume_cancelled_order(status))

    def test_restore_preserves_active_stage_status_only(self) -> None:
        self.assertEqual(restore_cancelled_stage("Cancelled", "Pending"), "Pending")
        self.assertEqual(restore_cancelled_stage("Cancelled", "In Progress"), "In Progress")
        self.assertEqual(restore_cancelled_stage("Cancelled", "Paused"), "Paused")
        with self.assertRaises(ValueError):
            restore_cancelled_stage("Pending", "In Progress")
        with self.assertRaises(ValueError):
            restore_cancelled_stage("Cancelled", "Completed")

    def test_snapshot_roundtrip_excludes_financial_fields(self) -> None:
        snapshot = build_cancellation_snapshot(
            order_status="CNC",
            department_status="قيد العمل",
            current_production_stage="PST-CNC",
            current_assignee="worker@example.com",
            current_department="CNC",
            production_path="ROUTE-DRAWING",
            approved_plan="CP-1",
            approved_plan_status="Approved",
            cancellable_stages=[
                CancelledStageSnapshot(
                    name="PST-CNC",
                    previous_status="In Progress",
                    stage_type="CNC",
                    department_label="CNC",
                ),
                CancelledStageSnapshot(
                    name="PST-SAND",
                    previous_status="Pending",
                    stage_type="Sanding",
                    department_label="تقشيط",
                ),
            ],
        )
        payload = snapshot_to_mapping(snapshot)
        encoded = json.dumps(payload)
        self.assertNotIn("cost", encoded.lower())
        self.assertNotIn("usd", encoded.lower())
        self.assertTrue(payload["restore_plan"])
        restored = snapshot_from_mapping(json.loads(encoded))
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored.order_status, "CNC")
        self.assertEqual(restored.current_assignee, "worker@example.com")
        self.assertEqual(restored.stages[0].previous_status, "In Progress")

        plan = resume_from_snapshot(restored)
        self.assertEqual(plan.order_status, "CNC")
        self.assertEqual(plan.department_status, "قيد العمل")
        self.assertTrue(plan.restore_plan)
        self.assertEqual(plan.approved_plan, "CP-1")
        self.assertEqual(
            [(stage.name, stage.target_status) for stage in plan.stages],
            [("PST-CNC", "In Progress"), ("PST-SAND", "Pending")],
        )

    def test_fallback_reopens_current_and_later_cancelled_stages_only(self) -> None:
        stages = (
            StageResumeFact("PST-DRAW", "Completed", 10, "Drawing", "رسم"),
            StageResumeFact("PST-CNC", "Cancelled", 20, "CNC", "CNC"),
            StageResumeFact("PST-SAND", "Cancelled", 30, "Sanding", "تقشيط"),
            StageResumeFact("PST-OLD", "Cancelled", 5, "Legacy", "قديم"),
        )
        plan = resume_without_snapshot(
            current_production_stage="PST-CNC",
            stages=stages,
            approved_plan="CP-1",
            approved_plan_status="Cancelled",
        )
        self.assertEqual(plan.order_status, "CNC")
        self.assertEqual(
            [(stage.name, stage.target_status) for stage in plan.stages],
            [("PST-CNC", "Pending"), ("PST-SAND", "Pending")],
        )
        self.assertTrue(plan.restore_plan)

    def test_fallback_ready_for_delivery_when_no_cancelled_current_work(self) -> None:
        plan = resume_without_snapshot(
            current_production_stage="PST-SAND",
            stages=(
                StageResumeFact("PST-CNC", "Completed", 20, "CNC", "CNC"),
                StageResumeFact("PST-SAND", "Completed", 30, "Sanding", "تقشيط"),
            ),
            approved_plan="CP-1",
            approved_plan_status="Cancelled",
        )
        self.assertEqual(plan.order_status, "Ready for Delivery")
        self.assertEqual(plan.stages, ())
        self.assertTrue(plan.restore_plan)

    def test_fallback_without_current_stage_returns_to_draft(self) -> None:
        plan = resume_without_snapshot(
            current_production_stage=None,
            stages=(),
            approved_plan=None,
            approved_plan_status=None,
        )
        self.assertEqual(plan.order_status, "Draft")
        self.assertEqual(plan.stages, ())
        self.assertFalse(plan.restore_plan)

    def test_select_resume_plan_prefers_snapshot(self) -> None:
        snapshot = build_cancellation_snapshot(
            order_status="Ready for Delivery",
            department_status="مكتمل",
            current_production_stage="PST-SAND",
            current_assignee=None,
            current_department="تقشيط",
            production_path="ROUTE-DRAWING",
            approved_plan="CP-1",
            approved_plan_status="Approved",
            cancellable_stages=(),
        )
        plan = select_resume_plan(
            snapshot,
            current_production_stage="PST-SAND",
            stages=(StageResumeFact("PST-SAND", "Completed", 30, "Sanding", "تقشيط"),),
            approved_plan="CP-1",
            approved_plan_status="Cancelled",
        )
        self.assertEqual(plan.order_status, "Ready for Delivery")
        self.assertEqual(plan.stages, ())

    def test_resume_capability_does_not_open_shop_floor_by_itself(self) -> None:
        self.assertNotIn(
            Capability.RESUME_CANCELLED_ORDER,
            PRODUCTION_SUPERVISOR_CAPABILITIES,
        )
        self.assertNotIn(Capability.CANCEL_ORDER, PRODUCTION_SUPERVISOR_CAPABILITIES)


if __name__ == "__main__":
    unittest.main()
