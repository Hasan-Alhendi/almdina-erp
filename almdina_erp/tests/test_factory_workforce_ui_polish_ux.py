from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "public" / "js" / "factory_workforce" / "renderer.js"
CSS = ROOT / "public" / "css" / "factory_workforce.css"


def test_workforce_polish_has_professional_hierarchy_and_accessibility() -> None:
    renderer = RENDERER.read_text(encoding="utf-8")

    for marker in (
        "aw-hero",
        "aw-eyebrow",
        "aw-hero-meta",
        "aw-toolbar-heading",
        "aw-search-control",
        "aw-avatar",
        "aw-role-row",
        "aw-user-grid",
        'role="status"',
        'aria-live="polite"',
        'role="alert"',
        'role="search"',
    ):
        assert marker in renderer

    assert "إدارة القوى العاملة" in renderer
    assert "الأدوار والصلاحيات لا تُمنح تلقائيًا" in renderer


def test_workforce_polish_is_dense_and_responsive() -> None:
    css = CSS.read_text(encoding="utf-8")

    assert ".aw-user-grid" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in css
    for breakpoint in (
        "@media(max-width:1200px)",
        "@media(max-width:980px)",
        "@media(max-width:720px)",
        "@media(max-width:480px)",
    ):
        assert breakpoint in css
    assert "prefers-reduced-motion" in css


def test_workforce_polish_distinguishes_operational_states() -> None:
    renderer = RENDERER.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")

    assert 'user.enabled ? "is-enabled-user" : "is-disabled-user"' in renderer
    assert "aw-active-warning" in renderer
    assert ".aw-card.is-enabled-user" in css
    assert ".aw-card.is-disabled-user" in css
    assert ".aw-stat-enabled" in css
    assert ".aw-stat-disabled" in css
    assert ".aw-stat-assignments" in css


def test_workforce_polish_is_presentation_only() -> None:
    renderer = RENDERER.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    surface = f"{renderer}\n{css}"

    for forbidden in (
        "frappe.call(",
        "workforce_service",
        "AlmdinaFactoryWorkforceApi",
        "AlmdinaFactoryWorkforceState",
        "System Manager",
        "Administrator",
        "Order Entry",
        "CNC Worker",
        "Drawing Worker",
    ):
        assert forbidden not in surface

    for action_class in (
        "aw-edit",
        "aw-password",
        "aw-toggle",
        "aw-audit-open",
        "aw-adopt-user",
        "aw-refresh",
        "aw-search",
        "aw-enabled-filter",
    ):
        assert action_class in renderer
