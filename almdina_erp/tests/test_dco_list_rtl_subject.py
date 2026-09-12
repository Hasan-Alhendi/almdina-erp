from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "frontend_assets.py"
RTL_CSS = ROOT / "public" / "css" / "door_cutting_order_list_rtl_subject.css"


class TestDcoListRtlSubject(unittest.TestCase):
    def test_rtl_subject_asset_loads_after_main_list_css(self) -> None:
        manifest = MANIFEST.read_text(encoding="utf-8")
        main = '"/assets/almdina_erp/css/door_cutting_order_list.css?v=15"'
        rtl = '"/assets/almdina_erp/css/door_cutting_order_list_rtl_subject.css?v=1"'

        self.assertIn(main, manifest)
        self.assertIn(rtl, manifest)
        self.assertLess(manifest.index(main), manifest.index(rtl))

    def test_checkbox_stays_on_rtl_edge_while_id_text_remains_ltr(self) -> None:
        css = RTL_CSS.read_text(encoding="utf-8")
        subject = (
            '.dco-order-list .list-row-col:is(.name, .list-subject, '
            '[data-fieldname="name"])'
        )

        self.assertIn(subject, css)
        self.assertIn("direction: rtl;", css)
        self.assertIn("unicode-bidi: normal;", css)
        self.assertIn(f"{subject} > :not(.select-like)", css)
        self.assertIn("direction: ltr;", css)
        self.assertIn("unicode-bidi: isolate;", css)
        self.assertIn(f"{subject} > .select-like", css)
        self.assertIn("flex: 0 0 auto;", css)
        self.assertNotIn("nth-child", css)


if __name__ == "__main__":
    unittest.main()
