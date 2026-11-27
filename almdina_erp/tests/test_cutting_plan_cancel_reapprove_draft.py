"""Regression: cancel approval must spawn a geometry-preserving Draft for re-approval."""

from __future__ import annotations

import unittest
from pathlib import Path

from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import (
    APPROVED,
    BOARD_EDITOR,
    CANCELLED,
    DRAFT,
    SYSTEM,
    UPLOADED_DXF,
    CuttingPlanLifecycleError,
    next_revision,
    prefer_plan_tab_for_source,
    revision_from_lineage_source,
    select_newer_draft_of_source,
)


ROOT = Path(__file__).resolve().parents[1]
CANCEL_SERVICE = (
    ROOT
    / "almdina_erp"
    / "services"
    / "cutting_plan_approval_cancellation_service.py"
)
COMMAND_SERVICE = ROOT / "almdina_erp" / "services" / "cutting_plan_command_service.py"
REPOSITORY = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "cutting_plan_command_repository.py"
)
CONTEXT_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "cutting_plan"
    / "door_cutting_order_plan_context_actions_ux.js"
)
TRANSLATIONS = ROOT / "translations" / "ar.csv"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestCuttingPlanCancelReapproveDraft(unittest.TestCase):
    def test_domain_lineage_accepts_approved_and_cancelled_sources(self) -> None:
        approved = revision_from_lineage_source(
            current_name="CP-A",
            current_revision=3,
            current_status=APPROVED,
            source_type=SYSTEM,
            next_revision_number=7,
        )
        self.assertEqual(approved.status, DRAFT)
        self.assertEqual(approved.revision, 7)
        self.assertEqual(approved.based_on_plan, "CP-A")

        cancelled = revision_from_lineage_source(
            current_name="CP-C",
            current_revision=2,
            current_status=CANCELLED,
            source_type=UPLOADED_DXF,
            next_revision_number=4,
        )
        self.assertEqual(cancelled.status, DRAFT)
        self.assertEqual(cancelled.revision, 4)
        self.assertEqual(cancelled.source_type, UPLOADED_DXF)

        with self.assertRaises(CuttingPlanLifecycleError):
            revision_from_lineage_source(
                current_name="CP-D",
                current_revision=1,
                current_status=DRAFT,
                source_type=SYSTEM,
            )

    def test_newer_draft_selection_ignores_older_and_other_sources(self) -> None:
        rows = [
            {"name": "BE-3", "source_type": BOARD_EDITOR, "status": DRAFT, "revision": 9},
            {"name": "SYS-OLD", "source_type": SYSTEM, "status": DRAFT, "revision": 2},
            {
                "name": "SYS-TIP",
                "source_type": SYSTEM,
                "status": DRAFT,
                "revision": 5,
                "modified": "2026-01-02",
            },
            {
                "name": "SYS-TIP-2",
                "source_type": SYSTEM,
                "status": DRAFT,
                "revision": 5,
                "modified": "2026-01-03",
            },
            {"name": "SYS-A", "source_type": SYSTEM, "status": APPROVED, "revision": 4},
        ]
        selected = select_newer_draft_of_source(
            rows,
            source_type=SYSTEM,
            min_revision=4,
        )
        self.assertIsNotNone(selected)
        self.assertEqual(selected["name"], "SYS-TIP-2")
        self.assertIsNone(
            select_newer_draft_of_source(rows, source_type=SYSTEM, min_revision=5)
        )
        self.assertEqual(next_revision([2, 9, 5, 4]), 10)

    def test_prefer_plan_tab_maps_source_types(self) -> None:
        self.assertEqual(prefer_plan_tab_for_source(SYSTEM), "System")
        self.assertEqual(prefer_plan_tab_for_source(UPLOADED_DXF), "Custom")
        self.assertEqual(prefer_plan_tab_for_source(BOARD_EDITOR), "BoardEditor")

    def test_cancellation_service_creates_geometry_preserving_draft_before_cancel(self) -> None:
        service = _source(CANCEL_SERVICE)
        body = service.split("def cancel_approved_order_plan", 1)[1]
        self.assertIn("create_geometry_preserving_draft", body)
        self.assertIn("find_newer_draft", body)
        self.assertIn('"draft_plan"', body)
        self.assertIn("prefer_plan_tab_for_source", body)
        # Draft must be prepared while the tip is still Approved.
        create_at = body.index("create_geometry_preserving_draft")
        cancel_at = body.index("cancel_approval_transition")
        self.assertLess(create_at, cancel_at)
        self.assertNotIn("calculate_system_plan", body)
        self.assertNotIn("optimize_order_plan", body)

    def test_repository_owns_geometry_copy_without_engine(self) -> None:
        repository = _source(REPOSITORY)
        self.assertIn("def create_geometry_preserving_draft", repository)
        self.assertIn("frappe.copy_doc(source_plan)", repository)
        self.assertIn("ensure_geometry_draft_from_cancelled", repository)
        self.assertIn("_copy_board_editor_drawings", repository)
        self.assertIn("_apply_post_copy_freshness", repository)
        self.assertNotIn("calculate_system_plan", repository)
        self.assertNotIn("optimize_order_plan", repository)

    def test_approve_recovers_historical_cancelled_draft(self) -> None:
        command = _source(COMMAND_SERVICE)
        approve = command.split("def approve_order_plan", 1)[1].split(
            "\ndef ",
            1,
        )[0]
        self.assertIn("ensure_geometry_draft_from_cancelled", approve)
        self.assertIn("يمكن اعتماد خطة قص في حالة المسودة فقط.", approve)

    def test_ui_and_translations_advertise_matching_draft(self) -> None:
        context = _source(CONTEXT_UX)
        translations = _source(TRANSLATIONS)
        confirm = (
            "A matching draft copy will be prepared for re-approval without recalculation"
        )
        success = (
            "Cutting plan approval was cancelled. A matching draft is ready for review and re-approval."
        )
        self.assertIn(confirm, context)
        self.assertIn(success, context)
        self.assertIn("prefer_plan_tab", context)
        self.assertIn(confirm, translations)
        self.assertIn(success, translations)
        self.assertIn("مسودة مطابقة", translations)


if __name__ == "__main__":
    unittest.main()
