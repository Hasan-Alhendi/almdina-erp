"""Compile one sheet program from the approved plan.

CUT_PATH centers use the approved kerf offset and are not accepted when the
selected tool diameter differs. Liner, handle recess, and rear groove reuse
the existing cutter-center toolpath when the approved piece has its mill
settings. This module does not nest, approve, or write a machine file.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from almdina_erp.almdina_erp.domain.cnc.operational_file import (
    OperationalFileError,
    _fingerprint,
    catalog_sheet,
)
from almdina_erp.almdina_erp.domain.cnc.operations import (
    CNC_OPERATIONS_BY_KEY,
    DEFAULT_MACHINING_ORDER,
)
from almdina_erp.almdina_erp.domain.cnc.perimeter import (
    PERIMETER_JOIN_CONNECTED,
    SHEET_PERIMETER_PATH_KEY,
    extract_connected_perimeter,
    normalize_perimeter_join_mode,
    polyline_segments,
    prefer_uploaded_perimeter_polyline,
    remaining_segments_after_perimeter,
)
from almdina_erp.almdina_erp.domain.cnc.program import (
    CncSourceEntity,
    build_board_program,
    chain_line_paths,
    program_payload,
)
from almdina_erp.almdina_erp.domain.cnc.tool_preset import ToolPresetError, normalize_tool_preset
from almdina_erp.almdina_erp.domain.cutting.cutter_center_paths import (
    classify_saw_center_segments,
    cutter_center_paths,
    cutter_center_segments,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import point_in_polygon
from almdina_erp.almdina_erp.domain.cutting.finished_piece_geometry import (
    resolve_finished_geometry_mm,
)
from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    LinerGeometryError,
    LinerPiece,
    inverse_transform_point,
    liner_region_polygon_mm,
    piece_quarter_turns,
    sawn_liner_ends,
    transform_point,
)
from almdina_erp.almdina_erp.domain.cutting.machining_overlay import (
    generate_liner_set_toolpaths,
    generate_toolpath,
    machining_values,
)
from almdina_erp.almdina_erp.domain.orders.extra_addons import EXTRA_OVERLAY_LAYER_BY_KIND
from almdina_erp.almdina_erp.domain.orders.liner_specs import DoorLinerError, door_liners_from_source


_BIND_TOLERANCE_MM = 0.25
_GENERATED = "generated"
_PRESENT = "uploaded_present"
_LEGACY = "uploaded_legacy"
_UNKNOWN = "uploaded_unknown"


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _positive(value: Any) -> float | None:
    number = _number(value)
    if number is None or number <= 0:
        return None
    return number


def _has(source: Mapping[str, Any] | None, key: str) -> bool:
    return isinstance(source, Mapping) and key in source and source.get(key) is not None


def _sheet_record(snapshot: Mapping[str, Any], sheet_no: int) -> Mapping[str, Any]:
    sheets = snapshot.get("sheets")
    if isinstance(sheets, (str, bytes)) or not isinstance(sheets, Sequence):
        return {}
    for index, sheet in enumerate(sheets, start=1):
        if isinstance(sheet, Mapping) and int(sheet.get("sheet_no") or index) == int(sheet_no):
            return sheet
    return {}


def _trim_cm(snapshot: Mapping[str, Any], sheet: Mapping[str, Any], axis: str) -> float:
    trim_key = "applied_trim_width_cm" if axis == "x" else "applied_trim_length_cm"
    full_key = "full_width_cm" if axis == "x" else "full_length_cm"
    usable_key = "usable_width_cm" if axis == "x" else "usable_length_cm"
    plan_full_key = "full_board_width_cm" if axis == "x" else "full_board_length_cm"
    plan_usable_key = "usable_board_width_cm" if axis == "x" else "usable_board_length_cm"
    if _has(sheet, trim_key):
        return max(0.0, _number(sheet.get(trim_key)) or 0.0)
    sheet_full = _number(sheet.get(full_key)) or 0.0
    sheet_usable = _number(sheet.get(usable_key)) or 0.0
    if sheet_full > sheet_usable > 0:
        return (sheet_full - sheet_usable) / 2.0
    if _has(snapshot, trim_key):
        return max(0.0, _number(snapshot.get(trim_key)) or 0.0)
    plan_full = _number(snapshot.get(plan_full_key)) or 0.0
    plan_usable = _number(snapshot.get(plan_usable_key)) or 0.0
    if plan_full > plan_usable > 0:
        return (plan_full - plan_usable) / 2.0
    return max(0.0, _number(snapshot.get("trim_cm")) or 0.0)


def _sheet_size_mm(snapshot: Mapping[str, Any], sheet: Mapping[str, Any]) -> tuple[float | None, float | None]:
    width_cm = _positive(sheet.get("full_width_cm")) or _positive(snapshot.get("full_board_width_cm"))
    length_cm = _positive(sheet.get("full_length_cm")) or _positive(snapshot.get("full_board_length_cm"))
    return (
        None if width_cm is None else width_cm * 10.0,
        None if length_cm is None else length_cm * 10.0,
    )


def _kerf_mm(snapshot: Mapping[str, Any]) -> float | None | str:
    millimetres = _number(snapshot.get("kerf_mm")) if _has(snapshot, "kerf_mm") else None
    centimetres = _number(snapshot.get("kerf_cm")) if _has(snapshot, "kerf_cm") else None
    from_centimetres = None if centimetres is None else centimetres * 10.0
    if millimetres is not None and from_centimetres is not None and abs(millimetres - from_centimetres) > 0.05:
        return "conflict"
    chosen = millimetres if millimetres is not None else from_centimetres
    if chosen is None or chosen <= 0:
        return None
    return chosen


def _to_sheet(points: Sequence[Sequence[float]], *, trim_x: float, trim_y: float, length_mm: float) -> list[tuple[float, float]] | None:
    converted: list[tuple[float, float]] = []
    for point in points:
        if isinstance(point, (str, bytes)) or len(point) < 2:
            return None
        x = _number(point[0])
        y = _number(point[1])
        if x is None or y is None:
            return None
        converted.append((trim_x + x, length_mm - trim_y - y))
    return converted


def _point_segment_distance(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-12:
        return math.dist(point, start)
    ratio = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_sq
    ratio = min(1.0, max(0.0, ratio))
    return math.dist(point, (start[0] + ratio * dx, start[1] + ratio * dy))


def _distance_to_ring(point: tuple[float, float], ring: Sequence[tuple[float, float]]) -> float:
    if len(ring) < 2:
        return math.inf
    count = len(ring)
    return min(
        _point_segment_distance(point, ring[index], ring[(index + 1) % count])
        for index in range(count)
    )


def _midpoint(points: Sequence[tuple[float, float]]) -> tuple[float, float]:
    if len(points) == 1:
        return points[0]
    total = sum(math.dist(start, end) for start, end in zip(points, points[1:]))
    target = total / 2.0
    walked = 0.0
    for start, end in zip(points, points[1:]):
        length = math.dist(start, end)
        if walked + length >= target and length > 0:
            ratio = (target - walked) / length
            return (start[0] + (end[0] - start[0]) * ratio, start[1] + (end[1] - start[1]) * ratio)
        walked += length
    return points[-1]


def _usable_geometry(geometry: Mapping[str, Any] | None) -> tuple[list[list[float]], list[list[list[float]]]] | str:
    if not isinstance(geometry, Mapping):
        return "finished_geometry_missing"
    if geometry.get("unit") not in (None, "", "mm") or geometry.get("coordinate_space") not in (
        None,
        "",
        "usable_sheet",
    ):
        return "geometry_invalid"
    outer = geometry.get("outer")
    if isinstance(outer, (str, bytes)) or not isinstance(outer, Sequence) or len(outer) < 3:
        return "finished_geometry_missing"
    holes = geometry.get("holes") or []
    if isinstance(holes, (str, bytes)) or not isinstance(holes, Sequence):
        return "geometry_invalid"
    return (
        [list(point) for point in outer],
        [[list(point) for point in hole] for hole in holes if isinstance(hole, Sequence)],
    )


def _finished_geometry_for_piece(piece: Mapping[str, Any]) -> tuple[list[list[float]], list[list[list[float]]]] | str:
    """Use stored geometry when valid; otherwise rebuild from approved placement."""

    stored = piece.get("geometry") if isinstance(piece.get("geometry"), Mapping) else None
    parsed = _usable_geometry(stored)
    if not isinstance(parsed, str):
        return parsed
    if parsed != "finished_geometry_missing":
        return parsed
    rebuilt = resolve_finished_geometry_mm(
        stored_geometry=None,
        piece=piece,
        stored_piece=piece,
    )
    if rebuilt is None:
        return "finished_geometry_missing"
    return _usable_geometry(rebuilt)


def _hole_keys(piece_id: str, holes: Sequence[Any]) -> list[tuple[str, Any]]:
    ranked = sorted((_fingerprint(hole), hole) for hole in holes)
    seen: dict[str, int] = {}
    keys: list[tuple[str, Any]] = []
    for digest, hole in ranked:
        seen[digest] = seen.get(digest, 0) + 1
        suffix = digest if seen[digest] == 1 else f"{digest}:{seen[digest]}"
        keys.append((f"cut_path:{piece_id}:hole:{suffix}", hole))
    return keys


def _complete_order(requested: Sequence[str], present: set[str]) -> list[str]:
    """Keep a requested order and insert newly present operations by default rank."""

    from almdina_erp.almdina_erp.domain.cnc.operational_file import merge_operation_order

    known = [
        str(raw or "").strip()
        for raw in requested
        if str(raw or "").strip() in CNC_OPERATIONS_BY_KEY
    ]
    return list(merge_operation_order(sorted(present), known))


def _entity(
    *,
    layer: str,
    points: Sequence[tuple[float, float]],
    closed: bool,
    entity_type: str,
    role: str,
    ring: str,
    path_key: str = "",
    piece_id: str = "",
    piece_label: str = "",
) -> CncSourceEntity:
    return CncSourceEntity(
        layer=layer,
        points=tuple((float(point[0]), float(point[1])) for point in points),
        closed=closed,
        entity_type=entity_type,
        role=role,
        ring=ring,
        path_key=path_key,
        piece_instance_id=piece_id,
        piece_label=piece_label,
    )


def _bind_open_path(
    points: Sequence[tuple[float, float]],
    hosts: Sequence[dict[str, Any]],
    radius: float,
) -> tuple[str, str, str, str]:
    midpoint = _midpoint(points)
    hits: list[tuple[float, dict[str, Any], str]] = []
    for host in hosts:
        outer_distance = _distance_to_ring(midpoint, host["outer"])
        hole_hits = [
            ( _distance_to_ring(midpoint, hole), key)
            for hole, key in zip(host["holes"], host["hole_keys"])
        ]
        hole_distance = min((distance for distance, _key in hole_hits), default=math.inf)
        nearest = min(outer_distance, hole_distance)
        if nearest <= radius + _BIND_TOLERANCE_MM:
            kind = "hole" if hole_distance + 0.05 < outer_distance else "outer"
            hits.append((nearest, host, kind))
    if len(hits) != 1:
        return "", "", "open", ""
    _distance, host, kind = hits[0]
    if kind == "hole":
        hole_key = host["hole_keys"][0] if len(host["hole_keys"]) == 1 else ""
        return host["piece_id"], host["label"], "hole" if hole_key else "unknown", hole_key
    return host["piece_id"], host["label"], "outer", host["outer_key"]


def _cut_center_segments(entities: Sequence[CncSourceEntity]) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for entity in entities:
        if entity.layer.upper() != "CUT_PATH" or entity.role != "tool_center":
            continue
        segments.extend(polyline_segments(entity.points, closed=entity.closed))
    return segments


def _apply_connected_perimeter(
    entities: list[CncSourceEntity],
    *,
    uploaded: Mapping[str, Any] | None,
    blocked_path,
) -> list[CncSourceEntity]:
    cut_entities = [
        entity
        for entity in entities
        if entity.layer.upper() == "CUT_PATH" and entity.role == "tool_center"
    ]
    other_entities = [
        entity
        for entity in entities
        if not (entity.layer.upper() == "CUT_PATH" and entity.role == "tool_center")
    ]
    if not cut_entities:
        blocked_path("perimeter_unavailable", SHEET_PERIMETER_PATH_KEY)
        return entities
    network = _cut_center_segments(cut_entities)
    try:
        preferred = None
        if isinstance(uploaded, Mapping):
            preferred = prefer_uploaded_perimeter_polyline(
                list(uploaded.get("cut_paths") or []),
                network,
            )
        perimeter = preferred or extract_connected_perimeter(network)
        leftovers = remaining_segments_after_perimeter(network, perimeter)
    except OperationalFileError as exc:
        blocked_path(exc.code, SHEET_PERIMETER_PATH_KEY)
        return entities
    rebuilt: list[CncSourceEntity] = list(other_entities)
    rebuilt.append(
        _entity(
            layer="CUT_PATH",
            points=perimeter.points,
            closed=True,
            entity_type="LWPOLYLINE",
            role="tool_center",
            ring="outer",
            path_key=SHEET_PERIMETER_PATH_KEY,
            piece_id="",
            piece_label="",
        )
    )
    for points, closed in chain_line_paths(leftovers):
        if len(points) < 2:
            continue
        rebuilt.append(
            _entity(
                layer="CUT_PATH",
                points=points,
                closed=closed,
                entity_type="LWPOLYLINE" if len(points) > 2 or closed else "LINE",
                role="tool_center",
                ring="outer" if closed else "open",
                path_key="",
                piece_id="",
                piece_label="",
            )
        )
    return rebuilt


def compile_sheet_program(
    *,
    sheet_no: int,
    pieces: Sequence[Mapping[str, Any]],
    snapshot: Mapping[str, Any] | None,
    operation_presets: Mapping[str, str],
    path_overrides: Mapping[str, str],
    operation_order: Sequence[str],
    known_presets: Mapping[str, Mapping[str, Any]],
    cut_path_early_confirmed: bool = False,
    manufacturing_mode: str = _GENERATED,
    uploaded: Mapping[str, Any] | None = None,
    perimeter_join_mode: str = "separate",
    cut_path_sequence: Sequence[str] | None = None,
    perimeter_cut_early_confirmed: bool = False,
) -> dict[str, Any]:
    """Return the JSON program for one sheet. Nothing is stored."""

    sheet_pieces = [
        piece for piece in pieces if int(piece.get("sheet_no") or 0) == int(sheet_no)
    ]
    if int(sheet_no) <= 0 or not sheet_pieces:
        raise OperationalFileError("sheet_not_in_plan")
    join_mode = normalize_perimeter_join_mode(perimeter_join_mode)
    catalog = catalog_sheet(
        int(sheet_no),
        sheet_pieces,
        include_sheet_perimeter=join_mode == PERIMETER_JOIN_CONNECTED,
    )
    plan = snapshot if isinstance(snapshot, Mapping) else {}
    sheet = _sheet_record(plan, int(sheet_no))
    width_mm, length_mm = _sheet_size_mm(plan, sheet)
    trim_x = _trim_cm(plan, sheet, "x") * 10.0
    trim_y = _trim_cm(plan, sheet, "y") * 10.0
    kerf = _kerf_mm(plan)
    mode = str(manufacturing_mode or _GENERATED)
    present = {path.operation_key for path in catalog.paths}
    order = _complete_order(operation_order, present)
    blocked: list[dict[str, str]] = []
    entities: list[CncSourceEntity] = []
    hosts: list[dict[str, Any]] = []

    def blocked_path(code: str, path_key: str) -> None:
        blocked.append({"code": code, "path_key": path_key})

    if width_mm is None or length_mm is None:
        program = build_board_program(
            sheet_no=int(sheet_no),
            entities=(),
            operation_order=order,
            operation_presets=operation_presets,
            path_overrides=path_overrides,
            known_presets=known_presets,
            cut_path_early_confirmed=cut_path_early_confirmed,
            units="mm",
            frame_origin_mm=None,
            sheet_width_mm=width_mm,
            sheet_length_mm=length_mm,
            blocked_catalog_paths=blocked,
        )
        return program_payload(program)

    units = "mm"
    if isinstance(uploaded, Mapping):
        raw_units = str(uploaded.get("units") or "mm")
        if raw_units == "unspecified":
            units = "unspecified"
        elif raw_units != "mm":
            units = "unknown"
    if isinstance(uploaded, Mapping) and uploaded.get("unsupported"):
        blocked_path("geometry_invalid", "")

    shapes: list[tuple[list[tuple[float, float]], list[list[tuple[float, float]]]]] = []
    for piece in sheet_pieces:
        piece_id = str(piece.get("piece_instance_id") or "")
        label = str(piece.get("label") or "")
        parsed = _finished_geometry_for_piece(piece)
        if isinstance(parsed, str):
            for path in catalog.paths:
                if path.piece_instance_id == piece_id and path.operation_key == "cut_path" and path.path_key.endswith(":outer"):
                    blocked_path(parsed, path.path_key)
            continue
        outer_raw, holes_raw = parsed
        outer = _to_sheet(outer_raw, trim_x=trim_x, trim_y=trim_y, length_mm=length_mm)
        hole_pairs = []
        hole_failed = outer is None
        if outer is not None:
            for key, hole in _hole_keys(piece_id, holes_raw):
                converted = _to_sheet(hole, trim_x=trim_x, trim_y=trim_y, length_mm=length_mm)
                if converted is None:
                    hole_failed = True
                    break
                hole_pairs.append((key, converted))
        if hole_failed or outer is None:
            blocked_path("geometry_invalid", f"cut_path:{piece_id}:outer")
            continue
        hosts.append(
            {
                "piece_id": piece_id,
                "label": label,
                "outer": outer,
                "outer_key": f"cut_path:{piece_id}:outer",
                "holes": [points for _key, points in hole_pairs],
                "hole_keys": [key for key, _points in hole_pairs],
            }
        )
        shapes.append((outer, [points for _key, points in hole_pairs]))

    uploaded_overlays = list((uploaded or {}).get("overlays") or []) if isinstance(uploaded, Mapping) else []
    use_file_overlays = mode in {_PRESENT, _LEGACY, _UNKNOWN} and bool(uploaded_overlays)
    if kerf == "conflict" or kerf is None:
        if mode in {_GENERATED, _PRESENT}:
            blocked_path("kerf_unknown", "")
    elif mode in {_GENERATED, _PRESENT} and shapes:
        radius = float(kerf) / 2.0
        generated = cutter_center_paths(shapes, radius)
        expected = cutter_center_segments(shapes, radius)
        use_generated = mode == _GENERATED
        if mode == _PRESENT:
            observed = list((uploaded or {}).get("cut_segments") or [])
            read_error = str(uploaded.get("read_error") or "") if isinstance(uploaded, Mapping) else ""
            if not isinstance(uploaded, Mapping) or uploaded.get("unreadable"):
                use_generated = False
                blocked_path("dxf_unreadable", "")
            elif read_error:
                use_generated = False
                blocked_path(read_error, "")
            elif uploaded.get("origin") is None and not observed:
                use_generated = False
                blocked_path("dxf_unreadable", "")
            elif str(uploaded.get("units") or "mm") != "mm":
                use_generated = False
            elif classify_saw_center_segments(observed, expected) != "match":
                use_generated = False
                for segment in observed:
                    if len(segment) != 2:
                        continue
                    entities.append(
                        _entity(
                            layer="CUT_PATH",
                            points=(tuple(segment[0]), tuple(segment[1])),
                            closed=False,
                            entity_type="LINE",
                            role="unmatched_cut",
                            ring="open",
                        )
                    )
                if not observed:
                    blocked_path("cut_path_does_not_match_approved_centers", "")
            else:
                use_generated = True
        if use_generated:
            rings: list[tuple[str, str, str, str]] = []
            for host in hosts:
                rings.append(("outer", host["piece_id"], host["label"], host["outer_key"]))
                for key in host["hole_keys"]:
                    rings.append(("hole", host["piece_id"], host["label"], key))
            if generated and all(path.closed for path in generated) and len(generated) == len(rings):
                for path, (ring, piece_id, label, path_key) in zip(generated, rings):
                    entities.append(
                        _entity(
                            layer="CUT_PATH",
                            points=path.points,
                            closed=True,
                            entity_type="LWPOLYLINE",
                            role="tool_center",
                            ring=ring,
                            path_key=path_key,
                            piece_id=piece_id,
                            piece_label=label,
                        )
                    )
            else:
                for path in generated:
                    piece_id, label, ring, path_key = _bind_open_path(path.points, hosts, radius)
                    entities.append(
                        _entity(
                            layer="CUT_PATH",
                            points=path.points,
                            closed=path.closed,
                            entity_type="LWPOLYLINE",
                            role="tool_center",
                            ring=ring if path.closed else "open",
                            path_key=path_key if piece_id else "",
                            piece_id=piece_id,
                            piece_label=label,
                        )
                    )
    elif mode == _LEGACY:
        legacy_error = str(uploaded.get("read_error") or "") if isinstance(uploaded, Mapping) else ""
        if legacy_error:
            blocked_path(legacy_error, "")
        elif not _uploaded_frame_ready(uploaded):
            blocked_path("dxf_unreadable", "")
        else:
            _append_uploaded_cuts(entities, uploaded, role="finished_boundary")
    elif mode == _UNKNOWN:
        unknown_error = str(uploaded.get("read_error") or "") if isinstance(uploaded, Mapping) else ""
        if unknown_error:
            blocked_path(unknown_error, "")
        elif not _uploaded_frame_ready(uploaded):
            blocked_path("dxf_unreadable", "")
        else:
            _append_uploaded_cuts(entities, uploaded, role="unverified")
    elif mode == _PRESENT:
        blocked_path("dxf_unreadable", "")

    if use_file_overlays:
        _append_file_overlays(entities, uploaded_overlays, hosts)
    else:
        _append_snapshot_overlays(entities, sheet_pieces, trim_x=trim_x, trim_y=trim_y, length_mm=length_mm)

    absorbed = _apply_parametric_mills(
        entities,
        sheet_pieces,
        catalog,
        trim_x=trim_x,
        trim_y=trim_y,
        length_mm=length_mm,
        width_mm=width_mm,
        operation_presets=operation_presets,
        path_overrides=path_overrides,
        known_presets=known_presets,
        blocked_path=blocked_path,
        manufacturing_mode=mode,
        require_upload_match=mode == _PRESENT and use_file_overlays,
    )
    extracted = {entity.path_key for entity in entities if entity.path_key}
    extracted_cut = any(entity.layer.upper() == "CUT_PATH" for entity in entities)
    covered_overlays = {
        (entity.piece_instance_id, kind)
        for entity in entities
        if entity.piece_instance_id
        for kind, layer in EXTRA_OVERLAY_LAYER_BY_KIND.items()
        if entity.layer.upper() == layer.upper()
    }
    kerf_blocked = any(item["code"] == "kerf_unknown" for item in blocked)
    for path in catalog.paths:
        if path.path_key in extracted or path.path_key in absorbed:
            continue
        if (path.piece_instance_id, path.operation_key) in covered_overlays:
            continue
        if path.operation_key == "cut_path" and (extracted_cut or kerf_blocked):
            continue
        if path.operation_key == "cut_path":
            continue
        # Filled by the connected-perimeter pass below; do not mark missing yet.
        if path.operation_key == "sheet_perimeter":
            continue
        if not any(item["path_key"] == path.path_key for item in blocked):
            blocked_path("toolpath_missing", path.path_key)

    if join_mode == PERIMETER_JOIN_CONNECTED:
        entities = _apply_connected_perimeter(
            entities,
            uploaded=uploaded if isinstance(uploaded, Mapping) else None,
            blocked_path=blocked_path,
        )
        extracted = {entity.path_key for entity in entities if entity.path_key}
        if SHEET_PERIMETER_PATH_KEY not in extracted and not any(
            item["path_key"] == SHEET_PERIMETER_PATH_KEY for item in blocked
        ):
            blocked_path("perimeter_unavailable", SHEET_PERIMETER_PATH_KEY)
    # Legacy cut_path_sequence is ignored for execution; operation_order wins.
    _ = cut_path_sequence
    _ = perimeter_cut_early_confirmed

    layer_cut = str(operation_presets.get("cut_path") or "").strip()
    shared_exists = any(
        entity.layer.upper() == "CUT_PATH"
        and entity.role == "tool_center"
        and not entity.piece_instance_id
        and entity.path_key != SHEET_PERIMETER_PATH_KEY
        for entity in entities
    )
    ambiguous = shared_exists and any(
        str(path_overrides.get(path.path_key) or "").strip() not in {"", layer_cut}
        for path in catalog.paths
        if path.operation_key == "cut_path" and path.path_key != SHEET_PERIMETER_PATH_KEY
    )
    # Ensure connected perimeter inherits the cut_path preset when omitted.
    presets = dict(operation_presets)
    if join_mode == PERIMETER_JOIN_CONNECTED and not str(presets.get("sheet_perimeter") or "").strip():
        inherited = str(presets.get("cut_path") or "").strip()
        if inherited:
            presets["sheet_perimeter"] = inherited
    overrides = {str(key): value for key, value in path_overrides.items()}
    program = build_board_program(
        sheet_no=int(sheet_no),
        entities=entities,
        operation_order=order,
        operation_presets=presets,
        path_overrides=overrides,
        known_presets=known_presets,
        cut_path_early_confirmed=cut_path_early_confirmed,
        units=units,
        frame_origin_mm=(0.0, 0.0),
        sheet_width_mm=width_mm,
        sheet_length_mm=length_mm,
        blocked_catalog_paths=blocked,
        shared_cut_ambiguous=ambiguous,
        approved_kerf_mm=float(kerf) if isinstance(kerf, (int, float)) and not isinstance(kerf, bool) else None,
        path_execution_order=(),
    )
    return program_payload(program)


def _uploaded_frame_ready(uploaded: Mapping[str, Any] | None) -> bool:
    return (
        isinstance(uploaded, Mapping)
        and not uploaded.get("unreadable")
        and uploaded.get("origin") is not None
        and str(uploaded.get("units") or "mm") == "mm"
    )


def _append_uploaded_cuts(entities: list[CncSourceEntity], uploaded: Mapping[str, Any] | None, *, role: str) -> None:
    if not isinstance(uploaded, Mapping) or uploaded.get("unreadable") or uploaded.get("origin") is None:
        return
    for segment in uploaded.get("cut_segments") or []:
        if not isinstance(segment, Sequence) or len(segment) != 2:
            continue
        entities.append(
            _entity(
                layer="CUT_PATH",
                points=(tuple(segment[0]), tuple(segment[1])),
                closed=False,
                entity_type="LINE",
                role=role,
                ring="open",
            )
        )


def _append_file_overlays(
    entities: list[CncSourceEntity],
    overlays: Sequence[Mapping[str, Any]],
    hosts: Sequence[dict[str, Any]],
) -> None:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for overlay in overlays:
        if not isinstance(overlay, Mapping):
            continue
        layer = str(overlay.get("layer") or "")
        kind = next((key for key, name in EXTRA_OVERLAY_LAYER_BY_KIND.items() if name.upper() == layer.upper()), "")
        if not kind:
            continue
        points = overlay.get("points") or []
        if not isinstance(points, Sequence) or isinstance(points, (str, bytes)) or len(points) < 2:
            continue
        midpoint = _midpoint([(float(point[0]), float(point[1])) for point in points])
        host = next((item for item in hosts if point_in_polygon(midpoint, item["outer"])), None)
        piece_id = host["piece_id"] if host else ""
        grouped.setdefault((kind, piece_id), []).append(overlay)
    for (kind, piece_id), rows in grouped.items():
        host = next((item for item in hosts if item["piece_id"] == piece_id), None)
        label = host["label"] if host else ""
        for overlay in rows:
            closed = bool(overlay.get("closed"))
            points = [(float(point[0]), float(point[1])) for point in overlay["points"]]
            entities.append(
                _entity(
                    layer=EXTRA_OVERLAY_LAYER_BY_KIND[kind],
                    points=points,
                    closed=closed,
                    entity_type=str(overlay.get("entity_type") or "LWPOLYLINE"),
                    role="region_boundary" if closed else "mill_path_unverified",
                    ring="unknown" if closed else "open",
                    piece_id=piece_id,
                    piece_label=label,
                )
            )


def _append_snapshot_overlays(
    entities: list[CncSourceEntity],
    pieces: Sequence[Mapping[str, Any]],
    *,
    trim_x: float,
    trim_y: float,
    length_mm: float,
) -> None:
    for piece in pieces:
        piece_id = str(piece.get("piece_instance_id") or "")
        label = str(piece.get("label") or "")
        overlays = piece.get("overlays") or []
        if isinstance(overlays, (str, bytes)) or not isinstance(overlays, Sequence):
            continue
        prepared = []
        for overlay in overlays:
            if not isinstance(overlay, Mapping):
                continue
            kind = str(overlay.get("kind") or "").strip()
            if kind not in EXTRA_OVERLAY_LAYER_BY_KIND:
                continue
            geometry = overlay.get("geometry") if isinstance(overlay.get("geometry"), Mapping) else None
            if geometry is None:
                continue
            path = geometry.get("path")
            if isinstance(path, (str, bytes)) or not isinstance(path, Sequence) or len(path) < 2:
                continue
            prepared.append((f"{kind}:{piece_id}:overlay:{_fingerprint(geometry)}", kind, geometry, path))
        prepared.sort(key=lambda item: item[0])
        seen: dict[str, int] = {}
        for base, kind, geometry, path in prepared:
            seen[base] = seen.get(base, 0) + 1
            path_key = base if seen[base] == 1 else f"{base}:{seen[base]}"
            closed = bool(geometry.get("closed"))
            verified_center = bool(geometry.get("toolpath")) and not closed
            points = _to_sheet(path, trim_x=trim_x, trim_y=trim_y, length_mm=length_mm)
            if points is None:
                entities.append(
                    _entity(
                        layer=EXTRA_OVERLAY_LAYER_BY_KIND[kind],
                        points=(),
                        closed=False,
                        entity_type="LWPOLYLINE",
                        role="invalid",
                        ring="unknown",
                        path_key=path_key,
                        piece_id=piece_id,
                        piece_label=label,
                    )
                )
                continue
            if closed:
                role = "region_boundary"
            elif verified_center:
                role = "tool_center"
            else:
                role = "mill_path_unverified"
            entities.append(
                _entity(
                    layer=EXTRA_OVERLAY_LAYER_BY_KIND[kind],
                    points=points,
                    closed=closed,
                    entity_type="LINE" if str(geometry.get("entity_type") or "").upper() == "LINE" else "LWPOLYLINE",
                    role=role,
                    ring="open" if not closed else "unknown",
                    path_key=path_key,
                    piece_id=piece_id,
                    piece_label=label,
                )
            )


def _preset_diameter(name: str, known: Mapping[str, Mapping[str, Any]]) -> float | None:
    raw = known.get(str(name or "").strip())
    if not isinstance(raw, Mapping):
        return None
    try:
        preset = normalize_tool_preset(raw)
    except ToolPresetError:
        return None
    if not preset.enabled:
        return None
    return float(preset.tool_diameter_mm)


def _placement(piece: Mapping[str, Any]) -> dict[str, Any] | None:
    width = _positive(piece.get("original_width_cm"))
    length = _positive(piece.get("original_length_cm"))
    origin_x = _number(piece.get("x_mm"))
    origin_y = _number(piece.get("y_mm"))
    if width is None or length is None or origin_x is None or origin_y is None:
        return None
    return {
        "piece_type": str(piece.get("piece_type") or "Regular"),
        "width_cm": width,
        "length_cm": length,
        "x_mm": origin_x,
        "y_mm": origin_y,
        "quarter_turns": piece_quarter_turns(piece),
        "mirrored": bool(int(piece.get("corner_mirrored") or 0)),
        "clipped_corner_position": str(piece.get("clipped_corner_position") or "Top Right"),
        "clipped_corner_width_cm": _number(piece.get("clipped_corner_width_cm")) or 0.0,
        "clipped_corner_length_cm": _number(piece.get("clipped_corner_length_cm")) or 0.0,
    }


def _same_polyline(
    left: Sequence[tuple[float, float]],
    right: Sequence[tuple[float, float]],
) -> bool:
    if len(left) < 2 or len(right) < 2:
        return False
    for candidate in (tuple(right), tuple(reversed(right))):
        if len(candidate) != len(left):
            continue
        if all(math.dist(start, end) <= 0.05 for start, end in zip(left, candidate)):
            return True
    return False


def _on_ring(points: Sequence[tuple[float, float]], ring: Sequence[tuple[float, float]]) -> bool:
    if len(points) < 2 or len(ring) < 2:
        return False
    edges = list(zip(ring, ring[1:]))
    if math.dist(ring[0], ring[-1]) > 0.5:
        edges.append((ring[-1], ring[0]))
    return all(
        min(_point_segment_distance(point, start, end) for start, end in edges) <= 0.5
        for point in points
    )


def _keep_mill_outline(entities: list[CncSourceEntity], piece_id: str, layer: str) -> bool:
    """Leave source mill geometry on the board when the cutter center cannot be calculated."""

    from dataclasses import replace

    kept = False
    updated: list[CncSourceEntity] = []
    for entity in entities:
        same_layer = entity.piece_instance_id == piece_id and entity.layer.upper() == layer.upper()
        if same_layer and len(entity.points) >= 2 and entity.role != "tool_center":
            updated.append(replace(entity, role="mill_diameter_required"))
            kept = True
            continue
        updated.append(entity)
    if kept:
        entities[:] = updated
    return kept


def _drop_layer(entities: list[CncSourceEntity], piece_id: str, layer: str) -> None:
    entities[:] = [
        entity
        for entity in entities
        if not (entity.piece_instance_id == piece_id and entity.layer.upper() == layer.upper())
    ]


def _layer_entities(
    entities: Sequence[CncSourceEntity],
    piece_id: str,
    layer: str,
) -> list[CncSourceEntity]:
    return [
        entity
        for entity in entities
        if entity.piece_instance_id == piece_id and entity.layer.upper() == layer.upper()
    ]


def _place_mill_path(
    path: Sequence[tuple[float, float]],
    placement: Mapping[str, Any],
    *,
    trim_x: float,
    trim_y: float,
    length_mm: float,
) -> list[tuple[float, float]] | None:
    width = float(placement["width_cm"]) * 10.0
    height = float(placement["length_cm"]) * 10.0
    placed = []
    for point in path:
        turned = transform_point(
            (float(point[0]), float(point[1])),
            mirrored=bool(placement.get("mirrored")),
            quarter_turns=int(placement["quarter_turns"]),
            width=width,
            height=height,
        )
        placed.append((turned[0] + float(placement["x_mm"]), turned[1] + float(placement["y_mm"])))
    return _to_sheet(placed, trim_x=trim_x, trim_y=trim_y, length_mm=length_mm)


def _to_canonical(
    sheet_points: Sequence[tuple[float, float]],
    placement: Mapping[str, Any],
    *,
    trim_x: float,
    trim_y: float,
    length_mm: float,
) -> list[tuple[float, float]]:
    width = float(placement["width_cm"]) * 10.0
    height = float(placement["length_cm"]) * 10.0
    canonical = []
    for point in sheet_points:
        usable = (point[0] - trim_x, length_mm - trim_y - point[1])
        local = (usable[0] - float(placement["x_mm"]), usable[1] - float(placement["y_mm"]))
        canonical.append(
            inverse_transform_point(
                local,
                mirrored=bool(placement.get("mirrored")),
                quarter_turns=int(placement["quarter_turns"]),
                width=width,
                height=height,
            )
        )
    return canonical


def _kind_specs(piece: Mapping[str, Any], kind: str, values: Mapping[str, Mapping[str, Any]]):
    if kind == "liner":
        try:
            liner_set = door_liners_from_source(piece)
        except DoorLinerError:
            return None
        if not liner_set.enabled or not liner_set.liners or liner_set.width_cm <= 0:
            return []
        if any(not str(spec.side or "").strip() for spec in liner_set.liners):
            return []
        return liner_set.width_cm, [
            {
                "id": spec.liner_id,
                "side": spec.side,
                "offset_cm": spec.offset_cm,
                "start_cm": spec.start_cm,
                "length_cm": spec.length_cm,
            }
            for spec in liner_set.liners
        ]
    spec = values[kind]
    if not spec["enabled"] or not str(spec["side"] or "").strip() or float(spec["width_cm"] or 0) <= 0:
        return []
    return float(spec["width_cm"]), [
        {
            "id": "primary",
            "side": spec["side"],
            "offset_cm": spec["offset_cm"],
            "start_cm": spec["start_cm"],
            "length_cm": spec["length_cm"],
        }
    ]


def _mill_issue(code: str) -> str:
    if code == "liner_narrower_than_cutter":
        return code
    if code == "side_unavailable":
        return code
    if code == "cutter_diameter_invalid":
        return "mill_diameter_required"
    return "mill_parameters_missing"


def _overlay_spec_keys(
    existing: Sequence[CncSourceEntity],
    catalog_keys: Sequence[str],
    specs: Sequence[Mapping[str, Any]],
    solos: Sequence[Sequence[tuple[float, float]]],
    liner_piece: LinerPiece,
    width_cm: float,
    placement: Mapping[str, Any],
    *,
    trim_x: float,
    trim_y: float,
    length_mm: float,
) -> dict[int, str]:
    found: dict[int, str] = {}
    for entity in existing:
        if entity.path_key not in catalog_keys or len(entity.points) < 2:
            continue
        canonical = _to_canonical(
            entity.points,
            placement,
            trim_x=trim_x,
            trim_y=trim_y,
            length_mm=length_mm,
        )
        hits = []
        for index, spec in enumerate(specs):
            if _same_polyline(canonical, tuple(solos[index])):
                hits.append(index)
                continue
            try:
                region = liner_region_polygon_mm(
                    liner_piece,
                    spec["side"],
                    spec["offset_cm"],
                    width_cm,
                    spec["start_cm"],
                    spec["length_cm"],
                )
            except LinerGeometryError:
                continue
            if _on_ring(canonical, region) and _on_ring(region, canonical):
                hits.append(index)
        if len(hits) == 1 and hits[0] not in found:
            found[hits[0]] = entity.path_key
    return found


def _bind_mill_paths(
    kind: str,
    piece_id: str,
    catalog_keys: Sequence[str],
    generated: Sequence[Sequence[tuple[float, float]]],
    solos: Sequence[Sequence[tuple[float, float]]],
    specs: Sequence[Mapping[str, Any]],
    overlay_keys: Mapping[int, str],
) -> tuple[list[str], set[str], bool]:
    matches = []
    for path in generated:
        matches.append([index for index, solo in enumerate(solos) if _same_polyline(path, solo)])
    merged = any(len(hits) != 1 for hits in matches) or len(generated) != len(specs)
    used: set[str] = set()
    bindings = []
    for index, hits in enumerate(matches):
        key = ""
        if len(hits) == 1:
            spec_id = str(specs[hits[0]]["id"])
            exact = f"{kind}:{piece_id}:{spec_id}"
            key = exact if exact in catalog_keys else overlay_keys.get(hits[0], "")
        if not key and len(catalog_keys) == 1 and len(generated) == 1:
            key = catalog_keys[0]
        if not key:
            key = f"{kind}:{piece_id}:merged:{_fingerprint([[round(point[0], 3), round(point[1], 3)] for point in generated[index]])}"
        bindings.append(key)
        if key in catalog_keys:
            used.add(key)
    return bindings, {key for key in catalog_keys if key not in used}, merged


def _effective_mill_diameter(
    catalog_keys: Sequence[str],
    kind: str,
    operation_presets: Mapping[str, str],
    path_overrides: Mapping[str, str],
    known_presets: Mapping[str, Mapping[str, Any]],
) -> float | None | str:
    """Return one diameter, None when missing, or ``conflict`` when paths disagree."""

    keys = list(catalog_keys) or [""]
    diameters: set[float] = set()
    for key in keys:
        name = str(path_overrides.get(key) or operation_presets.get(kind) or "").strip()
        diameter = _preset_diameter(name, known_presets)
        if diameter is None:
            return None
        diameters.add(round(diameter, 3))
    if len(diameters) != 1:
        return "conflict"
    return next(iter(diameters))


def _uploaded_matches_generated(
    existing: Sequence[CncSourceEntity],
    generated_sheet: Sequence[Sequence[tuple[float, float]]],
) -> bool:
    uploaded = [entity.points for entity in existing if len(entity.points) >= 2]
    if not uploaded:
        return False
    unused = list(range(len(uploaded)))
    for expected in generated_sheet:
        found = None
        for index in unused:
            if _same_polyline(uploaded[index], expected):
                found = index
                break
        if found is None:
            return False
        unused.remove(found)
    return not unused


def _apply_parametric_mills(
    entities: list[CncSourceEntity],
    pieces: Sequence[Mapping[str, Any]],
    catalog,
    *,
    trim_x: float,
    trim_y: float,
    length_mm: float,
    width_mm: float,
    operation_presets: Mapping[str, str],
    path_overrides: Mapping[str, str],
    known_presets: Mapping[str, Mapping[str, Any]],
    blocked_path,
    manufacturing_mode: str = _GENERATED,
    require_upload_match: bool = False,
) -> set[str]:
    """Replace a mill outline with the existing cutter-center path when it can be calculated."""

    absorbed: set[str] = set()
    board = (-trim_x, -trim_y, width_mm - trim_x, length_mm - trim_y)
    for piece in pieces:
        piece_id = str(piece.get("piece_instance_id") or "")
        label = str(piece.get("label") or "")
        if not piece_id:
            continue
        values = machining_values(piece)
        placement = _placement(piece)
        for kind in ("liner", "back_groove", "recessed_handle_cutout"):
            parsed = _kind_specs(piece, kind, values)
            if parsed is None:
                blocked_path("liner_specs_invalid", "")
                continue
            if not parsed:
                continue
            width_cm, specs = parsed
            layer = EXTRA_OVERLAY_LAYER_BY_KIND[kind]
            catalog_keys = [
                path.path_key
                for path in catalog.paths
                if path.piece_instance_id == piece_id and path.operation_key == kind
            ]
            existing = _layer_entities(entities, piece_id, layer)
            if not catalog_keys and not existing:
                continue
            if manufacturing_mode in {_LEGACY, _UNKNOWN}:
                continue
            open_centers = [
                entity for entity in existing if not entity.closed and entity.role == "tool_center"
            ]
            if placement is None:
                if open_centers:
                    continue
                _drop_layer(entities, piece_id, layer)
                for key in catalog_keys:
                    blocked_path("mill_placement_unknown", key)
                continue
            diameter = _effective_mill_diameter(
                catalog_keys, kind, operation_presets, path_overrides, known_presets
            )
            if diameter == "conflict":
                _drop_layer(entities, piece_id, layer)
                for key in catalog_keys:
                    blocked_path("tool_diameter_conflict", key)
                continue
            if diameter is None:
                if open_centers:
                    continue
                # Keep the approved outline visible and selectable. Do not invent a cutter center.
                if _keep_mill_outline(entities, piece_id, layer):
                    continue
                _drop_layer(entities, piece_id, layer)
                for key in catalog_keys:
                    blocked_path("mill_diameter_required", key)
                continue
            liner_piece = LinerPiece(
                placement["piece_type"],
                placement["width_cm"],
                placement["length_cm"],
                placement["clipped_corner_position"],
                float(placement["clipped_corner_width_cm"]),
                float(placement["clipped_corner_length_cm"]),
            )
            mirrored = bool(placement.get("mirrored"))
            try:
                sawn = [
                    sawn_liner_ends(
                        liner_piece,
                        spec["side"],
                        origin_mm=(placement["x_mm"], placement["y_mm"]),
                        mirrored=mirrored,
                        quarter_turns=placement["quarter_turns"],
                        board=board,
                        start_cm=spec["start_cm"],
                        length_cm=spec["length_cm"],
                    )
                    for spec in specs
                ]
                solos = [
                    generate_toolpath(
                        kind=kind,
                        piece=liner_piece,
                        reference_side=spec["side"],
                        offset_cm=float(spec["offset_cm"]),
                        width_cm=float(width_cm),
                        start_cm=spec["start_cm"],
                        length_cm=spec["length_cm"],
                        cutter_diameter_mm=float(diameter),
                        start_sawn=sawn[index][0],
                        end_sawn=sawn[index][1],
                    )
                    for index, spec in enumerate(specs)
                ]
                if kind == "liner":
                    generated = generate_liner_set_toolpaths(
                        piece=liner_piece,
                        specs=specs,
                        width_cm=float(width_cm),
                        cutter_diameter_mm=float(diameter),
                        start_sawn=[item[0] for item in sawn],
                        end_sawn=[item[1] for item in sawn],
                    )
                else:
                    generated = solos
            except LinerGeometryError as exc:
                _drop_layer(entities, piece_id, layer)
                code = _mill_issue(exc.code)
                for key in catalog_keys or [f"{kind}:{piece_id}:primary"]:
                    blocked_path(code, key)
                continue
            if not generated or any(len(path) < 2 for path in generated):
                _drop_layer(entities, piece_id, layer)
                for key in catalog_keys:
                    blocked_path("mill_parameters_missing", key)
                continue
            sheet_generated = []
            for path in generated:
                sheet_points = _place_mill_path(
                    path,
                    placement,
                    trim_x=trim_x,
                    trim_y=trim_y,
                    length_mm=length_mm,
                )
                if not sheet_points:
                    sheet_generated = []
                    break
                sheet_generated.append(sheet_points)
            if not sheet_generated:
                _drop_layer(entities, piece_id, layer)
                for key in catalog_keys:
                    blocked_path("geometry_invalid", key)
                continue
            if require_upload_match and existing:
                if not _uploaded_matches_generated(existing, sheet_generated):
                    _drop_layer(entities, piece_id, layer)
                    for key in catalog_keys or [f"{kind}:{piece_id}:primary"]:
                        blocked_path("mill_upload_mismatch", key)
                    continue
            elif require_upload_match and not existing:
                for key in catalog_keys:
                    blocked_path("toolpath_missing", key)
                continue
            overlay_keys = _overlay_spec_keys(
                existing,
                catalog_keys,
                specs,
                solos,
                liner_piece,
                float(width_cm),
                placement,
                trim_x=trim_x,
                trim_y=trim_y,
                length_mm=length_mm,
            )
            bindings, unused, merged = _bind_mill_paths(
                kind, piece_id, catalog_keys, generated, solos, specs, overlay_keys
            )
            layer_preset = str(operation_presets.get(kind) or "").strip()
            ambiguous = merged and any(
                str(path_overrides.get(key) or "").strip() not in {"", layer_preset}
                for key in catalog_keys
            )
            _drop_layer(entities, piece_id, layer)
            for path, key in zip(sheet_generated, bindings):
                entities.append(
                    _entity(
                        layer=layer,
                        points=path,
                        closed=False,
                        entity_type="LWPOLYLINE",
                        role="merged_mill_preset_ambiguous" if ambiguous else "tool_center",
                        ring="open",
                        path_key=key,
                        piece_id=piece_id,
                        piece_label=label,
                    )
                )
            absorbed.update(unused)
            if ambiguous:
                for key in unused:
                    blocked_path("merged_mill_preset_ambiguous", key)
    return absorbed


__all__ = ["compile_sheet_program"]
