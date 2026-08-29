from __future__ import annotations

from pathlib import Path

import pytest

from almdina_erp.almdina_erp.application.cutting.plan_revisions import (
    PlanRecord,
    PlanSettings,
    UpdatePlanSettingsCommand,
    update_settings,
)
from almdina_erp.almdina_erp.domain.cutting.catalog import (
    DEFAULT_OPTIMIZATION_MODE_ID,
    LEGACY_ENGINE_MODES,
    MACHINE_TYPES,
    OPTIMIZATION_MODES,
    engine_mode_for_request,
    machine_type_catalog,
    optimization_catalog,
    public_mode_value,
)
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import (
    DRAFT,
    SYSTEM,
    CuttingPlanLifecycleError,
)


EXPECTED_IDS = (
    "auto",
    "auto_pro",
    "deep_search",
    "optimal",
    "cp_sat_ortools",
    "mip_cbc",
    "scip",
    "highs",
    "gecode",
    "chuffed",
    "maxrects",
    "guillotine",
    "shelf",
    "skyline",
    "genetic",
    "simulated_annealing",
)
EXPECTED_AVAILABLE_MAPPINGS = {
    "auto": "Auto",
    "auto_pro": "Auto Pro",
    "deep_search": "Deep Search",
    "optimal": "Optimal Search",
    "maxrects": "MaxRects Best Short Side",
    "guillotine": "Guillotine Short Axis",
    "shelf": "Shelf Horizontal",
    "skyline": "Skyline Bottom Left",
}
EXPECTED_UNAVAILABLE_IDS = {
    "cp_sat_ortools",
    "mip_cbc",
    "scip",
    "highs",
    "gecode",
    "chuffed",
    "genetic",
    "simulated_annealing",
}
ROOT = Path(__file__).resolve().parents[1]
PLAN_EDIT_SESSION = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "cutting_plan"
    / "door_cutting_order_plan_edit_session_ux.js"
)
PLAN_CONTROLS = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "cutting_plan"
    / "door_cutting_order_plan_controls_ux.js"
)
FACTORY_DIALOGS = ROOT / "public" / "js" / "factory_production_settings" / "dialogs.js"


class FakePlanRepository:
    def __init__(self, mode: str = "Auto Pro") -> None:
        self.plan = PlanRecord(
            name="CUT-PLAN-1",
            order_name="DCO-1",
            revision=1,
            status=DRAFT,
            source_type=SYSTEM,
            based_on_plan=None,
            settings=PlanSettings(
                optimization_mode=mode,
                machine_type="Auto",
                optimization_time_limit_sec=10,
                kerf_mm=3,
                trim_margin_mm=5,
            ),
        )
        self.saved: PlanSettings | None = None

    def get(self, plan_name: str) -> PlanRecord:
        assert plan_name == self.plan.name
        return self.plan

    def save_settings(self, plan_name: str, settings: PlanSettings) -> PlanRecord:
        assert plan_name == self.plan.name
        self.saved = settings
        return PlanRecord(
            name=self.plan.name,
            order_name=self.plan.order_name,
            revision=self.plan.revision,
            status=self.plan.status,
            source_type=self.plan.source_type,
            based_on_plan=self.plan.based_on_plan,
            settings=settings,
        )


def _settings(mode: str) -> PlanSettings:
    return PlanSettings(
        optimization_mode=mode,
        machine_type="Auto",
        optimization_time_limit_sec=10,
        kerf_mm=3,
        trim_margin_mm=5,
    )


def test_canonical_catalog_contains_exactly_the_sixteen_story_ids() -> None:
    assert tuple(mode.id for mode in OPTIMIZATION_MODES) == EXPECTED_IDS
    assert len(set(EXPECTED_IDS)) == 16
    assert DEFAULT_OPTIMIZATION_MODE_ID == "auto_pro"

    catalog = optimization_catalog()
    assert [entry["id"] for entry in catalog] == list(EXPECTED_IDS)
    assert {entry["id"] for entry in catalog if not entry["available"]} == EXPECTED_UNAVAILABLE_IDS


def test_current_engine_paths_are_mapped_without_optimizer_changes() -> None:
    actual = {
        mode.id: mode.engine_mode
        for mode in OPTIMIZATION_MODES
        if mode.engine_mode is not None
    }
    assert actual == EXPECTED_AVAILABLE_MAPPINGS

    for public_id, engine_mode in EXPECTED_AVAILABLE_MAPPINGS.items():
        assert engine_mode_for_request(public_id) == engine_mode
        assert engine_mode_for_request(engine_mode) == engine_mode
        assert public_mode_value(engine_mode) == public_id


def test_advanced_modes_are_canonical_not_legacy() -> None:
    assert {"auto_pro", "deep_search", "optimal"}.issubset(EXPECTED_IDS)
    assert "Auto Pro" not in LEGACY_ENGINE_MODES
    assert "Deep Search" not in LEGACY_ENGINE_MODES
    assert "Optimal Search" not in LEGACY_ENGINE_MODES


def test_historical_low_level_variant_is_preserved_exactly() -> None:
    historical = "MaxRects Best Area"
    assert historical in LEGACY_ENGINE_MODES
    assert public_mode_value(historical) == historical
    assert engine_mode_for_request(historical) == historical

    repository = FakePlanRepository(historical)
    result = update_settings(
        UpdatePlanSettingsCommand(
            plan_name=repository.plan.name,
            settings=_settings(historical),
        ),
        repository,
    )
    assert repository.saved is not None
    assert repository.saved.optimization_mode == historical
    assert result.settings.optimization_mode == historical


def test_canonical_public_id_is_persisted_as_existing_engine_value() -> None:
    repository = FakePlanRepository()
    result = update_settings(
        UpdatePlanSettingsCommand(
            plan_name=repository.plan.name,
            settings=_settings("auto_pro"),
        ),
        repository,
    )
    assert repository.saved is not None
    assert repository.saved.optimization_mode == "Auto Pro"
    assert result.settings.optimization_mode == "Auto Pro"


def test_known_but_unimplemented_mode_fails_closed_before_optimizer() -> None:
    repository = FakePlanRepository()
    with pytest.raises(
        CuttingPlanLifecycleError,
        match="optimization_mode_not_implemented:scip",
    ):
        update_settings(
            UpdatePlanSettingsCommand(
                plan_name=repository.plan.name,
                settings=_settings("scip"),
            ),
            repository,
        )
    assert repository.saved is None


def test_machine_types_share_one_domain_contract() -> None:
    assert tuple(machine.id for machine in MACHINE_TYPES) == (
        "Auto",
        "CNC Router",
        "Panel Saw",
    )
    assert [entry["id"] for entry in machine_type_catalog()] == [
        "Auto",
        "CNC Router",
        "Panel Saw",
    ]


def test_frontend_consumes_payload_catalog_instead_of_hardcoded_algorithm_list() -> None:
    edit_source = PLAN_EDIT_SESSION.read_text(encoding="utf-8")
    controls_source = PLAN_CONTROLS.read_text(encoding="utf-8")
    factory_source = FACTORY_DIALOGS.read_text(encoding="utf-8")

    assert 'catalog: "optimization_catalog"' in edit_source
    assert 'catalog: "machine_type_catalog"' in edit_source
    assert "data[catalogName]" in edit_source
    assert "optimization_catalog" in factory_source
    assert "machine_type_catalog" in factory_source

    # The old post-render patch was a duplicate catalog and a lifecycle race.
    assert "ADVANCED_MODES" not in controls_source
    assert "ensureAdvancedModes" not in controls_source

    for source in (edit_source, factory_source):
        assert 'value: "Auto Pro"' not in source
        assert 'value: "Deep Search"' not in source
        assert 'value: "Optimal Search"' not in source
