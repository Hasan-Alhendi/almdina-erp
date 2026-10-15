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
        "apc-actor-status",
        "apc-capability-copy",
        "apc-impact-section",
        'role="status"',
        'aria-live="polite"',
        'aria-atomic="true"',
        "apc-role-mount",
        'fieldtype: "Link"',
    ):
        assert marker in renderer

    assert 'aria-label="${esc(capability.label)}"' in renderer
    assert "Permission management" in renderer
    assert "Active admin session" in renderer


def test_permissions_polish_has_clear_enabled_dirty_and_focus_states() -> None:
    css = CSS.read_text(encoding="utf-8")

    assert ".apc-capability:has(.apc-capability-input:checked)" in css
    assert ".apc-dirty.is-dirty::before" in css
    assert ".apc-switch input:focus-visible + .apc-slider" in css
    assert "safe-area-inset-bottom" in css
    assert "prefers-reduced-motion" in css
    assert "border-radius: 15px" in css
    assert "No unsaved changes" in RENDERER.read_text(encoding="utf-8")
    assert 'className: "apc-save"' in RENDERER.read_text(encoding="utf-8")
    assert 'className: "apc-reset"' in RENDERER.read_text(encoding="utf-8")


def test_permissions_polish_remains_responsive_and_dense() -> None:
    css = CSS.read_text(encoding="utf-8")
    patterns = (ROOT / "public" / "css" / "almdina_patterns.css").read_text(encoding="utf-8")

    for breakpoint in (
        "@media(max-width:1100px)",
        "@media(max-width:900px)",
        "@media(max-width:650px)",
        "@media(max-width:430px)",
    ):
        assert breakpoint in css

    # Summary density lives on the shared pattern; capability rows stay 2-column.
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in patterns
    assert ".apc-stats" in css
    assert "grid-template-columns: auto minmax(0, 1fr)" in css


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


def test_permissions_polish_uses_theme_tokens_not_light_only_paints() -> None:
    """Regression: hardcoded Light hex forced white cards/text under Dark Mode."""
    css = CSS.read_text(encoding="utf-8")
    assert "background: var(--alm-card);" in css
    assert "color: var(--alm-text-strong);" in css
    assert "color: var(--alm-text-subtle);" in css
    assert "background: var(--alm-surface-muted);" in css
    assert "background: linear-gradient(180deg, var(--alm-accent-soft), var(--alm-card) 55%)" in css
    assert "background: linear-gradient(90deg, var(--alm-accent-soft), var(--alm-card) 50%)" in css
    assert "color: var(--alm-status-info-fg);" in css
    assert "background: var(--alm-status-warning-bg);" in css or "background: var(--alm-warning-bg);" in css
    # No parallel Light-only paint board left as bare hex (fallbacks inside var() OK).
    bare = []
    for line in css.splitlines():
        stripped = line
        while "var(" in stripped:
            start = stripped.find("var(")
            depth = 0
            end = start
            for i, ch in enumerate(stripped[start:], start):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            stripped = stripped[:start] + stripped[end:]
        if "#" in stripped:
            bare.append(stripped.strip())
    assert bare == [], bare
