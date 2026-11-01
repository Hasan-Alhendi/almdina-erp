"""Compile one sheet program from the approved plan geometry.

Cutter centers come from the existing manufacturing offset. This module does
not nest, approve, or invent a path the approved drawing does not contain.
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
from almdina_erp.almdina_erp.domain.cnc.program import (
    CncSourceEntity,
    build_board_program,
    program_payload,
)
from almdina_erp.almdina_erp.domain.cutting.cutter_center_paths import (
    classify_saw_center_segments,
    cutter_center_paths,
    cutter_center_segments,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import point_in_polygon
from almdina_erp.almdina_erp.domain.orders.extra_addons import EXTRA_OVERLAY_LAYER_BY_KIND


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
    ordered: list[str] = []
    for raw in requested:
        key = str(raw or "").strip()
        if key in CNC_OPERATIONS_BY_KEY and key not in ordered:
            ordered.append(key)
    for key in DEFAULT_MACHINING_ORDER:
        if key in present and key not in ordered:
            ordered.append(key)
    return ordered


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
) -> dict[str, Any]:
    """Return the JSON program for one sheet. Nothing is stored."""

    sheet_pieces = [
        piece for piece in pieces if int(piece.get("sheet_no") or 0) == int(sheet_no)
    ]
    if int(sheet_no) <= 0 or not sheet_pieces:
        raise OperationalFileError("sheet_not_in_plan")
    catalog = catalog_sheet(int(sheet_no), sheet_pieces)
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
    if isinstance(uploaded, Mapping) and str(uploaded.get("units") or "mm") != "mm":
        units = "unknown"
    if isinstance(uploaded, Mapping) and uploaded.get("unsupported"):
        blocked_path("geometry_invalid", "")

    shapes: list[tuple[list[tuple[float, float]], list[list[tuple[float, float]]]]] = []
    for piece in sheet_pieces:
        piece_id = str(piece.get("piece_instance_id") or "")
        label = str(piece.get("label") or "")
        parsed = _usable_geometry(piece.get("geometry") if isinstance(piece.get("geometry"), Mapping) else None)
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
            if not isinstance(uploaded, Mapping) or uploaded.get("unreadable") or uploaded.get("origin") is None and not observed:
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
        if not _uploaded_frame_ready(uploaded):
            blocked_path("dxf_unreadable", "")
        else:
            _append_uploaded_cuts(entities, uploaded, role="finished_boundary")
    elif mode == _UNKNOWN:
        if not _uploaded_frame_ready(uploaded):
            blocked_path("dxf_unreadable", "")
        else:
            _append_uploaded_cuts(entities, uploaded, role="unverified")
    elif mode == _PRESENT:
        blocked_path("dxf_unreadable", "")

    if use_file_overlays:
        _append_file_overlays(entities, uploaded_overlays, hosts)
    else:
        _append_snapshot_overlays(entities, sheet_pieces, trim_x=trim_x, trim_y=trim_y, length_mm=length_mm)

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
        if path.path_key in extracted:
            continue
        if (path.piece_instance_id, path.operation_key) in covered_overlays:
            continue
        if path.operation_key == "cut_path" and (extracted_cut or kerf_blocked):
            continue
        if path.operation_key == "cut_path":
            continue
        if not any(item["path_key"] == path.path_key for item in blocked):
            blocked_path("toolpath_missing", path.path_key)

    layer_cut = str(operation_presets.get("cut_path") or "").strip()
    shared_exists = any(
        entity.layer.upper() == "CUT_PATH" and entity.role == "tool_center" and not entity.piece_instance_id
        for entity in entities
    )
    ambiguous = shared_exists and any(
        str(path_overrides.get(path.path_key) or "").strip() not in {"", layer_cut}
        for path in catalog.paths
        if path.operation_key == "cut_path"
    )
    overrides = {str(key): value for key, value in path_overrides.items()}
    program = build_board_program(
        sheet_no=int(sheet_no),
        entities=entities,
        operation_order=order,
        operation_presets=operation_presets,
        path_overrides=overrides,
        known_presets=known_presets,
        cut_path_early_confirmed=cut_path_early_confirmed,
        units=units,
        frame_origin_mm=(0.0, 0.0),
        sheet_width_mm=width_mm,
        sheet_length_mm=length_mm,
        blocked_catalog_paths=blocked,
        shared_cut_ambiguous=ambiguous,
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
                    role="region_boundary" if closed else "tool_center",
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
            toolpath = bool(geometry.get("toolpath")) and not closed
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
            entities.append(
                _entity(
                    layer=EXTRA_OVERLAY_LAYER_BY_KIND[kind],
                    points=points,
                    closed=closed,
                    entity_type="LINE" if str(geometry.get("entity_type") or "").upper() == "LINE" else "LWPOLYLINE",
                    role="tool_center" if (toolpath or not closed) else "region_boundary",
                    ring="open" if not closed else "unknown",
                    path_key=path_key,
                    piece_id=piece_id,
                    piece_label=label,
                )
            )


__all__ = ["compile_sheet_program"]
