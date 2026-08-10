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

    def test_no_active_stage_denies_mutation(self) -> None:
        allowed, code, reason = decide_stage_scoped_mutation(
            actor_roles=("عامل رسم",),
            operational_role="عامل رسم",
            has_current_stage=False,
        )
        self.assertFalse(allowed)
        self.assertEqual(code, "no_active_stage")
        self.assertIn("مرحلة", reason)

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
        self.assertIn("عامل رسم", reason)

        allowed, code, _reason = decide_stage_scoped_mutation(
            actor_roles=("عامل رسم", "عامل CNC"),
            operational_role="عامل رسم",
            has_current_stage=True,
        )
        self.assertTrue(allowed)
        self.assertEqual(code, "allowed")


if __name__ == "__main__":
    unittest.main()
