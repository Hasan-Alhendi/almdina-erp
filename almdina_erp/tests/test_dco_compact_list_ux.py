from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIST_JS = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "list_view"
    / "door_cutting_order_compact_list_ux.js"
)
CANONICAL_LIST_JS = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "list_view"
    / "door_cutting_order_list.js"
)
LIST_CSS = ROOT / "public" / "css" / "door_cutting_order_list.css"
MANIFEST = ROOT / "frontend_assets.py"


class TestDcoCompactListUx(unittest.TestCase):
    def test_compact_assets_preserve_the_canonical_list_runtime_owner(self) -> None:
        manifest = MANIFEST.read_text(encoding="utf-8")
        canonical = (
            '"Door Cutting Order": '
            '"public/js/door_cutting_order/list_view/door_cutting_order_list.js"'
        )
        compact_global = (
            '"/assets/almdina_erp/js/door_cutting_order/list_view/'
            'door_cutting_order_compact_list_ux.js?v=13"'
        )

        self.assertIn('"/assets/almdina_erp/css/door_cutting_order_list.css?v=13"', manifest)
        self.assertIn(compact_global, manifest)
        self.assertIn(canonical, manifest)
        self.assertNotIn(
            '"Door Cutting Order": [\n'
            '        "public/js/door_cutting_order/list_view/door_cutting_order_list.js"',
            manifest,
        )

    def test_list_uses_canonical_document_name_without_display_only_id_rewrite(self) -> None:
        source = LIST_JS.read_text(encoding="utf-8")

        self.assertNotIn("compactOrderId", source)
        self.assertNotIn("name: compactOrderId", source)
        self.assertNotIn(r"/^DCO-(\d{4})-(.+)$/", source)

    def test_long_text_is_capped_at_22_characters_and_remains_keyboard_filterable(self) -> None:
        source = LIST_JS.read_text(encoding="utf-8")

        self.assertIn('const MAX_TEXT_CHARACTERS = 22;', source)
        block = re.search(
            r'const TRUNCATED_TEXT_FIELDS = Object\.freeze\(\[(.*?)\]\);',
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(block)
        fields = re.findall(r'"([a-z_]+)"', block.group(1))
        self.assertEqual(fields, ["board_description", "order_notes"])
        self.assertIn('Array.from(text)', source)
        self.assertIn('characters.slice(0, limit)', source)
        self.assertIn('<button type="button"', source)
        self.assertIn(
            'class="filterable dco-list-compact-text dco-list-filterable-text ellipsis${boardClass}"',
            source,
        )
        self.assertIn('data-filter=', source)
        self.assertIn('title=', source)
        self.assertIn('aria-label=', source)
        self.assertNotIn('<a class="filterable dco-list-compact-text', source)

    def test_board_item_gets_pill_presentation_without_changing_other_compact_fields(self) -> None:
        source = LIST_JS.read_text(encoding="utf-8")
        css = LIST_CSS.read_text(encoding="utf-8")

        self.assertIn('fieldname === "board_description" ? " dco-list-board-pill" : ""', source)
        self.assertIn('.dco-list-filterable-text.dco-list-board-pill', css)
        self.assertIn('border-radius: 999px;', css)
        self.assertIn('background: var(--subtle-fg);', css)

    def test_edge_color_is_plain_text_instead_of_a_pill(self) -> None:
        css = LIST_CSS.read_text(encoding="utf-8")

        self.assertIn('.dco-order-list .dco-list-edge-color', css)
        self.assertIn('border-radius: 0 !important;', css)
        self.assertIn('background: transparent !important;', css)
        self.assertIn('box-shadow: none !important;', css)
        self.assertIn('font-weight: inherit !important;', css)

    def test_compact_module_has_bounded_initialization_and_no_parallel_runtime(self) -> None:
        source = LIST_JS.read_text(encoding="utf-8")

        self.assertIn('const existing = frappe.listview_settings[DOCTYPE] || {};', source)
        self.assertIn('const originalOnload = existing.onload;', source)
        self.assertIn('const formatters = Object.assign({}, existing.formatters || {});', source)
        self.assertIn('onload(listview)', source)
        self.assertIn('applyDefaultDesktopPageLength(listview);', source)
        self.assertNotIn('preserveSavedListSettingsOrder', source)
        self.assertNotIn('_dcoOrderNotesColumnInstalled', source)
        self.assertNotIn('style.textContent', source)
        self.assertNotIn('document.createElement', source)
        self.assertNotIn('MutationObserver', source)
        self.assertNotIn('setTimeout', source)
        self.assertNotIn('setInterval', source)
        self.assertNotIn('frappe.call', source)
        self.assertNotIn('refresh(listview)', source)

    def test_frappe_list_settings_are_the_only_column_order_owner(self) -> None:
        canonical = CANONICAL_LIST_JS.read_text(encoding="utf-8")
        compact = LIST_JS.read_text(encoding="utf-8")

        self.assertNotIn('function applyOrderNotesColumnOrder', canonical)
        self.assertNotIn('function installOrderNotesColumnOrder', canonical)
        self.assertNotIn('installOrderNotesColumnOrder(listview);', canonical)
        self.assertNotIn('_dcoOrderNotesColumnInstalled', canonical)
        self.assertNotIn('_dcoOrderNotesColumnInstalled', compact)
        self.assertNotIn('preserveSavedListSettingsOrder', compact)

    def test_default_desktop_page_length_is_500_without_changing_mobile_default(self) -> None:
        source = LIST_JS.read_text(encoding="utf-8")

        self.assertIn('const DEFAULT_DESKTOP_PAGE_LENGTH = 500;', source)
        self.assertIn('typeof frappe.is_mobile === "function" && frappe.is_mobile()', source)
        self.assertIn('if (isMobile) return;', source)
        self.assertIn('listview.start = 0;', source)
        self.assertIn('listview.page_length = DEFAULT_DESKTOP_PAGE_LENGTH;', source)
        self.assertIn('listview.selected_page_count = DEFAULT_DESKTOP_PAGE_LENGTH;', source)
        self.assertIn('data-value="${DEFAULT_DESKTOP_PAGE_LENGTH}"', source)
        self.assertIn('listview._dcoDefaultPageLengthApplied = true;', source)

    def test_column_widths_and_hidden_activity_areas_are_dco_scoped(self) -> None:
        css = LIST_CSS.read_text(encoding="utf-8")

        self.assertIn('@media (min-width: 601px)', css)
        self.assertIn('.dco-order-list .list-row .level-left', css)
        self.assertIn('.dco-order-list .list-row-head .level-left', css)
        self.assertIn('gap: 2px;', css)
        self.assertIn('.dco-order-list .list-row-col[data-fieldname] {', css)
        self.assertIn('margin: 0 !important;', css)
        self.assertIn('flex: 0 0 96px !important;', css)
        self.assertIn('.dco-order-list .list-row-col[data-fieldname="name"]', css)
        self.assertIn('width: 78px !important;', css)
        self.assertIn('.dco-order-list .list-row-col[data-fieldname="status_field"]', css)
        self.assertIn('.dco-order-list .list-row-col[data-fieldname="order_date"]', css)
        self.assertIn('width: 82px !important;', css)
        self.assertIn('.dco-order-list .list-row-col[data-fieldname="customer"]', css)
        self.assertIn('width: 92px !important;', css)
        self.assertIn('.dco-order-list .list-row-col[data-fieldname="important_note_preview"]', css)
        self.assertIn('flex: 0 0 92px !important;', css)
        self.assertIn('.dco-order-list .dco-important-note-link', css)
        self.assertIn('.dco-order-list .list-row-col[data-fieldname="current_production_stage"]', css)
        self.assertIn('.dco-order-list .list-row-col[data-fieldname="department_status"]', css)
        self.assertIn('.dco-order-list .list-row-head > .level-right', css)
        self.assertIn('.dco-order-list .list-row > .level-right', css)
        self.assertIn('display: none !important;', css)
        self.assertIn('.dco-order-list .dco-list-filterable-text', css)
        self.assertNotIn('nth-child', css)

    def test_important_note_is_contained_inside_its_own_column(self) -> None:
        css = LIST_CSS.read_text(encoding="utf-8")

        self.assertIn(
            '.dco-order-list .list-row-col[data-fieldname="important_note_preview"] > *',
            css,
        )
        self.assertIn('min-width: 0;', css)
        self.assertIn('width: 100%;', css)
        self.assertIn('box-sizing: border-box;', css)
        self.assertIn('overflow: hidden;', css)
        self.assertIn(
            '.dco-order-list .dco-important-note-link .dco-important-note-text',
            css,
        )
        self.assertIn('flex: 1 1 auto;', css)
        self.assertIn('text-overflow: ellipsis;', css)

    def test_operational_filters_are_compact_and_stay_side_by_side(self) -> None:
        css = LIST_CSS.read_text(encoding="utf-8")

        self.assertIn('.dco-order-list .dco-status-filter-slot {', css)
        self.assertIn('display: inline-flex !important;', css)
        self.assertIn('gap: 5px !important;', css)
        self.assertIn('width: auto !important;', css)
        self.assertIn('[data-fieldname="status"]', css)
        self.assertIn('width: 118px !important;', css)
        self.assertIn('[data-fieldname="current_assignee"]', css)
        self.assertIn('width: 138px !important;', css)
        self.assertIn('.dco-order-list .dco-status-filter-slot select.form-control', css)
        self.assertIn('height: 30px !important;', css)
        self.assertIn('border-radius: 8px !important;', css)
        self.assertIn('background-color: var(--control-bg) !important;', css)

    def test_native_filter_button_matches_compact_toolbar_without_global_frappe_changes(self) -> None:
        css = LIST_CSS.read_text(encoding="utf-8")

        self.assertIn('.dco-order-list .filter-section > .filter-selector {', css)
        self.assertIn('.dco-order-list .filter-section > .filter-selector .btn-group', css)
        self.assertIn('flex-direction: row !important;', css)
        self.assertIn('height: 30px;', css)
        self.assertIn('border-radius: 8px;', css)
        self.assertIn('.dco-order-list .filter-section > .filter-selector .filter-button', css)
        self.assertIn('min-width: 72px;', css)
        self.assertIn('.dco-order-list .filter-section > .filter-selector .filter-x-button', css)
        self.assertIn('width: 28px !important;', css)
        self.assertIn('.dco-order-list .filter-section > .filter-selector .button-label', css)
        self.assertIn('white-space: nowrap !important;', css)
        self.assertNotIn('.page-form .filter-selector', css)


if __name__ == "__main__":
    unittest.main()
