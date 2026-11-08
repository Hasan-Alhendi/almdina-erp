"""Bounded Regular grid proposals made from original source instances.

No virtual pieces, reference poses, new stock or stable-Kerf policy changes.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import math
import time

from .evaluation import evaluate_plan
from .primitives import create_sheet, num, orientations_for
from .strategies.maxrects import find_best_position_maxrects, place_piece_maxrects


def _unprotected_regular(item):
    protected = (
        "geometry", "overlays", "special_shape_geometry_json", "placement_outline_cm",
        "glass_host_piece_id", "mirrored", "corner_mirrored", "placement_mirrored",
        "extra_liner", "extra_back_groove", "extra_recessed_handle_cutout",
        "placement_rotation_deg", "corner_rotation_quarter_turns",
    )
    return ((item.get("piece_type") or "Regular") == "Regular"
            and (item.get("resource_kind") or "FULL_BOARD") == "FULL_BOARD"
            and not any(item.get(key) for key in protected))


def supports_regular_sources(sources):
    return bool(sources) and len(sources) <= 64 and all(_unprotected_regular(p) for p in sources)


def supports_regular_proposals(plan, sources):
    """Conservative first research cohort; manufacturing extras stay native."""
    if not supports_regular_sources(sources) or plan.get("unplaced") or not plan.get("sheets"):
        return False
    if not all(_unprotected_regular(p) for s in plan["sheets"] for p in s.get("pieces") or []):
        return False
    return all((s.get("resource_kind") or "FULL_BOARD") == "FULL_BOARD"
               for s in plan["sheets"])


def grid_specs(sources, width, height, kerf):
    """At most two families, deterministic candidates; coordinates stay in cm."""
    if not all(math.isfinite(v) for v in (width, height, kerf)) or min(width, height) <= 0 or kerf < 0:
        return []
    families = defaultdict(list)
    for piece in sorted(sources, key=lambda p: int(p["id"])):
        w, h = num(piece.get("width_cm")), num(piece.get("length_cm"))
        if min(w, h) <= 0 or not all(map(math.isfinite, (w, h))):
            return []
        families[(w, h, bool(piece.get("allow_rotation")))].append(piece)
    repeated = [v for v in families.values() if len(v) >= 2]
    repeated.sort(key=lambda f: (-len(f)*f[0]["width_cm"]*f[0]["length_cm"], int(f[0]["id"])))
    specs = []
    for family in repeated[:2]:
        for orientation in orientations_for(family[0]):
            w, h = orientation["w"], orientation["h"]
            max_c = min(len(family), int((width+kerf+1e-9)/(w+kerf)))
            max_r = int((height+kerf+1e-9)/(h+kerf))
            for columns in range(1, max_c+1):
                rows = min(max_r, len(family)//columns)
                if rows*columns < 2:
                    continue
                specs.append((family, orientation, columns, rows))
    specs.sort(key=lambda s: (-s[2]*s[3], int(s[0][0]["id"]),
                              s[1]["rotated"], -s[2], s[3]))
    return specs


def regular_template_candidates(plan, sources, width, height, kerf, *, budget, deadline):
    if not supports_regular_proposals(plan, sources):
        return
    limit = len(plan["sheets"])
    for family, orientation, columns, rows in grid_specs(sources, width, height, kerf)[:6]:
        if time.monotonic() >= deadline or not budget.take("templates"):
            return
        sheets = []

        def new_sheet():
            index = len(sheets)
            sheet = deepcopy(plan["sheets"][index])
            for key in ("pieces", "free_rects", "skyline", "shelves"):
                sheet.pop(key, None)
            sheet.update(create_sheet(index+1, width, height))
            sheets.append(sheet)
            return sheet

        first = new_sheet()
        members = family[:columns*rows]
        selected = {int(p["id"]) for p in members}
        for index, piece in enumerate(members):
            # Inner pitch includes k once. place_piece reserves the same k
            # in free-space bookkeeping, never in the actual part dimension.
            position = dict(x=(index % columns)*(orientation["w"]+kerf),
                            y=(index // columns)*(orientation["h"]+kerf), **orientation)
            place_piece_maxrects(first, piece, position, kerf)
        remaining = sorted((p for p in sources if int(p["id"]) not in selected),
                           key=lambda p: (-num(p.get("area_m2")), int(p["id"])))
        complete = True
        for piece in remaining:
            if time.monotonic() >= deadline:
                return
            for sheet in sheets:
                spot = find_best_position_maxrects(sheet, piece, "contact_point", kerf)
                if spot is not None:
                    place_piece_maxrects(sheet, piece, spot, kerf)
                    break
            else:
                if len(sheets) >= limit:
                    complete = False
                    break
                sheet = new_sheet()
                spot = find_best_position_maxrects(sheet, piece, "contact_point", kerf)
                if spot is None:
                    complete = False
                    break
                place_piece_maxrects(sheet, piece, spot, kerf)
        if complete:
            candidate = deepcopy(plan)
            candidate.update(evaluate_plan(dict(sheets=sheets, unplaced=[]), sources,
                width, height, "MaxRects - Contact Point", "MaxRects Contact Point", 4))
            candidate["ordering_strategy"] = "regular_grid"
            yield candidate
        else:
            # Failed packs also return control to the shared A/C scheduler.
            yield None
