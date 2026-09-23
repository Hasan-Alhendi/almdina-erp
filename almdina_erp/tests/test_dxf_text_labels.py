from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ezdxf = pytest.importorskip("ezdxf")

from almdina_erp.almdina_erp.domain.cutting.dxf_applied_trim import (
    apply_adaptive_trim_to_fixed_dxf_layout,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    DxfGeometrySnapshotError,
    canonicalize_snapshot_geometries,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_text_labels import (
    TEXT_LABEL_LAYER,
    canonicalize_text_labels,
    matches_text_label_layer,
    parse_text_label,
    serialize_text_label,
)
from almdina_erp.almdina_erp.infrastructure.cutting.dxf_reader import read_dxf_geometry
from almdina_erp.almdina_erp.services import dxf_import_service
from almdina_erp.almdina_erp.services.dxf_import_service import (
    CUT_PATH_LAYER,
    SHEET_OUTLINE_LAYER,
    DxfImportError,
)


def _rect(msp, points, *, layer: str) -> None:
    corners = tuple(points)
    for start, end in zip(corners, (*corners[1:], corners[0])):
        msp.add_line(start, end, dxfattribs={"layer": layer})


def _order():
    return SimpleNamespace(
        trim_margin_mm=0,
        board_width_cm=122,
        board_length_cm=244,
        full_board_width_mm=1220,
        full_board_length_mm=2440,
        kerf_mm=5,
        pieces=[
            SimpleNamespace(
                cut_width_cm=40,
                cut_length_cm=60,
                width_cm=40,
                length_cm=60,
                qty=1,
                allow_rotation=0,
                piece_type="Regular",
                extra_liner=0,
                extra_back_groove=0,
                extra_full_door_double=0,
                extra_recessed_handle_cutout=0,
                extra_double=0,
            )
        ],
    )


def _write(doc) -> str:
    handle = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
    handle.close()
    doc.saveas(handle.name)
    return handle.name


def _parse(doc, order):
    path = _write(doc)
    try:
        with patch.object(dxf_import_service.frappe, "get_site_path", return_value=path):
            return dxf_import_service.parse_production_dxf("/private/files/labels.dxf", order)
    finally:
        Path(path).unlink(missing_ok=True)


def test_text_label_layer_matches_case_insensitively():
    assert matches_text_label_layer("text")
    assert matches_text_label_layer(" TEXT ")
    assert not matches_text_label_layer("CUT_PATH")
    assert TEXT_LABEL_LAYER == "text"


def test_parse_text_label_rejects_empty_and_keeps_usable_sheet_coords():
    label = parse_text_label(
        {"text": " 3 ", "x_mm": 120.5, "y_mm": 80.0, "height_mm": 20, "rotation_deg": 90}
    )
    assert label["text"] == "3"
    assert label["layer"] == "text"
    assert label["x_mm"] == 120.5
    with pytest.raises(Exception):
        parse_text_label({"text": "  ", "x_mm": 1, "y_mm": 1, "height_mm": 1})
    assert canonicalize_text_labels([]) == []
    assert serialize_text_label(text="1", x_mm=0, y_mm=0, height_mm=10)["text"] == "1"


def test_reader_collects_text_and_mtext_from_text_layer_only(tmp_path: Path):
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0), dxfattribs={"layer": CUT_PATH_LAYER})
    msp.add_text("1", dxfattribs={"layer": "text", "insert": (100, 200), "height": 18})
    msp.add_mtext("2", dxfattribs={"layer": "text", "insert": (150, 250), "char_height": 16})
    msp.add_line((0, 5), (10, 5), dxfattribs={"layer": "text"})
    path = tmp_path / "labels.dxf"
    doc.saveas(path)

    result = read_dxf_geometry(
        str(path),
        relevant_layers={SHEET_OUTLINE_LAYER, CUT_PATH_LAYER, TEXT_LABEL_LAYER},
    )

    assert result["unsupported"] == []
    assert len(result["segments"]) == 1
    assert result["segments"][0]["layer"] == CUT_PATH_LAYER
    texts = {item["text"] for item in result["annotations"]}
    assert texts == {"1", "2"}
    assert all(item["layer"] == "TEXT" for item in result["annotations"])


def test_text_on_cut_path_stays_unsupported(tmp_path: Path):
    doc = ezdxf.new("R2010")
    doc.modelspace().add_text("x", dxfattribs={"layer": CUT_PATH_LAYER, "insert": (0, 0)})
    path = tmp_path / "bad-text.dxf"
    doc.saveas(path)

    result = read_dxf_geometry(str(path), relevant_layers={CUT_PATH_LAYER, "text"})
    assert result["unsupported"] == [{"layer": CUT_PATH_LAYER, "entity_type": "TEXT"}]
    assert result["annotations"] == []


def test_import_attaches_text_labels_without_changing_piece_count():
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    _rect(msp, ((0, 0), (1220, 0), (1220, 2440), (0, 2440)), layer=SHEET_OUTLINE_LAYER)
    _rect(msp, ((0, 0), (400, 0), (400, 600), (0, 600)), layer=CUT_PATH_LAYER)
    msp.add_text("1", dxfattribs={"layer": "text", "insert": (200, 300), "height": 22})
    snapshot = _parse(doc, _order())

    assert len(snapshot["sheets"]) == 1
    assert len(snapshot["sheets"][0]["pieces"]) == 1
    labels = snapshot["sheets"][0]["text_labels"]
    assert len(labels) == 1
    assert labels[0]["text"] == "1"
    assert labels[0]["layer"] == "text"
    assert labels[0]["height_mm"] == pytest.approx(22)


def test_import_without_text_layer_does_not_fail():
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    _rect(msp, ((0, 0), (1220, 0), (1220, 2440), (0, 2440)), layer=SHEET_OUTLINE_LAYER)
    _rect(msp, ((0, 0), (400, 0), (400, 600), (0, 600)), layer=CUT_PATH_LAYER)
    snapshot = _parse(doc, _order())
    assert "text_labels" not in snapshot["sheets"][0]


def test_canonicalize_and_applied_trim_shift_text_labels():
    snapshot = {
        "full_board_width_cm": 122.0,
        "full_board_length_cm": 244.0,
        "usable_board_width_cm": 122.0,
        "usable_board_length_cm": 244.0,
        "trim_cm": 0.0,
        "sheets": [
            {
                "sheet_no": 1,
                "full_width_cm": 122.0,
                "full_length_cm": 244.0,
                "usable_width_cm": 122.0,
                "usable_length_cm": 244.0,
                "w": 122.0,
                "h": 244.0,
                "text_labels": [
                    {
                        "text": "1",
                        "x_mm": 100.0,
                        "y_mm": 200.0,
                        "height_mm": 20.0,
                        "rotation_deg": 0.0,
                        "layer": "text",
                    }
                ],
                "pieces": [
                    {
                        "id": 1,
                        "x": 10.0,
                        "y": 10.0,
                        "w": 30.0,
                        "h": 40.0,
                    }
                ],
            }
        ],
    }
    canonical = canonicalize_snapshot_geometries(snapshot)
    assert canonical["sheets"][0]["text_labels"][0]["text"] == "1"
    trimmed = apply_adaptive_trim_to_fixed_dxf_layout(canonical, preferred_trim_mm=5.0)
    label = trimmed["sheets"][0]["text_labels"][0]
    assert label["x_mm"] == pytest.approx(95.0)
    assert label["y_mm"] == pytest.approx(195.0)

    with pytest.raises(DxfGeometrySnapshotError):
        canonicalize_snapshot_geometries(
            {"sheets": [{"sheet_no": 1, "text_labels": [{"text": "1"}]}]}
        )


def test_text_on_cut_path_still_rejects_upload():
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    _rect(msp, ((0, 0), (1220, 0), (1220, 2440), (0, 2440)), layer=SHEET_OUTLINE_LAYER)
    _rect(msp, ((0, 0), (400, 0), (400, 600), (0, 600)), layer=CUT_PATH_LAYER)
    msp.add_text("1", dxfattribs={"layer": CUT_PATH_LAYER, "insert": (20, 20)})
    with pytest.raises(DxfImportError, match="غير مدعومة"):
        _parse(doc, _order())
