from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CUTTING_PLAN = ROOT / "public" / "js" / "door_cutting_order" / "cutting_plan"
PLAN_CONTENT = CUTTING_PLAN / "door_cutting_order_plan_content_ux.js"
PLAN_STYLES = CUTTING_PLAN / "door_cutting_order_plan_content_styles.js"
PLAN_PRESENTER = CUTTING_PLAN / "door_cutting_order_plan_board_presenter.js"
PLAN_RENDERER = CUTTING_PLAN / "door_cutting_order_cutting_plan_renderer.js"


class TestCuttingPlanBoardGalleryUX(unittest.TestCase):
    def test_screen_layout_is_container_aware_and_responsive(self) -> None:
        content = PLAN_CONTENT.read_text(encoding="utf-8")
        presenter = PLAN_PRESENTER.read_text(encoding="utf-8")
        styles = PLAN_STYLES.read_text(encoding="utf-8")

        self.assertIn("function desiredBoardColumns", presenter)
        self.assertIn("MOBILE_VIEWPORT_MAX_PX = 600", presenter)
        self.assertIn("TABLET_VIEWPORT_MAX_PX = 1024", presenter)
        self.assertIn("TWO_COLUMN_MIN_PX = 520", presenter)
        self.assertIn("THREE_COLUMN_MIN_PX = 760", presenter)
        self.assertIn("FOUR_COLUMN_MIN_PX = 1180", presenter)
        self.assertIn("viewport <= MOBILE_VIEWPORT_MAX_PX", presenter)
        self.assertIn("viewport <= TABLET_VIEWPORT_MAX_PX", presenter)
        self.assertIn("available >= FOUR_COLUMN_MIN_PX", presenter)
        self.assertIn("return 3", presenter)
        self.assertIn("dco-board-gallery", presenter)
        self.assertIn('data-board-columns="4"', styles)
        self.assertIn('data-board-columns="3"', styles)
        self.assertIn('data-board-columns="2"', styles)
        self.assertIn("BOARD_VIEWPORT_HEIGHT_RATIO", presenter)
        self.assertIn("--dco-board-screen-max-width", presenter)
        self.assertIn("ResizeObserver", content)
        self.assertIn("boardPresenter().layoutBoardGallery(planRoot)", content)

    def test_gallery_uses_compact_cards_to_fit_more_boards(self) -> None:
        presenter = PLAN_PRESENTER.read_text(encoding="utf-8")
        styles = PLAN_STYLES.read_text(encoding="utf-8")

        self.assertIn("BOARD_GAP_PX = 8", presenter)
        self.assertIn("BOARD_CARD_CHROME_PX = 12", presenter)
        self.assertIn("padding:5px !important", styles)
        self.assertIn("border-radius:10px !important", styles)
        self.assertIn("box-shadow:none !important", styles)
        self.assertIn("min-height:27px", styles)
        self.assertIn("- BOARD_CARD_CHROME_PX", presenter)

    def test_gallery_preserves_board_ratio_and_has_focus_view(self) -> None:
        presenter = PLAN_PRESENTER.read_text(encoding="utf-8")
        styles = PLAN_STYLES.read_text(encoding="utf-8")

        self.assertIn("function boardAspect", presenter)
        self.assertIn("--dco-board-aspect", presenter)
        self.assertIn("aspect-ratio:var(--dco-board-aspect", styles)
        self.assertIn("dco-board-focus-trigger", presenter)
        self.assertIn("function openBoardFocus", presenter)
        self.assertIn("dco-board-focus__dialog", presenter)
        self.assertIn('event.key === "Escape"', presenter)
        self.assertIn('button.setAttribute("aria-label", "تكبير اللوح")', presenter)

    def test_focus_view_is_materially_larger_and_user_zoomable(self) -> None:
        presenter = PLAN_PRESENTER.read_text(encoding="utf-8")
        styles = PLAN_STYLES.read_text(encoding="utf-8")

        self.assertIn("FOCUS_INITIAL_ZOOM = 1.25", presenter)
        self.assertIn("FOCUS_MAX_ZOOM = 2", presenter)
        self.assertIn("function focusFitWidth", presenter)
        self.assertIn("function applyFocusZoom", presenter)
        self.assertIn("availableBoardHeight", presenter)
        self.assertIn("dco-board-focus__zoom", presenter)
        self.assertIn("dco-board-focus__fit", presenter)
        self.assertIn('data-focus-zoom="in"', presenter)
        self.assertIn('data-focus-zoom="out"', presenter)
        self.assertIn(".dco-board-focus .dco-sheet-title", styles)
        self.assertIn("display:none !important", styles)
        self.assertIn("max-width:none !important", styles)

    def test_workshop_print_layout_remains_renderer_owned(self) -> None:
        content_source = PLAN_CONTENT.read_text(encoding="utf-8")
        renderer_source = PLAN_RENDERER.read_text(encoding="utf-8")

        self.assertNotIn("MAX_SHEETS_PER_PAGE", content_source)
        self.assertNotIn("buildPrintPages", content_source)
        self.assertIn("MAX_SHEETS_PER_PAGE = 10", renderer_source)
        self.assertIn("buildPrintPages", renderer_source)
        self.assertIn("sizeBoardsForPage", renderer_source)


if __name__ == "__main__":
    unittest.main()
