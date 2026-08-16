from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "public" / "js" / "factory_permissions" / "renderer.js"
CSS = ROOT / "public" / "css" / "factory_permissions.css"


def test_permissions_polish_keeps_ui_semantics_accessible() -> None:
    renderer = RENDERER.read_text(encoding="utf-8")

    for marker in (
        "apc-eyebrow",
        "apc-panel-kicker",
        "apc-actor-icon",
        "apc-capability-copy",
        "apc-impact-section",
        'role="status"',
        'aria-live="polite"',
        'aria-atomic="true"',
        'role="combobox"',
    ):
        assert marker in renderer

    assert 'aria-label="${esc(capability.label)}"' in renderer
    assert "إدارة الصلاحيات" in renderer
    assert "المستخدم الحالي" in renderer


def test_permissions_polish_has_clear_enabled_dirty_and_focus_states() -> None:
    css = CSS.read_text(encoding="utf-8")

    assert ".apc-capability:has(.apc-capability-input:checked)" in css
    assert ".apc-dirty.is-dirty::before" in css
    assert ".apc-switch input:focus-visible + .apc-slider" in css
    assert "safe-area-inset-bottom" in css
    assert "prefers-reduced-motion" in css


def test_permissions_polish_remains_responsive_and_dense() -> None:
    css = CSS.read_text(encoding="utf-8")

    for breakpoint in (
        "@media(max-width:1100px)",
        "@media(max-width:900px)",
        "@media(max-width:650px)",
        "@media(max-width:430px)",
    ):
        assert breakpoint in css

    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in css
    assert "grid-template-columns: 42px minmax(0, 1fr)" in css


def test_permissions_polish_is_presentation_only() -> None:
    renderer = RENDERER.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    surface = f"{renderer}\n{css}"

    for forbidden in (
        "frappe.call(",
        "permission_management_service",
        "AlmdinaFactoryPermissionsApi",
        "System Manager",
        "Administrator",
        "Order Entry",
        "CNC Worker",
        "Drawing Worker",
    ):
        assert forbidden not in surface

    assert "<style" not in renderer
    assert "apc-savebar" in renderer
    assert ".apc-savebar" in css
