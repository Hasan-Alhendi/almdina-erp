"""Board-editor Phase 1 data-contract and projection tests."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

ezdxf = pytest.importorskip("ezdxf")

from almdina_erp.almdina_erp.application.cutting.board_editor_projection import (
    AFFILIATION_BOUND,
    AFFILIATION_REFERENCE,
    AFFILIATION_UNRESOLVED,
    ELEMENT_KIND_FINISHED_OUTLINE,
    ELEMENT_KIND_OVERLAY,
    ELEMENT_KIND_REFERENCE,
    ELEMENT_KIND_TEXT,
    project_board_editor,
)
from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import (
    is_financial_plan_key,
    sanitize_plan_snapshot,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    serialize_geometry_mm,
    serialize_overlay_geometry_mm,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_layer_catalog import (
    CUT_PATH_LAYER,
    GEOMETRY_LAYER,
    LINER_LAYER,
    OFFCUT_LAYER,
    TEXT_LAYER_EXPORT_NAME,
    build_layer_registry,
    layer_match_key,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_topology import PartGeometry
from almdina_erp.almdina_erp.infrastructure.cutting.dxf_reader import read_dxf_geometry
from almdina_erp.almdina_erp.services import dxf_import_service


def _nested_keys(value):
    keys = set()
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(key)
            keys |= _nested_keys(item)
    elif isinstance(value, list):
        for item in value:
            keys |= _nested_keys(item)
    return keys


def _geometry(outer, holes=()):
    return serialize_geometry_mm(
        PartGeometry(
            outer=tuple(tuple(point) for point in outer),
            holes=tuple(tuple(tuple(point) for point in hole) for hole in holes),
        )
    )


def _system_snapshot():
    return {
        "physical_execution_contract": 1,
        "saw_center_status": "Absent",
        "full_board_width_cm": 122,
        "full_board_length_cm": 244,
        "usable_board_width_cm": 121,
        "usable_board_length_cm": 243,
        "kerf_cm": 0.5,
        "trim_cm": 0.5,
        "approved_cost": {"total_cost_usd": 99.0},
        "sheets": [
            {
                "sheet_no": 1,
                "resource_kind": "FULL_BOARD",
                "w": 122,
                "h": 244,
                "full_width_cm": 122,
                "full_length_cm": 244,
                "pieces": [
                    {
                        "id": 1,
                        "label": "1.1",
                        "source_piece_no": 1,
                        "copy_no": 1,
                        "piece_instance_id": "pi-1",
                        "piece_type": "Glass",
                        "x": 1,
                        "y": 1,
                        "w": 60,
                        "h": 80,
                        "rotated": False,
                        "edge_rate_usd": 1.25,
                        "geometry": _geometry(
                            ((10, 10), (610, 10), (610, 810), (10, 810)),
                            (((110, 110), (510, 110), (510, 710), (110, 710)),),
                        ),
                        "overlays": [
                            {
                                "kind": "liner",
                                "layer": "Liner",
                                "geometry": serialize_overlay_geometry_mm(
                                    ((20, 20), (200, 20)),
                                    closed=False,
                                ),
                            }
                        ],
                        "glass_hole_local_mm": [
                            [100, 100],
                            [500, 100],
                            [500, 700],
                            [100, 700],
                        ],
                    },
                    {
                        "id": 2,
                        "label": "2.1",
                        "source_piece_no": 2,
                        "copy_no": 1,
                        "piece_instance_id": "pi-2",
                        "piece_type": "Regular",
                        "x": 15,
                        "y": 20,
                        "w": 30,
                        "h": 40,
                        "rotated": False,
                        "glass_host_piece_id": 1,
                        "geometry": _geometry(
                            ((150, 200), (450, 200), (450, 600), (150, 600)),
                        ),
                    },
                ],
                "text_labels": [
                    {
                        "text": "1.1",
                        "x_mm": 20,
                        "y_mm": 30,
                        "height_mm": 12,
                        "rotation_deg": 0,
                        "layer": "text",
                    }
                ],
            }
        ],
    }


def test_layer_match_key_preserves_original_spelling_separately():
    registry = build_layer_registry(
        layer_table=[
            {
                "original_name": " Geometry ",
                "aci_color": 4,
                "linetype": "DASHED",
                "is_empty": False,
            },
            {
                "original_name": "along",
                "aci_color": 7,
                "linetype": "CONTINUOUS",
                "is_empty": True,
            },
        ]
    )
    by_key = {row["match_key"]: row for row in registry}

    assert layer_match_key(" Geometry ") == "GEOMETRY"
    assert by_key["GEOMETRY"]["original_name"] == "Geometry"
    assert by_key["GEOMETRY"]["match_key"] == "GEOMETRY"
    assert by_key["ALONG"]["original_name"] == "along"
    assert by_key["ALONG"]["is_defined_empty"] is True
    assert by_key[CUT_PATH_LAYER]["is_canonical"] is True


def test_projection_binds_multi_layer_elements_to_one_door_without_guessing():
    projection = project_board_editor(_system_snapshot(), source_kind="system")

    bound = [
        element
        for element in projection["elements"]
        if element["piece_id"] == 1 and element["affiliation_status"] == AFFILIATION_BOUND
    ]
    layers = {element["layer_original_name"] for element in bound}
    kinds = {element["kind"] for element in bound}

    assert GEOMETRY_LAYER in layers
    assert LINER_LAYER in layers
    assert ELEMENT_KIND_FINISHED_OUTLINE in kinds
    assert ELEMENT_KIND_OVERLAY in kinds
    assert projection["support_limits"]["cut_path_entities_projected"] is False
    cut_path = next(
        layer for layer in projection["layers"] if layer["match_key"] == CUT_PATH_LAYER
    )
    assert cut_path["is_defined_empty"] is True


def test_empty_extra_layer_and_canonical_empty_cut_path_are_listed():
    projection = project_board_editor(
        _system_snapshot(),
        layer_table=[
            {
                "original_name": "along",
                "aci_color": 7,
                "linetype": "CONTINUOUS",
                "is_empty": True,
            }
        ],
    )
    by_key = {row["match_key"]: row for row in projection["layers"]}

    assert by_key["ALONG"]["original_name"] == "along"
    assert by_key["ALONG"]["is_defined_empty"] is True
    assert by_key[CUT_PATH_LAYER]["is_defined_empty"] is True
    assert by_key[GEOMETRY_LAYER]["is_defined_empty"] is False


def test_reference_entity_on_geometry_is_not_bound_by_layer_name():
    projection = project_board_editor(
        _system_snapshot(),
        reference_entities=[
            {
                "entity_id": 99,
                "entity_type": "LINE",
                "layer": GEOMETRY_LAYER,
                "kind": ELEMENT_KIND_REFERENCE,
                "reason": "ambiguous_contour",
                "color_source": "BYENTITY",
                "linetype_source": "BYLAYER",
            }
        ],
    )
    refs = [
        element
        for element in projection["elements"]
        if element["kind"] == ELEMENT_KIND_REFERENCE
    ]

    assert len(refs) == 1
    assert refs[0]["affiliation_status"] == AFFILIATION_REFERENCE
    assert refs[0]["piece_id"] is None
    assert refs[0]["layer_match_key"] == GEOMETRY_LAYER


def test_piece_identity_and_glass_hosting_tree():
    projection = project_board_editor(_system_snapshot())
    sheet = projection["sheets"][0]
    hosting = sheet["hosting"]

    by_id = {piece["piece_id"]: piece for piece in sheet["pieces"]}
    assert by_id[1]["piece_instance_id"] == "pi-1"
    assert by_id[2]["glass_host_piece_id"] == 1
    assert hosting["roots"][0]["piece_id"] == 1
    assert hosting["roots"][0]["guests"][0]["piece_id"] == 2
    assert hosting["unresolved_host_links"] == []


def test_historical_snapshot_is_consumed_without_mutation_or_id_invention():
    historical = {
        "sheets": [
            {
                "sheet_no": 1,
                "pieces": [
                    {
                        "id": 7,
                        "label": "3.2",
                        "x": 0,
                        "y": 0,
                        "w": 10,
                        "h": 20,
                        "geometry": _geometry(((0, 0), (100, 0), (100, 200), (0, 200))),
                    }
                ],
            }
        ]
    }
    before = copy.deepcopy(historical)

    projection = project_board_editor(historical)

    assert historical == before
    piece = projection["pieces"][0]
    assert piece["piece_id"] == 7
    assert piece["piece_instance_id"] is None
    assert projection["legacy_physical_execution"] is True


def test_projection_strips_financial_fields():
    projection = project_board_editor(_system_snapshot())
    keys = _nested_keys(projection)

    assert "approved_cost" not in keys
    assert "edge_rate_usd" not in keys
    assert not [key for key in keys if is_financial_plan_key(key)]
    assert projection["view_settings"]["layer_visibility"] == {}
    assert projection["persistence"]["stores_view_settings_in_snapshot"] is False


def test_text_label_stays_unbound_and_preserves_match_key():
    projection = project_board_editor(_system_snapshot())
    texts = [
        element
        for element in projection["elements"]
        if element["kind"] == ELEMENT_KIND_TEXT
    ]

    assert len(texts) == 1
    assert texts[0]["affiliation_status"] == AFFILIATION_UNRESOLVED
    assert texts[0]["piece_id"] is None
    assert texts[0]["layer_match_key"] == TEXT_LAYER_EXPORT_NAME


def test_offcut_keeps_classification_meaning():
    snapshot = {
        "physical_execution_contract": 1,
        "sheets": [
            {
                "sheet_no": 1,
                "resource_kind": "OFFCUT",
                "pieces": [
                    {
                        "id": 3,
                        "label": "9.1",
                        "piece_instance_id": "pi-off",
                        "x": 0,
                        "y": 0,
                        "w": 40,
                        "h": 50,
                        "geometry": _geometry(((0, 0), (400, 0), (400, 500), (0, 500))),
                    }
                ],
            }
        ],
    }
    projection = project_board_editor(snapshot)
    offcut_elements = [
        element
        for element in projection["elements"]
        if element["layer_original_name"] == OFFCUT_LAYER
    ]

    assert projection["sheets"][0]["resource_kind"] == "OFFCUT"
    assert offcut_elements
    assert "deficient-board classification" in offcut_elements[0]["payload"]["note"]


def test_reader_exposes_empty_layer_table_and_color_sources(tmp_path: Path):
    document = ezdxf.new("R2010")
    document.layers.add(name="along", color=7)
    document.layers.add(name="GEOMETRY", color=4)
    document.layers.add(name="CUT_PATH", color=1)
    modelspace = document.modelspace()
    modelspace.add_line(
        (0, 0),
        (10, 0),
        dxfattribs={"layer": "GEOMETRY", "color": 5, "linetype": "DASHED"},
    )
    path = tmp_path / "layers.dxf"
    document.saveas(path)

    result = read_dxf_geometry(
        str(path),
        relevant_layers={"GEOMETRY", "CUT_PATH"},
    )
    by_key = {row["match_key"]: row for row in result["layer_defs"]}

    assert by_key["ALONG"]["original_name"] == "along"
    assert by_key["ALONG"]["is_empty"] is True
    assert by_key["GEOMETRY"]["is_empty"] is False
    assert by_key["CUT_PATH"]["is_empty"] is True
    assert result["segments"]
    assert result["segments"][0]["color_source"] == "BYENTITY"
    assert result["segments"][0]["aci_color"] == 5
    assert result["segments"][0]["linetype_source"] == "BYENTITY"
    assert result["segments"][0]["linetype"] == "DASHED"


def test_import_path_still_ignores_new_reader_fields(tmp_path: Path, monkeypatch):
    """Additive reader fields must not change production import wiring."""

    document = ezdxf.new("R2010")
    for name in ("SHEET_OUTLINE", "GEOMETRY", "CUT_PATH", "TEXT"):
        document.layers.add(name)
    modelspace = document.modelspace()
    modelspace.add_lwpolyline(
        [(0, 0), (1220, 0), (1220, 2440), (0, 2440)],
        close=True,
        dxfattribs={"layer": "SHEET_OUTLINE"},
    )
    path = tmp_path / "import-smoke.dxf"
    document.saveas(path)

    segments, diagnostics, annotations = dxf_import_service._read_normalized_geometry(
        str(path)
    )

    assert isinstance(segments, list)
    assert "detected_layers" in diagnostics
    assert isinstance(annotations, list)
    # Import continues to unpack only the historical triple; layer_defs stay unused.
    assert "layer_defs" not in diagnostics


def test_sanitize_then_project_keeps_operational_sanitizer_contract():
    source = _system_snapshot()
    sanitized = sanitize_plan_snapshot(source)
    projection = project_board_editor(sanitized)

    assert "approved_cost" in source
    assert "approved_cost" not in sanitized
    assert "approved_cost" not in _nested_keys(projection)


def test_l_shaped_break_door_uses_parametric_outline_not_rectangle():
    snapshot = {
        "physical_execution_contract": 1,
        "sheets": [
            {
                "sheet_no": 1,
                "resource_kind": "FULL_BOARD",
                "pieces": [
                    {
                        "id": 11,
                        "label": "4.1",
                        "source_piece_no": 4,
                        "copy_no": 1,
                        "piece_instance_id": "pi-l-break",
                        "piece_type": "L-Shaped Corner",
                        "x": 5,
                        "y": 8,
                        "w": 40,
                        "h": 60,
                        "rotated": False,
                        "clipped_corner_position": "Top Right",
                        "clipped_corner_width_cm": 12,
                        "clipped_corner_length_cm": 18,
                        "extra_liner": 1,
                        "liner_reference_side": "edge_long_left",
                        "liner_offset_cm": 2,
                        "liner_width_cm": 3,
                        "liner_start_cm": 0,
                        "liner_length_cm": 40,
                        "edge_long_left": 1,
                        "edge_width_top": 1,
                    }
                ],
            }
        ],
    }

    projection = project_board_editor(snapshot, source_kind="system")
    piece = projection["pieces"][0]
    outlines = [
        element
        for element in projection["elements"]
        if element["kind"] == ELEMENT_KIND_FINISHED_OUTLINE
        and element["piece_instance_id"] == "pi-l-break"
        and element["layer_original_name"] == GEOMETRY_LAYER
    ]
    overlays = [
        element
        for element in projection["elements"]
        if element["kind"] == ELEMENT_KIND_OVERLAY
        and element["piece_instance_id"] == "pi-l-break"
    ]

    assert piece["piece_type"] == "L-Shaped Corner"
    assert piece["fill_role"] == "l_shaped"
    assert piece["geometry_source"] == "placed_parametric_polygon"
    assert len(outlines) == 1
    outer = outlines[0]["geometry"]["outer"]
    assert len(outer) >= 6
    # Top-right L notch: not an axis-aligned rectangle of four corners.
    assert len(outer) != 4
    assert outlines[0]["payload"]["geometry_source"] == "placed_parametric_polygon"
    assert overlays
    assert overlays[0]["payload"]["kind"] == "liner"
    assert overlays[0]["payload"]["synthetic"] is True
    assert overlays[0]["layer_original_name"] == LINER_LAYER
    path = overlays[0]["geometry"]["path"]
    assert len(path) >= 2
    # Machining parameters stay on the piece identity even if a client hides the layer.
    assert piece["extra_liner"] == 1
    assert piece["liner_reference_side"] == "edge_long_left"
    assert float(piece["liner_width_cm"]) == 3


def test_persisted_dxf_liner_is_not_replaced_by_synthetic_overlay():
    snapshot = _system_snapshot()
    projection = project_board_editor(snapshot, source_kind="system")
    overlays = [
        element
        for element in projection["elements"]
        if element["kind"] == ELEMENT_KIND_OVERLAY and element["piece_id"] == 1
    ]
    assert len(overlays) == 1
    assert overlays[0]["payload"].get("synthetic") is not True


def test_clipped_corner_and_offcut_fill_roles():
    snapshot = {
        "physical_execution_contract": 1,
        "sheets": [
            {
                "sheet_no": 1,
                "resource_kind": "OFFCUT",
                "pieces": [
                    {
                        "id": 21,
                        "label": "5.1",
                        "piece_instance_id": "pi-clip",
                        "piece_type": "Clipped Corner",
                        "resource_kind": "OFFCUT",
                        "x": 1,
                        "y": 2,
                        "w": 30,
                        "h": 40,
                        "clipped_corner_position": "Bottom Left",
                        "clipped_corner_width_cm": 8,
                        "clipped_corner_length_cm": 10,
                        "edge_long_left": 1,
                        "edge_break": 1,
                        "edge_long_left_type_override": "Blue",
                        "corner_mirrored": 1,
                        "corner_rotation_quarter_turns": 1,
                    }
                ],
            }
        ],
    }
    projection = project_board_editor(snapshot)
    piece = projection["pieces"][0]
    outline = next(
        element
        for element in projection["elements"]
        if element["kind"] == ELEMENT_KIND_FINISHED_OUTLINE
        and element["layer_original_name"] == GEOMETRY_LAYER
    )
    assert piece["fill_role"] == "offcut"
    assert len(outline["geometry"]["outer"]) >= 5
    assert piece["display_edges"]["edge_long_left"] is True
    assert piece["display_edges"]["edge_break"] is True
    assert piece["display_edges"]["edge_long_left_type_override"] == "Blue"
    assert piece["corner_mirrored"] == 1
    assert piece["corner_rotation_quarter_turns"] == 1
    assert outline["payload"]["display_edges"]["edge_break"] is True
    assert projection["edge_display"]["default_edge_type"] == ""
    classified = project_board_editor(snapshot, default_edge_type="PVC Default")
    assert classified["edge_display"]["default_edge_type"] == "PVC Default"
    assert classified["pieces"][0]["display_edges"]["edge_long_left_type_override"] == "Blue"


def test_special_cnc_raw_gets_finished_outline_not_unresolved():
    snapshot = {
        "physical_execution_contract": 1,
        "sheets": [
            {
                "sheet_no": 1,
                "resource_kind": "FULL_BOARD",
                "w": 122,
                "h": 244,
                "pieces": [
                    {
                        "id": 101,
                        "label": "S22",
                        "piece_instance_id": "pi-raw-22",
                        "piece_type": "Special",
                        "x": 10,
                        "y": 20,
                        "w": 22,
                        "h": 22,
                        "original_w": 22,
                        "original_h": 22,
                        "allow_rotation": 0,
                    },
                    {
                        "id": 102,
                        "label": "S21",
                        "piece_instance_id": "pi-raw-21",
                        "piece_type": "Special",
                        "x": 80,
                        "y": 180,
                        "w": 22,
                        "h": 21,
                        "original_w": 22,
                        "original_h": 21,
                        "allow_rotation": 0,
                    },
                    {
                        "id": 103,
                        "label": "S-miss",
                        "piece_instance_id": "pi-special-miss",
                        "piece_type": "Special",
                        "x": 0,
                        "y": 0,
                        "w": 0,
                        "h": 0,
                    },
                ],
            }
        ],
    }
    projection = project_board_editor(snapshot)
    by_instance = {row["piece_instance_id"]: row for row in projection["pieces"]}
    assert by_instance["pi-raw-22"]["geometry_source"] == "cnc_raw_rect"
    assert by_instance["pi-raw-22"]["exact_geometry"] is False
    assert by_instance["pi-raw-22"]["special_representation"] == "cnc_raw"
    assert by_instance["pi-raw-21"]["geometry_source"] == "cnc_raw_rect"
    assert by_instance["pi-special-miss"]["geometry_source"] == "unavailable"
    assert by_instance["pi-special-miss"]["special_representation"] == "unavailable"

    outlines = {
        element["piece_instance_id"]: element
        for element in projection["elements"]
        if element["kind"] == ELEMENT_KIND_FINISHED_OUTLINE
        and element.get("piece_instance_id")
    }
    assert "pi-raw-22" in outlines
    assert outlines["pi-raw-22"]["payload"]["geometry_source"] == "cnc_raw_rect"
    assert outlines["pi-raw-22"]["payload"]["special_representation"] == "cnc_raw"
    outer = outlines["pi-raw-22"]["geometry"]["outer"]
    assert len(outer) == 4
    assert outer[0] == [100.0, 200.0]
    assert outer[2] == [320.0, 420.0]

    unresolved = [
        element
        for element in projection["elements"]
        if element["kind"] == "unresolved"
        and (element.get("payload") or {}).get("reason") == "special_geometry_unavailable"
    ]
    assert len(unresolved) == 1
    assert unresolved[0]["piece_instance_id"] == "pi-special-miss"


def test_special_exact_json_uses_real_contour():
    import json

    geometry_json = json.dumps(
        {
            "version": 1,
            "kind": "polygon",
            "units": "cm",
            "blank_width_cm": 30,
            "blank_length_cm": 40,
            "points": [[0, 0], [30, 0], [30, 40], [10, 40], [10, 20], [0, 20]],
        }
    )
    snapshot = {
        "physical_execution_contract": 1,
        "sheets": [
            {
                "sheet_no": 1,
                "resource_kind": "FULL_BOARD",
                "pieces": [
                    {
                        "id": 201,
                        "label": "SX",
                        "piece_instance_id": "pi-exact-special",
                        "piece_type": "Special",
                        "x": 5,
                        "y": 6,
                        "w": 30,
                        "h": 40,
                        "original_w": 30,
                        "original_h": 40,
                        "special_shape_geometry_json": geometry_json,
                    }
                ],
            }
        ],
    }
    projection = project_board_editor(snapshot)
    piece = projection["pieces"][0]
    assert piece["geometry_source"] == "special_shape_geometry_json"
    assert piece["exact_geometry"] is True
    assert piece["special_representation"] == "exact_geometry"
    outline = next(
        element
        for element in projection["elements"]
        if element["kind"] == ELEMENT_KIND_FINISHED_OUTLINE
        and element["piece_instance_id"] == "pi-exact-special"
    )
    assert len(outline["geometry"]["outer"]) == 6
    assert outline["payload"]["geometry_source"] == "special_shape_geometry_json"
