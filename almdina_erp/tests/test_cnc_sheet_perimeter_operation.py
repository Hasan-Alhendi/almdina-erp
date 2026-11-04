"""Independent sheet_perimeter CNC operation for connected perimeter mode."""

from __future__ import annotations

import pytest

from almdina_erp.almdina_erp.application.cnc.nc_export import build_simulation_nc
from almdina_erp.almdina_erp.application.cnc.program import compile_sheet_program
from almdina_erp.almdina_erp.application.cnc.workspace import (
    build_operational_workspace,
    prepare_sheet_settings,
)
from almdina_erp.almdina_erp.domain.cnc.operational_file import (
    ApprovedPlanRef,
    OperationalFileError,
    apply_legacy_cut_path_sequence_to_order,
    assign_sheet_presets,
    catalog_sheet,
    confirmed_perimeter_operation_order,
    derive_legacy_cut_path_sequence,
    normalize_path_piece_instance,
    settings_fingerprint,
    sheet_perimeter_precedes_milling,
    validate_operational_path_rows,
)
from almdina_erp.almdina_erp.domain.cnc.operations import (
    CNC_OPERATION_TYPES,
    CUT_PATH_LAYER,
    DEFAULT_MACHINING_ORDER,
    PRIMARY_OPERATION_BY_LAYER,
    SHEET_PERIMETER_OPERATION_KEY,
    primary_operation_for_layer,
)
from almdina_erp.almdina_erp.domain.cnc.perimeter import (
    CUT_PATH_INTERNAL_SEQUENCE_KEY,
    SHEET_PERIMETER_PATH_KEY,
)
from almdina_erp.almdina_erp.domain.cnc.program import CncSourceEntity, build_board_program


KERF_MM = 5.0
SHEET_W = 1220.0
SHEET_H = 2440.0


def _raw(**overrides):
    values = {
        "preset_name": "Finish",
        "tool_name": "Finish",
        "tool_number": "T9",
        "tool_diameter_mm": 5,
        "final_depth_mm": 18,
        "spindle_speed_rpm": 15000,
        "feed_rate_mm_min": 8000,
        "plunge_rate_mm_min": 1500,
        "pass_depth_mm": 6,
        "enabled": True,
    }
    values.update(overrides)
    return values


PRESETS = {
    "Finish": _raw(),
    "Deep": _raw(preset_name="Deep", final_depth_mm=22, spindle_speed_rpm=12000),
    "OtherTool": _raw(preset_name="OtherTool", tool_number="T2", tool_diameter_mm=6),
}


def _rect(x, y, width, height):
    return [[x, y], [x + width, y], [x + width, y + height], [x, y + height]]


def _piece(instance_id, outer, *, sheet_no=1, label=None, **extras):
    row = {
        "piece_instance_id": instance_id,
        "label": label or instance_id,
        "sheet_no": sheet_no,
        "piece_type": "Regular",
        "extra_liner": 0,
        "liner_reference_side": "Left",
        "liner_offset_cm": 2,
        "liner_width_cm": 1.5,
        "liner_start_cm": 0,
        "liner_length_cm": 10,
        "extra_back_groove": 0,
        "extra_recessed_handle_cutout": 0,
        "geometry": {
            "schema_version": 1,
            "unit": "mm",
            "coordinate_space": "usable_sheet",
            "outer": outer,
            "holes": [],
        },
    }
    row.update(extras)
    return row


def _snapshot():
    return {
        "kerf_mm": KERF_MM,
        "full_board_width_cm": SHEET_W / 10.0,
        "full_board_length_cm": SHEET_H / 10.0,
        "sheets": [
            {
                "sheet_no": 1,
                "full_width_cm": SHEET_W / 10.0,
                "full_length_cm": SHEET_H / 10.0,
                "applied_trim_width_cm": 0,
                "applied_trim_length_cm": 0,
            }
        ],
    }


def _plan():
    return ApprovedPlanRef(
        name="PLAN-1",
        revision=1,
        source_type="System",
        status="Approved",
    )


def _pieces_with_addons():
    return [
        _piece(
            "A",
            _rect(40, 40, 300, 400),
            extra_liner=1,
            extra_back_groove=1,
            extra_recessed_handle_cutout=1,
        ),
        _piece("B", _rect(345, 40, 250, 200)),
    ]


def test_layer_map_keeps_cut_path_primary_when_perimeter_shares_dxf_layer():
    assert CUT_PATH_LAYER == "CUT_PATH"
    cut = next(op for op in CNC_OPERATION_TYPES if op.key == "cut_path")
    peri = next(op for op in CNC_OPERATION_TYPES if op.key == SHEET_PERIMETER_OPERATION_KEY)
    assert cut.dxf_layer == peri.dxf_layer == CUT_PATH_LAYER
    assert PRIMARY_OPERATION_BY_LAYER[CUT_PATH_LAYER] is cut
    assert primary_operation_for_layer(CUT_PATH_LAYER).key == "cut_path"
    assert SHEET_PERIMETER_OPERATION_KEY not in {
        op.key for op in PRIMARY_OPERATION_BY_LAYER.values()
    }


def test_entity_path_key_resolves_perimeter_without_hijacking_cut_path():
    perimeter = CncSourceEntity(
        layer="CUT_PATH",
        points=((0.0, 0.0), (100.0, 0.0), (100.0, 80.0), (0.0, 80.0)),
        closed=True,
        entity_type="LWPOLYLINE",
        role="tool_center",
        ring="outer",
        path_key=SHEET_PERIMETER_PATH_KEY,
    )
    internal = CncSourceEntity(
        layer="CUT_PATH",
        points=((40.0, 0.0), (40.0, 80.0)),
        closed=False,
        entity_type="LINE",
        role="tool_center",
        ring="open",
        path_key="",
    )
    program = build_board_program(
        sheet_no=1,
        entities=[perimeter, internal],
        operation_order=["sheet_perimeter", "cut_path"],
        operation_presets={"cut_path": "Finish", "sheet_perimeter": "Finish"},
        path_overrides={},
        known_presets=PRESETS,
        units="mm",
        frame_origin_mm=(0.0, 0.0),
        sheet_width_mm=SHEET_W,
        sheet_length_mm=SHEET_H,
        approved_kerf_mm=KERF_MM,
    )
    keys = [op.operation_key for op in program.operations]
    assert keys == ["sheet_perimeter", "cut_path"]
    peri_paths = program.operations[0].toolpaths
    cut_paths = program.operations[1].toolpaths
    assert len(peri_paths) == 1
    assert peri_paths[0].path_key == SHEET_PERIMETER_PATH_KEY
    assert all(path.path_key != SHEET_PERIMETER_PATH_KEY for path in cut_paths)
    assert cut_paths


def test_separate_mode_keeps_four_operations_with_addons():
    pieces = _pieces_with_addons()
    catalog = catalog_sheet(1, pieces, include_sheet_perimeter=False)
    assert catalog.operations == (
        "liner",
        "recessed_handle_cutout",
        "back_groove",
        "cut_path",
    )
    assert all(path.operation_key != SHEET_PERIMETER_OPERATION_KEY for path in catalog.paths)


def test_connected_mode_exposes_five_operations_and_default_order():
    pieces = _pieces_with_addons()
    catalog = catalog_sheet(1, pieces, include_sheet_perimeter=True)
    assert catalog.operations == (
        "liner",
        "recessed_handle_cutout",
        "back_groove",
        "sheet_perimeter",
        "cut_path",
    )
    assert DEFAULT_MACHINING_ORDER[:5] == catalog.operations
    peri = next(path for path in catalog.paths if path.path_key == SHEET_PERIMETER_PATH_KEY)
    assert peri.operation_key == SHEET_PERIMETER_OPERATION_KEY
    assert peri.dxf_layer == CUT_PATH_LAYER


def test_perimeter_inherits_cut_path_preset_and_can_override():
    pieces = [_piece("A", _rect(40, 40, 300, 400))]
    catalog = catalog_sheet(1, pieces, include_sheet_perimeter=True)
    inherited = assign_sheet_presets(
        catalog=catalog,
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        known_presets=PRESETS,
        operation_sources={"cut_path": "sheet", "sheet_perimeter": "factory"},
        factory_defaults={"cut_path": "Finish"},
    )
    assert inherited.effective_operations["sheet_perimeter"] == "Finish"
    assert inherited.sources["sheet_perimeter"] == "Factory"
    assert inherited.stored_operations["sheet_perimeter"] == ""

    customized = assign_sheet_presets(
        catalog=catalog,
        operation_presets={"cut_path": "Finish", "sheet_perimeter": "Deep"},
        path_overrides={},
        known_presets=PRESETS,
        operation_sources={"cut_path": "sheet", "sheet_perimeter": "sheet"},
        factory_defaults={"cut_path": "Finish"},
    )
    assert customized.effective_operations["sheet_perimeter"] == "Deep"
    assert customized.stored_operations["sheet_perimeter"] == "Deep"

    restored = assign_sheet_presets(
        catalog=catalog,
        operation_presets={"cut_path": "Finish", "sheet_perimeter": ""},
        path_overrides={},
        known_presets=PRESETS,
        operation_sources={"cut_path": "sheet", "sheet_perimeter": "factory"},
        factory_defaults={"cut_path": "Finish"},
    )
    assert restored.effective_operations["sheet_perimeter"] == "Finish"


def test_tool_number_conflict_rejected_for_perimeter_override():
    pieces = [_piece("A", _rect(40, 40, 300, 400))]
    catalog = catalog_sheet(1, pieces, include_sheet_perimeter=True)
    with pytest.raises(OperationalFileError) as exc:
        assign_sheet_presets(
            catalog=catalog,
            operation_presets={"cut_path": "Finish", "sheet_perimeter": "OtherTool"},
            path_overrides={},
            known_presets=PRESETS,
            operation_sources={"cut_path": "sheet", "sheet_perimeter": "sheet"},
            factory_defaults={"cut_path": "Finish"},
        )
    assert exc.value.code in {"tool_identity_conflict", "tool_diameter_conflict"}


def test_perimeter_before_cut_path_is_accepted_without_error():
    order = ("liner", "recessed_handle_cutout", "back_groove", "sheet_perimeter", "cut_path")
    assert not sheet_perimeter_precedes_milling(order)
    confirmed, early = confirmed_perimeter_operation_order(order, perimeter_early_confirmed=False)
    assert confirmed == order
    assert early is False


def test_perimeter_before_milling_requires_confirmation():
    order = ("sheet_perimeter", "liner", "cut_path")
    assert sheet_perimeter_precedes_milling(order)
    with pytest.raises(OperationalFileError) as exc:
        confirmed_perimeter_operation_order(order, perimeter_early_confirmed=False)
    assert exc.value.code == "perimeter_cut_early_unconfirmed"
    confirmed, early = confirmed_perimeter_operation_order(order, perimeter_early_confirmed=True)
    assert confirmed == order
    assert early is True


def test_legacy_sequence_maps_into_operation_order():
    base = ("liner", "sheet_perimeter", "cut_path")
    early = apply_legacy_cut_path_sequence_to_order(
        base,
        [SHEET_PERIMETER_PATH_KEY, CUT_PATH_INTERNAL_SEQUENCE_KEY],
        join_mode="connected",
    )
    assert early.index("sheet_perimeter") < early.index("cut_path")
    late = apply_legacy_cut_path_sequence_to_order(
        base,
        [CUT_PATH_INTERNAL_SEQUENCE_KEY, SHEET_PERIMETER_PATH_KEY],
        join_mode="connected",
    )
    assert late.index("cut_path") < late.index("sheet_perimeter")
    assert derive_legacy_cut_path_sequence(early)[0] == SHEET_PERIMETER_PATH_KEY
    assert derive_legacy_cut_path_sequence(late)[0] == CUT_PATH_INTERNAL_SEQUENCE_KEY


def test_compile_default_order_places_perimeter_before_cut_between_pieces():
    pieces = _pieces_with_addons()
    program = compile_sheet_program(
        sheet_no=1,
        pieces=pieces,
        snapshot=_snapshot(),
        operation_presets={
            "cut_path": "Finish",
            "liner": "Finish",
            "back_groove": "Finish",
            "recessed_handle_cutout": "Finish",
        },
        path_overrides={},
        operation_order=[
            "liner",
            "recessed_handle_cutout",
            "back_groove",
            "sheet_perimeter",
            "cut_path",
        ],
        known_presets=PRESETS,
        perimeter_join_mode="connected",
    )
    keys = [op["operation_key"] for op in program["operations"]]
    assert keys.index("sheet_perimeter") < keys.index("cut_path")
    peri = next(op for op in program["operations"] if op["operation_key"] == "sheet_perimeter")
    assert len(peri["toolpaths"]) == 1
    assert peri["toolpaths"][0]["path_key"] == SHEET_PERIMETER_PATH_KEY
    cut = next(op for op in program["operations"] if op["operation_key"] == "cut_path")
    assert all(path["path_key"] != SHEET_PERIMETER_PATH_KEY for path in cut["toolpaths"])


def test_moving_perimeter_to_end_changes_simulation_order_and_fingerprint():
    pieces = [_piece("A", _rect(40, 40, 300, 400)), _piece("B", _rect(345, 40, 250, 200))]
    early_order = ["sheet_perimeter", "cut_path"]
    late_order = ["cut_path", "sheet_perimeter"]
    early = compile_sheet_program(
        sheet_no=1,
        pieces=pieces,
        snapshot=_snapshot(),
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        operation_order=early_order,
        known_presets=PRESETS,
        perimeter_join_mode="connected",
    )
    late = compile_sheet_program(
        sheet_no=1,
        pieces=pieces,
        snapshot=_snapshot(),
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        operation_order=late_order,
        known_presets=PRESETS,
        perimeter_join_mode="connected",
    )
    assert [op["operation_key"] for op in early["operations"]] == early_order
    assert [op["operation_key"] for op in late["operations"]] == late_order
    fp_early = settings_fingerprint(
        operation_presets={"cut_path": "Finish", "sheet_perimeter": "Finish"},
        path_overrides={},
        presets=PRESETS,
        operation_order=early_order,
        perimeter_join_mode="connected",
    )
    fp_late = settings_fingerprint(
        operation_presets={"cut_path": "Finish", "sheet_perimeter": "Finish"},
        path_overrides={},
        presets=PRESETS,
        operation_order=late_order,
        perimeter_join_mode="connected",
    )
    assert fp_early != fp_late
    package = build_simulation_nc(
        early,
        machine_profile={"production_approved": False, "retract_z_mm": 20, "dialect": "fanuc"},
        sheet_no=1,
        settings_fingerprint=fp_early,
    )
    assert package["production"] is False


def test_prepare_and_workspace_persist_independent_operation():
    pieces = _pieces_with_addons()
    prepared = prepare_sheet_settings(
        order_name="DCO-1",
        approved_plan=_plan(),
        plan_is_current=True,
        pieces=pieces,
        sheet_no=1,
        existing=None,
        operation_presets={"cut_path": "Finish", "liner": "Finish"},
        path_overrides={},
        known_presets=PRESETS,
        machine_profile={"fingerprint_payload": {}, "production_approved": False},
        operation_order=[
            "liner",
            "recessed_handle_cutout",
            "back_groove",
            "sheet_perimeter",
            "cut_path",
        ],
        cut_path_early_confirmed=False,
        perimeter_join_mode="connected",
        perimeter_cut_early_confirmed=False,
        factory_defaults={"cut_path": "Finish", "liner": "Finish"},
        operation_sources={
            "cut_path": "sheet",
            "liner": "sheet",
            "sheet_perimeter": "factory",
            "back_groove": "factory",
            "recessed_handle_cutout": "factory",
        },
    )
    assert [row["operation_key"] for row in prepared["operations"]] == [
        "liner",
        "recessed_handle_cutout",
        "back_groove",
        "sheet_perimeter",
        "cut_path",
    ]
    workspace = build_operational_workspace(
        order_name="DCO-1",
        approved_plan=_plan(),
        plan_is_current=True,
        pieces=pieces,
        saved_files=[
            {
                "name": "CNC-OF-1",
                "cutting_plan": "PLAN-1",
                "plan_revision": 1,
                "sheet_no": 1,
                "perimeter_join_mode": "connected",
                "cut_path_sequence": [
                    SHEET_PERIMETER_PATH_KEY,
                    CUT_PATH_INTERNAL_SEQUENCE_KEY,
                ],
                "operations": prepared["operations"],
                "paths": prepared["paths"],
                "generation_fingerprint": "",
                "generated_file": "",
                "cut_path_early_confirmed": 0,
                "perimeter_cut_early_confirmed": 0,
            }
        ],
        factory_defaults={"cut_path": "Finish", "liner": "Finish"},
        known_presets=PRESETS,
        machine_profile={
            "production_approved": False,
            "source_note": "",
            "fingerprint_payload": {},
        },
        can_prepare=True,
    )
    sheet = workspace["sheets"][0]
    assert any(row["operation_key"] == "sheet_perimeter" for row in sheet["operations"])
    assert sheet["perimeter_join_mode"] == "connected"


def test_legacy_saved_without_sheet_perimeter_row_is_coerced():
    pieces = [_piece("A", _rect(40, 40, 300, 400))]
    prepared = prepare_sheet_settings(
        order_name="DCO-1",
        approved_plan=_plan(),
        plan_is_current=True,
        pieces=pieces,
        sheet_no=1,
        existing={
            "perimeter_join_mode": "connected",
            "cut_path_sequence": [
                CUT_PATH_INTERNAL_SEQUENCE_KEY,
                SHEET_PERIMETER_PATH_KEY,
            ],
            "operations": [
                {
                    "operation_key": "cut_path",
                    "dxf_layer": "CUT_PATH",
                    "sequence": 1,
                    "tool_preset": "Finish",
                    "preset_source": "Sheet",
                }
            ],
            "paths": [],
            "cut_path_early_confirmed": 0,
            "perimeter_cut_early_confirmed": 0,
            "generation_fingerprint": "",
            "generated_file": "",
        },
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        known_presets=PRESETS,
        machine_profile={"fingerprint_payload": {}, "production_approved": False},
        operation_order=None,
        factory_defaults={"cut_path": "Finish"},
    )
    keys = [row["operation_key"] for row in prepared["operations"]]
    assert keys == ["cut_path", "sheet_perimeter"]
    assert prepared["cut_path_sequence"][0] == CUT_PATH_INTERNAL_SEQUENCE_KEY


def test_sheet_perimeter_piece_id_must_stay_empty_and_piece_paths_keep_ids():
    assert (
        normalize_path_piece_instance(
            path_key=SHEET_PERIMETER_PATH_KEY,
            operation_key="sheet_perimeter",
            piece_instance_id="",
        )
        == ""
    )
    with pytest.raises(OperationalFileError) as forbidden:
        normalize_path_piece_instance(
            path_key=SHEET_PERIMETER_PATH_KEY,
            operation_key="sheet_perimeter",
            piece_instance_id="piece-a",
        )
    assert forbidden.value.code == "sheet_perimeter_piece_forbidden"
    assert (
        normalize_path_piece_instance(
            path_key="cut_path:piece-a:outer",
            operation_key="cut_path",
            piece_instance_id="piece-a",
        )
        == "piece-a"
    )
    with pytest.raises(OperationalFileError) as missing:
        normalize_path_piece_instance(
            path_key="cut_path:piece-a:outer",
            operation_key="cut_path",
            piece_instance_id="",
        )
    assert missing.value.code == "missing_piece_instance_id"
    # Shared anonymous centers may omit a piece id.
    assert (
        normalize_path_piece_instance(
            path_key="cut_path:center:abcd",
            operation_key="cut_path",
            piece_instance_id="",
        )
        == ""
    )
    rows = validate_operational_path_rows(
        [
            {
                "path_key": SHEET_PERIMETER_PATH_KEY,
                "operation_key": "sheet_perimeter",
                "piece_instance_id": "",
                "dxf_layer": "CUT_PATH",
                "sequence": 1,
            },
            {
                "path_key": "cut_path:piece-a:outer",
                "operation_key": "cut_path",
                "piece_instance_id": "piece-a",
                "dxf_layer": "CUT_PATH",
                "sequence": 2,
            },
        ]
    )
    assert rows[0]["piece_instance_id"] == ""
    assert rows[1]["piece_instance_id"] == "piece-a"
    with pytest.raises(OperationalFileError) as duplicate:
        validate_operational_path_rows(
            [
                {
                    "path_key": SHEET_PERIMETER_PATH_KEY,
                    "operation_key": "sheet_perimeter",
                    "piece_instance_id": "",
                },
                {
                    "path_key": SHEET_PERIMETER_PATH_KEY,
                    "operation_key": "sheet_perimeter",
                    "piece_instance_id": "",
                },
            ]
        )
    assert duplicate.value.code == "sheet_perimeter_duplicate"


def test_prepare_connected_keeps_empty_perimeter_piece_and_piece_ids():
    pieces = [_piece("A", _rect(40, 40, 300, 400)), _piece("B", _rect(345, 40, 250, 200))]
    prepared = prepare_sheet_settings(
        order_name="DCO-1",
        approved_plan=_plan(),
        plan_is_current=True,
        pieces=pieces,
        sheet_no=1,
        existing=None,
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        known_presets=PRESETS,
        machine_profile={"fingerprint_payload": {}, "production_approved": False},
        operation_order=["sheet_perimeter", "cut_path"],
        perimeter_join_mode="connected",
        factory_defaults={"cut_path": "Finish"},
    )
    peri = next(row for row in prepared["paths"] if row["path_key"] == SHEET_PERIMETER_PATH_KEY)
    assert peri["operation_key"] == "sheet_perimeter"
    assert peri["piece_instance_id"] == ""
    piece_rows = [row for row in prepared["paths"] if row["path_key"] != SHEET_PERIMETER_PATH_KEY]
    assert piece_rows
    assert all(str(row["piece_instance_id"] or "").strip() for row in piece_rows)
    assert sum(1 for row in prepared["paths"] if row["path_key"] == SHEET_PERIMETER_PATH_KEY) == 1


def test_other_sheet_unaffected_by_connected_mode_on_sheet_one():
    pieces = [
        _piece("A", _rect(40, 40, 300, 400), sheet_no=1),
        _piece("B", _rect(40, 40, 300, 400), sheet_no=2),
    ]
    workspace = build_operational_workspace(
        order_name="DCO-1",
        approved_plan=_plan(),
        plan_is_current=True,
        pieces=pieces,
        saved_files=[
            {
                "name": "CNC-OF-1",
                "cutting_plan": "PLAN-1",
                "plan_revision": 1,
                "sheet_no": 1,
                "perimeter_join_mode": "connected",
                "operations": [
                    {
                        "operation_key": "sheet_perimeter",
                        "dxf_layer": "CUT_PATH",
                        "sequence": 1,
                        "tool_preset": "",
                        "preset_source": "Factory",
                    },
                    {
                        "operation_key": "cut_path",
                        "dxf_layer": "CUT_PATH",
                        "sequence": 2,
                        "tool_preset": "Finish",
                        "preset_source": "Sheet",
                    },
                ],
                "paths": [],
                "generation_fingerprint": "",
                "generated_file": "",
            }
        ],
        factory_defaults={"cut_path": "Finish"},
        known_presets=PRESETS,
        machine_profile={
            "production_approved": False,
            "source_note": "",
            "fingerprint_payload": {},
        },
        can_prepare=True,
    )
    by_sheet = {sheet["sheet_no"]: sheet for sheet in workspace["sheets"]}
    assert any(
        row["operation_key"] == "sheet_perimeter" for row in by_sheet[1]["operations"]
    )
    assert all(
        row["operation_key"] != "sheet_perimeter" for row in by_sheet[2]["operations"]
    )
    assert by_sheet[2]["perimeter_join_mode"] == "separate"
