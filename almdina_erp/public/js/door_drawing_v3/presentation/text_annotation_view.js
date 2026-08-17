(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const Base = root.ShapeView;
    const G = root.Geometry;
    const D = root.DocumentModel;
    if (!Base || !G || !D || !G.TEXT_TYPE) throw new Error("Text annotation domain must load before text annotation view");

    function esc(value) {
        const text = String(value ?? "");
        if (window.frappe && frappe.utils && frappe.utils.escape_html) return frappe.utils.escape_html(text);
        return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\"/g, "&quot;");
    }

    function fmt(value, precision = 1) { return String(G.roundMm(value, precision)); }
    function isRtl(text) { return /[\u0590-\u08ff]/.test(String(text || "")); }

    function textIcon() {
        return '<svg viewBox="0 0 24 24"><path d="M6 5h12M12 5v14M8.5 19h7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';
    }

    function shell(row, readOnly) {
        const html = Base.shell(row, readOnly);
        if (readOnly || html.includes('data-ddv3-tool="text"')) return html;
        const button = `<button type="button" data-ddv3-tool="text" title="نص T · انقر ثم اكتب مباشرة">${textIcon()}</button>`;
        return html.replace('<span class="ddv3-separator"></span>', `${button}<span class="ddv3-separator"></span>`);
    }

    function selectedText(c) {
        const object = D.objectById(c.history.current(), c.selectedId);
        return object && object.type === G.TEXT_TYPE ? object : null;
    }

    function lineTspans(object, x, y, fontSizePx) {
        const lines = String(object.text || "").split("\n");
        const rtl = isRtl(object.text);
        const anchor = rtl ? "end" : "start";
        const direction = rtl ? "rtl" : "ltr";
        return `<text x="${x}" y="${y}" text-anchor="${anchor}" direction="${direction}" unicode-bidi="plaintext">${lines.map((line, index) => `<tspan x="${x}" dy="${index === 0 ? 0 : fontSizePx * 1.25}">${esc(line || " ")}</tspan>`).join("")}</text>`;
    }

    function textMarkup(c, object, selected) {
        const p = Base.worldToScreen(c, object.geometry.position);
        const fontSizePx = Math.max(6, object.style.fontSizeMm * c.viewport.scale);
        const lines = String(object.text || "").split("\n");
        const longest = Math.max(1, ...lines.map(line => line.length));
        const width = Math.max(fontSizePx, longest * fontSizePx * 0.58);
        const height = Math.max(fontSizePx, lines.length * fontSizePx * 1.25);
        const rtl = isRtl(object.text);
        const left = rtl ? p.x - width : p.x;
        const top = p.y - fontSizePx;
        const selection = selected ? `<rect class="ddv3-text-selection" x="${left - 5}" y="${top - 5}" width="${width + 10}" height="${height + 10}" rx="3"/>` : "";
        const hit = `<rect class="ddv3-text-hit" data-ddv3-object="${esc(object.id)}" x="${left - 8}" y="${top - 8}" width="${width + 16}" height="${height + 16}"/>`;
        const visible = lineTspans(object, p.x, p.y, fontSizePx).replace("<text ", `<text class="ddv3-text-object${selected ? " is-selected" : ""}" data-ddv3-object="${esc(object.id)}" fill="${esc(object.style.fill)}" font-size="${fontSizePx}" font-weight="${esc(object.style.fontWeight)}" `);
        return `<g class="ddv3-text-annotation" data-ddv3-text-id="${esc(object.id)}">${hit}${selection}${visible}</g>`;
    }

    function textInspector(c, object) {
        const g = object.geometry, style = object.style;
        const disabled = c.readOnly ? " disabled" : "";
        c.inspector.innerHTML = `<section class="ddv3-panel-section"><div class="ddv3-panel-title"><strong>Text</strong><span>⋯</span></div></section>
            <section class="ddv3-panel-section"><div class="ddv3-section-title">النص</div><textarea class="ddv3-text-inspector-input" data-ddv3-text-prop="text" rows="4"${disabled}>${esc(object.text)}</textarea></section>
            <section class="ddv3-panel-section"><div class="ddv3-section-title">الموقع</div><div class="ddv3-field-grid"><label class="ddv3-field"><span>X</span><div><input type="number" step="0.1" value="${fmt(g.position.x, 3)}" data-ddv3-text-prop="x"${disabled}><b>mm</b></div></label><label class="ddv3-field"><span>Y</span><div><input type="number" step="0.1" value="${fmt(g.position.y, 3)}" data-ddv3-text-prop="y"${disabled}><b>mm</b></div></label></div></section>
            <section class="ddv3-panel-section"><div class="ddv3-section-title">الخط</div><div class="ddv3-field-grid is-single"><label class="ddv3-field"><span>حجم الخط</span><div><input type="number" min="4" step="1" value="${fmt(style.fontSizeMm, 1)}" data-ddv3-text-prop="fontSizeMm"${disabled}><b>mm</b></div></label></div></section>`;
    }

    function render(c) {
        const result = Base.render(c);
        if (!c || !c.canvas) return result;
        const doc = c.history.current();
        const livePreview = c.previewObject && c.previewObject.type === G.TEXT_TYPE ? c.previewObject : null;
        const textObjects = doc.objects
            .filter(object => object.type === G.TEXT_TYPE)
            .map(object => livePreview && String(livePreview.id) === String(object.id) ? livePreview : object);
        if (textObjects.length) {
            const markup = textObjects.map(object => textMarkup(c, object, String(object.id) === String(c.selectedId))).join("");
            c.canvas.insertAdjacentHTML("beforeend", `<g class="ddv3-text-layer">${markup}</g>`);
        }
        const object = livePreview && String(livePreview.id) === String(c.selectedId) ? livePreview : selectedText(c);
        if (object) textInspector(c, object);
        return result;
    }

    function renderInspector(c) {
        const object = selectedText(c);
        if (object) return textInspector(c, object);
        return Base.renderInspector(c);
    }

    root.ShapeView = Object.freeze({ ...Base, shell, render, renderInspector, textMarkup, textInspector });
    root.TextAnnotationView = Object.freeze({ textMarkup, textInspector, isRtl });
})();
