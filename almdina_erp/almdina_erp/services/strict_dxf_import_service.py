from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from almdina_erp.almdina_erp.application.cutting.plan_revisions import PlanSettings
from almdina_erp.almdina_erp.domain.cutting.corner_contour_rotation import (
    classify_corner_contour_type,
    match_corner_contour,
    measure_corner_remainings_cm,
    measure_l_remainings_cm,
)
from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    LINER_SHAPE_MISMATCH as LINER_SHAPE_CODE,
    LinerGeometryError,
    LinerMeasurement,
    LinerPiece,
    canonical_path,
    contour_notch_cm,
    liner_parameters_active,
    localize_path,
    sawn_liner_ends,
)
from almdina_erp.almdina_erp.domain.cutting.machining_overlay import (
    MACHINING_ADDONS,
    MACHINING_ADDONS_BY_KIND,
    compare_liner_set_paths,
    compare_overlay_path,
    machining_metadata,
    machining_values,
)
from almdina_erp.almdina_erp.domain.cutting.regular_machining_orientation import (
    match_regular_machining_orientation,
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
from almdina_erp.almdina_erp.domain.orders.piece_mirroring import (
    piece_mirroring_allowed,
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
    CLIPPED_CORNER_DIMENSIONS_MISMATCH,
    REGULAR_EDGE_ORIENTATION_UNRESOLVED,
    L_CORNER_NOTCH_MISMATCH,
    CUT_DIMENSIONS_BIND_FAILED,
    CUT_DIMENSIONS_MISSING,
    CUT_SIZE_MISMATCH,
    FORBIDDEN_MIRRORING,
    FORBIDDEN_ROTATION,
    PERSISTED_CUT_SPECS,
    PERSISTED_CUT_CONTEXT_CODES,
    PIECE_IDENTITY_MISSING,
    PIECE_IDENTITY_AMBIGUOUS,
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


@dataclass(frozen=True, slots=True)
class _ExactCandidateMatch:
    index: int | None
    corner_reason: str | None = None
    candidate_rows: tuple[int, ...] = ()


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
        piece_values = {
            "qty": spec.qty,
            **addon_flags,
            # The legacy topology parser expects its public width/length inputs in
            # manufacturing space. Preserve the same canonical values explicitly
            # under cut_* as well so ALMADINA-143 never relies on a finished-size
            # fallback while this internal proxy crosses the service boundary.
            "width_cm": float(spec.cut_width_cm),
            "length_cm": float(spec.cut_length_cm),
            "cut_width_cm": float(spec.cut_width_cm),
            "cut_length_cm": float(spec.cut_length_cm),
            "finished_width_cm": float(spec.finished_width_cm),
            "finished_length_cm": float(spec.finished_length_cm),
            "allow_rotation": spec.allow_rotation,
            "piece_type": spec.piece_type,
            "liner_reference_side": str(getattr(row, "liner_reference_side", "") or ""),
            "liner_offset_cm": float(getattr(row, "liner_offset_cm", 0) or 0),
            "liner_width_cm": float(getattr(row, "liner_width_cm", 0) or 0),
            "liner_start_cm": float(getattr(row, "liner_start_cm", 0) or 0),
            "liner_length_cm": float(getattr(row, "liner_length_cm", 0) or 0),
            "liner_specs_json": str(getattr(row, "liner_specs_json", "") or ""),
        }
        # Copy only fields that exist on the saved row. A missing glass margin
        # stays missing so import can tell a dropped field from a blank value.
        for fieldname in (
            "glass_margin_mm",
            "edge_long_left",
            "edge_long_right",
            "edge_width_top",
            "edge_width_bottom",
            "edge_long_thickness_mm",
            "edge_width_thickness_mm",
        ):
            if row is not None and hasattr(row, fieldname):
                piece_values[fieldname] = getattr(row, fieldname)
        for addon in MACHINING_ADDONS:
            for fieldname in (
                addon.side_field, addon.offset_field, addon.width_field,
                addon.start_field, addon.length_field,
            ):
                if row is not None and hasattr(row, fieldname):
                    piece_values[fieldname] = getattr(row, fieldname)
        pieces.append(SimpleNamespace(**piece_values))
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
) -> _ExactCandidateMatch:
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
        return _ExactCandidateMatch(matches[0] if matches else None)
    if all(is_corner_cut(unmatched[index]["spec"].piece_type) for index in matches):
        return _unique_corner_contour_candidate(unmatched, matches, piece)
    return _ExactCandidateMatch(matches[0])


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
) -> _ExactCandidateMatch:
    """Pick the one corner row whose full contour matches when outer size does not.

    Physical copies of one order row are one geometric candidate. Once that
    row is proven, its first unmatched copy keeps deterministic copy numbering.
    A contour that matches none, or more than one distinct row, never falls
    back to bounding-box order.
    """

    outer = _outer_ring_mm(piece)
    if outer is None:
        return _ExactCandidateMatch(None, "none")

    actual_corner_type = classify_corner_contour_type(outer)
    if actual_corner_type is not None:
        compatible_matches = [
            index
            for index in matches
            if unmatched[index]["spec"].piece_type == actual_corner_type
        ]
        # Keep the historical unresolved path when no candidate has the
        # proven topology. When a compatible row exists, however, do not let
        # an equal-bbox L and clipped row remain ambiguous merely because the
        # requested notch dimensions are wrong.
        if compatible_matches:
            matches = compatible_matches

    first_copy_by_row: dict[int, int] = {}
    for index in matches:
        spec: OrderPieceCutSpec = unmatched[index]["spec"]
        first_copy_by_row.setdefault(spec.row_index, index)

    identified_rows: list[int] = []
    for row_index, index in first_copy_by_row.items():
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
        # An ambiguous transform still proves the order-row geometry. The
        # later edge-binding step owns whether that transform ambiguity is
        # acceptable for the row's edge-band contract.
        if match.reason in {"unique", "ambiguous"}:
            identified_rows.append(row_index)

    if len(identified_rows) == 1:
        row_index = identified_rows[0]
        return _ExactCandidateMatch(
            first_copy_by_row[row_index],
            "unique",
            (row_index,),
        )
    if identified_rows:
        return _ExactCandidateMatch(
            None,
            "ambiguous",
            tuple(sorted(identified_rows)),
        )
    return _ExactCandidateMatch(
        None,
        "none",
        tuple(sorted(first_copy_by_row)),
    )


def _imported_identity_candidate(
    unmatched: list[dict[str, Any]],
    piece: dict[str, Any],
) -> int | None:
    """Preserve importer-owned identity after private keys are stripped.

    These labels come from the order binding, never from DXF TEXT.
    """
    if str(piece.get("piece_type") or "") not in {"Special", "Regular"}:
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
        and candidate["spec"].piece_type == piece["piece_type"]
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
    *,
    rotated: bool | None = None,
) -> DxfValidationIssue | None:
    raw = _l_corner_cut(spec)
    if raw is None or not raw.proven:
        return None
    is_rotated = bool(piece.get("rotated")) if rotated is None else rotated
    measured = measure_l_remainings_cm(outer, rotated=is_rotated)
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
        params={
            "piece_type": spec.piece_type,
            "axes": axes,
            "expected_finished_remaining_cm": {
                "width": str(raw.width.finished_remaining_cm),
                "length": str(raw.length.finished_remaining_cm),
            },
            "expected_raw_remaining_cm": {
                "width": str(raw.width.expected_raw_cm),
                "length": str(raw.length.expected_raw_cm),
            },
            "actual_raw_remaining_cm": {
                "width": str(normalize_cut_cm(measured[0])),
                "length": str(normalize_cut_cm(measured[1])),
            },
        },
    )


def _clipped_corner_dimensions_mismatch_issue(
    piece: dict[str, Any],
    spec: OrderPieceCutSpec,
    candidate: dict[str, Any],
    outer: list[list[float]],
    *,
    rotated: bool,
) -> DxfValidationIssue | None:
    if spec.piece_type != "Clipped Corner":
        return None
    measured = measure_corner_remainings_cm(
        outer,
        piece_type=spec.piece_type,
        rotated=rotated,
    )
    if measured is None:
        return None
    notch_width_cm, notch_length_cm = _contour_notch_cm(spec)
    expected_finished = (
        normalize_cut_cm(spec.finished_width_cm - spec.clipped_corner_width_cm),
        normalize_cut_cm(spec.finished_length_cm - spec.clipped_corner_length_cm),
    )
    expected_raw = (
        normalize_cut_cm(spec.cut_width_cm - Decimal(str(notch_width_cm))),
        normalize_cut_cm(spec.cut_length_cm - Decimal(str(notch_length_cm))),
    )
    actual_raw = (
        normalize_cut_cm(measured[0]),
        normalize_cut_cm(measured[1]),
    )
    if actual_raw == expected_raw:
        return None
    axes: list[dict[str, str]] = []
    for index, name in enumerate(("width", "length")):
        if actual_raw[index] == expected_raw[index]:
            continue
        band_mm = (expected_finished[index] - expected_raw[index]) * MM_PER_CM
        axes.append(
            {
                "axis": name,
                "finished_remaining_cm": str(expected_finished[index]),
                "band_mm": str(band_mm),
                "expected_raw_cm": str(expected_raw[index]),
                "actual_raw_cm": str(actual_raw[index]),
                "delta_mm": str((actual_raw[index] - expected_raw[index]) * MM_PER_CM),
            }
        )
    return issue(
        CLIPPED_CORNER_DIMENSIONS_MISMATCH,
        CATEGORY_DIMENSIONS,
        target=piece_target(
            source_piece_no=spec.row_index,
            copy_no=int(candidate.get("copy_no") or 1),
            label=str(candidate.get("label") or ""),
        ),
        params={
            "piece_type": spec.piece_type,
            "axes": axes,
            "expected_finished_remaining_cm": {
                "width": str(expected_finished[0]),
                "length": str(expected_finished[1]),
            },
            "expected_raw_remaining_cm": {
                "width": str(expected_raw[0]),
                "length": str(expected_raw[1]),
            },
            "actual_raw_remaining_cm": {
                "width": str(actual_raw[0]),
                "length": str(actual_raw[1]),
            },
        },
    )


def _corner_dimensions_mismatch_issue(
    piece: dict[str, Any],
    spec: OrderPieceCutSpec,
    candidate: dict[str, Any],
    outer: list[list[float]],
    *,
    rotated: bool,
) -> DxfValidationIssue | None:
    if spec.piece_type == "L-Shaped Corner":
        return _l_notch_mismatch_issue(
            piece,
            spec,
            candidate,
            outer,
            rotated=rotated,
        )
    return _clipped_corner_dimensions_mismatch_issue(
        piece,
        spec,
        candidate,
        outer,
        rotated=rotated,
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


def _unique_unresolved_corner_dimension_candidate(
    unmatched: list[dict[str, Any]],
    piece: dict[str, Any],
    results: tuple[tuple[bool, _ExactCandidateMatch], ...],
) -> tuple[int, DxfValidationIssue] | None:
    """Diagnose one proven corner row without guessing among equal-size rows."""

    rows = {
        row_index
        for _rotated, result in results
        if result.corner_reason == "none"
        for row_index in result.candidate_rows
    }
    if len(rows) != 1:
        return None
    row_index = next(iter(rows))
    candidate_index = next(
        (
            index
            for index, candidate in enumerate(unmatched)
            if candidate["spec"].row_index == row_index
        ),
        None,
    )
    if candidate_index is None:
        return None

    candidate = unmatched[candidate_index]
    spec: OrderPieceCutSpec = candidate["spec"]
    outer = _outer_ring_mm(piece)
    if outer is None:
        return None
    rotations = []
    for rotated, result in results:
        if row_index in result.candidate_rows and rotated not in rotations:
            rotations.append(rotated)

    diagnosed: list[DxfValidationIssue] = []
    for rotated in rotations:
        measured = measure_corner_remainings_cm(
            outer,
            piece_type=spec.piece_type,
            rotated=rotated,
        )
        if measured is None:
            continue
        mismatch = _corner_dimensions_mismatch_issue(
            piece,
            spec,
            candidate,
            outer,
            rotated=rotated,
        )
        if mismatch is None:
            reason = (
                "break_thickness_unknown"
                if spec.piece_type == "L-Shaped Corner"
                and spec.edge_break
                and spec.edge_break_thickness_mm is None
                else "none"
            )
            return (
                candidate_index,
                issue(
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
                ),
            )
        diagnosed.append(mismatch)
    return (candidate_index, diagnosed[0]) if diagnosed else None


def _bind_corner_edge_rotation(
    piece: dict[str, Any],
    candidate: dict[str, Any],
    *,
    allow_piece_mirroring: object = None,
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
            mismatch = _corner_dimensions_mismatch_issue(
                piece,
                spec,
                candidate,
                outer,
                rotated=bool(piece.get("rotated")),
            )
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
    if match.mirrored and not piece_mirroring_allowed(allow_piece_mirroring):
        return issue(
            FORBIDDEN_MIRRORING,
            CATEGORY_DIMENSIONS,
            target=piece_target(
                source_piece_no=spec.row_index,
                copy_no=int(candidate.get("copy_no") or 1),
                label=str(candidate.get("label") or ""),
            ),
            params={"piece_type": spec.piece_type},
        )

    piece["corner_rotation_quarter_turns"] = int(match.quarter_turns)
    piece["corner_mirrored"] = 1 if match.mirrored else 0
    return None


def _shifted_board_mm(sheet: dict[str, Any] | None) -> tuple[float, float, float, float] | None:
    """Physical board in the post-adaptive usable frame.

    Legacy ingestion for a strict import does not subtract trim. Adaptive trim
    then shifts piece coordinates by the applied inset, so the board origin in
    that frame sits one applied inset outside usable ``(0, 0)``. The inset is
    the symmetric difference between the physical sheet and its usable size.
    """

    if not sheet:
        return None
    full_w = float(sheet.get("full_width_cm") or 0.0) * 10.0
    full_h = float(sheet.get("full_length_cm") or 0.0) * 10.0
    if full_w <= 0.0 or full_h <= 0.0:
        return None
    usable_w = sheet.get("usable_width_cm")
    usable_h = sheet.get("usable_length_cm")
    if usable_w is None:
        usable_w = sheet.get("w")
    if usable_h is None:
        usable_h = sheet.get("h")
    applied_w = max(0.0, (full_w - float(usable_w) * 10.0) / 2.0) if usable_w is not None else 0.0
    applied_l = max(0.0, (full_h - float(usable_h) * 10.0) / 2.0) if usable_h is not None else 0.0
    return (-applied_w, -applied_l, full_w - applied_w, full_h - applied_l)


def _corner_liner_issue(
    piece: dict[str, Any],
    spec: OrderPieceCutSpec,
    order: Any | None,
    *,
    cutter_diameter_mm: float | None = None,
    sheet: dict[str, Any] | None = None,
    kind: str = "liner",
):
    if not is_corner_cut(spec.piece_type) or order is None:
        return None
    addon = MACHINING_ADDONS_BY_KIND[kind]
    row = _row_for_spec(order, spec)
    enabled = bool(int(getattr(row, addon.enabled_field, 0) or 0)) if row else False
    side = str(getattr(row, addon.side_field, "") or "") if row else ""
    offset_cm = float(getattr(row, addon.offset_field, 0) or 0) if row else 0.0
    width_cm = float(getattr(row, addon.width_field, 0) or 0) if row else 0.0
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
        if isinstance(overlay, dict) and overlay.get("kind") == kind
    ]
    if kind != "liner" and len(liners) != 1:
        return None
    if kind == "liner" and not liners:
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
                overlay_kind=kind,
            )
        turns = int(match.quarter_turns)
        mirrored = bool(match.mirrored)
    liner_piece = LinerPiece(
        spec.piece_type,
        float(spec.cut_width_cm),
        float(spec.cut_length_cm),
        str(spec.clipped_corner_position or ""),
        notch_width_cm,
        notch_length_cm,
    )
    canonical_paths = []
    for overlay in liners:
        overlay_path = ((overlay.get("geometry") or {}).get("path") or ())
        if len(overlay_path) < 2:
            continue
        canonical_paths.append(
            canonical_path(
                localize_path(overlay_path, outer),
                mirrored=mirrored,
                quarter_turns=turns,
                width_mm=float(spec.cut_width_cm) * 10.0,
                height_mm=float(spec.cut_length_cm) * 10.0,
            )
        )
    if not canonical_paths:
        return None
    start_cm = float(getattr(row, addon.start_field, 0) or 0) if row else None
    length_cm = float(getattr(row, addon.length_field, 0) or 0) if row else None
    machining = machining_values(row) if row is not None else {}
    liner_specs = tuple((machining.get("liner") or {}).get("liners") or ())
    if kind == "liner" and (len(liner_specs) > 1 or len(canonical_paths) != 1):
        measurement = compare_liner_set_paths(
            canonical_paths,
            liner_piece,
            liner_specs
            or (
                {
                    "side": side,
                    "offset_cm": offset_cm,
                    "start_cm": start_cm,
                    "length_cm": length_cm,
                },
            ),
            width_cm,
            (
                float(cutter_diameter_mm)
                if cutter_diameter_mm is not None and float(cutter_diameter_mm) > 0
                else None
            ),
        )
    else:
        try:
            start_sawn, end_sawn = sawn_liner_ends(
                liner_piece,
                side,
                origin_mm=(float(piece.get("x") or 0.0) * 10.0, float(piece.get("y") or 0.0) * 10.0),
                mirrored=mirrored,
                quarter_turns=turns,
                board=_shifted_board_mm(sheet),
                start_cm=start_cm,
                length_cm=length_cm,
            )
        except LinerGeometryError:
            start_sawn, end_sawn = None, None
        measurement = compare_overlay_path(
            canonical_paths[0],
            liner_piece,
            kind,
            side,
            offset_cm,
            width_cm,
            (
                float(cutter_diameter_mm)
                if cutter_diameter_mm is not None and float(cutter_diameter_mm) > 0
                else None
            ),
            start_cm,
            length_cm,
            start_sawn=start_sawn,
            end_sawn=end_sawn,
        )
    return liner_geometry_issue(
        measurement,
        source_piece_no=spec.row_index,
        copy_no=int(piece.get("copy_no") or 1),
        piece_type=spec.piece_type,
        overlay_kind=kind,
    )


def _corner_machining_issues(
    piece: dict[str, Any],
    spec: OrderPieceCutSpec,
    order: Any | None,
    *,
    cutter_diameter_mm: float | None = None,
    sheet: dict[str, Any] | None = None,
):
    issues = []
    for addon in MACHINING_ADDONS:
        found = _corner_liner_issue(
            piece,
            spec,
            order,
            cutter_diameter_mm=cutter_diameter_mm,
            sheet=sheet,
            kind=addon.kind,
        )
        if found is not None:
            issues.append(found)
    return issues



def _regular_machining_issues(
    piece: dict[str, Any],
    spec: OrderPieceCutSpec,
    order: Any | None,
    *,
    cutter_diameter_mm: float | None,
    sheet: dict[str, Any] | None,
) -> list[DxfValidationIssue]:
    """Bind one proved rotation after exact dimensions and piece identity."""
    if spec.piece_type != "Regular" or order is None:
        return []
    row = _row_for_spec(order, spec)
    if row is None:
        return []
    settings = machining_values(row)
    if not any(
        item["enabled"] and item["side"] and item["width_cm"] > 0
        for item in settings.values()
    ):
        # Without geometric evidence, preserve the historical 0/90 contract.
        # Never assert that its 180/270 physical orientation was proved.
        return []

    geometry = piece.get("geometry") or {}
    outer = geometry.get("outer") or []
    if len(outer) < 3:
        return []
    grouped: dict[str, list] = {}
    for overlay in piece.get("overlays") or []:
        if not isinstance(overlay, dict):
            continue
        path = ((overlay.get("geometry") or {}).get("path") or ())
        if len(path) >= 2:
            kind = str(overlay.get("kind") or "")
            grouped.setdefault(kind, []).append(localize_path(path, outer))
    paths = {
        kind: items[0] if len(items) == 1 else items
        for kind, items in grouped.items()
    }

    actual_w, actual_h = _actual_dimensions(piece)
    # Strict dimensions already selected direct/swapped geometry. A square
    # permits all four angles; a non-square admits only one parity.
    square = dimensions_match_exact(
        spec.cut_width_cm, spec.cut_length_cm,
        spec.cut_length_cm, spec.cut_width_cm,
    )
    turns = (0, 1, 2, 3) if square else ((1, 3) if piece.get("rotated") else (0, 2))
    result = match_regular_machining_orientation(
        piece=LinerPiece("Regular", float(spec.cut_width_cm), float(spec.cut_length_cm)),
        overlay_paths=paths,
        settings=settings,
        candidate_turns=turns,
        edge_bands=_corner_band_tokens(spec),
        cutter_diameter_mm=cutter_diameter_mm,
        origin_mm=(float(piece.get("x") or 0) * 10, float(piece.get("y") or 0) * 10),
        board_mm=_shifted_board_mm(sheet),
    )
    target = piece_target(source_piece_no=spec.row_index, copy_no=int(piece.get("copy_no") or 1))
    if result.reason == "ambiguous":
        return [
            issue(
                REGULAR_EDGE_ORIENTATION_UNRESOLVED,
                CATEGORY_TOPOLOGY,
                target=target,
                params={"reason": "machining_symmetric"},
            )
        ]
    if result.reason == "invalid":
        if result.failure is not None:
            return [
                liner_geometry_issue(
                    result.failure,
                    source_piece_no=spec.row_index,
                    copy_no=int(piece.get("copy_no") or 1),
                    piece_type=spec.piece_type,
                    overlay_kind=result.failed_kind,
                )
            ]
        return [
            issue(
                REGULAR_EDGE_ORIENTATION_UNRESOLVED,
                CATEGORY_TOPOLOGY,
                target=target,
                params={"reason": "machining_invalid"},
            )
        ]
    if result.quarter_turns is None:
        return []
    if result.quarter_turns != 0 and not spec.allow_rotation:
        return [
            _dimension_issue(
                FORBIDDEN_ROTATION, spec=spec,
                candidate={"label": piece.get("label"), "copy_no": piece.get("copy_no")},
                actual_w=actual_w, actual_h=actual_h,
            )
        ]
    # Persist the same canonical machining settings used to prove orientation.
    # Export and preview consume this physical binding without re-reading or
    # guessing each add-on's side. Do not write metadata on invalid imports.
    piece.update(machining_metadata(row))
    piece["rotation_quarter_turns"] = result.quarter_turns
    return []


def _piece_machining_issues(
    piece: dict[str, Any],
    spec: OrderPieceCutSpec,
    order: Any | None,
    *,
    cutter_diameter_mm: float | None,
    sheet: dict[str, Any] | None,
) -> list[DxfValidationIssue]:
    if spec.piece_type == "Regular":
        return _regular_machining_issues(
            piece, spec, order,
            cutter_diameter_mm=cutter_diameter_mm, sheet=sheet,
        )
    return _corner_machining_issues(
        piece, spec, order,
        cutter_diameter_mm=cutter_diameter_mm, sheet=sheet,
    )


def _apply_strict_dimension_contract(
    snapshot: dict[str, Any],
    specs: list[OrderPieceCutSpec],
    *,
    order: Any | None = None,
    cutter_diameter_mm: float | None = None,
) -> list[DxfValidationIssue]:
    """Relabel pieces and enrich them with exact order + edge-print metadata."""
    issues: list[DxfValidationIssue] = []
    unmatched = _expanded_expected(specs, order)

    for sheet in snapshot.get("sheets") or []:
        for piece in sheet.get("pieces") or []:
            # Prefer the importer-owned index when present. After
            # ``_public_piece`` strips private keys, imported pieces still carry
            # label/source/copy identity that ``_imported_identity_candidate``
            # can prove uniquely against the order.
            topology_index = _topology_candidate(unmatched, piece)
            if topology_index is None:
                topology_index = _imported_identity_candidate(unmatched, piece)
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
                binding_error = _bind_corner_edge_rotation(
                    piece,
                    candidate,
                    allow_piece_mirroring=(
                        getattr(order, "allow_piece_mirroring", None) if order is not None else None
                    ),
                )
                if binding_error:
                    issues.append(binding_error)
                else:
                    issues.extend(
                        _piece_machining_issues(
                            piece,
                            candidate["spec"],
                            order,
                            cutter_diameter_mm=cutter_diameter_mm,
                            sheet=sheet,
                        )
                    )
                continue
            if str(piece.get("piece_type") or "") == "Special" or (
                piece.get("piece_type") == "Regular"
                and (piece.get("_expected_piece_index") is not None or (
                    piece.get("source_piece_no") and piece.get("copy_no")
                ))
            ):
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
            direct_match = _find_exact_candidate(
                unmatched,
                actual_w,
                actual_h,
                rotated=False,
                piece=piece,
            )
            rotated_match = _find_exact_candidate(
                unmatched,
                actual_w,
                actual_h,
                rotated=True,
                piece=piece,
            )
            ambiguous_rows = tuple(sorted({
                row_index
                for result in (direct_match, rotated_match)
                if result.corner_reason == "ambiguous"
                for row_index in result.candidate_rows
            }))
            if (
                direct_match.index is not None
                and rotated_match.index is not None
                and direct_match.index != rotated_match.index
                and is_corner_cut(
                    unmatched[direct_match.index]["spec"].piece_type
                )
                and is_corner_cut(
                    unmatched[rotated_match.index]["spec"].piece_type
                )
            ):
                ambiguous_rows = tuple(sorted({
                    unmatched[direct_match.index]["spec"].row_index,
                    unmatched[rotated_match.index]["spec"].row_index,
                }))
            if ambiguous_rows:
                issues.append(
                    issue(
                        PIECE_IDENTITY_AMBIGUOUS,
                        CATEGORY_IDENTITY,
                        target=(
                            contour_target(int(piece["id"]))
                            if str(piece.get("id") or "").isdigit()
                            else DxfIssueTarget()
                        ),
                        params={"candidate_source_piece_nos": list(ambiguous_rows)},
                    )
                )
                continue

            match_index = (
                direct_match.index
                if direct_match.index is not None
                else rotated_match.index
            )
            rotated = direct_match.index is None and rotated_match.index is not None

            if match_index is None:
                forbidden_match = _find_exact_candidate(
                    unmatched,
                    actual_w,
                    actual_h,
                    rotated=True,
                    require_rotation_allowed=False,
                    piece=piece,
                )
                if forbidden_match.corner_reason == "ambiguous":
                    issues.append(
                        issue(
                            PIECE_IDENTITY_AMBIGUOUS,
                            CATEGORY_IDENTITY,
                            target=(
                                contour_target(int(piece["id"]))
                                if str(piece.get("id") or "").isdigit()
                                else DxfIssueTarget()
                            ),
                            params={
                                "candidate_source_piece_nos": list(
                                    forbidden_match.candidate_rows
                                )
                            },
                        )
                    )
                    continue
                if forbidden_match.index is not None:
                    candidate = unmatched[forbidden_match.index]
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

                corner_dimension_candidate = _unique_unresolved_corner_dimension_candidate(
                    unmatched,
                    piece,
                    (
                        (False, direct_match),
                        (True, rotated_match),
                        (True, forbidden_match),
                    ),
                )
                if corner_dimension_candidate is not None:
                    diagnosed_index, diagnosed_issue = corner_dimension_candidate
                    unmatched.pop(diagnosed_index)
                    issues.append(diagnosed_issue)
                    continue

                unresolved_rows = tuple(sorted({
                    row_index
                    for result in (direct_match, rotated_match, forbidden_match)
                    if result.corner_reason == "none"
                    for row_index in result.candidate_rows
                }))
                if unresolved_rows:
                    candidate_specs = [
                        candidate["spec"]
                        for candidate in unmatched
                        if candidate["spec"].row_index in unresolved_rows
                    ]
                    piece_types = {
                        spec.piece_type for spec in candidate_specs
                    }
                    issues.append(
                        issue(
                            CORNER_EDGE_UNRESOLVED,
                            CATEGORY_TOPOLOGY,
                            target=(
                                contour_target(int(piece["id"]))
                                if str(piece.get("id") or "").isdigit()
                                else DxfIssueTarget()
                            ),
                            params={
                                "piece_type": (
                                    next(iter(piece_types))
                                    if len(piece_types) == 1
                                    else "Corner"
                                ),
                                "reason": "none",
                                "candidate_source_piece_nos": list(unresolved_rows),
                            },
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
            binding_error = _bind_corner_edge_rotation(
                piece,
                candidate,
                allow_piece_mirroring=(
                    getattr(order, "allow_piece_mirroring", None) if order is not None else None
                ),
            )
            if binding_error:
                issues.append(binding_error)
            else:
                issues.extend(
                    _piece_machining_issues(
                        piece,
                        candidate["spec"],
                        order,
                        cutter_diameter_mm=cutter_diameter_mm,
                        sheet=sheet,
                    )
                )

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
            validate_regular_machining=False,
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
        details = exc.details
        target = piece_target(
            source_piece_no=details.get("source_piece_no"),
            copy_no=details.get("copy_no"),
            label=details.get("label"),
        )
        raise DxfImportError(
            issues=[issue(
                APPLIED_TRIM_OVERFLOW,
                CATEGORY_LAYOUT,
                target=target,
                params={key: value for key, value in details.items() if key not in {"source_piece_no", "copy_no", "label"}},
            )]
        ) from exc

    exact_issues = _apply_strict_dimension_contract(
        snapshot,
        specs,
        order=order,
        cutter_diameter_mm=settings.kerf_mm,
    )
    if exact_issues:
        # Existing saw-center provenance distinguishes modern GEOMETRY from
        # legacy contour DXF without adding persisted snapshot/API fields.
        outline_layer = (
            "GEOMETRY" if snapshot.get("saw_center_status") in {"Present", "Absent"}
            else "CUT_PATH"
        )
        raise DxfImportError(issues=[
            replace(item, params={**item.params, "outline_layer": outline_layer})
            if item.code == CUT_SIZE_MISMATCH else item
            for item in exact_issues
        ])

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
