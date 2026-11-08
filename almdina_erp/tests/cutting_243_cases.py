"""Reproducible geometry from the three supplied 26-00243 DXF exports."""
import json
from pathlib import Path

from almdina_erp.almdina_erp.domain.cutting.primitives import (
    create_sheet, expand_piece_groups, make_placed_piece,
)


def source_case():
    return json.loads((Path(__file__).parent / "fixtures/cutting_243_trim.json").read_text())


def observed_plan(index, trim_mm=0):
    case = source_case()
    pieces = expand_piece_groups(case["rows"])
    by_id = {p["id"]: p for p in pieces}
    trim = trim_mm / 10
    sheets = []
    for number, placements in enumerate(case["observed"][index]["sheets"], 1):
        sheet = create_sheet(number, case["full_width_cm"]-2*trim, case["full_length_cm"]-2*trim)
        sheet["pieces"] = [make_placed_piece(by_id[identity], x-trim,
            y-trim, w, h, rotated) for identity, x, y, w, h, rotated in placements]
        sheets.append(sheet)
    return pieces, {"sheets": sheets, "unplaced": [], "method_key": "MaxRects Contact Point"}
