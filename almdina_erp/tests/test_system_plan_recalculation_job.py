from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.cutting.system_plan_recalculation_job import (
    COMPLETED,
    ENQUEUE,
    FAILED,
    IDLE,
    MARK_PENDING_RERUN,
    QUEUED,
    RUNNING,
    JobState,
    RecalculationFacts,
    decide_after_system_plan_recalculation_job,
    decide_enqueue_system_plan_recalculation,
    has_cuttable_pieces,
    job_presentation,
    system_draft_is_stale,
)


def _facts(**overrides: object) -> RecalculationFacts:
    values = {
        "has_recalculate_capability": True,
        "lifecycle_allows": True,
        "has_cuttable_pieces": True,
        "has_system_draft": True,
        "system_draft_is_stale": True,
    }
    values.update(overrides)
    return RecalculationFacts(**values)  # type: ignore[arg-type]


class TestSystemPlanRecalculationJob(unittest.TestCase):
    def test_has_cuttable_pieces_requires_positive_qty_and_size(self) -> None:
        self.assertFalse(has_cuttable_pieces([]))
        self.assertFalse(
            has_cuttable_pieces([{"qty": 1, "width_cm": 0, "length_cm": 200}])
        )
        self.assertFalse(
            has_cuttable_pieces([{"qty": 0, "width_cm": 80, "length_cm": 200}])
        )
        self.assertTrue(
            has_cuttable_pieces(
                [
                    {"qty": 0, "width_cm": 80, "length_cm": 200},
                    {"qty": 2, "width_cm": 40, "length_cm": 90},
                ]
            )
        )

    def test_system_draft_stale_when_missing_or_mismatched_fingerprint(self) -> None:
        self.assertFalse(
            system_draft_is_stale(
                has_system_draft=False,
                needs_recalculation=False,
                stored_fingerprint="",
                expected_fingerprint="abc",
            )
        )
        self.assertTrue(
            system_draft_is_stale(
                has_system_draft=True,
                needs_recalculation=True,
                stored_fingerprint="abc",
                expected_fingerprint="abc",
            )
        )
        self.assertFalse(
            system_draft_is_stale(
                has_system_draft=True,
                needs_recalculation=False,
                stored_fingerprint="abc",
                expected_fingerprint="abc",
            )
        )
        self.assertTrue(
            system_draft_is_stale(
                has_system_draft=True,
                needs_recalculation=False,
                stored_fingerprint="before",
                expected_fingerprint="after",
            )
        )

    def test_enqueue_skips_without_capability_lifecycle_or_pieces(self) -> None:
        self.assertEqual(
            decide_enqueue_system_plan_recalculation(
                _facts(has_recalculate_capability=False)
            ).reason,
            "no_capability",
        )
        self.assertEqual(
            decide_enqueue_system_plan_recalculation(
                _facts(lifecycle_allows=False)
            ).reason,
            "lifecycle_blocked",
        )
        self.assertEqual(
            decide_enqueue_system_plan_recalculation(
                _facts(has_cuttable_pieces=False)
            ).reason,
            "no_pieces",
        )
        self.assertEqual(
            decide_enqueue_system_plan_recalculation(
                _facts(system_draft_is_stale=False)
            ).reason,
            "fresh",
        )

    def test_missing_system_draft_enqueues_first_plan(self) -> None:
        decision = decide_enqueue_system_plan_recalculation(
            _facts(has_system_draft=False, system_draft_is_stale=False)
        )
        self.assertEqual(decision.action, ENQUEUE)
        self.assertEqual(decision.reason, "missing_system_draft")
        self.assertEqual(decision.next_generation, 1)

    def test_active_job_marks_pending_rerun_instead_of_queueing_another(self) -> None:
        current = JobState("DCO-1", QUEUED, generation=3)
        decision = decide_enqueue_system_plan_recalculation(_facts(), current)
        self.assertEqual(decision.action, MARK_PENDING_RERUN)
        self.assertEqual(decision.reason, "already_active")
        self.assertEqual(decision.next_generation, 3)

        running = JobState("DCO-1", RUNNING, generation=4)
        self.assertEqual(
            decide_enqueue_system_plan_recalculation(_facts(), running).action,
            MARK_PENDING_RERUN,
        )

    def test_completed_job_can_enqueue_a_new_generation(self) -> None:
        current = JobState("DCO-1", COMPLETED, generation=2)
        decision = decide_enqueue_system_plan_recalculation(_facts(), current)
        self.assertEqual(decision.action, ENQUEUE)
        self.assertEqual(decision.next_generation, 3)

    def test_after_job_requeues_only_when_pending_and_still_stale(self) -> None:
        self.assertEqual(
            decide_after_system_plan_recalculation_job(
                succeeded=True,
                pending_rerun=True,
                still_stale=True,
            ),
            ENQUEUE,
        )
        self.assertEqual(
            decide_after_system_plan_recalculation_job(
                succeeded=True,
                pending_rerun=True,
                still_stale=False,
            ),
            COMPLETED,
        )
        self.assertEqual(
            decide_after_system_plan_recalculation_job(
                succeeded=False,
                pending_rerun=False,
                still_stale=True,
            ),
            FAILED,
        )
        self.assertEqual(
            decide_after_system_plan_recalculation_job(
                succeeded=False,
                pending_rerun=True,
                still_stale=True,
            ),
            ENQUEUE,
        )

    def test_presentation_omits_error_except_on_failure(self) -> None:
        idle = job_presentation(None)
        self.assertEqual(idle["status"], IDLE)
        self.assertEqual(idle["error"], "")
        running = job_presentation(
            JobState("DCO-1", RUNNING, 1, error="secret-cost")
        )
        self.assertEqual(running["status"], RUNNING)
        self.assertEqual(running["error"], "")
        failed = job_presentation(JobState("DCO-1", FAILED, 1, error="boom"))
        self.assertEqual(failed["error"], "boom")
        for key in ("mdf_cost_usd", "total_cost_usd", "board_rate_usd"):
            self.assertNotIn(key, idle)
            self.assertNotIn(key, running)
            self.assertNotIn(key, failed)


if __name__ == "__main__":
    unittest.main()
