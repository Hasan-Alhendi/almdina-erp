from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape
import json
from typing import Any


DOCUMENTATION_SCHEMA = "almdina.special-shape-documentation"
DRAWING_VERSION = 1
# Same base languages as frappe.utils.jinja_globals.is_rtl. Kept local so this
# builder can be tested without importing Frappe.
RTL_DOCUMENT_LANGUAGES = frozenset({"ar", "he", "fa", "ps"})
PIECE_TYPE_LABELS = {
    "Special": "Special door",
    "Clipped Corner": "Clipped corner",
    "L-Shaped Corner": "L-shaped corner",
    "Glass": "Glass door",
}
EXTRA_ADDONS = (
    ("extra_double", "Double edge banding"),
    ("extra_full_door_double", "Full door double"),
    ("extra_liner", "Liner"),
    ("extra_back_groove", "Back groove"),
    ("extra_recessed_handle_cutout", "Recessed handle cutout"),
)
EDGE_SIDES = (
    ("edge_width_top", "edge_width_top_type_override", "Top width edge"),
    ("edge_width_bottom", "edge_width_bottom_type_override", "Bottom width edge"),
    ("edge_long_right", "edge_long_right_type_override", "Right length edge"),
    ("edge_long_left", "edge_long_left_type_override", "Left length edge"),
)
PRINT_IDENTITY_DEFAULTS = {
    "print_factory_name": "مجمع المدينة المنورة التجاري",
    "print_factory_description": "الواح هايغلوس - فورميكا - cnc - ليزر - قشر",
    "print_factory_address": "دمشق - ببيلا - طريق السيدة زينب",
    "print_factory_contacts": "",
}

MEASUREMENTS_PRINT_CSS = """
@page{size:A4 portrait;margin:6mm}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:#fff;color:#172033;direction:rtl;font-family:Tahoma,"Segoe UI",Arial,sans-serif}
.ltr{direction:ltr;unicode-bidi:isolate;display:inline-block}
body{font-size:8.1pt;line-height:1.28;-webkit-print-color-adjust:exact;print-color-adjust:exact;font-variant-numeric:tabular-nums}
.dco-unified-print-header{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(42mm,.62fr);align-items:start;gap:5mm;padding-bottom:1.5mm;margin-bottom:1.6mm;border-bottom:1.2pt solid #172033}
.dco-unified-print-brand{min-width:0;text-align:right;line-height:1.25;overflow-wrap:anywhere}
.dco-unified-print-factory-name{font-size:12.8pt;font-weight:950;line-height:1.05;color:#172033}
.dco-unified-print-factory-description{margin-top:.55mm;font-size:6.8pt;font-weight:800;line-height:1.35;color:#394550}
.dco-unified-print-factory-address{margin-top:.42mm;font-size:6.35pt;font-weight:650;line-height:1.35;color:#5d6874}
.dco-unified-print-factory-contacts{display:flex;flex-wrap:wrap;gap:.4mm 2.3mm;margin-top:.45mm;font-size:6.1pt;font-weight:700;line-height:1.3;color:#4f5a65}
.dco-unified-print-factory-contacts span{white-space:nowrap}
.dco-unified-print-document{min-width:0;text-align:left}
.dco-unified-print-document h1{margin:0;font-size:10.8pt;font-weight:900;line-height:1.08;letter-spacing:-.05pt;color:#394550}
.dco-unified-print-reference{margin-top:.7mm;font-size:15.6pt;font-weight:950;line-height:1.05;letter-spacing:.1pt;color:#172033;direction:ltr;unicode-bidi:plaintext;overflow-wrap:anywhere}
.dco-unified-print-date{margin-top:.75mm;font-size:6.7pt;font-weight:750;line-height:1.35;color:#5d6874;direction:ltr;unicode-bidi:plaintext}
.info{display:grid;gap:1.2mm;margin:0 0 2.2mm}
.shared-info{grid-template-columns:minmax(0,1.55fr) minmax(0,1.15fr) minmax(0,.95fr) minmax(0,.8fr) minmax(0,.7fr)}
.info>div{min-width:0;min-height:10.5mm;padding:1.35mm 1.55mm;border:.7pt solid #c7cdd3;border-radius:2.1mm;background:#fbfcfd;line-height:1.25;overflow-wrap:anywhere}
.info b{display:block;margin-bottom:.55mm;color:#5d6874;font-size:6.35pt;font-weight:800}
.shared-info-primary{display:block;color:#172033;font-size:8pt;font-weight:850;line-height:1.2;overflow-wrap:anywhere}
.shared-info-phone{display:flex;align-items:baseline;gap:1mm;margin-top:.65mm;color:#5d6874;font-size:6.35pt;font-weight:700;line-height:1.25}
.shared-info-phone-label{flex:0 0 auto}
.shared-info-phone-value{min-width:0;direction:ltr;unicode-bidi:plaintext;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.title{margin:2.1mm 0 1.2mm;font-size:9.2pt;font-weight:900;color:#172033}
.table{width:100%;border-collapse:separate;border-spacing:0;table-layout:fixed;border:.75pt solid #98a2ac;border-radius:2mm;overflow:hidden}
.table thead{display:table-header-group}
.table th,.table td{padding:1.05mm 1.1mm;text-align:center;vertical-align:middle;border-inline-start:.55pt solid #c5cbd1;border-bottom:.55pt solid #c5cbd1;line-height:1.2}
.table th:first-child,.table td:first-child{border-inline-start:0}
.table tbody tr:last-child td{border-bottom:0}
.table th{background:#eef1f4;color:#303a44;font-size:7.15pt;font-weight:900;white-space:nowrap}
.table tr{break-inside:avoid;page-break-inside:avoid}
.right{text-align:right!important;white-space:normal}
.measurements{font-size:7.65pt}
.measurements tbody tr:nth-child(even){background:#fbfcfd}
.measurements th:nth-child(1),.measurements td:nth-child(1){width:4%}
.measurements th:nth-child(2),.measurements td:nth-child(2){width:8%}
.measurements th:nth-child(3),.measurements td:nth-child(3),.measurements th:nth-child(4),.measurements td:nth-child(4){width:9%}
.measurements th:nth-child(5),.measurements td:nth-child(5){width:6%}
.measurements th:nth-child(6),.measurements td:nth-child(6){width:28%}
.measurements th:nth-child(7),.measurements td:nth-child(7){width:36%}
.dimension{display:inline-flex;min-width:12mm;flex-direction:column;align-items:center;gap:.35mm;line-height:1}
.dimension b{font-size:9pt;font-weight:900}
.dimension-lines{display:flex;min-height:1.7mm;flex-direction:column;align-items:center;gap:.35mm}
.dimension-edge-line{display:block;width:9mm;height:.55pt;border-radius:999px;background:#172033}
.dimension-lines-0{visibility:hidden}
.custom-edge-empty{display:block;min-height:2mm}
.custom-edge-summary{display:grid;gap:.8mm}
.custom-edge-line{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.25fr) auto;align-items:center;gap:1mm;padding:.8mm 1.1mm;border:.7pt solid #d7b54b;border-radius:1.6mm;background:#fff8df;text-align:right}
.custom-edge-line span{font-size:6.65pt;font-weight:800;color:#4c5258}
.custom-edge-line b{font-size:7.15pt;font-weight:900;overflow-wrap:anywhere}
.custom-edge-line em{padding:.25mm 1mm;border:.65pt solid currentColor;border-radius:999px;color:#805b00;font-size:5.9pt;font-style:normal;font-weight:900;white-space:nowrap}
.notes-cell{font-size:7.35pt;line-height:1.35}
.row-with-drawing td{padding-top:1.6mm;padding-bottom:1.6mm}
.order-note{margin-top:2.2mm;padding:1.7mm 2mm;border:.7pt solid #b9c0c7;border-radius:1.8mm;font-size:7.5pt;line-height:1.4}
.footer{display:flex;justify-content:space-between;margin-top:2.2mm;padding-top:1.1mm;border-top:.65pt solid #c4cad0;color:#6c7781;font-size:6.5pt}
.invoice{font-size:8.05pt;break-inside:avoid;page-break-inside:avoid}
.invoice th,.invoice td{padding:1.4mm 1.5mm}
.invoice th:nth-child(1),.invoice td:nth-child(1){width:5%}
.invoice th:nth-child(2),.invoice td:nth-child(2){width:47%}
.invoice th:nth-child(3),.invoice td:nth-child(3){width:11%}
.invoice th:nth-child(4),.invoice td:nth-child(4){width:10%}
.invoice th:nth-child(5),.invoice td:nth-child(5),.invoice th:nth-child(6),.invoice td:nth-child(6){width:13.5%}
.invoice-description{line-height:1.32}
.line-note{display:block;margin-top:.65mm;color:#66717c;font-size:6.8pt;font-weight:500;line-height:1.3}
.total{display:flex;justify-content:space-between;align-items:center;width:42%;margin:2.4mm 0 0 auto;padding:2mm 2.5mm;border:1.4pt solid #172033;border-radius:1.8mm;font-size:11pt;font-weight:900}
.dco-piece-notes{display:flex;flex-direction:column;gap:1.1mm;align-items:stretch;text-align:right}
.dco-piece-notes-text{white-space:pre-wrap;overflow-wrap:anywhere;font-size:7.6pt;font-weight:650;line-height:1.4}
.dco-piece-sketch{display:block;margin:0;padding:1mm 1.2mm .7mm;border:.7pt solid #aeb7bf;border-radius:1.8mm;background:#fff;break-inside:avoid}
.dco-piece-sketch>svg{display:block;width:100%;height:27mm;max-width:54mm;margin:0 auto;overflow:visible}
.dco-piece-sketch figcaption{margin-top:.5mm;color:#5e6974;font-size:6.7pt;font-weight:800;line-height:1.2;text-align:center}
.dco-piece-sketch em{display:block;margin-top:3px;color:#92400e;font-size:6px;font-style:normal;text-align:center}
@media print{a{color:inherit;text-decoration:none}}
"""


def _esc(value: object) -> str:
    return escape(str(value or ""), quote=True)


def _number(value: object) -> float:
    try:
        parsed = float(str(value or 0).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0
    return parsed if parsed == parsed else 0.0


def _quantity(value: object) -> str:
    number = _number(value)
    text = f"{number:.3f}".rstrip("0").rstrip(".")
    return text or "0"


def _truthy(value: object) -> bool:
    if value in (None, "", False):
        return False
    try:
        return float(value) != 0
    except (TypeError, ValueError):
        return bool(value)


def document_locale(language: str | None = None) -> tuple[str, str]:
    """Return ``(code, direction)`` for a supplied print language.

    The code keeps the caller's official spelling (``pt-BR``). Direction uses
    the base language, case-insensitively, and is RTL for ``ar``, ``he``,
    ``fa``, and ``ps``. A missing code maps to ``ar`` only inside this helper.
    HTML builders do not use that default.
    """
    code = str(language or "ar").strip().replace("_", "-") or "ar"
    base = code.lower().split("-", 1)[0]
    direction = "rtl" if base in RTL_DOCUMENT_LANGUAGES else "ltr"
    return code, direction


def _require_print_locale(language: str | None, translator: Any) -> tuple[str, str]:
    """Require the language that the labels will actually be written in.

    Message IDs are English. Frappe remains the only translation catalog, so
    this module does not embed an Arabic catalog and does not declare an
    Arabic document when the caller omitted a translator. Production passes the
    active language and ``frappe._``. Tests pass ``language="en"`` with an
    identity translator, or ``language="ar"`` with a translator that returns
    Arabic.
    """
    if not str(language or "").strip():
        raise ValueError("print_language_required")
    if not callable(translator):
        raise ValueError("print_translator_required")
    return document_locale(language)


def _label_separator(direction: str) -> str:
    return "، " if direction == "rtl" else ", "


def _label(message: str, translator: Any = None) -> str:
    if translator is None:
        return message
    return str(translator(message))


def _piece_type_label(value: object, translator: Any = None) -> str:
    key = str(value or "Regular").strip() or "Regular"
    return _label(PIECE_TYPE_LABELS.get(key, "Regular door"), translator)


def _qty(row: Mapping[str, Any]) -> int:
    return max(1, int(_number(row.get("qty")) or 1))


def _contact_lines(value: object) -> list[str]:
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


def _identity_value(identity: Mapping[str, Any], fieldname: str) -> str:
    stored = str(identity.get(fieldname) or "").strip()
    return stored or PRINT_IDENTITY_DEFAULTS[fieldname]


def _header_html(identity: Mapping[str, Any], *, reference: str, date: str, translator: Any = None) -> str:
    contacts = _contact_lines(_identity_value(identity, "print_factory_contacts"))
    contact_html = ""
    if contacts:
        contact_html = (
            '<div class="dco-unified-print-factory-contacts">'
            + "".join(f"<span>{_esc(line)}</span>" for line in contacts)
            + "</div>"
        )
    date_html = f'<div class="dco-unified-print-date">{_esc(date)}</div>' if date else ""
    return f"""<header class="dco-unified-print-header">
            <div class="dco-unified-print-brand">
                <div class="dco-unified-print-factory-name">{_esc(_identity_value(identity, "print_factory_name"))}</div>
                <div class="dco-unified-print-factory-description">{_esc(_identity_value(identity, "print_factory_description"))}</div>
                <div class="dco-unified-print-factory-address">{_esc(_identity_value(identity, "print_factory_address"))}</div>
                {contact_html}
            </div>
            <div class="dco-unified-print-document">
                <h1>{_esc(_label("Order measurements table", translator))}</h1>
                <div class="dco-unified-print-reference">{_esc(reference)}</div>
                {date_html}
            </div>
        </header>"""


def _shared_info(order: Mapping[str, Any], phone: str, translator: Any = None) -> str:
    pieces = order.get("pieces") or []
    door_count = sum(_qty(row) for row in pieces if isinstance(row, Mapping))
    return f"""<div class="info shared-info">
            <div class="shared-info-customer">
                <b>{_esc(_label("Customer", translator))}</b>
                <span class="shared-info-primary">{_esc(order.get("customer") or "—")}</span>
                <span class="shared-info-phone"><span class="shared-info-phone-label">{_esc(_label("Phone", translator))}</span><span class="shared-info-phone-value">{_esc(phone or "—")}</span></span>
            </div>
            <div><b>{_esc(_label("Board", translator))}</b>{_esc(order.get("board_description") or "—")}</div>
            <div><b>{_esc(_label("Edge color", translator))}</b>{_esc(order.get("edge_color") or _label("Not specified", translator))}</div>
            <div><b>{_esc(_label("Cutting machine", translator))}</b>{_esc(order.get("order_cutting_machine") or "—")}</div>
            <div><b>{_esc(_label("Door count", translator))}</b>{_quantity(door_count)}</div>
        </div>"""


def _extra_addon_labels(row: Mapping[str, Any], translator: Any = None) -> list[str]:
    return [_label(label, translator) for fieldname, label in EXTRA_ADDONS if _truthy(row.get(fieldname))]


def _notes_text(row: Mapping[str, Any], translator: Any = None, *, direction: str = "rtl") -> str:
    addons = _extra_addon_labels(row, translator)
    summary = (
        f"{_label('Add-ons', translator)}: {_label_separator(direction).join(addons)}"
        if addons
        else ""
    )
    notes = str(row.get("notes") or "").strip()
    if summary and notes:
        return f"{summary} — {notes}"
    return summary or notes


def _custom_edge_groups(row: Mapping[str, Any], translator: Any = None) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for selected_field, override_field, side_label in EDGE_SIDES:
        if not _truthy(row.get(selected_field)):
            continue
        override = str(row.get(override_field) or "").strip()
        if not override:
            continue
        group = groups.setdefault(override, {"type": override, "sides": []})
        group["sides"].append(_label(side_label, translator))
    return list(groups.values())


def _side_summary(
    group: Mapping[str, Any],
    custom_side_count: int,
    translator: Any = None,
    *,
    direction: str = "rtl",
) -> str:
    sides = list(group.get("sides") or [])
    if custom_side_count == 4 and len(sides) == 4:
        return _label("All around", translator)
    return _label_separator(direction).join(str(side) for side in sides)


def _custom_edge_html(row: Mapping[str, Any], translator: Any = None, *, direction: str = "rtl") -> str:
    groups = _custom_edge_groups(row, translator)
    if not groups:
        return f'<span class="custom-edge-empty" aria-label="{_esc(_label("No customization", translator))}"></span>'
    custom_side_count = sum(len(group["sides"]) for group in groups)
    lines = "".join(
        f"""<div class="custom-edge-line">
                <span>{_esc(_side_summary(group, custom_side_count, translator, direction=direction))}</span>
                <b>{_esc(group["type"])}</b>
                <em>{_esc(_label("Custom", translator))}</em>
            </div>"""
        for group in groups
    )
    return f'<div class="custom-edge-summary">{lines}</div>'


def _dimension_mark(value: object, count: int) -> str:
    safe_count = max(0, min(2, int(count or 0)))
    lines = "".join('<span class="dimension-edge-line"></span>' for _ in range(safe_count))
    return (
        f'<span class="dimension"><b>{_quantity(value)}</b>'
        f'<span class="dimension-lines dimension-lines-{safe_count}">{lines}</span></span>'
    )


def _parse_json(raw: object) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _legacy_pen_svg(payload: Mapping[str, Any]) -> str:
    canvas = payload.get("canvas") if isinstance(payload.get("canvas"), Mapping) else {}
    width = max(1.0, _number(canvas.get("width")) or 800)
    height = max(1.0, _number(canvas.get("height")) or 600)
    paths: list[str] = []
    for element in payload.get("elements") or []:
        if not isinstance(element, Mapping) or element.get("type") != "pen":
            continue
        points = element.get("points") or []
        pairs = [
            f"{_number(point[0])},{_number(point[1])}"
            for point in points
            if isinstance(point, Sequence) and len(point) >= 2
        ]
        if len(pairs) < 2:
            continue
        color = str(element.get("color") or "#172033")
        paths.append(
            f'<polyline points="{" ".join(pairs)}" fill="none" stroke="{_esc(color)}" '
            'stroke-width="3" stroke-linecap="round" stroke-linejoin="round" fill-opacity="0"/>'
        )
    if not paths:
        return ""
    return (
        f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet" role="img">'
        f'<rect width="{width}" height="{height}" fill="#fff"/>'
        f"{''.join(paths)}</svg>"
    )


def _documentation_svg(payload: Mapping[str, Any], label: str) -> str:
    canvas = payload.get("canvas") if isinstance(payload.get("canvas"), Mapping) else {}
    width = max(1.0, _number(canvas.get("widthMm") or canvas.get("width")) or 800)
    height = max(1.0, _number(canvas.get("heightMm") or canvas.get("height")) or 2100)
    marks: list[str] = []
    for element in payload.get("elements") or []:
        if not isinstance(element, Mapping):
            continue
        kind = str(element.get("type") or "")
        style = element.get("style") if isinstance(element.get("style"), Mapping) else {}
        stroke = str(style.get("color") or element.get("color") or "#1463e6")
        if kind in {"stroke", "pen"}:
            points = element.get("points") or []
            pairs = []
            for point in points:
                if isinstance(point, Mapping):
                    pairs.append(f"{_number(point.get('xMm'))} {_number(point.get('yMm'))}")
                elif isinstance(point, Sequence) and len(point) >= 2:
                    pairs.append(f"{_number(point[0])} {_number(point[1])}")
            if len(pairs) < 2:
                continue
            commands = " ".join(
                f"{'M' if index == 0 else 'L'}{pair}" for index, pair in enumerate(pairs)
            )
            closed = " Z" if element.get("closed") else ""
            marks.append(
                f'<path d="{commands}{closed}" fill="none" stroke="{_esc(stroke)}" '
                'stroke-width="3" stroke-linecap="round"/>'
            )
        elif kind in {"line", "arrow", "dimension"}:
            start = element.get("start") if isinstance(element.get("start"), Mapping) else {}
            end = element.get("end") if isinstance(element.get("end"), Mapping) else {}
            marks.append(
                f'<line x1="{_number(start.get("xMm"))}" y1="{_number(start.get("yMm"))}" '
                f'x2="{_number(end.get("xMm"))}" y2="{_number(end.get("yMm"))}" '
                f'stroke="{_esc(stroke)}" stroke-width="3"/>'
            )
        elif kind == "rect":
            marks.append(
                f'<rect x="{_number(element.get("xMm"))}" y="{_number(element.get("yMm"))}" '
                f'width="{max(0.0, _number(element.get("widthMm")))}" '
                f'height="{max(0.0, _number(element.get("heightMm")))}" '
                f'fill="none" stroke="{_esc(stroke)}" stroke-width="3"/>'
            )
        elif kind == "ellipse":
            ellipse_width = max(0.0, _number(element.get("widthMm")))
            ellipse_height = max(0.0, _number(element.get("heightMm")))
            marks.append(
                f'<ellipse cx="{_number(element.get("xMm")) + ellipse_width / 2}" '
                f'cy="{_number(element.get("yMm")) + ellipse_height / 2}" '
                f'rx="{ellipse_width / 2}" ry="{ellipse_height / 2}" '
                f'fill="none" stroke="{_esc(stroke)}" stroke-width="3"/>'
            )
        elif kind == "text":
            position = element.get("position") if isinstance(element.get("position"), Mapping) else {}
            marks.append(
                f'<text x="{_number(position.get("xMm"))}" y="{_number(position.get("yMm"))}" '
                f'direction="rtl" text-anchor="end" font-size="24" fill="{_esc(stroke)}">'
                f'{_esc(element.get("text"))}</text>'
            )
    if not marks:
        return _legacy_pen_svg(payload)
    return (
        f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet" '
        f'role="img" aria-label="{_esc(label)}"><rect width="{width}" height="{height}" fill="#fff"/>'
        f"{''.join(marks)}</svg>"
    )


def _geometry_svg(payload: Mapping[str, Any], label: str) -> str:
    width = max(0.0, _number(payload.get("blank_width_cm")))
    height = max(0.0, _number(payload.get("blank_length_cm")))
    points = payload.get("points") or []
    pairs = [
        f"{_number(point[0])},{_number(point[1])}"
        for point in points
        if isinstance(point, Sequence) and len(point) >= 2
    ]
    if not width or not height or len(pairs) < 3:
        return ""
    padding = max(width, height) * 0.06
    return (
        f'<svg viewBox="{-padding} {-padding} {width + padding * 2} {height + padding * 2}" '
        f'preserveAspectRatio="xMidYMid meet" role="img" aria-label="{_esc(label)}">'
        f'<polygon points="{" ".join(pairs)}" fill="#f5f7f9" stroke="#172033" stroke-width="1.8"/>'
        "</svg>"
    )


def _drawing_caption(index: int, translator: Any = None) -> str:
    return _label("Door piece drawing {0}", translator).replace("{0}", str(index))


def _drawing_svg(row: Mapping[str, Any], index: int, translator: Any = None) -> str:
    label = _drawing_caption(index, translator)
    drawing = _parse_json(row.get("special_shape_drawing_json") or row.get("drawing_json"))
    if drawing:
        schema = str(drawing.get("schema") or "")
        if schema == DOCUMENTATION_SCHEMA and int(_number(drawing.get("version"))) == DRAWING_VERSION:
            return _documentation_svg(drawing, label)
        if drawing.get("elements"):
            return _documentation_svg(drawing, label)
    geometry = _parse_json(row.get("special_shape_geometry_json") or row.get("geometry_json"))
    if geometry:
        return _geometry_svg(geometry, label)
    return ""


def _notes_cell(
    row: Mapping[str, Any],
    index: int,
    translator: Any = None,
    *,
    direction: str = "rtl",
) -> str:
    notes = _notes_text(row, translator, direction=direction)
    visual = _drawing_svg(row, index, translator)
    if not visual:
        return _esc(notes or "—")
    text = f'<div class="dco-piece-notes-text">{_esc(notes)}</div>' if notes else ""
    return (
        f'<div class="dco-piece-notes">{text}'
        f'<figure class="dco-piece-sketch">{visual}'
        f'<figcaption>{_esc(_drawing_caption(index, translator))}</figcaption>'
        f"<em>{_esc(_label('This documents the customer request and is not a manufacturing file.', translator))}</em></figure></div>"
    )


def _row_html(
    row: Mapping[str, Any],
    index: int,
    translator: Any = None,
    *,
    direction: str = "rtl",
) -> str:
    long_count = int(_truthy(row.get("edge_long_right"))) + int(_truthy(row.get("edge_long_left")))
    width_count = int(_truthy(row.get("edge_width_top"))) + int(_truthy(row.get("edge_width_bottom")))
    drawing = bool(_drawing_svg(row, index, translator))
    row_class = ' class="row-with-drawing"' if drawing else ""
    notes_class = " notes-with-drawing" if drawing else ""
    return f"""<tr{row_class}>
                <td><b>{index}</b></td>
                <td>{_esc(_piece_type_label(row.get("piece_type"), translator))}</td>
                <td class="ltr">{_dimension_mark(row.get("width_cm"), width_count)}</td>
                <td class="ltr">{_dimension_mark(row.get("length_cm"), long_count)}</td>
                <td>{_qty(row)}</td>
                <td class="right custom-edge-cell">{_custom_edge_html(row, translator, direction=direction)}</td>
                <td class="right notes-cell{notes_class}">{_notes_cell(row, index, translator, direction=direction)}</td>
            </tr>"""


def _table_html(pieces: Sequence[Any], translator: Any = None, *, direction: str = "rtl") -> str:
    rows = [
        _row_html(row, index, translator, direction=direction)
        for index, row in enumerate(pieces, start=1)
        if isinstance(row, Mapping)
    ]
    body = "".join(rows)
    return f"""<table class="table measurements">
            <thead><tr><th>#</th><th>{_esc(_label("Type", translator))}</th><th>{_esc(_label("Width", translator))}</th><th>{_esc(_label("Length", translator))}</th><th>{_esc(_label("Qty", translator))}</th><th>{_esc(_label("Custom edge banding", translator))}</th><th>{_esc(_label("Notes", translator))}</th></tr></thead>
            <tbody>{body}</tbody>
        </table>"""


PRINT_ORDER_FIELDS = (
    "name",
    "customer",
    "order_date",
    "board_description",
    "edge_color",
    "order_cutting_machine",
    "order_notes",
)
PRINT_PIECE_FIELDS = (
    "name",
    "piece_type",
    "width_cm",
    "length_cm",
    "qty",
    "notes",
    "edge_long_right",
    "edge_long_left",
    "edge_width_top",
    "edge_width_bottom",
    "edge_long_right_type_override",
    "edge_long_left_type_override",
    "edge_width_top_type_override",
    "edge_width_bottom_type_override",
    "extra_double",
    "extra_full_door_double",
    "extra_liner",
    "extra_back_groove",
    "extra_recessed_handle_cutout",
    "special_shape_drawing_json",
    "drawing_json",
    "special_shape_geometry_json",
    "geometry_json",
)


def as_mapping(value: Any) -> Mapping[str, Any]:
    converter = getattr(value, "as_dict", None)
    if callable(converter):
        converted = converter()
        if isinstance(converted, Mapping):
            return converted
    if isinstance(value, Mapping):
        return value
    return {}


def order_print_payload(order: Any) -> dict[str, Any]:
    values = as_mapping(order)
    pieces = []
    for row in values.get("pieces") or []:
        row_values = as_mapping(row)
        pieces.append({fieldname: row_values.get(fieldname) for fieldname in PRINT_PIECE_FIELDS})
    payload = {fieldname: values.get(fieldname) for fieldname in PRINT_ORDER_FIELDS}
    payload["pieces"] = pieces
    return payload


def _print_body_html(
    order: Mapping[str, Any],
    *,
    identity: Mapping[str, Any] | None,
    customer_phone: str,
    printed_on: str,
    title_prefix: str,
    extra_html: str = "",
    language: str | None = None,
    translator: Any = None,
) -> str:
    language_code, direction = _require_print_locale(language, translator)
    reference = str(order.get("name") or "").strip() or _label("Draft", translator)
    date = str(order.get("order_date") or "").strip()
    notes = str(order.get("order_notes") or "").strip()
    notes_html = (
        f'<div class="order-note"><b>{_esc(_label("Order notes:", translator))}</b> {_esc(notes)}</div>'
        if notes
        else ""
    )
    pieces = order.get("pieces") or []
    title = f"{_esc(_label(title_prefix, translator))} {_esc(reference)}"
    css = MEASUREMENTS_PRINT_CSS.replace("direction:rtl", f"direction:{direction}", 1)
    return f"""<!doctype html><html dir="{direction}" lang="{_esc(language_code)}"><head><meta charset="utf-8"><title>{title}</title><style>{css}</style></head><body>
            {_header_html(identity or {}, reference=reference, date=date, translator=translator)}
            {_shared_info(order, customer_phone, translator)}
            <div class="title">{_esc(_label("Measurements table", translator))}</div>
            {_table_html(pieces if isinstance(pieces, Sequence) else [], translator, direction=direction)}
            {notes_html}
            {extra_html}
            <div class="footer"><span>{_esc(_label("Order number:", translator))} {_esc(reference)}</span><span>{_esc(_label("Printed on:", translator))} {_esc(printed_on)}</span></div>
        </body></html>"""


def measurements_print_html(
    order: Mapping[str, Any],
    *,
    identity: Mapping[str, Any] | None = None,
    customer_phone: str = "",
    printed_on: str = "",
    language: str | None = None,
    translator: Any = None,
) -> str:
    """Render the measurements document.

    ``language`` and ``translator`` are required. ``translator`` is ``frappe._``
    in production. Omitting either raises ``ValueError`` instead of emitting an
    Arabic document whose labels are still English message IDs.
    """
    return _print_body_html(
        order,
        identity=identity,
        customer_phone=customer_phone,
        printed_on=printed_on,
        title_prefix="Order measurements",
        language=language,
        translator=translator,
    )


def _quote_quantity(value: object) -> str:
    number = _number(value)
    text = f"{number:,.3f}".rstrip("0").rstrip(".")
    return text or "0"


def _quote_money(value: object) -> str:
    return f"{_number(value):,.2f}"


# Historical stored quote phrases. They match old edge notes and are not UI labels.
_LEGACY_DEFAULT_EDGE_NOTE = "من القشاط الافتراضي"
_LEGACY_CUSTOM_EDGE_PHRASE = "يتضمن أطرافًا مخصصة"


def _quote_line_note(line: Mapping[str, Any], translator: Any = None) -> str:
    note = str(line.get("note") or "").strip()
    if not note:
        return ""
    if str(line.get("type") or "") != "edge":
        return note
    if _LEGACY_DEFAULT_EDGE_NOTE in note:
        return ""
    return note.replace(
        _LEGACY_CUSTOM_EDGE_PHRASE,
        _label("Exceptional customization", translator),
    )


def _quote_total(payload: Mapping[str, Any]) -> float:
    totals = payload.get("totals") or []
    if isinstance(totals, Sequence):
        for item in totals:
            if isinstance(item, Mapping) and item.get("value_usd") is not None:
                return _number(item.get("value_usd"))
    lines = payload.get("lines") or []
    if not isinstance(lines, Sequence):
        return 0.0
    return sum(
        _number(line.get("amount_usd"))
        for line in lines
        if isinstance(line, Mapping)
    )


def _quote_rows_html(payload: Mapping[str, Any], translator: Any = None) -> str:
    lines = payload.get("lines") or []
    if not isinstance(lines, Sequence) or not lines:
        empty = _esc(_label("No price lines are available for this order.", translator))
        return f'<tr><td colspan="6">{empty}</td></tr>'
    rows: list[str] = []
    for index, line in enumerate(lines, start=1):
        if not isinstance(line, Mapping):
            continue
        note = _quote_line_note(line, translator)
        rate = line.get("rate_usd")
        rate_html = _quote_money(rate) if rate or rate == 0 else "—"
        note_html = (
            f'<span class="line-note">{_esc(note)}</span>' if note else ""
        )
        rows.append(
            f"""<tr>
                <td>{index}</td>
                <td class="right invoice-description"><b>{_esc(line.get("description"))}</b>{note_html}</td>
                <td>{_quote_quantity(line.get("quantity"))}</td>
                <td>{_esc(line.get("unit"))}</td>
                <td>{rate_html}</td>
                <td><b>{_quote_money(line.get("amount_usd"))}</b></td>
            </tr>"""
        )
    return "".join(rows) or f'<tr><td colspan="6">{_esc(_label("No price lines are available for this order.", translator))}</td></tr>'


def _quote_details_html(payload: Mapping[str, Any], translator: Any = None) -> str:
    return f"""<section class="quote-details">
            <div class="title quote-title">{_esc(_label("Quotation details", translator))}</div>
            <table class="table invoice"><thead><tr><th>#</th><th class="right">{_esc(_label("Description", translator))}</th><th>{_esc(_label("Quantity", translator))}</th><th>{_esc(_label("Unit", translator))}</th><th>{_esc(_label("Unit price $", translator))}</th><th>{_esc(_label("Total $", translator))}</th></tr></thead><tbody>{_quote_rows_html(payload, translator)}</tbody></table>
            <div class="total"><span>{_esc(_label("Final total", translator))}</span><span>$ {_quote_money(_quote_total(payload))}</span></div>
        </section>"""


def _overlay_invoice_drawings(
    order: Mapping[str, Any],
    quote_payload: Mapping[str, Any],
) -> dict[str, Any]:
    payload = dict(order)
    drawings: dict[str, object] = {}
    for row in quote_payload.get("measurements") or []:
        if not isinstance(row, Mapping):
            continue
        piece_name = str(row.get("piece_name") or "").strip()
        drawing = row.get("special_shape_drawing_json")
        if piece_name and drawing:
            drawings[piece_name] = drawing
    pieces: list[dict[str, Any]] = []
    for row in payload.get("pieces") or []:
        if not isinstance(row, Mapping):
            continue
        values = dict(row)
        name = str(values.get("name") or "").strip()
        if name and name in drawings:
            values["special_shape_drawing_json"] = drawings[name]
            values["drawing_json"] = drawings[name]
        pieces.append(values)
    payload["pieces"] = pieces
    return payload


def customer_invoice_print_html(
    order: Mapping[str, Any],
    quote_payload: Mapping[str, Any] | None = None,
    *,
    identity: Mapping[str, Any] | None = None,
    customer_phone: str = "",
    printed_on: str = "",
    language: str | None = None,
    translator: Any = None,
) -> str:
    """Render the customer invoice on the measurements document.

    ``language`` and ``translator`` follow the same contract as
    ``measurements_print_html``: both are required, and translation stays in
    the supplied translator rather than a catalog inside this module.
    """
    payload = quote_payload if isinstance(quote_payload, Mapping) else {}
    printable = _overlay_invoice_drawings(order, payload)
    return _print_body_html(
        printable,
        identity=identity,
        customer_phone=customer_phone,
        printed_on=printed_on,
        title_prefix="Customer invoice for order",
        extra_html=_quote_details_html(payload, translator),
        language=language,
        translator=translator,
    )


__all__ = [
    "PRINT_IDENTITY_DEFAULTS",
    "as_mapping",
    "customer_invoice_print_html",
    "measurements_print_html",
    "order_print_payload",
]
