from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "public" / "js" / "notes" / "notes_panel.js"


class TestA156NotesPanelLifecycle(unittest.TestCase):
    def setUp(self) -> None:
        self.source = PANEL.read_text(encoding="utf-8")

    def test_open_and_close_invalidate_old_async_work(self) -> None:
        self.assertIn("mutationGeneration: 0", self.source)
        self.assertIn("function invalidateTransientWork()", self.source)
        open_body = self.source.split("function openForOrder", 1)[1].split(
            "function close",
            1,
        )[0]
        close_body = self.source.split("function close", 1)[1].split(
            "function refresh",
            1,
        )[0]
        self.assertIn("invalidateTransientWork();", open_body)
        self.assertIn("invalidateTransientWork();", close_body)
        self.assertIn("state.context = null;", open_body)

    def test_mutation_response_cannot_take_over_a_new_panel_lifecycle(self) -> None:
        body = self.source.split("function performMutation", 1)[1].split(
            "function submitCurrentDraft",
            1,
        )[0]
        self.assertIn("const generation = ++state.mutationGeneration", body)
        self.assertIn("generation !== state.mutationGeneration", body)
        self.assertIn("orderName !== state.orderName", body)
        self.assertIn("!state.isOpen", body)
        # A successful response still updates list/form projection consumers even
        # when the drawer that initiated it is no longer current.
        self.assertLess(
            body.index("emitContextUpdated(context)"),
            body.index("generation !== state.mutationGeneration"),
        )

    def test_load_response_requires_current_open_drawer(self) -> None:
        body = self.source.split("function loadCurrentOrder", 1)[1].split(
            "function referenceArgs",
            1,
        )[0]
        self.assertIn("generation !== state.loadGeneration", body)
        self.assertIn("orderName !== state.orderName", body)
        self.assertIn("!state.isOpen", body)

    def test_panel_has_explicit_destroy_and_route_cleanup(self) -> None:
        self.assertIn("function destroy()", self.source)
        self.assertIn('removeEventListener("click", onClick)', self.source)
        self.assertIn('removeEventListener("keydown", onKeydown)', self.source)
        self.assertIn('frappe.router.on("change"', self.source)
        export_body = self.source.split("window.AlmdinaNotesPanel = Object.freeze", 1)[1]
        self.assertIn("destroy,", export_body)


if __name__ == "__main__":
    unittest.main()
