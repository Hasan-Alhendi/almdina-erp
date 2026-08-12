from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.domain.orders.stage_operational_access import (
    actor_holds_operational_role,
    decide_stage_scoped_mutation,
)


class TestStageOperationalAccessDomain(unittest.TestCase):
    def test_admin_bypasses_role_gate(self) -> None:
        self.assertTrue(
            actor_holds_operational_role((), "عامل رسم", is_admin=True)
        )
        allowed, code, _reason = decide_stage_scoped_mutation(
            actor_roles=(),
            operational_role=None,
            has_current_stage=False,
            is_admin=True,
        )
        self.assertTrue(allowed)
        self.assertEqual(code, "allowed")

    def test_pre_production_allows_capability_layer(self) -> None:
        allowed, code, reason = decide_stage_scoped_mutation(
            actor_roles=("عامل رسم",),
            operational_role=None,
            has_current_stage=False,
            has_production_path=False,
        )
        self.assertTrue(allowed)
        self.assertEqual(code, "pre_production")
        self.assertEqual(reason, "")

    def test_finished_route_without_stage_denies_mutation(self) -> None:
        allowed, code, reason = decide_stage_scoped_mutation(
            actor_roles=("عامل رسم",),
            operational_role="عامل رسم",
            has_current_stage=False,
            has_production_path=True,
        )
        self.assertFalse(allowed)
        self.assertEqual(code, "no_active_stage")
        self.assertIn("التسليم", reason)

    def test_missing_configured_role_denies_mutation(self) -> None:
        allowed, code, reason = decide_stage_scoped_mutation(
            actor_roles=("عامل رسم",),
            operational_role=None,
            has_current_stage=True,
        )
        self.assertFalse(allowed)
        self.assertEqual(code, "missing_stage_role")
        self.assertIn("دور تشغيلي", reason)

    def test_actor_must_hold_exact_operational_role(self) -> None:
        denied, code, reason = decide_stage_scoped_mutation(
            actor_roles=("عامل CNC",),
            operational_role="عامل رسم",
            has_current_stage=True,
        )
        self.assertFalse(denied)
        self.assertEqual(code, "missing_operational_role")
        self.assertIn("عرض", reason)
        self.assertNotIn("عامل رسم", reason)

        allowed, code, _reason = decide_stage_scoped_mutation(
            actor_roles=("عامل رسم", "عامل CNC"),
            operational_role="عامل رسم",
            has_current_stage=True,
        )
        self.assertTrue(allowed)
        self.assertEqual(code, "allowed")


if __name__ == "__main__":
    unittest.main()
