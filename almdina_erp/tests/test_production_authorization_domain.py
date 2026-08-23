from __future__ import annotations

import unittest
from pathlib import Path

from almdina_erp.almdina_erp.domain.orders.production_authorization import (
    PRODUCTION_ACTIONS,
    ProductionActionFacts,
    build_production_action_context,
    decide_production_action,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


POLICY_PATH = (
    Path(__file__).resolve().parents[1]
    / "almdina_erp"
    / "domain"
    / "orders"
    / "production_authorization.py"
)


class TestProductionAuthorizationDomain(unittest.TestCase):
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
            "drawing_dxf_status": "Approved by Drawing",
            "operational_role": "عامل CNC",
            "actor_roles": ("عامل CNC",),
        }
        values.update(overrides)
        return ProductionActionFacts(**values)

    def test_policy_has_no_framework_or_route_name_dependency(self) -> None:
        source = POLICY_PATH.read_text(encoding="utf-8")
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)
        self.assertNotIn("services", source)
        self.assertNotIn("infrastructure", source)
        self.assertNotIn('stage_type == "Drawing"', source)
        self.assertNotIn("dxf_not_approved", source)

    def test_every_action_fails_closed_without_its_capability(self) -> None:
        for action in PRODUCTION_ACTIONS:
            with self.subTest(action=action):
                decision = decide_production_action(
                    action,
                    capabilities=set(PRODUCTION_ACTIONS).difference({action}),
                    facts=self.facts(),
                )
                self.assertFalse(decision.allowed)
                self.assertEqual(decision.code, "missing_capability")
                self.assertTrue(decision.reason)

    def test_dispatch_requires_fresh_plan_and_undispatched_order(self) -> None:
        allowed = decide_production_action(
            Capability.DISPATCH_ORDER,
            capabilities={Capability.DISPATCH_ORDER},
            facts=self.facts(
                order_status="Approved",
                production_path=None,
                current_stage_name=None,
                stage_name=None,
                stage_type=None,
                stage_status=None,
                assigned_to=None,
            ),
        )
        self.assertTrue(allowed.allowed)

        missing_plan = decide_production_action(
            Capability.DISPATCH_ORDER,
            capabilities={Capability.DISPATCH_ORDER},
            facts=self.facts(
                order_status="Approved",
                production_path=None,
                current_stage_name=None,
                has_cutting_plan=False,
                stage_name=None,
                stage_type=None,
                stage_status=None,
                assigned_to=None,
            ),
        )
        self.assertEqual(missing_plan.code, "missing_cutting_plan")

        stale = decide_production_action(
            Capability.DISPATCH_ORDER,
            capabilities={Capability.DISPATCH_ORDER},
            facts=self.facts(
                order_status="Approved",
                production_path=None,
                current_stage_name=None,
                plan_needs_recalculation=True,
                stage_name=None,
                stage_type=None,
                stage_status=None,
                assigned_to=None,
            ),
        )
        self.assertEqual(stale.code, "stale_cutting_plan")

        already_dispatched = decide_production_action(
            Capability.DISPATCH_ORDER,
            capabilities={Capability.DISPATCH_ORDER},
            facts=self.facts(order_status="Approved"),
        )
        self.assertEqual(already_dispatched.code, "already_dispatched")

    def test_worker_actions_require_current_assigned_stage(self) -> None:
        not_assigned = decide_production_action(
            Capability.START_ASSIGNED_STAGE,
            capabilities={Capability.START_ASSIGNED_STAGE},
            facts=self.facts(assigned_to="another@example.com"),
        )
        self.assertEqual(not_assigned.code, "not_assigned")

        inactive = decide_production_action(
            Capability.START_ASSIGNED_STAGE,
            capabilities={Capability.START_ASSIGNED_STAGE},
            facts=self.facts(current_stage_name="PST-2"),
        )
        self.assertEqual(inactive.code, "inactive_stage")

        allowed = decide_production_action(
            Capability.START_ASSIGNED_STAGE,
            capabilities={Capability.START_ASSIGNED_STAGE},
            facts=self.facts(),
        )
        self.assertTrue(allowed.allowed)

        role_mismatch = decide_production_action(
            Capability.START_ASSIGNED_STAGE,
            capabilities={Capability.START_ASSIGNED_STAGE},
            facts=self.facts(actor_roles=("عامل رسم",)),
        )
        self.assertTrue(role_mismatch.allowed)
        self.assertEqual(role_mismatch.code, "allowed")

    def test_handoff_policy_is_independent_from_drawing_and_dxf_metadata(self) -> None:
        for dxf_status in (None, "Uploaded", "Approved by Drawing"):
            with self.subTest(dxf_status=dxf_status):
                decision = decide_production_action(
                    Capability.HANDOFF_ASSIGNED_STAGE,
                    capabilities={Capability.HANDOFF_ASSIGNED_STAGE},
                    facts=self.facts(
                        order_status="At Drawing",
                        stage_type="Drawing",
                        stage_status="In Progress",
                        drawing_dxf_status=dxf_status,
                        operational_role="عامل رسم",
                        actor_roles=("عامل رسم",),
                    ),
                )
                self.assertTrue(decision.allowed)

    def test_reassignment_is_independent_from_worker_assignment(self) -> None:
        allowed = decide_production_action(
            Capability.REASSIGN_WORKER,
            capabilities={Capability.REASSIGN_WORKER},
            facts=self.facts(assigned_to="another@example.com"),
        )
        self.assertTrue(allowed.allowed)

        closed = decide_production_action(
            Capability.REASSIGN_WORKER,
            capabilities={Capability.REASSIGN_WORKER},
            facts=self.facts(stage_status="Completed"),
        )
        self.assertEqual(closed.code, "closed_stage")

    def test_context_is_complete_arabic_and_json_safe(self) -> None:
        context = build_production_action_context(
            capabilities=PRODUCTION_ACTIONS,
            facts=self.facts(stage_status="In Progress"),
        )
        self.assertEqual(set(context), set(PRODUCTION_ACTIONS))
        for action, item in context.items():
            self.assertEqual(item["capability"], action)
            self.assertIsInstance(item["allowed"], bool)
            self.assertIsInstance(item["code"], str)
            self.assertIsInstance(item["reason"], str)

        denied = decide_production_action(
            Capability.START_ASSIGNED_STAGE,
            capabilities={Capability.START_ASSIGNED_STAGE},
            facts=self.facts(assigned_to="other@example.com"),
        )
        self.assertIn("مستخدم آخر", denied.reason)

        role_mismatch = decide_production_action(
            Capability.START_ASSIGNED_STAGE,
            capabilities={Capability.START_ASSIGNED_STAGE},
            facts=self.facts(actor_roles=("عامل رسم",)),
        )
        self.assertTrue(role_mismatch.allowed)
        self.assertEqual(role_mismatch.code, "allowed")


if __name__ == "__main__":
    unittest.main()
