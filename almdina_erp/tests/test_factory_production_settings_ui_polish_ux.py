from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "public" / "js" / "factory_production_settings" / "renderer.js"
CSS = ROOT / "public" / "css" / "factory_production_settings.css"


def test_production_settings_polish_has_clear_arabic_hierarchy_and_feedback() -> None:
    renderer = RENDERER.read_text(encoding="utf-8")

    for marker in (
        "alm-page-intro",
        "alm-page-intro--accented",
        "alm-section-header",
        "aps-section-intro",
        "aps-section-kicker",
        "aps-readonly-note",
        "aps-legacy-summary-copy",
        "aps-note-icon",
        "aps-audit-dot",
        'role="status"',
        'aria-live="polite"',
        'role="alert"',
    ):
        assert marker in renderer

    assert "Default factory operating settings" in renderer
    assert "Active operating values approved for all operations and workstations" in renderer
    assert "قابل للتعديل" not in renderer
    assert "aps-hero-updated" not in renderer
    assert "عرض فقط" not in renderer
    assert "Legacy settings data kept" in renderer
    assert "Read-only" in renderer


def test_production_settings_polish_distinguishes_editable_and_readonly_sections() -> None:
    renderer = RENDERER.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")

    assert 'section.editable ? "is-editable" : "is-readonly"' in renderer
    assert ".aps-section.is-editable" in css
    assert ".aps-section.is-readonly" in css
    assert ".aps-permission.readonly" in css
    assert ".aps-readonly-note" in css
    assert "AlmdinaUi.button" in renderer
    assert 'variant: "secondary"' in renderer
    assert 'className: "aps-edit"' in renderer
    assert "aps-section-accent" in renderer
    assert "aps-status-pill" in renderer
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in css


def test_production_settings_polish_is_dense_responsive_and_motion_safe() -> None:
    css = CSS.read_text(encoding="utf-8")

    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in css
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in css
    for breakpoint in (
        "@media(max-width:1100px)",
        "@media(max-width:760px)",
        "@media(max-width:480px)",
    ):
        assert breakpoint in css
    assert "prefers-reduced-motion" in css


def test_production_settings_polish_is_presentation_only() -> None:
    renderer = RENDERER.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    surface = f"{renderer}\n{css}"

    for forbidden in (
        "frappe.call(",
        "production_settings_service",
        "AlmdinaFactoryProductionSettingsApi",
        "AlmdinaFactoryProductionSettingsState",
        "AlmdinaFactoryProductionSettingsController",
        "System Manager",
        "Administrator",
        "Production Manager",
        "Order Entry",
        "CNC Worker",
        "Drawing Worker",
    ):
        assert forbidden not in surface

    assert "aps-edit" in renderer
    assert "data-section=" in renderer


def test_production_settings_polish_uses_theme_tokens_not_light_only_paints() -> None:
    """Regression: section/note/error paints must follow --alm-* theme boards."""
    import re

    css = CSS.read_text(encoding="utf-8")
    assert "background: var(--alm-card);" in css or "background: var(--alm-card, #fff);" in css
    assert "color: var(--alm-text-strong);" in css or "color: var(--alm-text-strong, #101828);" in css
    assert "color: var(--alm-status-danger-fg);" in css
    assert "var(--alm-brand-soft-fg" in css
    assert "background: color-mix(in srgb, var(--alm-accent) 18%, var(--alm-card));" in css
    # Intentional exception: WhatsApp QR needs opaque white for scanners.
    assert "/* QR must stay on opaque white for scanner contrast in both themes. */" in css
    qr_block = css.split(".aps-whatsapp-qr img", 1)[1].split("}", 1)[0]
    assert "background: #fff;" in qr_block

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
        if re.search(r"#[0-9a-fA-F]{3,8}", stripped):
            bare.append(stripped.strip())
    assert bare == ["background: #fff;"], bare


def test_production_settings_direction_uses_logical_properties() -> None:
    css = CSS.read_text(encoding="utf-8")
    templates = (ROOT / "public" / "css" / "almdina_page_templates.css").read_text(encoding="utf-8")
    renderer = RENDERER.read_text(encoding="utf-8")

    assert "function uiDirection()" in renderer
    assert "AlmdinaLocale" in renderer
    assert 'document.documentElement' in renderer
    assert 'dir="${uiDirection()}"' in renderer
    assert "text-align: start" in templates
    assert "direction: rtl" not in templates

    for forbidden in (
        "margin-left",
        "margin-right",
        "padding-left",
        "padding-right",
        "text-align: left",
        "text-align: right",
        "text-align:left",
        "text-align:right",
        "direction: rtl",
        "direction:rtl",
    ):
        assert forbidden not in css
    assert "left:" not in css
    assert "right:" not in css
    assert "inset-inline-start: 50%" in css
    assert "text-align: start" in css
    assert "margin-inline-start" in css
    assert "margin-inline-end" in css

    ltr_rules = [
        block.strip()
        for block in css.split("}")
        if "direction: ltr" in block or "direction:ltr" in block
    ]
    assert ltr_rules
    for block in ltr_rules:
        assert "unicode-bidi: isolate" in block or "unicode-bidi:isolate" in block
        assert ".aps-ltr-value" in block or ".aps-restore-warning code" in block
