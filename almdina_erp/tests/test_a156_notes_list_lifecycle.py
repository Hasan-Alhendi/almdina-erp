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
            "function importantColumnTargetIndex",
            1,
        )[0]
        self.assertIn("savedListSettingsFields(listview)", body)
        self.assertIn("fieldname: IMPORTANT_FIELD", body)
        self.assertIn('fieldname || "") === "order_notes"', body)
        self.assertIn("fields.splice(notesIndex >= 0 ? notesIndex + 1 : fields.length, 0, entry)", body)
        self.assertIn("settings.fields = JSON.stringify(fields)", body)

    def test_saved_list_settings_order_is_authoritative_for_important_note(self) -> None:
        body = self.source.split("function importantColumnTargetIndex", 1)[1].split(
            "function ensureImportantColumn",
            1,
        )[0]
        self.assertIn("savedListSettingsFields(listview)", body)
        self.assertIn("desired.indexOf(IMPORTANT_FIELD)", body)
        self.assertIn("listSettingsFieldname(column) === desired[index]", body)
        self.assertIn("return nextIndex", body)
        self.assertIn("return previousIndex + 1", body)

    def test_existing_or_missing_important_column_is_reconciled_after_list_setup(self) -> None:
        body = self.source.split("function ensureImportantColumn", 1)[1].split(
            "function reconcileColumns",
            1,
        )[0]
        self.assertIn("ensureImportantFieldInListSettings(listview)", body)
        self.assertIn("const before = columns.map(listSettingsFieldname)", body)
        self.assertIn("const currentIndex = columns.findIndex", body)
        self.assertIn("columns.splice(currentIndex, 1)[0]", body)
        self.assertIn("importantColumnTargetIndex(listview, columns)", body)
        self.assertIn("columns.splice(targetIndex, 0, important)", body)
        self.assertIn("return !arraysMatch(before, after)", body)
        self.assertIn("saved List Settings", body)
        self.assertIn("Do not rewrite unrelated", body)

    def test_reconciliation_is_idempotent_when_saved_order_is_already_rendered(self) -> None:
        self.assertIn("function arraysMatch", self.source)
        body = self.source.split("function ensureImportantColumn", 1)[1].split(
            "function reconcileColumns",
            1,
        )[0]
        self.assertIn("const after = columns.map(listSettingsFieldname)", body)
        self.assertIn("!arraysMatch(before, after)", body)

    def test_desktop_important_preview_is_capped_at_exactly_22_characters(self) -> None:
        self.assertIn("const IMPORTANT_PREVIEW_CHARACTERS = 22;", self.source)
        body = self.source.split("function truncateImportantPreview", 1)[1].split(
            "function formatter",
            1,
        )[0]
        self.assertIn("Array.from(text)", body)
        self.assertIn("limit - 1", body)
        self.assertIn("…", body)
        formatter = self.source.split("function formatter", 1)[1].split(
            "frappe.listview_settings",
            1,
        )[0]
        self.assertIn("truncateImportantPreview(preview)", formatter)
        self.assertIn('title="${escapeHtml(preview)}"', formatter)

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

    def test_new_list_instance_disposes_previous_runtime_and_syncs_settings(self) -> None:
        body = self.source.split("function installRuntime", 1)[1].split(
            "function truncateImportantPreview",
            1,
        )[0]
        self.assertIn("activeListView && activeListView !== listview", body)
        self.assertIn("disposeRuntime(activeListView)", body)
        self.assertIn("ensureImportantFieldInListSettings(listview)", body)

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
