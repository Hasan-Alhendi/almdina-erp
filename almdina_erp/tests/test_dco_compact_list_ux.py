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

    def test_id_compaction_is_display_only(self) -> None:
        source = LIST_JS.read_text(encoding="utf-8")

        self.assertIn(r'/^DCO-(\d{4})-(.+)$/', source)
        self.assertIn('match[1].slice(-2)', source)
        self.assertIn('name: compactOrderId', source)
        self.assertNotIn('doc.name =', source)
        self.assertNotIn('set_value', source)
        self.assertNotIn('rename_doc', source)

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
            'class="filterable dco-list-compact-text dco-list-filterable-text ellipsis"',
            source,
        )
        self.assertIn('data-filter=', source)
        self.assertIn('title=', source)
        self.assertIn('aria-label=', source)
        self.assertNotIn('<a class="filterable dco-list-compact-text', source)

    def test_compact_module_has_bounded_initialization_and_no_parallel_runtime(self) -> None:
        source = LIST_JS.read_text(encoding="utf-8")

        self.assertIn('const existing = frappe.listview_settings[DOCTYPE] || {};', source)
        self.assertIn('const originalOnload = existing.onload;', source)
        self.assertIn('Object.assign({}, existing.formatters || {}, {', source)
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

    def test_column_widths_live_in_external_css_and_use_stable_field_selectors(self) -> None:
        css = LIST_CSS.read_text(encoding="utf-8")

        self.assertIn('@media (min-width: 601px)', css)
        self.assertIn('.dco-order-list .list-row-col[data-fieldname] {', css)
        self.assertIn('margin-right: 6px !important;', css)
        self.assertIn('.dco-order-list .list-row-col[data-fieldname="name"]', css)
        self.assertIn('width: 90px !important;', css)
        self.assertIn('.dco-order-list .list-row-col[data-fieldname="status_field"]', css)
        self.assertIn('width: 92px !important;', css)
        self.assertIn('.dco-order-list .list-row-col[data-fieldname="order_date"]', css)
        self.assertIn('.dco-order-list .list-row-col[data-fieldname="customer"]', css)
        self.assertIn('width: 110px !important;', css)
        self.assertIn('.dco-order-list .dco-list-filterable-text', css)
        self.assertNotIn('nth-child', css)


if __name__ == "__main__":
    unittest.main()
