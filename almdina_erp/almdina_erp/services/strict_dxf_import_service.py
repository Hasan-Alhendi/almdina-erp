from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from almdina_erp.almdina_erp.domain.cutting.piece_cut_dimensions import (
    CutDimensionError,
    dimensions_match_exact,
    normalize_cut_cm,
)
from almdina_erp.almdina_erp.services.dxf_import_service import (
    DxfImportError,
    parse_production_dxf as _legacy_parse_production_dxf,
)
from almdina_erp.almdina_erp.services.piece_cut_dimension_service import (
    OrderPieceCutSpec,
    build_order_piece_cut_specs,
)


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


def _proxy_order(order: Any, specs: list[OrderPieceCutSpec]) -> Any:
    pieces = [
        SimpleNamespace(
            qty=spec.qty,
            width_cm=float(spec.cut_width_cm),
            length_cm=float(spec.cut_length_cm),
            allow_rotation=spec.allow_rotation,
            piece_type=spec.piece_type,
        )
        for spec in specs
    ]
    return SimpleNamespace(
        pieces=pieces,
        trim_margin_mm=getattr(order, "trim_margin_mm", 0),
        board_width_cm=getattr(order, "board_width_cm", 0),
        board_length_cm=getattr(order, "board_length_cm", 0),
        full_board_width_mm=getattr(order, "full_board_width_mm", 0),
        full_board_length_mm=getattr(order, "full_board_length_mm", 0),
        kerf_mm=getattr(order, "kerf_mm", 0),
    )


def _expanded_expected(specs: list[OrderPieceCutSpec]) -> list[dict[str, Any]]:
    return [
        {
            "spec": spec,
            "copy_no": copy_no,
            "label": f"{spec.row_index}.{copy_no}",
        }
        for spec in specs
        for copy_no in range(1, spec.qty + 1)
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


def _apply_strict_dimension_contract(
    snapshot: dict[str, Any],
    specs: list[OrderPieceCutSpec],
) -> list[str]:
    """Relabel and accept pieces only by exact edge-adjusted raw-cut dimensions."""
    errors: list[str] = []
    unmatched = _expanded_expected(specs)

    for sheet in snapshot.get("sheets") or []:
        for piece in sheet.get("pieces") or []:
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
                    row_hint = next((spec for spec in specs if spec.row_index == row_no), None)
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
            spec: OrderPieceCutSpec = candidate["spec"]
            piece["label"] = candidate["label"]
            piece["source_piece_no"] = spec.row_index
            piece["copy_no"] = candidate["copy_no"]
            piece["rotated"] = rotated
            piece["piece_type"] = spec.piece_type
            piece["original_w"] = float(spec.cut_width_cm)
            piece["original_h"] = float(spec.cut_length_cm)
            piece["finished_w"] = float(spec.finished_width_cm)
            piece["finished_h"] = float(spec.finished_length_cm)
            piece["cut_width_cm"] = float(spec.cut_width_cm)
            piece["cut_length_cm"] = float(spec.cut_length_cm)
            piece["edge_width_deduction_mm"] = float(spec.width_deduction_mm)
            piece["edge_length_deduction_mm"] = float(spec.length_deduction_mm)

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


def parse_production_dxf(file_url: str, order: Any) -> dict[str, Any]:
    """Validate DXF against exact raw-cut sizes derived from finished size + edge banding.

    The legacy geometry importer is reused for DXF topology, layers, board bounds,
    kerf and contour checks. Its historical piece association tolerance is only
    used to identify a candidate; acceptance is then exact at 0.001 cm.
    """
    try:
        specs = build_order_piece_cut_specs(order)
    except CutDimensionError as exc:
        raise DxfImportError(exc.errors) from exc

    try:
        snapshot = _legacy_parse_production_dxf(file_url, _proxy_order(order, specs))
    except DxfImportError as exc:
        text = str(exc)
        if "سماحية" in text or "لا تطابق أي قطعة" in text or "بعد تدويرها" in text:
            expected = "؛ ".join(
                f"الدرفة {spec.row_index}: {_format_spec(spec)}" for spec in specs[:8]
            )
            suffix = " ..." if len(specs) > 8 else ""
            raise DxfImportError(
                "مقاسات القطع في DXF لا تطابق مقاسات القص الدقيقة المحسوبة من الطلب والقشاط. "
                f"{expected}{suffix}. لا توجد سماحية لتغيير مقاس الدرفة."
            ) from exc
        raise

    exact_errors = _apply_strict_dimension_contract(snapshot, specs)
    if exact_errors:
        raise DxfImportError(exact_errors)

    snapshot["dimension_contract"] = {
        "mode": "exact-edge-adjusted",
        "precision_cm": "0.001",
        "finished_dimensions_immutable": True,
    }
    return snapshot


__all__ = ["parse_production_dxf"]
