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
    def test_compact_list_assets_are_scoped_and_load_after_the_canonical_owner(self) -> None:
        manifest = MANIFEST.read_text(encoding="utf-8")
        canonical = "public/js/door_cutting_order/list_view/door_cutting_order_list.js"
        compact = "public/js/door_cutting_order/list_view/door_cutting_order_compact_list_ux.js"

        self.assertIn('"/assets/almdina_erp/css/door_cutting_order_list.css"', manifest)
        self.assertIn(canonical, manifest)
        self.assertIn(compact, manifest)
        self.assertLess(manifest.index(canonical), manifest.index(compact))

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
        self.assertIn('class="filterable dco-list-compact-text dco-list-filterable-text ellipsis"', source)
        self.assertIn('data-filter=', source)
        self.assertIn('title=', source)
        self.assertIn('aria-label=', source)
        self.assertNotIn('<a class="filterable dco-list-compact-text', source)

    def test_compact_module_has_no_lifecycle_or_inline_style_owner(self) -> None:
        source = LIST_JS.read_text(encoding="utf-8")

        self.assertNotIn('style.textContent', source)
        self.assertNotIn('document.createElement', source)
        self.assertNotIn('MutationObserver', source)
        self.assertNotIn('setTimeout', source)
        self.assertNotIn('frappe.call', source)
        self.assertNotIn('onload(listview)', source)
        self.assertNotIn('refresh(listview)', source)

    def test_column_widths_live_in_external_css_and_use_stable_field_selectors(self) -> None:
        css = LIST_CSS.read_text(encoding="utf-8")

        self.assertIn('@media (min-width: 601px)', css)
        self.assertIn('.dco-order-list .list-row-col[data-fieldname="name"]', css)
        self.assertIn('width: 108px !important;', css)
        self.assertIn('.dco-order-list .list-row-col[data-fieldname="order_date"]', css)
        self.assertIn('width: 96px !important;', css)
        self.assertIn('.dco-order-list .dco-list-filterable-text', css)
        self.assertNotIn('nth-child', css)


if __name__ == "__main__":
    unittest.main()
