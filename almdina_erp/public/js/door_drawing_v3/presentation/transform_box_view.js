(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    const Selection = root.VectorSelectionGeometry;
    const Base = root.ShapeView;
    if (!G || !Selection || !Base) throw new Error("Door Drawing V3 selection and shape view must load before transform box view");

    const SVG_NS = "http://www.w3.org/2000/svg";
    const HANDLE_ROLES = Object.freeze(["nw", "n", "ne", "e", "se", "s", "sw", "w"]);

    function svg(name, attributes = {}) {
        const element = document.createElementNS(SVG_NS, name);
        Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, String(value)));
        return element;
    }
    function fmt(value, precision = 2) { return String(G.roundMm(value, precision)); }
    function selectedIds(c) {
        const values = Array.isArray(c.selectedIds) && c.selectedIds.length ? c.selectedIds : (c.selectedId ? [c.selectedId] : []);
        return [...new Set(values.filter(Boolean).map(String))];
    }
    function selectedObjects(c) {
        const ids = new Set(selectedIds(c));
        return (c.history.current().objects || []).filter(object => ids.has(String(object.id)) && Selection.boundsOfObject(object));
    }
    function bounds(c) {
        if (c.transformPreviewBounds) return c.transformPreviewBounds;
        return Selection.unionBounds(selectedObjects(c));
    }
    function screenRect(c, box) {
        if (!box) return null;
        const a = Base.worldToScreen(c, G.point(box.left, box.top));
        const b = Base.worldToScreen(c, G.point(box.right, box.bottom));
        return Object.freeze({ x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), width: Math.abs(b.x - a.x), height: Math.abs(b.y - a.y) });
    }
    function handleWorld(box, role) {
        const x = role.includes("w") ? box.left : role.includes("e") ? box.right : box.cx;
        const y = role.includes("n") ? box.bottom : role.includes("s") ? box.top : box.cy;
        return G.point(x, y);
    }
    function screenMatrix(c, m) {
        const s = Number(c.viewport.scale || 1), ox = Number(c.viewport.offsetX || 0), oy = Number(c.viewport.offsetY || 0);
        return Object.freeze({
            a: m.a,
            b: -m.b,
            c: -m.c,
            d: m.d,
            e: ox - m.a * ox + m.c * oy + s * m.e,
            f: oy + m.b * ox - m.d * oy - s * m.f,
        });
    }
    function clearPreview(c) {
        c.canvas.querySelectorAll("[data-ddv3-transform-preview]").forEach(element => {
            element.removeAttribute("transform");
            delete element.dataset.ddv3TransformPreview;
        });
    }
    function applyPreview(c) {
        clearPreview(c);
        const preview = c.transformPreviewMatrix;
        if (!preview) return;
        const ids = new Set(selectedIds(c));
        if (!ids.size) return;
        const matrix = screenMatrix(c, preview);
        c.canvas.querySelectorAll("[data-ddv3-object]").forEach(element => {
            if (!ids.has(String(element.dataset.ddv3Object || ""))) return;
            element.setAttribute("transform", `matrix(${matrix.a} ${matrix.b} ${matrix.c} ${matrix.d} ${matrix.e} ${matrix.f})`);
            element.dataset.ddv3TransformPreview = "1";
        });
    }
    function ensureOverlay(c) {
        c.canvas.querySelectorAll(".ddv3-transform-overlay").forEach(element => element.remove());
        const box = bounds(c);
        const visible = Boolean(!c.readOnly && c.tool === "select" && !c.nodeEditId && box && selectedObjects(c).length);
        c.canvas.dataset.transformBox = visible ? "1" : "";
        if (!visible) return null;
        const rect = screenRect(c, box);
        if (!rect) return null;
        const layer = svg("g", { class: "ddv3-transform-overlay" });
        layer.appendChild(svg("rect", {
            class: "ddv3-transform-outline",
            x: rect.x,
            y: rect.y,
            width: Math.max(0.5, rect.width),
            height: Math.max(0.5, rect.height),
        }));
        HANDLE_ROLES.forEach(role => {
            const world = handleWorld(box, role), point = Base.worldToScreen(c, world);
            const group = svg("g", { class: `ddv3-transform-handle is-${role}`, "data-ddv3-transform-handle": role });
            group.appendChild(svg("rect", { class: "ddv3-transform-handle-hit", x: point.x - 11, y: point.y - 11, width: 22, height: 22 }));
            group.appendChild(svg("rect", { class: "ddv3-transform-handle-dot", x: point.x - 4, y: point.y - 4, width: 8, height: 8, rx: 1 }));
            layer.appendChild(group);
        });
        c.canvas.appendChild(layer);
        return layer;
    }
    function ensureContextBar(c) {
        const workspace = c.root.querySelector(".ddv3-workspace") || c.root;
        let bar = workspace.querySelector(".ddv3-transform-contextbar");
        if (!bar) {
            bar = document.createElement("div");
            bar.className = "ddv3-transform-contextbar";
            bar.dir = "rtl";
            workspace.appendChild(bar);
        }
        const box = bounds(c), count = selectedObjects(c).length;
        if (c.readOnly || c.tool !== "select" || c.nodeEditId || !box || !count) {
            bar.innerHTML = "";
            bar.classList.remove("is-visible");
            return bar;
        }
        bar.innerHTML = `<span class="ddv3-transform-context-summary">${count > 1 ? `${count} عناصر` : "تحويل"}</span>` +
            '<button type="button" data-ddv3-transform-action="flip-horizontal" title="انعكاس أفقي">↔ انعكاس</button>' +
            '<button type="button" data-ddv3-transform-action="flip-vertical" title="انعكاس عمودي">↕ انعكاس</button>';
        bar.classList.add("is-visible");
        return bar;
    }
    function ensureInspector(c) {
        if (!c.inspector) return;
        c.inspector.querySelectorAll(".ddv3-transform-inspector").forEach(element => element.remove());
        const box = bounds(c), count = selectedObjects(c).length;
        if (c.readOnly || c.tool !== "select" || c.nodeEditId || !box || !count) return;
        const widthDisabled = box.width < G.EPSILON_MM ? " disabled" : "";
        const heightDisabled = box.height < G.EPSILON_MM ? " disabled" : "";
        const section = document.createElement("section");
        section.className = "ddv3-panel-section ddv3-transform-inspector";
        section.dir = "ltr";
        section.innerHTML = `<div class="ddv3-section-title">Transform</div>
            <div class="ddv3-field-grid">
                <label class="ddv3-field"><span>X</span><div><input type="number" step="0.1" value="${fmt(box.left, 3)}" data-ddv3-transform-prop="x"><b>mm</b></div></label>
                <label class="ddv3-field"><span>Y</span><div><input type="number" step="0.1" value="${fmt(box.bottom, 3)}" data-ddv3-transform-prop="y"><b>mm</b></div></label>
            </div>
            <div class="ddv3-field-grid">
                <label class="ddv3-field"><span>W</span><div><input type="number" min="0.001" step="0.1" value="${fmt(box.width, 3)}" data-ddv3-transform-prop="width"${widthDisabled}><b>mm</b></div></label>
                <label class="ddv3-field"><span>H</span><div><input type="number" min="0.001" step="0.1" value="${fmt(box.height, 3)}" data-ddv3-transform-prop="height"${heightDisabled}><b>mm</b></div></label>
            </div>
            <p class="ddv3-transform-hint" dir="rtl">اسحب مقابض الإطار · Shift يحافظ على النسبة · Alt من المركز</p>`;
        c.inspector.insertBefore(section, c.inspector.firstChild);
    }
    function decorate(c) {
        if (!c || !c.canvas || c.__transformBoxDecorating) return;
        c.__transformBoxDecorating = true;
        try {
            applyPreview(c);
            ensureOverlay(c);
            ensureContextBar(c);
            ensureInspector(c);
        } finally {
            c.__transformBoxDecorating = false;
        }
    }
    function schedule(c) {
        if (!c || c.__transformBoxScheduled) return;
        c.__transformBoxScheduled = true;
        const run = () => { c.__transformBoxScheduled = false; decorate(c); };
        if (typeof requestAnimationFrame === "function") requestAnimationFrame(run); else setTimeout(run, 0);
    }
    function render(c) {
        const result = Base.render(c);
        decorate(c);
        return result;
    }

    root.ShapeView = Object.freeze({ ...Base, render });
    root.TransformBoxView = Object.freeze({ HANDLE_ROLES, selectedIds, selectedObjects, bounds, screenRect, handleWorld, screenMatrix, decorate, schedule });
})();
