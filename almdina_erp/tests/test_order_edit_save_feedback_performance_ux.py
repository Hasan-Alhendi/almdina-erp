from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REVISION_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "core"
    / "door_cutting_order_revision_ux.js"
)


class TestOrderEditSaveFeedbackPerformanceUx(unittest.TestCase):
    def test_lock_path_defers_heavy_dependent_refresh(self) -> None:
        source = REVISION_UX.read_text(encoding="utf-8")
        lock = source.split("function lockEditSession", 1)[1].split(
            "async function flushPendingCostPriceEdits", 1
        )[0]

        self.assertIn("scheduleDependentUxRefresh(frm);", lock)
        self.assertNotIn("refreshDependentUx(frm);", lock)

    def test_dependent_refresh_is_deduplicated_and_yields_before_rendering(self) -> None:
        source = REVISION_UX.read_text(encoding="utf-8")
        scheduler = source.split("function scheduleDependentUxRefresh", 1)[1].split(
            "function enterEditSession", 1
        )[0]

        self.assertIn("frm.__almdinaDependentUxRefreshScheduled", scheduler)
        self.assertIn("window.requestAnimationFrame(queueAfterPaint);", scheduler)
        self.assertIn("window.setTimeout(run, 0);", scheduler)
        self.assertIn("refreshDependentUx(frm);", scheduler)

    def test_native_save_uses_single_success_notification(self) -> None:
        source = REVISION_UX.read_text(encoding="utf-8")
        after_save = source.split("after_save(frm) {", 1)[1].split("refresh(frm) {", 1)[0]

        self.assertIn("lockEditSession(frm, { silent: true });", after_save)
        self.assertNotIn(
            'message: __("تم حفظ التعديل وإعادة قفل الحقول.',
            after_save,
        )

    def test_after_save_and_refresh_share_the_same_deferred_batch(self) -> None:
        source = REVISION_UX.read_text(encoding="utf-8")
        lifecycle = source.split('frappe.ui.form.on("Door Cutting Order", {', 1)[1]

        self.assertGreaterEqual(lifecycle.count("scheduleDependentUxRefresh(frm);"), 3)
        self.assertNotIn(
            "requestAnimationFrame(() => refreshDependentUx(frm));",
            lifecycle,
        )


if __name__ == "__main__":
    unittest.main()
