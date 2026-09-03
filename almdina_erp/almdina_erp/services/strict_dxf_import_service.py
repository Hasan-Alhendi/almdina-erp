from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from almdina_erp.almdina_erp.application.cutting.plan_revisions import PlanSettings
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
    dimensions_match_exact,
    normalize_cut_cm,
)
from almdina_erp.almdina_erp.domain.orders.extra_addons import physical_cut_quantity
from almdina_erp.almdina_erp.services.dxf_import_service import (
    DxfImportError,
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
            "تعذر ربط مقاسات القص التصنيعية المحفوظة بقطع الطلب بشكل موثوق. "
            "احفظ الطلب ثم أعد رفع DXF."
        )

    persisted_specs: list[OrderPieceCutSpec] = []
    for row_index, (row, spec) in enumerate(zip(rows, specs), start=1):
        if spec.row_index != row_index:
            raise DxfImportError(
                "تعذر ربط مقاسات القص التصنيعية المحفوظة بقطع الطلب بشكل موثوق. "
                "احفظ الطلب ثم أعد رفع DXF."
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
                f"مقاسات القص التصنيعية للقطعة رقم {row_index} غير محفوظة أو غير صالحة. "
                "احفظ الطلب لإعادة تثبيت مقاسات القص ثم أعد رفع DXF."
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
        pieces.append(
            SimpleNamespace(
                qty=spec.qty,
                extra_full_door_double=getattr(row, "extra_full_door_double", 0) if row else 0,
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
    return [
        {
            "spec": spec,
            "copy_no": copy_no,
            "label": f"{spec.row_index}.{copy_no}",
        }
        for spec in specs
        for copy_no in range(1, _physical_spec_qty(order, spec) + 1)
    ]


def _actual_dimensions(piece: dict[str, Any]) -> tuple[Decimal, Decimal]:
    return normalize_cut_cm(piece.get("w")), normalize_cut_cm(piece.get("h"))


def _find_exact_candidate(
    unmatched: list[dict[str, Any]],
    actual_w: Decimal,
    actual_h: Decimal,
    *,
    rotated: bool,
    require_rotation_allowed: bool = True,
) -> int | None:
    for index, candidate in enumerate(unmatched):
        spec: OrderPieceCutSpec = candidate["spec"]
        if rotated:
            if require_rotation_allowed and not spec.allow_rotation:
                continue
            expected_w, expected_h = spec.cut_length_cm, spec.cut_width_cm
        else:
            expected_w, expected_h = spec.cut_width_cm, spec.cut_length_cm
        if dimensions_match_exact(actual_w, actual_h, expected_w, expected_h):
            return index
    return None


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


def _validate_topology_candidate_dimensions(
    piece: dict[str, Any],
    candidate: dict[str, Any],
) -> tuple[bool | None, str | None]:
    """Validate a topology-owned Special against its persisted cut envelope."""
    actual_w, actual_h = _actual_dimensions(piece)
    spec: OrderPieceCutSpec = candidate["spec"]

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
        return None, (
            f"القطعة {candidate['label']}: {_format_spec(spec)}. "
            f"DXF يحتوي {_format_decimal(actual_w)} × {_format_decimal(actual_h)} سم، "
            "وهو نفس مقاس القص بعد التدوير، لكن التدوير غير مسموح لهذه الدرفة."
        )

    return None, (
        f"القطعة {candidate['label']}: {_format_spec(spec)}. "
        f"DXF يحتوي {_format_decimal(actual_w)} × {_format_decimal(actual_h)} سم. "
        "شكل الدرفة الخاصة حر، لكن الإطار الخارجي للتصنيع يجب أن يطابق مقاس القص المحفوظ تمامًا."
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
    return flags


def _apply_piece_contract_metadata(
    piece: dict[str, Any],
    candidate: dict[str, Any],
    *,
    rotated: bool,
) -> None:
    spec: OrderPieceCutSpec = candidate["spec"]
    piece["label"] = candidate["label"]
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
    piece.update(_edge_print_contract(spec))


def _apply_strict_dimension_contract(
    snapshot: dict[str, Any],
    specs: list[OrderPieceCutSpec],
    *,
    order: Any | None = None,
) -> list[str]:
    """Relabel pieces and enrich them with exact order + edge-print metadata."""
    errors: list[str] = []
    unmatched = _expanded_expected(specs, order)

    for sheet in snapshot.get("sheets") or []:
        for piece in sheet.get("pieces") or []:
            topology_special_index = _topology_special_candidate(unmatched, piece)
            if topology_special_index is not None:
                candidate = unmatched[topology_special_index]
                rotated, error = _validate_topology_candidate_dimensions(
                    piece,
                    candidate,
                )
                if error:
                    errors.append(error)
                    continue
                unmatched.pop(topology_special_index)
                _apply_piece_contract_metadata(
                    piece,
                    candidate,
                    rotated=bool(rotated),
                )
                continue
            if str(piece.get("piece_type") or "") == "Special":
                errors.append(
                    f"تعذر ربط الدرفة الخاصة {piece.get('label') or '؟'} "
                    "بهوية قطعة خاصة واحدة مثبتة في الطلب. أعد تصدير DXF من الخطة الحالية ثم أعد الرفع."
                )
                continue

            actual_w, actual_h = _actual_dimensions(piece)
            direct_index = _find_exact_candidate(
                unmatched,
                actual_w,
                actual_h,
                rotated=False,
            )
            rotated_index = _find_exact_candidate(
                unmatched,
                actual_w,
                actual_h,
                rotated=True,
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
                )
                if forbidden_index is not None:
                    candidate = unmatched[forbidden_index]
                    spec = candidate["spec"]
                    errors.append(
                        f"القطعة {candidate['label']}: {_format_spec(spec)}. "
                        f"DXF يحتوي {_format_decimal(actual_w)} × {_format_decimal(actual_h)} سم، "
                        "وهو نفس مقاس القص بعد التدوير، لكن التدوير غير مسموح لهذه الدرفة."
                    )
                    continue

                legacy_label = str(piece.get("label") or "")
                row_hint = None
                try:
                    row_no = int(legacy_label.split(".", 1)[0])
                    row_hint = next(
                        (spec for spec in specs if spec.row_index == row_no),
                        None,
                    )
                except (TypeError, ValueError):
                    row_hint = None
                if row_hint:
                    errors.append(
                        f"القطعة {legacy_label or '؟'}: {_format_spec(row_hint)}. "
                        f"DXF يحتوي {_format_decimal(actual_w)} × {_format_decimal(actual_h)} سم. "
                        "يجب أن يطابق DXF مقاس القص المحسوب تمامًا؛ لا توجد سماحية لتغيير مقاس الدرفة."
                    )
                else:
                    errors.append(
                        f"وجد النظام في DXF قطعة بمقاس {_format_decimal(actual_w)} × "
                        f"{_format_decimal(actual_h)} سم لا تطابق أي مقاس قص مطلوب في الطلب تمامًا. "
                        "لا توجد سماحية لتغيير مقاس الدرفة."
                    )
                continue

            candidate = unmatched.pop(match_index)
            _apply_piece_contract_metadata(piece, candidate, rotated=rotated)

    if unmatched:
        preview = "، ".join(
            f"{candidate['label']} ({_format_decimal(candidate['spec'].cut_width_cm)} × "
            f"{_format_decimal(candidate['spec'].cut_length_cm)} سم)"
            for candidate in unmatched[:8]
        )
        suffix = " ..." if len(unmatched) > 8 else ""
        errors.append(
            f"ملف DXF لا يحتوي على جميع مقاسات القص المطلوبة تمامًا. المتبقي: {preview}{suffix}."
        )
    return errors


def _with_persisted_cut_context(
    error: DxfImportError,
    specs: list[OrderPieceCutSpec],
) -> DxfImportError:
    """Keep the original geometry diagnosis and append persisted cut specs."""
    text = str(error)
    if "لا يمكن مطابقة محيطات CUT_PATH" in text:
        return error
    if (
        "سماحية" not in text
        and "لا تطابق أي قطعة" not in text
        and "بعد تدويرها" not in text
    ):
        return error
    expected = "؛ ".join(
        f"الدرفة {spec.row_index}: {_format_spec(spec)}" for spec in specs[:8]
    )
    suffix = " ..." if len(specs) > 8 else ""
    return DxfImportError(
        list(error.errors)
        + [
            "مقاسات القص التصنيعية المحفوظة في الطلب: "
            f"{expected}{suffix}. يجب مطابقة مقاس القص وليس المقاس النهائي، ولا توجد سماحية لتغيير مقاس الدرفة."
        ]
    )


def parse_production_dxf(
    file_url: str,
    order: Any,
    *,
    settings: PlanSettings,
) -> dict[str, Any]:
    """Validate DXF against order pieces and canonical Cutting Plan settings.

    Topology/layers/physical board bounds/kerf remain owned by the geometry
    importer. Applied Trim is resolved over that fixed physical layout through
    ALMADINA-138. Manufacturing identity remains exact at 0.001 cm for every
    piece. Special outlines stay topology-owned and shape-free inside that fixed
    persisted cut envelope.
    """
    try:
        specs = build_order_piece_cut_specs(order)
    except CutDimensionError as exc:
        raise DxfImportError(exc.errors) from exc
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
            "هندسة DXF تتجاوز حدود اللوح الفيزيائية ولا يمكن جعلها صالحة حتى بعد تطبيق سياسة التشذيب التكيفية."
        ) from exc

    exact_errors = _apply_strict_dimension_contract(snapshot, specs, order=order)
    if exact_errors:
        raise DxfImportError(exact_errors)

    snapshot["dimension_contract"] = {
        "mode": "exact-persisted-cut",
        "precision_cm": "0.001",
        "finished_dimensions_immutable": True,
        "special_outline_identity": "topology-owned",
        "special_bbox_match_required": True,
    }
    snapshot["print_contract"] = {
        "renderer": "canonical-cutting-plan",
        "edge_markers_from_order": True,
        "rotation_owned_by_renderer": True,
    }
    return snapshot


__all__ = ["parse_production_dxf"]