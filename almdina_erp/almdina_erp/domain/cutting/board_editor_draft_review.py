"""Read-only readiness of one saved board-editor draft.

The draft layout supplies pose and membership only. Geometry, rotation
permission, kerf, trim, and machine type come from the trusted model.
Nothing here writes the draft, the plan, or an approval.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from almdina_erp.almdina_erp.domain.cutting.board_editor_draft import (
    EDITOR_ORIGIN_FULL_BOARD,
    DraftLayoutError,
    distribution_fingerprint,
    normalize_layout,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_rotation import (
    angles_equivalent,
    ensure_base_geometry,
    machine_accepts_rotation,
    preview_piece_rotation,
    rotate_points,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_transform import (
    apply_draft_parity_to_entry,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_session_edit import (
    _reframe_piece_geometry,
    _reframe_points,
    piece_footprint_mm,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import polygon_inside_rect
from almdina_erp.almdina_erp.domain.cutting.dxf_topology import (
    PartGeometry,
    PlacedPartGeometry,
    material_layout_issues,
    polygon_strictly_contains_polygon,
)
from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import (
    host_link_issue_codes,
)
from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    LinerGeometryError,
    LinerPiece,
    extension_conflict_details,
    piece_quarter_turns,
    sawn_liner_ends,
    transform_point,
)
from almdina_erp.almdina_erp.domain.cutting.machining_overlay import (
    MACHINING_ADDONS,
    generate_liner_set_toolpaths,
    generate_toolpath,
    machining_values,
)
from almdina_erp.almdina_erp.domain.cutting.offcut_policy import (
    OffcutPolicyError,
    ResourceKind,
    decision_from_piece,
    decision_from_values,
    resource_kind_from_value,
    validate_source_resource_homogeneity,
)
from almdina_erp.almdina_erp.domain.cutting.primitives import num, rect_intersects
from almdina_erp.almdina_erp.domain.orders.liner_specs import (
    DoorLinerError,
    DoorLinerSpec,
)

ERROR = "error"
WARNING = "warning"


def _clone_ring_mm(ring: Any) -> list[list[float]] | None:
    if not isinstance(ring, list) or len(ring) < 3:
        return None
    points: list[list[float]] = []
    for point in ring:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return None
        points.append([num(point[0]), num(point[1])])
    return points


def usable_sheet_hole_from_piece_local(
    ring: Any,
    placement_cm: Mapping[str, Any] | None,
) -> list[list[float]] | None:
    """Lift manufacturing piece-local glass_hole_local_mm into usable-sheet mm."""

    local = _clone_ring_mm(ring)
    if local is None:
        return None
    placement = placement_cm or {}
    ox = num(placement.get("x")) * 10.0
    oy = num(placement.get("y")) * 10.0
    return [[point[0] + ox, point[1] + oy] for point in local]


def resolve_trusted_glass_hole_mm(
    *,
    piece: Mapping[str, Any],
    geometry_holes: Any = None,
) -> list[list[float]] | None:
    """Resolve one glass opening into the same usable-sheet frame as outline_mm.

    Prefer finished_outline geometry.holes (already usable-sheet). Otherwise lift
    manufacturing glass_hole_local_mm once from entry placement_cm. Do not change
    the manufacturing meaning of the source field outside this review pose.
    """

    if isinstance(geometry_holes, list) and geometry_holes:
        first = _clone_ring_mm(geometry_holes[0])
        if first is not None:
            return first
    return usable_sheet_hole_from_piece_local(
        piece.get("glass_hole_local_mm"),
        piece.get("placement_cm") if isinstance(piece.get("placement_cm"), Mapping) else None,
    )


def trusted_model_from_projection(
    projection: Mapping[str, Any],
    *,
    machine_type: str,
) -> dict[str, Any]:
    """Trusted geometry for a review. Display settings are not included."""

    outlines: dict[str, list] = {}
    outline_holes: dict[str, list] = {}
    for element in projection.get("elements") or []:
        if not isinstance(element, Mapping) or element.get("kind") != "finished_outline":
            continue
        instance = str(element.get("piece_instance_id") or "").strip()
        geometry = element.get("geometry") if isinstance(element.get("geometry"), Mapping) else {}
        outer = geometry.get("outer") if isinstance(geometry, Mapping) else None
        if instance and isinstance(outer, list) and len(outer) >= 3:
            outlines[instance] = outer
        holes = geometry.get("holes") if isinstance(geometry, Mapping) else None
        if instance and isinstance(holes, list) and holes and instance not in outline_holes:
            outline_holes[instance] = holes
    pieces: dict[str, dict[str, Any]] = {}
    for piece in projection.get("pieces") or []:
        if not isinstance(piece, Mapping):
            continue
        instance = str(piece.get("piece_instance_id") or "").strip()
        if not instance or instance in pieces:
            continue
        placement = piece.get("placement_cm") or {}
        local_x = num(placement.get("x")) * 10.0
        local_y = num(placement.get("y")) * 10.0
        width = num(placement.get("w")) * 10.0
        length = num(placement.get("h")) * 10.0
        outline = outlines.get(instance)
        piece_type = str(piece.get("piece_type") or "Regular")
        geometry_source = str(piece.get("geometry_source") or "")
        exact_geometry = bool(piece.get("exact_geometry"))
        special_representation = piece.get("special_representation")
        # CNC-raw Special stock uses the trusted placement rectangle for layout
        # collision; exact Special without an outline stays unproven.
        if outline is None and width > 0 and length > 0:
            allow_rect = piece_type != "Special" or geometry_source == "cnc_raw_rect"
            if allow_rect:
                outline = [
                    [local_x, local_y],
                    [local_x + width, local_y],
                    [local_x + width, local_y + length],
                    [local_x, local_y + length],
                ]
        # Review pose stores the opening in usable-sheet mm (same frame as outline_mm).
        session_hole = resolve_trusted_glass_hole_mm(
            piece=piece,
            geometry_holes=outline_holes.get(instance),
        )
        pieces[instance] = {
            "piece_instance_id": instance,
            "piece_id": piece.get("piece_id"),
            "label": piece.get("label") or instance,
            "sheet_no": piece.get("sheet_no"),
            "local_x_mm": local_x,
            "local_y_mm": local_y,
            "width_mm": width,
            "length_mm": length,
            "outline_mm": outline,
            "glass_hole_local_mm": session_hole,
            "glass_host_piece_id": piece.get("glass_host_piece_id"),
            "allow_rotation": piece.get("allow_rotation") is True,
            "allow_rotation_proven": piece.get("allow_rotation_proven") is True,
            "resource_kind": piece.get("resource_kind"),
            "offcut_source_party": piece.get("offcut_source_party"),
            "offcut_execution_party": piece.get("offcut_execution_party"),
            "piece_type": piece_type,
            "geometry_source": geometry_source,
            "exact_geometry": exact_geometry,
            "special_representation": special_representation,
            "clipped_corner_position": piece.get("clipped_corner_position"),
            "clipped_corner_width_cm": piece.get("clipped_corner_width_cm"),
            "clipped_corner_length_cm": piece.get("clipped_corner_length_cm"),
            "corner_mirrored": piece.get("corner_mirrored"),
            "corner_rotation_quarter_turns": piece.get("corner_rotation_quarter_turns"),
            "original_w": piece.get("original_w"),
            "original_h": piece.get("original_h"),
            "source_rotated_dims": piece.get("source_rotated_dims"),
            # Machining fields are copied verbatim; layer visibility is ignored.
            **{
                field: piece.get(field)
                for field in (
                    "extra_liner",
                    "liner_reference_side",
                    "liner_offset_cm",
                    "liner_width_cm",
                    "liner_start_cm",
                    "liner_length_cm",
                    "liner_specs_json",
                    "extra_back_groove",
                    "back_groove_reference_side",
                    "back_groove_offset_cm",
                    "back_groove_width_cm",
                    "back_groove_start_cm",
                    "back_groove_length_cm",
                    "extra_recessed_handle_cutout",
                    "recessed_handle_reference_side",
                    "recessed_handle_offset_cm",
                    "recessed_handle_width_cm",
                    "recessed_handle_start_cm",
                    "recessed_handle_length_cm",
                )
            },
        }
    sheets: dict[int, dict[str, Any]] = {}
    for sheet in projection.get("sheets") or []:
        if not isinstance(sheet, Mapping) or sheet.get("sheet_no") in (None, ""):
            continue
        number = int(sheet["sheet_no"])
        full_w = num(sheet.get("full_width_cm") or sheet.get("w")) * 10.0
        full_h = num(sheet.get("full_length_cm") or sheet.get("h")) * 10.0
        trim_x = num(sheet.get("applied_trim_width_cm")) * 10.0
        trim_y = num(sheet.get("applied_trim_length_cm")) * 10.0
        usable_w = num(sheet.get("usable_width_cm")) * 10.0
        usable_h = num(sheet.get("usable_length_cm")) * 10.0
        if usable_w <= 0:
            usable_w = max(1.0, full_w - (trim_x * 2.0))
        if usable_h <= 0:
            usable_h = max(1.0, full_h - (trim_y * 2.0))
        sheets[number] = {
            "resource_kind": sheet.get("resource_kind") or "FULL_BOARD",
            "usable_width_mm": usable_w,
            "usable_length_mm": usable_h,
            "full_width_mm": full_w if full_w > 0 else usable_w,
            "full_length_mm": full_h if full_h > 0 else usable_h,
            "trim_x_mm": trim_x,
            "trim_y_mm": trim_y,
        }
    board = projection.get("board") if isinstance(projection.get("board"), Mapping) else {}
    trim_cm = num(board.get("trim_cm"))
    trim_x_cm = board.get("applied_trim_width_cm")
    trim_y_cm = board.get("applied_trim_length_cm")
    standard = {
        "full_width_mm": num(board.get("full_width_cm")) * 10.0,
        "full_length_mm": num(board.get("full_length_cm")) * 10.0,
        "usable_width_mm": num(board.get("usable_width_cm")) * 10.0,
        "usable_length_mm": num(board.get("usable_length_cm")) * 10.0,
        "trim_x_mm": num(trim_x_cm if trim_x_cm not in (None, "") else trim_cm) * 10.0,
        "trim_y_mm": num(trim_y_cm if trim_y_cm not in (None, "") else trim_cm) * 10.0,
    }
    if standard["usable_width_mm"] <= 0 and standard["full_width_mm"] > 0:
        standard["usable_width_mm"] = max(1.0, standard["full_width_mm"] - (standard["trim_x_mm"] * 2.0))
    if standard["usable_length_mm"] <= 0 and standard["full_length_mm"] > 0:
        standard["usable_length_mm"] = max(1.0, standard["full_length_mm"] - (standard["trim_y_mm"] * 2.0))
    if standard["full_width_mm"] <= 0:
        standard["full_width_mm"] = standard["usable_width_mm"]
    if standard["full_length_mm"] <= 0:
        standard["full_length_mm"] = standard["usable_length_mm"]
    return {
        "pieces": pieces,
        "sheets": sheets,
        "standard_full_board": standard,
        "kerf_mm": num((projection.get("board") or {}).get("kerf_cm")) * 10.0,
        "machine_type": str(machine_type or ""),
    }


def review_saved_draft(
    draft: Mapping[str, Any] | None,
    trusted: Mapping[str, Any],
) -> dict[str, Any]:
    """Return readiness for the stored draft. Does not merge a changed source."""

    stored = dict(draft or {})
    version = int(stored.get("draft_version") or 0)
    fingerprint = str(stored.get("distribution_fingerprint") or "")
    if not stored.get("present"):
        return _result(False, version, fingerprint, [_issue("draft_missing")])
    if stored.get("conflict") == "source" or stored.get("compatible") is False:
        return _result(False, version, fingerprint, [_issue("source_changed")])

    layout = stored.get("layout")
    try:
        normalized = normalize_layout(layout, _catalog(trusted))
    except DraftLayoutError as exc:
        return _result(False, version, fingerprint, [_issue(exc.code)])

    fingerprint = distribution_fingerprint(normalized)
    issues = _review_normalized(normalized, trusted)
    ready = not any(issue["severity"] == ERROR for issue in issues)
    return _result(ready, version, fingerprint, issues)


def pose_normalized_layout(
    layout: Mapping[str, Any],
    trusted: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply draft pose once. Used by review and by plan materialization."""

    issues: list[dict[str, Any]] = []
    sheets = _sheets(trusted, layout, issues)
    pieces = _posed_pieces(layout, trusted, sheets, issues)
    return {"sheets": sheets, "pieces": pieces, "issues": issues}


def _review_normalized(
    layout: Mapping[str, Any],
    trusted: Mapping[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    sheets = _sheets(trusted, layout, issues)
    pieces = _posed_pieces(layout, trusted, sheets, issues)
    placed = [
        piece
        for piece in pieces
        if piece.get("distribution") != "excluded" and piece.get("sheet_no") not in (None, "")
    ]
    _homogeneity_rules(placed, issues)
    _placement_rules(pieces, sheets, issues)
    _hosting_rules(placed, issues)
    _rotation_rules(pieces, str(trusted.get("machine_type") or ""), issues)
    kerf_mm = num(trusted.get("kerf_mm"))
    _material_rules(placed, kerf_mm, issues)
    _addon_rules(placed, sheets, kerf_mm, issues)
    return _dedupe(issues)


def _catalog(trusted: Mapping[str, Any]) -> dict[str, Any]:
    pieces = {}
    for instance, info in (trusted.get("pieces") or {}).items():
        pieces[str(instance)] = {
            "piece_id": info.get("piece_id"),
            "allow_rotation": info.get("allow_rotation") is True
            and info.get("allow_rotation_proven") is True,
            "glass_host_piece_id": info.get("glass_host_piece_id"),
        }
    return {
        "pieces": pieces,
        "source_sheet_nos": [int(number) for number in (trusted.get("sheets") or {})],
    }


def _sheets(
    trusted: Mapping[str, Any],
    layout: Mapping[str, Any],
    issues: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    layout_boards = {
        int(board["sheet_no"]): board
        for board in (layout.get("boards") or [])
        if isinstance(board, Mapping) and board.get("sheet_no") not in (None, "")
    }
    sheets: dict[str, dict[str, Any]] = {}
    standard = trusted.get("standard_full_board") if isinstance(trusted.get("standard_full_board"), Mapping) else {}
    for number, info in (trusted.get("sheets") or {}).items():
        if int(number) not in layout_boards:
            continue
        try:
            kind = resource_kind_from_value(info.get("resource_kind"))
        except OffcutPolicyError:
            issues.append(
                _issue(
                    "unsupported_sheet_resource",
                    sheet_nos=[int(number)],
                )
            )
            continue
        sheets[str(number)] = {
            "sheet_no": int(number),
            "resource_kind": kind.value,
            "origin_x_mm": 0.0,
            "origin_y_mm": 0.0,
            "trim_x_mm": num(info.get("trim_x_mm")),
            "trim_y_mm": num(info.get("trim_y_mm")),
            "usable_width_mm": num(info.get("usable_width_mm")),
            "usable_length_mm": num(info.get("usable_length_mm")),
            "width_mm": num(info.get("full_width_mm") or info.get("usable_width_mm")),
            "height_mm": num(info.get("full_length_mm") or info.get("usable_length_mm")),
            "editor_origin": None,
        }
    for number, board in layout_boards.items():
        if str(number) in sheets:
            continue
        if board.get("editor_origin") != EDITOR_ORIGIN_FULL_BOARD:
            issues.append(_issue("unknown_sheet", sheet_nos=[int(number)]))
            continue
        usable_w = num(standard.get("usable_width_mm"))
        usable_h = num(standard.get("usable_length_mm"))
        if usable_w <= 0 or usable_h <= 0:
            issues.append(_issue("standard_board_unavailable", sheet_nos=[int(number)]))
            continue
        sheets[str(number)] = {
            "sheet_no": int(number),
            "resource_kind": ResourceKind.FULL_BOARD.value,
            "origin_x_mm": 0.0,
            "origin_y_mm": 0.0,
            "trim_x_mm": num(standard.get("trim_x_mm")),
            "trim_y_mm": num(standard.get("trim_y_mm")),
            "usable_width_mm": usable_w,
            "usable_length_mm": usable_h,
            "width_mm": num(standard.get("full_width_mm")) or usable_w,
            "height_mm": num(standard.get("full_length_mm")) or usable_h,
            "editor_origin": EDITOR_ORIGIN_FULL_BOARD,
        }
    return sheets


def _posed_pieces(
    layout: Mapping[str, Any],
    trusted: Mapping[str, Any],
    sheets: Mapping[str, Mapping[str, Any]],
    issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_layout = {row["piece_instance_id"]: row for row in layout.get("pieces") or []}
    posed: list[dict[str, Any]] = []
    session_pieces: dict[str, dict[str, Any]] = {}
    kerf_mm = num(trusted.get("kerf_mm"))
    for instance, info in (trusted.get("pieces") or {}).items():
        row = by_layout[str(instance)]
        piece = _entry_piece(str(instance), info)
        if piece.get("outline_mm") is None:
            issues.append(
                _issue(
                    "geometry_unproven",
                    piece_instance_ids=[str(instance)],
                    piece_ids=_ids(info),
                    reason="piece_outline_unavailable",
                )
            )
        board = sheets.get(str(info.get("sheet_no"))) or {}
        paths, path_issues = _entry_machining_paths(
            info,
            kerf_mm=kerf_mm,
            board_width_mm=num(board.get("usable_width_mm")),
            board_length_mm=num(board.get("usable_length_mm")),
        )
        issues.extend(path_issues)
        piece["machining_paths"] = paths
        key = f"instance:{instance}"
        piece["piece_key"] = key
        piece["machining_paths"] = list(paths)
        session_pieces[key] = piece
        ensure_base_geometry(piece)
        # Apply draft transform parity before rotation so preview/validate/plan
        # materialize share one geometry path derived from the trusted entry.
        apply_draft_parity_to_entry(piece, row)
        paths = list(piece.get("machining_paths") or paths)
        entry_pivot = {
            "x": num((piece.get("pivot_mm") or {}).get("x")),
            "y": num((piece.get("pivot_mm") or {}).get("y")),
        }
        angle = num(row.get("rotation_deg"))
        if piece.get("outline_mm") is not None and not angles_equivalent(angle, 0):
            trial = preview_piece_rotation(
                {"pieces": session_pieces, "boards": sheets, "kerf_mm": 0},
                piece_key=key,
                rotation_deg=angle,
            )
            session_pieces[key] = trial["pieces"][key]
            piece = session_pieces[key]
            piece["machining_paths"] = [
                {
                    **item,
                    "path_mm": rotate_points(item.get("path_mm"), entry_pivot, angle) or [],
                }
                for item in paths
            ]
        target = row.get("sheet_no")
        origin_from = _origin(sheets, piece.get("sheet_no"))
        origin_to = _origin(sheets, target)
        world_dx = (num(row.get("local_x_mm")) + origin_to[0]) - (num(piece.get("local_x_mm")) + origin_from[0])
        world_dy = (num(row.get("local_y_mm")) + origin_to[1]) - (num(piece.get("local_y_mm")) + origin_from[1])
        from_sheet = piece.get("sheet_no")
        _reframe_piece_geometry(
            piece,
            sheets,
            from_sheet=from_sheet,
            to_sheet=target,
            world_dx=world_dx,
            world_dy=world_dy,
        )
        piece["machining_paths"] = [
            {
                **item,
                "path_mm": _reframe_points(
                    item.get("path_mm"),
                    sheets,
                    from_sheet=from_sheet,
                    to_sheet=target,
                    world_dx=world_dx,
                    world_dy=world_dy,
                )
                or [],
            }
            for item in (piece.get("machining_paths") or [])
        ]
        piece["sheet_no"] = target
        piece["local_x_mm"] = num(row.get("local_x_mm"))
        piece["local_y_mm"] = num(row.get("local_y_mm"))
        piece["rotation_deg"] = angle
        piece["distribution"] = row.get("distribution")
        piece["glass_host_piece_id"] = row.get("glass_host_piece_id")
        if row.get("resource_kind") not in (None, ""):
            kind_value = row.get("resource_kind")
            source_party = row.get("offcut_source_party")
            execution_party = row.get("offcut_execution_party")
        else:
            kind_value = info.get("resource_kind")
            source_party = info.get("offcut_source_party")
            execution_party = info.get("offcut_execution_party")
        try:
            decision = decision_from_values(kind_value, source_party, execution_party)
        except OffcutPolicyError:
            issues.append(
                _issue(
                    "unsupported_sheet_resource",
                    piece_instance_ids=[str(instance)],
                    piece_ids=_ids(info),
                )
            )
            continue
        piece["resource_kind"] = decision.resource_kind.value
        piece["offcut_source_party"] = decision.source_party.value
        piece["offcut_execution_party"] = decision.execution_party.value
        posed.append(piece)
    return posed


def _homogeneity_rules(placed: list[dict[str, Any]], issues: list[dict[str, Any]]) -> None:
    by_sheet: dict[int, list[dict[str, Any]]] = {}
    for piece in placed:
        sheet_no = piece.get("sheet_no")
        if sheet_no in (None, ""):
            continue
        by_sheet.setdefault(int(sheet_no), []).append(piece)
        try:
            decision = decision_from_piece(piece)
        except OffcutPolicyError:
            issues.append(
                _issue(
                    "unsupported_sheet_resource",
                    piece_instance_ids=[str(piece.get("piece_instance_id") or "")],
                    piece_ids=_ids(piece),
                    sheet_nos=[int(sheet_no)],
                )
            )
            continue
        if decision.is_offcut and not decision.is_resolved:
            issues.append(
                _issue(
                    "offcut_unresolved",
                    piece_instance_ids=[str(piece.get("piece_instance_id") or "")],
                    piece_ids=_ids(piece),
                    sheet_nos=[int(sheet_no)],
                )
            )
    sources = [{"pieces": group} for group in by_sheet.values()]
    try:
        validate_source_resource_homogeneity(sources)
    except OffcutPolicyError:
        for sheet_no, group in by_sheet.items():
            kinds = set()
            for piece in group:
                try:
                    kinds.add(decision_from_piece(piece).resource_kind)
                except OffcutPolicyError:
                    continue
            if len(kinds) > 1:
                piece_ids: list[int] = []
                for piece in group:
                    piece_ids.extend(_ids(piece))
                issues.append(
                    _issue(
                        "mixed_full_board_offcut_source",
                        piece_instance_ids=[
                            str(piece.get("piece_instance_id") or "")
                            for piece in group
                            if piece.get("piece_instance_id")
                        ],
                        piece_ids=piece_ids,
                        sheet_nos=[sheet_no],
                    )
                )


def _entry_piece(instance: str, info: Mapping[str, Any]) -> dict[str, Any]:
    outline = info.get("outline_mm")
    hole = info.get("glass_hole_local_mm")
    local_x = num(info.get("local_x_mm"))
    local_y = num(info.get("local_y_mm"))
    piece: dict[str, Any] = {
        "piece_instance_id": instance,
        "piece_id": info.get("piece_id"),
        "id": info.get("piece_id"),
        "label": info.get("label") or instance,
        "sheet_no": info.get("sheet_no"),
        "local_x_mm": local_x,
        "local_y_mm": local_y,
        "rotation_deg": 0,
        "editable": True,
        "allow_rotation": info.get("allow_rotation") is True,
        "allow_rotation_proven": info.get("allow_rotation_proven") is True,
        "outline_mm": deepcopy(outline) if isinstance(outline, list) else None,
        "glass_hole_local_mm": deepcopy(hole) if isinstance(hole, list) else None,
        "piece_type": info.get("piece_type") or "Regular",
        "placement_cm": {
            "x": local_x / 10.0,
            "y": local_y / 10.0,
            "w": num(info.get("width_mm")) / 10.0,
            "h": num(info.get("length_mm")) / 10.0,
        },
        "machining_paths": [],
    }
    return piece


def _liner_piece_from_trusted(info: Mapping[str, Any]) -> LinerPiece | None:
    width = num(info.get("original_w"))
    length = num(info.get("original_h"))
    if width <= 0:
        width = num(info.get("width_mm")) / 10.0
    if length <= 0:
        length = num(info.get("length_mm")) / 10.0
    if width <= 0 or length <= 0:
        return None
    if str(info.get("piece_type") or "") == "Special":
        return None
    return LinerPiece(
        str(info.get("piece_type") or "Regular"),
        width,
        length,
        str(info.get("clipped_corner_position") or "Top Right"),
        num(info.get("clipped_corner_width_cm")),
        num(info.get("clipped_corner_length_cm")),
    )


def _place_local_toolpath(
    info: Mapping[str, Any],
    liner: LinerPiece,
    local_path: list[tuple[float, float]],
) -> list[list[float]]:
    turns = piece_quarter_turns(
        {
            "corner_rotation_quarter_turns": info.get("corner_rotation_quarter_turns"),
            "rotated": info.get("source_rotated_dims"),
        }
    )
    mirrored = bool(info.get("corner_mirrored"))
    origin_x = num(info.get("local_x_mm"))
    origin_y = num(info.get("local_y_mm"))
    width = float(liner.width_cm) * 10.0
    height = float(liner.length_cm) * 10.0
    placed: list[list[float]] = []
    for point in local_path:
        moved = transform_point(
            (float(point[0]), float(point[1])),
            mirrored=mirrored,
            quarter_turns=turns,
            width=width,
            height=height,
        )
        placed.append([moved[0] + origin_x, moved[1] + origin_y])
    return placed


def _entry_machining_paths(
    info: Mapping[str, Any],
    *,
    kerf_mm: float,
    board_width_mm: float,
    board_length_mm: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build cutter-center paths once in the entry usable-sheet frame."""

    issues: list[dict[str, Any]] = []
    try:
        values = machining_values(info)
    except (DoorLinerError, LinerGeometryError, TypeError, ValueError) as exc:
        code = getattr(exc, "code", "") or "machining_values_unproven"
        issues.append(
            _issue(
                "geometry_unproven",
                piece_instance_ids=[str(info.get("piece_instance_id") or "")],
                piece_ids=_ids(info),
                reason=str(code),
                addon_kind="machining",
            )
        )
        return [], issues

    enabled = [addon for addon in MACHINING_ADDONS if (values.get(addon.kind) or {}).get("enabled")]
    if not enabled:
        return [], issues
    if kerf_mm <= 0:
        issues.append(
            _issue(
                "geometry_unproven",
                piece_instance_ids=[str(info.get("piece_instance_id") or "")],
                piece_ids=_ids(info),
                reason="cutter_diameter_unavailable",
                addon_kind=enabled[0].kind,
            )
        )
        return [], issues
    liner = _liner_piece_from_trusted(info)
    if liner is None:
        issues.append(
            _issue(
                "geometry_unproven",
                piece_instance_ids=[str(info.get("piece_instance_id") or "")],
                piece_ids=_ids(info),
                reason="addon_piece_geometry_unavailable",
                addon_kind=enabled[0].kind,
            )
        )
        return [], issues

    origin = (num(info.get("local_x_mm")), num(info.get("local_y_mm")))
    board = (
        0.0,
        0.0,
        max(0.0, board_width_mm),
        max(0.0, board_length_mm),
    )
    paths: list[dict[str, Any]] = []
    for addon in enabled:
        kind = addon.kind
        spec = values.get(kind) or {}
        try:
            if kind == "liner":
                liners = list(spec.get("liners") or ())
                width_cm = float(spec.get("width_cm") or 0)
                if liners and width_cm > 0:
                    specs = [
                        DoorLinerSpec(
                            str(row.get("id") or f"liner_{index + 1}"),
                            str(row.get("side") or ""),
                            float(row.get("offset_cm") or 0),
                            float(row.get("start_cm") or 0),
                            float(row.get("length_cm") or 0),
                        )
                        for index, row in enumerate(liners)
                    ]
                    start_flags = []
                    end_flags = []
                    for row in specs:
                        start_sawn, end_sawn = sawn_liner_ends(
                            liner,
                            row.side,
                            origin_mm=origin,
                            mirrored=bool(info.get("corner_mirrored")),
                            quarter_turns=piece_quarter_turns(
                                {
                                    "corner_rotation_quarter_turns": info.get(
                                        "corner_rotation_quarter_turns"
                                    ),
                                    "rotated": info.get("source_rotated_dims"),
                                }
                            ),
                            board=board,
                            start_cm=row.start_cm,
                            length_cm=row.length_cm,
                        )
                        start_flags.append(start_sawn)
                        end_flags.append(end_sawn)
                    local_paths = generate_liner_set_toolpaths(
                        piece=liner,
                        specs=specs,
                        width_cm=width_cm,
                        cutter_diameter_mm=kerf_mm,
                        start_sawn=start_flags,
                        end_sawn=end_flags,
                    )
                else:
                    start_sawn, end_sawn = sawn_liner_ends(
                        liner,
                        str(spec.get("side") or ""),
                        origin_mm=origin,
                        mirrored=bool(info.get("corner_mirrored")),
                        quarter_turns=piece_quarter_turns(
                            {
                                "corner_rotation_quarter_turns": info.get(
                                    "corner_rotation_quarter_turns"
                                ),
                                "rotated": info.get("source_rotated_dims"),
                            }
                        ),
                        board=board,
                        start_cm=float(spec.get("start_cm") or 0)
                        if spec.get("start_cm") not in (None, "")
                        else None,
                        length_cm=float(spec.get("length_cm") or 0)
                        if spec.get("length_cm") not in (None, "")
                        else None,
                    )
                    local_paths = [
                        generate_toolpath(
                            kind=kind,
                            piece=liner,
                            reference_side=str(spec.get("side") or ""),
                            offset_cm=float(spec.get("offset_cm") or 0),
                            width_cm=float(spec.get("width_cm") or 0),
                            start_cm=float(spec.get("start_cm") or 0)
                            if spec.get("start_cm") not in (None, "")
                            else None,
                            length_cm=float(spec.get("length_cm") or 0)
                            if spec.get("length_cm") not in (None, "")
                            else None,
                            cutter_diameter_mm=kerf_mm,
                            start_sawn=start_sawn,
                            end_sawn=end_sawn,
                        )
                    ]
            else:
                start_sawn, end_sawn = sawn_liner_ends(
                    liner,
                    str(spec.get("side") or ""),
                    origin_mm=origin,
                    mirrored=bool(info.get("corner_mirrored")),
                    quarter_turns=piece_quarter_turns(
                        {
                            "corner_rotation_quarter_turns": info.get(
                                "corner_rotation_quarter_turns"
                            ),
                            "rotated": info.get("source_rotated_dims"),
                        }
                    ),
                    board=board,
                    start_cm=float(spec.get("start_cm") or 0)
                    if spec.get("start_cm") not in (None, "")
                    else None,
                    length_cm=float(spec.get("length_cm") or 0)
                    if spec.get("length_cm") not in (None, "")
                    else None,
                )
                local_paths = [
                    generate_toolpath(
                        kind=kind,
                        piece=liner,
                        reference_side=str(spec.get("side") or ""),
                        offset_cm=float(spec.get("offset_cm") or 0),
                        width_cm=float(spec.get("width_cm") or 0),
                        start_cm=float(spec.get("start_cm") or 0)
                        if spec.get("start_cm") not in (None, "")
                        else None,
                        length_cm=float(spec.get("length_cm") or 0)
                        if spec.get("length_cm") not in (None, "")
                        else None,
                        cutter_diameter_mm=kerf_mm,
                        start_sawn=start_sawn,
                        end_sawn=end_sawn,
                    )
                ]
        except (LinerGeometryError, DoorLinerError, TypeError, ValueError) as exc:
            reason = getattr(exc, "code", "") or "addon_toolpath_unproven"
            issues.append(
                _issue(
                    "geometry_unproven",
                    piece_instance_ids=[str(info.get("piece_instance_id") or "")],
                    piece_ids=_ids(info),
                    reason=str(reason),
                    addon_kind=kind,
                )
            )
            continue
        for index, local in enumerate(local_paths):
            placed = _place_local_toolpath(info, liner, list(local or ()))
            if len(placed) < 2:
                issues.append(
                    _issue(
                        "geometry_unproven",
                        piece_instance_ids=[str(info.get("piece_instance_id") or "")],
                        piece_ids=_ids(info),
                        reason="addon_path_empty",
                        addon_kind=kind,
                    )
                )
                continue
            paths.append({"kind": kind, "path_index": index, "path_mm": placed})
    return paths, issues


def _addon_rules(
    placed: list[dict[str, Any]],
    sheets: Mapping[str, Mapping[str, Any]],
    kerf_mm: float,
    issues: list[dict[str, Any]],
) -> None:
    """Reuse liner extension clearance against neighbouring material.

    ``kerf_mm`` is the plan blade/cutter diameter already used by
    ``generate_toolpath`` / DXF liner export. It is not a second gap on top of
    piece-to-piece kerf, and it is not a substitute for the add-on strip width.
    ``extension_conflict_details`` ignores board bounds on purpose: historical
    policy allows a contour-end tip past the usable sheet, while piece material
    outside the usable sheet remains a separate placement fault.
    """

    by_sheet: dict[str, list[dict[str, Any]]] = {}
    for piece in placed:
        by_sheet.setdefault(str(piece.get("sheet_no")), []).append(piece)
    for sheet_no, group in by_sheet.items():
        obstacles_by_instance = {}
        for piece in group:
            footprint = piece_footprint_mm(piece)
            if not footprint.get("points"):
                continue
            holes = []
            hole = piece.get("glass_hole_local_mm")
            if isinstance(hole, list) and len(hole) >= 3:
                holes.append([(float(point[0]), float(point[1])) for point in hole])
            obstacles_by_instance[str(piece["piece_instance_id"])] = {
                "outer": [(float(point[0]), float(point[1])) for point in footprint["points"]],
                "holes": holes,
                "diagnostic": {
                    "piece_instance_id": piece["piece_instance_id"],
                    "piece_id": piece.get("piece_id"),
                    "label": piece.get("label"),
                },
            }
        board = sheets.get(str(sheet_no)) or {}
        board_bounds = (
            0.0,
            0.0,
            num(board.get("usable_width_mm")),
            num(board.get("usable_length_mm")),
        )
        for piece in group:
            owner = str(piece.get("piece_instance_id") or "")
            for item in piece.get("machining_paths") or []:
                path = item.get("path_mm") or []
                if len(path) < 2:
                    continue
                obstacles = [
                    obstacle
                    for instance, obstacle in obstacles_by_instance.items()
                    if instance != owner
                ]
                details = extension_conflict_details(
                    [(float(point[0]), float(point[1])) for point in path],
                    kerf_mm,
                    board_bounds,
                    obstacles,
                )
                if not details:
                    continue
                neighbor = details.get("obstacle") or {}
                neighbor_instance = str(neighbor.get("piece_instance_id") or "")
                neighbor_ids = []
                if neighbor.get("piece_id") not in (None, ""):
                    neighbor_ids = [int(neighbor["piece_id"])]
                issues.append(
                    _issue(
                        "addon_material_conflict",
                        piece_instance_ids=[
                            item
                            for item in (owner, neighbor_instance)
                            if item
                        ],
                        piece_ids=_ids(piece) + neighbor_ids,
                        sheet_nos=[int(sheet_no)] if str(sheet_no).lstrip("-").isdigit() else [],
                        addon_kind=str(item.get("kind") or ""),
                        reason=str(details.get("reject_condition") or ""),
                    )
                )


def _placement_rules(
    pieces: list[dict[str, Any]],
    sheets: Mapping[str, Mapping[str, Any]],
    issues: list[dict[str, Any]],
) -> None:
    for piece in pieces:
        try:
            decision = decision_from_piece(piece)
        except OffcutPolicyError:
            issues.append(_issue("unsupported_sheet_resource", piece_instance_ids=[piece["piece_instance_id"]], piece_ids=_ids(piece)))
            continue
        if decision.is_offcut and not decision.is_resolved:
            issues.append(_issue("offcut_unresolved", piece_instance_ids=[piece["piece_instance_id"]], piece_ids=_ids(piece)))
            continue
        if decision.is_customer_executed:
            continue
        if not decision.requires_factory_execution and not decision.consumes_full_board:
            continue
        if piece.get("distribution") == "excluded":
            issues.append(_issue("piece_excluded", piece_instance_ids=[piece["piece_instance_id"]], piece_ids=_ids(piece)))
            continue
        sheet_no = piece.get("sheet_no")
        if sheet_no in (None, ""):
            issues.append(_issue("piece_outside_board", piece_instance_ids=[piece["piece_instance_id"]], piece_ids=_ids(piece)))
            continue
        if piece.get("outline_mm") is None:
            continue
        footprint = piece_footprint_mm(piece)
        board = sheets.get(str(sheet_no)) or {}
        usable = {
            "x": 0.0,
            "y": 0.0,
            "w": num(board.get("usable_width_mm")),
            "h": num(board.get("usable_length_mm")),
        }
        points = footprint.get("points")
        inside = bool(points) and polygon_inside_rect(
            points,
            min_x=0.0,
            min_y=0.0,
            max_x=usable["w"],
            max_y=usable["h"],
            tolerance=1e-6,
        )
        if inside:
            continue
        code = "partial_board_overlap" if rect_intersects(footprint["bounds"], usable) else "outside_usable_sheet"
        issues.append(
            _issue(
                code,
                piece_instance_ids=[piece["piece_instance_id"]],
                piece_ids=_ids(piece),
                sheet_nos=[int(sheet_no)],
            )
        )


def _hosting_rules(placed: list[dict[str, Any]], issues: list[dict[str, Any]]) -> None:
    rows = []
    for piece in placed:
        if piece.get("piece_id") in (None, ""):
            continue
        rows.append(
            {
                "id": int(piece["piece_id"]),
                "label": piece.get("label"),
                "glass_host_piece_id": piece.get("glass_host_piece_id"),
                "_sheet_no": piece.get("sheet_no"),
            }
        )
    for issue in host_link_issue_codes(rows):
        guest = _piece_by_id(placed, issue.get("piece_id"))
        host = _piece_by_id(placed, issue.get("host_id"))
        issues.append(
            _issue(
                str(issue["code"]),
                piece_instance_ids=_instances(guest, host),
                piece_ids=[value for value in (issue.get("piece_id"), issue.get("host_id")) if value is not None],
                sheet_nos=_sheets_of(guest, host),
            )
        )
    for piece in placed:
        host_id = piece.get("glass_host_piece_id")
        if host_id in (None, ""):
            continue
        host = _piece_by_id(placed, host_id)
        if host is None or piece.get("outline_mm") is None or host.get("glass_hole_local_mm") is None:
            if host is not None and host.get("glass_hole_local_mm") is None:
                issues.append(
                    _issue(
                        "geometry_unproven",
                        piece_instance_ids=_instances(host),
                        piece_ids=_ids(host),
                        sheet_nos=_sheets_of(host),
                    )
                )
            continue
        hole = host.get("glass_hole_local_mm")
        guest_points = piece_footprint_mm(piece).get("points")
        if not isinstance(hole, list) or not guest_points:
            continue
        hole_points = tuple((float(point[0]), float(point[1])) for point in hole)
        guest_ring = tuple((float(point[0]), float(point[1])) for point in guest_points)
        if not polygon_strictly_contains_polygon(hole_points, guest_ring):
            issues.append(
                _issue(
                    "hosting_not_contained",
                    piece_instance_ids=_instances(piece, host),
                    piece_ids=_ids(piece) + _ids(host),
                    sheet_nos=_sheets_of(piece, host),
                )
            )


def _rotation_rules(
    pieces: list[dict[str, Any]],
    machine_type: str,
    issues: list[dict[str, Any]],
) -> None:
    for piece in pieces:
        if piece.get("distribution") == "excluded" or piece.get("sheet_no") in (None, ""):
            continue
        if decision_from_piece(piece).is_customer_executed:
            continue
        angle = num(piece.get("rotation_deg"))
        allowed = piece.get("allow_rotation") is True and piece.get("allow_rotation_proven") is True
        if not angles_equivalent(angle, 0) and not allowed:
            issues.append(
                _issue(
                    "rotation_forbidden",
                    piece_instance_ids=[piece["piece_instance_id"]],
                    piece_ids=_ids(piece),
                    sheet_nos=_sheets_of(piece),
                )
            )
        if machine_accepts_rotation(machine_type, angle):
            continue
        known = str(machine_type or "").strip() in {"Auto", "CNC Router", "Panel Saw"}
        issues.append(
            _issue(
                "machine_rotation_forbidden" if known else "machine_rotation_unproven",
                piece_instance_ids=[piece["piece_instance_id"]],
                piece_ids=_ids(piece),
                sheet_nos=_sheets_of(piece),
            )
        )


def _material_rules(
    placed: list[dict[str, Any]],
    kerf_mm: float,
    issues: list[dict[str, Any]],
) -> None:
    by_sheet: dict[str, list[dict[str, Any]]] = {}
    for piece in placed:
        if piece.get("outline_mm") is None:
            continue
        by_sheet.setdefault(str(piece.get("sheet_no")), []).append(piece)
    for sheet_no, group in by_sheet.items():
        parts = []
        for piece in group:
            footprint = piece_footprint_mm(piece)
            if not footprint.get("points"):
                continue
            holes = []
            hole = piece.get("glass_hole_local_mm")
            if isinstance(hole, list) and len(hole) >= 3:
                holes.append(tuple((float(point[0]), float(point[1])) for point in hole))
            parts.append(
                PlacedPartGeometry(
                    key=piece["piece_instance_id"],
                    geometry=PartGeometry(
                        outer=tuple((float(point[0]), float(point[1])) for point in footprint["points"]),
                        holes=tuple(holes),
                    ),
                )
            )
        for found in material_layout_issues(parts, required_clearance=max(0.0, kerf_mm)):
            code = {
                "MATERIAL_FOOTPRINT_OVERLAP": "piece_overlap",
                "PART_CLEARANCE_VIOLATION": "kerf_clearance",
                "HOLE_CLEARANCE_VIOLATION": "hole_kerf_clearance",
            }.get(str(found["code"]), "piece_overlap")
            instances = [str(found.get("first_key") or ""), str(found.get("second_key") or "")]
            issues.append(
                _issue(
                    code,
                    piece_instance_ids=[item for item in instances if item],
                    sheet_nos=[int(sheet_no)] if str(sheet_no).lstrip("-").isdigit() else [],
                )
            )


def _origin(sheets: Mapping[str, Mapping[str, Any]], sheet_no: Any) -> tuple[float, float]:
    if sheet_no in (None, ""):
        return 0.0, 0.0
    board = sheets.get(str(sheet_no)) or {}
    return num(board.get("origin_x_mm")) + num(board.get("trim_x_mm")), num(board.get("origin_y_mm")) + num(board.get("trim_y_mm"))


def _piece_by_id(pieces: list[dict[str, Any]], piece_id: Any) -> dict[str, Any] | None:
    for piece in pieces:
        if piece.get("piece_id") == piece_id:
            return piece
    return None


def _ids(piece: Mapping[str, Any] | None) -> list[int]:
    if not piece or piece.get("piece_id") in (None, ""):
        return []
    return [int(piece["piece_id"])]


def _instances(*pieces: Mapping[str, Any] | None) -> list[str]:
    return [
        str(piece.get("piece_instance_id"))
        for piece in pieces
        if piece and piece.get("piece_instance_id")
    ]


def _sheets_of(*pieces: Mapping[str, Any] | None) -> list[int]:
    numbers = []
    for piece in pieces:
        if not piece or piece.get("sheet_no") in (None, ""):
            continue
        number = int(piece["sheet_no"])
        if number not in numbers:
            numbers.append(number)
    return numbers


def _issue(
    code: str,
    *,
    severity: str = ERROR,
    piece_instance_ids: list[str] | None = None,
    piece_ids: list[int] | None = None,
    sheet_nos: list[int] | None = None,
    addon_kind: str = "",
    reason: str = "",
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "piece_instance_ids": list(piece_instance_ids or []),
        "piece_ids": list(piece_ids or []),
        "sheet_nos": list(sheet_nos or []),
        "addon_kind": str(addon_kind or ""),
        "reason": str(reason or ""),
    }


def _dedupe(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    unique = []
    for issue in issues:
        key = (
            issue["code"],
            tuple(issue["piece_instance_ids"]),
            tuple(issue["sheet_nos"]),
            issue.get("addon_kind") or "",
            issue.get("reason") or "",
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(issue)
    return unique


def _result(
    ready: bool,
    version: int,
    fingerprint: str,
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "ready": ready,
        "draft_version": version,
        "distribution_fingerprint": fingerprint,
        "issues": issues,
    }
