"""Final edge preference: geometry, lifecycle, factory authority and export regressions."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from almdina_erp.almdina_erp.domain.cutting import expand_piece_groups
from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import sheet_cut_line_quality
from almdina_erp.almdina_erp.domain.cutting.edge_protection import protect_plan_edges
from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan
from almdina_erp.almdina_erp.domain.cutting.optimizer import enrich_plan_metrics, _largest_reusable_free_area
from almdina_erp.almdina_erp.domain.cutting.plan_settings import (
    EDGE_PROTECTION_FIELDS, EdgeProtectionPolicy, PlanSettingsValidationError,
)
from almdina_erp.almdina_erp.domain.cutting.primitives import make_placed_piece
from almdina_erp.almdina_erp.domain.cutting.sheet_edge_trim import (
    physical_edge_margins_mm, realize_sheet_edge_trim,
)

ROOT = Path(__file__).resolve().parents[1]
METRICS = dict(min_remnant_width_cm=10, min_remnant_length_cm=10, min_remnant_area_m2=.01)


def _plan(*, x=0, y=0, w=75, h=75, trim=0, qty=1, kerf=.5):
    sources = expand_piece_groups([dict(width_cm=w, length_cm=h, qty=qty, allow_rotation=False,
                                       piece_instance_id="edge-regression")])
    placed = [make_placed_piece(p, x, y + i * (h + kerf), w, h, False) for i, p in enumerate(sources)]
    sheet = dict(sheet_no=1, resource_kind="FULL_BOARD", full_width_cm=100, full_length_cm=100,
                 usable_width_cm=100-2*trim, usable_length_cm=100-2*trim,
                 w=100-2*trim, h=100-2*trim, applied_trim_width_cm=trim,
                 applied_trim_length_cm=trim, pieces=placed)
    result = dict(method_key="MaxRects Best Short Side", sheets=[sheet], unplaced=[], kerf_cm=kerf,
                  used_area_m2=w*h*qty/10000, total_board_area_m2=1, waste_area_m2=1-w*h*qty/10000)
    return enrich_plan_metrics(result, result["method_key"], "CNC Router", **METRICS), sources


def _protect(plan, sources, *, policy=None, **kwargs):
    return protect_plan_edges(plan, sources, 100, 100, plan["kerf_cm"],
        policy=policy or EdgeProtectionPolicy(5, 10), max_centerable_edge_gap_cm=5,
        machine_type=kwargs.pop("machine_type", "CNC Router"), mirroring_allowed=False,
        metric_options=kwargs.pop("metric_options", METRICS), **kwargs)


@pytest.mark.parametrize("axis", ["horizontal_mm", "vertical_mm"])
@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), -float("inf"), "bad", "", None])
def test_policy_rejects_invalid_values(axis, value):
    with pytest.raises(PlanSettingsValidationError):
        EdgeProtectionPolicy(**{axis: value})


def test_missing_factory_policy_is_disabled_and_zero_is_preserved():
    assert EdgeProtectionPolicy.from_settings({}).field_values() == dict.fromkeys(EDGE_PROTECTION_FIELDS, 0)
    assert EdgeProtectionPolicy("0", "2.5") == EdgeProtectionPolicy(0, 2.5)
    assert EdgeProtectionPolicy.from_settings(SimpleNamespace()) == EdgeProtectionPolicy()
    assert EdgeProtectionPolicy.from_settings(SimpleNamespace(edge_protection_vertical_mm=10)) == EdgeProtectionPolicy(0, 10)


@pytest.mark.parametrize("x,y,left,right,top,bottom", [
    (0, 0, 5, 245, 10, 240), (25, 25, 245, 5, 240, 10),
    (3, 3, 30, 220, 30, 220),
])
def test_acceptance_large_remainder_minimal_independent_axis_move(x, y, left, right, top, bottom):
    plan, sources = _plan(x=x, y=y)
    original = deepcopy(plan)
    result, decisions = _protect(plan, sources)
    assert physical_edge_margins_mm(result["sheets"][0]) == dict(left=left, right=right, top=top, bottom=bottom)
    assert not validate_plan(result, sources, 100, 100, kerf_cm=.5)
    assert plan == original
    assert len(result["sheets"]) == 1
    assert {d["reason"] for d in decisions} == ({"ALREADY_PROTECTED"} if x == 3 else {"EDGE_PROTECTED"})


@pytest.mark.parametrize("axis", ["x", "y"])
@pytest.mark.parametrize("gap,centered", [(4, True), (4.99999, True), (5, True), (5.00001, False), (10, False)])
def test_centering_boundary_is_each_gap_not_total_slack(axis, gap, centered):
    kwargs = {"w" if axis == "x" else "h": 100-gap}
    plan, sources = _plan(**kwargs)
    realize_sheet_edge_trim(plan["sheets"], full_width_cm=100, full_length_cm=100,
        preferred_width_trim_cm=0, preferred_length_trim_cm=0, balance_existing_applied=True,
        max_centerable_edge_gap_cm=5, min_remnant_width_cm=200, min_remnant_length_cm=200,
        min_remnant_area_m2=4)
    result, _ = _protect(plan, sources, metric_options=dict(min_remnant_width_cm=200,
        min_remnant_length_cm=200, min_remnant_area_m2=4))
    expected = gap/2 if centered else (.5 if axis == "x" else 1)
    assert result["sheets"][0]["pieces"][0][axis] == pytest.approx(expected)


def test_two_five_cm_gaps_keep_existing_centering_even_when_total_slack_is_ten():
    plan, sources = _plan(x=5, w=90)
    result, decisions = _protect(plan, sources)
    assert result["sheets"][0]["pieces"][0]["x"] == 5
    assert decisions[0]["reason"] == "CENTERED"


@pytest.mark.parametrize("trim,protection,expected", [(0, 5, .5), (.5, 5, 0), (.5, 10, .5), (1, 5, 0)])
def test_mandatory_trim_contributes_to_protection_without_double_counting(trim, protection, expected):
    plan, sources = _plan(trim=trim)
    result, _ = _protect(plan, sources, policy=EdgeProtectionPolicy(protection, 0))
    sheet = result["sheets"][0]
    assert sheet["pieces"][0]["x"] == pytest.approx(expected)
    assert sheet["applied_trim_width_cm"] == trim
    assert sheet["w"] == 100-2*trim


def test_zero_policy_is_exact_noop_and_repeated_protection_is_idempotent():
    plan, sources = _plan()
    assert _protect(plan, sources, policy=EdgeProtectionPolicy()) == (plan, [])
    once, _ = _protect(plan, sources)
    twice, decisions = _protect(once, sources)
    assert twice == once
    assert all(d["reason"] == "ALREADY_PROTECTED" for d in decisions)


@pytest.mark.parametrize("kerf", [0, .5])
def test_whole_rigid_group_preserves_kerf_row_alignment_and_shared_cutter_network(kerf):
    plan, sources = _plan(w=75, h=20, qty=3, kerf=kerf)
    before = plan["sheets"][0]
    result, _ = _protect(plan, sources)
    after = result["sheets"][0]
    for a, b in zip(before["pieces"], after["pieces"]):
        assert b["x"]-a["x"] == pytest.approx(.5)
        assert b["y"]-a["y"] == pytest.approx(1)
        assert {k:v for k,v in a.items() if k not in {"x", "y"}} == {k:v for k,v in b.items() if k not in {"x", "y"}}
    assert sheet_cut_line_quality(before, kerf)[:2] == pytest.approx(sheet_cut_line_quality(after, kerf)[:2])
    assert not validate_plan(result, sources, 100, 100, kerf_cm=kerf)


def test_remnant_can_lose_only_protection_strip_without_losing_factory_eligibility():
    plan, sources = _plan(w=75, h=100)
    result, decisions = _protect(plan, sources, policy=EdgeProtectionPolicy(5, 0))
    before = _largest_reusable_free_area(plan, **METRICS, machine_type="CNC Router")
    after = _largest_reusable_free_area(result, **METRICS, machine_type="CNC Router")
    assert (before, after) == pytest.approx((.25, .245))
    assert decisions[0]["reason"] == "EDGE_PROTECTED"
    strict = dict(min_remnant_width_cm=25, min_remnant_length_cm=100, min_remnant_area_m2=.25)
    rejected, decisions = _protect(plan, sources, policy=EdgeProtectionPolicy(5, 0), metric_options=strict)
    assert rejected == plan
    assert decisions[0]["reason"] == "REMNANT_PRESERVED"


@pytest.mark.parametrize("attribute,value", [
    ("piece_type", "L-Shaped Corner"), ("piece_type", "Clipped Corner"),
    ("piece_type", "Glass"), ("piece_type", "Special"), ("piece_type", "Joint"),
    ("geometry", {"outer": [[0,0]]}), ("overlays", [{"path": []}]),
    ("placement_outline_cm", [[0,0]]), ("glass_host_piece_id", 4),
    ("toolpaths", [[0,0]]), ("attached_geometry", [[0,0]]),
])
def test_protected_special_or_attached_geometry_is_never_moved(attribute, value):
    plan, sources = _plan()
    plan["sheets"][0]["pieces"][0][attribute] = value
    before = deepcopy(plan)
    assert _protect(plan, sources)[0] == before


def test_source_geometry_and_offcuts_are_protected_even_if_placement_is_reduced():
    plan, sources = _plan()
    sources[0]["overlays"] = [{"path": []}]
    assert _protect(plan, sources)[0] == plan
    sources[0].pop("overlays")
    plan["sheets"][0]["resource_kind"] = "OFFCUT"
    assert _protect(plan, sources)[0] == plan


@pytest.mark.parametrize("owner", ["sheet", "plan"])
def test_attached_toolpaths_on_sheet_or_plan_are_not_left_at_old_coordinates(owner):
    plan, sources = _plan()
    (plan["sheets"][0] if owner == "sheet" else plan)["cnc_toolpaths"] = [[0, 0], [75, 0]]
    result, decisions = _protect(plan, sources)
    assert result == plan
    assert all(d["reason"] == "UNSAFE_MOVE" for d in decisions)


def test_centered_row_blocks_whole_sheet_shift_that_would_undo_its_centering():
    plan, sources = _plan(w=96, h=20, qty=2)
    plan["sheets"][0]["pieces"][0]["x"] = 2
    # A shorter unprotected row shares the same sheet but must not drag the
    # valid centered row when the entire rigid collection is translated.
    plan["sheets"][0]["pieces"][1]["w"] = 75
    sources[1]["width_cm"] = 75
    result, decisions = _protect(plan, sources, policy=EdgeProtectionPolicy(5, 0))
    assert result == plan
    assert decisions[0]["reason"] == "REMNANT_PRESERVED"
    assert decisions[0]["detail"] == "centering_priority"


def test_impossible_target_and_failed_full_validation_leave_no_partial_mutations(monkeypatch):
    plan, sources = _plan()
    assert _protect(plan, sources, policy=EdgeProtectionPolicy(200, 200))[0] == plan
    from almdina_erp.almdina_erp.domain.cutting import edge_protection
    monkeypatch.setattr(edge_protection, "validate_plan", lambda *a, **k: ["unsafe"])
    result, decisions = _protect(plan, sources)
    assert result == plan
    assert all(d["reason"] == "UNSAFE_MOVE" and d["shift_mm"] == 0 for d in decisions)


def test_axis_rejection_does_not_block_a_safe_move_on_the_other_axis():
    plan, sources = _plan()
    result, decisions = _protect(plan, sources, policy=EdgeProtectionPolicy(200, 10))
    piece = result["sheets"][0]["pieces"][0]
    assert (piece["x"], piece["y"]) == (0, 1)
    assert [d["reason"] for d in decisions] == ["UNSAFE_MOVE", "EDGE_PROTECTED"]


def _command(**optimizer_options):
    from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
        BoardGeometry, OptimizeOrderPlanCommand, OptimizerOptions,
    )
    return OptimizeOrderPlanCommand("edge-test", "unchanged-input", BoardGeometry(100, 100, 0, .5),
        OptimizerOptions("smart", "CNC Router", .2, 40, 10, 10, .01,
                         edge_protection=EdgeProtectionPolicy(5, 10), **optimizer_options),
        (dict(width_cm=75, length_cm=20, qty=1, allow_rotation=False, piece_instance_id="edge-regression"),))


class _GalleryEngine:
    expand_pieces = staticmethod(expand_piece_groups)

    def optimize(self, sources, *args, **kwargs):
        variants = [_plan(y=y, h=20)[0] for y in (0, 10, 20, 30, 40)]
        return {**deepcopy(variants[0]), "smart_candidates": deepcopy(variants)}

    def validate(self, plan, sources, w, h):
        return validate_plan(plan, sources, w, h, kerf_cm=.5)


def test_every_gallery_candidate_is_protected_validated_and_warm_seed_unchanged(monkeypatch):
    from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import optimize_order_plan
    from almdina_erp.almdina_erp.domain.cutting import plan_search, final_cut_line_alignment
    # Isolate final protection across five deliberately different valid inputs.
    # The next test exercises the real packing/compaction/alignment pipeline.
    monkeypatch.setattr(plan_search, "compact_regular_final", lambda plan, *a, **k: plan)
    monkeypatch.setattr(final_cut_line_alignment, "align_regular_cut_lines", lambda plan, *a, **k: plan)
    outcome = optimize_order_plan(_command(), engine=_GalleryEngine())
    assert len(outcome.candidate_snapshots) == 5
    assert len(outcome.search_seeds) == 5
    for snapshot, seed in zip(outcome.candidate_snapshots, outcome.search_seeds):
        assert snapshot["validation"]["is_valid"]
        assert snapshot["edge_protection_horizontal_mm"] == 5
        assert snapshot["edge_protection_vertical_mm"] == 10
        assert snapshot["sheets"][0]["pieces"][0]["x"] == .5
        assert seed["sheets"][0]["pieces"][0]["x"] == 0
        assert snapshot["applied_trim_width_cm"] == 0


def test_final_adapter_rejection_rolls_back_to_aligned_geometry(monkeypatch):
    from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import optimize_order_plan
    from almdina_erp.almdina_erp.domain.cutting import plan_search, final_cut_line_alignment
    monkeypatch.setattr(plan_search, "compact_regular_final", lambda plan, *a, **k: plan)
    monkeypatch.setattr(final_cut_line_alignment, "align_regular_cut_lines", lambda plan, *a, **k: plan)
    class RejectProtected(_GalleryEngine):
        def validate(self, plan, sources, w, h):
            return ["adapter-rejected"] if plan["sheets"][0]["pieces"][0]["x"] > 0 else []
    outcome = optimize_order_plan(_command(), engine=RejectProtected())
    assert len(outcome.candidate_snapshots) == 5
    for snapshot in outcome.candidate_snapshots:
        assert snapshot["validation"]["is_valid"]
        assert snapshot["sheets"][0]["pieces"][0]["x"] == 0
        assert all(d["reason"] != "EDGE_PROTECTED" for d in snapshot["edge_positioning"])


def test_native_search_continue_and_snapshot_reload_share_final_policy():
    from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import optimize_order_plan
    from almdina_erp.almdina_erp.application.cutting.plan_preview_session import CuttingPlanPreviewSession
    from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import sanitize_plan_snapshot
    from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import DomainCuttingEngineAdapter
    engine = DomainCuttingEngineAdapter()
    command = _command(alignment_search_budget_sec=.1)
    first = optimize_order_plan(command, engine=engine)
    continued = optimize_order_plan(replace(command, seed_plans=first.search_seeds, search_round=1), engine=engine)
    for outcome in (first, continued):
        assert outcome.snapshot["validation"]["is_valid"]
        assert outcome.required_boards == 1
        for snapshot in outcome.candidate_snapshots:
            margins = physical_edge_margins_mm(snapshot["sheets"][0])
            assert min(margins["left"], margins["right"]) >= 5
            assert min(margins["top"], margins["bottom"]) >= 10
            assert not validate_plan(snapshot, outcome.expanded_pieces, 100, 100, kerf_cm=.5)
    saved = sanitize_plan_snapshot(json.loads(json.dumps(first.snapshot)))
    session = CuttingPlanPreviewSession("preview", "order", "user", "source", "revision", "input", "settings",
                                       {}, saved, "now")
    restored = CuttingPlanPreviewSession.from_cache_value(json.loads(json.dumps(session.as_cache_value())))
    assert restored.snapshot == saved
    assert saved["edge_protection_horizontal_mm"] == 5
    assert any(d["reason"] == "EDGE_PROTECTED" for d in saved["edge_positioning"])


def test_settings_fields_use_existing_section_and_migration_defaults():
    from almdina_erp.almdina_erp.domain.security.authorization import Capability
    from almdina_erp.almdina_erp.domain.security.factory_settings import decide_settings_update
    metadata = json.loads((ROOT/"almdina_erp/doctype/almdina_erp_settings/almdina_erp_settings.json").read_text())
    fields = {f["fieldname"]: f for f in metadata["fields"]}
    for field in EDGE_PROTECTION_FIELDS:
        assert fields[field]["fieldtype"] == "Float"
        assert float(fields[field]["default"]) == 0
        assert fields[field]["non_negative"] == 1
        assert metadata["field_order"].count(field) == 1
        assert decide_settings_update({Capability.EDIT_FACTORY_CUTTING_DEFAULTS}, {field: 5}).allowed
        assert not decide_settings_update({Capability.VIEW_FACTORY_SETTINGS}, {field: 5}).allowed
        assert not decide_settings_update({Capability.EDIT_FACTORY_COST_DEFAULTS}, {field: 5}).allowed


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


def test_native_full_board_still_fits_with_protection_enabled():
    from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import optimize_order_plan
    from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import DomainCuttingEngineAdapter
    command = replace(_command(alignment_search_budget_sec=0), piece_rows=(
        dict(width_cm=100, length_cm=100, qty=1, allow_rotation=False, piece_instance_id="full-board"),))
    outcome = optimize_order_plan(command, engine=DomainCuttingEngineAdapter())
    assert outcome.required_boards == 1
    assert outcome.snapshot["validation"]["is_valid"]
    assert physical_edge_margins_mm(outcome.snapshot["sheets"][0]) == dict.fromkeys(("left", "right", "top", "bottom"), 0)


def test_protected_geometry_survives_persistence_actual_dxf_and_strict_import(tmp_path):
    import os
    import subprocess
    from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import BoardGeometry, optimize_order_plan
    from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import DomainCuttingEngineAdapter
    from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import sanitize_plan_snapshot
    _services()
    from almdina_erp.almdina_erp.services.export_validation_service import _plan_to_export_snapshot
    from almdina_erp.almdina_erp.services.dxf_export_service import _kerf_errors
    from almdina_erp.almdina_erp.services.dxf_autocad_normalization import rebuild_autocad_dxf
    from almdina_erp.tests.test_glass_opening_nesting import _lifecycle_placed_row
    from almdina_erp.tests.test_cutter_center_paths import _import, _order, _piece
    command = _command(alignment_search_budget_sec=0)
    command = replace(command, board=BoardGeometry(100, 100, .5, .5),
        optimizer=replace(command.optimizer, edge_protection=EdgeProtectionPolicy(10, 15)))
    outcome = optimize_order_plan(command, engine=DomainCuttingEngineAdapter())
    saved = sanitize_plan_snapshot(json.loads(json.dumps(outcome.snapshot)))
    assert saved["validation"]["is_valid"]
    cutting_plan = SimpleNamespace(
        snapshot_json=json.dumps(saved), placed_pieces=[_lifecycle_placed_row(p, s["sheet_no"])
            for s in saved["sheets"] for p in s["pieces"]],
        sources=[SimpleNamespace(sheet_no=s["sheet_no"], source_type="Full Board", remnant=None,
            board_item=None, material="", color="", thickness_mm=18, full_width_mm=1000,
            full_length_mm=1000, usable_width_mm=990, usable_length_mm=990, source_area_m2=1)
            for s in saved["sheets"]],
        engine_version=saved["engine_version"], method_key=saved["method_key"], method_label=saved["method_label"],
        full_board_width_mm=1000, full_board_length_mm=1000, usable_board_width_mm=990,
        usable_board_length_mm=990, kerf_mm=5, trim_margin_mm=5, used_area_m2=saved["used_area_m2"],
        total_source_area_m2=1, waste_area_m2=saved["waste_area_m2"], required_boards=1)
    rebuilt = _plan_to_export_snapshot(cutting_plan)
    def coordinates(plan):
        return [(p["x"], p["y"], p["w"], p["h"])
                for s in plan["sheets"] for p in s["pieces"]]
    assert coordinates(rebuilt) == coordinates(saved)
    assert not _kerf_errors(rebuilt)
    cases = tmp_path/"protected.json"
    cases.write_text(json.dumps([rebuilt]))
    subprocess.run(["node", str(ROOT/"tests/js/secure_dxf_topology_export.test.js")], check=True,
        capture_output=True, text=True,
        env=dict(os.environ, PERIMETER_CASES=str(cases), PERIMETER_OUTPUT_DIR=str(tmp_path)))
    path = tmp_path/"0.dxf"
    path.write_bytes(rebuild_autocad_dxf(path.read_bytes()))
    order = _order([_piece(width_cm=75, length_cm=20, cut_width_cm=75, cut_length_cm=20,
                           piece_instance_id="edge-regression")])
    order.board_width_cm = order.board_length_cm = 100
    order.full_board_width_mm = order.full_board_length_mm = 1000
    imported = _import(str(path), order, kerf_mm=5, trim_mm=5)
    for actual, expected in zip(coordinates(imported), coordinates(rebuilt), strict=True):
        assert actual == pytest.approx(expected)
    assert physical_edge_margins_mm(imported["sheets"][0]) == physical_edge_margins_mm(saved["sheets"][0])
