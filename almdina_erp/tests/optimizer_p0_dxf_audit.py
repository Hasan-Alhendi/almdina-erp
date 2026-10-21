"""Read-only comparison of local customer DXFs; never copy source files to Git.

Usage: python -m almdina_erp.tests.optimizer_p0_dxf_audit /path/to/extracted
Requires ezdxf. A rectangle signature proves only the cut-envelope multiset,
not source order inputs, machine eligibility, trim, kerf or material identity.
"""

import json
import sys
from collections import Counter
from pathlib import Path

import ezdxf


CASE_IDS = (230, 231, 232, 234, 235, 236, 240, 241, 242, 243, 244, 246)


def _dims(points):
    width = round((max(x for x, _ in points) - min(x for x, _ in points)) / 10, 3)
    height = round((max(y for _, y in points) - min(y for _, y in points)) / 10, 3)
    return tuple(sorted((width, height)))


def _is_rectangle(points):
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return (
        min(xs) < max(xs)
        and min(ys) < max(ys)
        and set(points) == {
            (min(xs), min(ys)), (min(xs), max(ys)),
            (max(xs), min(ys)), (max(xs), max(ys)),
        }
    )


def inspect(path):
    entities = list(ezdxf.readfile(path).modelspace())
    geometry = [e for e in entities if e.dxf.layer == "GEOMETRY"]
    outlines = [e for e in entities if e.dxf.layer == "SHEET_OUTLINE"]
    if not geometry or not outlines:
        return {"verified_rectangles": False, "reason": "missing_geometry_or_board"}
    signatures = []
    verified = True
    if all(e.dxftype() == "LWPOLYLINE" for e in geometry):
        for e in geometry:
            pts = [(round(x, 3), round(y, 3)) for x, y in e.get_points("xy")]
            if not _is_rectangle(pts):
                verified = False
            signatures.append(_dims(pts))
    elif all(e.dxftype() == "LINE" for e in geometry):
        if len(geometry) % 4:
            verified = False
        for i in range(0, len(geometry), 4):
            lines = geometry[i : i + 4]
            points = [
                (round(x, 3), round(y, 3))
                for e in lines
                for x, y in ((e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y))
            ]
            if len(lines) != 4 or not _is_rectangle(points):
                verified = False
            signatures.append(_dims(points))
    else:
        verified = False
    if outlines[0].dxftype() == "LWPOLYLINE":
        boards = len(outlines)
    elif all(e.dxftype() == "LINE" for e in outlines) and len(outlines) % 4 == 0:
        boards = len(outlines) // 4
    else:
        boards = None
        verified = False
    return {
        "boards_drawn": boards,
        "piece_envelopes": len(signatures),
        "verified_rectangles": verified,
        "envelopes": Counter(signatures) if verified else None,
    }


def run(directory):
    root = Path(directory)
    results = {}
    for case_id in CASE_IDS:
        designer_files = list(root.glob(f"{case_id}*.dxf"))
        system_files = list(root.glob(f"cutting_plan_26-00{case_id}*.dxf"))
        if len(designer_files) != 1 or len(system_files) != 1:
            results[case_id] = {"classification": "INSUFFICIENT_EVIDENCE", "reason": "ambiguous_pair"}
            continue
        designer, system = inspect(designer_files[0]), inspect(system_files[0])
        comparable = designer["verified_rectangles"] and system["verified_rectangles"]
        if not comparable:
            category = "INSUFFICIENT_EVIDENCE"
        elif designer["envelopes"] == system["envelopes"]:
            category = "MATCHED"
        else:
            category = "INPUT_MISMATCH"
        results[case_id] = {
            "classification": category,
            "scope": "piece envelope multiset only; real optimizer replay remains blocked",
            "designer_boards_drawn": designer.get("boards_drawn"),
            "system_boards_drawn": system.get("boards_drawn"),
            "designer_piece_envelopes": designer.get("piece_envelopes"),
            "system_piece_envelopes": system.get("piece_envelopes"),
            "designer_verified_rectangles": designer["verified_rectangles"],
            "system_verified_rectangles": system["verified_rectangles"],
            "different_envelope_copies": (
                [sum((designer["envelopes"] - system["envelopes"]).values()),
                 sum((system["envelopes"] - designer["envelopes"]).values())]
                if comparable else None
            ),
        }
    return results


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m almdina_erp.tests.optimizer_p0_dxf_audit EXTRACTED_DIR")
    print(json.dumps(run(sys.argv[1]), indent=2))
