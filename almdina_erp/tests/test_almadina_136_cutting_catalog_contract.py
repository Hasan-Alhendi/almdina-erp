from __future__ import annotations

from pathlib import Path

import frappe
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
    OptimizationModeUnavailableError,
    engine_mode_for_request,
    machine_type_catalog,
    optimization_catalog,
    optimization_mode,
    public_mode_value,
    require_engine_mode,
)
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import DRAFT, SYSTEM
from almdina_erp.almdina_erp.infrastructure.frappe.optimization_mode_validation import (
    require_executable_optimization_mode,
)
from almdina_erp.almdina_erp.services.order_plan_permission_service import (
    recalculate_order,
)
from almdina_erp.almdina_erp.services.plan_settings_edit_service import (
    normalize_plan_settings_updates,
)


EXPECTED_ACTIVE_IDS = (
    "auto",
    "auto_pro",
    "deep_search",
    "optimal",
    "maxrects",
    "guillotine",
    "shelf",
    "skyline",
)
EXPECTED_DISABLED_IDS = (
    "cp_sat_ortools",
    "mip_cbc",
    "scip",
    "highs",
    "gecode",
    "chuffed",
    "genetic",
    "simulated_annealing",
)
EXPECTED_IDS = EXPECTED_ACTIVE_IDS + EXPECTED_DISABLED_IDS
EXPECTED_LABELS = {
    "auto": "تلقائي",
    "auto_pro": "تلقائي متقدم (موصى به)",
    "deep_search": "بحث معمّق",
    "optimal": "بحث أمثل",
    "maxrects": "تعبئة المستطيلات القصوى",
    "guillotine": "القص المقصلي",
    "shelf": "التعبئة بالرفوف",
    "skyline": "التعبئة بخط الأفق",
    "cp_sat_ortools": "البرمجة بالقيود — CP-SAT",
    "mip_cbc": "البرمجة الصحيحة المختلطة — CBC",
    "scip": "محلّل SCIP",
    "highs": "محلّل HiGHS",
    "gecode": "محلّل القيود Gecode",
    "chuffed": "محلّل القيود Chuffed",
    "genetic": "الخوارزمية الجينية",
    "simulated_annealing": "التلدين المُحاكى",
}
EXPECTED_IMPLEMENTED_MAPPINGS = {
    "auto": "Auto",
    "auto_pro": "Auto Pro",
    "deep_search": "Deep Search",
    "optimal": "Optimal Search",
    "maxrects": "MaxRects Best Short Side",
    "guillotine": "Guillotine Short Axis",
    "shelf": "Shelf Horizontal",
    "skyline": "Skyline Bottom Left",
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
ENGINE_ADAPTER = ROOT / "almdina_erp" / "infrastructure" / "cutting" / "domain_engine.py"


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
    assert [entry["id"] for entry in catalog if entry["available"]] == list(
        EXPECTED_ACTIVE_IDS
    )
    assert [entry["id"] for entry in catalog if not entry["available"]] == list(
        EXPECTED_DISABLED_IDS
    )
    assert all(
        entry["available"] == entry["implemented"] == entry["executable"]
        for entry in catalog
    )


def test_all_public_algorithm_labels_are_canonical_arabic_labels() -> None:
    catalog = optimization_catalog()
    assert {entry["id"]: entry["label"] for entry in catalog} == EXPECTED_LABELS


def test_current_engine_paths_are_mapped_without_optimizer_changes() -> None:
    actual = {
        mode.id: mode.engine_mode
        for mode in OPTIMIZATION_MODES
        if mode.engine_mode is not None
    }
    assert actual == EXPECTED_IMPLEMENTED_MAPPINGS

    for public_id, engine_mode in EXPECTED_IMPLEMENTED_MAPPINGS.items():
        assert engine_mode_for_request(public_id) == engine_mode
        assert engine_mode_for_request(engine_mode) == engine_mode
        assert public_mode_value(engine_mode) == public_id
        assert require_engine_mode(public_id) == engine_mode
        assert require_executable_optimization_mode(public_id) == engine_mode


def test_cp_sat_remains_known_but_disabled_until_it_has_an_independent_contract() -> None:
    mode = optimization_mode("cp_sat_ortools")
    assert mode is not None
    assert mode.engine_mode is None
    assert mode.implemented is False
    assert mode.executable is False
    assert optimization_catalog()[len(EXPECTED_ACTIVE_IDS)]["id"] == "cp_sat_ortools"

    with pytest.raises(
        OptimizationModeUnavailableError,
        match="optimization_mode_not_implemented:cp_sat_ortools",
    ):
        require_engine_mode("cp_sat_ortools")


def test_disabled_public_modes_fail_closed_at_user_request_boundaries() -> None:
    for mode_id in EXPECTED_DISABLED_IDS:
        label = EXPECTED_LABELS[mode_id]
        message = f"خوارزمية {label} غير متاحة للتنفيذ حاليًا. يرجى اختيار خوارزمية متاحة."

        with pytest.raises(frappe.ValidationError, match=message):
            require_executable_optimization_mode(mode_id)

        with pytest.raises(frappe.ValidationError, match=message):
            normalize_plan_settings_updates({"packing_mode": mode_id})

        # The whitelisted recalculation facade rejects the mode before any DB
        # read/mutation, so a crafted direct request cannot bypass the catalog.
        with pytest.raises(frappe.ValidationError, match=message):
            recalculate_order(order_name="DCO-1", packing_mode=mode_id)


def test_unknown_public_mode_has_a_distinct_fail_closed_error() -> None:
    with pytest.raises(
        frappe.ValidationError,
        match="خوارزمية التحسين المحددة غير معروفة. يرجى اختيار خوارزمية متاحة.",
    ):
        require_executable_optimization_mode("unknown_solver")


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
    assert require_engine_mode(historical) == historical

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


def test_public_id_is_persisted_as_canonical_identifier() -> None:
    repository = FakePlanRepository()
    result = update_settings(
        UpdatePlanSettingsCommand(
            plan_name=repository.plan.name,
            settings=_settings("auto_pro"),
        ),
        repository,
    )
    assert repository.saved is not None
    assert repository.saved.optimization_mode == "auto_pro"
    assert result.settings.optimization_mode == "auto_pro"


def test_known_unavailable_mode_remains_persistable_for_history_but_is_not_executable() -> None:
    repository = FakePlanRepository()
    result = update_settings(
        UpdatePlanSettingsCommand(
            plan_name=repository.plan.name,
            settings=_settings("scip"),
        ),
        repository,
    )
    assert repository.saved is not None
    assert repository.saved.optimization_mode == "scip"
    assert result.settings.optimization_mode == "scip"
    assert optimization_mode("scip") is not None
    assert optimization_mode("scip").executable is False

    with pytest.raises(
        OptimizationModeUnavailableError,
        match="optimization_mode_not_implemented:scip",
    ):
        require_engine_mode("scip")


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


def test_frontend_consumes_payload_catalog_and_blocks_disabled_modes() -> None:
    edit_source = PLAN_EDIT_SESSION.read_text(encoding="utf-8")
    controls_source = PLAN_CONTROLS.read_text(encoding="utf-8")
    factory_source = FACTORY_DIALOGS.read_text(encoding="utf-8")
    adapter_source = ENGINE_ADAPTER.read_text(encoding="utf-8")

    assert 'catalog: "optimization_catalog"' in edit_source
    assert 'catalog: "machine_type_catalog"' in edit_source
    assert "data[catalogName]" in edit_source
    assert 'option.available === false ? " disabled"' in edit_source
    assert "selected.available === false" in edit_source
    assert "optimization_catalog" in factory_source
    assert "machine_type_catalog" in factory_source
    assert "require_engine_mode(selected_mode)" in adapter_source

    # The old post-render patch was a duplicate catalog and a lifecycle race.
    assert "ADVANCED_MODES" not in controls_source
    assert "ensureAdvancedModes" not in controls_source

    for source in (edit_source, factory_source):
        assert 'value: "Auto Pro"' not in source
        assert 'value: "Deep Search"' not in source
        assert 'value: "Optimal Search"' not in source
        for mode_id in EXPECTED_IDS:
            assert f'value: "{mode_id}"' not in source
