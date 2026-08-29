from __future__ import annotations

from pathlib import Path

import pytest

from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
    BoardGeometry,
    OptimizeOrderPlanCommand,
    OptimizerOptions,
    optimize_order_plan,
)
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


class _CapturingEngine:
    def __init__(self) -> None:
        self.calls: list[dict[str, float]] = []

    def expand_pieces(self, rows):
        return list(rows)

    def optimize(
        self,
        pieces,
        board_width_cm,
        board_length_cm,
        kerf_cm,
        **kwargs,
    ):
        self.calls.append(
            {
                "board_width_cm": board_width_cm,
                "board_length_cm": board_length_cm,
                "kerf_cm": kerf_cm,
                "time_limit_sec": kwargs["time_limit_sec"],
            }
        )
        return {
            "sheets": [{"sheet_no": 1, "pieces": []}],
            "used_area_m2": 0,
            "total_board_area_m2": 2,
            "waste_area_m2": 2,
            "method_label": "test",
            "industrial_metrics": {},
        }

    def validate(self, plan, pieces, board_width_cm, board_length_cm):
        return []


def test_zero_kerf_and_trim_reach_optimizer_without_fallback() -> None:
    settings = valid_settings(
        optimization_mode="auto",
        kerf_mm=0,
        preferred_trim_mm=0,
        optimization_time_limit_sec=7,
    )
    engine = _CapturingEngine()

    optimize_order_plan(
        OptimizeOrderPlanCommand(
            engine_version="test",
            input_fingerprint="fingerprint",
            board=BoardGeometry(
                full_width_cm=100,
                full_length_cm=200,
                trim_cm=settings.preferred_trim_mm / 10,
                kerf_cm=settings.kerf_mm / 10,
            ),
            optimizer=OptimizerOptions(
                selected_mode=settings.optimization_mode,
                machine_type=settings.machine_type,
                time_limit_sec=settings.optimization_time_limit_sec,
                exact_piece_limit=40,
                min_remnant_width_cm=0,
                min_remnant_length_cm=0,
                min_remnant_area_m2=0,
            ),
            piece_rows=(),
        ),
        engine=engine,
    )

    assert engine.calls == [
        {
            "board_width_cm": 100,
            "board_length_cm": 200,
            "kerf_cm": 0,
            "time_limit_sec": 7,
        }
    ]


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
    assert "trim_cm=plan_settings.preferred_trim_mm / 10" in backend
    assert "kerf_cm=plan_settings.kerf_mm / 10" in backend
    assert "time_limit_sec=plan_settings.optimization_time_limit_sec" in backend


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
