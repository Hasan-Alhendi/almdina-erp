(() => {
    "use strict";
    const shapeOutput = window.AlmdinaShapeOutputContract;
    if (!shapeOutput) { console.error("Shape output contract must load before the printable documentation renderer"); return; }
    let sequence = 0;
    function esc(value) { return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;"); }
    function finite(value, fallback = 0) { const number = Number(value); return Number.isFinite(number) ? number : fallback; }
    function clampPrintedNoteFontSize(value) { const parsed = Number(value || 0); if (!Number.isFinite(parsed)) return 24; return Math.max(24, Math.min(38, parsed)); }
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
        if (element.type === "text") { const position = point(element.position); const fontSize = clampPrintedNoteFontSize(element.font_size || element.fontSize || 24); return position ? `<text data-dco-readable-note="1" x="${position.x}" y="${position.y}" direction="rtl" unicode-bidi="plaintext" text-anchor="end" font-family="Tahoma,Arial,sans-serif" font-size="${fontSize}" font-weight="700" fill="${color(element.style && element.style.color, "#9a4b00")}" paint-order="stroke" stroke="#fff" stroke-width="3">${esc(element.text)}</text>` : ""; }
        return "";
    }
    function referenceCrop(reference) {
        const raw = reference && reference.crop && typeof reference.crop === "object" ? reference.crop : {};
        const x = Math.max(0, Math.min(.98, finite(raw.x)));
        const y = Math.max(0, Math.min(.98, finite(raw.y)));
        return {
            x,
            y,
            width: Math.max(.02, Math.min(1 - x, finite(raw.width, 1))),
            height: Math.max(.02, Math.min(1 - y, finite(raw.height, 1))),
        };
    }
    function referenceLayout(reference, width, height) {
        if (!reference) return null;
        const crop = referenceCrop(reference);
        const rawSize = reference.imageSize && typeof reference.imageSize === "object" ? reference.imageSize : {};
        const pixelWidth = finite(rawSize.widthPx);
        const pixelHeight = finite(rawSize.heightPx);
        const hasImageSize = pixelWidth > 0 && pixelHeight > 0;
        let destinationWidth = width;
        let destinationHeight = height;
        if (hasImageSize) {
            const sourceWidth = pixelWidth * crop.width;
            const sourceHeight = pixelHeight * crop.height;
            const ratio = Math.min(width / sourceWidth, height / sourceHeight);
            destinationWidth = sourceWidth * ratio;
            destinationHeight = sourceHeight * ratio;
        }
        const centerX = width / 2;
        const centerY = height / 2;
        const x = centerX - destinationWidth / 2;
        const y = centerY - destinationHeight / 2;
        const rotation = Math.max(-360, Math.min(360, finite(reference.rotationDeg)));
        const angle = rotation * Math.PI / 180;
        const rotatedWidth = Math.abs(destinationWidth * Math.cos(angle)) + Math.abs(destinationHeight * Math.sin(angle));
        const rotatedHeight = Math.abs(destinationWidth * Math.sin(angle)) + Math.abs(destinationHeight * Math.cos(angle));
        return {
            crop,
            imageSize: hasImageSize ? { widthPx: pixelWidth, heightPx: pixelHeight } : null,
            destination: { x, y, width: destinationWidth, height: destinationHeight },
            rotation,
            center: { x: centerX, y: centerY },
            bounds: {
                minX: centerX - rotatedWidth / 2,
                minY: centerY - rotatedHeight / 2,
                maxX: centerX + rotatedWidth / 2,
                maxY: centerY + rotatedHeight / 2,
            },
        };
    }
    function referenceMarkup(reference, width, height, layout = referenceLayout(reference, width, height)) {
        if (!layout || !String(reference.fileUrl || "").startsWith("/private/files/")) return "";
        const crop = layout.crop;
        const destination = layout.destination;
        const transform = `rotate(${layout.rotation} ${layout.center.x} ${layout.center.y})`;
        const cropped = crop.x > .000001 || crop.y > .000001 || crop.width < .999999 || crop.height < .999999;
        if (cropped && layout.imageSize) {
            const viewX = crop.x * layout.imageSize.widthPx;
            const viewY = crop.y * layout.imageSize.heightPx;
            const viewWidth = crop.width * layout.imageSize.widthPx;
            const viewHeight = crop.height * layout.imageSize.heightPx;
            return `<svg class="dco-reference-crop" data-reference-crop="1" data-reference-fit="visible-content" x="${destination.x}" y="${destination.y}" width="${destination.width}" height="${destination.height}" viewBox="${viewX} ${viewY} ${viewWidth} ${viewHeight}" preserveAspectRatio="xMidYMid meet" overflow="hidden" style="overflow:hidden" opacity="1" transform="${transform}"><image href="${esc(reference.fileUrl)}" x="0" y="0" width="${layout.imageSize.widthPx}" height="${layout.imageSize.heightPx}" preserveAspectRatio="none"/></svg>`;
        }
        const fitAttribute = layout.imageSize ? ' data-reference-fit="visible-content"' : "";
        return `<image href="${esc(reference.fileUrl)}" x="${destination.x}" y="${destination.y}" width="${destination.width}" height="${destination.height}" preserveAspectRatio="xMidYMid meet" opacity="1"${fitAttribute} transform="${transform}"/>`;
    }
    function elementBounds(element) {
        if (!element || typeof element !== "object") return null; let points = [];
        if (element.type === "stroke") points = element.points || [];
        else if (["line", "arrow", "dimension"].includes(element.type)) points = [element.start, element.end];
        else if (["rect", "ellipse"].includes(element.type)) points = [
            { xMm: element.xMm, yMm: element.yMm },
            { xMm: finite(element.xMm) + Math.max(0, finite(element.widthMm)), yMm: finite(element.yMm) + Math.max(0, finite(element.heightMm)) },
        ];
        else if (element.type === "text") points = [element.position, { xMm: finite(element.position && element.position.xMm) + 120, yMm: finite(element.position && element.position.yMm) + 40 }];
        const valid = points.map(point).filter(Boolean); if (!valid.length) return null;
        return { minX: Math.min(...valid.map(item => item.x)), maxX: Math.max(...valid.map(item => item.x)), minY: Math.min(...valid.map(item => item.y)), maxY: Math.max(...valid.map(item => item.y)) };
    }
    function documentationBounds(payload, width, height, layout = referenceLayout(payload.reference, width, height)) {
        const values = (payload.elements || []).map(elementBounds).filter(Boolean);
        if (layout) values.push(layout.bounds);
        if (!values.length) values.push({ minX: 0, minY: 0, maxX: width, maxY: height });
        const bounds = {
            minX: Math.min(...values.map(value => value.minX)), maxX: Math.max(...values.map(value => value.maxX)),
            minY: Math.min(...values.map(value => value.minY)), maxY: Math.max(...values.map(value => value.maxY)),
        };
        const padding = Math.max(20, Math.max(bounds.maxX - bounds.minX, bounds.maxY - bounds.minY) * .04);
        return { x: bounds.minX - padding, y: bounds.minY - padding, width: Math.max(1, bounds.maxX - bounds.minX) + padding * 2, height: Math.max(1, bounds.maxY - bounds.minY) + padding * 2 };
    }
    function documentationSvg(payload, label) {
        const width = Math.max(1, finite(payload.canvas && payload.canvas.widthMm, 800)), height = Math.max(1, finite(payload.canvas && payload.canvas.heightMm, 2100)), layout = referenceLayout(payload.reference, width, height), view = documentationBounds(payload, width, height, layout); sequence += 1; const markerId = `dco-doc-arrow-${sequence}`;
        const elements = (payload.elements || []).map(item => documentationElement(item, markerId)).join("");
        return `<svg viewBox="${view.x} ${view.y} ${view.width} ${view.height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${esc(label)}"><defs>${arrowHead(markerId, "#173c75")}</defs><rect x="${view.x}" y="${view.y}" width="${view.width}" height="${view.height}" fill="#fff"/>${referenceMarkup(payload.reference, width, height, layout)}${elements}</svg>`;
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
    const css = `.dco-piece-notes{display:flex;flex-direction:column;gap:4px;align-items:stretch;text-align:right}.dco-piece-notes-text{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.45}.dco-piece-sketch{display:block;margin:0;padding:4px;border:1px solid #aeb7bf;border-radius:4px;background:#fff;break-inside:avoid;page-break-inside:avoid}.dco-piece-sketch>svg{display:block;width:100%;height:68px;max-width:155px;margin:0 auto;overflow:visible;shape-rendering:geometricPrecision}.dco-piece-sketch .dco-reference-crop{overflow:hidden}.dco-piece-sketch figcaption{margin-top:2px;color:#344054;font-size:7px;font-weight:700;text-align:center}.dco-piece-sketch p{margin:3px 0 0;font-size:7px;line-height:1.35;white-space:pre-wrap}.dco-piece-sketch em{display:block;margin-top:3px;color:#92400e;font-size:6px;font-style:normal;text-align:center}tr.dco-row-with-sketch{break-inside:avoid;page-break-inside:avoid}td.dco-notes-has-sketch{min-width:38mm}`;
    window.AlmdinaShapePrint = Object.freeze({ parse: shapeOutput.parseDrawing, drawingPayload: shapeOutput.drawingFromPiece, geometryPayload: shapeOutput.geometryFromPiece, hasVisual: shapeOutput.hasVisual, svg, notesCell, css });
})();
