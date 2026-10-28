"""Place complementary L and clipped-corner outlines after the base pack.

MaxRects, Guillotine, Shelf, and Skyline stay the packing engines. A nest is
kept when the outlines clear each other, stay on the board, and respect kerf,
rotation, and mirroring. Fewer boards, a larger remnant, and a better
``industrial_rank`` are not required. Those values only break a tie between
nests that already place the same pieces in voids.

Identical corners are grouped by type and cut size, then split into fours,
one pair, and a single. A pair is two adjacent cells of the current quad:
opposite notch facings, one kerf between the boxes, and the shared opening
toward the board interior. Same-facing adjacency is not a pair. A different
piece may sit in the void as a guest. It is not paired with the host. One
non-quarter angle is stored, and only for a rectangle sitting in the void of
four clipped corners.
"""

from __future__ import annotations

import math
import time
from itertools import combinations
from typing import Any, Mapping, Sequence

from .dxf_geometry import point_in_polygon, polygon_distance, polygons_overlap
from .glass_opening_nesting import material_outline_cm
from .primitives import make_placed_piece, num

_CORNER_TYPES = frozenset({"Clipped Corner", "L-Shaped Corner"})
_TURN = {
    "Top Left": "Top Right",
    "Top Right": "Bottom Right",
    "Bottom Right": "Bottom Left",
    "Bottom Left": "Top Left",
}
_MIRROR = {
    "Top Left": "Top Right",
    "Top Right": "Top Left",
    "Bottom Left": "Bottom Right",
    "Bottom Right": "Bottom Left",
}
# Column, row in a 2×2 cluster whose missing corner faces the centre.
_SLOTS = (
    ("Bottom Right", 0, 0),
    ("Bottom Left", 1, 0),
    ("Top Right", 0, 1),
    ("Top Left", 1, 1),
)
_MAX_QUAD_TRIALS = 8
_MAX_GUEST_ORDERS = 6
_MAX_VOID_SPOTS = 24
_NEST_BUDGET_FRACTION = 0.25


def void_edge_angle_deg(cut_width_cm: float, cut_length_cm: float) -> float | None:
    """Angle of a clipped-corner void edge, measured from the width axis."""

    if cut_width_cm <= 0 or cut_length_cm <= 0:
        return None
    return math.degrees(math.atan2(cut_length_cm, cut_width_cm)) % 360.0


def non_quarter_rotation_is_admitted(
    rotation_deg: float,
    *,
    cut_width_cm: float,
    cut_length_cm: float,
    outline_inside_void: bool,
    tolerance_deg: float = 0.05,
) -> bool:
    """Allow one computed angle, and only together with a proven void.

    A DXF angle is not admitted merely because the file contains it. Quarter
    turns are outside this exception.
    """

    if not outline_inside_void:
        return False
    expected = void_edge_angle_deg(cut_width_cm, cut_length_cm)
    if expected is None:
        return False
    if abs(rotation_deg % 90.0) <= tolerance_deg:
        return False
    return _angle_close(rotation_deg, expected, tolerance_deg) or _angle_close(
        rotation_deg, expected + 180.0, tolerance_deg
    )


def apply_shape_aware_nesting(
    plan: dict[str, Any],
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    *,
    mirroring_allowed: bool,
    machine_type: str,
    time_limit_sec: float,
    min_remnant_width_cm: float,
    min_remnant_length_cm: float,
    min_remnant_area_m2: float,
) -> dict[str, Any]:
    """Return a valid nest, or the same plan object when none is proven.

    Geometric clearance accepts the nest. ``industrial_rank`` only ranks two
    nests that already keep the same complements and the same void guests.
    """

    if machine_type == "Panel Saw" or time_limit_sec <= 0 or plan.get("unplaced"):
        return plan
    if not plan.get("sheets"):
        return plan
    deadline = time.monotonic() + max(
        0.05, min(float(time_limit_sec), float(time_limit_sec) * _NEST_BUDGET_FRACTION)
    )
    from .evaluation import placement_permission_errors, validate_plan
    from .optimizer import _candidate_is_better, enrich_plan_metrics
    from .plan_search import _spot_on_sheet

    reserved = _glass_hosted_ids(plan)
    eligible = [piece for piece in pieces if int(piece["id"]) not in reserved]
    partitions = _cluster_sheet(
        eligible,
        board_w_cm,
        board_h_cm,
        kerf_cm,
        mirroring_allowed=mirroring_allowed,
        deadline=deadline,
    )
    if not partitions:
        plan["shape_nesting_diagnostics"] = {
            "outcome": "kept_baseline",
            "reason": "no_corner_groups",
            "reserved_ids": sorted(reserved),
        }
        return plan
    metric_kwargs = {
        "min_remnant_width_cm": min_remnant_width_cm,
        "min_remnant_length_cm": min_remnant_length_cm,
        "min_remnant_area_m2": min_remnant_area_m2,
    }
    method = str(plan.get("method_key") or "MaxRects Best Short Side")
    best: dict[str, Any] | None = None
    best_key: tuple[Any, ...] | None = None
    for blocks in partitions:
        if time.monotonic() > deadline:
            break
        candidate, seated, dropped = _retain_shape_blocks(
            plan,
            pieces,
            blocks,
            board_w_cm,
            board_h_cm,
            kerf_cm,
            mirroring_allowed=mirroring_allowed,
            hosted=reserved,
            spot_on_sheet=_spot_on_sheet,
            validate_plan=validate_plan,
            placement_permission_errors=placement_permission_errors,
            deadline=deadline,
        )
        if candidate is None or _placement_signature(candidate) == _placement_signature(plan):
            continue
        enriched = enrich_plan_metrics(candidate, method, machine_type, **metric_kwargs)
        key = _nest_choice_key(enriched, seated)
        if best is None or key > best_key or (
            key == best_key and _candidate_is_better(enriched, best)
        ):
            for preserved in (
                "search_elapsed_sec",
                "search_time_limit_sec",
                "solver_status",
                "solver_wall_time_sec",
                "glass_nesting_diagnostics",
                "method_label",
                "optimization_mode",
                "ordering_strategy",
                "attempts",
                "complexity",
            ):
                if preserved in plan and preserved not in enriched:
                    enriched[preserved] = plan[preserved]
            enriched["shape_nesting_diagnostics"] = {
                "outcome": "accepted",
                "formations": [block["kind"] for block in seated],
                "formation_ids": [
                    [int(piece["id"]) for piece in block["pieces"]]
                    for block in seated
                    if block["kind"] in {"quad", "pair"}
                ],
                "void_guests": [
                    int(piece["id"])
                    for block in seated
                    for piece in block.get("guests") or []
                ],
                "reserved_ids": sorted(reserved),
                "dropped": dropped,
            }
            best = enriched
            best_key = key
    if best is None:
        plan["shape_nesting_diagnostics"] = {
            "outcome": "kept_baseline",
            "reason": "no_complete_valid_nest",
            "reserved_ids": sorted(reserved),
        }
        return plan
    return best


def _block_diagnostic(block: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {
        "kind": block["kind"],
        "ids": [int(piece["id"]) for piece in block["pieces"]],
        "reason": reason,
    }


def _shape_block_score(blocks: Sequence[Mapping[str, Any]]) -> int:
    return sum(
        len(block["pieces"])
        for block in blocks
        if block["kind"] in {"quad", "pair"}
    )


def _candidate_rejection(
    plan: Mapping[str, Any],
    pieces: list[dict[str, Any]],
    blocks: Sequence[Mapping[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    *,
    mirroring_allowed: bool,
    hosted: set[int],
    spot_on_sheet: Any,
    validate_plan: Any,
    placement_permission_errors: Any,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str]:
    """Return a complete plan, or the reason this block set cannot be kept."""

    seated = _seat_void_guests(
        blocks,
        pieces,
        kerf_cm,
        board_w_cm,
        board_h_cm,
        mirroring_allowed=mirroring_allowed,
        hosted=hosted,
    )
    candidate = _compose_plan(
        plan,
        pieces,
        seated,
        board_w_cm,
        board_h_cm,
        kerf_cm,
        spot_on_sheet,
    )
    if candidate is None:
        candidate = _fallback_plan(plan, pieces, seated, board_w_cm, board_h_cm, kerf_cm)
    if candidate is None:
        return None, seated, "compose_incomplete"
    if _glass_nest_links(plan) != _glass_nest_links(candidate):
        return None, seated, "glass_links"
    if validate_plan(candidate, pieces, board_w_cm, board_h_cm, kerf_cm=kerf_cm):
        return None, seated, "validation"
    if placement_permission_errors(
        candidate,
        pieces,
        mirroring_allowed=mirroring_allowed,
    ):
        return None, seated, "permissions"
    return candidate, seated, ""


def _retain_shape_blocks(
    plan: Mapping[str, Any],
    pieces: list[dict[str, Any]],
    blocks: Sequence[Mapping[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    *,
    mirroring_allowed: bool,
    hosted: set[int],
    spot_on_sheet: Any,
    validate_plan: Any,
    placement_permission_errors: Any,
    deadline: float,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep every block that still produces one complete valid plan.

    A block that breaks glass links, geometry, or placement permission is
    removed. Pieces from a removed block stay on the baseline. The returned
    plan still contains every piece once.
    """

    pending = [block for block in blocks]
    dropped: list[dict[str, Any]] = []
    while pending and time.monotonic() <= deadline:
        candidate, seated, reason = _candidate_rejection(
            plan,
            pieces,
            pending,
            board_w_cm,
            board_h_cm,
            kerf_cm,
            mirroring_allowed=mirroring_allowed,
            hosted=hosted,
            spot_on_sheet=spot_on_sheet,
            validate_plan=validate_plan,
            placement_permission_errors=placement_permission_errors,
        )
        if candidate is not None:
            return candidate, seated, dropped
        if len(pending) == 1:
            dropped.append(_block_diagnostic(pending[0], reason))
            return None, [], dropped
        rescued: tuple[int, dict[str, Any], list[dict[str, Any]], Mapping[str, Any]] | None = None
        for index in range(len(pending)):
            if time.monotonic() > deadline:
                break
            trial = pending[:index] + pending[index + 1 :]
            candidate, seated, _ignored = _candidate_rejection(
                plan,
                pieces,
                trial,
                board_w_cm,
                board_h_cm,
                kerf_cm,
                mirroring_allowed=mirroring_allowed,
                hosted=hosted,
                spot_on_sheet=spot_on_sheet,
                validate_plan=validate_plan,
                placement_permission_errors=placement_permission_errors,
            )
            if candidate is None:
                continue
            score = _shape_block_score(trial)
            if rescued is None or score > rescued[0]:
                rescued = (score, candidate, seated, pending[index])
        if rescued is not None:
            dropped.append(_block_diagnostic(rescued[3], reason))
            return rescued[1], rescued[2], dropped
        dropped.append(_block_diagnostic(pending[-1], reason))
        pending = pending[:-1]
    return None, [], dropped


def _cluster_sheet(
    pieces: Sequence[Mapping[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    *,
    mirroring_allowed: bool,
    deadline: float | None = None,
) -> list[list[dict[str, Any]]]:
    """Return a few partitions of proven quad, pair, and single blocks."""

    groups = _identical_groups(pieces)
    if not groups:
        return []
    orders = _group_orders(groups)
    partitions: list[list[dict[str, Any]]] = []
    seen: set[tuple[Any, ...]] = set()
    for order in orders:
        if deadline is not None and time.monotonic() > deadline:
            break
        blocks: list[dict[str, Any]] = []
        for group in order:
            blocks.extend(
                _partition_group(
                    group,
                    board_w_cm,
                    board_h_cm,
                    kerf_cm,
                    mirroring_allowed=mirroring_allowed,
                )
            )
        if not blocks:
            continue
        signature = tuple(
            sorted(
                (block["kind"], tuple(sorted(int(piece["id"]) for piece in block["pieces"])))
                for block in blocks
            )
        )
        if signature in seen:
            continue
        seen.add(signature)
        partitions.append(blocks)
        if len(partitions) >= 3:
            break
    return partitions


def _assign_cluster(
    pieces: Sequence[Mapping[str, Any]],
    kerf_cm: float,
    *,
    mirroring_allowed: bool,
) -> list[dict[str, Any]] | None:
    options = [_orientations(piece, mirroring_allowed) for piece in pieces]
    width = num(pieces[0].get("width_cm"))
    height = num(pieces[0].get("length_cm"))

    def _search(slot: int, unused: set[int]) -> list[dict[str, Any]] | None:
        if slot == 4:
            return []
        position, column, row = _SLOTS[slot]
        for index in sorted(unused):
            for mirrored, turns, facing, _cut_x, _cut_y in options[index]:
                if facing != position:
                    continue
                oriented_w, oriented_h = (height, width) if turns % 2 else (width, height)
                if abs(oriented_w - width) > 1e-6 or abs(oriented_h - height) > 1e-6:
                    continue
                placed = _placed_corner(
                    pieces[index],
                    x_cm=column * (width + kerf_cm),
                    y_cm=row * (height + kerf_cm),
                    mirrored=mirrored,
                    turns=turns,
                )
                unused.remove(index)
                rest = _search(slot + 1, unused)
                unused.add(index)
                if rest is not None:
                    return [placed, *rest]
        return None

    return _search(0, set(range(4)))


def _identical_groups(
    pieces: Sequence[Mapping[str, Any]],
) -> list[list[Mapping[str, Any]]]:
    """Group corners that can match after an allowed transform.

    Original corner side is not part of the key. Length, width, notch size,
    and piece type are. An L is never grouped with a clipped corner.
    """

    groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = {}
    for piece in pieces:
        kind = str(piece.get("piece_type") or "")
        if kind not in _CORNER_TYPES:
            continue
        key = (
            kind,
            round(num(piece.get("width_cm")), 4),
            round(num(piece.get("length_cm")), 4),
            round(num(piece.get("clipped_corner_width_cm")), 4),
            round(num(piece.get("clipped_corner_length_cm")), 4),
        )
        if key[1] <= 0 or key[2] <= 0 or key[3] <= 0 or key[4] <= 0:
            continue
        groups.setdefault(key, []).append(piece)
    ordered = list(groups.values())
    ordered.sort(key=lambda group: (-len(group), int(group[0]["id"])))
    return ordered


def _group_orders(
    groups: Sequence[Sequence[Mapping[str, Any]]],
) -> list[list[list[Mapping[str, Any]]]]:
    primary = [list(group) for group in groups]
    if not any(_group_varies(group) for group in groups):
        return [primary]
    reversed_groups = [
        list(reversed(group)) if _group_varies(group) else list(group) for group in groups
    ]
    rotated = []
    for group in groups:
        items = list(group)
        if _group_varies(group) and len(items) > 1:
            items = items[1:] + items[:1]
        rotated.append(items)
    return [primary, reversed_groups, rotated]


def _group_varies(group: Sequence[Mapping[str, Any]]) -> bool:
    rotations = {bool(int(piece.get("allow_rotation") or 0)) for piece in group}
    positions = {str(piece.get("clipped_corner_position") or "") for piece in group}
    return len(rotations) > 1 or len(positions) > 1


def _partition_group(
    group: Sequence[Mapping[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    *,
    mirroring_allowed: bool,
) -> list[dict[str, Any]]:
    """Split one identical group into fours, then a pair, then one single."""

    remaining = list(group)
    blocks: list[dict[str, Any]] = []
    quad_failed = False
    while len(remaining) >= 4:
        quad = _take_quad(
            remaining,
            board_w_cm,
            board_h_cm,
            kerf_cm,
            mirroring_allowed=mirroring_allowed,
        )
        if quad is None:
            quad_failed = True
            break
        blocks.append(quad["block"])
        chosen = quad["ids"]
        remaining = [piece for piece in remaining if int(piece["id"]) not in chosen]
    if quad_failed and len(remaining) >= 4:
        while len(remaining) >= 2:
            pair = _take_pair(
                remaining,
                board_w_cm,
                board_h_cm,
                kerf_cm,
                mirroring_allowed=mirroring_allowed,
            )
            if pair is None:
                break
            blocks.append(pair["block"])
            remaining = [piece for piece in remaining if int(piece["id"]) not in pair["ids"]]
    elif len(remaining) in (2, 3):
        pair = _take_pair(
            remaining,
            board_w_cm,
            board_h_cm,
            kerf_cm,
            mirroring_allowed=mirroring_allowed,
        )
        if pair is not None:
            blocks.append(pair["block"])
            remaining = [piece for piece in remaining if int(piece["id"]) not in pair["ids"]]
    if len(group) == 1 or len(remaining) == 1:
        for piece in remaining:
            single = _inward_single(
                piece,
                board_w_cm,
                board_h_cm,
                mirroring_allowed=mirroring_allowed,
            )
            if single is not None:
                blocks.append(single)
    return blocks


def _take_quad(
    pool: Sequence[Mapping[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    *,
    mirroring_allowed: bool,
) -> dict[str, Any] | None:
    ordered = sorted(
        pool,
        key=lambda piece: (
            -len(_orientations(piece, mirroring_allowed)),
            int(piece["id"]),
        ),
    )
    tried = 0
    for combo in combinations(ordered, 4):
        tried += 1
        if tried > _MAX_QUAD_TRIALS:
            break
        placed = _assign_cluster(combo, kerf_cm, mirroring_allowed=mirroring_allowed)
        if placed is None:
            continue
        if not _block_fits_board(placed, board_w_cm, board_h_cm):
            continue
        return {
            "ids": {int(piece["id"]) for piece in combo},
            "block": _make_block(placed, "quad", kerf_cm),
        }
    return None


def _take_pair(
    pool: Sequence[Mapping[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    *,
    mirroring_allowed: bool,
) -> dict[str, Any] | None:
    ordered = sorted(pool, key=lambda piece: int(piece["id"]))
    tried = 0
    for first, second in combinations(ordered, 2):
        tried += 1
        if tried > _MAX_QUAD_TRIALS:
            break
        placed = _complement_sheet(
            (first, second),
            board_w_cm,
            board_h_cm,
            kerf_cm,
            mirroring_allowed=mirroring_allowed,
        )
        if placed is None:
            continue
        return {
            "ids": {int(first["id"]), int(second["id"])},
            "block": _make_block(placed, "pair", kerf_cm),
        }
    return None


def _complement_sheet(
    pieces: Sequence[Mapping[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    *,
    mirroring_allowed: bool,
) -> list[dict[str, Any]] | None:
    """Place two identical corners on one edge of the current quad.

    The boxes stay apart by the kerf. Their notches face one another and the
    shared opening faces the board interior. A mirror is used when the order
    allows it. Otherwise only an allowed rotation may reach the same facing.
    Same-facing adjacency and a 180° turn that does not land on that edge are
    refused. A forbidden transform is never recorded.
    """

    if len(pieces) != 2:
        return None
    first, second = pieces
    options = (
        _orientations(first, mirroring_allowed),
        _orientations(second, mirroring_allowed),
    )
    if not options[0] or not options[1]:
        return None
    best: list[dict[str, Any]] | None = None
    best_key: tuple[int, float] | None = None
    for edge in _quad_edges():
        for placed in _edge_assignments(pieces, options, edge, kerf_cm, board_w_cm, board_h_cm):
            inward = _pair_inward_score(placed, board_w_cm, board_h_cm)
            if inward is None or inward <= 0:
                continue
            mirrors = sum(1 for piece in placed if piece.get("mirrored"))
            preference = 1 if mirroring_allowed and mirrors == 1 else 0
            key = (preference, inward)
            if best_key is None or key > best_key:
                best = placed
                best_key = key
    return best


def _quad_edges() -> list[tuple[tuple[str, int, int], tuple[str, int, int], int, int]]:
    """Adjacent ``_SLOTS`` cells and the direction their notches open."""

    edges = []
    slots = list(_SLOTS)
    for index, left in enumerate(slots):
        for right in slots[index + 1 :]:
            same_row = left[2] == right[2] and abs(left[1] - right[1]) == 1
            same_col = left[1] == right[1] and abs(left[2] - right[2]) == 1
            if same_row:
                edges.append((left, right, 0, 1 if left[2] == 0 else -1))
            elif same_col:
                edges.append((left, right, 1 if left[1] == 0 else -1, 0))
    return edges


def _edge_assignments(
    pieces: Sequence[Mapping[str, Any]],
    options: tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]],
    edge: tuple[tuple[str, int, int], tuple[str, int, int], int, int],
    kerf_cm: float,
    board_w_cm: float,
    board_h_cm: float,
) -> list[list[dict[str, Any]]]:
    left_slot, right_slot, open_x, open_y = edge
    found = []
    for first_index in (0, 1):
        second_index = 1 - first_index
        for left in _facings(options[first_index], left_slot[0]):
            for right in _facings(options[second_index], right_slot[0]):
                placed = _interlock_pair(
                    pieces[first_index],
                    pieces[second_index],
                    left,
                    right,
                    left_slot,
                    right_slot,
                    open_x,
                    open_y,
                    kerf_cm,
                    board_w_cm,
                    board_h_cm,
                )
                if placed is not None:
                    found.append(placed)
    return found


def _facings(
    options: Sequence[tuple[Any, ...]],
    facing: str,
) -> list[tuple[Any, ...]]:
    return [item for item in options if item[2] == facing]


def _interlock_pair(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
    left: tuple[Any, ...],
    right: tuple[Any, ...],
    left_slot: tuple[str, int, int],
    right_slot: tuple[str, int, int],
    open_x: int,
    open_y: int,
    kerf_cm: float,
    board_w_cm: float,
    board_h_cm: float,
) -> list[dict[str, Any]] | None:
    """Seat one quad edge. Bounding-box overlap is not acceptance."""

    if left[2] == right[2]:
        return None
    cell = _pair_cell(first, left)
    other_cell = _pair_cell(second, right)
    if cell is None or other_cell is None or cell != other_cell:
        return None
    width, height = cell
    anchor = _translate_pieces(
        [_placed_corner(first, x_cm=0.0, y_cm=0.0, mirrored=left[0], turns=left[1])],
        *_pair_offsets(left_slot, right_slot, width, height, kerf_cm)[0],
    )[0]
    other = _translate_pieces(
        [_placed_corner(second, x_cm=0.0, y_cm=0.0, mirrored=right[0], turns=right[1])],
        *_pair_offsets(left_slot, right_slot, width, height, kerf_cm)[1],
    )[0]
    span_w, span_h = _block_size((anchor, other))
    origin = _opening_origin(span_w, span_h, open_x, open_y, board_w_cm, board_h_cm)
    if origin is None:
        return None
    moved = _translate_pieces((anchor, other), origin[0], origin[1])
    if not _slot_pair_geometry(moved[0], moved[1], kerf_cm):
        return None
    outlines = [material_outline_cm(piece) for piece in moved]
    if any(outline is None for outline in outlines):
        return None
    proven = [outline for outline in outlines if outline is not None]
    if not all(_inside_board(outline, board_w_cm, board_h_cm) for outline in proven):
        return None
    if not _clears(proven[1], [proven[0]], kerf_cm):
        return None
    return moved


def _pair_cell(
    piece: Mapping[str, Any],
    orientation: tuple[Any, ...],
) -> tuple[float, float] | None:
    """Quad cell size. An odd turn that changes the box is not a cell."""

    _mirrored, turns, _facing, _cut_x, _cut_y = orientation
    width = num(piece.get("width_cm"))
    height = num(piece.get("length_cm"))
    if int(turns) % 2 and abs(width - height) > 1e-6:
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def _pair_offsets(
    left_slot: tuple[str, int, int],
    right_slot: tuple[str, int, int],
    width: float,
    height: float,
    kerf_cm: float,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Kerf-spaced coordinates of two adjacent quad cells, origin at the edge."""

    column = min(left_slot[1], right_slot[1])
    row = min(left_slot[2], right_slot[2])
    return (
        ((left_slot[1] - column) * (width + kerf_cm), (left_slot[2] - row) * (height + kerf_cm)),
        ((right_slot[1] - column) * (width + kerf_cm), (right_slot[2] - row) * (height + kerf_cm)),
    )


def _opening_origin(
    width: float,
    height: float,
    open_x: int,
    open_y: int,
    board_w_cm: float,
    board_h_cm: float,
) -> tuple[float, float] | None:
    """Put the shared opening toward the interior when the block keeps this anchor."""

    if width > board_w_cm + 1e-6 or height > board_h_cm + 1e-6:
        return None
    if open_y > 0:
        return 0.0, 0.0
    if open_y < 0:
        return 0.0, board_h_cm - height
    if open_x > 0:
        return 0.0, 0.0
    return board_w_cm - width, 0.0


def _slot_pair_geometry(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
    kerf_cm: float,
) -> bool:
    """True only for a quad edge: opposite facings and a kerf gap, no box overlap."""

    if _recorded_facing(first) == _recorded_facing(second):
        return False
    gap_x = max(num(first.get("x")), num(second.get("x"))) - min(
        num(first.get("x")) + num(first.get("w")),
        num(second.get("x")) + num(second.get("w")),
    )
    gap_y = max(num(first.get("y")), num(second.get("y"))) - min(
        num(first.get("y")) + num(first.get("h")),
        num(second.get("y")) + num(second.get("h")),
    )
    overlap_x = -gap_x
    overlap_y = -gap_y
    horizontal = (
        abs(gap_x - kerf_cm) <= 0.05
        and overlap_y + 1e-6 >= min(num(first.get("h")), num(second.get("h"))) * 0.5
    )
    vertical = (
        abs(gap_y - kerf_cm) <= 0.05
        and overlap_x + 1e-6 >= min(num(first.get("w")), num(second.get("w"))) * 0.5
    )
    return horizontal or vertical


def _recorded_facing(piece: Mapping[str, Any]) -> str:
    position = str(piece.get("clipped_corner_position") or "")
    if position not in _TURN:
        return ""
    if piece.get("mirrored") or piece.get("corner_mirrored") or piece.get("placement_mirrored"):
        position = _MIRROR[position]
    for _step in range(int(piece.get("corner_rotation_quarter_turns") or 0) % 4):
        position = _TURN[position]
    return position


def _pair_inward_score(
    pieces: Sequence[Mapping[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
) -> float | None:
    """Free board beyond the opening, minus the free board behind the pair.

    A positive value means the shared notches point into the board. Pointing
    off an outer edge, or toward the nearer edge, is refused.
    """

    notches = [_notch_bounds(material_outline_cm(piece)) for piece in pieces]
    if any(notch is None for notch in notches) or len(pieces) != 2:
        return None
    proven = [notch for notch in notches if notch is not None]
    void_x = sum(notch["x"] + notch["w"] / 2 for notch in proven) / len(proven)
    void_y = sum(notch["y"] + notch["h"] / 2 for notch in proven) / len(proven)
    if (
        void_x < -1e-6
        or void_y < -1e-6
        or void_x > board_w_cm + 1e-6
        or void_y > board_h_cm + 1e-6
    ):
        return None
    pair_x = sum(num(piece.get("x")) + num(piece.get("w")) / 2 for piece in pieces) / len(pieces)
    pair_y = sum(num(piece.get("y")) + num(piece.get("h")) / 2 for piece in pieces) / len(pieces)
    min_x = min(num(piece.get("x")) for piece in pieces)
    min_y = min(num(piece.get("y")) for piece in pieces)
    max_x = max(num(piece.get("x")) + num(piece.get("w")) for piece in pieces)
    max_y = max(num(piece.get("y")) + num(piece.get("h")) for piece in pieces)
    if abs(void_y - pair_y) >= abs(void_x - pair_x):
        if void_y >= pair_y:
            ahead, behind = board_h_cm - max_y, min_y
        else:
            ahead, behind = min_y, board_h_cm - max_y
    elif void_x >= pair_x:
        ahead, behind = board_w_cm - max_x, min_x
    else:
        ahead, behind = min_x, board_w_cm - max_x
    if ahead < -1e-6 or ahead + 1e-6 < behind:
        return None
    return ahead - behind


def _inward_single(
    piece: Mapping[str, Any],
    board_w_cm: float,
    board_h_cm: float,
    *,
    mirroring_allowed: bool,
) -> dict[str, Any] | None:
    """Turn one corner so its notch faces the board interior."""

    if not mirroring_allowed and not _rotation_allowed(piece):
        return None
    best: tuple[float, dict[str, Any]] | None = None
    for mirrored, turns, _facing, _cut_x, _cut_y in _orientations(piece, mirroring_allowed):
        placed = _placed_corner(piece, x_cm=0.0, y_cm=0.0, mirrored=mirrored, turns=turns)
        width = num(placed.get("w"))
        height = num(placed.get("h"))
        origins = (
            (0.0, 0.0),
            (board_w_cm - width, 0.0),
            (0.0, board_h_cm - height),
            (board_w_cm - width, board_h_cm - height),
        )
        for x_cm, y_cm in origins:
            if x_cm < -1e-6 or y_cm < -1e-6:
                continue
            candidate = _translate_pieces([placed], x_cm, y_cm)[0]
            outline = material_outline_cm(candidate)
            if outline is None or not _inside_board(outline, board_w_cm, board_h_cm):
                continue
            score = _inward_score(candidate, board_w_cm, board_h_cm)
            if score is None or score <= 0.05:
                continue
            if best is None or score > best[0]:
                best = (score, candidate)
    if best is None:
        return None
    return _make_block([best[1]], "single", 0.0)


def _inward_score(
    placed: Mapping[str, Any],
    board_w_cm: float,
    board_h_cm: float,
) -> float | None:
    outline = material_outline_cm(placed)
    notch = _notch_bounds(outline) if outline is not None else None
    if notch is None:
        return None
    center_x = num(placed.get("x")) + num(placed.get("w")) / 2
    center_y = num(placed.get("y")) + num(placed.get("h")) / 2
    notch_x = notch["x"] + notch["w"] / 2
    notch_y = notch["y"] + notch["h"] / 2
    board_x = board_w_cm / 2
    board_y = board_h_cm / 2
    body = math.hypot(center_x - board_x, center_y - board_y)
    cavity = math.hypot(notch_x - board_x, notch_y - board_y)
    return body - cavity


def _make_block(
    placed: Sequence[Mapping[str, Any]],
    kind: str,
    kerf_cm: float,
) -> dict[str, Any]:
    pieces = [dict(piece) for piece in placed]
    if kind == "quad":
        pieces = _normalize_pieces(pieces)
    return {
        "kind": kind,
        "pieces": pieces,
        "guests": [],
        "voids": _voids_for_block(pieces, kind, kerf_cm),
        "host_kind": str(pieces[0].get("piece_type") or ""),
    }


def _voids_for_block(
    pieces: Sequence[Mapping[str, Any]],
    kind: str,
    kerf_cm: float,
) -> list[dict[str, float]]:
    if kind == "quad" and pieces:
        width = num(pieces[0].get("original_w") or pieces[0].get("width_cm"))
        height = num(pieces[0].get("original_h") or pieces[0].get("length_cm"))
        cut_x = num(pieces[0].get("clipped_corner_width_cm"))
        cut_y = num(pieces[0].get("clipped_corner_length_cm"))
        origin_x = min(num(piece.get("x")) for piece in pieces)
        origin_y = min(num(piece.get("y")) for piece in pieces)
        usable = {
            "x": origin_x + width - cut_x + kerf_cm,
            "y": origin_y + height - cut_y + kerf_cm,
            "w": cut_x * 2 - kerf_cm,
            "h": cut_y * 2 - kerf_cm,
        }
        if usable["w"] > 1e-6 and usable["h"] > 1e-6:
            return [usable]
        return []
    if kind == "pair" and len(pieces) == 2:
        notches = [_notch_bounds(material_outline_cm(piece)) for piece in pieces]
        if any(notch is None for notch in notches):
            return []
        proven = [notch for notch in notches if notch is not None]
        x0 = min(notch["x"] for notch in proven)
        y0 = min(notch["y"] for notch in proven)
        x1 = max(notch["x"] + notch["w"] for notch in proven)
        y1 = max(notch["y"] + notch["h"] for notch in proven)
        usable = {
            "x": x0 + kerf_cm,
            "y": y0 + kerf_cm,
            "w": (x1 - x0) - (2 * kerf_cm),
            "h": (y1 - y0) - (2 * kerf_cm),
        }
        if usable["w"] > 1e-6 and usable["h"] > 1e-6:
            return [usable]
        return []
    if kind == "single" and pieces:
        notch = _notch_bounds(material_outline_cm(pieces[0]))
        if notch is None:
            return []
        usable = {
            "x": notch["x"] + kerf_cm,
            "y": notch["y"] + kerf_cm,
            "w": notch["w"] - 2 * kerf_cm,
            "h": notch["h"] - 2 * kerf_cm,
        }
        if usable["w"] > 1e-6 and usable["h"] > 1e-6:
            return [usable]
    return []


def _rotation_allowed(piece: Mapping[str, Any]) -> bool:
    value = piece.get("allow_rotation")
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true"}
    if isinstance(value, int):
        return bool(value)
    return bool(value)


def _normalize_pieces(pieces: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not pieces:
        return []
    min_x = min(num(piece.get("x")) for piece in pieces)
    min_y = min(num(piece.get("y")) for piece in pieces)
    for piece in pieces:
        outline = piece.get("placement_outline_cm")
        if not isinstance(outline, (list, tuple)):
            continue
        for point in outline:
            min_x = min(min_x, float(point[0]))
            min_y = min(min_y, float(point[1]))
    if abs(min_x) <= 1e-9 and abs(min_y) <= 1e-9:
        return [dict(piece) for piece in pieces]
    return _translate_pieces(pieces, -min_x, -min_y)


def _translate_pieces(
    pieces: Sequence[Mapping[str, Any]],
    dx_cm: float,
    dy_cm: float,
) -> list[dict[str, Any]]:
    moved: list[dict[str, Any]] = []
    for piece in pieces:
        copied = dict(piece)
        copied["x"] = num(piece.get("x")) + dx_cm
        copied["y"] = num(piece.get("y")) + dy_cm
        outline = piece.get("placement_outline_cm")
        if isinstance(outline, (list, tuple)) and outline:
            copied["placement_outline_cm"] = [
                (float(point[0]) + dx_cm, float(point[1]) + dy_cm) for point in outline
            ]
        moved.append(copied)
    return moved


def _block_size(pieces: Sequence[Mapping[str, Any]]) -> tuple[float, float]:
    max_x = max(num(piece.get("x")) + num(piece.get("w")) for piece in pieces)
    max_y = max(num(piece.get("y")) + num(piece.get("h")) for piece in pieces)
    min_x = min(num(piece.get("x")) for piece in pieces)
    min_y = min(num(piece.get("y")) for piece in pieces)
    return max_x - min_x, max_y - min_y


def _block_fits_board(
    pieces: Sequence[Mapping[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
) -> bool:
    width, height = _block_size(_normalize_pieces(pieces))
    return width <= board_w_cm + 1e-6 and height <= board_h_cm + 1e-6


def _pieces_inside(
    pieces: Sequence[Mapping[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
) -> bool:
    for piece in pieces:
        outline = material_outline_cm(piece)
        if outline is None or not _inside_board(outline, board_w_cm, board_h_cm):
            return False
    return True


def _pieces_clear(
    pieces: Sequence[Mapping[str, Any]],
    others: Sequence[Mapping[str, Any]],
    kerf_cm: float,
) -> bool:
    for piece in pieces:
        outline = material_outline_cm(piece)
        if outline is None or not _clears(outline, others, kerf_cm):
            return False
    return True


def _notch_bounds(
    outline: Sequence[tuple[float, float]] | None,
) -> dict[str, float] | None:
    if not outline:
        return None
    min_x = min(point[0] for point in outline)
    max_x = max(point[0] for point in outline)
    min_y = min(point[1] for point in outline)
    max_y = max(point[1] for point in outline)
    missing = None
    for corner in ((min_x, min_y), (max_x, min_y), (min_x, max_y), (max_x, max_y)):
        if _bbox_corner_is_material(corner, outline):
            continue
        missing = corner
        break
    if missing is None:
        return None
    share_x = [point for point in outline if abs(point[0] - missing[0]) <= 1e-4]
    share_y = [point for point in outline if abs(point[1] - missing[1]) <= 1e-4]
    if not share_x or not share_y:
        return None
    along_x = min(share_x, key=lambda point: abs(point[1] - missing[1]))
    along_y = min(share_y, key=lambda point: abs(point[0] - missing[0]))
    x0, x1 = sorted((missing[0], along_y[0]))
    y0, y1 = sorted((missing[1], along_x[1]))
    if x1 - x0 <= 1e-4 or y1 - y0 <= 1e-4:
        return None
    return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}


def _bbox_corner_is_material(
    corner: tuple[float, float],
    outline: Sequence[tuple[float, float]],
) -> bool:
    if any(
        abs(corner[0] - point[0]) <= 1e-4 and abs(corner[1] - point[1]) <= 1e-4
        for point in outline
    ):
        return True
    return point_in_polygon(corner, outline)


def _seat_void_guests(
    blocks: Sequence[Mapping[str, Any]],
    pieces: Sequence[Mapping[str, Any]],
    kerf_cm: float,
    board_w_cm: float,
    board_h_cm: float,
    *,
    mirroring_allowed: bool,
    hosted: set[int],
) -> list[dict[str, Any]]:
    complements = [block for block in blocks if block["kind"] != "single"]
    singles = [block for block in blocks if block["kind"] == "single"]
    seated = []
    for block in complements:
        seated.append(
            {
                "kind": block["kind"],
                "pieces": [dict(piece) for piece in block["pieces"]],
                "guests": [],
                "voids": [dict(void) for void in block.get("voids") or []],
                "host_kind": block.get("host_kind") or "",
            }
        )
    used = {int(piece["id"]) for block in seated for piece in block["pieces"]}
    used.update(hosted)
    candidates = [
        piece
        for piece in pieces
        if int(piece["id"]) not in used and _guest_outline_ready(piece)
    ]
    voids = [void for block in seated for void in block["voids"]]
    orders = _guest_orders(candidates, voids)
    best_guests: list[tuple[int, dict[str, Any]]] | None = None
    best_score: tuple[int, float] | None = None
    best_trial = seated
    for order in orders:
        trial = [
            {
                **block,
                "pieces": [dict(piece) for piece in block["pieces"]],
                "guests": [],
            }
            for block in seated
        ]
        placed: list[tuple[int, dict[str, Any]]] = []
        for piece in order:
            found = _place_in_voids(
                piece,
                trial,
                kerf_cm,
                board_w_cm,
                board_h_cm,
                mirroring_allowed=mirroring_allowed,
            )
            if found is None:
                continue
            block_index, guest = found
            trial[block_index]["pieces"].append(guest)
            trial[block_index]["guests"].append(guest)
            placed.append((block_index, guest))
        area = sum(num(guest.get("w")) * num(guest.get("h")) for _index, guest in placed)
        score = (len(placed), area)
        if best_score is None or score > best_score:
            best_score = score
            best_guests = placed
            best_trial = trial
    if best_guests:
        seated = best_trial
    seated_ids = {
        int(piece["id"])
        for block in seated
        for piece in block.get("guests") or []
    }
    for block in singles:
        if any(int(piece["id"]) in seated_ids for piece in block["pieces"]):
            continue
        seated.append(
            {
                "kind": block["kind"],
                "pieces": [dict(piece) for piece in block["pieces"]],
                "guests": [],
                "voids": [dict(void) for void in block.get("voids") or []],
                "host_kind": block.get("host_kind") or "",
            }
        )
    return seated


def _guest_outline_ready(piece: Mapping[str, Any]) -> bool:
    return material_outline_cm(
        {
            **piece,
            "x": 0.0,
            "y": 0.0,
            "w": num(piece.get("width_cm")),
            "h": num(piece.get("length_cm")),
            "rotated": False,
        }
    ) is not None


def _guest_orders(
    candidates: Sequence[Mapping[str, Any]],
    voids: Sequence[Mapping[str, float]],
) -> list[list[Mapping[str, Any]]]:
    if not candidates or not voids:
        return []
    limit = max(void["w"] for void in voids) + 1e-6
    tall = max(void["h"] for void in voids) + 1e-6
    fitting = [
        piece
        for piece in candidates
        if min(num(piece.get("width_cm")), num(piece.get("length_cm"))) <= max(limit, tall)
        and max(num(piece.get("width_cm")), num(piece.get("length_cm"))) <= max(limit, tall)
    ]
    fitting.sort(key=lambda piece: (-(num(piece.get("width_cm")) * num(piece.get("length_cm"))), int(piece["id"])))
    if not fitting:
        return []
    orders = [fitting, list(reversed(fitting))]
    head = fitting[:4]
    for shift in range(1, len(head)):
        orders.append(head[shift:] + head[:shift] + fitting[4:])
    unique: list[list[Mapping[str, Any]]] = []
    seen: set[tuple[int, ...]] = set()
    for order in orders:
        key = tuple(int(piece["id"]) for piece in order)
        if key in seen:
            continue
        seen.add(key)
        unique.append(order)
        if len(unique) >= _MAX_GUEST_ORDERS:
            break
    return unique


def _place_in_voids(
    piece: Mapping[str, Any],
    blocks: Sequence[dict[str, Any]],
    kerf_cm: float,
    board_w_cm: float,
    board_h_cm: float,
    *,
    mirroring_allowed: bool,
) -> tuple[int, dict[str, Any]] | None:
    for index, block in enumerate(blocks):
        if (
            block["kind"] == "quad"
            and block.get("host_kind") == "Clipped Corner"
            and str(piece.get("piece_type") or "Regular") in {"Regular", "Glass"}
            and not any(guest.get("placement_rotation_deg") for guest in block["guests"])
        ):
            angled = _guest_in_clipped_void(
                piece,
                [outline for outline in (material_outline_cm(host) for host in block["pieces"]) if outline],
                num(block["pieces"][0].get("original_w") or block["pieces"][0].get("width_cm")),
                num(block["pieces"][0].get("original_h") or block["pieces"][0].get("length_cm")),
                num(block["pieces"][0].get("clipped_corner_width_cm")),
                num(block["pieces"][0].get("clipped_corner_length_cm")),
                kerf_cm,
                board_w_cm,
                board_h_cm,
                obstacles=block["pieces"],
            )
            if angled is not None:
                return index, angled
        for void in block.get("voids") or []:
            guest = _guest_in_rect(
                piece,
                void,
                block["pieces"],
                kerf_cm,
                board_w_cm,
                board_h_cm,
                mirroring_allowed=mirroring_allowed,
            )
            if guest is not None:
                return index, guest
    return None


def _guest_in_rect(
    piece: Mapping[str, Any],
    void: Mapping[str, float],
    hosts: Sequence[Mapping[str, Any]],
    kerf_cm: float,
    board_w_cm: float,
    board_h_cm: float,
    *,
    mirroring_allowed: bool,
) -> dict[str, Any] | None:
    if void["w"] <= 0 or void["h"] <= 0:
        return None
    for mirrored, turns, width, height in _guest_orientations(piece, mirroring_allowed):
        if width > void["w"] + 1e-6 or height > void["h"] + 1e-6:
            continue
        for x_cm, y_cm in _void_spots(void, width, height, kerf_cm):
            guest = _guest_at(piece, x_cm, y_cm, width, height, mirrored, turns)
            outline = material_outline_cm(guest)
            if outline is None or not _outline_inside_rect(outline, void):
                continue
            if not _inside_board(outline, board_w_cm, board_h_cm):
                continue
            if not _clears(outline, hosts, kerf_cm):
                continue
            return guest
    return None


def _guest_orientations(
    piece: Mapping[str, Any],
    mirroring_allowed: bool,
) -> list[tuple[bool, int, float, float]]:
    kind = str(piece.get("piece_type") or "Regular")
    if kind in _CORNER_TYPES:
        found = []
        for mirrored, turns, _facing, _cut_x, _cut_y in _orientations(piece, mirroring_allowed):
            source_w = num(piece.get("width_cm"))
            source_h = num(piece.get("length_cm"))
            odd = bool(int(turns) % 2) and abs(source_w - source_h) > 1e-6
            found.append(
                (mirrored, turns, source_h if odd else source_w, source_w if odd else source_h)
            )
        return found
    from .primitives import orientations_for

    return [
        (False, 1 if item["rotated"] else 0, item["w"], item["h"])
        for item in orientations_for(dict(piece))
    ]


def _guest_at(
    piece: Mapping[str, Any],
    x_cm: float,
    y_cm: float,
    width: float,
    height: float,
    mirrored: bool,
    turns: int,
) -> dict[str, Any]:
    kind = str(piece.get("piece_type") or "Regular")
    if kind in _CORNER_TYPES:
        return _placed_corner(piece, x_cm=x_cm, y_cm=y_cm, mirrored=mirrored, turns=turns)
    placed = make_placed_piece(
        dict(piece),
        x_cm,
        y_cm,
        width,
        height,
        bool(turns % 2),
    )
    return placed


def _void_spots(
    void: Mapping[str, float],
    width: float,
    height: float,
    kerf_cm: float,
) -> list[tuple[float, float]]:
    spots: list[tuple[float, float]] = []
    step_x = max(width + kerf_cm, kerf_cm, 0.5)
    step_y = max(height + kerf_cm, kerf_cm, 0.5)
    y_cm = void["y"]
    while y_cm + height <= void["y"] + void["h"] + 1e-6 and len(spots) < _MAX_VOID_SPOTS:
        x_cm = void["x"]
        while x_cm + width <= void["x"] + void["w"] + 1e-6 and len(spots) < _MAX_VOID_SPOTS:
            spots.append((x_cm, y_cm))
            x_cm += step_x
        y_cm += step_y
    if not spots and width <= void["w"] + 1e-6 and height <= void["h"] + 1e-6:
        spots.append((void["x"], void["y"]))
    return spots


def _outline_inside_rect(
    outline: Sequence[tuple[float, float]],
    rect: Mapping[str, float],
) -> bool:
    return all(
        rect["x"] - 1e-6 <= point[0] <= rect["x"] + rect["w"] + 1e-6
        and rect["y"] - 1e-6 <= point[1] <= rect["y"] + rect["h"] + 1e-6
        for point in outline
    )


def _compose_plan(
    plan: Mapping[str, Any],
    pieces: Sequence[Mapping[str, Any]],
    blocks: Sequence[Mapping[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    spot_on_sheet: Any,
) -> dict[str, Any] | None:
    sheets = _copy_sheets(plan)
    ordered = sorted(
        blocks,
        key=lambda block: (
            0 if block["kind"] == "quad" else 1 if block["kind"] == "pair" else 2,
            -sum(num(piece.get("w")) * num(piece.get("h")) for piece in block["pieces"]),
        ),
    )
    for block in ordered:
        body = [dict(piece) for piece in block["pieces"]]
        if block["kind"] == "quad":
            body = _normalize_pieces(body)
        optional = block["kind"] == "single"
        if not _block_fits_board(body, board_w_cm, board_h_cm) or not _pieces_inside(
            body, board_w_cm, board_h_cm
        ):
            if optional:
                continue
            return None
        removed = {int(piece["id"]) for piece in body}
        _remove_ids(sheets, removed)
        if block["kind"] == "pair":
            _seat_authored_pair(sheets, body, kerf_cm, board_w_cm, board_h_cm)
            continue
        translation = None
        target = None
        constraint = "single" if block["kind"] == "single" else ""
        for sheet in sheets:
            translation = _block_translation(
                sheet,
                body,
                kerf_cm,
                board_w_cm,
                board_h_cm,
                constraint=constraint,
            )
            if translation is not None:
                target = sheet
                break
        if translation is None:
            if not _pieces_inside(body, board_w_cm, board_h_cm):
                if optional:
                    continue
                return None
            sheets.append(
                {
                    "sheet_no": len(sheets) + 1,
                    "w": board_w_cm,
                    "h": board_h_cm,
                    "pieces": body,
                }
            )
        else:
            target["pieces"].extend(_translate_pieces(body, translation[0], translation[1]))
    _pull_loose_pieces(
        sheets,
        kerf_cm,
        board_w_cm,
        board_h_cm,
        spot_on_sheet,
        _sources_by_id(pieces),
    )
    sheets = [sheet for sheet in sheets if sheet.get("pieces")]
    for index, sheet in enumerate(sheets, start=1):
        sheet["sheet_no"] = index
        sheet["w"] = board_w_cm
        sheet["h"] = board_h_cm
    candidate = _plan_from(plan, sheets)
    expected = {int(piece["id"]) for piece in pieces}
    if _placed_ids(candidate) != expected:
        return None
    return candidate


def _fallback_plan(
    plan: Mapping[str, Any],
    pieces: Sequence[Mapping[str, Any]],
    blocks: Sequence[Mapping[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
) -> dict[str, Any] | None:
    """Keep proven quads and pairs on their own boards and leave the rest put."""

    required = [block for block in blocks if block["kind"] in {"quad", "pair"}]
    if not required:
        return None
    sheets = _copy_sheets(plan)
    removed: set[int] = set()
    fresh: list[dict[str, Any]] = []
    for block in required:
        body = (
            [dict(piece) for piece in block["pieces"]]
            if block["kind"] == "pair"
            else _normalize_pieces(block["pieces"])
        )
        if not _pieces_inside(body, board_w_cm, board_h_cm):
            continue
        removed.update(int(piece["id"]) for piece in body)
        fresh.append(
            {
                "sheet_no": 1,
                "w": board_w_cm,
                "h": board_h_cm,
                "pieces": body,
            }
        )
    if not removed:
        return None
    _remove_ids(sheets, removed)
    sheets = [sheet for sheet in sheets if sheet.get("pieces")]
    sheets.extend(fresh)
    for index, sheet in enumerate(sheets, start=1):
        sheet["sheet_no"] = index
    candidate = _plan_from(plan, sheets)
    if _placed_ids(candidate) != {int(piece["id"]) for piece in pieces}:
        return None
    return candidate


def _seat_authored_pair(
    sheets: list[dict[str, Any]],
    body: Sequence[Mapping[str, Any]],
    kerf_cm: float,
    board_w_cm: float,
    board_h_cm: float,
) -> None:
    """Place the authored pair on an existing board before opening another.

    The two pieces stay a rigid block: the same facings, the same kerf gap,
    and the shared opening toward the board interior. The original coordinates
    are one candidate, not the only one.
    """

    from .nesting_consolidation import best_rigid_translation

    normalized = _normalize_pieces(body)
    best: tuple[tuple[Any, ...], dict[str, Any], float, float] | None = None
    for sheet in sheets:
        found = best_rigid_translation(
            sheet,
            normalized,
            kerf_cm,
            board_w_cm,
            board_h_cm,
            constraint="pair",
        )
        if found is None:
            continue
        dx, dy, rank = found
        used = 0 if sheet.get("pieces") else 1
        if best is None or (used, rank) < best[0]:
            best = ((used, rank), sheet, dx, dy)
    if best is not None:
        _rank, sheet, dx, dy = best
        sheet["pieces"].extend(_translate_pieces(normalized, dx, dy))
        return
    sheets.append(
        {
            "sheet_no": len(sheets) + 1,
            "w": board_w_cm,
            "h": board_h_cm,
            "pieces": [dict(piece) for piece in body],
        }
    )


def _copy_sheets(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    copied = []
    for sheet in plan.get("sheets") or []:
        copied.append({**sheet, "pieces": [dict(piece) for piece in sheet.get("pieces") or []]})
    return copied


def _remove_ids(sheets: list[dict[str, Any]], removed: set[int]) -> None:
    for sheet in sheets:
        sheet["pieces"] = [
            piece for piece in sheet.get("pieces") or [] if int(piece["id"]) not in removed
        ]


def _block_translation(
    sheet: Mapping[str, Any],
    body: Sequence[Mapping[str, Any]],
    kerf_cm: float,
    board_w_cm: float,
    board_h_cm: float,
    *,
    constraint: str = "",
) -> tuple[float, float] | None:
    """Shift a whole block onto this sheet. The return value is a delta."""

    from .nesting_consolidation import best_rigid_translation

    found = best_rigid_translation(
        sheet,
        body,
        kerf_cm,
        board_w_cm,
        board_h_cm,
        constraint=constraint,
    )
    if found is None:
        return None
    return found[0], found[1]


def _sources_by_id(pieces: Sequence[Mapping[str, Any]]) -> dict[int, dict[str, Any]]:
    """Index expanded source rows. A placed record is not a source."""

    sources: dict[int, dict[str, Any]] = {}
    for piece in pieces:
        try:
            piece_id = int(piece["id"])
        except (TypeError, ValueError, KeyError):
            continue
        if num(piece.get("width_cm")) <= 0 or num(piece.get("length_cm")) <= 0:
            continue
        sources[piece_id] = dict(piece)
    return sources


def _pull_loose_pieces(
    sheets: list[dict[str, Any]],
    kerf_cm: float,
    board_w_cm: float,
    board_h_cm: float,
    spot_on_sheet: Any,
    sources: Mapping[int, Mapping[str, Any]],
) -> None:
    nest_sheets = [sheet for sheet in sheets if _sheet_has_nest(sheet)]
    if not nest_sheets:
        return
    hosts: set[int] = set()
    for sheet in sheets:
        for piece in sheet.get("pieces") or []:
            host = piece.get("glass_host_piece_id")
            if host in (None, ""):
                continue
            try:
                hosts.add(int(host))
            except (TypeError, ValueError):
                continue
    for source_sheet in list(sheets):
        if source_sheet in nest_sheets:
            continue
        kept: list[dict[str, Any]] = []
        for piece in list(source_sheet.get("pieces") or []):
            if (
                _piece_is_nest_locked(piece)
                or piece.get("glass_host_piece_id") not in (None, "")
                or int(piece["id"]) in hosts
            ):
                kept.append(piece)
                continue
            try:
                piece_id = int(piece["id"])
            except (TypeError, ValueError):
                kept.append(piece)
                continue
            catalog = sources.get(piece_id)
            if catalog is None:
                kept.append(piece)
                continue
            moved = False
            for target in nest_sheets:
                pending = _fill_free_space(
                    target,
                    [dict(catalog)],
                    kerf_cm,
                    spot_on_sheet,
                    board_w_cm=board_w_cm,
                    board_h_cm=board_h_cm,
                )
                if not pending:
                    moved = True
                    break
            if not moved:
                kept.append(piece)
        source_sheet["pieces"] = kept


def _sheet_has_nest(sheet: Mapping[str, Any]) -> bool:
    return any(_piece_is_nest_locked(piece) for piece in sheet.get("pieces") or [])


def _piece_is_nest_locked(piece: Mapping[str, Any]) -> bool:
    if piece.get("placement_outline_cm") or piece.get("placement_rotation_deg"):
        return True
    if piece.get("mirrored") or piece.get("corner_mirrored") or piece.get("placement_mirrored"):
        return True
    return "corner_rotation_quarter_turns" in piece or "placement_quarter_turns" in piece


def _plan_from(plan: Mapping[str, Any], sheets: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "sheets": sheets,
        "unplaced": [],
        "method_key": plan.get("method_key") or "",
        "method_label": plan.get("method_label") or "",
        "optimization_mode": plan.get("optimization_mode") or "",
        "ordering_strategy": plan.get("ordering_strategy") or "",
        "attempts": plan.get("attempts") or 1,
        "complexity": plan.get("complexity") or 0,
    }


def _placed_ids(plan: Mapping[str, Any]) -> set[int]:
    return {
        int(piece["id"])
        for sheet in plan.get("sheets") or []
        for piece in sheet.get("pieces") or []
    }


def _placement_signature(plan: Mapping[str, Any]) -> tuple[Any, ...]:
    rows = []
    for sheet in plan.get("sheets") or []:
        for piece in sheet.get("pieces") or []:
            rows.append(
                (
                    int(piece["id"]),
                    int(sheet.get("sheet_no") or 0),
                    round(num(piece.get("x")), 2),
                    round(num(piece.get("y")), 2),
                    int(piece.get("corner_rotation_quarter_turns") or 0),
                    bool(piece.get("mirrored") or piece.get("corner_mirrored")),
                    round(float(piece.get("placement_rotation_deg") or 0), 2),
                    round(num(piece.get("w")), 2),
                    round(num(piece.get("h")), 2),
                )
            )
    return tuple(sorted(rows))


def _nest_choice_key(
    plan: Mapping[str, Any],
    blocks: Sequence[Mapping[str, Any]],
) -> tuple[Any, ...]:
    guest_ids = {
        int(piece["id"])
        for block in blocks
        for piece in block.get("guests") or []
    }
    complement = 0
    for block in blocks:
        if block["kind"] not in {"quad", "pair"}:
            continue
        complement += sum(1 for piece in block["pieces"] if int(piece["id"]) not in guest_ids)
    guest_area = 0.0
    for block in blocks:
        for piece in block.get("guests") or []:
            guest_area += num(piece.get("w")) * num(piece.get("h"))
    return (
        complement,
        len(guest_ids),
        round(guest_area, 4),
        -len(plan.get("sheets") or []),
    )


def _glass_hosted_ids(plan: Mapping[str, Any]) -> set[int]:
    hosted: set[int] = set()
    for sheet in plan.get("sheets") or []:
        for piece in sheet.get("pieces") or []:
            if piece.get("glass_host_piece_id") in (None, ""):
                continue
            try:
                hosted.add(int(piece["id"]))
                hosted.add(int(piece["glass_host_piece_id"]))
            except (TypeError, ValueError):
                continue
    return hosted


def _orientations(
    piece: Mapping[str, Any],
    mirroring_allowed: bool,
) -> list[tuple[bool, int, str, float, float]]:
    """Quarter-turns and mirrors the piece is allowed to use.

    The permission is checked before the candidate is recorded. A 90° or 270°
    turn of a non-square piece is still recorded; the cluster cell rejects it
    when the oriented box no longer matches. The clipped-void angle is not
    produced here.
    """

    from .placement_orientation import (
        PlacementOrientation,
        PlacementOrientationError,
        assert_orientation_allowed,
    )

    position = str(piece.get("clipped_corner_position") or "")
    cut_x = num(piece.get("clipped_corner_width_cm"))
    cut_y = num(piece.get("clipped_corner_length_cm"))
    if position not in _TURN:
        return []
    allow_rotation = piece.get("allow_rotation")
    found: list[tuple[bool, int, str, float, float]] = []
    for mirrored in (False, True):
        if mirrored and not mirroring_allowed:
            continue
        facing = _MIRROR[position] if mirrored else position
        turned_x, turned_y = cut_x, cut_y
        for turns in range(4):
            try:
                assert_orientation_allowed(
                    PlacementOrientation(mirrored, turns),
                    mirroring_allowed=mirroring_allowed,
                    allow_rotation=allow_rotation,
                )
            except PlacementOrientationError:
                pass
            else:
                found.append((mirrored, turns, facing, turned_x, turned_y))
            facing = _TURN[facing]
            turned_x, turned_y = turned_y, turned_x
    return found


def _placed_corner(
    piece: Mapping[str, Any],
    *,
    x_cm: float,
    y_cm: float,
    mirrored: bool,
    turns: int,
) -> dict[str, Any]:
    """Place a corner without rewriting which edge is its notch.

    Odd turns swap the bounding box only when the sides differ. The original
    position, cuts, edge bands, and machining sides stay on the piece. The
    outline transform consumes ``corner_rotation_quarter_turns``.
    """

    source_w = num(piece.get("width_cm"))
    source_h = num(piece.get("length_cm"))
    quarter_turns = int(turns) % 4
    odd = bool(quarter_turns % 2) and abs(source_w - source_h) > 1e-6
    placed = make_placed_piece(
        dict(piece),
        x_cm,
        y_cm,
        source_h if odd else source_w,
        source_w if odd else source_h,
        odd,
    )
    placed["corner_rotation_quarter_turns"] = quarter_turns
    placed["placement_quarter_turns"] = quarter_turns
    placed["corner_mirrored"] = bool(mirrored)
    placed["mirrored"] = bool(mirrored)
    placed["placement_mirrored"] = bool(mirrored)
    return placed


def _glass_nest_links(plan: Mapping[str, Any]) -> tuple[tuple[int, int], ...]:
    links = []
    for sheet in plan.get("sheets") or []:
        for piece in sheet.get("pieces") or []:
            host = piece.get("glass_host_piece_id")
            if host in (None, ""):
                continue
            try:
                links.append((int(piece["id"]), int(host)))
            except (TypeError, ValueError):
                return tuple()
    return tuple(sorted(links))


def _fill_free_space(
    sheet: dict[str, Any],
    remainder: Sequence[Mapping[str, Any]],
    kerf_cm: float,
    spot_on_sheet: Any,
    board_w_cm: float | None = None,
    board_h_cm: float | None = None,
) -> list[Mapping[str, Any]]:
    """Put leftover pieces on the nest board when their real outlines fit.

    A piece that does not fit stays in the returned list. That miss does not
    discard the nest already sitting on the board.
    """

    pending = sorted(
        remainder,
        key=lambda piece: num(piece.get("width_cm")) * num(piece.get("length_cm")),
        reverse=True,
    )
    placed = list(sheet.get("pieces") or [])
    width = board_w_cm if board_w_cm is not None else num(sheet.get("w"))
    height = board_h_cm if board_h_cm is not None else num(sheet.get("h"))
    leftover: list[Mapping[str, Any]] = []
    for piece in pending:
        spot = spot_on_sheet(
            {"w": width, "h": height, "pieces": placed},
            dict(piece),
            kerf_cm,
        )
        if spot is None:
            leftover.append(piece)
            continue
        guest = make_placed_piece(
            dict(piece),
            spot["x"],
            spot["y"],
            spot["w"],
            spot["h"],
            bool(spot["rotated"]),
        )
        if (
            str(piece.get("piece_type") or "") == "Glass"
            and num(piece.get("glass_margin_mm")) > 0
            and not guest.get("glass_hole_local_mm")
        ):
            leftover.append(piece)
            continue
        outline = material_outline_cm(guest)
        if (
            outline is None
            or not _inside_board(outline, width, height)
            or not _clears(outline, placed, kerf_cm)
        ):
            leftover.append(piece)
            continue
        placed.append(guest)
    sheet["pieces"] = placed
    return leftover


def _inner_guest(
    pieces: Sequence[Mapping[str, Any]],
    used: set[int],
    corners: Sequence[Mapping[str, Any]],
    key: tuple[Any, ...],
    kerf_cm: float,
    board_w_cm: float,
    board_h_cm: float,
    *,
    mirroring_allowed: bool = False,
) -> dict[str, Any] | None:
    """Place one proven outline in the shared void. Score does not decide."""

    kind, width, height, cut_x, cut_y = key
    outlines = [material_outline_cm(piece) for piece in corners]
    if any(outline is None for outline in outlines):
        return None
    proven = [outline for outline in outlines if outline is not None]
    void = {
        "x": width - cut_x + kerf_cm,
        "y": height - cut_y + kerf_cm,
        "w": cut_x * 2 - kerf_cm,
        "h": cut_y * 2 - kerf_cm,
    }
    for piece in pieces:
        if int(piece["id"]) in used or not _guest_outline_ready(piece):
            continue
        if kind == "Clipped Corner" and str(piece.get("piece_type") or "Regular") in {
            "Regular",
            "Glass",
        }:
            guest = _guest_in_clipped_void(
                piece,
                proven,
                width,
                height,
                cut_x,
                cut_y,
                kerf_cm,
                board_w_cm,
                board_h_cm,
                obstacles=corners,
            )
        else:
            guest = _guest_in_rect(
                piece,
                void,
                corners,
                kerf_cm,
                board_w_cm,
                board_h_cm,
                mirroring_allowed=mirroring_allowed,
            )
        if guest is not None:
            return {"id": piece["id"], "piece": guest}
    return None


def _guest_in_clipped_void(
    piece: Mapping[str, Any],
    corner_outlines: Sequence[Sequence[tuple[float, float]]],
    width: float,
    height: float,
    cut_x: float,
    cut_y: float,
    kerf_cm: float,
    board_w_cm: float,
    board_h_cm: float,
    obstacles: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any] | None:
    angle = void_edge_angle_deg(cut_x, cut_y)
    if angle is None:
        return None
    origin_x = min(point[0] for outline in corner_outlines for point in outline)
    origin_y = min(point[1] for outline in corner_outlines for point in outline)
    center_x = origin_x + width + kerf_cm / 2
    center_y = origin_y + height + kerf_cm / 2
    piece_w = num(piece.get("width_cm"))
    piece_h = num(piece.get("length_cm"))
    for rotation in (angle, angle + 180.0):
        if not non_quarter_rotation_is_admitted(
            rotation,
            cut_width_cm=cut_x,
            cut_length_cm=cut_y,
            outline_inside_void=True,
        ):
            continue
        outline = _rotated_rectangle(center_x, center_y, piece_w, piece_h, rotation)
        if not _inside_board(outline, board_w_cm, board_h_cm):
            continue
        if not _clears(outline, [*corner_outlines, *obstacles], kerf_cm):
            continue
        xs = [point[0] for point in outline]
        ys = [point[1] for point in outline]
        placed = make_placed_piece(
            dict(piece),
            min(xs),
            min(ys),
            max(xs) - min(xs),
            max(ys) - min(ys),
            False,
        )
        placed["placement_outline_cm"] = outline
        placed["placement_rotation_deg"] = rotation % 360.0
        placed["placement_void_angle_deg"] = angle
        return placed
    return None


def _rotated_rectangle(
    center_x: float,
    center_y: float,
    width: float,
    height: float,
    rotation_deg: float,
) -> list[tuple[float, float]]:
    radians = math.radians(rotation_deg)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    half_w = width / 2
    half_h = height / 2
    points = []
    for px, py in ((-half_w, -half_h), (half_w, -half_h), (half_w, half_h), (-half_w, half_h)):
        points.append((center_x + px * cosine - py * sine, center_y + px * sine + py * cosine))
    return points


def _inside_board(
    outline: Sequence[tuple[float, float]],
    board_w_cm: float,
    board_h_cm: float,
) -> bool:
    return all(
        -1e-6 <= point[0] <= board_w_cm + 1e-6
        and -1e-6 <= point[1] <= board_h_cm + 1e-6
        for point in outline
    )


def _clears(
    outline: Sequence[tuple[float, float]],
    corners: Sequence[Mapping[str, Any]] | Sequence[Sequence[tuple[float, float]]],
    kerf_cm: float,
) -> bool:
    for corner in corners:
        other = corner if isinstance(corner, (list, tuple)) else material_outline_cm(corner)
        if other is None:
            return False
        if polygons_overlap(outline, other):
            return False
        if polygon_distance(outline, other) + 1e-6 < kerf_cm:
            return False
    return True


def _angle_close(left: float, right: float, tolerance: float) -> bool:
    return abs((left - right + 180.0) % 360.0 - 180.0) <= tolerance


def admit_clipped_void_topology(
    contours: Sequence[Any],
    expected: Sequence[Any],
    *,
    geometry_tolerance: float,
) -> Any | None:
    """Return topology for four clipped corners plus one void-angle piece.

    Any other angle, a missing clip, or a piece outside the void returns
    ``None`` so the ordinary matcher keeps rejecting it.
    """

    from almdina_erp.almdina_erp.domain.orders.piece_policy import (
        CLIPPED_CORNER_POSITIONS,
        CLIPPED_CORNER_TYPE,
    )

    from .corner_contour_rotation import match_corner_contour
    from .dxf_geometry import point_in_polygon
    from .dxf_topology import PartGeometry, ResolvedPartGeometry, ResolvedTopology

    clips = [
        piece
        for piece in expected
        if getattr(piece, "piece_type", "") == CLIPPED_CORNER_TYPE
        and float(getattr(piece, "clipped_cut_width_mm", 0) or 0) > 0
        and float(getattr(piece, "clipped_cut_length_mm", 0) or 0) > 0
    ]
    if len(expected) != 5 or len(clips) != 4 or len(contours) != 5:
        return None
    inners = [piece for piece in expected if piece not in clips]
    if len(inners) != 1:
        return None
    inner = inners[0]
    unused = list(contours)
    assigned: list[tuple[Any, Any]] = []
    for clip in clips:
        found = None
        for contour in list(unused):
            if _contour_matches_clip(
                contour,
                clip,
                geometry_tolerance,
                match_corner_contour,
                CLIPPED_CORNER_POSITIONS,
            ):
                found = contour
                break
        if found is None:
            return None
        unused.remove(found)
        assigned.append((found, clip))
    polygon = _ring(unused[0].polygon)
    angle = _rectangle_angle_deg(polygon)
    cut_w = float(clips[0].clipped_cut_width_mm) / 10.0
    cut_h = float(clips[0].clipped_cut_length_mm) / 10.0
    if angle is None or not non_quarter_rotation_is_admitted(
        angle,
        cut_width_cm=cut_w,
        cut_length_cm=cut_h,
        outline_inside_void=True,
    ):
        return None
    if not _edge_lengths_match(polygon, float(inner.width), float(inner.height)):
        return None
    clip_rings = [_ring(contour.polygon) for contour, _clip in assigned]
    if not _contour_sits_in_void(polygon, clip_rings, point_in_polygon):
        return None
    parts = [
        ResolvedPartGeometry(
            contour_key=int(contour.key),
            geometry=PartGeometry(outer=_ring(contour.polygon)),
            expected_piece_index=list(expected).index(clip),
        )
        for contour, clip in assigned
    ]
    parts.append(
        ResolvedPartGeometry(
            contour_key=int(unused[0].key),
            geometry=PartGeometry(outer=polygon),
            expected_piece_index=list(expected).index(inner),
        )
    )
    return ResolvedTopology(parts=tuple(parts))


def _contour_matches_clip(
    contour: Any,
    clip: Any,
    tolerance: float,
    match_corner_contour: Any,
    positions: Sequence[str],
) -> bool:
    saved = str(getattr(clip, "clipped_corner_position", "") or "")
    choices = (saved,) if saved in positions else positions
    for position in choices:
        match = match_corner_contour(
            contour.polygon,
            piece_type=str(clip.piece_type),
            position=position,
            width_cm=float(clip.width) / 10.0,
            length_cm=float(clip.height) / 10.0,
            cut_width_cm=float(clip.clipped_cut_width_mm) / 10.0,
            cut_length_cm=float(clip.clipped_cut_length_mm) / 10.0,
            tolerance_mm=tolerance,
        )
        if match.quarter_turns is not None and match.reason == "unique":
            return True
    return False


def _ring(points: Sequence[Sequence[float]]) -> tuple[tuple[float, float], ...]:
    ring = tuple((float(point[0]), float(point[1])) for point in points)
    if len(ring) > 1 and ring[0] == ring[-1]:
        return ring[:-1]
    return ring


def _rectangle_angle_deg(polygon: Sequence[tuple[float, float]]) -> float | None:
    if len(polygon) != 4:
        return None
    dx = polygon[1][0] - polygon[0][0]
    dy = polygon[1][1] - polygon[0][1]
    if math.hypot(dx, dy) <= 1e-6:
        return None
    return math.degrees(math.atan2(dy, dx)) % 360.0


def _edge_lengths_match(
    polygon: Sequence[tuple[float, float]],
    width_mm: float,
    height_mm: float,
) -> bool:
    lengths = sorted(
        math.hypot(
            polygon[(index + 1) % len(polygon)][0] - point[0],
            polygon[(index + 1) % len(polygon)][1] - point[1],
        )
        for index, point in enumerate(polygon)
    )
    short = min(width_mm, height_mm)
    long = max(width_mm, height_mm)
    return (
        abs(lengths[0] - short) <= 0.2
        and abs(lengths[1] - short) <= 0.2
        and abs(lengths[-2] - long) <= 0.2
        and abs(lengths[-1] - long) <= 0.2
    )


def _contour_sits_in_void(
    polygon: Sequence[tuple[float, float]],
    clips: Sequence[Sequence[tuple[float, float]]],
    point_in_polygon: Any,
) -> bool:
    centroid = (
        sum(point[0] for point in polygon) / len(polygon),
        sum(point[1] for point in polygon) / len(polygon),
    )
    centers = []
    for clip in clips:
        if point_in_polygon(centroid, clip):
            return False
        if polygons_overlap(polygon, clip):
            return False
        centers.append(
            (
                sum(point[0] for point in clip) / len(clip),
                sum(point[1] for point in clip) / len(clip),
            )
        )
    mean_x = sum(point[0] for point in centers) / len(centers)
    mean_y = sum(point[1] for point in centers) / len(centers)
    span = max(
        math.hypot(point[0] - mean_x, point[1] - mean_y) for point in centers
    )
    return math.hypot(centroid[0] - mean_x, centroid[1] - mean_y) <= span * 0.45


__all__ = [
    "admit_clipped_void_topology",
    "apply_shape_aware_nesting",
    "non_quarter_rotation_is_admitted",
    "void_edge_angle_deg",
]
