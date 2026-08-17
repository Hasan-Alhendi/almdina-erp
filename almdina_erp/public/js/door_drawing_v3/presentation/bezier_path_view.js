(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const Base = root.ShapeView;
    const G = root.Geometry;
    const D = root.DocumentModel;
    if (!Base || !G || !D || !G.pathSegment || !G.absolutePathHandle) throw new Error("Door Drawing V3 Bezier domain and smart path view must load first");

    const SVG_NS = "http://www.w3.org/2000/svg";

    function esc(value) {
        const text = String(value ?? "");
        if (window.frappe && frappe.utils && frappe.utils.escape_html) return frappe.utils.escape_html(text);
        return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\"/g, "&quot;");
    }
    function svg(name, attrs = {}) {
        const element = document.createElementNS(SVG_NS, name);
        Object.entries(attrs).forEach(([key, value]) => element.setAttribute(key, String(value)));
        return element;
    }
    function screen(c, point) { return Base.worldToScreen(c, point); }
    function segmentScreenD(c, segment) {
        const start = screen(c, segment.start), end = screen(c, segment.end);
        if (!segment.curved) return `M ${start.x} ${start.y} L ${end.x} ${end.y}`;
        const c1 = screen(c, segment.c1), c2 = screen(c, segment.c2);
        return `M ${start.x} ${start.y} C ${c1.x} ${c1.y} ${c2.x} ${c2.y} ${end.x} ${end.y}`;
    }
    function pathD(c, object) {
        const segments = G.pathSegments(object);
        if (!segments.length) return "";
        const start = screen(c, segments[0].start);
        const commands = [`M ${start.x} ${start.y}`];
        segments.forEach(segment => {
            const end = screen(c, segment.end);
            if (segment.curved) {
                const c1 = screen(c, segment.c1), c2 = screen(c, segment.c2);
                commands.push(`C ${c1.x} ${c1.y} ${c2.x} ${c2.y} ${end.x} ${end.y}`);
            } else commands.push(`L ${end.x} ${end.y}`);
        });
        if (object.geometry.closed) commands.push("Z");
        return commands.join(" ");
    }
    function displayObject(c, id) {
        if (c.previewObject && String(c.previewObject.id) === String(id)) return c.previewObject;
        return D.objectById(c.history.current(), id);
    }
    function pathObject(c, id) {
        const object = displayObject(c, id);
        return object && object.type === G.PATH_TYPE ? object : null;
    }
    function hasCurves(object) { return Boolean(object && G.pathSegments(object).some(segment => segment.curved)); }

    function updatePathGeometry(c) {
        c.canvas.querySelectorAll(".ddv3-path-object[data-ddv3-path-object]").forEach(group => {
            const object = pathObject(c, group.dataset.ddv3PathObject);
            if (!object) return;
            const d = pathD(c, object);
            group.querySelectorAll(".ddv3-path-stroke").forEach(path => path.setAttribute("d", d));
            group.querySelectorAll(".ddv3-path-segment-hit").forEach(element => element.remove());
            const firstStroke = group.querySelector(".ddv3-path-stroke");
            G.pathSegments(object).forEach(segment => {
                const hit = svg("path", {
                    class: "ddv3-object-hit ddv3-path-segment-hit ddv3-bezier-segment-hit",
                    "data-ddv3-object": esc(object.id),
                    "data-ddv3-path-segment": segment.index,
                    d: segmentScreenD(c, segment),
                    "stroke-width": Base.OBJECT_HIT_STROKE_PX || 30,
                });
                if (firstStroke) group.insertBefore(hit, firstStroke); else group.appendChild(hit);
            });
        });
    }

    function selectedNodeIndices(c, object) {
        const values = Array.isArray(c.selectedNodeIndices) && c.selectedNodeIndices.length
            ? c.selectedNodeIndices
            : (Number.isInteger(c.selectedNodeIndex) ? [c.selectedNodeIndex] : []);
        return [...new Set(values.map(Number).filter(index => Number.isInteger(index) && index >= 0 && index < object.geometry.points.length))];
    }
    function handleMarkup(c) {
        c.canvas.querySelectorAll(".ddv3-bezier-handle-layer").forEach(element => element.remove());
        const object = pathObject(c, c.nodeEditId || c.selectedId);
        if (!object || String(c.nodeEditId || "") !== String(object.id)) return;
        const indices = selectedNodeIndices(c, object);
        if (!indices.length) return;
        const layer = svg("g", { class: "ddv3-bezier-handle-layer" });
        indices.forEach(index => {
            const anchor = object.geometry.points[index], anchorScreen = screen(c, anchor), node = G.pathNode(object, index);
            if (!node) return;
            ["in", "out"].forEach(role => {
                const absolute = G.absolutePathHandle(object, index, role);
                if (!absolute) return;
                const handleScreen = screen(c, absolute);
                layer.appendChild(svg("line", {
                    class: "ddv3-bezier-tangent-line",
                    x1: anchorScreen.x, y1: anchorScreen.y, x2: handleScreen.x, y2: handleScreen.y,
                }));
                layer.appendChild(svg("circle", {
                    class: `ddv3-bezier-handle is-${role}`,
                    "data-ddv3-object": object.id,
                    "data-ddv3-path-node": index,
                    "data-ddv3-path-handle": role,
                    cx: handleScreen.x, cy: handleScreen.y, r: 5,
                }));
            });
        });
        c.canvas.appendChild(layer);
    }

    function penDraftD(c, draft) {
        const anchors = draft && Array.isArray(draft.anchors) ? draft.anchors : [];
        if (!anchors.length) return "";
        const first = screen(c, anchors[0].point), commands = [`M ${first.x} ${first.y}`];
        for (let index = 1; index < anchors.length; index += 1) {
            const previous = anchors[index - 1], current = anchors[index];
            const start = previous.point, end = current.point;
            const c1 = previous.out ? G.point(start.x + previous.out.x, start.y + previous.out.y) : start;
            const c2 = current.in ? G.point(end.x + current.in.x, end.y + current.in.y) : end;
            const curve = Boolean(previous.out || current.in), sEnd = screen(c, end);
            if (curve) {
                const s1 = screen(c, c1), s2 = screen(c, c2);
                commands.push(`C ${s1.x} ${s1.y} ${s2.x} ${s2.y} ${sEnd.x} ${sEnd.y}`);
            } else commands.push(`L ${sEnd.x} ${sEnd.y}`);
        }
        if (draft.hover && anchors.length) {
            const previous = anchors[anchors.length - 1], end = draft.hover;
            const c1 = previous.out ? G.point(previous.point.x + previous.out.x, previous.point.y + previous.out.y) : previous.point;
            const endScreen = screen(c, end);
            if (previous.out) {
                const s1 = screen(c, c1);
                commands.push(`C ${s1.x} ${s1.y} ${endScreen.x} ${endScreen.y} ${endScreen.x} ${endScreen.y}`);
            } else commands.push(`L ${endScreen.x} ${endScreen.y}`);
        }
        return commands.join(" ");
    }
    function penDraftMarkup(c) {
        c.canvas.querySelectorAll(".ddv3-bezier-pen-layer").forEach(element => element.remove());
        const draft = c.bezierPathDraft;
        if (!draft || !Array.isArray(draft.anchors) || !draft.anchors.length) return;
        const layer = svg("g", { class: "ddv3-bezier-pen-layer", "pointer-events": "none" });
        layer.appendChild(svg("path", { class: "ddv3-bezier-pen-preview", d: penDraftD(c, draft) }));
        draft.anchors.forEach((anchor, index) => {
            const point = screen(c, anchor.point);
            layer.appendChild(svg("rect", {
                class: `ddv3-bezier-pen-anchor${index === 0 ? " is-first" : ""}${draft.closeReady && index === 0 ? " is-close-ready" : ""}`,
                x: point.x - 3.5, y: point.y - 3.5, width: 7, height: 7, rx: 1,
            }));
        });
        const active = draft.anchors[draft.anchors.length - 1];
        if (active && (active.in || active.out)) {
            const anchorScreen = screen(c, active.point);
            ["in", "out"].forEach(role => {
                if (!active[role]) return;
                const absolute = G.point(active.point.x + active[role].x, active.point.y + active[role].y), target = screen(c, absolute);
                layer.appendChild(svg("line", { class: "ddv3-bezier-tangent-line is-draft", x1: anchorScreen.x, y1: anchorScreen.y, x2: target.x, y2: target.y }));
                layer.appendChild(svg("circle", { class: "ddv3-bezier-draft-handle", cx: target.x, cy: target.y, r: 4.5 }));
            });
        }
        if (draft.closeReady) {
            const first = screen(c, draft.anchors[0].point);
            const label = svg("text", { class: "ddv3-bezier-close-label", x: first.x + 11, y: first.y - 11 });
            label.textContent = "إغلاق";
            layer.appendChild(label);
        }
        c.canvas.appendChild(layer);
    }

    function nodeTypeLabel(type) {
        if (type === G.NODE_SMOOTH) return "ناعم";
        if (type === G.NODE_SYMMETRIC) return "متماثل";
        return "زاوية";
    }
    function ensureContextControls(c) {
        const workspace = c.root.querySelector(".ddv3-workspace") || c.root;
        let bar = workspace.querySelector(".ddv3-bezier-contextbar");
        if (!bar) {
            bar = document.createElement("div");
            bar.className = "ddv3-bezier-contextbar";
            bar.dir = "rtl";
            workspace.appendChild(bar);
        }
        if (c.readOnly) { bar.innerHTML = ""; bar.classList.remove("is-visible"); return; }
        const object = pathObject(c, c.nodeEditId || c.selectedId);
        if (!object) { bar.innerHTML = ""; bar.classList.remove("is-visible"); return; }
        const nodes = selectedNodeIndices(c, object);
        const segments = Array.isArray(c.selectedSegmentIndices) ? c.selectedSegmentIndices.map(Number).filter(Number.isInteger) : [];
        const controls = [];
        if (nodes.length) {
            const nodeTypes = new Set(nodes.map(index => (G.pathNode(object, index) || {}).type));
            const current = nodeTypes.size === 1 ? [...nodeTypes][0] : "mixed";
            controls.push(`<span class="ddv3-bezier-context-label">${nodes.length > 1 ? `${nodes.length} نقاط` : nodeTypeLabel(current)}</span>`);
            [
                [G.NODE_CORNER, "زاوية", "Corner · مقابض مستقلة"],
                [G.NODE_SMOOTH, "ناعم", "Smooth · اتجاه واحد وأطوال مستقلة"],
                [G.NODE_SYMMETRIC, "متماثل", "Symmetric · اتجاه وطول متماثلان"],
            ].forEach(([action, label, title]) => controls.push(`<button type="button" class="${current === action ? "is-active" : ""}" data-ddv3-bezier-action="node-type" data-ddv3-node-type="${action}" title="${title}">${label}</button>`));
        }
        if (segments.length) {
            const segmentStates = new Set(segments.map(index => { const segment = G.pathSegment(object, index); return segment && segment.curved ? "curve" : "line"; }));
            const current = segmentStates.size === 1 ? [...segmentStates][0] : "mixed";
            controls.push(`<span class="ddv3-bezier-context-label">${segments.length > 1 ? `${segments.length} أضلاع` : "الضلع"}</span>`);
            controls.push(`<button type="button" class="${current === "line" ? "is-active" : ""}" data-ddv3-bezier-action="segment-type" data-ddv3-segment-type="line" title="تحويل إلى ضلع مستقيم">مستقيم</button>`);
            controls.push(`<button type="button" class="${current === "curve" ? "is-active" : ""}" data-ddv3-bezier-action="segment-type" data-ddv3-segment-type="curve" title="تحويل إلى منحنى Bezier">منحنى</button>`);
        }
        bar.innerHTML = controls.join("");
        bar.classList.toggle("is-visible", controls.length > 0);
    }

    function decorate(c) {
        if (!c || !c.canvas || c.__bezierDecorating) return;
        c.__bezierDecorating = true;
        try {
            updatePathGeometry(c);
            handleMarkup(c);
            penDraftMarkup(c);
            ensureContextControls(c);
            const edited = pathObject(c, c.nodeEditId || c.selectedId);
            c.canvas.dataset.bezierEditing = String(Boolean(edited && selectedNodeIndices(c, edited).length));
        } finally {
            c.__bezierDecorating = false;
        }
    }
    function schedule(c) {
        if (!c || c.__bezierDecorateScheduled) return;
        c.__bezierDecorateScheduled = true;
        const run = () => { c.__bezierDecorateScheduled = false; decorate(c); };
        if (typeof requestAnimationFrame === "function") requestAnimationFrame(run); else setTimeout(run, 0);
    }
    function render(c) {
        const result = Base.render(c);
        decorate(c);
        return result;
    }

    root.ShapeView = Object.freeze({ ...Base, render, pathD });
    root.BezierPathView = Object.freeze({ pathD, segmentScreenD, updatePathGeometry, decorate, schedule, hasCurves });
})();
