"""Shared add-on cutter fit for calculation, approval, DXF, and NC.

A cutter wider than its add-on is refused. A rear groove that starts on the
door edge may use a wider cutter after the center is shifted outward. The
check uses the cutter body, including the ends, and only the add-ons that are
actually present. It does not change requested widths or stored diameters.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    GEOMETRY_TOLERANCE_MM,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_issue import (
    ADDON_CUTTER_REJECTED,
    CATEGORY_OVERLAY,
    DxfValidationIssue,
    issue,
    piece_target,
)
from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    CM_TO_MM,
    LinerGeometryError,
    LinerPiece,
    extension_conflict_details,
    piece_quarter_turns,
    liner_parameters_active,
    transform_point,
)
from almdina_erp.almdina_erp.domain.cutting.machining_overlay import (
    MACHINING_ADDONS,
    generate_toolpath,
    machining_values,
)
from almdina_erp.almdina_erp.domain.cutting.primitives import num, rects_have_clearance


def _piece_host(piece: Mapping[str, Any]) -> LinerPiece:
    width = (
        piece.get("original_w")
        or piece.get("original_width_cm")
        or piece.get("cut_width_cm")
        or piece.get("width_cm")
        or piece.get("w")
        or 0
    )
    length = (
        piece.get("original_h")
        or piece.get("original_length_cm")
        or piece.get("cut_length_cm")
        or piece.get("length_cm")
        or piece.get("h")
        or 0
    )
    return LinerPiece(
        str(piece.get("piece_type") or "Regular"),
        float(width or 0),
        float(length or 0),
        str(piece.get("clipped_corner_position") or "Top Right"),
        float(piece.get("clipped_corner_width_cm") or 0),
        float(piece.get("clipped_corner_length_cm") or 0),
    )


def _door_no(piece: Mapping[str, Any]) -> int | None:
    raw = piece.get("source_piece_no")
    if raw in (None, ""):
        label = str(piece.get("label") or "")
        head = label.split(".", 1)[0]
        if head.isdigit():
            return int(head)
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _copy_no(piece: Mapping[str, Any]) -> int | None:
    raw = piece.get("copy_no")
    try:
        return int(raw) if raw not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _active(kind: str, spec: Mapping[str, Any]) -> bool:
    if liner_parameters_active(
        enabled=bool(spec.get("enabled")),
        side=str(spec.get("side") or ""),
        offset_cm=float(spec.get("offset_cm") or 0),
        width_cm=float(spec.get("width_cm") or 0),
    ):
        return True
    if kind != "liner":
        return False
    return any(
        str(item.get("side") or "").strip() and float(item.get("width_cm") or spec.get("width_cm") or 0) > 0
        for item in (spec.get("liners") or ())
        if isinstance(item, Mapping)
    )


def _issue(
    piece: Mapping[str, Any],
    *,
    kind: str,
    code: str,
    width_mm: float,
    diameter_mm: float,
    offset_mm: float,
    neighbor: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "code": code,
        "kind": kind,
        "label": str(piece.get("label") or ""),
        "source_piece_no": _door_no(piece),
        "copy_no": _copy_no(piece),
        "width_mm": float(width_mm),
        "diameter_mm": float(diameter_mm),
        "offset_mm": float(offset_mm),
        "neighbor_label": "",
        "neighbor_piece_no": None,
    }
    if neighbor is not None:
        payload["neighbor_label"] = str(neighbor.get("label") or "")
        payload["neighbor_piece_no"] = _door_no(neighbor)
    return payload


def _diameter(kind: str, diameters: Mapping[str, Any]) -> float | None:
    raw = diameters.get(kind)
    if raw in (None, ""):
        field = {
            "liner": "liner_tool_diameter_mm",
            "recessed_handle_cutout": "handle_recess_tool_diameter_mm",
            "back_groove": "rear_groove_tool_diameter_mm",
        }.get(kind)
        raw = diameters.get(field) if field else None
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= GEOMETRY_TOLERANCE_MM:
        return None
    return number


def _specs(kind: str, spec: Mapping[str, Any]) -> list[dict[str, Any]]:
    if kind == "liner" and spec.get("liners"):
        return [dict(item) for item in spec["liners"] if isinstance(item, Mapping)]
    return [dict(spec)]


def as_dxf_issues(findings: Sequence[Mapping[str, Any]]) -> list[DxfValidationIssue]:
    issues: list[DxfValidationIssue] = []
    for item in findings:
        issues.append(issue(
            ADDON_CUTTER_REJECTED,
            CATEGORY_OVERLAY,
            target=piece_target(
                source_piece_no=item.get("source_piece_no"),
                copy_no=item.get("copy_no"),
                label=str(item.get("label") or "") or None,
            ),
            params={
                "kind": item.get("kind") or "",
                "width_mm": item.get("width_mm"),
                "diameter_mm": item.get("diameter_mm"),
                "offset_mm": item.get("offset_mm"),
                "reason": item.get("code") or "",
                "neighbor_piece_no": item.get("neighbor_piece_no"),
                "source_piece_no": item.get("source_piece_no"),
            },
        ))
    return issues


def assess_piece_addons(
    piece: Mapping[str, Any],
    diameters: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Refuse add-ons whose cutter cannot machine the requested width."""

    if str(piece.get("piece_type") or "") == "Special":
        return []
    values = machining_values(piece)
    host = _piece_host(piece)
    found: list[dict[str, Any]] = []
    for addon in MACHINING_ADDONS:
        spec = values.get(addon.kind) or {}
        if not _active(addon.kind, spec):
            continue
        diameter = _diameter(addon.kind, diameters)
        for row in _specs(addon.kind, spec):
            width_mm = float(row.get("width_cm") or spec.get("width_cm") or 0) * CM_TO_MM
            offset_mm = float(row.get("offset_cm") or 0) * CM_TO_MM
            if diameter is None:
                found.append(_issue(
                    piece, kind=addon.kind, code="cutter_diameter_invalid",
                    width_mm=width_mm, diameter_mm=0, offset_mm=offset_mm,
                ))
                continue
            if width_mm + GEOMETRY_TOLERANCE_MM >= diameter:
                continue
            if addon.kind == "back_groove" and abs(offset_mm) <= GEOMETRY_TOLERANCE_MM:
                try:
                    generate_toolpath(
                        kind=addon.kind,
                        piece=host,
                        reference_side=str(row.get("side") or ""),
                        offset_cm=float(row.get("offset_cm") or 0),
                        width_cm=float(row.get("width_cm") or spec.get("width_cm") or 0),
                        start_cm=row.get("start_cm"),
                        length_cm=row.get("length_cm"),
                        cutter_diameter_mm=diameter,
                    )
                except LinerGeometryError as exc:
                    found.append(_issue(
                        piece, kind=addon.kind, code=exc.code or "rear_groove_oversize_unsafe",
                        width_mm=width_mm, diameter_mm=diameter, offset_mm=offset_mm,
                    ))
                continue
            found.append(_issue(
                piece, kind=addon.kind, code="liner_narrower_than_cutter",
                width_mm=width_mm, diameter_mm=diameter, offset_mm=offset_mm,
            ))
    return found


def _sheet_path(piece: Mapping[str, Any], local: Sequence[Sequence[float]]) -> list[tuple[float, float]]:
    host = _piece_host(piece)
    width = float(host.width_cm) * CM_TO_MM
    height = float(host.length_cm) * CM_TO_MM
    turns = piece_quarter_turns(piece)
    mirrored = bool(piece.get("corner_mirrored") or piece.get("mirrored") or piece.get("placement_mirrored"))
    origin_x = num(piece.get("x")) * CM_TO_MM
    origin_y = num(piece.get("y")) * CM_TO_MM
    placed: list[tuple[float, float]] = []
    for point in local:
        moved = transform_point(
            (float(point[0]), float(point[1])),
            mirrored=mirrored,
            quarter_turns=turns,
            width=width,
            height=height,
        )
        placed.append((moved[0] + origin_x, moved[1] + origin_y))
    return placed


def _obstacle(piece: Mapping[str, Any]) -> dict[str, Any]:
    x = num(piece.get("x")) * CM_TO_MM
    y = num(piece.get("y")) * CM_TO_MM
    width = num(piece.get("w")) * CM_TO_MM
    height = num(piece.get("h")) * CM_TO_MM
    return {
        "outer": [(x, y), (x + width, y), (x + width, y + height), (x, y + height)],
        "holes": [],
        "diagnostic": {
            "label": str(piece.get("label") or ""),
            "piece_id": piece.get("id"),
            "source_piece_no": _door_no(piece),
        },
    }


def _exceptional_groove(piece: Mapping[str, Any], diameters: Mapping[str, Any]) -> tuple[dict[str, Any], float] | None:
    values = machining_values(piece)
    spec = values.get("back_groove") or {}
    if not _active("back_groove", spec):
        return None
    diameter = _diameter("back_groove", diameters)
    width_mm = float(spec.get("width_cm") or 0) * CM_TO_MM
    offset_mm = float(spec.get("offset_cm") or 0) * CM_TO_MM
    if diameter is None or width_mm + GEOMETRY_TOLERANCE_MM >= diameter:
        return None
    if abs(offset_mm) > GEOMETRY_TOLERANCE_MM:
        return None
    return spec, diameter


def layout_conflicts(
    plan: Mapping[str, Any],
    diameters: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Cutter-body conflicts for edge rear grooves after the outward shift."""

    issues: list[dict[str, Any]] = []
    for sheet in plan.get("sheets") or ():
        if not isinstance(sheet, Mapping):
            continue
        pieces = [piece for piece in (sheet.get("pieces") or ()) if isinstance(piece, Mapping)]
        by_id = {piece.get("id"): piece for piece in pieces}
        for piece in pieces:
            if str(piece.get("piece_type") or "") == "Special":
                continue
            exceptional = _exceptional_groove(piece, diameters)
            if exceptional is None:
                continue
            spec, diameter = exceptional
            host = _piece_host(piece)
            try:
                local = generate_toolpath(
                    kind="back_groove",
                    piece=host,
                    reference_side=str(spec.get("side") or ""),
                    offset_cm=float(spec.get("offset_cm") or 0),
                    width_cm=float(spec.get("width_cm") or 0),
                    start_cm=spec.get("start_cm"),
                    length_cm=spec.get("length_cm"),
                    cutter_diameter_mm=diameter,
                )
            except LinerGeometryError:
                continue
            path = _sheet_path(piece, local)
            obstacles = [_obstacle(other) for other in pieces if other is not piece]
            details = extension_conflict_details(path, diameter, None, obstacles)
            if not details:
                continue
            diagnostic = details.get("obstacle") or {}
            neighbor = by_id.get(diagnostic.get("piece_id"))
            if neighbor is None:
                label = str(diagnostic.get("label") or "")
                neighbor = next((item for item in pieces if str(item.get("label") or "") == label), None)
            issues.append(_issue(
                piece,
                kind="back_groove",
                code="rear_groove_neighbor_conflict",
                width_mm=float(spec.get("width_cm") or 0) * CM_TO_MM,
                diameter_mm=diameter,
                offset_mm=float(spec.get("offset_cm") or 0) * CM_TO_MM,
                neighbor=neighbor,
            ))
            issues[-1]["deficit_mm"] = max(
                0.0,
                float(details.get("cutter_radius_mm") or 0)
                - float(details.get("minimum_distance_mm") or 0),
            )
            issues[-1]["sheet_no"] = sheet.get("sheet_no")
    return issues


def _rect(piece: Mapping[str, Any]) -> dict[str, float]:
    return {
        "x": num(piece.get("x")),
        "y": num(piece.get("y")),
        "w": num(piece.get("w")),
        "h": num(piece.get("h")),
    }


def _inside_sheet(piece: Mapping[str, Any], sheet: Mapping[str, Any]) -> bool:
    rect = _rect(piece)
    return (
        rect["x"] >= -1e-6
        and rect["y"] >= -1e-6
        and rect["x"] + rect["w"] <= num(sheet.get("w")) + 1e-6
        and rect["y"] + rect["h"] <= num(sheet.get("h")) + 1e-6
    )


def _shift_pair(
    sheet: dict[str, Any],
    host_id: Any,
    neighbor_id: Any,
    axis: str,
    sign: float,
    distance_cm: float,
    kerf_cm: float,
) -> bool:
    pieces = sheet.get("pieces") or []
    host = next((piece for piece in pieces if piece.get("id") == host_id), None)
    neighbor = next((piece for piece in pieces if piece.get("id") == neighbor_id), None)
    if host is None or neighbor is None or distance_cm <= 0:
        return False
    key = "x" if axis == "x" else "y"

    def apply(target: dict[str, Any], delta: float) -> bool:
        original = num(target.get(key))
        target[key] = original + delta
        if not _inside_sheet(target, sheet):
            target[key] = original
            return False
        rect = _rect(target)
        for other in pieces:
            if other is target:
                continue
            if not rects_have_clearance(rect, _rect(other), kerf_cm):
                target[key] = original
                return False
        return True

    if apply(neighbor, sign * distance_cm):
        return True
    if apply(host, -sign * distance_cm):
        return True
    return False


def _path_samples(path: Sequence[Sequence[float]]) -> list[tuple[float, float]]:
    samples: list[tuple[float, float]] = []
    for index in range(len(path) - 1):
        start = (float(path[index][0]), float(path[index][1]))
        end = (float(path[index + 1][0]), float(path[index + 1][1]))
        span_x = end[0] - start[0]
        span_y = end[1] - start[1]
        steps = max(1, int(math.hypot(span_x, span_y)))
        for step in range(steps + 1):
            ratio = step / steps
            samples.append((start[0] + ratio * span_x, start[1] + ratio * span_y))
    return samples or [(float(path[0][0]), float(path[0][1]))]


def _neighbor_rect_mm(neighbor: Mapping[str, Any]) -> tuple[float, float, float, float]:
    x0 = num(neighbor.get("x")) * CM_TO_MM
    y0 = num(neighbor.get("y")) * CM_TO_MM
    return (x0, y0, x0 + num(neighbor.get("w")) * CM_TO_MM, y0 + num(neighbor.get("h")) * CM_TO_MM)


def _push_from_body(
    path: Sequence[Sequence[float]],
    rect: tuple[float, float, float, float],
) -> tuple[float, float]:
    """Direction that moves the touched door off the cutter body."""

    x0, y0, x1, y1 = rect
    inside = [
        point for point in _path_samples(path)
        if x0 <= point[0] <= x1 and y0 <= point[1] <= y1
    ]
    if inside:
        point = inside[0]
        edges = (
            (point[0] - x0, 1.0, 0.0),
            (x1 - point[0], -1.0, 0.0),
            (point[1] - y0, 0.0, 1.0),
            (y1 - point[1], 0.0, -1.0),
        )
        _distance, sign_x, sign_y = min(edges, key=lambda item: item[0])
        return sign_x, sign_y
    best_vector = (0.0, 0.0)
    best_distance = float("inf")
    for point in _path_samples(path):
        clamped = (min(max(point[0], x0), x1), min(max(point[1], y0), y1))
        vector = (clamped[0] - point[0], clamped[1] - point[1])
        distance = vector[0] * vector[0] + vector[1] * vector[1]
        if distance < best_distance:
            best_vector = vector
            best_distance = distance
    return best_vector


def _separation_axis(
    host: Mapping[str, Any],
    neighbor: Mapping[str, Any],
    diameters: Mapping[str, Any],
) -> tuple[str, float] | None:
    """Push the touched door away from the cutter body, not every door."""

    exceptional = _exceptional_groove(host, diameters)
    if exceptional is None:
        return None
    spec, diameter = exceptional
    try:
        local = generate_toolpath(
            kind="back_groove",
            piece=_piece_host(host),
            reference_side=str(spec.get("side") or ""),
            offset_cm=float(spec.get("offset_cm") or 0),
            width_cm=float(spec.get("width_cm") or 0),
            start_cm=spec.get("start_cm"),
            length_cm=spec.get("length_cm"),
            cutter_diameter_mm=diameter,
        )
    except LinerGeometryError:
        return None
    path = _sheet_path(host, local)
    if len(path) < 2:
        return None
    vector_x, vector_y = _push_from_body(path, _neighbor_rect_mm(neighbor))
    if abs(vector_x) <= 1e-6 and abs(vector_y) <= 1e-6:
        return None
    if abs(vector_x) >= abs(vector_y):
        return "x", 1.0 if vector_x >= 0 else -1.0
    return "y", 1.0 if vector_y >= 0 else -1.0


def resolve_exceptional_groove_layout(
    plan: Mapping[str, Any],
    diameters: Mapping[str, Any],
    *,
    kerf_cm: float = 0.0,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Keep a safe placement when one candidate collides and another shift fits.

    Only the edge that owns an exceptional rear groove is moved, and only far
    enough for that cutter body. Other gaps stay as the packer left them.
    """

    current = deepcopy(dict(plan))
    pieces = []
    for sheet in current.get("sheets") or ():
        pieces.extend(sheet.get("pieces") or [])
    pieces.extend(current.get("unplaced") or [])
    hard = []
    for piece in pieces:
        if isinstance(piece, Mapping):
            hard.extend(assess_piece_addons(piece, diameters))
    if hard:
        return current, hard
    for _ in range(8):
        issues = layout_conflicts(current, diameters)
        if not issues:
            return current, []
        issue = issues[0]
        moved = False
        for sheet in current.get("sheets") or ():
            host = next(
                (
                    piece for piece in sheet.get("pieces") or []
                    if str(piece.get("label") or "") == issue["label"]
                ),
                None,
            )
            neighbor = next(
                (
                    piece for piece in sheet.get("pieces") or []
                    if issue.get("neighbor_label")
                    and str(piece.get("label") or "") == issue["neighbor_label"]
                ),
                None,
            )
            if host is None or neighbor is None:
                continue
            axis = _separation_axis(host, neighbor, diameters)
            if axis is None:
                continue
            distance_cm = (float(issue.get("deficit_mm") or 0) + 0.05) / CM_TO_MM
            moved = _shift_pair(
                sheet,
                host.get("id"),
                neighbor.get("id"),
                axis[0],
                axis[1],
                distance_cm,
                kerf_cm,
            )
            if moved:
                break
        if not moved:
            return current, issues
    return current, layout_conflicts(current, diameters)
