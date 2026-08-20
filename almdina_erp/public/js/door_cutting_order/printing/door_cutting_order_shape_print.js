(() => {
    "use strict";
    const shapeOutput = window.AlmdinaShapeOutputContract;
    if (!shapeOutput) { console.error("Shape output contract must load before the printable documentation renderer"); return; }
    let sequence = 0;
    function esc(value) { return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;"); }
    function finite(value, fallback = 0) { const number = Number(value); return Number.isFinite(number) ? number : fallback; }
    function color(value, fallback = "#1463e6") { const resolved = String(value || ""); return /^#[0-9a-f]{3,8}$/i.test(resolved) ? resolved : fallback; }
    function point(value) { return value && Number.isFinite(Number(value.xMm)) && Number.isFinite(Number(value.yMm)) ? { x: Number(value.xMm), y: Number(value.yMm) } : null; }
    function path(points, closed) { const valid = (points || []).map(point).filter(Boolean); if (valid.length < 2) return ""; return `${valid.map((item, index) => `${index ? "L" : "M"}${item.x} ${item.y}`).join(" ")}${closed ? " Z" : ""}`; }
    function arrowHead(id, markerColor) { return `<marker id="${id}" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto-start-reverse"><path d="M8,0 L0,4 L8,8" fill="none" stroke="${markerColor}" stroke-width="1.2"/></marker>`; }
    function documentationElement(element, markerId) {
        if (!element || typeof element !== "object") return ""; const stroke = color(element.style && element.style.color); const width = Math.max(1, Math.min(8, finite(element.style && element.style.width, 3)));
        if (element.type === "stroke") { const data = path(element.points, element.closed); return data ? `<path d="${data}" fill="none" stroke="${stroke}" stroke-width="${width}" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>` : ""; }
        if (["line", "arrow", "dimension"].includes(element.type)) {
            const start = point(element.start), end = point(element.end); if (!start || !end) return ""; const marker = element.type === "arrow" ? ` marker-end="url(#${markerId})"` : element.type === "dimension" ? ` marker-start="url(#${markerId})" marker-end="url(#${markerId})"` : "";
            const line = `<line x1="${start.x}" y1="${start.y}" x2="${end.x}" y2="${end.y}" stroke="${stroke}" stroke-width="${width}" vector-effect="non-scaling-stroke"${marker}/>`;
            if (element.type !== "dimension") return line; const unit = element.unit === "cm" ? "cm" : "mm"; const value = unit === "cm" ? finite(element.valueMm) / 10 : finite(element.valueMm); const label = `${Math.round(value * 10) / 10} ${unit}`; const x = (start.x + end.x) / 2, y = (start.y + end.y) / 2;
            return `${line}<g><rect x="${x - 55}" y="${y - 20}" width="110" height="28" rx="5" fill="#fff" stroke="${stroke}" stroke-width="1" vector-effect="non-scaling-stroke"/><text x="${x}" y="${y}" text-anchor="middle" font-family="Tahoma,Arial,sans-serif" font-size="18" font-weight="700" fill="${stroke}">${esc(label)}</text></g>`;
        }
        if (["rect", "ellipse"].includes(element.type)) { const x = finite(element.xMm), y = finite(element.yMm), w = Math.max(0, finite(element.widthMm)), h = Math.max(0, finite(element.heightMm)); return element.type === "rect" ? `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="none" stroke="${stroke}" stroke-width="${width}" vector-effect="non-scaling-stroke"/>` : `<ellipse cx="${x + w / 2}" cy="${y + h / 2}" rx="${w / 2}" ry="${h / 2}" fill="none" stroke="${stroke}" stroke-width="${width}" vector-effect="non-scaling-stroke"/>`; }
        if (element.type === "text") { const position = point(element.position); return position ? `<text x="${position.x}" y="${position.y}" direction="rtl" unicode-bidi="plaintext" text-anchor="end" font-family="Tahoma,Arial,sans-serif" font-size="22" font-weight="700" fill="${color(element.style && element.style.color, "#9a4b00")}" paint-order="stroke" stroke="#fff" stroke-width="3">${esc(element.text)}</text>` : ""; }
        return "";
    }
    function referenceMarkup(reference, width, height) {
        if (!reference || !String(reference.fileUrl || "").startsWith("/private/files/")) return ""; const opacity = Math.max(.1, Math.min(1, finite(reference.opacity, .72))), rotation = Math.max(-360, Math.min(360, finite(reference.rotationDeg)));
        return `<image href="${esc(reference.fileUrl)}" x="0" y="0" width="${width}" height="${height}" preserveAspectRatio="xMidYMid meet" opacity="${opacity}" transform="rotate(${rotation} ${width / 2} ${height / 2})"/>`;
    }
    function documentationSvg(payload, label) {
        const width = Math.max(1, finite(payload.canvas && payload.canvas.widthMm, 800)), height = Math.max(1, finite(payload.canvas && payload.canvas.heightMm, 2100)); sequence += 1; const markerId = `dco-doc-arrow-${sequence}`;
        const elements = (payload.elements || []).map(item => documentationElement(item, markerId)).join("");
        return `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${esc(label)}"><defs>${arrowHead(markerId, "#173c75")}</defs><rect width="${width}" height="${height}" fill="#fff"/>${referenceMarkup(payload.reference, width, height)}${elements}</svg>`;
    }
    function geometrySvg(payload, label) {
        const width = Math.max(0, finite(payload.blank_width_cm)), height = Math.max(0, finite(payload.blank_length_cm)); const points = (payload.points || []).filter(item => Array.isArray(item) && item.length >= 2).map(item => `${finite(item[0])},${finite(item[1])}`).join(" "); if (!width || !height || !points) return ""; const padding = Math.max(width, height) * .06;
        return `<svg viewBox="${-padding} ${-padding} ${width + padding * 2} ${height + padding * 2}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${esc(label)}"><polygon points="${points}" fill="#f5f7f9" stroke="#172033" stroke-width="1.8" vector-effect="non-scaling-stroke"/></svg>`;
    }
    function svg(piece, options = {}) { const selected = shapeOutput.visual(piece); if (!selected) return ""; return selected.kind === "documentation" ? documentationSvg(selected.payload, options.label || "توثيق الدرفة") : geometrySvg(selected.payload, options.label || "هندسة الدرفة"); }
    function notesCell(piece, notes, options = {}) {
        const selected = shapeOutput.visual(piece), visual = svg(piece, options), text = String(notes || "").trim(), documentationNotes = selected && selected.kind === "documentation" ? String(selected.payload.notes || "").trim() : ""; if (!visual) return esc(text || "—");
        return `<div class="dco-piece-notes">${text ? `<div class="dco-piece-notes-text">${esc(text)}</div>` : ""}<figure class="dco-piece-sketch">${visual}<figcaption>${esc(options.caption || "توثيق الدرفة")}</figcaption>${documentationNotes ? `<p>${esc(documentationNotes)}</p>` : ""}<em>هذا توثيق لطلب العميل وليس ملف تصنيع</em></figure></div>`;
    }
    const css = `.dco-piece-notes{display:flex;flex-direction:column;gap:4px;align-items:stretch;text-align:right}.dco-piece-notes-text{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.45}.dco-piece-sketch{display:block;margin:0;padding:4px;border:1px solid #aeb7bf;border-radius:4px;background:#fff;break-inside:avoid;page-break-inside:avoid}.dco-piece-sketch svg{display:block;width:100%;height:92px;max-width:165px;margin:0 auto;overflow:visible}.dco-piece-sketch figcaption{margin-top:2px;color:#344054;font-size:7px;font-weight:700;text-align:center}.dco-piece-sketch p{margin:3px 0 0;font-size:7px;line-height:1.35;white-space:pre-wrap}.dco-piece-sketch em{display:block;margin-top:3px;color:#92400e;font-size:6px;font-style:normal;text-align:center}tr.dco-row-with-sketch{break-inside:avoid;page-break-inside:avoid}td.dco-notes-has-sketch{min-width:38mm}`;
    window.AlmdinaShapePrint = Object.freeze({ parse: shapeOutput.parseDrawing, drawingPayload: shapeOutput.drawingFromPiece, geometryPayload: shapeOutput.geometryFromPiece, hasVisual: shapeOutput.hasVisual, svg, notesCell, css });
})();
