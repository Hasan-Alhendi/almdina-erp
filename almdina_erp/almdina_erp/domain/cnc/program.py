"""Intermediate CNC motion model extracted from approved DXF geometry.

This module does not emit G-code, choose a machine origin, or offset a path
a second time. Closed cutter-center rings keep a deterministic direction.
Connected lines become one path. A branch is split into simple chains instead
of inventing a route through the junction.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from almdina_erp.almdina_erp.domain.cnc.operations import (
    CNC_OPERATION_TYPES,
    ILLUSTRATIVE_DXF_LAYERS,
)
from almdina_erp.almdina_erp.domain.cnc.tool_preset import (
    ToolPresetError,
    ToolPresetValues,
    assert_single_tool_for_file,
    normalize_tool_preset,
)


CHAIN_TOLERANCE_MM = 0.05
_DIAMETER_TOLERANCE_MM = 0.05
COORDINATE_SPACE = "sheet_bottom_left_y_up_mm"
MACHINE_ORIGIN = "not_established"
DEPTH_CONVENTION = "positive_millimetres"
_ROLE_ISSUES = {
    "region_boundary": "region_not_supported",
    "finished_boundary": "cut_path_is_piece_boundary",
    "unmatched_cut": "cut_path_does_not_match_approved_centers",
    "unverified": "compensation_unverified",
    "invalid": "geometry_invalid",
    "mill_path_unverified": "mill_path_unverified",
    "mill_placement_unknown": "mill_placement_unknown",
    "mill_parameters_missing": "mill_parameters_missing",
    "mill_diameter_required": "mill_diameter_required",
    "liner_narrower_than_cutter": "liner_narrower_than_cutter",
    "side_unavailable": "side_unavailable",
    "merged_mill_preset_ambiguous": "merged_mill_preset_ambiguous",
}

_OPERATIONS_BY_LAYER = {
    operation.dxf_layer.upper(): operation for operation in CNC_OPERATION_TYPES
}
_ILLUSTRATIVE = {layer.upper() for layer in ILLUSTRATIVE_DXF_LAYERS}


@dataclass(frozen=True, slots=True)
class CncSourceEntity:
    """One DXF entity already expressed in millimetres, before sheet translation."""

    layer: str
    points: tuple[tuple[float, float], ...]
    closed: bool
    entity_type: str
    role: str
    ring: str = "unknown"
    path_key: str = ""
    piece_instance_id: str = ""
    piece_label: str = ""


@dataclass(frozen=True, slots=True)
class CncMotion:
    kind: str
    x_mm: float | None
    y_mm: float | None
    depth_mm: float | None


@dataclass(frozen=True, slots=True)
class CncToolpath:
    path_key: str
    operation_key: str
    dxf_layer: str
    piece_instance_id: str
    piece_label: str
    closed: bool
    direction: str
    points: tuple[tuple[float, float], ...]
    start: tuple[float, float] | None
    end: tuple[float, float] | None
    preset_name: str
    preset: dict[str, object] | None
    ready: bool
    issues: tuple[str, ...]
    motions: tuple[CncMotion, ...]
    sequence: int


@dataclass(frozen=True, slots=True)
class CncOperationProgram:
    operation_key: str
    dxf_layer: str
    sequence: int
    toolpaths: tuple[CncToolpath, ...]


@dataclass(frozen=True, slots=True)
class CncBoardProgram:
    sheet_no: int
    ready: bool
    coordinate_space: str
    machine_origin: str
    depth_convention: str
    sheet_width_mm: float | None
    sheet_length_mm: float | None
    cut_path_early: bool
    cut_path_early_confirmed: bool
    issues: tuple[tuple[str, str], ...]
    operations: tuple[CncOperationProgram, ...]
    geometry_ready: bool = False
    machine_ready: bool = False
    nc_export_ready: bool = False


def _finite_point(point: Sequence[float]) -> tuple[float, float] | None:
    if isinstance(point, (str, bytes)) or len(point) < 2:
        return None
    try:
        x = float(point[0])
        y = float(point[1])
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x) or not math.isfinite(y):
        return None
    return (x, y)


def _distance(left: tuple[float, float], right: tuple[float, float]) -> float:
    return math.dist(left, right)


def _node(point: tuple[float, float]) -> tuple[int, int]:
    scale = CHAIN_TOLERANCE_MM
    return (int(round(point[0] / scale)), int(round(point[1] / scale)))


def _same_segment(
    left: tuple[tuple[float, float], tuple[float, float]],
    right: tuple[tuple[float, float], tuple[float, float]],
) -> bool:
    return (
        _distance(left[0], right[0]) <= CHAIN_TOLERANCE_MM
        and _distance(left[1], right[1]) <= CHAIN_TOLERANCE_MM
    ) or (
        _distance(left[0], right[1]) <= CHAIN_TOLERANCE_MM
        and _distance(left[1], right[0]) <= CHAIN_TOLERANCE_MM
    )


def _dedupe_segments(
    segments: Sequence[tuple[tuple[float, float], tuple[float, float]]],
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    unique: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for segment in segments:
        if _distance(segment[0], segment[1]) <= CHAIN_TOLERANCE_MM:
            continue
        if any(_same_segment(segment, existing) for existing in unique):
            continue
        unique.append(segment)
    return unique


def _chain_lines(
    segments: Sequence[tuple[tuple[float, float], tuple[float, float]]],
) -> list[tuple[tuple[tuple[float, float], ...], bool]]:
    """Join connected lines. Split at a branch instead of choosing a route."""

    usable = _dedupe_segments(segments)
    if not usable:
        return []
    adjacency: dict[tuple[int, int], list[int]] = {}
    ends: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for index, (start, end) in enumerate(usable):
        start_key = _node(start)
        end_key = _node(end)
        ends.append((start_key, end_key))
        adjacency.setdefault(start_key, []).append(index)
        adjacency.setdefault(end_key, []).append(index)

    unused = set(range(len(usable)))
    paths: list[tuple[tuple[tuple[float, float], ...], bool]] = []

    def walk(start_edge: int, start_key: tuple[int, int]) -> tuple[list[tuple[float, float]], bool]:
        points: list[tuple[float, float]] = []
        edge_index = start_edge
        current = start_key
        closed = False
        while edge_index in unused:
            unused.remove(edge_index)
            start, end = usable[edge_index]
            start_node, end_node = ends[edge_index]
            if start_node == current:
                first, second, nxt = start, end, end_node
            else:
                first, second, nxt = end, start, start_node
            if not points:
                points.append(first)
            points.append(second)
            current = nxt
            choices = [item for item in adjacency.get(current, []) if item in unused]
            if not choices:
                closed = _node(points[0]) == current and len(points) >= 4
                break
            if len(choices) > 1 or len(adjacency.get(current, [])) != 2:
                break
            edge_index = choices[0]
        return points, closed

    terminals = [key for key, edges in adjacency.items() if len(edges) != 2]
    terminal_edges: list[tuple[tuple[float, float], int, tuple[int, int]]] = []
    for key in terminals:
        for edge_index in adjacency[key]:
            if edge_index not in unused:
                continue
            start, end = usable[edge_index]
            other = end if _node(start) == key else start
            terminal_edges.append((other, edge_index, key))
    terminal_edges.sort(key=lambda item: (item[0][0], item[0][1], item[1]))
    for _other, edge_index, key in terminal_edges:
        if edge_index not in unused:
            continue
        points, closed = walk(edge_index, key)
        if len(points) >= 2:
            paths.append((tuple(points), closed))

    while unused:
        edge_index = min(unused)
        start, _end = usable[edge_index]
        points, closed = walk(edge_index, _node(start))
        if len(points) >= 2:
            paths.append((tuple(points), closed))
    return paths


def _signed_area(points: Sequence[tuple[float, float]]) -> float:
    area = 0.0
    count = len(points)
    for index, point in enumerate(points):
        nxt = points[(index + 1) % count]
        area += point[0] * nxt[1] - nxt[0] * point[1]
    return area / 2.0


def _rotate_closed(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    start = min(range(len(points)), key=lambda index: (points[index][0], points[index][1], index))
    return points[start:] + points[:start]


def orient_path(
    points: Sequence[tuple[float, float]],
    *,
    closed: bool,
    ring: str,
) -> tuple[tuple[tuple[float, float], ...], str] | str:
    """Return canonical points and a direction label, or an issue code."""

    cleaned: list[tuple[float, float]] = []
    for point in points:
        finite = _finite_point(point)
        if finite is None:
            return "geometry_invalid"
        if not cleaned or _distance(cleaned[-1], finite) > CHAIN_TOLERANCE_MM:
            cleaned.append(finite)
    if closed and len(cleaned) >= 2 and _distance(cleaned[0], cleaned[-1]) <= CHAIN_TOLERANCE_MM:
        cleaned.pop()
    if closed:
        if len(cleaned) < 3 or abs(_signed_area(cleaned)) <= CHAIN_TOLERANCE_MM:
            return "geometry_invalid"
        if ring not in {"outer", "hole"}:
            return "cut_side_unknown"
        cleaned = _rotate_closed(cleaned)
        positive = _signed_area(cleaned) > 0
        want_positive = ring == "outer"
        if positive != want_positive:
            cleaned = _rotate_closed([cleaned[0], *reversed(cleaned[1:])])
        direction = "ccw" if ring == "outer" else "cw"
        return tuple(cleaned), direction
    if len(cleaned) < 2:
        return "geometry_invalid"
    if (cleaned[-1][0], cleaned[-1][1]) < (cleaned[0][0], cleaned[0][1]):
        cleaned.reverse()
    return tuple(cleaned), "start_to_end"


def _pass_depths(final_depth: float, pass_depth: float | None) -> tuple[float, ...] | str:
    if pass_depth is None:
        return (final_depth,)
    depths: list[float] = []
    depth = 0.0
    while depth + 1e-9 < final_depth:
        depth = min(final_depth, depth + pass_depth)
        depths.append(round(depth, 3))
        if len(depths) > 10000:
            return "geometry_invalid"
    return tuple(depths)


def _motions(
    points: Sequence[tuple[float, float]],
    *,
    closed: bool,
    depths: Sequence[float],
) -> tuple[CncMotion, ...]:
    motions: list[CncMotion] = []
    start = points[0]
    end = points[0] if closed else points[-1]
    for depth in depths:
        motions.append(CncMotion("travel", start[0], start[1], None))
        motions.append(CncMotion("plunge", start[0], start[1], depth))
        for point in points[1:]:
            motions.append(CncMotion("cut", point[0], point[1], depth))
        if closed and _distance(points[-1], points[0]) > CHAIN_TOLERANCE_MM:
            motions.append(CncMotion("cut", points[0][0], points[0][1], depth))
        motions.append(CncMotion("retract", end[0], end[1], None))
    return tuple(motions)


def _preset_payload(preset: ToolPresetValues, name: str) -> dict[str, object]:
    return {
        "name": name,
        "preset_name": preset.preset_name,
        "tool_number": preset.tool_number,
        "tool_diameter_mm": preset.tool_diameter_mm,
        "final_depth_mm": preset.final_depth_mm,
        "spindle_speed_rpm": preset.spindle_speed_rpm,
        "feed_rate_mm_min": preset.feed_rate_mm_min,
        "plunge_rate_mm_min": preset.plunge_rate_mm_min,
        "pass_depth_mm": preset.pass_depth_mm,
    }


def _identity(points: Sequence[tuple[float, float]], closed: bool) -> str:
    payload = {
        "closed": closed,
        "points": [[round(point[0], 3), round(point[1], 3)] for point in points],
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _translate(
    points: Sequence[tuple[float, float]],
    origin: tuple[float, float] | None,
) -> list[tuple[float, float]] | None:
    if origin is None:
        return None
    return [(point[0] - origin[0], point[1] - origin[1]) for point in points]


def _layer_operation(layer: str):
    return _OPERATIONS_BY_LAYER.get(str(layer or "").strip().upper())


def _collect_paths(
    entities: Sequence[CncSourceEntity],
    origin: tuple[float, float] | None,
) -> list[dict[str, object]]:
    collected: list[dict[str, object]] = []
    line_groups: dict[tuple[str, str, str, str, str], list[tuple[tuple[float, float], tuple[float, float]]]] = {}
    for entity in entities:
        layer_name = str(entity.layer or "").strip()
        if layer_name.upper() in _ILLUSTRATIVE or _layer_operation(layer_name) is None:
            continue
        translated = _translate(entity.points, origin)
        if translated is None:
            collected.append({"entity": entity, "issue": "sheet_frame_unknown"})
            continue
        finite = [_finite_point(point) for point in translated]
        if any(point is None for point in finite):
            collected.append({"entity": entity, "issue": "geometry_invalid"})
            continue
        points = [point for point in finite if point is not None]
        entity_type = str(entity.entity_type or "").strip().upper()
        if entity_type == "LINE":
            if len(points) != 2:
                collected.append({"entity": entity, "issue": "geometry_invalid"})
                continue
            key = (
                layer_name.upper(),
                entity.role,
                entity.ring,
                entity.piece_instance_id,
                entity.path_key,
            )
            line_groups.setdefault(key, []).append((points[0], points[1]))
            continue
        collected.append({"entity": entity, "points": tuple(points), "closed": entity.closed})
    for key, segments in line_groups.items():
        layer_name, role, ring, piece_id, path_key = key
        sample = next(entity for entity in entities if entity.layer.upper() == layer_name)
        for points, closed in _chain_lines(segments):
            collected.append(
                {
                    "entity": CncSourceEntity(
                        layer=sample.layer,
                        points=points,
                        closed=closed,
                        entity_type="LINE",
                        role=role,
                        ring="open" if not closed else ring,
                        path_key=path_key,
                        piece_instance_id=piece_id,
                        piece_label=sample.piece_label if piece_id else "",
                    ),
                    "points": points,
                    "closed": closed,
                }
            )
    return collected


def build_board_program(
    *,
    sheet_no: int,
    entities: Sequence[CncSourceEntity],
    operation_order: Sequence[str],
    operation_presets: Mapping[str, str],
    path_overrides: Mapping[str, str],
    known_presets: Mapping[str, Mapping[str, object]],
    cut_path_early_confirmed: bool = False,
    units: str = "mm",
    frame_origin_mm: tuple[float, float] | None = (0.0, 0.0),
    sheet_width_mm: float | None = None,
    sheet_length_mm: float | None = None,
    blocked_catalog_paths: Sequence[Mapping[str, str]] = (),
    shared_cut_ambiguous: bool = False,
    approved_kerf_mm: float | None = None,
    path_execution_order: Sequence[str] | None = None,
) -> CncBoardProgram:
    """Build one board program. Confirmation never clears a geometric block."""

    order = [str(key) for key in operation_order]
    early = "cut_path" in order and any(
        key in order and order.index(key) > order.index("cut_path")
        for key in ("liner", "recessed_handle_cutout", "back_groove")
    )
    issues: list[tuple[str, str]] = []
    unit_name = str(units or "").strip().lower()
    if unit_name == "unspecified":
        issues.append(("units_unspecified", ""))
        return _empty_program(sheet_no, issues, early, cut_path_early_confirmed, sheet_width_mm, sheet_length_mm)
    if unit_name != "mm":
        issues.append(("units_unknown", ""))
        return _empty_program(sheet_no, issues, early, cut_path_early_confirmed, sheet_width_mm, sheet_length_mm)
    if frame_origin_mm is None:
        issues.append(("sheet_frame_unknown", ""))

    raw_paths = [] if frame_origin_mm is None else _collect_paths(entities, frame_origin_mm)
    selected: list[tuple[dict[str, object], ToolPresetValues | None, str]] = []
    for item in raw_paths:
        entity = item["entity"]
        assert isinstance(entity, CncSourceEntity)
        operation = _layer_operation(entity.layer)
        if operation is None:
            continue
        issue = str(item.get("issue") or "")
        points = item.get("points")
        raw_points = tuple(points) if isinstance(points, tuple) else ()
        closed = bool(item.get("closed"))
        oriented: tuple[tuple[float, float], ...] = ()
        direction = ""
        if not issue:
            mapped = _ROLE_ISSUES.get(entity.role)
            if mapped:
                issue = mapped
            elif entity.role != "tool_center":
                issue = "compensation_unverified"
        if not issue:
            result = orient_path(raw_points, closed=closed, ring=entity.ring if closed else "open")
            if isinstance(result, str):
                issue = result
            else:
                oriented, direction = result
        shown = oriented or raw_points
        path_key = entity.path_key or f"{operation.key}:center:{_identity(shown, closed)}"
        preset_name = str(path_overrides.get(path_key) or operation_presets.get(operation.key) or "").strip()
        preset: ToolPresetValues | None = None
        preset_issue = ""
        if not preset_name:
            preset_issue = "preset_missing"
        else:
            raw = known_presets.get(preset_name)
            if raw is None:
                preset_issue = "preset_not_found"
            else:
                try:
                    preset = normalize_tool_preset(raw)
                except ToolPresetError as exc:
                    preset_issue = exc.code
                else:
                    if not preset.enabled:
                        preset_issue = "preset_disabled"
                        preset = None
        if not issue:
            issue = preset_issue
        if (
            not issue
            and preset is not None
            and operation.key == "cut_path"
            and entity.role == "tool_center"
            and approved_kerf_mm is not None
            and abs(float(preset.tool_diameter_mm) - float(approved_kerf_mm)) > _DIAMETER_TOLERANCE_MM
        ):
            issue = "tool_diameter_kerf_mismatch"
        selected.append(
            (
                {
                    "entity": entity,
                    "operation": operation,
                    "path_key": path_key,
                    "points": shown,
                    "closed": bool(oriented) and closed and not issue,
                    "direction": direction,
                    "issue": issue,
                    "preset_name": preset_name,
                },
                preset,
                issue,
            )
        )

    usable = [preset for _item, preset, issue in selected if preset is not None and not issue]
    conflict = ""
    try:
        assert_single_tool_for_file(usable)
    except ToolPresetError as exc:
        conflict = exc.code
        issues.append((conflict, ""))

    for catalog in blocked_catalog_paths:
        issues.append((str(catalog.get("code") or "toolpath_missing"), str(catalog.get("path_key") or "")))

    grouped: dict[str, list[CncToolpath]] = {}
    for item, preset, issue in selected:
        entity = item["entity"]
        assert isinstance(entity, CncSourceEntity)
        operation = item["operation"]
        path_issues = [code for code in (issue, conflict) if code]
        if (
            shared_cut_ambiguous
            and operation.key == "cut_path"
            and not str(entity.piece_instance_id or "").strip()
            and "shared_cut_preset_ambiguous" not in path_issues
        ):
            path_issues.append("shared_cut_preset_ambiguous")
            if ("shared_cut_preset_ambiguous", "") not in issues:
                issues.append(("shared_cut_preset_ambiguous", ""))
        if "tool_diameter_kerf_mismatch" in path_issues:
            pair = ("tool_diameter_kerf_mismatch", str(item["path_key"]))
            if pair not in issues:
                issues.append(pair)
        ready = not path_issues
        points = item["points"] if isinstance(item["points"], tuple) else ()
        motions: tuple[CncMotion, ...] = ()
        if ready and preset is not None and points:
            depths = _pass_depths(preset.final_depth_mm, preset.pass_depth_mm)
            if isinstance(depths, str):
                path_issues.append(depths)
                ready = False
            else:
                motions = _motions(points, closed=bool(item["closed"]), depths=depths)
        toolpath = CncToolpath(
            path_key=str(item["path_key"]),
            operation_key=operation.key,
            dxf_layer=operation.dxf_layer,
            piece_instance_id=entity.piece_instance_id,
            piece_label=entity.piece_label,
            closed=bool(item["closed"]) if ready else bool(entity.closed),
            direction=str(item["direction"] or ""),
            points=points,
            start=points[0] if points else None,
            end=(points[0] if item["closed"] else points[-1]) if points else None,
            preset_name=str(item["preset_name"]),
            preset=_preset_payload(preset, str(item["preset_name"])) if preset is not None else None,
            ready=ready,
            issues=tuple(path_issues),
            motions=motions,
            sequence=0,
        )
        grouped.setdefault(operation.key, []).append(toolpath)

    for code, path_key in issues:
        if path_key and not any(path.path_key == path_key for paths in grouped.values() for path in paths):
            operation_key = path_key.split(":", 1)[0]
            operation = next((item for item in CNC_OPERATION_TYPES if item.key == operation_key), None)
            if operation is None:
                continue
            grouped.setdefault(operation.key, []).append(
                CncToolpath(
                    path_key=path_key,
                    operation_key=operation.key,
                    dxf_layer=operation.dxf_layer,
                    piece_instance_id="",
                    piece_label="",
                    closed=False,
                    direction="",
                    points=(),
                    start=None,
                    end=None,
                    preset_name="",
                    preset=None,
                    ready=False,
                    issues=(code,),
                    motions=(),
                    sequence=0,
                )
            )

    from almdina_erp.almdina_erp.domain.cnc.perimeter import (
        CUT_PATH_INTERNAL_SEQUENCE_KEY,
        SHEET_PERIMETER_PATH_KEY,
    )

    ordered_path_keys = [str(key) for key in (path_execution_order or ())]
    execution_rank = {key: index for index, key in enumerate(ordered_path_keys)}
    perimeter_rank = execution_rank.get(SHEET_PERIMETER_PATH_KEY)
    internal_rank = execution_rank.get(CUT_PATH_INTERNAL_SEQUENCE_KEY)

    def _path_sort_rank(path: CncToolpath) -> int:
        if perimeter_rank is None and internal_rank is None:
            return execution_rank.get(path.path_key, len(execution_rank))
        if path.path_key == SHEET_PERIMETER_PATH_KEY:
            return perimeter_rank if perimeter_rank is not None else len(execution_rank)
        if path.operation_key == "cut_path":
            # Stable contract: internals share one bucket; only perimeter moves.
            if internal_rank is not None:
                return internal_rank
            return 1 if perimeter_rank == 0 else 0
        return execution_rank.get(path.path_key, len(execution_rank) + 1)

    operations: list[CncOperationProgram] = []
    for key in order:
        paths = grouped.get(key) or []
        paths.sort(
            key=lambda path: (
                _path_sort_rank(path),
                (path.start or (0.0, 0.0))[1],
                (path.start or (0.0, 0.0))[0],
                path.path_key,
            )
        )
        numbered = [
            CncToolpath(
                path_key=path.path_key,
                operation_key=path.operation_key,
                dxf_layer=path.dxf_layer,
                piece_instance_id=path.piece_instance_id,
                piece_label=path.piece_label,
                closed=path.closed,
                direction=path.direction,
                points=path.points,
                start=path.start,
                end=path.end,
                preset_name=path.preset_name,
                preset=path.preset,
                ready=path.ready,
                issues=path.issues,
                motions=path.motions,
                sequence=index,
            )
            for index, path in enumerate(paths, start=1)
        ]
        if not numbered:
            continue
        operations.append(
            CncOperationProgram(
                operation_key=key,
                dxf_layer=numbered[0].dxf_layer,
                sequence=len(operations) + 1,
                toolpaths=tuple(numbered),
            )
        )
    geometry_ready = (
        not issues
        and all(path.ready for operation in operations for path in operation.toolpaths)
        and bool(operations)
    )
    return CncBoardProgram(
        sheet_no=int(sheet_no),
        ready=geometry_ready,
        coordinate_space=COORDINATE_SPACE,
        machine_origin=MACHINE_ORIGIN,
        depth_convention=DEPTH_CONVENTION,
        sheet_width_mm=sheet_width_mm,
        sheet_length_mm=sheet_length_mm,
        cut_path_early=early,
        cut_path_early_confirmed=bool(early and cut_path_early_confirmed),
        issues=tuple(issues),
        operations=tuple(operations),
        geometry_ready=geometry_ready,
        machine_ready=False,
        nc_export_ready=geometry_ready,
    )


def _empty_program(
    sheet_no: int,
    issues: list[tuple[str, str]],
    early: bool,
    confirmed: bool,
    width: float | None,
    length: float | None,
) -> CncBoardProgram:
    return CncBoardProgram(
        sheet_no=int(sheet_no),
        ready=False,
        coordinate_space=COORDINATE_SPACE,
        machine_origin=MACHINE_ORIGIN,
        depth_convention=DEPTH_CONVENTION,
        sheet_width_mm=width,
        sheet_length_mm=length,
        cut_path_early=early,
        cut_path_early_confirmed=bool(early and confirmed),
        issues=tuple(issues),
        operations=(),
        geometry_ready=False,
        machine_ready=False,
        nc_export_ready=False,
    )


def chain_line_paths(
    segments: Sequence[tuple[tuple[float, float], tuple[float, float]]],
) -> list[tuple[tuple[tuple[float, float], ...], bool]]:
    """Join connected lines, splitting a branch instead of choosing a route."""

    return _chain_lines(segments)


def program_payload(program: CncBoardProgram) -> dict[str, object]:
    """JSON-ready view. Depth stays a positive millimetre depth, never a Z word."""

    return {
        "sheet_no": program.sheet_no,
        "ready": program.ready,
        "geometry_ready": program.geometry_ready,
        "machine_ready": program.machine_ready,
        "nc_export_ready": program.nc_export_ready,
        "coordinate_space": program.coordinate_space,
        "machine_origin": program.machine_origin,
        "depth_convention": program.depth_convention,
        "sheet_width_mm": program.sheet_width_mm,
        "sheet_length_mm": program.sheet_length_mm,
        "cut_path_early": program.cut_path_early,
        "cut_path_early_confirmed": program.cut_path_early_confirmed,
        "issues": [{"code": code, "path_key": path_key} for code, path_key in program.issues],
        "operations": [
            {
                "operation_key": operation.operation_key,
                "dxf_layer": operation.dxf_layer,
                "sequence": operation.sequence,
                "toolpaths": [
                    {
                        "path_key": path.path_key,
                        "operation_key": path.operation_key,
                        "dxf_layer": path.dxf_layer,
                        "piece_instance_id": path.piece_instance_id,
                        "piece_label": path.piece_label,
                        "closed": path.closed,
                        "direction": path.direction,
                        "start": list(path.start) if path.start else None,
                        "end": list(path.end) if path.end else None,
                        "points": [[point[0], point[1]] for point in path.points],
                        "preset_name": path.preset_name,
                        "preset": path.preset,
                        "ready": path.ready,
                        "issues": list(path.issues),
                        "sequence": path.sequence,
                        "motions": [
                            {
                                "kind": motion.kind,
                                "x_mm": motion.x_mm,
                                "y_mm": motion.y_mm,
                                "depth_mm": motion.depth_mm,
                            }
                            for motion in path.motions
                        ],
                    }
                    for path in operation.toolpaths
                ],
            }
            for operation in program.operations
        ],
    }


__all__ = [
    "CHAIN_TOLERANCE_MM",
    "CncBoardProgram",
    "CncMotion",
    "CncOperationProgram",
    "CncSourceEntity",
    "CncToolpath",
    "build_board_program",
    "chain_line_paths",
    "orient_path",
    "program_payload",
]
