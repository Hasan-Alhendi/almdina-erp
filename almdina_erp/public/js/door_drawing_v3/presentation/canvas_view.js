(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    const D = root.DocumentModel;
    if (!G || !D) throw new Error("Door Drawing V3 domain must load before canvas view");

    const MIN_SCALE = 0.02;
    const MAX_SCALE = 20;
    const HIT_PX = 14;

    function esc(value) {
        const text = String(value ?? "");
        if (window.frappe && frappe.utils && frappe.utils.escape_html) return frappe.utils.escape_html(text);
        return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

    function fmt(value, precision = 1) { return String(G.roundMm(value, precision)); }

    function icon(name) {
        const map = {
            select: '<svg viewBox="0 0 24 24"><path d="M5 3l12.4 8.2-6 1.5 3.2 6.2-2.3 1.2-3.1-6.1L5 18V3z" fill="currentColor"/></svg>',
            line: '<svg viewBox="0 0 24 24"><path d="M5 19L19 5" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>',
            rectangle: '<svg viewBox="0 0 24 24"><rect x="5" y="6" width="14" height="12" fill="none" stroke="currentColor" stroke-width="1.7"/></svg>',
            circle: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="7" fill="none" stroke="currentColor" stroke-width="1.7"/></svg>',
            arc: '<svg viewBox="0 0 24 24"><path d="M5 17A10 10 0 0018 6" fill="none" stroke="currentColor" stroke-width="1.7"/></svg>',
            undo: '<svg viewBox="0 0 24 24"><path d="M9 7L5 11l4 4M6 11h7a5 5 0 010 10" fill="none" stroke="currentColor" stroke-width="1.7"/></svg>',
            redo: '<svg viewBox="0 0 24 24"><path d="M15 7l4 4-4 4m3-4h-7a5 5 0 000 10" fill="none" stroke="currentColor" stroke-width="1.7"/></svg>',
            close: '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>',
        };
        return map[name] || "";
    }

    function shell(row, readOnly) {
        const widthMm = Math.max(0, G.number(row && row.width_cm) * 10);
        const heightMm = Math.max(0, G.number(row && row.length_cm) * 10);
        const pieceNo = row && (row.idx || row.piece_no || "");
        const tools = readOnly ? "" : `<nav class="ddv3-toolbar" aria-label="أدوات الرسم">
            <button type="button" data-ddv3-tool="select" title="تحديد V">${icon("select")}</button>
            <button type="button" data-ddv3-tool="line" title="مستقيم L · Shift أفقي/عمودي">${icon("line")}</button>
            <button type="button" data-ddv3-tool="rectangle" title="مستطيل R · Shift للمربع">${icon("rectangle")}</button>
            <button type="button" data-ddv3-tool="circle" title="دائرة O">${icon("circle")}</button>
            <button type="button" data-ddv3-tool="arc" title="قوس A · المركز ثم نصف القطر ثم نهاية القوس">${icon("arc")}</button>
            <span class="ddv3-separator"></span>
            <button type="button" data-ddv3-undo title="تراجع Ctrl+Z">${icon("undo")}</button>
            <button type="button" data-ddv3-redo title="إعادة Ctrl+Shift+Z">${icon("redo")}</button>
        </nav>`;
        return `<div class="ddv3-app${readOnly ? " is-readonly" : ""}" dir="ltr">
            <header class="ddv3-topbar"><div class="ddv3-top-left"><button type="button" class="ddv3-icon-button" data-ddv3-close>${icon("close")}</button></div>
            <div class="ddv3-title" dir="rtl">رسم الدرفة الخاصة رقم ${esc(pieceNo)}</div>
            <div class="ddv3-top-right"><span class="ddv3-size">${fmt(widthMm)} × ${fmt(heightMm)} mm</span>${readOnly ? "" : '<button type="button" class="ddv3-save" data-ddv3-save>حفظ</button>'}</div></header>
            <div class="ddv3-body"><main class="ddv3-workspace"><svg class="ddv3-canvas" xmlns="http://www.w3.org/2000/svg"></svg>${tools}
            <div class="ddv3-zoom"><button type="button" data-ddv3-zoom-out>−</button><button type="button" class="ddv3-zoom-value" data-ddv3-zoom-reset>100%</button><button type="button" data-ddv3-zoom-in>+</button></div></main>
            <aside class="ddv3-inspector" dir="ltr"><div class="ddv3-inspector-tabs"><span class="is-active">Design</span></div><div class="ddv3-inspector-content" data-ddv3-inspector></div></aside></div></div>`;
    }

    function viewport(canvas, doc) {
        const rect = canvas.getBoundingClientRect();
        const rw = Math.max(1200, doc.blank.widthMm || 0);
        const rh = Math.max(900, doc.blank.heightMm || 0);
        const scale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, Math.min(Math.max(300, rect.width - 160) / rw, Math.max(240, rect.height - 160) / rh)));
        return { scale, baseScale: scale, offsetX: rect.width / 2 - rw * scale / 2, offsetY: rect.height / 2 + rh * scale / 2, widthPx: rect.width, heightPx: rect.height };
    }

    function worldToScreen(c, p) { return { x: c.viewport.offsetX + G.number(p && p.x) * c.viewport.scale, y: c.viewport.offsetY - G.number(p && p.y) * c.viewport.scale }; }
    function screenToWorld(c, x, y) { return G.point((x - c.viewport.offsetX) / c.viewport.scale, (c.viewport.offsetY - y) / c.viewport.scale); }
    function localPoint(c, event) { const r = c.canvas.getBoundingClientRect(); return { x: event.clientX - r.left, y: event.clientY - r.top }; }
    function eventWorld(c, event) { const p = localPoint(c, event); return screenToWorld(c, p.x, p.y); }

    function measure(x, y, text, selected) {
        const w = Math.max(44, String(text).length * 6.2 + 12);
        return `<g class="ddv3-measure${selected ? " is-selected" : ""}" transform="translate(${x} ${y})"><rect x="${-w / 2}" y="-9" width="${w}" height="18" rx="3"></rect><text x="0" y="0">${esc(text)}</text></g>`;
    }

    function arcPath(c, object) {
        const start = worldToScreen(c, G.arcStart(object));
        const end = worldToScreen(c, G.arcEnd(object));
        const r = object.geometry.radiusMm * c.viewport.scale;
        const large = Math.abs(object.geometry.sweepAngleDeg) > 180 ? 1 : 0;
        const sweep = object.geometry.sweepAngleDeg > 0 ? 0 : 1;
        return `M ${start.x} ${start.y} A ${r} ${r} 0 ${large} ${sweep} ${end.x} ${end.y}`;
    }

    function objectMarkup(c, object, selected = false, draft = false) {
        const cls = `ddv3-line${selected ? " is-selected" : ""}${draft ? " is-draft" : ""}`;
        const data = draft ? "" : ` data-ddv3-object="${esc(object.id)}"`;
        const hit = draft ? "" : "ddv3-object-hit";
        const out = [];
        if (object.type === "line") {
            const a = worldToScreen(c, object.geometry.start), b = worldToScreen(c, object.geometry.end);
            if (!draft) out.push(`<line class="${hit}"${data} x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke-width="${HIT_PX}"/>`);
            out.push(`<line class="${cls}"${data} x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"/>`);
            if (selected || draft) out.push(measure((a.x + b.x) / 2, (a.y + b.y) / 2 + 18, `${fmt(G.lineLength(object), 3)} mm`, selected));
            if (selected) for (const [role, p] of [["start", a], ["end", b]]) out.push(`<g data-ddv3-handle="${role}" class="ddv3-handle"><circle cx="${p.x}" cy="${p.y}" r="10" class="ddv3-handle-hit"/><rect x="${p.x - 3}" y="${p.y - 3}" width="6" height="6" class="ddv3-handle-square"/></g>`);
        } else if (object.type === "rectangle") {
            const g = object.geometry, p = worldToScreen(c, g.origin), w = g.widthMm * c.viewport.scale, h = g.heightMm * c.viewport.scale;
            if (!draft) out.push(`<rect class="${hit}"${data} x="${p.x}" y="${p.y - h}" width="${w}" height="${h}" stroke-width="${HIT_PX}"/>`);
            out.push(`<rect class="${cls}"${data} x="${p.x}" y="${p.y - h}" width="${w}" height="${h}"/>`);
            if (selected || draft) out.push(measure(p.x + w / 2, p.y - h / 2, `${fmt(g.widthMm, 3)} × ${fmt(g.heightMm, 3)} mm`, selected));
        } else if (object.type === "circle") {
            const g = object.geometry, p = worldToScreen(c, g.center), r = g.radiusMm * c.viewport.scale;
            if (!draft) out.push(`<circle class="${hit}"${data} cx="${p.x}" cy="${p.y}" r="${r}" stroke-width="${HIT_PX}"/>`);
            out.push(`<circle class="${cls}"${data} cx="${p.x}" cy="${p.y}" r="${r}"/>`);
            if (selected || draft) out.push(measure(p.x, p.y + r + 18, `Ø ${fmt(g.radiusMm * 2, 3)} mm`, selected));
        } else if (object.type === "arc") {
            const path = arcPath(c, object), mid = worldToScreen(c, G.arcMid(object));
            if (!draft) out.push(`<path class="${hit}"${data} d="${path}" stroke-width="${HIT_PX}"/>`);
            out.push(`<path class="${cls}"${data} d="${path}"/>`);
            if (selected || draft) out.push(measure(mid.x, mid.y + 18, `R ${fmt(object.geometry.radiusMm, 3)} · L ${fmt(G.arcLength(object), 3)} mm`, selected));
        }
        return out.join("");
    }

    function snapMarkup(c) {
        const state = c.snapState;
        if (!state || !state.point) return "";
        const p = worldToScreen(c, state.point);
        const out = [];
        if (state.axis === "horizontal") out.push(`<line class="ddv3-snap-axis-guide" x1="0" y1="${p.y}" x2="${Math.max(0, c.viewport.widthPx)}" y2="${p.y}"/>`);
        if (state.axis === "vertical") out.push(`<line class="ddv3-snap-axis-guide" x1="${p.x}" y1="0" x2="${p.x}" y2="${Math.max(0, c.viewport.heightPx)}"/>`);
        if (state.snapped) {
            const role = state.target && state.target.role ? ` data-ddv3-snap-role="${esc(state.target.role)}"` : "";
            out.push(`<g class="ddv3-snap-indicator" transform="translate(${p.x} ${p.y})"${role}><circle r="6"></circle><path d="M -9 0 H 9 M 0 -9 V 9"></path></g>`);
        }
        return out.join("");
    }

    function field(label, key, value, suffix, disabled = false) { return `<label class="ddv3-field"><span>${esc(label)}</span><div><input type="number" step="0.1" value="${esc(value)}" data-ddv3-prop="${esc(key)}"${disabled ? " disabled" : ""}><b>${esc(suffix || "")}</b></div></label>`; }
    function grid(...fields) { return `<div class="ddv3-field-grid${fields.length === 1 ? " is-single" : ""}">${fields.join("")}</div>`; }
    function section(title, body) { return `<section class="ddv3-panel-section"><div class="ddv3-section-title">${esc(title)}</div>${body}</section>`; }

    function renderInspector(c) {
        const object = D.objectById(c.history.current(), c.selectedId);
        if (!object) { c.inspector.innerHTML = `<div class="ddv3-empty" dir="rtl"><b>الخصائص</b><span>${c.tool === "arc" ? "القوس: انقر المركز ثم نقطة نصف القطر ثم نهاية القوس." : "حدد عنصرًا لتعديل أبعاده وموقعه بدقة بالميليمتر. النقاط تنجذب تلقائيًا عند الاقتراب منها."}</span></div>`; return; }
        const g = object.geometry;
        let html = `<section class="ddv3-panel-section"><div class="ddv3-panel-title"><strong>${esc(object.type[0].toUpperCase() + object.type.slice(1))}</strong><span>⋯</span></div></section>`;
        if (object.type === "line") html += section("Position", grid(field("X", "x", fmt(g.start.x, 3), "mm"), field("Y", "y", fmt(g.start.y, 3), "mm")) + grid(field("Rotation", "angle", fmt(G.lineAngle(object), 2), "°"))) + section("Dimensions", grid(field("Length", "length", fmt(G.lineLength(object), 3), "mm")));
        if (object.type === "rectangle") html += section("Position", grid(field("X", "x", fmt(g.origin.x, 3), "mm"), field("Y", "y", fmt(g.origin.y, 3), "mm"))) + section("Dimensions", grid(field("Width", "width", fmt(g.widthMm, 3), "mm"), field("Height", "height", fmt(g.heightMm, 3), "mm")));
        if (object.type === "circle") html += section("Center", grid(field("X", "cx", fmt(g.center.x, 3), "mm"), field("Y", "cy", fmt(g.center.y, 3), "mm"))) + section("Dimensions", grid(field("Radius", "radius", fmt(g.radiusMm, 3), "mm"), field("Diameter", "diameter", fmt(g.radiusMm * 2, 3), "mm")));
        if (object.type === "arc") html += section("Center", grid(field("X", "cx", fmt(g.center.x, 3), "mm"), field("Y", "cy", fmt(g.center.y, 3), "mm"))) + section("Arc", grid(field("Radius", "radius", fmt(g.radiusMm, 3), "mm"), field("Length", "arcLength", fmt(G.arcLength(object), 3), "mm", true)) + grid(field("Start", "startAngle", fmt(g.startAngleDeg, 2), "°"), field("Sweep", "sweep", fmt(g.sweepAngleDeg, 2), "°")));
        c.inspector.innerHTML = html;
        if (c.readOnly) c.inspector.querySelectorAll("input").forEach(input => input.disabled = true);
    }

    function render(c) {
        const doc = c.history.current();
        const previewId = c.previewObject && c.previewObject.id;
        const gridSize = Math.max(8, 50 * c.viewport.scale);
        const gx = ((c.viewport.offsetX % gridSize) + gridSize) % gridSize, gy = ((c.viewport.offsetY % gridSize) + gridSize) % gridSize;
        const parts = [`<defs><pattern id="ddv3-grid-small" width="${gridSize}" height="${gridSize}" patternUnits="userSpaceOnUse" x="${gx}" y="${gy}"><path d="M ${gridSize} 0 L 0 0 0 ${gridSize}" fill="none" stroke="#d8d8d8" stroke-width="0.65"/></pattern></defs><rect width="100%" height="100%" class="ddv3-canvas-bg"/><rect width="100%" height="100%" fill="url(#ddv3-grid-small)" pointer-events="none"/>`];
        doc.objects.forEach(item => { const object = previewId === item.id ? c.previewObject : item; parts.push(objectMarkup(c, object, String(item.id) === String(c.selectedId), false)); });
        if (c.draftObject) parts.push(objectMarkup(c, c.draftObject, false, true));
        if (c.arcDraft && c.arcDraft.center && c.arcDraft.pointer) { const a = worldToScreen(c, c.arcDraft.center), b = worldToScreen(c, c.arcDraft.pointer); parts.push(`<line class="ddv3-line is-draft" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"/>`); }
        parts.push(snapMarkup(c));
        c.canvas.innerHTML = parts.join("");
        c.canvas.dataset.tool = c.tool;
        c.canvas.style.cursor = c.spaceHeld ? "grab" : (c.tool === "select" ? "default" : "crosshair");
        c.root.querySelectorAll("[data-ddv3-tool]").forEach(button => button.classList.toggle("is-active", button.dataset.ddv3Tool === c.tool));
        const undo = c.root.querySelector("[data-ddv3-undo]"), redo = c.root.querySelector("[data-ddv3-redo]"); if (undo) undo.disabled = !c.history.canUndo(); if (redo) redo.disabled = !c.history.canRedo();
        const zoom = c.root.querySelector("[data-ddv3-zoom-reset]"); if (zoom) zoom.textContent = `${Math.round(c.viewport.scale / c.viewport.baseScale * 100)}%`;
        renderInspector(c);
    }

    root.ShapeView = Object.freeze({ MIN_SCALE, MAX_SCALE, shell, viewport, worldToScreen, screenToWorld, localPoint, eventWorld, render, renderInspector, arcPath, snapMarkup });
})();
