from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any


def _value(source: Mapping[str, Any], key: str, default: Any = None) -> Any:
    return source.get(key, default)


def _number(value: Any) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _quantity(value: Any) -> int:
    return max(1, int(_number(value) or 1))


def _text(value: Any, fallback: str = "") -> str:
    result = str(value or "").strip()
    return result or fallback


def _money(value: Any) -> float:
    return round(_number(value), 2)


def _metric(value: Any, digits: int = 3) -> float:
    return round(_number(value), digits)


def _piece_type_label(value: Any) -> str:
    return {
        "Special": "خاصة",
        "Clipped Corner": "زاوية مقصوصة",
        "Extra": "إضافية",
        "Regular": "عادية",
    }.get(_text(value, "Regular"), "عادية")


def _extra_addon_labels(piece: Mapping[str, Any]) -> list[str]:
    return [
        label
        for fieldname, label in (
            ("extra_double", "Double"),
            ("extra_liner", "Liner"),
            ("extra_recessed_handle_cutout", "تفريغ مسكة مخفية"),
        )
        if _number(_value(piece, fieldname))
    ]


def _price_status_label(value: Any) -> str:
    return {
        "Approved": "معتمد",
        "Estimated": "تقديري",
        "Not Applicable": "غير مطبق",
    }.get(_text(value), _text(value, "غير محدد"))


def _quote_status_label(value: Any) -> str:
    return {
        "Automatic": "تلقائي",
        "Estimated": "تقديري",
        "Partially Approved": "معتمد جزئيًا",
        "Approved": "معتمد",
    }.get(_text(value), _text(value, "تلقائي"))


def _measurement_rows(pieces: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, piece in enumerate(pieces, start=1):
        notes = _text(_value(piece, "notes"), "")
        extra_labels = _extra_addon_labels(piece)
        if extra_labels:
            extra_summary = f"إضافات: {'، '.join(extra_labels)}"
            notes = f"{extra_summary} — {notes}" if notes else extra_summary
        rows.append(
            {
                "piece_name": _text(_value(piece, "name")),
                "index": index,
                "piece_no": int(_number(_value(piece, "piece_no")) or index),
                "piece_type": _piece_type_label(_value(piece, "piece_type")),
                "width_cm": _metric(_value(piece, "width_cm")),
                "length_cm": _metric(_value(piece, "length_cm")),
                "quantity": _quantity(_value(piece, "qty")),
                "edge_type": _text(_value(piece, "edge_type"), "—"),
                "notes": notes or "—",
                "special_shape_drawing_json": _text(
                    _value(piece, "special_shape_drawing_json")
                ),
            }
        )
    return rows


def _customer_invoice_lines(
    order: Mapping[str, Any],
    pieces: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    board_count = max(0, int(_number(_value(order, "required_boards"))))
    board_rate = _number(_value(order, "board_rate_usd"))
    cutting_rate = _number(_value(order, "cutting_cost_per_board_usd"))
    material_amount = (
        board_count * board_rate
        if board_count
        else _number(_value(order, "mdf_cost_usd"))
    )
    cutting_amount = (
        board_count * cutting_rate
        if board_count
        else _number(_value(order, "cutting_cost_usd"))
    )
    board_description = _text(_value(order, "board_description"))
    lines: list[dict[str, Any]] = []

    if board_count or material_amount:
        lines.append(
            {
                "type": "material",
                "description": (
                    f"ألواح MDF — {board_description}"
                    if board_description
                    else "ألواح MDF"
                ),
                "quantity": board_count or (
                    material_amount / board_rate if board_rate else 0
                ),
                "unit": "لوح",
                "rate_usd": _money(board_rate),
                "amount_usd": _money(material_amount),
                "note": "",
            }
        )

    if board_count or cutting_amount:
        lines.append(
            {
                "type": "cutting",
                "description": "أجور قص وتجهيز الألواح",
                "quantity": board_count or (
                    cutting_amount / cutting_rate if cutting_rate else 0
                ),
                "unit": "لوح",
                "rate_usd": _money(cutting_rate),
                "amount_usd": _money(cutting_amount),
                "note": "",
            }
        )

    special_pieces = [
        piece
        for piece in pieces
        if _text(_value(piece, "piece_type")) in {"Special", "Clipped Corner"}
    ]
    edge_source = (
        [piece for piece in pieces if piece not in special_pieces]
        if special_pieces
        else list(pieces)
    )
    edge_groups: dict[tuple[str, float], dict[str, Any]] = defaultdict(
        lambda: {"meters": 0.0, "amount": 0.0}
    )
    for piece in edge_source:
        meters = _number(_value(piece, "edge_meters"))
        if meters <= 0:
            continue
        edge_type = _text(_value(piece, "edge_type"), "قشاط")
        rate = _number(_value(piece, "edge_rate_usd"))
        group = edge_groups[(edge_type, rate)]
        group["meters"] += meters
        group["amount"] += _number(_value(piece, "edge_cost_usd")) or meters * rate

    for (edge_type, rate), group in sorted(edge_groups.items()):
        lines.append(
            {
                "type": "edge",
                "description": f"قشاط — {edge_type}",
                "quantity": _metric(group["meters"]),
                "unit": "متر",
                "rate_usd": _money(rate),
                "amount_usd": _money(group["amount"]),
                "note": "",
            }
        )

    if not special_pieces and not edge_groups:
        edge_amount = _number(_value(order, "edge_cost_usd"))
        if edge_amount:
            lines.append(
                {
                    "type": "edge",
                    "description": "تكلفة القشاط",
                    "quantity": _metric(_value(order, "total_edge_meters")),
                    "unit": "متر",
                    "rate_usd": 0.0,
                    "amount_usd": _money(edge_amount),
                    "note": "",
                }
            )

    for index, piece in enumerate(pieces, start=1):
        piece_type = _text(_value(piece, "piece_type"), "Regular")
        quantity = _quantity(_value(piece, "qty"))
        if piece_type == "Special":
            final_rate = _number(_value(piece, "special_shape_final_unit_price_usd"))
            lines.append(
                {
                    "type": "special",
                    "description": f"درفة خاصة رقم {index}",
                    "quantity": quantity,
                    "unit": "درفة",
                    "rate_usd": _money(final_rate),
                    "amount_usd": _money(final_rate * quantity),
                    "note": _text(_value(piece, "special_shape_price_note")),
                }
            )
        elif piece_type == "Clipped Corner":
            edge_rate = _number(_value(piece, "clipped_corner_edge_price_usd"))
            lines.append(
                {
                    "type": "cut_corner",
                    "description": f"درفة زاوية مقصوصة {index}",
                    "quantity": quantity,
                    "unit": "درفة",
                    "rate_usd": _money(edge_rate),
                    "amount_usd": _money(edge_rate * quantity),
                    "note": _text(_value(piece, "clipped_corner_edge_price_note")),
                }
            )
        elif piece_type == "Extra":
            specs = (
                (
                    "extra_double",
                    "extra_double_unit_price_usd",
                    "extra_double_total_usd",
                    "Double",
                ),
                (
                    "extra_liner",
                    "extra_liner_unit_price_usd",
                    "extra_liner_total_usd",
                    "Liner",
                ),
                (
                    "extra_recessed_handle_cutout",
                    "extra_recessed_handle_cutout_unit_price_usd",
                    "extra_recessed_handle_cutout_total_usd",
                    "تفريغ مسكة مخفية",
                ),
            )
            for flag_field, rate_field, amount_field, label in specs:
                amount = _number(_value(piece, amount_field))
                if not _number(_value(piece, flag_field)) and amount <= 0:
                    continue
                rate = _number(_value(piece, rate_field))
                lines.append(
                    {
                        "type": "extra_addon",
                        "description": f"إضافة {label} — درفة رقم {index}",
                        "quantity": quantity,
                        "unit": "درفة",
                        "rate_usd": _money(rate),
                        "amount_usd": _money(amount or (rate * quantity)),
                        "note": _text(_value(piece, "notes")),
                    }
                )

    return lines


def _base_meta(order: Mapping[str, Any]) -> list[dict[str, str]]:
    return [
        {"label": "رقم الطلب", "value": _text(_value(order, "name"), "—")},
        {"label": "الزبون", "value": _text(_value(order, "customer"), "—")},
        {"label": "تاريخ الطلب", "value": _text(_value(order, "order_date"), "—")},
        {"label": "اللوح", "value": _text(_value(order, "board_description"), "—")},
        {"label": "لون القشاط", "value": _text(_value(order, "edge_color"), "—")},
        {"label": "المراجعة", "value": _text(_value(order, "revision"), "1")},
    ]


def build_customer_invoice_document(
    order: Mapping[str, Any],
    pieces: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a customer-facing document without internal cost or margin fields."""

    invoice_lines = _customer_invoice_lines(order, pieces)
    total = _money(sum(_number(line["amount_usd"]) for line in invoice_lines))
    if not invoice_lines:
        total = _money(
            _value(order, "customer_quote_total_usd")
            or _value(order, "total_cost_usd")
        )
    door_count = sum(_quantity(_value(piece, "qty")) for piece in pieces)

    return {
        "kind": "customer_invoice",
        "title": "عرض سعر الطلب",
        "subtitle": "تفاصيل القياسات والخدمات والأسعار المعتمدة للزبون",
        "meta": _base_meta(order),
        "summary": [
            {
                "label": "حالة عرض السعر",
                "value": _quote_status_label(_value(order, "customer_quote_status")),
            },
            {"label": "عدد الدرف", "value": door_count},
            {"label": "إجمالي العرض ($)", "value": total, "format": "money"},
        ],
        "measurements": _measurement_rows(pieces),
        "lines": invoice_lines,
        "totals": [
            {"label": "الإجمالي النهائي", "value_usd": total},
        ],
        "notes": _text(_value(order, "order_notes")),
    }


def build_internal_cost_report_document(
    order: Mapping[str, Any],
    pieces: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a management-only operational cost and margin report."""

    mdf_cost = _number(_value(order, "mdf_cost_usd"))
    cutting_cost = _number(_value(order, "cutting_cost_usd"))
    edge_cost = _number(_value(order, "edge_cost_usd"))
    planned_total = _number(_value(order, "total_cost_usd")) or (
        mdf_cost + cutting_cost + edge_cost
    )
    material_variance = _number(_value(order, "material_variance_cost_usd"))
    internal_loss = _number(_value(order, "internal_loss_cost_usd"))
    stored_actual = _number(_value(order, "actual_cost_usd"))
    effective_actual = stored_actual or planned_total + material_variance + internal_loss
    quote_total = _number(_value(order, "customer_quote_total_usd"))
    if not quote_total:
        quote_total = sum(
            _number(line["amount_usd"])
            for line in _customer_invoice_lines(order, pieces)
        )
    gross_margin = quote_total - effective_actual
    margin_percent = gross_margin / quote_total * 100 if quote_total else 0.0

    special_rows: list[dict[str, Any]] = []
    for index, piece in enumerate(pieces, start=1):
        if _text(_value(piece, "piece_type")) != "Special":
            continue
        quantity = _quantity(_value(piece, "qty"))
        estimated = _number(_value(piece, "special_shape_estimated_unit_price_usd"))
        approved = _number(_value(piece, "special_shape_custom_unit_price_usd"))
        final = _number(_value(piece, "special_shape_final_unit_price_usd"))
        special_rows.append(
            {
                "piece_no": int(_number(_value(piece, "piece_no")) or index),
                "quantity": quantity,
                "estimated_unit_usd": _money(estimated),
                "approved_unit_usd": _money(approved),
                "final_unit_usd": _money(final),
                "variance_total_usd": _money((final - estimated) * quantity),
                "status": _price_status_label(
                    _value(piece, "special_shape_price_status")
                ),
                "approved_by": _text(
                    _value(piece, "special_shape_price_approved_by"), "—"
                ),
                "approved_on": _text(
                    _value(piece, "special_shape_price_approved_on"), "—"
                ),
                "note": _text(_value(piece, "special_shape_price_note"), "—"),
            }
        )

    return {
        "kind": "internal_cost_report",
        "title": "تقرير التكلفة الداخلي",
        "subtitle": "تقرير إداري سري للتكلفة التشغيلية والربحية المتوقعة",
        "classification": "داخلي — لا يسلّم للزبون",
        "meta": _base_meta(order),
        "summary": [
            {"label": "التكلفة المخططة ($)", "value": _money(planned_total), "format": "money"},
            {"label": "التكلفة الفعلية/المتوقعة ($)", "value": _money(effective_actual), "format": "money"},
            {"label": "عرض الزبون ($)", "value": _money(quote_total), "format": "money"},
            {"label": "هامش الربح ($)", "value": _money(gross_margin), "format": "money"},
            {"label": "هامش الربح (%)", "value": round(margin_percent, 2), "format": "percent"},
        ],
        "cost_breakdown": [
            {"label": "تكلفة ألواح MDF", "amount_usd": _money(mdf_cost)},
            {"label": "أجور القص", "amount_usd": _money(cutting_cost)},
            {"label": "تكلفة القشاط", "amount_usd": _money(edge_cost)},
            {"label": "فروقات المواد", "amount_usd": _money(material_variance)},
            {"label": "الخسائر الداخلية", "amount_usd": _money(internal_loss)},
        ],
        "operations": [
            {"label": "عدد الألواح", "value": max(0, int(_number(_value(order, "required_boards"))))},
            {"label": "المساحة الإجمالية (م²)", "value": _metric(_value(order, "total_area_m2"))},
            {"label": "إجمالي القشاط (م)", "value": _metric(_value(order, "total_edge_meters"))},
            {"label": "مساحة الهدر (م²)", "value": _metric(_value(order, "waste_area_m2"))},
            {"label": "نسبة الهدر (%)", "value": round(_number(_value(order, "waste_percent")), 2)},
            {"label": "طريقة الترتيب", "value": _text(_value(order, "packing_method"), "—")},
        ],
        "special_prices": special_rows,
        "totals": [
            {"label": "التكلفة المخططة", "value_usd": _money(planned_total)},
            {"label": "التكلفة الفعلية/المتوقعة", "value_usd": _money(effective_actual)},
            {"label": "عرض الزبون", "value_usd": _money(quote_total)},
            {"label": "هامش الربح", "value_usd": _money(gross_margin)},
        ],
        "notes": _text(_value(order, "order_notes")),
    }


__all__ = [
    "build_customer_invoice_document",
    "build_internal_cost_report_document",
]
