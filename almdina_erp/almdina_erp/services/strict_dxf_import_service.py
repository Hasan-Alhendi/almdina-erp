from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from almdina_erp.almdina_erp.application.cutting.plan_revisions import PlanSettings
from almdina_erp.almdina_erp.domain.cutting.corner_contour_rotation import (
    match_corner_contour,
    measure_l_remainings_cm,
)
from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    LINER_SHAPE_MISMATCH as LINER_SHAPE_CODE,
    LinerMeasurement,
    LinerPiece,
    canonical_path,
    compare_liner_path,
    contour_notch_cm,
    liner_parameters_active,
    localize_path,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_applied_trim import (
    DxfAppliedTrimError,
    apply_adaptive_trim_to_fixed_dxf_layout,
)
from almdina_erp.almdina_erp.domain.cutting.manufacturing_requirements import (
    ManufacturingRequirementsError,
    require_cut_dimension_cm,
)
from almdina_erp.almdina_erp.domain.cutting.piece_cut_dimensions import (
    CutDimensionError,
    MM_PER_CM,
    dimensions_match_exact,
    l_shaped_raw_cut,
    normalize_cut_cm,
    special_bbox_allowed_range_cm,
    special_bbox_matches_cut_envelope_with_unrecorded_edge_deduction,
)
from almdina_erp.almdina_erp.domain.orders.extra_addons import (
    EXTRA_ADDON_FIELD_BY_CODE,
    physical_cut_quantity,
)
from almdina_erp.almdina_erp.domain.orders.piece_policy import is_corner_cut
from almdina_erp.almdina_erp.domain.cutting.dxf_issue import (
    CATEGORY_DIMENSIONS,
    CATEGORY_IDENTITY,
    CATEGORY_LAYOUT,
    CATEGORY_PERSISTENCE,
    CATEGORY_TOPOLOGY,
    APPLIED_TRIM_OVERFLOW,
    CORNER_EDGE_UNRESOLVED,
    L_CORNER_NOTCH_MISMATCH,
    CUT_DIMENSIONS_BIND_FAILED,
    CUT_DIMENSIONS_MISSING,
    CUT_SIZE_MISMATCH,
    FORBIDDEN_ROTATION,
    PERSISTED_CUT_SPECS,
    PERSISTED_CUT_CONTEXT_CODES,
    PIECE_IDENTITY_MISSING,
    PIECE_MISSING,
    contour_target,
    SKIP_PERSISTED_CUT_CONTEXT_CODES,
    SPECIAL_SIZE_MISMATCH,
    DxfIssueTarget,
    DxfValidationIssue,
    issue,
    piece_target,
)
from almdina_erp.almdina_erp.services.dxf_import_service import (
    DxfImportError,
    liner_geometry_issue,
    parse_production_dxf as _legacy_parse_production_dxf,
)
from almdina_erp.almdina_erp.services.piece_cut_dimension_service import (
    OrderPieceCutSpec,
    build_order_piece_cut_specs,
)


_EDGE_FIELD_BY_SIDE = {
    "long_right": "edge_long_right",
    "long_left": "edge_long_left",
    "width_top": "edge_width_top",
    "width_bottom": "edge_width_bottom",
}
_CUT_QUANTUM_CM = Decimal("0.001")


def _format_decimal(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _format_spec(spec: OrderPieceCutSpec) -> str:
    return (
        f"المقاس النهائي {_format_decimal(spec.finished_width_cm)} × "
        f"{_format_decimal(spec.finished_length_cm)} سم؛ "
        f"حسم القشاط: من العرض {_format_decimal(spec.width_deduction_mm)} مم "
        f"ومن الطول {_format_decimal(spec.length_deduction_mm)} مم؛ "
        f"مقاس القص المطلوب {_format_decimal(spec.cut_width_cm)} × "
        f"{_format_decimal(spec.cut_length_cm)} سم"
    )


def _bind_persisted_cut_dimensions(
    order: Any,
    specs: list[OrderPieceCutSpec],
) -> list[OrderPieceCutSpec]:
    """Make saved DCO cut fields authoritative for strict DXF identity matching.

    ``build_order_piece_cut_specs`` still owns the existing edge-print metadata
    contract. Its calculated dimensions are intentionally discarded here because
    ALMADINA-143 requires a newly uploaded DXF to match the cut dimensions already
    persisted on the saved DCO, not a recomputation from current edge master data.
    """

    rows = list(getattr(order, "pieces", None) or [])
    if len(rows) != len(specs):
        raise DxfImportError(
            issues=[issue(CUT_DIMENSIONS_BIND_FAILED, CATEGORY_PERSISTENCE)]
        )

    persisted_specs: list[OrderPieceCutSpec] = []
    for row_index, (row, spec) in enumerate(zip(rows, specs), start=1):
        if spec.row_index != row_index:
            raise DxfImportError(
                issues=[issue(CUT_DIMENSIONS_BIND_FAILED, CATEGORY_PERSISTENCE)]
            )
        try:
            cut_width_cm = Decimal(
                str(
                    require_cut_dimension_cm(
                        getattr(row, "cut_width_cm", None),
                        fieldname="cut_width_cm",
                    )
                )
            ).quantize(_CUT_QUANTUM_CM)
            cut_length_cm = Decimal(
                str(
                    require_cut_dimension_cm(
                        getattr(row, "cut_length_cm", None),
                        fieldname="cut_length_cm",
                    )
                )
            ).quantize(_CUT_QUANTUM_CM)
        except ManufacturingRequirementsError as exc:
            raise DxfImportError(
                issues=[
                    issue(
                        CUT_DIMENSIONS_MISSING,
                        CATEGORY_PERSISTENCE,
                        target=piece_target(source_piece_no=row_index),
                    )
                ]
            ) from exc

        persisted_specs.append(
            replace(
                spec,
                cut_width_cm=cut_width_cm,
                cut_length_cm=cut_length_cm,
                width_deduction_mm=(spec.finished_width_cm - cut_width_cm)
                * Decimal("10"),
                length_deduction_mm=(spec.finished_length_cm - cut_length_cm)
                * Decimal("10"),
            )
        )

    return persisted_specs


def _row_for_spec(order: Any, spec: OrderPieceCutSpec) -> Any | None:
    rows = list(getattr(order, "pieces", None) or [])
    index = spec.row_index - 1
    if 0 <= index < len(rows):
        return rows[index]
    return None


def _physical_spec_qty(order: Any | None, spec: OrderPieceCutSpec) -> int:
    if order is None:
        return spec.qty
    row = _row_for_spec(order, spec)
    return physical_cut_quantity(
        spec.qty,
        full_door_double=bool(int(getattr(row, "extra_full_door_double", 0) or 0)) if row else False,
    )


def _proxy_order(
    order: Any,
    specs: list[OrderPieceCutSpec],
    settings: PlanSettings,
) -> Any:
    pieces = []
    for spec in specs:
        row = _row_for_spec(order, spec)
        addon_flags = {
            attr: getattr(row, attr, 0) if row else 0
            for attr in EXTRA_ADDON_FIELD_BY_CODE.values()
        }
        pieces.append(
            SimpleNamespace(
                qty=spec.qty,
                **addon_flags,
                # The legacy topology parser expects its public width/length inputs in
                # manufacturing space. Preserve the same canonical values explicitly
                # under cut_* as well so ALMADINA-143 never relies on a finished-size
                # fallback while this internal proxy crosses the service boundary.
                width_cm=float(spec.cut_width_cm),
                length_cm=float(spec.cut_length_cm),
                cut_width_cm=float(spec.cut_width_cm),
                cut_length_cm=float(spec.cut_length_cm),
                finished_width_cm=float(spec.finished_width_cm),
                finished_length_cm=float(spec.finished_length_cm),
                allow_rotation=spec.allow_rotation,
                piece_type=spec.piece_type,
                liner_reference_side=str(getattr(row, "liner_reference_side", "") or ""),
                liner_offset_cm=float(getattr(row, "liner_offset_cm", 0) or 0),
                liner_width_cm=float(getattr(row, "liner_width_cm", 0) or 0),
            )
        )
    return SimpleNamespace(
        pieces=pieces,
        # Before ALMADINA-141 this boundary used
        # trim_margin_mm=settings.trim_margin_mm directly. Geometry ingestion now
        # validates physical coordinates with zero inset, then the canonical
        # ALMADINA-138 resolver derives the Applied Trim from the same settings.
        trim_margin_mm=0.0,
        board_width_cm=getattr(order, "board_width_cm", 0),
        board_length_cm=getattr(order, "board_length_cm", 0),
        full_board_width_mm=getattr(order, "full_board_width_mm", 0),
        full_board_length_mm=getattr(order, "full_board_length_mm", 0),
        kerf_mm=settings.kerf_mm,
    )


def _expanded_expected(
    specs: list[OrderPieceCutSpec],
    order: Any | None = None,
) -> list[dict[str, Any]]:
    expected: list[dict[str, Any]] = []
    for spec in specs:
        row_identity = str(
            getattr(_row_for_spec(order, spec), "piece_instance_id", "") or ""
        ).strip()
        if not row_identity:
            raise DxfImportError(
                issues=[
                    issue(
                        PIECE_IDENTITY_MISSING,
                        CATEGORY_IDENTITY,
                        target=piece_target(source_piece_no=spec.row_index),
                    )
                ]
            )
        for copy_no in range(1, _physical_spec_qty(order, spec) + 1):
            expected.append(
                {
                    "expected_index": len(expected),
                    "spec": spec,
                    "copy_no": copy_no,
                    "label": f"{spec.row_index}.{copy_no}",
                    "piece_instance_id": f"{row_identity}:{copy_no}",
                }
            )
    return expected


def _actual_dimensions(piece: dict[str, Any]) -> tuple[Decimal, Decimal]:
    return normalize_cut_cm(piece.get("w")), normalize_cut_cm(piece.get("h"))


def _find_exact_candidate(
    unmatched: list[dict[str, Any]],
    actual_w: Decimal,
    actual_h: Decimal,
    *,
    rotated: bool,
    require_rotation_allowed: bool = True,
    piece: dict[str, Any] | None = None,
) -> int | None:
    matches: list[int] = []
    for index, candidate in enumerate(unmatched):
        spec: OrderPieceCutSpec = candidate["spec"]
        if rotated:
            if require_rotation_allowed and not spec.allow_rotation:
                continue
            expected_w, expected_h = spec.cut_length_cm, spec.cut_width_cm
        else:
            expected_w, expected_h = spec.cut_width_cm, spec.cut_length_cm
        if dimensions_match_exact(actual_w, actual_h, expected_w, expected_h):
            matches.append(index)
    if len(matches) <= 1 or piece is None:
        return matches[0] if matches else None
    identified = _unique_corner_contour_candidate(unmatched, matches, piece)
    return matches[0] if identified is None else identified


def _corner_band_tokens(spec: OrderPieceCutSpec) -> dict[str, str]:
    """Token per semantic edge. Equal tokens mean a swap does not move a band."""

    profiles = {
        str(profile.get("side") or ""): profile
        for profile in spec.side_profiles
    }

    def side_token(side: str) -> str:
        profile = profiles.get(side)
        if not profile:
            return "0"
        return (
            "1|"
            f"{profile.get('edge_type') or ''}|"
            f"{profile.get('thickness_mm') or 0}"
        )

    if spec.edge_break:
        notch = "break"
    elif spec.edge_break_only and spec.piece_type == "Clipped Corner":
        notch = "break-only"
    else:
        notch = "open"
    return {
        "top": side_token("width_top"),
        "bottom": side_token("width_bottom"),
        "left": side_token("long_left"),
        "right": side_token("long_right"),
        "inner_horizontal": notch,
        "inner_vertical": notch,
        "chord": notch,
    }


def _unique_corner_contour_candidate(
    unmatched: list[dict[str, Any]],
    matches: list[int],
    piece: dict[str, Any],
) -> int | None:
    """Pick the one corner row whose full contour matches when outer size does not.

    Identical contours keep the existing first-match order. A contour that
    matches none, or more than one row, does not guess a row here.
    """

    if not all(is_corner_cut(unmatched[index]["spec"].piece_type) for index in matches):
        return None
    outer = _outer_ring_mm(piece)
    if outer is None:
        return None
    identified: list[int] = []
    for index in matches:
        spec: OrderPieceCutSpec = unmatched[index]["spec"]
        notch_width_cm, notch_length_cm = _contour_notch_cm(spec)
        match = match_corner_contour(
            outer,
            piece_type=spec.piece_type,
            position=str(spec.clipped_corner_position or ""),
            width_cm=float(spec.cut_width_cm),
            length_cm=float(spec.cut_length_cm),
            cut_width_cm=notch_width_cm,
            cut_length_cm=notch_length_cm,
            edge_bands=_corner_band_tokens(spec),
        )
        if match.reason == "unique":
            identified.append(index)
    return identified[0] if len(identified) == 1 else None


def _topology_special_candidate(
    unmatched: list[dict[str, Any]],
    piece: dict[str, Any],
) -> int | None:
    """Resolve a Special piece only from identity proven by the topology importer."""
    if str(piece.get("piece_type") or "") != "Special":
        return None

    label = str(piece.get("label") or "").strip()
    try:
        source_piece_no = int(piece.get("source_piece_no") or 0)
        copy_no = int(piece.get("copy_no") or 0)
    except (TypeError, ValueError):
        return None
    if not label or source_piece_no <= 0 or copy_no <= 0:
        return None

    matches = [
        index
        for index, candidate in enumerate(unmatched)
        if candidate["label"] == label
        and candidate["copy_no"] == copy_no
        and candidate["spec"].row_index == source_piece_no
        and candidate["spec"].piece_type == "Special"
    ]
    return matches[0] if len(matches) == 1 else None


def _topology_candidate(
    unmatched: list[dict[str, Any]],
    piece: dict[str, Any],
) -> int | None:
    """Resolve any piece only through the importer-owned canonical topology index."""
    try:
        expected_index = int(piece.get("_expected_piece_index"))
    except (TypeError, ValueError):
        return None
    matches = [
        index
        for index, candidate in enumerate(unmatched)
        if candidate.get("expected_index") == expected_index
    ]
    return matches[0] if len(matches) == 1 else None


def _dimension_issue(
    code: str,
    *,
    spec: OrderPieceCutSpec,
    candidate: dict[str, Any],
    actual_w: Decimal,
    actual_h: Decimal,
) -> DxfValidationIssue:
    params = {
        "actual_width_cm": float(actual_w),
        "actual_height_cm": float(actual_h),
        "expected_width_cm": float(spec.cut_width_cm),
        "expected_height_cm": float(spec.cut_length_cm),
        "piece_type": spec.piece_type,
        "spec_summary": _format_spec(spec),
    }
    if code == SPECIAL_SIZE_MISMATCH:
        min_w, max_w, min_h, max_h = special_bbox_allowed_range_cm(
            spec.cut_width_cm, spec.cut_length_cm
        )
        params.update({
            "allowed_min_width_cm": float(min_w),
            "allowed_max_width_cm": float(max_w),
            "allowed_min_height_cm": float(min_h),
            "allowed_max_height_cm": float(max_h),
        })
    return issue(
        code,
        CATEGORY_DIMENSIONS,
        target=piece_target(
            source_piece_no=spec.row_index,
            copy_no=int(candidate.get("copy_no") or 1),
            label=str(candidate.get("label") or ""),
        ),
        params=params,
    )


def _validate_topology_candidate_dimensions(
    piece: dict[str, Any],
    candidate: dict[str, Any],
) -> tuple[bool | None, DxfValidationIssue | None]:
    """Validate a topology-owned piece against its persisted cut envelope."""
    actual_w, actual_h = _actual_dimensions(piece)
    spec: OrderPieceCutSpec = candidate["spec"]

    if spec.piece_type == "Special":
        direct_match = special_bbox_matches_cut_envelope_with_unrecorded_edge_deduction(
            actual_w,
            actual_h,
            spec.cut_width_cm,
            spec.cut_length_cm,
        )
        if direct_match:
            return False, None

        rotated_match = special_bbox_matches_cut_envelope_with_unrecorded_edge_deduction(
            actual_w,
            actual_h,
            spec.cut_length_cm,
            spec.cut_width_cm,
        )
        if rotated_match:
            if spec.allow_rotation:
                return True, None
            return None, _dimension_issue(
                FORBIDDEN_ROTATION,
                spec=spec,
                candidate=candidate,
                actual_w=actual_w,
                actual_h=actual_h,
            )

        return None, _dimension_issue(
            SPECIAL_SIZE_MISMATCH,
            spec=spec,
            candidate=candidate,
            actual_w=actual_w,
            actual_h=actual_h,
        )

    if dimensions_match_exact(
        actual_w,
        actual_h,
        spec.cut_width_cm,
        spec.cut_length_cm,
    ):
        return False, None

    if dimensions_match_exact(
        actual_w,
        actual_h,
        spec.cut_length_cm,
        spec.cut_width_cm,
    ):
        if spec.allow_rotation:
            return True, None
        return None, _dimension_issue(
            FORBIDDEN_ROTATION,
            spec=spec,
            candidate=candidate,
            actual_w=actual_w,
            actual_h=actual_h,
        )

    return None, _dimension_issue(
        CUT_SIZE_MISMATCH,
        spec=spec,
        candidate=candidate,
        actual_w=actual_w,
        actual_h=actual_h,
    )


def _edge_print_contract(spec: OrderPieceCutSpec) -> dict[str, Any]:
    """Return canonical plan-piece edge metadata used by screen and print renderers.

    Edge flags stay in the finished-door physical orientation. The renderer owns
    visual rotation, so a rotated DXF piece receives the same four semantic edge
    flags as the source order row instead of pre-rotating them here.
    """
    flags: dict[str, Any] = {
        fieldname: 0 for fieldname in _EDGE_FIELD_BY_SIDE.values()
    }
    profiles: dict[str, dict[str, Any]] = {}

    for profile in spec.side_profiles:
        side = str(profile.get("side") or "")
        fieldname = _EDGE_FIELD_BY_SIDE.get(side)
        if not fieldname:
            continue

        flags[fieldname] = 1
        profiles[side] = {
            "side": side,
            "side_label": str(profile.get("side_label") or ""),
            "edge_type": str(profile.get("edge_type") or ""),
            "thickness_mm": float(profile.get("thickness_mm") or 0),
        }

    edge_types = {
        str(profile.get("edge_type") or "").strip()
        for profile in profiles.values()
        if str(profile.get("edge_type") or "").strip()
    }
    flags["edge_type"] = next(iter(edge_types)) if len(edge_types) == 1 else ""
    flags["edge_profiles"] = profiles
    flags["edge_break"] = 1 if getattr(spec, "edge_break", 0) else 0
    if is_corner_cut(spec.piece_type):
        flags["edge_break_only"] = 1 if getattr(spec, "edge_break_only", 0) else 0
    return flags


def _apply_piece_contract_metadata(
    piece: dict[str, Any],
    candidate: dict[str, Any],
    *,
    rotated: bool,
) -> None:
    spec: OrderPieceCutSpec = candidate["spec"]
    piece["label"] = candidate["label"]
    piece["piece_instance_id"] = candidate["piece_instance_id"]
    piece["resource_kind"] = piece.get("resource_kind") or "FULL_BOARD"
    piece["offcut_source_party"] = piece.get("offcut_source_party") or "UNASSIGNED"
    piece["offcut_execution_party"] = piece.get("offcut_execution_party") or "UNASSIGNED"
    piece["source_piece_no"] = spec.row_index
    piece["copy_no"] = candidate["copy_no"]
    piece["rotated"] = rotated
    # DCO business identity is authoritative. The imported contour stays
    # physical geometry truth for bounds/topology but cannot reclassify a
    # Special door as Regular merely because its bbox is rectangular.
    piece["piece_type"] = spec.piece_type
    piece["original_w"] = float(spec.cut_width_cm)
    piece["original_h"] = float(spec.cut_length_cm)
    piece["finished_w"] = float(spec.finished_width_cm)
    piece["finished_h"] = float(spec.finished_length_cm)
    piece["cut_width_cm"] = float(spec.cut_width_cm)
    piece["cut_length_cm"] = float(spec.cut_length_cm)
    piece["edge_width_deduction_mm"] = float(spec.width_deduction_mm)
    piece["edge_length_deduction_mm"] = float(spec.length_deduction_mm)
    if is_corner_cut(spec.piece_type):
        piece["clipped_corner_position"] = str(spec.clipped_corner_position or "")
        piece["clipped_corner_width_cm"] = float(spec.clipped_corner_width_cm)
        piece["clipped_corner_length_cm"] = float(spec.clipped_corner_length_cm)
    piece.update(_edge_print_contract(spec))


def _corner_edge_markers_selected(piece: dict[str, Any]) -> bool:
    return any(
        piece.get(fieldname)
        for fieldname in (
            "edge_long_right",
            "edge_long_left",
            "edge_width_top",
            "edge_width_bottom",
            "edge_break",
            "edge_break_only",
        )
    )


def _side_thickness_mm(spec: OrderPieceCutSpec) -> dict[str, Decimal]:
    thicknesses = {
        side: Decimal("0")
        for side in ("long_right", "long_left", "width_top", "width_bottom")
    }
    for profile in spec.side_profiles:
        side = str(profile.get("side") or "")
        if side in thicknesses:
            thicknesses[side] = Decimal(str(profile.get("thickness_mm") or 0))
    return thicknesses


def _l_corner_cut(spec: OrderPieceCutSpec):
    if spec.piece_type != "L-Shaped Corner":
        return None
    return l_shaped_raw_cut(
        finished_width_cm=spec.finished_width_cm,
        finished_length_cm=spec.finished_length_cm,
        notch_width_cm=spec.clipped_corner_width_cm,
        notch_length_cm=spec.clipped_corner_length_cm,
        position=str(spec.clipped_corner_position or ""),
        side_thickness_mm=_side_thickness_mm(spec),
        edge_break=bool(spec.edge_break),
        edge_break_thickness_mm=spec.edge_break_thickness_mm,
    )


def _contour_notch_cm(spec: OrderPieceCutSpec) -> tuple[float, float]:
    """Notch passed to the contour matcher and to liner checks, in centimetres."""

    return contour_notch_cm(
        piece_type=spec.piece_type,
        finished_width_cm=float(spec.finished_width_cm),
        finished_length_cm=float(spec.finished_length_cm),
        notch_width_cm=float(spec.clipped_corner_width_cm),
        notch_length_cm=float(spec.clipped_corner_length_cm),
        position=str(spec.clipped_corner_position or ""),
        side_thickness_mm=_side_thickness_mm(spec),
        edge_break=bool(spec.edge_break),
        edge_break_thickness_mm=spec.edge_break_thickness_mm,
    )


def _l_notch_mismatch_issue(
    piece: dict[str, Any],
    spec: OrderPieceCutSpec,
    candidate: dict[str, Any],
    outer: list[list[float]],
) -> DxfValidationIssue | None:
    raw = _l_corner_cut(spec)
    if raw is None or not raw.proven:
        return None
    measured = measure_l_remainings_cm(outer, rotated=bool(piece.get("rotated")))
    if measured is None:
        return None
    axes: list[dict[str, str]] = []
    for name, axis_cut, actual in (
        ("width", raw.width, measured[0]),
        ("length", raw.length, measured[1]),
    ):
        if axis_cut.expected_raw_cm is None or axis_cut.band_mm is None:
            return None
        actual_cm = normalize_cut_cm(actual)
        if actual_cm == axis_cut.expected_raw_cm:
            continue
        axes.append(
            {
                "axis": name,
                "finished_remaining_cm": str(axis_cut.finished_remaining_cm),
                "band_mm": str(axis_cut.band_mm),
                "expected_raw_cm": str(axis_cut.expected_raw_cm),
                "actual_raw_cm": str(actual_cm),
                "delta_mm": str((actual_cm - axis_cut.expected_raw_cm) * MM_PER_CM),
            }
        )
    if not axes:
        return None
    return issue(
        L_CORNER_NOTCH_MISMATCH,
        CATEGORY_DIMENSIONS,
        target=piece_target(
            source_piece_no=spec.row_index,
            copy_no=int(candidate.get("copy_no") or 1),
            label=str(candidate.get("label") or ""),
        ),
        params={"piece_type": spec.piece_type, "axes": axes},
    )


def _l_break_thickness_unproven(
    piece: dict[str, Any],
    spec: OrderPieceCutSpec,
    outer: list[list[float]],
) -> bool:
    if spec.piece_type != "L-Shaped Corner" or not spec.edge_break:
        return False
    if spec.edge_break_thickness_mm is not None:
        return False
    return measure_l_remainings_cm(outer, rotated=bool(piece.get("rotated"))) is not None


def _outer_ring_mm(piece: dict[str, Any]) -> list[list[float]] | None:
    geometry = piece.get("geometry")
    if not isinstance(geometry, dict):
        return None
    outer = geometry.get("outer")
    if isinstance(outer, (str, bytes)) or not isinstance(outer, list) or len(outer) < 3:
        return None
    return outer


def _bind_corner_edge_rotation(
    piece: dict[str, Any],
    candidate: dict[str, Any],
) -> DxfValidationIssue | None:
    """Record the unique dihedral transform used to place corner edge bands.

    ``rotated`` stays the bbox flag owned by dimension matching. It cannot tell
    0° from 180°, 90° from 270°, or a reflection from either, so corner bands
    do not read it. The imported contour itself is not transformed here.
    """

    spec: OrderPieceCutSpec = candidate["spec"]
    if not is_corner_cut(spec.piece_type) or not _corner_edge_markers_selected(piece):
        return None

    outer = _outer_ring_mm(piece)
    notch_width_cm, notch_length_cm = _contour_notch_cm(spec)
    match = (
        match_corner_contour(
            outer,
            piece_type=spec.piece_type,
            position=str(spec.clipped_corner_position or ""),
            width_cm=float(spec.cut_width_cm),
            length_cm=float(spec.cut_length_cm),
            cut_width_cm=notch_width_cm,
            cut_length_cm=notch_length_cm,
            edge_bands=_corner_band_tokens(spec),
        )
        if outer is not None
        else None
    )
    if match is None or match.quarter_turns is None:
        if outer is not None:
            mismatch = _l_notch_mismatch_issue(piece, spec, candidate, outer)
            if mismatch is not None:
                return mismatch
        reason = match.reason if match is not None else "none"
        if (
            reason == "none"
            and outer is not None
            and _l_break_thickness_unproven(piece, spec, outer)
        ):
            reason = "break_thickness_unknown"
        return issue(
            CORNER_EDGE_UNRESOLVED,
            CATEGORY_TOPOLOGY,
            target=piece_target(
                source_piece_no=spec.row_index,
                copy_no=int(candidate.get("copy_no") or 1),
                label=str(candidate.get("label") or ""),
            ),
            params={
                "piece_type": spec.piece_type,
                "reason": reason,
            },
        )

    if match.quarter_turns and not spec.allow_rotation:
        actual_w, actual_h = _actual_dimensions(piece)
        return _dimension_issue(
            FORBIDDEN_ROTATION,
            spec=spec,
            candidate=candidate,
            actual_w=actual_w,
            actual_h=actual_h,
        )

    piece["corner_rotation_quarter_turns"] = int(match.quarter_turns)
    piece["corner_mirrored"] = 1 if match.mirrored else 0
    return None


def _corner_liner_issue(piece: dict[str, Any], spec: OrderPieceCutSpec, order: Any | None):
    if not is_corner_cut(spec.piece_type) or order is None:
        return None
    row = _row_for_spec(order, spec)
    enabled = bool(int(getattr(row, "extra_liner", 0) or 0)) if row else False
    side = str(getattr(row, "liner_reference_side", "") or "") if row else ""
    offset_cm = float(getattr(row, "liner_offset_cm", 0) or 0) if row else 0.0
    width_cm = float(getattr(row, "liner_width_cm", 0) or 0) if row else 0.0
    if not liner_parameters_active(
        enabled=enabled,
        side=side,
        offset_cm=offset_cm,
        width_cm=width_cm,
    ):
        return None
    liners = [
        overlay
        for overlay in (piece.get("overlays") or [])
        if isinstance(overlay, dict) and overlay.get("kind") == "liner"
    ]
    if len(liners) != 1:
        return None
    geometry = piece.get("geometry") if isinstance(piece.get("geometry"), dict) else {}
    outer = geometry.get("outer") or ()
    path = ((liners[0].get("geometry") or {}).get("path") or ())
    if len(outer) < 3 or len(path) < 2:
        return None
    notch_width_cm, notch_length_cm = _contour_notch_cm(spec)
    if "corner_rotation_quarter_turns" in piece:
        turns = int(piece.get("corner_rotation_quarter_turns") or 0)
        mirrored = bool(int(piece.get("corner_mirrored") or 0))
    else:
        match = match_corner_contour(
            outer,
            piece_type=spec.piece_type,
            position=str(spec.clipped_corner_position or ""),
            width_cm=float(spec.cut_width_cm),
            length_cm=float(spec.cut_length_cm),
            cut_width_cm=notch_width_cm,
            cut_length_cm=notch_length_cm,
        )
        if match.quarter_turns is None:
            return liner_geometry_issue(
                LinerMeasurement(False, LINER_SHAPE_CODE, "shape", side, "", "orientation_unresolved"),
                source_piece_no=spec.row_index,
                copy_no=int(piece.get("copy_no") or 1),
                piece_type=spec.piece_type,
            )
        turns = int(match.quarter_turns)
        mirrored = bool(match.mirrored)
    local = localize_path(path, outer)
    canonical = canonical_path(
        local,
        mirrored=mirrored,
        quarter_turns=turns,
        width_mm=float(spec.cut_width_cm) * 10.0,
        height_mm=float(spec.cut_length_cm) * 10.0,
    )
    measurement = compare_liner_path(
        canonical,
        LinerPiece(
            spec.piece_type,
            float(spec.cut_width_cm),
            float(spec.cut_length_cm),
            str(spec.clipped_corner_position or ""),
            notch_width_cm,
            notch_length_cm,
        ),
        side,
        offset_cm,
        width_cm,
        (
            float(getattr(order, "kerf_mm", 0) or 0)
            if float(getattr(order, "kerf_mm", 0) or 0) > 0
            else None
        ),
    )
    return liner_geometry_issue(
        measurement,
        source_piece_no=spec.row_index,
        copy_no=int(piece.get("copy_no") or 1),
        piece_type=spec.piece_type,
    )


def _apply_strict_dimension_contract(
    snapshot: dict[str, Any],
    specs: list[OrderPieceCutSpec],
    *,
    order: Any | None = None,
) -> list[DxfValidationIssue]:
    """Relabel pieces and enrich them with exact order + edge-print metadata."""
    issues: list[DxfValidationIssue] = []
    unmatched = _expanded_expected(specs, order)

    for sheet in snapshot.get("sheets") or []:
        for piece in sheet.get("pieces") or []:
            # Prefer the importer-owned index when present. After
            # ``_public_piece`` strips private keys, Special pieces still carry
            # label/source/copy identity that ``_topology_special_candidate``
            # can prove uniquely against the order.
            topology_index = _topology_candidate(unmatched, piece)
            if topology_index is None:
                topology_index = _topology_special_candidate(unmatched, piece)
            if topology_index is not None:
                candidate = unmatched[topology_index]
                rotated, error = _validate_topology_candidate_dimensions(
                    piece,
                    candidate,
                )
                if error:
                    issues.append(error)
                    # A topology-owned expected index proves which persisted
                    # copy is present even when its dimensions are rejected.
                    # Consume that copy so the residual inventory reports only
                    # genuinely unmatched expected pieces.
                    unmatched.pop(topology_index)
                    continue
                unmatched.pop(topology_index)
                _apply_piece_contract_metadata(
                    piece,
                    candidate,
                    rotated=bool(rotated),
                )
                binding_error = _bind_corner_edge_rotation(piece, candidate)
                if binding_error:
                    issues.append(binding_error)
                else:
                    liner_issue = _corner_liner_issue(piece, candidate["spec"], order)
                    if liner_issue is not None:
                        issues.append(liner_issue)
                continue
            if str(piece.get("piece_type") or "") == "Special":
                issues.append(
                    issue(
                        PIECE_IDENTITY_MISSING,
                        CATEGORY_IDENTITY,
                        target=(
                            contour_target(int(piece["id"]))
                            if str(piece.get("id") or "").isdigit()
                            else DxfIssueTarget()
                        ),
                        params={"piece_type": "Special"},
                    )
                )
                continue

            actual_w, actual_h = _actual_dimensions(piece)
            direct_index = _find_exact_candidate(
                unmatched,
                actual_w,
                actual_h,
                rotated=False,
                piece=piece,
            )
            rotated_index = _find_exact_candidate(
                unmatched,
                actual_w,
                actual_h,
                rotated=True,
                piece=piece,
            )
            match_index = direct_index if direct_index is not None else rotated_index
            rotated = direct_index is None and rotated_index is not None

            if match_index is None:
                forbidden_index = _find_exact_candidate(
                    unmatched,
                    actual_w,
                    actual_h,
                    rotated=True,
                    require_rotation_allowed=False,
                    piece=piece,
                )
                if forbidden_index is not None:
                    candidate = unmatched[forbidden_index]
                    issues.append(
                        _dimension_issue(
                            FORBIDDEN_ROTATION,
                            spec=candidate["spec"],
                            candidate=candidate,
                            actual_w=actual_w,
                            actual_h=actual_h,
                        )
                    )
                    continue

                # A complete canonical label identifies a specific expected
                # copy even when its dimensions are rejected. Consume only
                # that proven-present copy; row-only hints cannot establish
                # copy identity and must not suppress a genuine missing-copy
                # diagnostic.
                legacy_label = str(piece.get("label") or "").strip()
                identified_index = next(
                    (
                        index
                        for index, candidate in enumerate(unmatched)
                        if candidate["label"] == legacy_label
                    ),
                    None,
                )
                if identified_index is not None:
                    candidate = unmatched.pop(identified_index)
                    issues.append(
                        _dimension_issue(
                            CUT_SIZE_MISMATCH,
                            spec=candidate["spec"],
                            candidate=candidate,
                            actual_w=actual_w,
                            actual_h=actual_h,
                        )
                    )
                else:
                    issues.append(
                        issue(
                            CUT_SIZE_MISMATCH,
                            CATEGORY_DIMENSIONS,
                            params={
                                "actual_width_cm": float(actual_w),
                                "actual_height_cm": float(actual_h),
                            },
                        )
                    )
                continue

            candidate = unmatched.pop(match_index)
            _apply_piece_contract_metadata(piece, candidate, rotated=rotated)
            binding_error = _bind_corner_edge_rotation(piece, candidate)
            if binding_error:
                issues.append(binding_error)
            else:
                liner_issue = _corner_liner_issue(piece, candidate["spec"], order)
                if liner_issue is not None:
                    issues.append(liner_issue)

    if unmatched:
        preview = "، ".join(
            f"{candidate['label']} ({_format_decimal(candidate['spec'].cut_width_cm)} × "
            f"{_format_decimal(candidate['spec'].cut_length_cm)} سم)"
            for candidate in unmatched[:8]
        )
        suffix = " ..." if len(unmatched) > 8 else ""
        issues.append(
            issue(
                PIECE_MISSING,
                CATEGORY_IDENTITY,
                params={"preview": f"{preview}{suffix}"},
            )
        )
    return issues


def _has_self_contained_forbidden_rotation(
    item: DxfValidationIssue,
) -> bool:
    """Return whether a rotation error already identifies its door and both sizes."""
    if item.code != FORBIDDEN_ROTATION:
        return False
    try:
        has_target_row = int(getattr(item.target, "source_piece_no", 0) or 0) > 0
    except (TypeError, ValueError):
        has_target_row = False

    params = item.params or {}
    dimension_fields = (
        (
            "actual_width_cm",
            "actual_height_cm",
            "expected_width_cm",
            "expected_height_cm",
        ),
        (
            "actual_width_mm",
            "actual_height_mm",
            "expected_width_mm",
            "expected_height_mm",
        ),
    )
    if has_target_row and any(
        all(params.get(field) is not None for field in fields)
        for fields in dimension_fields
    ):
        return True

    measurements = params.get("possible_measurements_cm")
    candidate_rows = params.get("candidate_source_piece_nos") or ()
    if not measurements:
        return False
    try:
        has_row_evidence = (
            has_target_row or bool(candidate_rows)
        )
    except (TypeError, ValueError):
        has_row_evidence = bool(candidate_rows)
    if not has_row_evidence:
        return False
    required_fields = (
        "actual_width_cm",
        "actual_height_cm",
        "expected_width_cm",
        "expected_height_cm",
    )
    return all(
        all(measurement.get(field) is not None for field in required_fields)
        for measurement in measurements
    )


def _with_persisted_cut_context(
    error: DxfImportError,
    specs: list[OrderPieceCutSpec],
) -> DxfImportError:
    """Keep the original geometry diagnosis and append persisted cut specs."""
    issue_codes = {item.code for item in error.issues}
    if issue_codes & SKIP_PERSISTED_CUT_CONTEXT_CODES:
        return error
    needs_context = any(
        item.code in PERSISTED_CUT_CONTEXT_CODES
        and not _has_self_contained_forbidden_rotation(item)
        for item in error.issues
    )
    if not needs_context:
        return error
    expected = "؛ ".join(
        f"الدرفة {spec.row_index}: {_format_spec(spec)}" for spec in specs[:8]
    )
    suffix = " ..." if len(specs) > 8 else ""
    annotated = list(error.issues) + [
        issue(
            PERSISTED_CUT_SPECS,
            CATEGORY_PERSISTENCE,
            params={"preview": f"{expected}{suffix}"},
        )
    ]
    return DxfImportError(issues=annotated)


def parse_production_dxf(
    file_url: str,
    order: Any,
    *,
    settings: PlanSettings,
) -> dict[str, Any]:
    """Validate DXF against order pieces and canonical Cutting Plan settings.

    Topology/layers/physical board bounds/kerf remain owned by the geometry
    importer. Applied Trim is resolved over that fixed physical layout through
    ALMADINA-138. Persisted cut dimensions remain the manufacturing source of
    truth: all non-Special pieces require exact identity at 0.001 cm, while a
    Special bbox may be up to 2 mm smaller per axis for unrecorded edge
    deductions, with no oversize. Special outlines remain topology-owned and
    shape-free.
    """
    try:
        specs = build_order_piece_cut_specs(order)
    except CutDimensionError as exc:
        raise DxfImportError(
            issues=[
                issue(
                    CUT_DIMENSIONS_MISSING,
                    CATEGORY_PERSISTENCE,
                    params={"message": str(message)},
                )
                for message in (exc.errors or ["مقاسات القص غير صالحة."])
            ]
        ) from exc
    specs = _bind_persisted_cut_dimensions(order, specs)

    try:
        snapshot = _legacy_parse_production_dxf(
            file_url,
            _proxy_order(order, specs, settings),
        )
    except DxfImportError as exc:
        annotated = _with_persisted_cut_context(exc, specs)
        if annotated is exc:
            raise
        raise annotated from exc

    try:
        snapshot = apply_adaptive_trim_to_fixed_dxf_layout(
            snapshot,
            preferred_trim_mm=settings.preferred_trim_mm,
        )
    except DxfAppliedTrimError as exc:
        raise DxfImportError(
            issues=[issue(APPLIED_TRIM_OVERFLOW, CATEGORY_LAYOUT)]
        ) from exc

    exact_issues = _apply_strict_dimension_contract(snapshot, specs, order=order)
    if exact_issues:
        raise DxfImportError(issues=exact_issues)

    snapshot["dimension_contract"] = {
        "mode": "exact-edge-adjusted",
        "identity": "persisted-cut-envelope",
        "precision_cm": "0.001",
        "finished_dimensions_immutable": True,
        "special_outline_identity": "topology-owned",
        "special_bbox_match_required": True,
        "special_max_unrecorded_edge_deduction_mm": 2,
        "piece_dimension_rules": {
            "default": "exact-persisted-cut",
            "Special": {
                "identity": "persisted-cut-envelope",
                "max_unrecorded_edge_deduction_mm_per_axis": 2,
                "oversize_allowed": False,
            },
        },
    }
    snapshot["print_contract"] = {
        "renderer": "canonical-cutting-plan",
        "edge_markers_from_order": True,
        "rotation_owned_by_renderer": True,
    }
    return snapshot


__all__ = ["parse_production_dxf"]
