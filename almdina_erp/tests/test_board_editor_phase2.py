"""Board editor Phase 2: stable identities, auth wiring, and display contracts."""

from __future__ import annotations

import copy
import inspect
from pathlib import Path

import pytest

from almdina_erp.almdina_erp.application.cutting.board_editor_projection import (
    CONTENT_STATE_EMPTY,
    CONTENT_STATE_UNAVAILABLE,
    project_board_editor,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_hosting import (
    hosting_forest_for_pieces,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    serialize_geometry_mm,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_topology import PartGeometry
from almdina_erp.almdina_erp.services import board_editor_query_service as query_service
from almdina_erp.tests.security_endpoint_contracts import WHITELISTED_ENDPOINT_CONTRACTS


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"
PUBLIC = ROOT / "public"


def _geometry(outer, holes=()):
    return serialize_geometry_mm(
        PartGeometry(
            outer=tuple(tuple(point) for point in outer),
            holes=tuple(tuple(tuple(point) for point in hole) for hole in holes),
        )
    )


def _multi_sheet_snapshot():
    return {
        "physical_execution_contract": 1,
        "saw_center_status": "Present",
        "sheets": [
            {
                "sheet_no": 1,
                "full_width_cm": 122,
                "full_length_cm": 244,
                "pieces": [
                    {
                        "id": 1,
                        "label": "1.1",
                        "piece_instance_id": "a",
                        "x": 1,
                        "y": 1,
                        "w": 20,
                        "h": 30,
                        "geometry": _geometry(((0, 0), (200, 0), (200, 300), (0, 300))),
                    }
                ],
            },
            {
                "sheet_no": 2,
                "full_width_cm": 122,
                "full_length_cm": 244,
                "pieces": [
                    {
                        "id": 2,
                        "label": "2.1",
                        "piece_instance_id": "b",
                        "x": 2,
                        "y": 2,
                        "w": 15,
                        "h": 25,
                        "geometry": _geometry(((0, 0), (150, 0), (150, 250), (0, 250))),
                    }
                ],
            },
        ],
    }


def test_element_ids_are_stable_unique_and_sheet_scoped():
    snapshot = _multi_sheet_snapshot()
    first = project_board_editor(snapshot)
    second = project_board_editor(snapshot)
    ids = [row["element_id"] for row in first["elements"]]

    assert len(ids) == len(set(ids))
    assert ids == [row["element_id"] for row in second["elements"]]
    assert any(element_id.startswith("sheet:1:piece:1:") for element_id in ids)
    assert any(element_id.startswith("sheet:2:piece:2:") for element_id in ids)
    assert not any(":geometry:1" == element_id[-10:] for element_id in ids)


def test_hosting_cycle_is_unresolved_not_nested():
    pieces = [
        {"id": 1, "label": "1.1", "glass_host_piece_id": 2},
        {"id": 2, "label": "2.1", "glass_host_piece_id": 1},
    ]
    forest = hosting_forest_for_pieces(pieces)
    reasons = {row["reason"] for row in forest["unresolved_host_links"]}
    assert "host_cycle" in reasons
    # At most one direction of a mutual host link may remain; never a closed nest.
    nested_pairs = [
        (root["piece_id"], guest["piece_id"])
        for root in forest["roots"]
        for guest in root["guests"]
    ]
    assert not (
        (1, 2) in nested_pairs and (2, 1) in nested_pairs
    )


def test_auxiliary_inputs_are_financially_sanitized():
    projection = project_board_editor(
        {"sheets": []},
        layer_table=[{"original_name": "along", "edge_rate_usd": 9, "is_empty": True}],
        reference_entities=[
            {
                "layer": "NOTES",
                "entity_id": 1,
                "approved_cost": 12,
                "start": [0, 0],
                "end": [1, 1],
            }
        ],
    )
    blob = str(projection)
    assert "edge_rate_usd" not in blob
    assert "approved_cost" not in blob
    along = next(layer for layer in projection["layers"] if layer["match_key"] == "ALONG")
    assert along["content_state"] == CONTENT_STATE_EMPTY


def test_cut_path_present_marked_unavailable_not_empty():
    projection = project_board_editor(
        {"sheets": [], "saw_center_status": "Present"},
        source_kind="system",
    )
    cut = next(layer for layer in projection["layers"] if layer["match_key"] == "CUT_PATH")
    assert cut["content_state"] == CONTENT_STATE_UNAVAILABLE
    assert cut["is_defined_empty"] is False
    assert projection["persistence"]["generates_cut_path_on_open"] is False


def test_occupied_source_layer_without_elements_is_unavailable():
    projection = project_board_editor(
        {"sheets": []},
        layer_table=[{"original_name": "along", "is_empty": False}],
    )
    along = next(layer for layer in projection["layers"] if layer["match_key"] == "ALONG")
    assert along["content_state"] == CONTENT_STATE_UNAVAILABLE
    assert along["is_defined_empty"] is False


def test_coordinate_frame_is_declared():
    projection = project_board_editor({"sheets": []})
    frame = projection["coordinate_frame"]
    assert frame["unit"] == "mm"
    assert frame["coordinate_space"] == "usable_sheet"
    assert frame["rtl_does_not_mirror_geometry"] is True


def test_query_service_requires_explicit_plan_and_capability_contract():
    source = Path(query_service.__file__).read_text(encoding="utf-8")
    assert "def get_board_editor_projection" in source
    assert "plan_name" in source
    assert "VIEW_CUTTING_PLAN" in source
    assert "file_url" in source  # documented rejection / never client authority
    assert "_load_scoped_plan_dxf_bytes" in source
    assert "project_board_editor" in source
    assert "cutter_center_paths" not in source
    assert (
        "almdina_erp.almdina_erp.services.board_editor_query_service.get_board_editor_projection"
        in WHITELISTED_ENDPOINT_CONTRACTS
    )


def test_query_service_is_read_only_whitelist():
    import re

    source = inspect.getsource(query_service.get_board_editor_projection)
    assert "frappe.whitelist" in Path(query_service.__file__).read_text(encoding="utf-8")
    assert "db.set_value" not in source
    assert "save(" not in source
    # Capability labels may say view_approved; mutating approve* calls must not appear.
    assert re.search(r"\bapprove(?:_|\()", source.lower()) is None


def test_page_and_entry_point_exist():
    page_js = APP / "page" / "board_editor" / "board_editor.js"
    page_json = APP / "page" / "board_editor" / "board_editor.json"
    context = PUBLIC / "js" / "door_cutting_order" / "cutting_plan" / "door_cutting_order_plan_context_actions_ux.js"
    assert page_js.is_file()
    assert page_json.is_file()
    context_source = context.read_text(encoding="utf-8")
    assert "Open board editor" in context_source
    assert "dco-open-board-editor" in context_source
    assert "board-editor" in context_source
    assert "edit_optimizer_settings" not in context_source.split("canOpenBoardEditor", 1)[1][:400]


def test_frontend_modules_use_svg_and_single_store():
    canvas = (PUBLIC / "js" / "board_editor" / "canvas_renderer.js").read_text(encoding="utf-8")
    store = (PUBLIC / "js" / "board_editor" / "store.js").read_text(encoding="utf-8")
    controller = (PUBLIC / "js" / "board_editor" / "controller.js").read_text(encoding="utf-8")
    assert "native SVG" in canvas or "<svg" in canvas
    assert "cdn." not in canvas.lower()
    assert "createStore" in store
    assert "layerVisibility" in store
    assert "createLatestRequestGate" in controller or "requestGate" in controller
    assert "suspend" in controller


def test_historical_snapshot_unchanged_after_phase2_projection():
    historical = {
        "sheets": [
            {
                "sheet_no": 1,
                "pieces": [
                    {
                        "id": 9,
                        "label": "9.1",
                        "x": 0,
                        "y": 0,
                        "w": 10,
                        "h": 10,
                        "geometry": _geometry(((0, 0), (100, 0), (100, 100), (0, 100))),
                    }
                ],
            }
        ]
    }
    before = copy.deepcopy(historical)
    projection = project_board_editor(historical)
    assert historical == before
    assert projection["pieces"][0]["piece_instance_id"] is None


def test_order_allow_rotation_maps_plan_copy_suffix():
    flags = {
        "piece:abc-uuid": True,
        "piece:locked": False,
    }
    map_id = query_service._order_allow_rotation_for_plan_instance
    assert map_id(flags, "piece:abc-uuid") is True
    assert map_id(flags, "piece:abc-uuid:1") is True
    assert map_id(flags, "piece:abc-uuid:2") is True
    assert map_id(flags, "piece:locked:1") is False
    assert map_id(flags, "piece:missing:1") is None
    assert map_id(flags, "piece:abc-uuid:x") is None


def test_enrich_snapshot_sets_proven_allow_from_order_base_id():
    class _Row:
        def __init__(self, instance_id, allow):
            self.piece_instance_id = instance_id
            self.allow_rotation = allow

    class _Order:
        def get(self, key):
            if key == "pieces":
                return [_Row("piece:rotatable", 1), _Row("piece:fixed", 0)]
            return None

    snapshot = {
        "sheets": [
            {
                "sheet_no": 1,
                "pieces": [
                    {"piece_instance_id": "piece:rotatable:1", "label": "A"},
                    {"piece_instance_id": "piece:fixed:1", "label": "B"},
                    {"piece_instance_id": "piece:orphan:1", "label": "C"},
                ],
            }
        ],
        "unplaced": [],
    }
    enriched = query_service._enrich_snapshot_allow_rotation(snapshot, _Order())
    pieces = {row["piece_instance_id"]: row for row in enriched["sheets"][0]["pieces"]}
    assert pieces["piece:rotatable:1"]["allow_rotation"] is True
    assert pieces["piece:rotatable:1"]["allow_rotation_proven"] is True
    assert pieces["piece:fixed:1"]["allow_rotation"] is False
    assert pieces["piece:fixed:1"]["allow_rotation_proven"] is True
    assert "allow_rotation" not in pieces["piece:orphan:1"]


def test_content_revision_token_stable_across_idle_and_completed():
    source = (APP / "services" / "board_editor_query_service.py").read_text(encoding="utf-8")
    assert '"1" if job_active else "0"' in source
    assert "stable active-job bit" in source
    token_block = source.split("content_revision_token = ")[1].split("return {", 1)[0]
    assert "job_status" not in token_block
