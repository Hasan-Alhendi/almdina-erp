from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.shop_floor import commands
from almdina_erp.almdina_erp.domain.orders.lifecycle import (
    can_transition_stage,
    transition_stage,
)
from almdina_erp.almdina_erp.domain.orders.production_authorization import (
    ProductionActionFacts,
    build_production_action_context,
    decide_production_action,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.tests.test_shop_floor_command_application import (
    FakeShopFloorCommandRepository,
)


class TestDirectHandoffWithoutStart(unittest.TestCase):
    @staticmethod
    def facts(**overrides) -> ProductionActionFacts:
        values = {
            "order_status": "At CNC",
            "production_path": "Drawing",
            "current_stage_name": "PST-1",
            "has_cutting_plan": True,
            "plan_needs_recalculation": False,
            "stage_name": "PST-1",
            "stage_type": "CNC",
            "stage_status": "Pending",
            "assigned_to": "worker@example.com",
            "actor": "worker@example.com",
        }
        values.update(overrides)
        return ProductionActionFacts(**values)

    @staticmethod
    def repository_for_stage(
        *,
        stage_type: str,
        stage_status: str = "Pending",
        has_approved_plan: bool = True,
    ) -> FakeShopFloorCommandRepository:
        repository = FakeShopFloorCommandRepository()
        repository.capabilities = {Capability.HANDOFF_ASSIGNED_STAGE}
        repository.orders["DCO-1"] = commands.OrderState(
            name="DCO-1",
            status=f"At {stage_type}",
            production_path="Drawing",
            current_stage="PST-1",
            has_cutting_plan=True,
            plan_needs_recalculation=False,
            has_approved_plan=has_approved_plan,
        )
        sequence = {"Drawing": 10, "CNC": 20, "Sanding": 30}[stage_type]
        repository.stages["PST-1"] = commands.StageState(
            name="PST-1",
            order_name="DCO-1",
            stage_type=stage_type,
            status=stage_status,
            assigned_to=repository.actor,
            sequence=sequence,
        )
        return repository

    def test_lifecycle_has_explicit_pending_direct_handoff_transition(self) -> None:
        self.assertTrue(can_transition_stage("Pending", "direct_handoff"))
        self.assertEqual(
            transition_stage("Pending", "direct_handoff"),
            "Completed",
        )

        for status in ("In Progress", "Paused", "Completed", "Cancelled"):
            with self.subTest(status=status):
                self.assertFalse(can_transition_stage(status, "direct_handoff"))
                with self.assertRaises(ValueError):
                    transition_stage(status, "direct_handoff")

    def test_normal_finish_still_rejects_pending(self) -> None:
        self.assertFalse(can_transition_stage("Pending", "finish"))
        with self.assertRaises(ValueError):
            transition_stage("Pending", "finish")

    def test_pending_permission_matrix_keeps_start_and_handoff_independent(self) -> None:
        cases = (
            (frozenset(), False, False, None),
            (frozenset({Capability.START_ASSIGNED_STAGE}), True, False, None),
            (frozenset({Capability.HANDOFF_ASSIGNED_STAGE}), False, True, "direct_handoff"),
            (
                frozenset(
                    {
                        Capability.START_ASSIGNED_STAGE,
                        Capability.HANDOFF_ASSIGNED_STAGE,
                    }
                ),
                True,
                False,
                None,
            ),
        )

        for capabilities, can_start, can_handoff, handoff_event in cases:
            with self.subTest(capabilities=capabilities):
                start = decide_production_action(
                    Capability.START_ASSIGNED_STAGE,
                    capabilities=capabilities,
                    facts=self.facts(),
                )
                handoff = decide_production_action(
                    Capability.HANDOFF_ASSIGNED_STAGE,
                    capabilities=capabilities,
                    facts=self.facts(),
                )
                self.assertEqual(start.allowed, can_start)
                self.assertEqual(handoff.allowed, can_handoff)
                self.assertEqual(handoff.transition_event, handoff_event)

        both = {
            Capability.START_ASSIGNED_STAGE,
            Capability.HANDOFF_ASSIGNED_STAGE,
        }
        handoff = decide_production_action(
            Capability.HANDOFF_ASSIGNED_STAGE,
            capabilities=both,
            facts=self.facts(),
        )
        self.assertEqual(handoff.code, "stage_not_handoff_ready")

    def test_in_progress_handoff_uses_normal_finish_transition(self) -> None:
        both = {
            Capability.START_ASSIGNED_STAGE,
            Capability.HANDOFF_ASSIGNED_STAGE,
        }
        start = decide_production_action(
            Capability.START_ASSIGNED_STAGE,
            capabilities=both,
            facts=self.facts(stage_status="In Progress"),
        )
        handoff = decide_production_action(
            Capability.HANDOFF_ASSIGNED_STAGE,
            capabilities=both,
            facts=self.facts(stage_status="In Progress"),
        )

        self.assertFalse(start.allowed)
        self.assertEqual(start.code, "stage_not_startable")
        self.assertTrue(handoff.allowed)
        self.assertEqual(handoff.transition_event, "finish")

        handoff_only = decide_production_action(
            Capability.HANDOFF_ASSIGNED_STAGE,
            capabilities={Capability.HANDOFF_ASSIGNED_STAGE},
            facts=self.facts(stage_status="In Progress"),
        )
        self.assertTrue(handoff_only.allowed)
        self.assertEqual(handoff_only.transition_event, "finish")

    def test_direct_handoff_still_requires_current_assigned_stage(self) -> None:
        not_assigned = decide_production_action(
            Capability.HANDOFF_ASSIGNED_STAGE,
            capabilities={Capability.HANDOFF_ASSIGNED_STAGE},
            facts=self.facts(assigned_to="another@example.com"),
        )
        self.assertFalse(not_assigned.allowed)
        self.assertEqual(not_assigned.code, "not_assigned")

        inactive = decide_production_action(
            Capability.HANDOFF_ASSIGNED_STAGE,
            capabilities={Capability.HANDOFF_ASSIGNED_STAGE},
            facts=self.facts(current_stage_name="PST-2"),
        )
        self.assertFalse(inactive.allowed)
        self.assertEqual(inactive.code, "inactive_stage")

    def test_backend_action_context_matches_pending_ui_matrix(self) -> None:
        handoff_only = build_production_action_context(
            capabilities={Capability.HANDOFF_ASSIGNED_STAGE},
            facts=self.facts(),
        )
        self.assertFalse(handoff_only[Capability.START_ASSIGNED_STAGE]["allowed"])
        self.assertTrue(handoff_only[Capability.HANDOFF_ASSIGNED_STAGE]["allowed"])

        both = build_production_action_context(
            capabilities={
                Capability.START_ASSIGNED_STAGE,
                Capability.HANDOFF_ASSIGNED_STAGE,
            },
            facts=self.facts(),
        )
        self.assertTrue(both[Capability.START_ASSIGNED_STAGE]["allowed"])
        self.assertFalse(both[Capability.HANDOFF_ASSIGNED_STAGE]["allowed"])

    def test_command_direct_handoff_completes_pending_without_fake_start(self) -> None:
        repository = self.repository_for_stage(stage_type="CNC")

        result = commands.handoff_to_next(
            repository,
            "PST-1",
            "sanding@example.com",
        )

        self.assertEqual(repository.stages["PST-1"].status, "Completed")
        self.assertEqual(result["next_stage_type"], "Sanding")
        self.assertFalse(any(call[0] == "start_stage" for call in repository.calls))
        self.assertIn(
            ("complete_stage", "PST-1", repository.actor, "Completed", 7),
            repository.calls,
        )
        self.assertIn(
            ("assert_worker_for_role", "sanding@example.com", "عامل تقشيط"),
            repository.calls,
        )

    def test_command_direct_handoff_from_final_stage_marks_ready_for_delivery(self) -> None:
        repository = self.repository_for_stage(stage_type="Sanding")

        result = commands.handoff_to_next(repository, "PST-1")

        self.assertTrue(result["ready_for_delivery"])
        self.assertEqual(repository.stages["PST-1"].status, "Completed")
        self.assertEqual(repository.orders["DCO-1"].status, "Ready for Delivery")
        self.assertFalse(any(call[0] == "start_stage" for call in repository.calls))
        self.assertIn(("track_order_ready_for_delivery", "DCO-1"), repository.calls)

    def test_planning_gate_still_blocks_direct_handoff_until_plan_is_approved(self) -> None:
        repository = self.repository_for_stage(
            stage_type="Drawing",
            has_approved_plan=False,
        )

        with self.assertRaisesRegex(commands.ShopFloorCommandError, "اعتمد خطة القص"):
            commands.handoff_to_next(repository, "PST-1", "cnc@example.com")

        self.assertEqual(repository.stages["PST-1"].status, "Pending")
        self.assertFalse(any(call[0] == "start_stage" for call in repository.calls))
        self.assertFalse(any(call[0] == "complete_stage" for call in repository.calls))


if __name__ == "__main__":
    unittest.main()
