from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "public" / "js" / "shop_floor_inbox" / "renderer.js"
CSS = ROOT / "public" / "css" / "shop_floor_responsive.css"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shop_floor_polish_has_clear_arabic_hierarchy_and_feedback_states() -> None:
    renderer = source(RENDERER)

    for marker in (
        "almdina-sf-hero",
        "almdina-sf-eyebrow",
        "almdina-sf-hero-stats",
        "almdina-sf-state",
        "almdina-sf-spinner",
        "almdina-sf-route-icon",
        "almdina-sf-list-section",
        "almdina-sf-account-heading",
        'role="status"',
        'aria-live="polite"',
        'role="alert"',
        'role="tablist"',
        'aria-selected="true"',
    ):
        assert marker in renderer

    assert "متابعة مراحل الإنتاج" in renderer
    assert "طلباتك التشغيلية" in renderer
    assert "معلومات المستخدم" in renderer
    assert "تعذر تحديث صالة الإنتاج" in renderer


def test_shop_floor_polish_keeps_actionable_and_completed_work_visually_distinct() -> None:
    renderer = source(RENDERER)
    css = source(CSS)

    assert 'terminal || completed ? "" : quickActionHtml(row, mode)' in renderer
    assert 'completed ? " is-completed" : ""' in renderer
    assert ".almdina-sf-order-card.is-completed" in css
    assert "background: #dcfce7 !important;" in css
    assert ".almdina-sf-list-title.is-completed" in css
    assert '.almdina-sf-order-card[data-status="Pending"]' in css
    assert '.almdina-sf-order-card[data-status="In Progress"]' in css
    assert '.almdina-sf-order-card[data-status="Paused"]' in css


def test_shop_floor_polish_is_dense_responsive_touch_safe_and_accessible() -> None:
    renderer = source(RENDERER)
    css = source(CSS)

    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in css
    assert "grid-template-columns: repeat(4, minmax(0, 1fr));" in css
    for breakpoint in (
        "@media (max-width: 1200px)",
        "@media (max-width: 900px)",
        "@media (max-width: 720px)",
        "@media (max-width: 480px)",
    ):
        assert breakpoint in css
    assert "min-height: 48px !important;" in css
    assert ":focus-visible" in css
    assert "prefers-reduced-motion" in css
    assert "overscroll-behavior-inline: contain" in css
    assert "-webkit-overflow-scrolling: touch" in css
    assert 'aria-label="${esc(`${action.label}' in renderer
    assert 'aria-label="${esc(`${__("فتح الطلب")}' in renderer


def test_shop_floor_polish_moves_page_visuals_out_of_inline_style_attributes() -> None:
    renderer = source(RENDERER)

    assert 'style="' not in renderer
    assert "almdina-sf-card-head" in renderer
    assert "almdina-sf-card-context" in renderer
    assert "almdina-sf-meta-item" in renderer
    assert "almdina-sf-card-actions" in renderer


def test_shop_floor_polish_is_presentation_only() -> None:
    renderer = source(RENDERER)
    css = source(CSS)
    surface = f"{renderer}\n{css}"

    for forbidden in (
        "frappe.call(",
        "shop_floor_query_service",
        "shop_floor_commands",
        "AlmdinaShopFloorInboxApi",
        "AlmdinaShopFloorInboxState",
        "AlmdinaShopFloorInboxController",
        "System Manager",
        "Administrator",
        "Production Manager",
        "Order Entry",
        "CNC Worker",
        "Drawing Worker",
    ):
        assert forbidden not in surface

    assert "AlmdinaShopFloorInboxViewModel" in renderer
    assert "AlmdinaShopFloorQuickActions" in renderer
