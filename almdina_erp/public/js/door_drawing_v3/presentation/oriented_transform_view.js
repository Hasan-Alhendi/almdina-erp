(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    const O = root.OrientedTransformDomain;
    const Base = root.ShapeView;
    const TransformView = root.TransformBoxView;
    if (!G || !O || !Base || !TransformView) throw new Error("Door Drawing V3 oriented geometry and transform view must load before oriented transform view");

    const SVG_NS = "http://www.w3.org/2000/svg";
    const HANDLE_ROLES = Object.freeze(["nw", "n", "ne", "e", "se", "s", "sw", "w"]);
    const ROTATION_OFFSET_PX = 34;

    function svg(name, attrs = {}) {
        const element = document.createElementNS(SVG_NS, name);
        Object.entries(attrs).forEach(([key, value]) => element.setAttribute(key, String(value)));
        return element;
    }
    function fmt(value, precision = 2) { return String(G.roundMm(value, precision)); }
    function selectedObjects(c) { return TransformView.selectedObjects(c); }
    function selectionKey(c) { return TransformView.selectedIds(c).slice().sort().join("|"); }
    function ensureSelectionState(c) {
        const key = selectionKey(c);
        if (c.orientedTransformSelectionKey !== key) {
            c.orientedTransformSelectionKey = key;
            c.orientedTransformPreferredAngle = null;
            c.orientedTransformPivot = null;
        }
        return key;
    }
    function sourceFrame(c) {
        ensureSelectionState(c);
        const objects = selectedObjects(c);
        if (!objects.length) return null;
        const frame = O.frameForObjects(objects, c.orientedTransformPreferredAngle);
        if (frame && !Number.isFinite(Number(c.orientedTransformPreferredAngle))) c.orientedTransformPreferredAngle = frame.angleDeg;
        return frame;
    }
    function frame(c) { return c.orientedTransformPreviewFrame || sourceFrame(c); }
    function pivot(c, value = frame(c)) {
        if (c.orientedTransformPivot) return c.orientedTransformPivot;
        return value ? value.center : null;
    }
    function screen(c, point) { return Base.worldToScreen(c, point); }

    function handlePoint(c, value, role) { return screen(c, O.handleWorld(value, role)); }
    function rotationPoint(c, value) {
        const offsetMm = ROTATION_OFFSET_PX / Math.max(0.000001, Number(c.viewport.scale || 1));
        return screen(c, O.worldPoint(value, G.point(0, value.height / 2 + offsetMm)));
    }
    function topPoint(c, value) { return screen(c, O.handleWorld(value, "n")); }

    function ensureOverlay(c) {
        c.canvas.querySelectorAll(".ddv3-oriented-transform-overlay").forEach(element => element.remove());
        const value = frame(c);
        const visible = Boolean(!c.readOnly && c.tool === "select" && !c.nodeEditId && selectedObjects(c).length && value && !c.professionalMoveGesture);
        c.root.classList.toggle("ddv3-has-oriented-transform", visible);
        if (!visible) return null;

        const layer = svg("g", { class: "ddv3-oriented-transform-overlay" });
        const corners = O.corners(value).map(point => screen(c, point));
        layer.appendChild(svg("polygon", {
            class: "ddv3-oriented-transform-outline",
            points: corners.map(point => `${point.x},${point.y}`).join(" "),
        }));
        HANDLE_ROLES.forEach(role => {
            const point = handlePoint(c, value, role);
            const group = svg("g", { class: `ddv3-oriented-transform-handle is-${role}`, "data-ddv3-oriented-transform-handle": role });
            group.appendChild(svg("circle", { class: "ddv3-oriented-transform-handle-hit", cx: point.x, cy: point.y, r: 12 }));
            group.appendChild(svg("rect", { class: "ddv3-oriented-transform-handle-dot", x: point.x - 4, y: point.y - 4, width: 8, height: 8, rx: 1 }));
            layer.appendChild(group);
        });

        const top = topPoint(c, value), rotate = rotationPoint(c, value);
        layer.appendChild(svg("line", { class: "ddv3-oriented-rotation-stem", x1: top.x, y1: top.y, x2: rotate.x, y2: rotate.y }));
        const rotateGroup = svg("g", { class: "ddv3-oriented-rotation-handle", "data-ddv3-oriented-transform-handle": "rotate" });
        rotateGroup.appendChild(svg("circle", { class: "ddv3-oriented-rotation-hit", cx: rotate.x, cy: rotate.y, r: 13 }));
        rotateGroup.appendChild(svg("circle", { class: "ddv3-oriented-rotation-dot", cx: rotate.x, cy: rotate.y, r: 5 }));
        layer.appendChild(rotateGroup);

        const pivotWorld = pivot(c, value);
        if (pivotWorld) {
            const p = screen(c, pivotWorld);
            const pivotGroup = svg("g", { class: "ddv3-oriented-pivot", "data-ddv3-oriented-transform-handle": "pivot" });
            pivotGroup.appendChild(svg("circle", { class: "ddv3-oriented-pivot-hit", cx: p.x, cy: p.y, r: 13 }));
            pivotGroup.appendChild(svg("circle", { class: "ddv3-oriented-pivot-ring", cx: p.x, cy: p.y, r: 6 }));
            pivotGroup.appendChild(svg("path", { class: "ddv3-oriented-pivot-cross", d: `M ${p.x - 9} ${p.y} H ${p.x + 9} M ${p.x} ${p.y - 9} V ${p.y + 9}` }));
            layer.appendChild(pivotGroup);
        }

        c.canvas.appendChild(layer);
        return layer;
    }

    function ensureContextBar(c) {
        const workspace = c.root.querySelector(".ddv3-workspace") || c.root;
        let bar = workspace.querySelector(".ddv3-oriented-transform-contextbar");
        if (!bar) {
            bar = document.createElement("div");
            bar.className = "ddv3-oriented-transform-contextbar";
            bar.dir = "rtl";
            workspace.appendChild(bar);
        }
        const value = frame(c), count = selectedObjects(c).length;
        if (c.readOnly || c.tool !== "select" || c.nodeEditId || !value || !count || c.professionalMoveGesture) {
            bar.innerHTML = "";
            bar.classList.remove("is-visible");
            return bar;
        }
        bar.innerHTML = `<span class="ddv3-oriented-transform-summary">${count > 1 ? `${count} عناصر` : "Transform"} · ${fmt(value.angleDeg, 1)}°</span>` +
            '<button type="button" data-ddv3-oriented-action="flip-horizontal" title="انعكاس حول المحور المحلي الأفقي">↔ انعكاس</button>' +
            '<button type="button" data-ddv3-oriented-action="flip-vertical" title="انعكاس حول المحور المحلي العمودي">↕ انعكاس</button>' +
            '<button type="button" data-ddv3-oriented-action="reset-pivot" title="إعادة مركز الدوران إلى الوسط">◎ المركز</button>';
        bar.classList.add("is-visible");
        return bar;
    }

    function ensureInspector(c) {
        if (!c.inspector) return;
        c.inspector.querySelectorAll(".ddv3-oriented-transform-inspector").forEach(element => element.remove());
        const value = frame(c), count = selectedObjects(c).length;
        if (c.readOnly || c.tool !== "select" || c.nodeEditId || !value || !count) return;
        const origin = O.handleWorld(value, "sw");
        const pivotWorld = pivot(c, value);
        const section = document.createElement("section");
        section.className = "ddv3-panel-section ddv3-oriented-transform-inspector";
        section.dir = "ltr";
        section.innerHTML = `<div class="ddv3-section-title">Transform</div>
            <div class="ddv3-field-grid">
                <label class="ddv3-field"><span>X</span><div><input type="number" step="0.1" value="${fmt(origin.x, 3)}" data-ddv3-oriented-prop="x"><b>mm</b></div></label>
                <label class="ddv3-field"><span>Y</span><div><input type="number" step="0.1" value="${fmt(origin.y, 3)}" data-ddv3-oriented-prop="y"><b>mm</b></div></label>
            </div>
            <div class="ddv3-field-grid">
                <label class="ddv3-field"><span>W</span><div><input type="number" min="0.001" step="0.1" value="${fmt(value.width, 3)}" data-ddv3-oriented-prop="width"><b>mm</b></div></label>
                <label class="ddv3-field"><span>H</span><div><input type="number" min="0.001" step="0.1" value="${fmt(value.height, 3)}" data-ddv3-oriented-prop="height"><b>mm</b></div></label>
            </div>
            <div class="ddv3-field-grid">
                <label class="ddv3-field"><span>Rotation</span><div><input type="number" step="0.1" value="${fmt(value.angleDeg, 2)}" data-ddv3-oriented-prop="rotation"><b>°</b></div></label>
            </div>
            <div class="ddv3-section-title ddv3-oriented-pivot-title">Pivot / Origin</div>
            <div class="ddv3-field-grid">
                <label class="ddv3-field"><span>PX</span><div><input type="number" step="0.1" value="${fmt(pivotWorld.x, 3)}" data-ddv3-oriented-prop="pivot-x"><b>mm</b></div></label>
                <label class="ddv3-field"><span>PY</span><div><input type="number" step="0.1" value="${fmt(pivotWorld.y, 3)}" data-ddv3-oriented-prop="pivot-y"><b>mm</b></div></label>
            </div>
            <p class="ddv3-transform-hint" dir="rtl">Shift أثناء الدوران = 15° · Shift أثناء Resize = حفظ النسبة · Alt أثناء Resize = من المركز</p>`;
        c.inspector.insertBefore(section, c.inspector.firstChild);
    }

    function decorate(c) {
        if (!c || !c.canvas || c.__orientedTransformDecorating) return;
        c.__orientedTransformDecorating = true;
        try { ensureOverlay(c); ensureContextBar(c); ensureInspector(c); }
        finally { c.__orientedTransformDecorating = false; }
    }
    function schedule(c) {
        if (!c || c.__orientedTransformScheduled) return;
        c.__orientedTransformScheduled = true;
        const run = () => { c.__orientedTransformScheduled = false; decorate(c); };
        if (typeof requestAnimationFrame === "function") requestAnimationFrame(run); else setTimeout(run, 0);
    }
    function render(c) { const result = Base.render(c); decorate(c); return result; }

    root.ShapeView = Object.freeze({ ...Base, render });
    root.OrientedTransformView = Object.freeze({ HANDLE_ROLES, selectedObjects, selectionKey, ensureSelectionState, sourceFrame, frame, pivot, decorate, schedule, rotationPoint });
})();
