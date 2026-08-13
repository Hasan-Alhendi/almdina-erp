(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    const Base = root.ShapeView;
    if (!G || !Base) throw new Error("Door Drawing V3 shape view must load before professional move view");

    const SVG_NS = "http://www.w3.org/2000/svg";

    function svg(name, attrs = {}) {
        const element = document.createElementNS(SVG_NS, name);
        Object.entries(attrs).forEach(([key, value]) => element.setAttribute(key, String(value)));
        return element;
    }
    function screen(c, point) { return Base.worldToScreen(c, point); }
    function fmt(value) { return `${G.roundMm(value, 1)} mm`; }

    function stripObjectIdentity(element) {
        if (element.removeAttribute) {
            element.removeAttribute("data-ddv3-object");
            element.removeAttribute("data-ddv3-vector-preview-moved");
            element.removeAttribute("data-ddv3-transform-preview");
            element.removeAttribute("transform");
            if (element.style) {
                element.style.transform = "";
                element.style.transformOrigin = "";
            }
        }
        if (element.querySelectorAll) element.querySelectorAll("[data-ddv3-object]").forEach(child => child.removeAttribute("data-ddv3-object"));
    }

    function duplicateGhost(c, layer) {
        if (!c.professionalMoveDuplicate || !c.professionalMoveGesture) return;
        const ids = new Set((c.professionalMoveGesture.ids || []).map(String));
        if (!ids.size) return;
        const ghost = svg("g", { class: "ddv3-move-duplicate-origin" });
        c.canvas.querySelectorAll("[data-ddv3-object]").forEach(element => {
            if (!ids.has(String(element.dataset.ddv3Object || ""))) return;
            const clone = element.cloneNode(true);
            stripObjectIdentity(clone);
            ghost.appendChild(clone);
        });
        if (ghost.childNodes.length) layer.appendChild(ghost);
    }

    function alignmentGuide(c, layer, guide) {
        if (guide.axis === "x") {
            const a = screen(c, G.point(guide.x, guide.from));
            const b = screen(c, G.point(guide.x, guide.to));
            layer.appendChild(svg("line", { class: "ddv3-move-guide ddv3-move-guide-alignment", x1: a.x, y1: a.y, x2: b.x, y2: b.y }));
        } else {
            const a = screen(c, G.point(guide.from, guide.y));
            const b = screen(c, G.point(guide.to, guide.y));
            layer.appendChild(svg("line", { class: "ddv3-move-guide ddv3-move-guide-alignment", x1: a.x, y1: a.y, x2: b.x, y2: b.y }));
        }
    }

    function geometryPointGuide(c, layer, guide) {
        if (!guide.point) return;
        const point = screen(c, guide.point);
        const group = svg("g", { class: `ddv3-move-point-snap is-${String(guide.kind || "point")}` });
        group.appendChild(svg("circle", { cx: point.x, cy: point.y, r: 5 }));
        group.appendChild(svg("line", { x1: point.x - 8, y1: point.y, x2: point.x + 8, y2: point.y }));
        group.appendChild(svg("line", { x1: point.x, y1: point.y - 8, x2: point.x, y2: point.y + 8 }));
        layer.appendChild(group);
    }

    function spacingGuide(c, layer, guide) {
        let a, b;
        if (guide.axis === "x") {
            a = screen(c, G.point(guide.from, guide.at));
            b = screen(c, G.point(guide.to, guide.at));
        } else {
            a = screen(c, G.point(guide.at, guide.from));
            b = screen(c, G.point(guide.at, guide.to));
        }
        const cls = guide.type === "spacing-reference" ? " is-reference" : "";
        const group = svg("g", { class: `ddv3-move-spacing${cls}` });
        group.appendChild(svg("line", { class: "ddv3-move-spacing-line", x1: a.x, y1: a.y, x2: b.x, y2: b.y }));
        if (guide.axis === "x") {
            group.appendChild(svg("line", { class: "ddv3-move-spacing-tick", x1: a.x, y1: a.y - 5, x2: a.x, y2: a.y + 5 }));
            group.appendChild(svg("line", { class: "ddv3-move-spacing-tick", x1: b.x, y1: b.y - 5, x2: b.x, y2: b.y + 5 }));
        } else {
            group.appendChild(svg("line", { class: "ddv3-move-spacing-tick", x1: a.x - 5, y1: a.y, x2: a.x + 5, y2: a.y }));
            group.appendChild(svg("line", { class: "ddv3-move-spacing-tick", x1: b.x - 5, y1: b.y, x2: b.x + 5, y2: b.y }));
        }
        const label = svg("text", { class: "ddv3-move-spacing-label", x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 - 7 });
        label.textContent = fmt(guide.distanceMm);
        group.appendChild(label);
        layer.appendChild(group);
    }

    function axisGuide(c, layer, guide) {
        const box = guide.box;
        if (!box) return;
        if (guide.axis === "x") {
            const a = screen(c, G.point(box.left - Math.max(30, box.width * 0.25), box.cy));
            const b = screen(c, G.point(box.right + Math.max(30, box.width * 0.25), box.cy));
            layer.appendChild(svg("line", { class: "ddv3-move-guide ddv3-move-guide-axis", x1: a.x, y1: a.y, x2: b.x, y2: b.y }));
        } else {
            const a = screen(c, G.point(box.cx, box.bottom - Math.max(30, box.height * 0.25)));
            const b = screen(c, G.point(box.cx, box.top + Math.max(30, box.height * 0.25)));
            layer.appendChild(svg("line", { class: "ddv3-move-guide ddv3-move-guide-axis", x1: a.x, y1: a.y, x2: b.x, y2: b.y }));
        }
    }

    function guideMarkup(c, layer) {
        const state = c.professionalMoveGuideState;
        if (!state || !Array.isArray(state.guides)) return;
        state.guides.forEach(guide => {
            if (guide.type === "alignment") alignmentGuide(c, layer, guide);
            else if (guide.type === "geometry-point") geometryPointGuide(c, layer, guide);
            else if (guide.type === "spacing" || guide.type === "spacing-reference") spacingGuide(c, layer, guide);
            else if (guide.type === "axis-lock") axisGuide(c, layer, guide);
        });
    }

    function ensureOverlay(c) {
        c.canvas.querySelectorAll(".ddv3-professional-move-overlay").forEach(element => element.remove());
        if (!c.professionalMoveGesture && !c.professionalMoveGuideState) return null;
        const layer = svg("g", { class: "ddv3-professional-move-overlay", "pointer-events": "none" });
        duplicateGhost(c, layer);
        guideMarkup(c, layer);
        c.canvas.appendChild(layer);
        return layer;
    }

    function decorate(c) {
        if (!c || !c.canvas || c.__professionalMoveDecorating) return;
        c.__professionalMoveDecorating = true;
        try { ensureOverlay(c); }
        finally { c.__professionalMoveDecorating = false; }
    }
    function schedule(c) {
        if (!c || c.__professionalMoveScheduled) return;
        c.__professionalMoveScheduled = true;
        const run = () => { c.__professionalMoveScheduled = false; decorate(c); };
        if (typeof requestAnimationFrame === "function") requestAnimationFrame(run); else setTimeout(run, 0);
    }
    function render(c) {
        const result = Base.render(c);
        decorate(c);
        return result;
    }

    root.ShapeView = Object.freeze({ ...Base, render });
    root.ProfessionalMoveView = Object.freeze({ decorate, schedule, ensureOverlay });
})();
