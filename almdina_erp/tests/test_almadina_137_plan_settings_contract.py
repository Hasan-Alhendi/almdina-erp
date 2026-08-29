from __future__ import annotations

from pathlib import Path

import pytest

from almdina_erp.almdina_erp.domain.cutting.plan_settings import (
    PlanSettingsValidationError,
    normalize_plan_settings,
)


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_REPOSITORY = (
    ROOT / "almdina_erp" / "infrastructure" / "frappe" / "cutting_plan_runtime_repository.py"
)
WORKSPACE = ROOT / "almdina_erp" / "infrastructure" / "frappe" / "cutting_plan_workspace.py"
PLAN_EDIT_SERVICE = ROOT / "almdina_erp" / "services" / "plan_settings_edit_service.py"
PRODUCTION_SETTINGS = ROOT / "almdina_erp" / "services" / "production_settings_service.py"
PREVIEW_SERVICE = ROOT / "almdina_erp" / "services" / "cutting_plan_preview_service.py"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def valid_settings(**overrides):
    values = {
        "optimization_mode": "auto_pro",
        "machine_type": "Auto",
        "optimization_time_limit_sec": 10,
        "kerf_mm": 3,
        "preferred_trim_mm": 5,
    }
    values.update(overrides)
    return normalize_plan_settings(**values)


def test_zero_kerf_and_trim_are_preserved_exactly() -> None:
    settings = valid_settings(kerf_mm=0, preferred_trim_mm=0)

    assert settings.kerf_mm == 0
    assert settings.preferred_trim_mm == 0
    assert settings.trim_margin_mm == 0


@pytest.mark.parametrize("time_limit", [0, -1, float("nan"), float("inf")])
def test_optimization_time_limit_must_be_finite_and_positive(time_limit: float) -> None:
    with pytest.raises(PlanSettingsValidationError):
        valid_settings(optimization_time_limit_sec=time_limit)


@pytest.mark.parametrize(
    ("fieldname", "value"),
    [("kerf_mm", -0.1), ("preferred_trim_mm", -0.1)],
)
def test_kerf_and_trim_reject_negative_values(fieldname: str, value: float) -> None:
    with pytest.raises(PlanSettingsValidationError):
        valid_settings(**{fieldname: value})


def test_factory_defaults_only_fallback_when_numeric_value_is_missing() -> None:
    backend = source(RUNTIME_REPOSITORY)

    assert "def _numeric_or_default(value: Any, default: float)" in backend
    assert "return default if value is None else value" in backend
    assert "flt(settings.default_kerf_mm) or 3" not in backend
    assert "flt(settings.default_trim_margin_mm) or 5" not in backend
    assert "existing = latest_plan(order_name)" in backend
    assert "plan_settings(existing) if existing else factory_default_plan_settings()" in backend


def test_all_plan_settings_entry_paths_use_the_canonical_domain_validator() -> None:
    edit_backend = source(PLAN_EDIT_SERVICE)
    factory_backend = source(PRODUCTION_SETTINGS)
    workspace_backend = source(WORKSPACE)
    preview_backend = source(PREVIEW_SERVICE)

    assert "normalize_plan_settings(" in edit_backend
    assert "normalize_plan_settings(" in factory_backend
    assert "normalize_plan_settings(" in workspace_backend
    assert "normalize_plan_settings_updates(" in preview_backend


def test_final_calculation_does_not_replace_zero_with_falsy_defaults() -> None:
    backend = source(WORKSPACE)

    assert "flt(plan.optimization_time_limit_sec) or 10" not in backend
    assert "flt(plan.kerf_mm) or" not in backend
    assert "flt(plan.trim_margin_mm) or" not in backend


def test_preview_and_final_calculation_share_validated_plan_setting_names() -> None:
    preview_backend = source(PREVIEW_SERVICE)
    workspace_backend = source(WORKSPACE)

    for storage_name in (
        '"packing_mode"',
        '"cutting_machine_type"',
        '"optimization_time_limit_sec"',
        '"kerf_mm"',
        '"trim_margin_mm"',
    ):
        assert storage_name in preview_backend

    for canonical_name in (
        "optimization_mode",
        "machine_type",
        "optimization_time_limit_sec",
        "kerf_mm",
        "preferred_trim_mm",
    ):
        assert canonical_name in workspace_backend
