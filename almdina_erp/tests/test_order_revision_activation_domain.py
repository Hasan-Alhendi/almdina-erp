from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.domain.orders.revisions import (
    RevisionActivationNotAllowed,
    RevisionState,
    assert_revision_activation_allowed,
    assert_revision_dispatchable,
    initial_revision_state,
    is_current_revision,
    is_pending_activation,
)


class TestOrderRevisionActivationDomain(unittest.TestCase):
    def activation_case(self, **overrides):
        values = {
            "revision_of": "DCO-OLD",
            "revision_state": RevisionState.PENDING_ACTIVATION,
            "predecessor_status": "Approved",
            "predecessor_state": RevisionState.CURRENT,
            "predecessor_dispatched": False,
            "predecessor_has_open_stages": False,
            "predecessor_has_material_activity": False,
            "competing_current_revision": False,
        }
        values.update(overrides)
        return values

    def test_new_successors_wait_for_activation(self) -> None:
        self.assertEqual(initial_revision_state(None), RevisionState.CURRENT)
        self.assertEqual(
            initial_revision_state("DCO-OLD"),
            RevisionState.PENDING_ACTIVATION,
        )
        self.assertTrue(is_current_revision(None))
        self.assertTrue(is_pending_activation(RevisionState.PENDING_ACTIVATION))

    def test_safe_approved_predecessor_can_be_replaced(self) -> None:
        assert_revision_activation_allowed(**self.activation_case())

    def test_revision_activation_requires_pending_successor_and_current_predecessor(self) -> None:
        cases = (
            self.activation_case(revision_state=RevisionState.CURRENT),
            self.activation_case(predecessor_state=RevisionState.SUPERSEDED),
            self.activation_case(competing_current_revision=True),
        )
        for case in cases:
            with self.subTest(case=case):
                with self.assertRaises(RevisionActivationNotAllowed):
                    assert_revision_activation_allowed(**case)

    def test_predecessor_must_be_approved_but_not_in_physical_production(self) -> None:
        blocked = (
            self.activation_case(predecessor_status="At Drawing"),
            self.activation_case(predecessor_dispatched=True),
            self.activation_case(predecessor_has_open_stages=True),
            self.activation_case(predecessor_has_material_activity=True),
        )
        for case in blocked:
            with self.subTest(case=case):
                with self.assertRaises(RevisionActivationNotAllowed):
                    assert_revision_activation_allowed(**case)

    def test_only_current_revision_is_dispatchable(self) -> None:
        assert_revision_dispatchable(RevisionState.CURRENT)
        assert_revision_dispatchable(None)
        for state in (
            RevisionState.PENDING_ACTIVATION,
            RevisionState.SUPERSEDED,
        ):
            with self.subTest(state=state):
                with self.assertRaises(RevisionActivationNotAllowed):
                    assert_revision_dispatchable(state)


if __name__ == "__main__":
    unittest.main()
