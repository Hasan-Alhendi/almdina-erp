from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIST_INTEGRATION = ROOT / "public" / "js" / "notes" / "notes_dco_list_integration.js"


class TestA156NotesListLifecycle(unittest.TestCase):
    def setUp(self) -> None:
        self.source = LIST_INTEGRATION.read_text(encoding="utf-8")

    def test_runtime_cleanup_disconnects_observer_frame_and_click_handler(self) -> None:
        body = self.source.split("function disposeRuntime", 1)[1].split(
            "function schedule",
            1,
        )[0]
        self.assertIn("_almdinaNotesObserver.disconnect()", body)
        self.assertIn("cancelFrame(listview._almdinaNotesFrame)", body)
        self.assertIn('removeEventListener("click", listview._almdinaNotesClickHandler)', body)
        self.assertIn("activeListView === listview", body)

    def test_saved_layout_exposes_important_note_to_list_settings(self) -> None:
        body = self.source.split("function ensureImportantFieldInListSettings", 1)[1].split(
            "function ensureImportantColumn",
            1,
        )[0]
        self.assertIn("savedListSettingsFields(listview)", body)
        self.assertIn("fieldname: IMPORTANT_FIELD", body)
        self.assertIn('fieldname || "") === "order_notes"', body)
        self.assertIn("fields.splice(notesIndex >= 0 ? notesIndex + 1 : fields.length, 0, entry)", body)
        self.assertIn("settings.fields = JSON.stringify(fields)", body)

    def test_saved_list_layout_still_restores_mandatory_important_signal(self) -> None:
        body = self.source.split("function ensureImportantColumn", 1)[1].split(
            "function reconcileColumns",
            1,
        )[0]
        self.assertIn("ensureImportantFieldInListSettings(listview)", body)
        self.assertIn("importantColumnDefinition()", body)
        self.assertIn('columnFieldname(column) === "order_notes"', body)
        self.assertIn("columns.splice(notesIndex + 1, 0, important)", body)
        self.assertIn("tagIndex", body)

    def test_existing_important_column_keeps_user_selected_order(self) -> None:
        body = self.source.split("function ensureImportantColumn", 1)[1].split(
            "function reconcileColumns",
            1,
        )[0]
        self.assertIn(
            "if (columns.some(column => columnFieldname(column) === IMPORTANT_FIELD)) return false;",
            body,
        )
        self.assertNotIn("reorderImportantColumn", self.source)
        self.assertNotIn("nextNotesIndex", self.source)

    def test_projection_event_immediately_refreshes_desktop_rows(self) -> None:
        helper = self.source.split("function refreshProjectionRows", 1)[1].split(
            "function openPanel",
            1,
        )[0]
        self.assertIn('typeof listview.render_list !== "function"', helper)
        self.assertIn("listview.render_list()", helper)

        event_body = self.source.split("document.addEventListener(UPDATED_EVENT", 1)[1].split(
            "if (window.frappe",
            1,
        )[0]
        self.assertIn("doc[IMPORTANT_FIELD]", event_body)
        self.assertIn("refreshProjectionRows(listview)", event_body)
        self.assertIn("schedule(listview)", event_body)

    def test_new_list_instance_disposes_previous_runtime(self) -> None:
        body = self.source.split("function installRuntime", 1)[1].split(
            "function formatter",
            1,
        )[0]
        self.assertIn("activeListView && activeListView !== listview", body)
        self.assertIn("disposeRuntime(activeListView)", body)

    def test_route_change_releases_dco_list_observers(self) -> None:
        self.assertIn('frappe.router.on("change"', self.source)
        self.assertIn('route[0] === "List"', self.source)
        self.assertIn("route[1] === DOCTYPE", self.source)
        self.assertIn("if (!isCurrentList) disposeRuntime(listview)", self.source)

    def test_mobile_projection_stays_inside_existing_card(self) -> None:
        self.assertIn('card.querySelector(".dco-card-date-row")', self.source)
        self.assertIn("card.insertBefore(next, date)", self.source)
        self.assertIn('className = "dco-card-important-note"', self.source)
        self.assertIn("if (!preview)", self.source)
        self.assertIn("existing.remove()", self.source)


if __name__ == "__main__":
    unittest.main()
