from types import SimpleNamespace

from almdina_erp.almdina_erp.services.export_validation_service import validate_cutting_plan_document


def _source(**overrides):
    values = {
        "sheet_no": 1,
        "board_item": "MDF-TEST",
        "source_type": "Full Board",
        "remnant": None,
        "usable_width_mm": 1000,
        "usable_length_mm": 1000,
        "full_width_mm": 1000,
        "full_length_mm": 1000,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _piece(label, x, y, w, h):
    return SimpleNamespace(
        sheet_no=1,
        piece_label=label,
        piece_id=1,
        source_piece_no=1,
        copy_no=1,
        x_mm=x,
        y_mm=y,
        width_mm=w,
        height_mm=h,
        original_width_cm=w / 10,
        original_length_cm=h / 10,
        rotated=0,
        edge_long_right=0,
        edge_long_left=0,
        edge_width_top=0,
        edge_width_bottom=0,
        edge_type="",
        notes="",
    )


def _plan(pieces, sources=None):
    return SimpleNamespace(
        plan_kind="Replacement",
        board_item="MDF-TEST",
        sources=sources if sources is not None else [_source()],
        placed_pieces=pieces,
        snapshot_json="{}",
    )


def test_dxf_validator_rejects_overlap():
    errors = validate_cutting_plan_document(
        _plan([
            _piece("A", 0, 0, 600, 600),
            _piece("B", 500, 500, 400, 400),
        ])
    )
    assert any("overlap" in message.lower() for message in errors)


def test_dxf_validator_rejects_out_of_bounds():
    errors = validate_cutting_plan_document(_plan([_piece("A", 800, 0, 300, 300)]))
    assert any("bounds" in message.lower() for message in errors)


def test_dxf_validator_rejects_missing_source_sheet():
    piece = _piece("A", 0, 0, 100, 100)
    piece.sheet_no = 2
    errors = validate_cutting_plan_document(_plan([piece]))
    assert any("missing source" in message.lower() for message in errors)


def test_dxf_validator_accepts_non_overlapping_valid_geometry():
    errors = validate_cutting_plan_document(
        _plan([
            _piece("A", 0, 0, 400, 400),
            _piece("B", 400, 0, 400, 400),
        ])
    )
    assert errors == []
