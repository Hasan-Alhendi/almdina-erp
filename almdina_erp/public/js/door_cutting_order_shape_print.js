(() => {
    "use strict";

    const DEFAULT_CANVAS = { width: 1000, height: 650 };
    const MAX_PRINT_POINTS = 1800;
    const PARSE_CACHE_LIMIT = 300;
    const parseCache = new Map();
    let previewSequence = 0;

    function esc(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function finite(value, fallback = 0) {
        const result = Number(value);
        return Number.isFinite(result) ? result : fallback;
    }

    function positive(value, fallback) {
        const result = finite(value, fallback);
        return result > 0 ? result : fallback;
    }

    function safeColor(value) {
        const color = String(value || "").trim();
        return /^#[0-9a-f]{3,8}$/i.test(color) ? color : "#172033";
    }

    function clampPrintedNoteFontSize(value) {
        const parsed = Number(value || 0);
        if (!Number.isFinite(parsed)) return 24;
        return Math.max(24, Math.min(38, parsed));
    }

    function parse(raw) {
        if (!raw) return null;
        try {
            if (typeof raw !== "string") return raw;
            if (parseCache.has(raw)) return parseCache.get(raw);
            const payload = JSON.parse(raw);
            parseCache.set(raw, payload);
            if (parseCache.size > PARSE_CACHE_LIMIT) {
                parseCache.delete(parseCache.keys().next().value);
            }
            return payload;
        } catch (error) {
            return null;
        }
    }

    function drawingPayload(piece) {
        const payload = parse(piece && (
            piece.special_shape_drawing_json
            || piece.drawing_json
        ));
        return (
            payload
            && Number(payload.version) === 1
            && Array.isArray(payload.elements)
            && payload.elements.length
        ) ? payload : null;
    }

    function geometryPayload(piece) {
        const payload = parse(piece && (
            piece.special_shape_geometry_json
            || piece.geometry_json
        ));
        return (
            payload
            && Number(payload.version) === 1
            && payload.kind === "polygon"
            && Array.isArray(payload.points)
            && payload.points.length >= 3
        ) ? payload : null;
    }

    function pointPair(point) {
        if (!Array.isArray(point) || point.length < 2) return null;
        const x = finite(point[0], NaN);
        const y = finite(point[1], NaN);
        return Number.isFinite(x) && Number.isFinite(y) ? [x, y] : null;
    }

    function printablePoints(points) {
        const source = (Array.isArray(points) ? points : [])
            .map(pointPair)
            .filter(Boolean);
        if (source.length <= MAX_PRINT_POINTS) return source;
        const stride = Math.ceil(source.length / MAX_PRINT_POINTS);
        const compact = source.filter((point, index) => index % stride === 0);
        const last = source[source.length - 1];
        if (compact[compact.length - 1] !== last) compact.push(last);
        return compact;
    }

    function boundsForPoints(points) {
        if (!points.length) return null;
        const xs = points.map(point => point[0]);
        const ys = points.map(point => point[1]);
        return {
            x: Math.min(...xs),
            y: Math.min(...ys),
            width: Math.max(...xs) - Math.min(...xs),
            height: Math.max(...ys) - Math.min(...ys),
        };
    }

    function unionBounds(first, second) {
        if (!first) return second;
        if (!second) return first;
        const x = Math.min(first.x, second.x);
        const y = Math.min(first.y, second.y);
        const right = Math.max(first.x + first.width, second.x + second.width);
        const bottom = Math.max(first.y + first.height, second.y + second.height);
        return { x, y, width: right - x, height: bottom - y };
    }

    function elementBounds(element) {
        if (!element || typeof element !== "object") return null;
        if (element.type === "pen") {
            return boundsForPoints(printablePoints(element.points));
        }
        if (element.type === "line" || element.type === "dimension") {
            const x1 = finite(element.x1);
            const y1 = finite(element.y1);
            const x2 = finite(element.x2);
            const y2 = finite(element.y2);
            const labelHeight = element.type === "dimension" ? 42 : 0;
            return {
                x: Math.min(x1, x2),
                y: Math.min(y1, y2) - labelHeight,
                width: Math.abs(x2 - x1),
                height: Math.abs(y2 - y1) + labelHeight,
            };
        }
        if (element.type === "rectangle") {
            return {
                x: finite(element.x),
                y: finite(element.y),
                width: Math.max(0, finite(element.width)),
                height: Math.max(0, finite(element.height)),
            };
        }
        if (element.type === "ellipse") {
            const rx = Math.max(0, finite(element.rx));
            const ry = Math.max(0, finite(element.ry));
            return {
                x: finite(element.cx) - rx,
                y: finite(element.cy) - ry,
                width: rx * 2,
                height: ry * 2,
            };
        }
        if (element.type === "note") {
            const text = String(element.text || "");
            const fontSize = clampPrintedNoteFontSize(
                element.font_size || element.fontSize || 24
            );
            const width = Math.min(
                460,
                Math.max(fontSize * 2, Math.min(34, text.length) * fontSize * 0.62)
            );
            const x = finite(element.x);
            const anchor = element.text_anchor === "middle" ? "middle" : "end";
            return {
                x: anchor === "middle" ? x - width / 2 : x - width,
                y: finite(element.y) - fontSize * 0.7,
                width,
                height: fontSize * 1.4,
            };
        }
        return null;
    }

    function drawingViewBox(payload) {
        const canvas = {
            width: positive(payload.canvas && payload.canvas.width, DEFAULT_CANVAS.width),
            height: positive(payload.canvas && payload.canvas.height, DEFAULT_CANVAS.height),
        };
        const bounds = payload.elements.reduce(
            (result, element) => unionBounds(result, elementBounds(element)),
            null
        );
        if (!bounds || (!bounds.width && !bounds.height)) {
            return { x: 0, y: 0, width: canvas.width, height: canvas.height };
        }
        const padding = Math.max(22, Math.min(canvas.width, canvas.height) * 0.035);
        const x = Math.min(canvas.width - 1, Math.max(0, bounds.x - padding));
        const y = Math.min(canvas.height - 1, Math.max(0, bounds.y - padding));
        const right = Math.max(x + 1, Math.min(canvas.width, bounds.x + bounds.width + padding));
        const bottom = Math.max(y + 1, Math.min(canvas.height, bounds.y + bounds.height + padding));
        return {
            x,
            y,
            width: Math.max(80, right - x),
            height: Math.max(60, bottom - y),
        };
    }

    function pathData(points) {
        return printablePoints(points)
            .map((point, index) => `${index ? "L" : "M"}${point[0].toFixed(1)} ${point[1].toFixed(1)}`)
            .join(" ");
    }

    function elementMarkup(element, markerId) {
        if (!element || typeof element !== "object") return "";
        const color = safeColor(element.color);
        const stroke = `stroke="${color}" vector-effect="non-scaling-stroke"`;
        if (element.type === "pen") {
            const path = pathData(element.points);
            return path
                ? `<path d="${path}" fill="none" ${stroke} stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>`
                : "";
        }
        if (element.type === "line") {
            return `<line x1="${finite(element.x1)}" y1="${finite(element.y1)}" x2="${finite(element.x2)}" y2="${finite(element.y2)}" ${stroke} stroke-width="1.8" stroke-linecap="round"/>`;
        }
        if (element.type === "rectangle") {
            return `<rect x="${finite(element.x)}" y="${finite(element.y)}" width="${Math.max(0, finite(element.width))}" height="${Math.max(0, finite(element.height))}" rx="2" fill="none" ${stroke} stroke-width="1.8"/>`;
        }
        if (element.type === "ellipse") {
            return `<ellipse cx="${finite(element.cx)}" cy="${finite(element.cy)}" rx="${Math.max(0, finite(element.rx))}" ry="${Math.max(0, finite(element.ry))}" fill="none" ${stroke} stroke-width="1.8"/>`;
        }
        if (element.type === "dimension") {
            const x1 = finite(element.x1);
            const y1 = finite(element.y1);
            const x2 = finite(element.x2);
            const y2 = finite(element.y2);
            const x = (x1 + x2) / 2;
            const y = (y1 + y2) / 2 - 12;
            const text = String(element.text || "");
            const width = Math.max(68, Math.min(280, text.length * 14));
            return `<g>
                <line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" ${stroke} stroke-width="1.25" marker-start="url(#${markerId})" marker-end="url(#${markerId})"/>
                <rect x="${x - width / 2}" y="${y - 18}" width="${width}" height="27" rx="6" fill="#fff" stroke="${color}" stroke-width="1"/>
                <text x="${x}" y="${y + 1}" text-anchor="middle" font-family="Tahoma,Arial,sans-serif" font-size="17" font-weight="700" fill="${color}">${esc(text)}</text>
            </g>`;
        }
        if (element.type === "note") {
            const text = String(element.text || "");
            const displayText = text.length > 34 ? `${text.slice(0, 33)}…` : text;
            const x = finite(element.x);
            const y = finite(element.y);
            const fontSize = clampPrintedNoteFontSize(
                element.font_size || element.fontSize || 24
            );
            const anchor = element.text_anchor === "middle" ? "middle" : "end";
            return `<g>
                <text data-dco-readable-note="1" x="${x}" y="${y}" direction="rtl" unicode-bidi="plaintext" text-anchor="${anchor}" dominant-baseline="middle" font-family="Tahoma,Arial,sans-serif" font-size="${fontSize}" font-weight="800" fill="${color}" paint-order="stroke" stroke="#fff" stroke-width="2.4" stroke-linejoin="round">${esc(displayText)}</text>
            </g>`;
        }
        return "";
    }

    function drawingSvg(payload, label) {
        previewSequence += 1;
        const markerId = `dco-print-arrow-${previewSequence}`;
        const viewBox = drawingViewBox(payload);
        const elements = payload.elements
            .map(element => elementMarkup(element, markerId))
            .join("");
        if (!elements) return "";
        return `<svg viewBox="${viewBox.x} ${viewBox.y} ${viewBox.width} ${viewBox.height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${esc(label)}">
            <defs><marker id="${markerId}" markerWidth="7" markerHeight="7" refX="3.5" refY="3.5" orient="auto-start-reverse"><path d="M7,0 L0,3.5 L7,7" fill="none" stroke="#172033" stroke-width="1.2"/></marker></defs>
            <rect x="${viewBox.x}" y="${viewBox.y}" width="${viewBox.width}" height="${viewBox.height}" fill="#fff"/>
            ${elements}
        </svg>`;
    }

    function geometrySvg(payload, label) {
        const width = positive(payload.blank_width_cm, 0);
        const length = positive(payload.blank_length_cm, 0);
        const points = (payload.points || []).map(pointPair).filter(Boolean);
        if (!width || !length || points.length < 3) return "";
        const padding = Math.max(width, length) * 0.06;
        const attribute = points.map(point => `${point[0]},${point[1]}`).join(" ");
        return `<svg viewBox="${-padding} ${-padding} ${width + padding * 2} ${length + padding * 2}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${esc(label)}">
            <polygon points="${attribute}" fill="#f5f7f9" stroke="#172033" stroke-width="1.8" vector-effect="non-scaling-stroke" stroke-linejoin="round"/>
        </svg>`;
    }

    function svg(piece, options = {}) {
        const label = options.label || "رسمة الدرفة";
        const drawing = drawingPayload(piece);
        if (drawing) return drawingSvg(drawing, label);
        const geometry = geometryPayload(piece);
        return geometry ? geometrySvg(geometry, label) : "";
    }

    function hasVisual(piece) {
        return Boolean(drawingPayload(piece) || geometryPayload(piece));
    }

    function notesCell(piece, notes, options = {}) {
        const drawing = svg(piece, options);
        const text = String(notes || "").trim();
        if (!drawing) return esc(text || "—");
        return `<div class="dco-piece-notes">
            ${text ? `<div class="dco-piece-notes-text">${esc(text)}</div>` : ""}
            <figure class="dco-piece-sketch">
                ${drawing}
                <figcaption>${esc(options.caption || "رسمة الدرفة")}</figcaption>
            </figure>
        </div>`;
    }

    const css = `
.dco-piece-notes{display:flex;flex-direction:column;gap:4px;align-items:stretch;text-align:right}
.dco-piece-notes-text{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.45}
.dco-piece-sketch{display:block;margin:0;padding:3px 4px 2px;border:1px solid #aeb7bf;border-radius:4px;background:#fff;break-inside:avoid;page-break-inside:avoid}
.dco-piece-sketch svg{display:block;width:100%;height:68px;max-width:155px;margin:0 auto;overflow:visible;shape-rendering:geometricPrecision}
.dco-piece-sketch svg text[data-dco-readable-note="1"]{font-family:Tahoma,"Segoe UI",Arial,sans-serif!important}
.dco-piece-sketch figcaption{margin-top:1px;color:#59636d;font-size:7px;font-weight:700;line-height:1.2;text-align:center}
tr.dco-row-with-sketch{break-inside:avoid;page-break-inside:avoid}
td.dco-notes-has-sketch{min-width:38mm}
`;

    window.AlmdinaShapePrint = Object.freeze({
        parse,
        drawingPayload,
        geometryPayload,
        hasVisual,
        svg,
        notesCell,
        css,
    });
})();
