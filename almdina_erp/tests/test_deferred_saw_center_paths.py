"""Deferred CUT_PATH generation until Production Cutting Plan approval."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import ezdxf
import pytest

from almdina_erp.almdina_erp.domain.cutting.catalog import DEFAULT_OPTIMIZATION_MODE_ID
from almdina_erp.almdina_erp.domain.cutting.cutter_center_paths import (
    SAW_CENTER_ABSENT,
    SAW_CENTER_INVALID,
    SAW_CENTER_MATCH,
    classify_saw_center_segments,
    cutter_center_segments,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_issue import SAW_CENTER_INVALID as SAW_CENTER_ISSUE
from almdina_erp.almdina_erp.domain.cutting.plan_settings import (
    DEFAULT_MACHINE_TYPE,
    DEFAULT_OPTIMIZATION_TIME_LIMIT_SEC,
    normalize_plan_settings,
)
from almdina_erp.almdina_erp.services import dxf_export_service, dxf_import_service
from almdina_erp.almdina_erp.services.strict_dxf_import_service import parse_production_dxf


def _rect(x, y, width, height):
    return ((x, y), (x + width, y), (x + width, y + height), (x, y + height))


def _settings(kerf_mm, trim_mm):
    return normalize_plan_settings(
        optimization_mode=DEFAULT_OPTIMIZATION_MODE_ID,
        machine_type=DEFAULT_MACHINE_TYPE,
        optimization_time_limit_sec=DEFAULT_OPTIMIZATION_TIME_LIMIT_SEC,
        kerf_mm=kerf_mm,
        preferred_trim_mm=trim_mm,
    )


def _piece(**fields):
    base = dict(
        piece_instance_id="door-1",
        qty=1,
        piece_type="Regular",
        width_cm=50,
        length_cm=50,
        cut_width_cm=50,
        cut_length_cm=50,
        allow_rotation=0,
        edge_long_left=0,
        edge_long_right=0,
        edge_width_top=0,
        edge_width_bottom=0,
        edge_long_thickness_mm=0,
        edge_width_thickness_mm=0,
        edge_break=0,
        extra_liner=0,
        extra_back_groove=0,
        extra_full_door_double=0,
        extra_recessed_handle_cutout=0,
        extra_double=0,
        liner_reference_side="",
        liner_offset_cm=0,
        liner_width_cm=0,
        liner_start_cm=0,
        liner_length_cm=0,
    )
    base.update(fields)
    return SimpleNamespace(**base)


def _order(pieces):
    return SimpleNamespace(
        name="DCO-DEFER",
        pieces=pieces,
        board_width_cm=122,
        board_length_cm=244,
        full_board_width_mm=1220,
        full_board_length_mm=2440,
        default_edge_type="",
    )


def _write(document):
    handle = tempfile_named()
    document.saveas(handle.name)
    return handle.name


def tempfile_named():
    import tempfile

    return tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)


def _sheet(document):
    modelspace = document.modelspace()
    outline = _rect(0, 0, 1220, 2440)
    for start, end in zip(outline, (*outline[1:], outline[0])):
        modelspace.add_line(start, end, dxfattribs={"layer": "SHEET_OUTLINE"})
    return modelspace


def _import(path, order, *, kerf_mm, trim_mm):
    with patch.object(dxf_import_service.frappe, "get_site_path", return_value=path):
        return parse_production_dxf(path, order, settings=_settings(kerf_mm, trim_mm))


def test_classify_absent_match_and_invalid_without_repair():
    shapes = [(_rect(10, 10, 200, 400), ())]
    board = (0.0, 0.0, 1220.0, 2440.0)
    expected = cutter_center_segments(shapes, 2.5, board=board)
    assert classify_saw_center_segments([], expected) == SAW_CENTER_ABSENT
    assert classify_saw_center_segments(expected, expected) == SAW_CENTER_MATCH
    partial = expected[: max(1, len(expected) // 2)]
    assert classify_saw_center_segments(partial, expected) == SAW_CENTER_INVALID
    bogus = [((0.0, 0.0), (100.0, 0.0))]
    assert classify_saw_center_segments(bogus, expected) == SAW_CENTER_INVALID


def test_modern_upload_without_saw_centers_is_accepted_as_absent():
    finished = _rect(10, 10, 500, 500)
    document = ezdxf.new("R2010")
    for name in ("SHEET_OUTLINE", "CUT_PATH", "GEOMETRY", "TEXT"):
        document.layers.add(name)
    modelspace = _sheet(document)
    for start, end in zip(finished, (*finished[1:], finished[0])):
        modelspace.add_line(start, end, dxfattribs={"layer": "GEOMETRY"})
    modelspace.add_text("1", dxfattribs={"layer": "TEXT", "insert": (250, 250), "height": 12})
    order = _order([
        _piece(piece_instance_id="door-1", width_cm=50, length_cm=50, cut_width_cm=50, cut_length_cm=50),
    ])
    snapshot = _import(_write(document), order, kerf_mm=5, trim_mm=5)
    assert snapshot["saw_center_status"] == "Absent"
    assert [(piece["w"], piece["h"]) for piece in snapshot["sheets"][0]["pieces"]] == [(50, 50)]


def test_modern_upload_with_matching_saw_centers_keeps_present_status():
    finished = _rect(10, 10, 500, 500)
    shapes = [(finished, ())]
    board = (0.0, 0.0, 1220.0, 2440.0)
    centers = cutter_center_segments(shapes, 2.5, board=board)
    document = ezdxf.new("R2010")
    for name in ("SHEET_OUTLINE", "CUT_PATH", "GEOMETRY", "TEXT"):
        document.layers.add(name)
    modelspace = _sheet(document)
    for start, end in zip(finished, (*finished[1:], finished[0])):
        modelspace.add_line(start, end, dxfattribs={"layer": "GEOMETRY"})
    for start, end in centers:
        modelspace.add_line(start, end, dxfattribs={"layer": "CUT_PATH"})
    modelspace.add_text("1", dxfattribs={"layer": "TEXT", "insert": (250, 250), "height": 12})
    order = _order([
        _piece(piece_instance_id="door-1", width_cm=50, length_cm=50, cut_width_cm=50, cut_length_cm=50),
    ])
    snapshot = _import(_write(document), order, kerf_mm=5, trim_mm=5)
    assert snapshot["saw_center_status"] == "Present"


def test_modern_upload_with_invalid_saw_centers_is_rejected():
    finished = _rect(10, 10, 500, 500)
    document = ezdxf.new("R2010")
    for name in ("SHEET_OUTLINE", "CUT_PATH", "GEOMETRY", "TEXT"):
        document.layers.add(name)
    modelspace = _sheet(document)
    for start, end in zip(finished, (*finished[1:], finished[0])):
        modelspace.add_line(start, end, dxfattribs={"layer": "GEOMETRY"})
    # Partial / wrong center: finished edge coordinates, not the radius offset.
    for start, end in zip(finished, (*finished[1:], finished[0])):
        modelspace.add_line(start, end, dxfattribs={"layer": "CUT_PATH"})
    modelspace.add_text("1", dxfattribs={"layer": "TEXT", "insert": (250, 250), "height": 12})
    order = _order([
        _piece(piece_instance_id="door-1", width_cm=50, length_cm=50, cut_width_cm=50, cut_length_cm=50),
    ])
    with pytest.raises(dxf_import_service.DxfImportError) as raised:
        _import(_write(document), order, kerf_mm=5, trim_mm=5)
    assert raised.value.issues[0].code == SAW_CENTER_ISSUE


def test_legacy_upload_without_geometry_stays_legacy():
    finished = _rect(10, 10, 500, 500)
    legacy = ezdxf.new("R2010")
    for name in ("SHEET_OUTLINE", "CUT_PATH", "text"):
        legacy.layers.add(name)
    modelspace = _sheet(legacy)
    for start, end in zip(finished, (*finished[1:], finished[0])):
        modelspace.add_line(start, end, dxfattribs={"layer": "CUT_PATH"})
    modelspace.add_text("1", dxfattribs={"layer": "text", "insert": (250, 250), "height": 12})
    order = _order([
        _piece(piece_instance_id="door-1", width_cm=50, length_cm=50, cut_width_cm=50, cut_length_cm=50),
    ])
    snapshot = _import(_write(legacy), order, kerf_mm=5, trim_mm=5)
    assert snapshot["saw_center_status"] == "Legacy"


def test_export_include_saw_centers_only_after_approval():
    draft = SimpleNamespace(
        name="CP-DRAFT",
        status="Draft",
        source_type="System",
        saw_center_status="Absent",
        dxf_file="",
    )
    approved = SimpleNamespace(
        name="CP-APP",
        status="Approved",
        source_type="System",
        saw_center_status="Absent",
        dxf_file="",
    )
    order = SimpleNamespace(approved_plan="CP-APP")
    assert dxf_export_service._include_saw_centers_for_export(draft, "system", order) is False
    assert dxf_export_service._include_saw_centers_for_export(approved, "approved", order) is True
    assert dxf_export_service._include_saw_centers_for_export(approved, None, order) is True
    assert dxf_export_service._include_saw_centers_for_export(draft, None, order) is False


def test_custom_tab_regenerates_when_uploaded_plan_is_current_approval_without_paths():
    uploaded = SimpleNamespace(
        name="CP-UP-1",
        status="Approved",
        source_type="Uploaded DXF",
        saw_center_status="Absent",
        dxf_file="/private/files/design.dxf",
    )
    order = SimpleNamespace(approved_plan="CP-UP-1")
    assert dxf_export_service.prefer_original_uploaded_download(order, uploaded) is False
    assert dxf_export_service._include_saw_centers_for_export(uploaded, "custom", order) is True


def test_custom_tab_keeps_original_before_approval_and_when_paths_present():
    draft = SimpleNamespace(
        name="CP-UP-2",
        status="Draft",
        source_type="Uploaded DXF",
        saw_center_status="Absent",
        dxf_file="/private/files/design.dxf",
    )
    present = SimpleNamespace(
        name="CP-UP-3",
        status="Approved",
        source_type="Uploaded DXF",
        saw_center_status="Present",
        dxf_file="/private/files/ready.dxf",
    )
    other_approved = SimpleNamespace(approved_plan="CP-SYSTEM")
    same_approved = SimpleNamespace(approved_plan="CP-UP-3")
    assert dxf_export_service.prefer_original_uploaded_download(other_approved, draft) is True
    assert dxf_export_service._include_saw_centers_for_export(draft, "custom", other_approved) is False
    assert dxf_export_service.prefer_original_uploaded_download(same_approved, present) is True
    # A different approved plan must never force Custom to emit the other plan's paths.
    assert dxf_export_service._is_current_approved_plan(other_approved, draft) is False


def test_original_manufacturing_ready_matrix():
    present = SimpleNamespace(saw_center_status="Present", dxf_file="/private/files/a.dxf")
    absent = SimpleNamespace(saw_center_status="Absent", dxf_file="/private/files/a.dxf")
    legacy = SimpleNamespace(saw_center_status="Legacy", dxf_file="/private/files/a.dxf")
    unknown = SimpleNamespace(saw_center_status="Unknown", dxf_file="/private/files/a.dxf")
    assert dxf_export_service._original_is_manufacturing_ready(present) is True
    assert dxf_export_service._original_is_manufacturing_ready(absent) is False
    assert dxf_export_service._original_is_manufacturing_ready(legacy) is True
    assert dxf_export_service._original_is_manufacturing_ready(unknown) is True
