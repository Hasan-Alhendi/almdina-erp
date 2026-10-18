from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "frontend_assets.py"
LIST_CSS = ROOT / "public" / "css" / "door_cutting_order_list.css"
RTL_CSS = ROOT / "public" / "css" / "door_cutting_order_list_rtl_subject.css"
LIST_JS = ROOT / "public" / "js" / "door_cutting_order" / "list_view" / "door_cutting_order_list.js"
COMPACT_JS = (
    ROOT / "public" / "js" / "door_cutting_order" / "list_view" / "door_cutting_order_compact_list_ux.js"
)


class TestDcoListRtlSubject(unittest.TestCase):
    def test_rtl_subject_asset_loads_after_main_list_css(self) -> None:
        manifest = MANIFEST.read_text(encoding="utf-8")
        main = '"/assets/almdina_erp/css/door_cutting_order_list.css?v=18"'
        rtl = '"/assets/almdina_erp/css/door_cutting_order_list_rtl_subject.css?v=2"'

        self.assertIn(main, manifest)
        self.assertIn(rtl, manifest)
        self.assertLess(manifest.index(main), manifest.index(rtl))

    def test_checkbox_stays_at_logical_start_while_id_text_remains_ltr(self) -> None:
        css = RTL_CSS.read_text(encoding="utf-8")
        list_css = LIST_CSS.read_text(encoding="utf-8")
        subject = (
            ".dco-order-list .list-row-col:is(.name, .list-subject, "
            '[data-fieldname="name"])'
        )

        self.assertIn(subject, css)
        self.assertIn("direction: inherit;", css)
        self.assertIn("unicode-bidi: normal;", css)
        self.assertIn(f"{subject} > :not(.select-like)", css)
        self.assertIn("direction: ltr;", css)
        self.assertIn("unicode-bidi: isolate;", css)
        self.assertIn(f"{subject} > .select-like", css)
        self.assertIn("flex: 0 0 auto;", css)
        self.assertNotIn("nth-child", css)
        self.assertNotIn("direction: rtl;", css)
        self.assertNotIn("direction:rtl;", css)
        self.assertNotIn("row-reverse", css)
        for forbidden in (
            "margin-left",
            "margin-right",
            "padding-left",
            "padding-right",
            "text-align: left",
            "text-align: right",
        ):
            self.assertNotIn(forbidden, css)
        self.assertNotIn("left:", css)
        self.assertNotIn("right:", css)

        # Main list CSS must not force the subject column LTR; that reorders the
        # checkbox away from the logical start on Arabic pages.
        self.assertIn(
            ".dco-order-list .list-row-col:is(.order_date, [data-fieldname=\"order_date\"])",
            list_css,
        )
        self.assertNotIn(
            ".name, .list-subject, .order_date, [data-fieldname=\"name\"], [data-fieldname=\"order_date\"]",
            list_css,
        )

    def test_subject_order_fix_does_not_add_observers_or_polling(self) -> None:
        css = RTL_CSS.read_text(encoding="utf-8")
        for forbidden in (
            "MutationObserver",
            "setInterval",
            "requestAnimationFrame",
            "querySelector",
            "appendChild",
            "insertBefore",
        ):
            self.assertNotIn(forbidden, css)

        # Presentation-only: the existing list modules must keep their own
        # contracts, and this subject-order fix must not invent a new DOM mover.
        for path in (LIST_JS, COMPACT_JS):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("door_cutting_order_list_rtl_subject", source)
            self.assertNotIn("select-like", source)


if __name__ == "__main__":
    unittest.main()
