"""Move finished nests as rigid groups and drop a board only when that fits.

A translation shifts every piece in the group by the same amount. Rotation,
mirroring, kerf gaps, void guests, and glass-host links stay as they were.
The search is bounded by a deadline, a few group orders, and a short anchor
list. Bounding boxes only reject hopeless spots; acceptance uses the real
outlines.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations, permutations
from typing import Any, Mapping, Sequence

from .dxf_geometry import polygon_distance, polygons_overlap
from .glass_opening_nesting import material_outline_cm
from .primitives import num


L_PAIR = "L Pair"
L_QUAD = "L Quad"
CLIPPED_PAIR = "Clipped Corner Pair"
CLIPPED_QUAD = "Clipped Corner Quad"
SINGLE_CORNER = "Single Corner"
GLASS_HOST = "Glass Host + Guests"
STANDALONE = "Standalone Piece"

_CORNER_TYPES = frozenset({"Clipped Corner", "L-Shaped Corner"})
_MAX_ANCHORS = 32
_MAX_VICTIMS = 4
_MAX_ORDERS = 4
_MAX_REPACK_SHEETS = 3
_MAX_LIVE_GROUPS = 8


@dataclass(frozen=True)
class NestingPlacementGroup:
    """One finished nest, or one loose piece, moved only as a whole."""

    kind: str
    piece_ids: tuple[int, ...]
    sheet_no: int
    origin_x: float
    origin_y: float
    pieces: tuple[dict[str, Any], ...]
    relative_offsets: tuple[tuple[int, float, float], ...]
    orientations: tuple[tuple[int, int, bool, float, bool], ...]
    glass_links: tuple[tuple[int, int], ...]
    guest_ids: tuple[int, ...]
    voids: tuple[tuple[float, float, float, float], ...]

    @property
    def area(self) -> float:
        return sum(num(piece.get("w")) * num(piece.get("h")) for piece in self.pieces)


def consolidate_nested_boards(
    plan: dict[str, Any],
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    *,
    machine_type: str,
    mirroring_allowed: bool,
    deadline: float,
) -> dict[str, Any]:
    """Pack rigid nests onto fewer boards, or the same boards more tightly.

    The input plan is returned unchanged when no complete candidate survives
    validation. A failed move never leaves part of a board transferred.
    """

    if machine_type == "Panel Saw" or time.monotonic() > deadline:
        return plan
    if plan.get("unplaced") or not plan.get("sheets"):
        return plan
    started = time.monotonic()
    prototypes = extract_placement_groups(plan)
    if not any(group.kind != STANDALONE for group in prototypes):
        return plan
    best = plan
    attempts = 0
    outcome = "unchanged"
    seen_victims: set[tuple[int, tuple[int, ...]]] = set()
    while attempts < _MAX_VICTIMS and time.monotonic() <= deadline:
        groups = extract_placement_groups(best)
        victim = _next_victim(best, groups, seen_victims)
        if victim is None:
            break
        moving = [group for group in groups if group.sheet_no == victim]
        seen_victims.add((victim, tuple(sorted(piece_id for group in moving for piece_id in group.piece_ids))))
        attempts += 1
        candidate = _empty_sheet(
            best,
            victim,
            moving,
            board_w_cm,
            board_h_cm,
            kerf_cm,
            deadline,
        )
        if candidate is None:
            continue
        if not _same_nests(candidate, prototypes):
            continue
        if not _geometry_ok(
            candidate,
            pieces,
            board_w_cm,
            board_h_cm,
            kerf_cm,
            mirroring_allowed=mirroring_allowed,
            deadline=deadline,
        ):
            continue
        if len(candidate.get("sheets") or []) >= len(best.get("sheets") or []):
            continue
        best = candidate
        outcome = "cancelled_sheet"
        seen_victims.clear()
    if time.monotonic() <= deadline:
        repacked = _repack_boards(
            best,
            prototypes,
            board_w_cm,
            board_h_cm,
            kerf_cm,
            deadline,
        )
        if (
            repacked is not None
            and _same_nests(repacked, prototypes)
            and _geometry_ok(
                repacked,
                pieces,
                board_w_cm,
                board_h_cm,
                kerf_cm,
                mirroring_allowed=mirroring_allowed,
                deadline=deadline,
            )
            and _tighter(repacked, best)
            and len(repacked.get("sheets") or []) <= len(best.get("sheets") or [])
        ):
            if repacked is not best:
                outcome = outcome if outcome == "cancelled_sheet" else "repacked"
                best = repacked
    if best is plan:
        return plan
    best["nest_consolidation_diagnostics"] = {
        "outcome": outcome,
        "sheets_before": len(plan.get("sheets") or []),
        "sheets_after": len(best.get("sheets") or []),
        "attempts": attempts,
        "elapsed_sec": round(time.monotonic() - started, 4),
    }
    return best


def extract_placement_groups(plan: Mapping[str, Any]) -> list[NestingPlacementGroup]:
    """Split a plan into rigid nests and leftover single pieces."""

    from .plan_search import _records_shape_nest

    located = _locate(plan)
    if not located:
        return []
    assigned: set[int] = set()
    groups: list[NestingPlacementGroup] = []
    for members in _glass_members(located):
        group = _build_group(GLASS_HOST, members, located, assigned)
        if group is not None:
            groups.append(group)
    for members in _diagnostic_members(plan, located, assigned):
        kind = _kind_for(members)
        if kind == STANDALONE:
            continue
        group = _build_group(kind, members, located, assigned)
        if group is not None:
            groups.append(group)
    by_sheet: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for piece_id, (sheet_no, piece) in located.items():
        if piece_id in assigned or not _corner_nest(piece, _records_shape_nest):
            continue
        by_sheet[(sheet_no, str(piece.get("piece_type") or ""))].append(piece)
    for (sheet_no, _piece_type), corners in by_sheet.items():
        for members in _split_corners(corners):
            kind = _kind_for(members)
            if kind == STANDALONE:
                continue
            absorbed = _absorb_inside(members, located, sheet_no, assigned)
            group = _build_group(kind, [*members, *absorbed], located, assigned)
            if group is not None:
                groups.append(group)
    for piece_id, (sheet_no, piece) in located.items():
        if piece_id in assigned:
            continue
        group = _build_group(STANDALONE, [piece], located, assigned)
        if group is not None:
            groups.append(group)
    return groups


def best_rigid_translation(
    sheet: Mapping[str, Any],
    pieces: Sequence[Mapping[str, Any]],
    kerf_cm: float,
    board_w_cm: float,
    board_h_cm: float,
    *,
    constraint: str = "",
    deadline: float | None = None,
) -> tuple[float, float, tuple[Any, ...]] | None:
    """Return the dx, dy of the best legal shift, plus its rank.

    ``constraint`` is ``pair`` or ``single`` when the opening has to keep
    facing the board interior. Quads, glass, and loose pieces pass ``""``.
    """

    from .shape_aware_nesting import (
        _block_size,
        _inward_score,
        _pair_inward_score,
        _translate_pieces,
    )

    if not pieces:
        return None
    origin_x, origin_y = _origin(pieces)
    width, height = _block_size(pieces)
    local_outlines = []
    for piece in pieces:
        outline = material_outline_cm(piece)
        if outline is None:
            return None
        local_outlines.append(
            tuple((point[0] - origin_x, point[1] - origin_y) for point in outline)
        )
    occupied = []
    for other in sheet.get("pieces") or []:
        outline = material_outline_cm(other)
        if outline is None:
            return None
        occupied.append(outline)
    anchors = _anchors(
        sheet,
        origin_x,
        origin_y,
        width,
        height,
        kerf_cm,
        board_w_cm,
        board_h_cm,
    )
    ranked: list[tuple[tuple[Any, ...], float, float]] = []
    for anchor_x, anchor_y in anchors:
        if deadline is not None and time.monotonic() >= deadline:
            break
        dx = anchor_x - origin_x
        dy = anchor_y - origin_y
        shifted = [
            tuple((point[0] + anchor_x, point[1] + anchor_y) for point in outline)
            for outline in local_outlines
        ]
        if any(not _outline_inside(outline, board_w_cm, board_h_cm) for outline in shifted):
            continue
        if not _outlines_clear(shifted, occupied, kerf_cm):
            continue
        moved = _translate_pieces(pieces, dx, dy)
        if constraint == "pair" and _pair_inward_score(_opening_pieces(moved), board_w_cm, board_h_cm) is None:
            continue
        if constraint == "single":
            opener = _opening_pieces(moved)[0]
            score = _inward_score(opener, board_w_cm, board_h_cm)
            if score is None or score <= 0.05:
                continue
            if _joins_existing_pair(opener, sheet.get("pieces") or [], kerf_cm):
                continue
        rank = _pack_rank(sheet, moved, anchor_x, anchor_y, width, height, kerf_cm, dx, dy)
        ranked.append((rank, dx, dy))
    if not ranked:
        return None
    if deadline is not None and time.monotonic() >= deadline:
        return None
    ranked.sort(key=lambda item: item[0])
    if not occupied:
        best_rank, dx, dy = ranked[0]
        return dx, dy, best_rank
    best_rank, dx, dy = _with_remnant(
        ranked[:8],
        sheet,
        pieces,
        board_w_cm,
        board_h_cm,
    )
    return dx, dy, best_rank


def translation_anchors(
    sheet: Mapping[str, Any],
    width: float,
    height: float,
    kerf_cm: float,
    board_w_cm: float,
    board_h_cm: float,
) -> list[tuple[float, float]]:
    """Candidate origins for a block whose own origin is currently zero."""

    return _anchors(sheet, 0.0, 0.0, width, height, kerf_cm, board_w_cm, board_h_cm)


def _empty_sheet(
    plan: Mapping[str, Any],
    victim_no: int,
    moving: Sequence[NestingPlacementGroup],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    deadline: float,
) -> dict[str, Any] | None:
    if not moving or not any(group.kind != STANDALONE for group in moving):
        return None
    others = [
        sheet
        for sheet in plan.get("sheets") or []
        if int(sheet.get("sheet_no") or 0) != int(victim_no)
    ]
    if not others:
        return None
    failed: set[tuple[Any, ...]] = set()
    for order in _orders(moving):
        if time.monotonic() > deadline:
            return None
        from copy import deepcopy

        trial = [deepcopy(sheet) for sheet in others]
        placed = True
        for group in order:
            if time.monotonic() > deadline:
                return None
            if not _seat_group(trial, group, kerf_cm, board_w_cm, board_h_cm, deadline, failed):
                placed = False
                break
        if not placed:
            continue
        kept = [sheet for sheet in trial if sheet.get("pieces")]
        for index, sheet in enumerate(kept, start=1):
            sheet["sheet_no"] = index
            sheet["w"] = board_w_cm
            sheet["h"] = board_h_cm
        return _replace_sheets(plan, kept)
    return None


def _repack_boards(
    plan: Mapping[str, Any],
    prototypes: Sequence[NestingPlacementGroup],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    deadline: float,
) -> dict[str, Any] | None:
    from copy import deepcopy

    current = deepcopy(plan)
    changed = False
    rigid_sheets = []
    for sheet in current.get("sheets") or []:
        sheet_no = int(sheet.get("sheet_no") or 0)
        count = sum(
            1
            for group in extract_placement_groups({"sheets": [sheet]})
            if group.kind != STANDALONE
        )
        if count >= 2:
            rigid_sheets.append(sheet_no)
    for sheet_no in rigid_sheets[:_MAX_REPACK_SHEETS]:
        if time.monotonic() > deadline:
            break
        if _repack_sheet(current, sheet_no, board_w_cm, board_h_cm, kerf_cm, deadline):
            changed = True
    if not changed:
        return None
    if not _same_nests(current, prototypes):
        return None
    return current


def _repack_sheet(
    plan: dict[str, Any],
    sheet_no: int,
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    deadline: float,
) -> bool:
    from copy import deepcopy

    sheet = next(
        (item for item in plan.get("sheets") or [] if int(item.get("sheet_no") or 0) == sheet_no),
        None,
    )
    if sheet is None:
        return False
    groups = [
        group
        for group in extract_placement_groups({"sheets": [sheet]})
        if group.kind != STANDALONE
    ]
    if len(groups) < 2 or len(groups) > _MAX_LIVE_GROUPS:
        return False
    before = _bbox_area(sheet.get("pieces") or [])
    saved = [dict(piece) for piece in sheet.get("pieces") or []]
    rigid_ids = {piece_id for group in groups for piece_id in group.piece_ids}
    sheet["pieces"] = [piece for piece in saved if int(piece["id"]) not in rigid_ids]
    failed: set[tuple[Any, ...]] = set()
    placed = True
    for group in sorted(groups, key=lambda item: item.area, reverse=True):
        if time.monotonic() > deadline or not _seat_group(
            [sheet],
            group,
            kerf_cm,
            board_w_cm,
            board_h_cm,
            deadline,
            failed,
        ):
            placed = False
            break
    if not placed or _bbox_area(sheet.get("pieces") or []) >= before - 1.0:
        sheet["pieces"] = saved
        return False
    sheet["pieces"] = [deepcopy(piece) for piece in sheet.get("pieces") or []]
    return True


def _seat_group(
    sheets: list[dict[str, Any]],
    group: NestingPlacementGroup,
    kerf_cm: float,
    board_w_cm: float,
    board_h_cm: float,
    deadline: float,
    failed: set[tuple[Any, ...]],
    *,
    allow_repack: bool = True,
) -> bool:
    from .shape_aware_nesting import _translate_pieces

    if time.monotonic() > deadline:
        return False
    occupancy = tuple(
        (
            int(sheet.get("sheet_no") or 0),
            tuple(sorted(int(piece["id"]) for piece in sheet.get("pieces") or [])),
        )
        for sheet in sheets
    )
    key = (group.piece_ids, occupancy)
    if key in failed:
        return False
    found: tuple[tuple[Any, ...], dict[str, Any], float, float] | None = None
    constraint = _constraint(group.kind)
    for sheet in sheets:
        if time.monotonic() > deadline:
            break
        translated = best_rigid_translation(
            sheet,
            group.pieces,
            kerf_cm,
            board_w_cm,
            board_h_cm,
            constraint=constraint,
        )
        if translated is None:
            continue
        dx, dy, rank = translated
        used = 0 if sheet.get("pieces") else 1
        candidate = ((used, *rank), sheet, dx, dy)
        if found is None or candidate[0] < found[0]:
            found = candidate
    if found is None:
        if not allow_repack or not _repack_target(
            sheets,
            group,
            kerf_cm,
            board_w_cm,
            board_h_cm,
            deadline,
        ):
            failed.add(key)
            return False
        return True
    _rank, sheet, dx, dy = found
    sheet.setdefault("pieces", []).extend(_translate_pieces(group.pieces, dx, dy))
    return True


def _repack_target(
    sheets: list[dict[str, Any]],
    incoming: NestingPlacementGroup,
    kerf_cm: float,
    board_w_cm: float,
    board_h_cm: float,
    deadline: float,
) -> bool:
    """Clear rigid groups on one board so the incoming group can sit with them."""

    from .plan_search import _largest_free_area

    if time.monotonic() > deadline or not sheets:
        return False
    target = max(sheets, key=_largest_free_area)
    live = [
        group
        for group in extract_placement_groups({"sheets": [target]})
        if group.kind != STANDALONE
    ]
    if not live or len(live) > 4:
        return False
    saved = [dict(piece) for piece in target.get("pieces") or []]
    rigid_ids = {piece_id for group in live for piece_id in group.piece_ids}
    fixed = [piece for piece in saved if int(piece["id"]) not in rigid_ids]
    orders = (
        [incoming, *sorted(live, key=lambda group: group.area, reverse=True)],
        sorted([incoming, *live], key=lambda group: group.area, reverse=True),
    )
    for order in orders[:2]:
        if time.monotonic() > deadline:
            break
        target["pieces"] = [dict(piece) for piece in fixed]
        failed: set[tuple[Any, ...]] = set()
        if all(
            _seat_group(
                [target],
                group,
                kerf_cm,
                board_w_cm,
                board_h_cm,
                deadline,
                failed,
                allow_repack=False,
            )
            for group in order
        ):
            return True
    target["pieces"] = saved
    return False


def _orders(groups: Sequence[NestingPlacementGroup]) -> list[tuple[NestingPlacementGroup, ...]]:
    largest = tuple(sorted(groups, key=lambda group: group.area, reverse=True))
    orders = [largest]
    if 1 < len(groups) <= 3:
        for perm in permutations(groups):
            if perm in orders:
                continue
            orders.append(perm)
            if len(orders) >= _MAX_ORDERS:
                break
    elif len(groups) > 1:
        orders.append(tuple(reversed(largest)))
    return orders


def _next_victim(
    plan: Mapping[str, Any],
    groups: Sequence[NestingPlacementGroup],
    seen: set[tuple[int, tuple[int, ...]]],
) -> int | None:
    sheets = list(plan.get("sheets") or [])
    if len(sheets) < 2:
        return None
    ranked: list[tuple[tuple[int, int, int], int]] = []
    for sheet in sheets:
        sheet_no = int(sheet.get("sheet_no") or 0)
        owned = [group for group in groups if group.sheet_no == sheet_no]
        if not any(group.kind != STANDALONE for group in owned):
            continue
        identity = (sheet_no, tuple(sorted(piece_id for group in owned for piece_id in group.piece_ids)))
        if identity in seen:
            continue
        ranked.append(
            (
                (
                    sum(1 for group in owned if group.kind != STANDALONE),
                    len(sheet.get("pieces") or []),
                    -sheet_no,
                ),
                sheet_no,
            )
        )
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0])
    return ranked[0][1]


def _anchors(
    sheet: Mapping[str, Any],
    origin_x: float,
    origin_y: float,
    width: float,
    height: float,
    kerf_cm: float,
    board_w_cm: float,
    board_h_cm: float,
) -> list[tuple[float, float]]:
    from .plan_search import _free_rectangles

    seen: set[tuple[float, float]] = set()
    found: list[tuple[float, float]] = []

    def add(x_cm: float, y_cm: float) -> None:
        if x_cm < -1e-6 or y_cm < -1e-6:
            return
        if x_cm + width > board_w_cm + 1e-6 or y_cm + height > board_h_cm + 1e-6:
            return
        key = (round(x_cm, 2), round(y_cm, 2))
        if key in seen:
            return
        seen.add(key)
        found.append((float(key[0]), float(key[1])))

    add(origin_x, origin_y)
    add(0.0, 0.0)
    add(max(0.0, board_w_cm - width), 0.0)
    add(0.0, max(0.0, board_h_cm - height))
    boxes = []
    for piece in list(sheet.get("pieces") or [])[:16]:
        x_cm = num(piece.get("x"))
        y_cm = num(piece.get("y"))
        box_w = num(piece.get("w"))
        box_h = num(piece.get("h"))
        boxes.append((x_cm, y_cm, box_w, box_h))
        add(x_cm + box_w + kerf_cm, y_cm)
        add(x_cm, y_cm + box_h + kerf_cm)
        add(0.0, y_cm)
        add(x_cm, 0.0)
        add(0.0, y_cm + box_h + kerf_cm)
        add(x_cm + box_w + kerf_cm, 0.0)
    for (left_x, left_y, left_w, left_h), (right_x, right_y, right_w, right_h) in combinations(boxes[:6], 2):
        add(left_x + left_w + kerf_cm, right_y + right_h + kerf_cm)
        add(right_x + right_w + kerf_cm, left_y + left_h + kerf_cm)
    for rect in _free_rectangles({"w": board_w_cm, "h": board_h_cm, "pieces": sheet.get("pieces") or []})[:8]:
        add(rect["x"], rect["y"])
        if rect["w"] + 1e-6 >= width and rect["h"] + 1e-6 >= height:
            add(rect["x"] + rect["w"] - width, rect["y"])
            add(rect["x"], rect["y"] + rect["h"] - height)
            add(rect["x"] + rect["w"] - width, rect["y"] + rect["h"] - height)
    forced = [(origin_x, origin_y), (0.0, 0.0)]
    rest = [anchor for anchor in found if anchor not in forced]
    rest.sort(key=lambda anchor: (_nearest_gap(anchor, width, height, boxes), anchor[1], anchor[0]))
    ordered = []
    for anchor in [*forced, *rest]:
        key = (round(anchor[0], 2), round(anchor[1], 2))
        if key in {(round(item[0], 2), round(item[1], 2)) for item in ordered}:
            continue
        if anchor[0] < -1e-6 or anchor[1] < -1e-6:
            continue
        if anchor[0] + width > board_w_cm + 1e-6 or anchor[1] + height > board_h_cm + 1e-6:
            continue
        ordered.append(anchor)
        if len(ordered) >= _MAX_ANCHORS:
            break
    return ordered


def _pack_rank(
    sheet: Mapping[str, Any],
    moved: Sequence[Mapping[str, Any]],
    anchor_x: float,
    anchor_y: float,
    width: float,
    height: float,
    kerf_cm: float,
    dx: float,
    dy: float,
) -> tuple[Any, ...]:
    existing = list(sheet.get("pieces") or [])
    union = _bbox_area([*existing, *moved])
    below = 1
    beside = 1
    for piece in existing:
        x_cm = num(piece.get("x"))
        y_cm = num(piece.get("y"))
        box_w = num(piece.get("w"))
        box_h = num(piece.get("h"))
        vertical_overlap = min(anchor_y + height, y_cm + box_h) - max(anchor_y, y_cm)
        horizontal_overlap = min(anchor_x + width, x_cm + box_w) - max(anchor_x, x_cm)
        if abs((y_cm + box_h + kerf_cm) - anchor_y) <= 0.08 and horizontal_overlap > 1.0:
            below = 0
        if abs((x_cm + box_w + kerf_cm) - anchor_x) <= 0.08 and vertical_overlap > 1.0:
            beside = 0
    return (round(union, 2), below, beside, round(anchor_y, 2), round(anchor_x, 2), round(abs(dx) + abs(dy), 2))


def _with_remnant(
    ranked: Sequence[tuple[tuple[Any, ...], float, float]],
    sheet: Mapping[str, Any],
    pieces: Sequence[Mapping[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
) -> tuple[tuple[Any, ...], float, float]:
    from .plan_search import _largest_free_area
    from .shape_aware_nesting import _translate_pieces

    best: tuple[tuple[Any, ...], float, float] | None = None
    for rank, dx, dy in ranked:
        moved = _translate_pieces(pieces, dx, dy)
        trial = {
            "w": board_w_cm,
            "h": board_h_cm,
            "pieces": [*(sheet.get("pieces") or []), *moved],
        }
        remnant = _largest_free_area(trial)
        full = (rank[0], -round(remnant, 2), *rank[1:])
        if best is None or full < best[0]:
            best = (full, dx, dy)
    assert best is not None
    return best


def _build_group(
    kind: str,
    members: Sequence[Mapping[str, Any]],
    located: Mapping[int, tuple[int, dict[str, Any]]],
    assigned: set[int],
) -> NestingPlacementGroup | None:
    unique: list[dict[str, Any]] = []
    seen: set[int] = set()
    sheet_no = None
    for piece in members:
        try:
            piece_id = int(piece["id"])
        except (TypeError, ValueError, KeyError):
            return None
        if piece_id in seen:
            continue
        found = located.get(piece_id)
        if found is None:
            return None
        if sheet_no is None:
            sheet_no = found[0]
        elif sheet_no != found[0]:
            return None
        seen.add(piece_id)
        unique.append(dict(piece))
    if not unique or sheet_no is None:
        return None
    if any(piece_id in assigned for piece_id in seen):
        return None
    origin_x, origin_y = _origin(unique)
    corner_ids = {
        int(piece["id"])
        for piece in unique
        if str(piece.get("piece_type") or "") in _CORNER_TYPES
    }
    guest_ids = tuple(sorted(piece_id for piece_id in seen if piece_id not in corner_ids))
    if kind == GLASS_HOST:
        guest_ids = tuple(
            sorted(
                int(piece["id"])
                for piece in unique
                if piece.get("glass_host_piece_id") not in (None, "")
            )
        )
    links = []
    for piece in unique:
        host = piece.get("glass_host_piece_id")
        if host in (None, ""):
            continue
        try:
            links.append((int(piece["id"]), int(host)))
        except (TypeError, ValueError):
            return None
    assigned.update(seen)
    return NestingPlacementGroup(
        kind=kind,
        piece_ids=tuple(sorted(seen)),
        sheet_no=sheet_no,
        origin_x=origin_x,
        origin_y=origin_y,
        pieces=tuple(unique),
        relative_offsets=tuple(
            (
                int(piece["id"]),
                round(num(piece.get("x")) - origin_x, 4),
                round(num(piece.get("y")) - origin_y, 4),
            )
            for piece in sorted(unique, key=lambda item: int(item["id"]))
        ),
        orientations=tuple(
            (
                int(piece["id"]),
                int(piece.get("corner_rotation_quarter_turns") or 0),
                bool(
                    piece.get("mirrored")
                    or piece.get("corner_mirrored")
                    or piece.get("placement_mirrored")
                ),
                round(float(piece.get("placement_rotation_deg") or 0), 4),
                bool(piece.get("rotated")),
            )
            for piece in sorted(unique, key=lambda item: int(item["id"]))
        ),
        glass_links=tuple(sorted(links)),
        guest_ids=guest_ids,
        voids=_stored_voids(kind, unique),
    )


def _stored_voids(kind: str, pieces: Sequence[Mapping[str, Any]]) -> tuple[tuple[float, float, float, float], ...]:
    from .shape_aware_nesting import _voids_for_block

    block_kind = ""
    if kind in {L_QUAD, CLIPPED_QUAD}:
        block_kind = "quad"
    elif kind in {L_PAIR, CLIPPED_PAIR}:
        block_kind = "pair"
    elif kind == SINGLE_CORNER:
        block_kind = "single"
    if not block_kind:
        return ()
    voids = []
    for void in _voids_for_block(pieces, block_kind, 0.0):
        voids.append((float(void["x"]), float(void["y"]), float(void["w"]), float(void["h"])))
    return tuple(voids)


def _glass_members(
    located: Mapping[int, tuple[int, dict[str, Any]]],
) -> list[list[dict[str, Any]]]:
    children: dict[int, list[dict[str, Any]]] = defaultdict(list)
    pieces = {piece_id: piece for piece_id, (_sheet_no, piece) in located.items()}
    for piece_id, piece in pieces.items():
        host = piece.get("glass_host_piece_id")
        if host in (None, ""):
            continue
        try:
            children[int(host)].append(piece)
        except (TypeError, ValueError):
            continue
    roots: set[int] = set()
    for host_id in children:
        cursor = host_id
        seen: set[int] = set()
        while cursor not in seen:
            seen.add(cursor)
            piece = pieces.get(cursor)
            if piece is None:
                break
            parent = piece.get("glass_host_piece_id")
            if parent in (None, ""):
                break
            try:
                parent_id = int(parent)
            except (TypeError, ValueError):
                break
            if parent_id not in pieces:
                break
            cursor = parent_id
        if cursor in pieces:
            roots.add(cursor)
    grouped = []
    for root_id in sorted(roots):
        members: list[dict[str, Any]] = []
        stack = [root_id]
        seen_ids: set[int] = set()
        while stack:
            current = stack.pop()
            if current in seen_ids:
                continue
            seen_ids.add(current)
            piece = pieces.get(current)
            if piece is not None:
                members.append(piece)
            for child in children.get(current, []):
                try:
                    stack.append(int(child["id"]))
                except (TypeError, ValueError, KeyError):
                    continue
        sheets = {located[int(piece["id"])][0] for piece in members if int(piece["id"]) in located}
        if len(members) >= 2 and len(sheets) == 1:
            grouped.append(members)
    return grouped


def _diagnostic_members(
    plan: Mapping[str, Any],
    located: Mapping[int, tuple[int, dict[str, Any]]],
    assigned: set[int],
) -> list[list[dict[str, Any]]]:
    diagnostics = plan.get("shape_nesting_diagnostics") or {}
    grouped = []
    for raw in diagnostics.get("formation_ids") or []:
        members = []
        sheets: set[int] = set()
        valid = True
        for raw_id in raw:
            try:
                piece_id = int(raw_id)
            except (TypeError, ValueError):
                valid = False
                break
            if piece_id in assigned or piece_id not in located:
                valid = False
                break
            sheet_no, piece = located[piece_id]
            sheets.add(sheet_no)
            members.append(piece)
        if not valid or len(sheets) != 1 or len(members) < 2:
            continue
        extras = _absorb_inside(members, located, next(iter(sheets)), assigned)
        grouped.append([*members, *extras])
    return grouped


def _split_corners(corners: Sequence[Mapping[str, Any]]) -> list[list[dict[str, Any]]]:
    from .shape_aware_nesting import _recorded_facing, _slot_pair_geometry

    remaining = [dict(piece) for piece in corners]
    if len(remaining) > 12:
        remaining.sort(key=lambda piece: int(piece["id"]))
        remaining = remaining[:12]
    components = _touching_components(remaining)
    grouped: list[list[dict[str, Any]]] = []
    for component in components:
        pool = list(component)
        for quad in _quads(pool, _recorded_facing):
            grouped.append(quad)
            quad_ids = {int(piece["id"]) for piece in quad}
            pool = [piece for piece in pool if int(piece["id"]) not in quad_ids]
        used: set[int] = set()
        candidates = []
        for first, second in combinations(pool, 2):
            if _recorded_facing(first) == _recorded_facing(second):
                continue
            gap = _box_gap(first, second)
            if gap < -1e-6 or gap > 1.0:
                continue
            if not _slot_pair_geometry(first, second, gap):
                continue
            candidates.append((gap, int(first["id"]), int(second["id"]), first, second))
        candidates.sort(key=lambda item: (item[0], item[1], item[2]))
        for _gap, first_id, second_id, first, second in candidates:
            if first_id in used or second_id in used:
                continue
            used.add(first_id)
            used.add(second_id)
            grouped.append([first, second])
        for piece in pool:
            if int(piece["id"]) in used:
                continue
            grouped.append([piece])
    return grouped


def _quads(
    pieces: Sequence[Mapping[str, Any]],
    recorded_facing: Any,
) -> list[list[dict[str, Any]]]:
    if len(pieces) < 4 or len(pieces) > 8:
        return []
    found = []
    used: set[int] = set()
    for combo in combinations(pieces, 4):
        ids = [int(piece["id"]) for piece in combo]
        if any(piece_id in used for piece_id in ids):
            continue
        facings = {recorded_facing(piece) for piece in combo}
        if len(facings) != 4 or "" in facings:
            continue
        width = max(num(piece.get("w")) for piece in combo)
        height = max(num(piece.get("h")) for piece in combo)
        min_x, min_y, max_x, max_y = _bounds(combo)
        if max_x - min_x > width * 2 + 1.2 or max_y - min_y > height * 2 + 1.2:
            continue
        found.append(list(combo))
        used.update(ids)
    return found


def _touching_components(pieces: Sequence[Mapping[str, Any]]) -> list[list[dict[str, Any]]]:
    parent = {int(piece["id"]): int(piece["id"]) for piece in pieces}

    def find(piece_id: int) -> int:
        while parent[piece_id] != piece_id:
            parent[piece_id] = parent[parent[piece_id]]
            piece_id = parent[piece_id]
        return piece_id

    for first, second in combinations(pieces, 2):
        if _box_gap(first, second) > 0.8:
            continue
        left = find(int(first["id"]))
        right = find(int(second["id"]))
        parent[right] = left
    buckets: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for piece in pieces:
        buckets[find(int(piece["id"]))].append(piece)
    return list(buckets.values())


def _absorb_inside(
    members: Sequence[Mapping[str, Any]],
    located: Mapping[int, tuple[int, dict[str, Any]]],
    sheet_no: int,
    assigned: set[int],
) -> list[dict[str, Any]]:
    min_x, min_y, max_x, max_y = _bounds(members)
    span = max((max_x - min_x) * (max_y - min_y), 0.0)
    member_ids = {int(piece["id"]) for piece in members}
    extras = []
    for piece_id, (found_sheet, piece) in located.items():
        if found_sheet != sheet_no or piece_id in assigned or piece_id in member_ids:
            continue
        if piece.get("glass_host_piece_id") not in (None, ""):
            continue
        center_x = num(piece.get("x")) + num(piece.get("w")) / 2
        center_y = num(piece.get("y")) + num(piece.get("h")) / 2
        if not (min_x + 1e-6 < center_x < max_x - 1e-6 and min_y + 1e-6 < center_y < max_y - 1e-6):
            continue
        if num(piece.get("w")) * num(piece.get("h")) >= span * 0.5:
            continue
        extras.append(piece)
    return extras


def _kind_for(pieces: Sequence[Mapping[str, Any]]) -> str:
    kinds = [str(piece.get("piece_type") or "") for piece in pieces]
    for piece_type, exact, label in (
        ("L-Shaped Corner", 4, L_QUAD),
        ("Clipped Corner", 4, CLIPPED_QUAD),
        ("L-Shaped Corner", 2, L_PAIR),
        ("Clipped Corner", 2, CLIPPED_PAIR),
        ("L-Shaped Corner", 1, SINGLE_CORNER),
        ("Clipped Corner", 1, SINGLE_CORNER),
    ):
        if kinds.count(piece_type) == exact:
            return label
    if kinds.count("L-Shaped Corner") > 4 and kinds.count("Clipped Corner") == 0:
        return L_QUAD
    if kinds.count("Clipped Corner") > 4 and kinds.count("L-Shaped Corner") == 0:
        return CLIPPED_QUAD
    return STANDALONE


def _constraint(kind: str) -> str:
    if kind in {L_PAIR, CLIPPED_PAIR}:
        return "pair"
    if kind == SINGLE_CORNER:
        return "single"
    return ""


def _joins_existing_pair(
    piece: Mapping[str, Any],
    others: Sequence[Mapping[str, Any]],
    kerf_cm: float,
) -> bool:
    """A single corner must not become a second pair just by where it sits."""

    from .shape_aware_nesting import _recorded_facing, _slot_pair_geometry

    if str(piece.get("piece_type") or "") not in _CORNER_TYPES:
        return False
    for other in others:
        if str(other.get("piece_type") or "") != str(piece.get("piece_type") or ""):
            continue
        if _recorded_facing(piece) == _recorded_facing(other):
            continue
        if _slot_pair_geometry(piece, other, kerf_cm):
            return True
    return False


def _opening_pieces(pieces: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    corners = [
        piece
        for piece in pieces
        if str(piece.get("piece_type") or "") in _CORNER_TYPES
        and piece.get("glass_host_piece_id") in (None, "")
    ]
    if corners:
        return corners
    return list(pieces)


def _same_nests(plan: Mapping[str, Any], prototypes: Sequence[NestingPlacementGroup]) -> bool:
    live = _live_signatures(plan, prototypes)
    original = _prototype_signatures(prototypes)
    return live is not None and live == original


def _prototype_signatures(prototypes: Sequence[NestingPlacementGroup]) -> tuple[Any, ...]:
    rows = []
    for group in prototypes:
        if group.kind == STANDALONE:
            continue
        rows.append(_relative_signature(group.kind, group.pieces))
    return tuple(sorted(rows, key=lambda item: item[1][0][0] if item[1] else 0))


def _live_signatures(
    plan: Mapping[str, Any],
    prototypes: Sequence[NestingPlacementGroup],
) -> tuple[Any, ...] | None:
    located = _locate(plan)
    rows = []
    for group in prototypes:
        if group.kind == STANDALONE:
            continue
        found = []
        sheets: set[int] = set()
        for piece_id in group.piece_ids:
            hit = located.get(piece_id)
            if hit is None:
                return None
            sheets.add(hit[0])
            found.append(hit[1])
        if len(sheets) != 1:
            return None
        rows.append(_relative_signature(group.kind, found))
    return tuple(sorted(rows, key=lambda item: item[1][0][0] if item[1] else 0))


def _relative_signature(kind: str, pieces: Sequence[Mapping[str, Any]]) -> tuple[Any, ...]:
    origin_x, origin_y = _origin(pieces)
    rows = []
    for piece in sorted(pieces, key=lambda item: int(item["id"])):
        outline = material_outline_cm(piece)
        relative = ()
        if outline is not None:
            relative = tuple(
                (round(point[0] - origin_x, 2), round(point[1] - origin_y, 2))
                for point in outline
            )
        host = piece.get("glass_host_piece_id")
        try:
            host_id = None if host in (None, "") else int(host)
        except (TypeError, ValueError):
            host_id = None
        hole = piece.get("glass_hole_local_mm")
        hole_key: tuple[tuple[float, float], ...] = ()
        if isinstance(hole, (list, tuple)):
            hole_key = tuple(
                (round(float(point[0]), 1), round(float(point[1]), 1))
                for point in hole
                if isinstance(point, (list, tuple)) and len(point) >= 2
            )
        rows.append(
            (
                int(piece["id"]),
                round(num(piece.get("x")) - origin_x, 2),
                round(num(piece.get("y")) - origin_y, 2),
                round(num(piece.get("w")), 2),
                round(num(piece.get("h")), 2),
                int(piece.get("corner_rotation_quarter_turns") or 0),
                bool(
                    piece.get("mirrored")
                    or piece.get("corner_mirrored")
                    or piece.get("placement_mirrored")
                ),
                round(float(piece.get("placement_rotation_deg") or 0), 2),
                bool(piece.get("rotated")),
                host_id,
                hole_key,
                relative,
            )
        )
    return (kind, tuple(rows))


def _geometry_ok(
    plan: dict[str, Any],
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    *,
    mirroring_allowed: bool,
    deadline: float,
) -> bool:
    from .evaluation import placement_permission_errors, validate_plan

    expected = {int(piece["id"]) for piece in pieces}
    placed = {
        int(piece["id"])
        for sheet in plan.get("sheets") or []
        for piece in sheet.get("pieces") or []
    }
    if placed != expected or plan.get("unplaced"):
        return False
    if validate_plan(
        plan,
        pieces,
        board_w_cm,
        board_h_cm,
        kerf_cm=kerf_cm,
        deadline_monotonic=deadline,
    ):
        return False
    if placement_permission_errors(plan, pieces, mirroring_allowed=mirroring_allowed):
        return False
    return True


def _tighter(candidate: Mapping[str, Any], baseline: Mapping[str, Any]) -> bool:
    return _spread(candidate) + 1.0 < _spread(baseline)


def _spread(plan: Mapping[str, Any]) -> float:
    return sum(_bbox_area(sheet.get("pieces") or []) for sheet in plan.get("sheets") or [])


def _replace_sheets(plan: Mapping[str, Any], sheets: list[dict[str, Any]]) -> dict[str, Any]:
    from copy import deepcopy

    copied = deepcopy(plan)
    copied["sheets"] = sheets
    copied["unplaced"] = list(plan.get("unplaced") or [])
    return copied


def _locate(plan: Mapping[str, Any]) -> dict[int, tuple[int, dict[str, Any]]]:
    located: dict[int, tuple[int, dict[str, Any]]] = {}
    for sheet in plan.get("sheets") or []:
        try:
            sheet_no = int(sheet.get("sheet_no") or 0)
        except (TypeError, ValueError):
            continue
        for piece in sheet.get("pieces") or []:
            try:
                piece_id = int(piece["id"])
            except (TypeError, ValueError, KeyError):
                continue
            located[piece_id] = (sheet_no, piece)
    return located


def _corner_nest(piece: Mapping[str, Any], records_shape_nest: Any) -> bool:
    return str(piece.get("piece_type") or "") in _CORNER_TYPES and bool(records_shape_nest(piece))


def _origin(pieces: Sequence[Mapping[str, Any]]) -> tuple[float, float]:
    min_x = min(num(piece.get("x")) for piece in pieces)
    min_y = min(num(piece.get("y")) for piece in pieces)
    for piece in pieces:
        outline = piece.get("placement_outline_cm")
        if not isinstance(outline, (list, tuple)):
            continue
        for point in outline:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                min_x = min(min_x, float(point[0]))
                min_y = min(min_y, float(point[1]))
    return min_x, min_y


def _bounds(pieces: Sequence[Mapping[str, Any]]) -> tuple[float, float, float, float]:
    min_x = min(num(piece.get("x")) for piece in pieces)
    min_y = min(num(piece.get("y")) for piece in pieces)
    max_x = max(num(piece.get("x")) + num(piece.get("w")) for piece in pieces)
    max_y = max(num(piece.get("y")) + num(piece.get("h")) for piece in pieces)
    return min_x, min_y, max_x, max_y


def _bbox_area(pieces: Sequence[Mapping[str, Any]]) -> float:
    if not pieces:
        return 0.0
    min_x, min_y, max_x, max_y = _bounds(pieces)
    return max(0.0, max_x - min_x) * max(0.0, max_y - min_y)


def _box_gap(first: Mapping[str, Any], second: Mapping[str, Any]) -> float:
    gap_x = max(
        num(first.get("x")) - (num(second.get("x")) + num(second.get("w"))),
        num(second.get("x")) - (num(first.get("x")) + num(first.get("w"))),
    )
    gap_y = max(
        num(first.get("y")) - (num(second.get("y")) + num(second.get("h"))),
        num(second.get("y")) - (num(first.get("y")) + num(first.get("h"))),
    )
    if gap_x > 0 and gap_y > 0:
        return (gap_x**2 + gap_y**2) ** 0.5
    return max(gap_x, gap_y, 0.0)


def _nearest_gap(
    anchor: tuple[float, float],
    width: float,
    height: float,
    boxes: Sequence[tuple[float, float, float, float]],
) -> float:
    if not boxes:
        return anchor[0] + anchor[1]
    best = None
    for x_cm, y_cm, box_w, box_h in boxes:
        gap_x = max(anchor[0] - (x_cm + box_w), x_cm - (anchor[0] + width))
        gap_y = max(anchor[1] - (y_cm + box_h), y_cm - (anchor[1] + height))
        if gap_x > 0 and gap_y > 0:
            gap = (gap_x**2 + gap_y**2) ** 0.5
        else:
            gap = max(gap_x, gap_y, 0.0)
        if best is None or gap < best:
            best = gap
    return 0.0 if best is None else best


def _outline_inside(
    outline: Sequence[tuple[float, float]],
    board_w_cm: float,
    board_h_cm: float,
) -> bool:
    return all(
        -1e-6 <= point[0] <= board_w_cm + 1e-6 and -1e-6 <= point[1] <= board_h_cm + 1e-6
        for point in outline
    )


def _outlines_clear(
    outlines: Sequence[Sequence[tuple[float, float]]],
    occupied: Sequence[Sequence[tuple[float, float]]],
    kerf_cm: float,
) -> bool:
    for outline in outlines:
        outline_box = _point_box(outline)
        for other in occupied:
            other_box = _point_box(other)
            if _separated(outline_box, other_box) + 1e-6 >= kerf_cm:
                continue
            if polygons_overlap(outline, other):
                return False
            if polygon_distance(outline, other) + 1e-6 < kerf_cm:
                return False
    return True


def _point_box(outline: Sequence[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [point[0] for point in outline]
    ys = [point[1] for point in outline]
    return min(xs), min(ys), max(xs), max(ys)


def _separated(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    gap_x = max(first[0] - second[2], second[0] - first[2])
    gap_y = max(first[1] - second[3], second[1] - first[3])
    if gap_x > 0 and gap_y > 0:
        return (gap_x**2 + gap_y**2) ** 0.5
    if gap_x > 0:
        return gap_x
    if gap_y > 0:
        return gap_y
    return 0.0


__all__ = [
    "CLIPPED_PAIR",
    "CLIPPED_QUAD",
    "GLASS_HOST",
    "L_PAIR",
    "L_QUAD",
    "SINGLE_CORNER",
    "STANDALONE",
    "NestingPlacementGroup",
    "best_rigid_translation",
    "consolidate_nested_boards",
    "extract_placement_groups",
    "translation_anchors",
]
