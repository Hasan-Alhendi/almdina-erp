from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any


Translate = Callable[[str], str]
Escape = Callable[[str], str]
Dumps = Callable[[Any], str]


def _value(row: Any, fieldname: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(fieldname, default)
    return getattr(row, fieldname, default)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _fmt_cm(value: Any) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return ""
    if number == int(number):
        return str(int(number))
    return f"{number:.1f}".rstrip("0").rstrip(".")


def _chip(
    label: str,
    checked: bool,
    *,
    escape: Escape,
) -> str:
    css_class = "is-checked" if checked else ""
    mark = "✓ " if checked else ""
    return (
        f'<span class="dco-check-toggle {css_class}" style="min-height:28px;border:1px solid #ccd3da;border-radius:8px;'
        f'padding:3px 6px;font-size:11px;display:inline-flex;align-items:center;justify-content:center;'
        f'background:{"#2490ef" if checked else "#fff"};color:{"#fff" if checked else "#334"};'
        f'font-weight:{"800" if checked else "400"};opacity:{"1" if checked else ".55"}">'
        f"{mark}{escape(label)}</span>"
    )


def render_pieces_html(
    order: Any,
    *,
    translate: Translate,
    escape: Escape,
) -> str:
    """Render the read-only pieces and edge-banding table."""

    rows = list(_value(order, "pieces") or [])
    if not rows:
        return ""

    default_edge = str(_value(order, "default_edge_type") or "")
    body_rows: list[str] = []
    for index, row in enumerate(rows, start=1):
        edge_type = (
            str(_value(row, "edge_type") or "").strip()
            or default_edge
            or translate("القشاط الرئيسي")
        )
        body_rows.append(
            "<tr>"
            f'<td style="text-align:center;font-weight:800">{index}</td>'
            f'<td style="text-align:center;direction:ltr">{_fmt_cm(_value(row, "width_cm"))}</td>'
            f'<td style="text-align:center;direction:ltr">{_fmt_cm(_value(row, "length_cm"))}</td>'
            f'<td style="text-align:center">{_int(_value(row, "qty"))}</td>'
            f'<td style="text-align:center">{_chip("↻", bool(_int(_value(row, "allow_rotation"))), escape=escape)}</td>'
            '<td><div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:4px">'
            f'{_chip(translate("طول يمين"), bool(_int(_value(row, "edge_long_right"))), escape=escape)}'
            f'{_chip(translate("طول يسار"), bool(_int(_value(row, "edge_long_left"))), escape=escape)}'
            f'{_chip(translate("عرض أعلى"), bool(_int(_value(row, "edge_width_top"))), escape=escape)}'
            f'{_chip(translate("عرض أسفل"), bool(_int(_value(row, "edge_width_bottom"))), escape=escape)}'
            "</div></td>"
            f'<td style="text-align:center">{escape(edge_type)}</td>'
            "</tr>"
        )

    return (
        '<div class="dco-fast-entry-shell" style="direction:rtl;border:1px solid #dfe3e8;border-radius:14px;'
        'overflow:hidden;background:#fff;margin-bottom:14px">'
        '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;'
        'padding:10px 12px;background:#f8f9fa;border-bottom:1px solid #dfe3e8;font-size:12px">'
        f"<b>{translate('قائمة القطع والقشاط')}</b>"
        f'<span style="font-weight:700;opacity:.75">{translate("الطلب للعرض فقط")}</span>'
        "</div>"
        '<div style="overflow:auto;-webkit-overflow-scrolling:touch;max-height:55vh">'
        '<table style="width:100%;min-width:640px;border-collapse:separate;border-spacing:0">'
        "<thead><tr>"
        '<th style="position:sticky;top:0;background:#fff;border-bottom:1px solid #dfe3e8;padding:8px 5px;font-size:12px;text-align:center">#</th>'
        f'<th style="position:sticky;top:0;background:#fff;border-bottom:1px solid #dfe3e8;padding:8px 5px;font-size:12px;text-align:center">{translate("العرض (سم)")}</th>'
        f'<th style="position:sticky;top:0;background:#fff;border-bottom:1px solid #dfe3e8;padding:8px 5px;font-size:12px;text-align:center">{translate("الطول (سم)")}</th>'
        f'<th style="position:sticky;top:0;background:#fff;border-bottom:1px solid #dfe3e8;padding:8px 5px;font-size:12px;text-align:center">{translate("العدد")}</th>'
        f'<th style="position:sticky;top:0;background:#fff;border-bottom:1px solid #dfe3e8;padding:8px 5px;font-size:12px;text-align:center">{translate("تدوير")}</th>'
        f'<th style="position:sticky;top:0;background:#fff;border-bottom:1px solid #dfe3e8;padding:8px 5px;font-size:12px;text-align:center">{translate("جهات القشاط")}</th>'
        f'<th style="position:sticky;top:0;background:#fff;border-bottom:1px solid #dfe3e8;padding:8px 5px;font-size:12px;text-align:center">{translate("نوع القشاط")}</th>'
        "</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table></div></div>"
    )


def _render_piece_edge_lines(piece: Mapping[str, Any]) -> str:
    rotated = bool(piece.get("rotated"))
    if not rotated:
        left = 1 if piece.get("edge_long_left") else 0
        right = 1 if piece.get("edge_long_right") else 0
        top = 1 if piece.get("edge_width_top") else 0
        bottom = 1 if piece.get("edge_width_bottom") else 0
    else:
        top = 1 if piece.get("edge_long_left") else 0
        bottom = 1 if piece.get("edge_long_right") else 0
        right = 1 if piece.get("edge_width_top") else 0
        left = 1 if piece.get("edge_width_bottom") else 0

    color = "#d00000"
    thickness = "3px"
    inset = "3px"
    edge_line_percent = 66.666
    edge_line_start = (100 - edge_line_percent) / 2
    parts: list[str] = []
    common = 'class="dco-edge-line" style="position:absolute;z-index:3;'
    if left:
        parts.append(
            f'<span {common}left:{inset};top:{edge_line_start}%;height:{edge_line_percent}%;'
            f'border-left:{thickness} solid {color};"></span>'
        )
    if right:
        parts.append(
            f'<span {common}right:{inset};top:{edge_line_start}%;height:{edge_line_percent}%;'
            f'border-right:{thickness} solid {color};"></span>'
        )
    if top:
        parts.append(
            f'<span {common}top:{inset};left:{edge_line_start}%;width:{edge_line_percent}%;'
            f'border-top:{thickness} solid {color};"></span>'
        )
    if bottom:
        parts.append(
            f'<span {common}bottom:{inset};left:{edge_line_start}%;width:{edge_line_percent}%;'
            f'border-bottom:{thickness} solid {color};"></span>'
        )
    return "".join(parts)


def render_plan_html(
    *,
    order_name: str,
    customer: str | None,
    snapshot: Mapping[str, Any],
    translate: Translate,
    escape: Escape,
) -> str:
    """Render simplified cutting-plan drawings for shop-floor operators."""

    sheets = snapshot.get("sheets") or []
    if not sheets:
        return ""

    def number(value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    board_width = (
        number(snapshot.get("usable_board_width_cm"))
        or number(snapshot.get("full_board_width_cm"))
        or 1
    )
    board_height = (
        number(snapshot.get("usable_board_length_cm"))
        or number(snapshot.get("full_board_length_cm"))
        or 1
    )
    board_width_px = 560
    board_height_px = max(
        260,
        int(round(board_width_px * (board_height / board_width))),
    )

    parts = [
        '<div class="dco-cutting-plan" style="font-family:Arial,Tahoma,sans-serif;direction:rtl;color:#111;background:#fff;">',
        f'<h2 style="margin:0 0 10px 0;font-size:18px;">{translate("خطة القص")}</h2>',
        (
            '<div style="line-height:1.7;margin-bottom:12px;font-size:13px;">'
            f"<b>{translate('الطلب')}:</b> {escape(order_name or '')} &nbsp; | &nbsp; "
            f"<b>{translate('الزبون')}:</b> {escape(customer or '')}"
            "</div>"
        ),
    ]

    for sheet in sheets:
        pieces = sheet.get("pieces") or []
        sheet_number = sheet.get("sheet_no") or ""
        parts.append(
            '<div class="dco-sheet-card" style="border:1px solid #bbb;border-radius:10px;padding:10px;margin:14px 0;background:#fff;">'
            f'<div style="margin-bottom:8px;font-size:13px;font-weight:bold;">{translate("اللوح")} {escape(str(sheet_number))}'
            f' &nbsp; | &nbsp; {translate("عدد القطع")}: {len(pieces)}</div>'
            f'<div style="position:relative;direction:ltr;width:{board_width_px}px;height:{board_height_px}px;max-width:100%;'
            'border:2px solid #111;background:linear-gradient(90deg,rgba(0,0,0,0.05) 1px,transparent 1px),'
            'linear-gradient(rgba(0,0,0,0.05) 1px,transparent 1px),#fff;background-size:32px 32px;overflow:hidden;margin:0 auto;">'
        )
        for piece in pieces:
            left = (number(piece.get("x")) / board_width) * 100
            top = (number(piece.get("y")) / board_height) * 100
            width = (number(piece.get("w")) / board_width) * 100
            height = (number(piece.get("h")) / board_height) * 100
            label = piece.get("label") or piece.get("piece_label") or ""
            original_width = number(piece.get("original_w")) or number(piece.get("w"))
            original_height = number(piece.get("original_h")) or number(piece.get("h"))
            edge_html = _render_piece_edge_lines(piece)
            parts.append(
                f'<div class="dco-piece" style="position:absolute;left:{left}%;top:{top}%;width:{width}%;height:{height}%;'
                "border:1px solid #111;background:#e4f5ff;color:#111;overflow:hidden;padding:2px;font-size:10px;"
                'line-height:1.2;text-align:center;box-sizing:border-box;display:flex;align-items:center;justify-content:center;">'
                f"{edge_html}"
                '<div class="dco-piece-label" style="position:relative;z-index:4;direction:ltr;text-align:center;">'
                f"<b>{escape(str(label))}</b><br>"
                f"<span>{round(original_width, 1)}*{round(original_height, 1)} سم</span></div>"
                "</div>"
            )
        parts.append("</div></div>")

    parts.append("</div>")
    return "".join(parts)


def present_order_detail(
    query_result: Mapping[str, Any],
    *,
    translate: Translate,
    escape: Escape,
    dumps: Dumps,
) -> dict[str, Any]:
    order = query_result["order"]
    stage_snapshot = query_result["stage_snapshot"]
    system_snapshot = query_result["system_snapshot"]
    custom_snapshot = query_result["custom_snapshot"]
    approved_snapshot = query_result.get("approved_snapshot") or {}
    active_snapshot = query_result["active_snapshot"]

    system_html = render_plan_html(
        order_name=str(_value(order, "name") or ""),
        customer=_value(order, "customer"),
        snapshot=system_snapshot,
        translate=translate,
        escape=escape,
    )
    custom_html = (
        render_plan_html(
            order_name=str(_value(order, "name") or ""),
            customer=_value(order, "customer"),
            snapshot=custom_snapshot,
            translate=translate,
            escape=escape,
        )
        if custom_snapshot.get("sheets")
        else ""
    )
    approved_html = (
        render_plan_html(
            order_name=str(_value(order, "name") or ""),
            customer=_value(order, "customer"),
            snapshot=approved_snapshot,
            translate=translate,
            escape=escape,
        )
        if approved_snapshot.get("sheets")
        else ""
    )
    active_html = render_plan_html(
        order_name=str(_value(order, "name") or ""),
        customer=_value(order, "customer"),
        snapshot=active_snapshot,
        translate=translate,
        escape=escape,
    )

    return {
        "name": _value(order, "name"),
        "customer": _value(order, "customer"),
        "status": _value(order, "status"),
        "production_path": _value(order, "production_path"),
        "current_department": _value(order, "current_department"),
        "current_assignee": _value(order, "current_assignee"),
        "department_status": _value(order, "department_status"),
        "current_production_stage": _value(order, "current_production_stage"),
        "active_stage_name": stage_snapshot.get("active_stage_name"),
        "active_stage_status": stage_snapshot.get("active_stage_status"),
        "can_start_stage": stage_snapshot.get("can_start_stage"),
        "can_handoff_stage": stage_snapshot.get("can_handoff_stage"),
        "can_handoff_to": stage_snapshot.get("can_handoff_to"),
        "approved_plan": _value(order, "approved_plan"),
        "pieces_html": render_pieces_html(
            order,
            translate=translate,
            escape=escape,
        ),
        "cutting_plan_html": active_html,
        "system_plan_html": system_html,
        "custom_plan_html": custom_html,
        "approved_plan_html": approved_html,
        "system_plan_json": dumps(system_snapshot) if system_snapshot else "",
        "custom_plan_json": (
            dumps(custom_snapshot) if custom_snapshot.get("sheets") else ""
        ),
        "approved_plan_source": query_result["approved_plan_source"],
        "active_plan_source": query_result["active_plan_source"],
        "visible_plan_tabs": list(query_result.get("visible_plan_tabs") or []),
        "show_dual_tabs": query_result["show_dual_tabs"],
        "packing_mode": _value(order, "packing_mode"),
        "kerf_mm": _value(order, "kerf_mm"),
        "trim_margin_mm": _value(order, "trim_margin_mm"),
        "cutting_machine_type": _value(order, "cutting_machine_type"),
        "current_stage_type": stage_snapshot.get("active_stage_type"),
        "can_recalculate_drawing_plan": query_result[
            "can_recalculate_drawing_plan"
        ],
        "production_dxf": _value(order, "production_dxf"),
        "drawing_dxf_status": _value(order, "drawing_dxf_status"),
        "stages": query_result["stages"],
    }
