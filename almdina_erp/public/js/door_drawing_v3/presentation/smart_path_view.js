(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const Base = root.ShapeView;
    const G = root.Geometry;
    const D = root.DocumentModel;
    if (!Base || !G || !D || !G.path) throw new Error("Door Drawing V3 canvas policy and smart path domain must load first");

    function esc(value) {
        const text = String(value ?? "");
        if (window.frappe && frappe.utils && frappe.utils.escape_html) return frappe.utils.escape_html(text);
        return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }
    function fmt(value, precision = 1) { return String(G.roundMm(value, precision)); }

    function penIcon() {
        return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 19l3.3-1 9.8-9.8-2.3-2.3L6 15.7 5 19zm9.7-14.2l2.3 2.3 1.1-1.1a1.6 1.6 0 000-2.3l-.1-.1a1.6 1.6 0 00-2.3 0l-1 1.2z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><circle cx="6" cy="18" r="1.5" fill="currentColor"/></svg>';
    }

    function ensurePenButton(c) {
        if (!c || !c.root || c.readOnly) return null;
        const toolbar = c.root.querySelector(".ddv3-toolbar");
        if (!toolbar) return null;
        let button = toolbar.querySelector('[data-ddv3-tool="pen"]');
        if (!button) {
            button = document.createElement("button");
            button.type = "button";
            button.dataset.ddv3Tool = "pen";
            button.setAttribute("aria-label", "القلم الذكي");
            button.innerHTML = penIcon();
            const separator = toolbar.querySelector(".ddv3-separator");
            toolbar.insertBefore(button, separator || null);
        }
        button.title = "القلم الذكي P · اضغط واسحب للرسم الحر · يصحح الاهتزاز ويستقيم الخط ويتعرف على الأقواس والدوائر";
        button.classList.toggle("is-active", c.tool === "pen");
        return button;
    }

    function screenPoints(c, points) { return (points || []).map(point => Base.worldToScreen(c, point)); }
    function pathD(c, object) {
        const points = screenPoints(c, object.geometry.points);
        if (!points.length) return "";
        const commands = [`M ${points[0].x} ${points[0].y}`];
        for (let index = 1; index < points.length; index += 1) commands.push(`L ${points[index].x} ${points[index].y}`);
        if (object.geometry.closed) commands.push("Z");
        return commands.join(" ");
    }

    function segmentHitMarkup(c, object) {
        return G.pathSegments(object).map(segment => {
            const a = Base.worldToScreen(c, segment.start), b = Base.worldToScreen(c, segment.end);
            return `<line class="ddv3-object-hit ddv3-path-segment-hit" data-ddv3-object="${esc(object.id)}" data-ddv3-path-segment="${segment.index}" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke-width="${Base.OBJECT_HIT_STROKE_PX || 30}"/>`;
        }).join("");
    }

    function nodeMarkup(c, object) {
        if (String(c.nodeEditId || "") !== String(object.id)) return "";
        return object.geometry.points.map((point, index) => {
            const p = Base.worldToScreen(c, point);
            const selected = Number(c.selectedNodeIndex) === index ? " is-selected" : "";
            return `<g class="ddv3-path-node${selected}" data-ddv3-path-node="${index}" data-ddv3-object="${esc(object.id)}"><circle class="ddv3-path-node-hit" cx="${p.x}" cy="${p.y}" r="11"/><rect class="ddv3-path-node-dot" x="${p.x - 4}" y="${p.y - 4}" width="8" height="8" rx="1"/></g>`;
        }).join("");
    }

    function objectMarkup(c, object, selected) {
        const d = pathD(c, object);
        return `<g class="ddv3-path-object${selected ? " is-selected" : ""}" data-ddv3-path-object="${esc(object.id)}">${segmentHitMarkup(c, object)}<path class="ddv3-path-stroke${selected ? " is-selected" : ""}" data-ddv3-object="${esc(object.id)}" d="${d}"/>${nodeMarkup(c, object)}</g>`;
    }

    function draftMarkup(c) {
        const draft = c.penDraft;
        if (!draft || !Array.isArray(draft.points) || !draft.points.length) return "";
        const points = draft.freehand ? draft.points.slice() : [...draft.points];
        if (!draft.freehand && draft.pointer && (!points.length || G.distance(points[points.length - 1], draft.pointer) >= G.EPSILON_MM)) points.push(draft.pointer);
        const screen = screenPoints(c, points);
        const d = screen.length ? [`M ${screen[0].x} ${screen[0].y}`, ...screen.slice(1).map(p => `L ${p.x} ${p.y}`)].join(" ") : "";
        if (draft.freehand) {
            const first = screen[0];
            const last = screen[screen.length - 1] || first;
            const closeClass = draft.closeReady ? " is-close-ready" : "";
            const closeLabel = draft.closeReady ? `<text class="ddv3-pen-close-label" x="${first.x + 12}" y="${first.y - 12}">إغلاق</text>` : "";
            return `<g class="ddv3-pen-draft is-freehand"><path d="${d}"/><circle class="ddv3-pen-draft-node${closeClass}" cx="${first.x}" cy="${first.y}" r="${draft.closeReady ? 6 : 3.5}"/><circle class="ddv3-freehand-tip" cx="${last.x}" cy="${last.y}" r="2.5"/>${closeLabel}</g>`;
        }
        const nodes = draft.points.map((point, index) => {
            const p = Base.worldToScreen(c, point);
            const first = index === 0 && draft.closeReady ? " is-close-ready" : "";
            return `<circle class="ddv3-pen-draft-node${first}" cx="${p.x}" cy="${p.y}" r="${first ? 6 : 3.5}"/>`;
        }).join("");
        const first = Base.worldToScreen(c, draft.points[0]);
        const closeLabel = draft.closeReady ? `<text class="ddv3-pen-close-label" x="${first.x + 12}" y="${first.y - 12}">إغلاق</text>` : "";
        return `<g class="ddv3-pen-draft"><path d="${d}"/>${nodes}${closeLabel}</g>`;
    }

    function insertPathLayer(c, markup) {
        if (!markup) return;
        const marker = c.canvas.querySelector(".ddv3-snap-axis-guide, .ddv3-snap-indicator");
        if (marker) marker.insertAdjacentHTML("beforebegin", markup);
        else c.canvas.insertAdjacentHTML("beforeend", markup);
    }

    function renderPathInspector(c, object) {
        if (!object || object.type !== G.PATH_TYPE) return;
        const nodeIndex = Number.isInteger(c.selectedNodeIndex) ? c.selectedNodeIndex : null;
        const node = nodeIndex != null ? object.geometry.points[nodeIndex] : null;
        const locked = c.readOnly ? " disabled" : "";
        const nodeSection = node ? `<section class="ddv3-panel-section"><div class="ddv3-section-title">النقطة ${nodeIndex + 1}</div><div class="ddv3-field-grid"><label class="ddv3-field"><span>X</span><div><input type="number" step="0.1" value="${fmt(node.x, 3)}" data-ddv3-path-node-prop="x"${locked}><b>mm</b></div></label><label class="ddv3-field"><span>Y</span><div><input type="number" step="0.1" value="${fmt(node.y, 3)}" data-ddv3-path-node-prop="y"${locked}><b>mm</b></div></label></div></section>` : "";
        c.inspector.innerHTML = `<section class="ddv3-panel-section"><div class="ddv3-panel-title"><strong>المسار</strong><span>⋯</span></div></section><section class="ddv3-panel-section"><div class="ddv3-section-title">الهندسة</div><div class="ddv3-path-stats"><span>النقاط <b>${object.geometry.points.length}</b></span><span>الطول <b>${fmt(G.pathLength(object), 3)} mm</b></span><span>الحالة <b>${object.geometry.closed ? "مغلق" : "مفتوح"}</b></span></div>${c.readOnly ? "" : `<button type="button" class="ddv3-path-toggle" data-ddv3-path-toggle>${object.geometry.closed ? "فتح المسار" : "إغلاق المسار"}</button>`}</section>${nodeSection}<section class="ddv3-panel-section ddv3-path-help" dir="rtl"><div class="ddv3-section-title">تعديل النقاط</div><p>انقر مرتين على المسار للدخول إلى وضع النقاط. اسحب نقطة لتحريكها، وانقر مرتين على ضلع لإضافة نقطة جديدة.</p></section>`;
    }

    function displayPath(c) {
        const object = c.previewObject && String(c.previewObject.id) === String(c.selectedId)
            ? c.previewObject
            : D.objectById(c.history.current(), c.selectedId);
        return object && object.type === G.PATH_TYPE ? object : null;
    }

    function render(c) {
        const result = Base.render(c);
        ensurePenButton(c);
        const doc = c.history.current();
        const pathMarkup = doc.objects.filter(object => object.type === G.PATH_TYPE).map(item => {
            const object = c.previewObject && String(c.previewObject.id) === String(item.id) ? c.previewObject : item;
            return objectMarkup(c, object, String(item.id) === String(c.selectedId));
        }).join("");
        insertPathLayer(c, pathMarkup + draftMarkup(c));
        renderPathInspector(c, displayPath(c));
        c.canvas.dataset.tool = c.tool;
        c.canvas.style.cursor = c.spaceHeld ? "grab" : (c.tool === "select" ? "default" : "crosshair");
        return result;
    }

    root.ShapeView = Object.freeze({ ...Base, render, ensurePenButton, pathD, renderPathInspector });
    root.SmartPathView = Object.freeze({ ensurePenButton, pathD, objectMarkup, draftMarkup, renderPathInspector });
})();
