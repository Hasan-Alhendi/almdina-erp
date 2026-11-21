"""Factory policy validation, localization and preview lifecycle."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import pytest
from almdina_erp.almdina_erp.domain.cutting.plan_settings import EDGE_PROTECTION_FIELDS, EdgeProtectionPolicy
ROOT = Path(__file__).resolve().parents[1]

def _services():
    from almdina_erp.tests.frappe_test_stub import install_if_unavailable
    install_if_unavailable()
    from almdina_erp.almdina_erp.services import cutting_plan_preview_service, production_settings_service
    return cutting_plan_preview_service, production_settings_service


@pytest.mark.parametrize("field", EDGE_PROTECTION_FIELDS)
@pytest.mark.parametrize("value", [-1, "nan", "inf", "bad", "", None])
def test_backend_update_rejects_invalid_protection_before_persistence(field, value):
    _, service = _services()
    with pytest.raises(service.frappe.ValidationError):
        service._apply_values({}, {field: value})


@pytest.mark.parametrize("field", EDGE_PROTECTION_FIELDS)
def test_changing_factory_policy_rejects_stale_preview_before_commit_or_continue(monkeypatch, field):
    service, _ = _services()
    from almdina_erp.almdina_erp.application.cutting.plan_preview_session import optimizer_settings_fingerprint
    source = SimpleNamespace(name="source", modified="same", revision=1)
    settings = EdgeProtectionPolicy(5, 10).field_values()
    session = SimpleNamespace(version=2, expires_at="", order_name="order", user="user",
        source_plan_name="source", source_plan_modified="same", source_revision=1,
        settings=settings, settings_fingerprint=optimizer_settings_fingerprint(settings))
    monkeypatch.setattr(service, "FrappeCuttingPlanPreviewStore", lambda: SimpleNamespace(get=lambda _: session))
    monkeypatch.setattr(service, "_system_draft", lambda *a: source)
    monkeypatch.setattr(service.frappe.session, "user", "user")
    changed = {**settings, field: settings[field]+1}
    monkeypatch.setattr(service.frappe, "get_cached_doc", lambda *a: changed, raising=False)
    with pytest.raises(service.frappe.ValidationError, match="protection settings changed"):
        service._session(SimpleNamespace(name="order"), "preview")


def test_policy_hash_changes_both_axes_but_keeps_legacy_preview_hashes():
    from almdina_erp.almdina_erp.application.cutting.plan_preview_session import optimizer_settings_fingerprint
    legacy = dict(packing_mode="smart", kerf_mm=5, trim_margin_mm=0, max_centerable_edge_gap_cm=5)
    original_hash = optimizer_settings_fingerprint(legacy)
    current = {**legacy, **EdgeProtectionPolicy().field_values()}
    assert optimizer_settings_fingerprint(current) != original_hash
    for field in EDGE_PROTECTION_FIELDS:
        assert optimizer_settings_fingerprint({**current, field: 5}) != optimizer_settings_fingerprint(current)
    assert optimizer_settings_fingerprint(legacy) == original_hash


def test_settings_update_persists_both_axes_and_explicit_zero():
    _, service = _services()
    class Settings(dict):
        def set(self, key, value):
            self[key] = value
    settings = Settings()
    service._apply_values(settings, EdgeProtectionPolicy(5, 10).field_values())
    assert settings == EdgeProtectionPolicy(5, 10).field_values()
    service._apply_values(settings, {"edge_protection_horizontal_mm": 0})
    assert settings == EdgeProtectionPolicy(0, 10).field_values()


def test_factory_policy_change_during_preview_generation_is_rejected(monkeypatch):
    service, _ = _services()
    monkeypatch.setattr(service.frappe, "copy_doc", deepcopy, raising=False)
    monkeypatch.setattr(service, "_apply_settings", lambda *a: None)
    monkeypatch.setattr(service, "calculate_system_plan", lambda *a, **k:
        SimpleNamespace(candidate_snapshots=(), snapshot=EdgeProtectionPolicy().field_values()))
    with pytest.raises(service.frappe.ValidationError, match="protection settings changed"):
        service._build_session(SimpleNamespace(), SimpleNamespace(), EdgeProtectionPolicy(5, 10).field_values())


def test_new_ui_messages_have_one_valid_arabic_translation_each():
    import csv
    keys = ["Horizontal edge protection (mm)", "Vertical edge protection (mm)",
        "Minimum actual gap from original board edges when centering is not eligible. Trim already counts; zero disables this axis. Unsafe moves keep the existing plan.",
        "Edge protection margins must be finite non-negative numbers.",
        "Edge protection settings changed. Recalculate the preview before saving."]
    with (ROOT/"translations/ar.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    for key in keys:
        matches = [row for row in rows if row and row[0] == key]
        assert len(matches) == 1
        assert len(matches[0]) == 2
        assert any("\u0600" <= char <= "\u06ff" for char in matches[0][1])
