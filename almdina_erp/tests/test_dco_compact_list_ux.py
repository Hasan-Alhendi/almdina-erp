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
            'door_cutting_order_compact_list_ux.js"'
        )

        self.assertIn('"/assets/almdina_erp/css/door_cutting_order_list.css"', manifest)
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
        self.assertIn('class="filterable dco-list-compact-text dco-list-filterable-text ellipsis${boardClass}"', source)
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
        self.assertNotIn('style.textContent', source)
        self.assertNotIn('document.createElement', source)
        self.assertNotIn('MutationObserver', source)
        self.assertNotIn('setTimeout', source)
        self.assertNotIn('setInterval', source)
        self.assertNotIn('frappe.call', source)
        self.assertNotIn('refresh(listview)', source)

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

    def test_saved_list_settings_are_not_overridden_by_legacy_order_notes_policy(self) -> None:
        source = CANONICAL_LIST_JS.read_text(encoding="utf-8")
        helper = source.split("function hasSavedListFieldOrder", 1)[1].split(
            "function applyOrderNotesColumnOrder",
            1,
        )[0]
        reorder = source.split("function applyOrderNotesColumnOrder", 1)[1].split(
            "function installOrderNotesColumnOrder",
            1,
        )[0]

        self.assertIn("listview.list_view_settings.fields", helper)
        self.assertIn("JSON.parse(raw)", helper)
        self.assertIn("Array.isArray(fields) && fields.length > 0", helper)
        self.assertIn("if (hasSavedListFieldOrder(listview)) return false;", reorder)
        self.assertIn('columnFieldname(column) === "order_notes"', reorder)
        self.assertIn('columnFieldname(column) === "edge_color"', reorder)

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
        self.assertIn('width: 96px !important;', css)
        self.assertIn('.dco-order-list .dco-important-note-link', css)
        self.assertIn('.dco-order-list .list-row-col[data-fieldname="current_production_stage"]', css)
        self.assertIn('.dco-order-list .list-row-col[data-fieldname="department_status"]', css)
        self.assertIn('.dco-order-list .list-row-head > .level-right', css)
        self.assertIn('.dco-order-list .list-row > .level-right', css)
        self.assertIn('display: none !important;', css)
        self.assertIn('.dco-order-list .dco-list-filterable-text', css)
        self.assertNotIn('nth-child', css)


if __name__ == "__main__":
    unittest.main()
