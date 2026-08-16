from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "public" / "js" / "factory_production_settings" / "renderer.js"
CSS = ROOT / "public" / "css" / "factory_production_settings.css"


def test_production_settings_polish_has_clear_arabic_hierarchy_and_feedback() -> None:
    renderer = RENDERER.read_text(encoding="utf-8")

    for marker in (
        "aps-eyebrow",
        "aps-hero-assurances",
        "aps-section-intro",
        "aps-section-kicker",
        "aps-permission-dot",
        "aps-readonly-note",
        "aps-legacy-summary-copy",
        "aps-note-icon",
        "aps-audit-dot",
        'role="status"',
        'aria-live="polite"',
        'role="alert"',
    ):
        assert marker in renderer

    assert "إعدادات التشغيل" in renderer
    assert "قابل للتعديل" in renderer
    assert "عرض فقط" in renderer
    assert "بيانات إعدادات قديمة محفوظة" in renderer
    assert "للقراءة فقط" in renderer


def test_production_settings_polish_distinguishes_editable_and_readonly_sections() -> None:
    renderer = RENDERER.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")

    assert 'section.editable ? "is-editable" : "is-readonly"' in renderer
    assert ".aps-section.is-editable" in css
    assert ".aps-section.is-readonly" in css
    assert ".aps-permission.readonly" in css
    assert ".aps-readonly-note" in css
    assert 'class="btn btn-primary aps-edit"' in renderer


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
