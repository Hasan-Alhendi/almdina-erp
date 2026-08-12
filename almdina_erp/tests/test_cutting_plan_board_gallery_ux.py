from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN_CONTENT = ROOT / "public" / "js" / "door_cutting_order_plan_content_ux.js"
PLAN_RENDERER = ROOT / "public" / "js" / "door_cutting_order_cutting_plan_renderer.js"


class TestCuttingPlanBoardGalleryUX(unittest.TestCase):
    def test_screen_layout_is_container_aware_and_responsive(self) -> None:
        source = PLAN_CONTENT.read_text(encoding="utf-8")

        self.assertIn("function desiredBoardColumns", source)
        self.assertIn("if (available >= 1400) return 4", source)
        self.assertIn("if (available >= 980) return 3", source)
        self.assertIn("if (available >= 620) return 2", source)
        self.assertIn("dco-board-gallery", source)
        self.assertIn('data-board-columns="4"', source)
        self.assertIn('data-board-columns="3"', source)
        self.assertIn('data-board-columns="2"', source)
        self.assertIn("BOARD_VIEWPORT_HEIGHT_RATIO", source)
        self.assertIn("--dco-board-screen-max-width", source)
        self.assertIn("ResizeObserver", source)

    def test_gallery_preserves_board_ratio_and_has_focus_view(self) -> None:
        source = PLAN_CONTENT.read_text(encoding="utf-8")

        self.assertIn("function boardAspect", source)
        self.assertIn("--dco-board-aspect", source)
        self.assertIn("aspect-ratio:var(--dco-board-aspect", source)
        self.assertIn("dco-board-focus-trigger", source)
        self.assertIn("function openBoardFocus", source)
        self.assertIn("dco-board-focus__dialog", source)
        self.assertIn('event.key === "Escape"', source)
        self.assertIn('button.setAttribute("aria-label", "تكبير اللوح")', source)

    def test_focus_view_is_materially_larger_and_user_zoomable(self) -> None:
        source = PLAN_CONTENT.read_text(encoding="utf-8")

        self.assertIn("FOCUS_INITIAL_ZOOM = 1.25", source)
        self.assertIn("FOCUS_MAX_ZOOM = 2", source)
        self.assertIn("function focusFitWidth", source)
        self.assertIn("function applyFocusZoom", source)
        self.assertIn("availableBoardHeight", source)
        self.assertIn("dco-board-focus__zoom", source)
        self.assertIn("dco-board-focus__fit", source)
        self.assertIn('data-focus-zoom="in"', source)
        self.assertIn('data-focus-zoom="out"', source)
        self.assertIn(".dco-board-focus .dco-sheet-title", source)
        self.assertIn("display:none !important", source)
        self.assertIn("max-width:none !important", source)

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
