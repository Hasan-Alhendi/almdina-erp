(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    const Selection = root.VectorSelectionGeometry;
    const BaseView = root.ShapeView;
    if (!G || !Selection || !BaseView) throw new Error("Door Drawing V3 vector selection domain and shape view must load before vector editing view");

    const SVG_NS = "http://www.w3.org/2000/svg";

    function selectedIds(c) {
        const values = Array.isArray(c && c.selectedIds) ? c.selectedIds : (c && c.selectedId ? [c.selectedId] : []);
        return [...new Set(values.filter(Boolean).map(String))];
    }

    function selectedObjects(c) {
        const ids = new Set(selectedIds(c));
        return (c.history.current().objects || []).filter(object => ids.has(String(object.id)));
    }

    function screenRect(c, box) {
        if (!box) return null;
        const first = BaseView.worldToScreen(c, G.point(box.left, box.top));
        const second = BaseView.worldToScreen(c, G.point(box.right, box.bottom));
        return {
            x: Math.min(first.x, second.x),
            y: Math.min(first.y, second.y),
            width: Math.abs(second.x - first.x),
            height: Math.abs(second.y - first.y),
        };
    }

    function svgElement(name, attributes = {}) {
        const element = document.createElementNS(SVG_NS, name);
        Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, String(value)));
        return element;
    }

    function clearObjectClasses(c) {
        c.canvas.querySelectorAll(".ddv3-vector-selected, .ddv3-vector-segment-selected, .ddv3-vector-node-selected")
            .forEach(element => element.classList.remove("ddv3-vector-selected", "ddv3-vector-segment-selected", "ddv3-vector-node-selected"));
    }

    function decorateObjectSelection(c) {
        const ids = new Set(selectedIds(c));
        if (!ids.size) return;
        c.canvas.querySelectorAll("[data-ddv3-object]").forEach(element => {
            if (ids.has(String(element.dataset.ddv3Object || ""))) element.classList.add("ddv3-vector-selected");
        });
    }

    function decoratePathSubselection(c) {
        const nodeIndices = new Set((c.selectedNodeIndices || []).map(Number));
        const segmentIndices = new Set((c.selectedSegmentIndices || []).map(Number));
        const editId = String(c.nodeEditId || "");
        if (!editId) return;
        c.canvas.querySelectorAll("[data-ddv3-path-node]").forEach(element => {
            if (String(element.dataset.ddv3Object || "") === editId && nodeIndices.has(Number(element.dataset.ddv3PathNode))) {
                element.classList.add("ddv3-vector-node-selected");
            }
        });
        c.canvas.querySelectorAll("[data-ddv3-path-segment]").forEach(element => {
            if (String(element.dataset.ddv3Object || "") === editId && segmentIndices.has(Number(element.dataset.ddv3PathSegment))) {
                element.classList.add("ddv3-vector-segment-selected");
            }
        });
    }

    function applyPreviewTranslation(c) {
        c.canvas.querySelectorAll("[data-ddv3-vector-preview-moved]").forEach(element => {
            element.style.transform = "";
            delete element.dataset.ddv3VectorPreviewMoved;
        });
        const preview = c.vectorActiveTranslation;
        if (!preview || !Array.isArray(preview.ids) || !preview.ids.length) return;
        const dxPx = Number(preview.dx || 0) * Number(c.viewport.scale || 1);
        const dyPx = -Number(preview.dy || 0) * Number(c.viewport.scale || 1);
        const ids = new Set(preview.ids.map(String));
        c.canvas.querySelectorAll("[data-ddv3-object]").forEach(element => {
            if (!ids.has(String(element.dataset.ddv3Object || ""))) return;
            element.style.transform = `translate(${dxPx}px, ${dyPx}px)`;
            element.style.transformOrigin = "0 0";
            element.dataset.ddv3VectorPreviewMoved = "1";
        });
    }

    function selectionBoundsMarkup(c, layer) {
        const objects = selectedObjects(c);
        if (!objects.length) return;
        const box = Selection.unionBounds(objects);
        const rect = screenRect(c, box);
        if (!rect) return;
        const outline = svgElement("rect", {
            class: `ddv3-vector-selection-box${objects.length > 1 ? " is-multi" : ""}`,
            x: rect.x,
            y: rect.y,
            width: Math.max(0.5, rect.width),
            height: Math.max(0.5, rect.height),
            rx: 1,
        });
        layer.appendChild(outline);
        if (objects.length > 1) {
            const label = svgElement("text", {
                class: "ddv3-vector-selection-count",
                x: rect.x + 4,
                y: Math.max(14, rect.y - 7),
            });
            label.textContent = `${objects.length} عناصر`;
            layer.appendChild(label);
        }
    }

    function marqueeMarkup(c, layer) {
        const marquee = c.vectorMarquee;
        if (!marquee || !marquee.start || !marquee.current) return;
        const rect = screenRect(c, Selection.normalizeRect(marquee.start, marquee.current));
        if (!rect) return;
        layer.appendChild(svgElement("rect", {
            class: `ddv3-vector-marquee ${marquee.current.x >= marquee.start.x ? "is-contain" : "is-intersect"}`,
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height,
        }));
    }

    function pathDraftMarkup(c, layer) {
        const draft = c.vectorPathDraft;
        if (!draft || !Array.isArray(draft.points) || !draft.points.length) return;
        const points = draft.points.slice();
        if (draft.hover && (!points.length || G.distance(points[points.length - 1], draft.hover) >= G.EPSILON_MM)) points.push(draft.hover);
        const screen = points.map(point => BaseView.worldToScreen(c, point));
        if (screen.length > 1) {
            const d = [`M ${screen[0].x} ${screen[0].y}`, ...screen.slice(1).map(point => `L ${point.x} ${point.y}`)].join(" ");
            layer.appendChild(svgElement("path", { class: "ddv3-vector-path-draft", d }));
        }
        draft.points.forEach((point, index) => {
            const screenPoint = BaseView.worldToScreen(c, point);
            layer.appendChild(svgElement("circle", {
                class: `ddv3-vector-path-draft-node${index === 0 ? " is-first" : ""}`,
                cx: screenPoint.x,
                cy: screenPoint.y,
                r: index === 0 ? 5 : 3.5,
            }));
        });
        if (draft.closeReady) {
            const first = BaseView.worldToScreen(c, draft.points[0]);
            const text = svgElement("text", { class: "ddv3-vector-path-close-label", x: first.x + 10, y: first.y - 10 });
            text.textContent = "إغلاق المسار";
            layer.appendChild(text);
        }
    }

    function snapMarkup(c, layer) {
        const state = c.vectorSnapState;
        if (!state || !state.point || !state.snapped) return;
        const point = BaseView.worldToScreen(c, state.point);
        if (state.axis === "horizontal") layer.appendChild(svgElement("line", {
            class: "ddv3-vector-snap-guide", x1: 0, y1: point.y, x2: Math.max(0, c.viewport.widthPx), y2: point.y,
        }));
        if (state.axis === "vertical") layer.appendChild(svgElement("line", {
            class: "ddv3-vector-snap-guide", x1: point.x, y1: 0, x2: point.x, y2: Math.max(0, c.viewport.heightPx),
        }));
        const marker = svgElement("g", { class: "ddv3-vector-snap-marker", transform: `translate(${point.x} ${point.y})` });
        marker.appendChild(svgElement("circle", { r: 5.5 }));
        marker.appendChild(svgElement("path", { d: "M -8 0 H 8 M 0 -8 V 8" }));
        layer.appendChild(marker);
    }

    function ensureSvgOverlay(c) {
        c.canvas.querySelectorAll(".ddv3-vector-overlay").forEach(element => element.remove());
        const layer = svgElement("g", { class: "ddv3-vector-overlay", "pointer-events": "none" });
        selectionBoundsMarkup(c, layer);
        marqueeMarkup(c, layer);
        pathDraftMarkup(c, layer);
        snapMarkup(c, layer);
        c.canvas.appendChild(layer);
        return layer;
    }

    function iconPath() {
        return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 18L9 7l6 4 4-6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><circle cx="5" cy="18" r="1.6"/><circle cx="9" cy="7" r="1.6"/><circle cx="15" cy="11" r="1.6"/><circle cx="19" cy="5" r="1.6"/></svg>';
    }

    function ensurePathTool(c) {
        if (!c || c.readOnly) return null;
        const toolbar = c.root.querySelector(".ddv3-toolbar");
        if (!toolbar) return null;
        let button = toolbar.querySelector('[data-ddv3-vector-tool="path"]');
        if (!button) {
            button = document.createElement("button");
            button.type = "button";
            button.dataset.ddv3VectorTool = "path";
            button.setAttribute("aria-label", "مسار دقيق");
            button.innerHTML = iconPath();
            const pen = toolbar.querySelector('[data-ddv3-tool="pen"]');
            if (pen && pen.nextSibling) toolbar.insertBefore(button, pen.nextSibling);
            else toolbar.appendChild(button);
        }
        button.title = "مسار دقيق B · انقر نقطةً بعد نقطة · Enter لإنهاء المسار المفتوح";
        button.classList.toggle("is-active", c.tool === "path");
        return button;
    }

    const ACTIONS = Object.freeze([
        ["align-left", "يسار", "محاذاة لليسار"],
        ["align-hcenter", "وسط أفقي", "محاذاة للمركز أفقيًا"],
        ["align-right", "يمين", "محاذاة لليمين"],
        ["align-top", "أعلى", "محاذاة للأعلى"],
        ["align-vcenter", "وسط عمودي", "محاذاة للمركز عموديًا"],
        ["align-bottom", "أسفل", "محاذاة للأسفل"],
        ["distribute-horizontal", "توزيع ↔", "توزيع المسافات أفقيًا"],
        ["distribute-vertical", "توزيع ↕", "توزيع المسافات عموديًا"],
    ]);

    function ensureActionBar(c) {
        if (!c || c.readOnly) return null;
        const workspace = c.root.querySelector(".ddv3-workspace") || c.root;
        let bar = workspace.querySelector(".ddv3-vector-actionbar");
        if (!bar) {
            bar = document.createElement("div");
            bar.className = "ddv3-vector-actionbar";
            bar.dir = "rtl";
            workspace.appendChild(bar);
        }
        const objectCount = selectedIds(c).length;
        const segmentCount = Array.isArray(c.selectedSegmentIndices) ? c.selectedSegmentIndices.length : 0;
        const nodeCount = Array.isArray(c.selectedNodeIndices) ? c.selectedNodeIndices.length : 0;
        const controls = [];
        if (objectCount > 1) {
            controls.push(`<span class="ddv3-vector-action-summary">${objectCount} عناصر</span>`);
            ACTIONS.forEach(([action, label, title]) => controls.push(`<button type="button" data-ddv3-vector-action="${action}" title="${title}">${label}</button>`));
        }
        if (segmentCount) {
            controls.push(`<span class="ddv3-vector-action-summary">${segmentCount} أضلاع</span>`);
            controls.push('<button type="button" data-ddv3-vector-action="segment-midpoints" title="إضافة نقطة في منتصف كل ضلع محدد">+ نقطة وسط</button>');
        }
        if (nodeCount > 1) {
            controls.push(`<span class="ddv3-vector-action-summary">${nodeCount} نقاط محددة</span>`);
            controls.push('<button type="button" data-ddv3-vector-action="nodes-align-x" title="جعل النقاط المحددة على نفس X">محاذاة X</button>');
            controls.push('<button type="button" data-ddv3-vector-action="nodes-align-y" title="جعل النقاط المحددة على نفس Y">محاذاة Y</button>');
            if (nodeCount > 2) {
                controls.push('<button type="button" data-ddv3-vector-action="nodes-distribute-x" title="توزيع النقاط بالتساوي على X">توزيع X</button>');
                controls.push('<button type="button" data-ddv3-vector-action="nodes-distribute-y" title="توزيع النقاط بالتساوي على Y">توزيع Y</button>');
            }
        }
        bar.innerHTML = controls.join("");
        bar.classList.toggle("is-visible", controls.length > 0);
        return bar;
    }

    function decorate(c) {
        if (!c || !c.canvas || c.__vectorDecorating) return;
        c.__vectorDecorating = true;
        const observer = c.__vectorMutationObserver;
        if (observer) observer.disconnect();
        try {
            clearObjectClasses(c);
            decorateObjectSelection(c);
            decoratePathSubselection(c);
            applyPreviewTranslation(c);
            ensureSvgOverlay(c);
            ensurePathTool(c);
            ensureActionBar(c);
            c.canvas.dataset.vectorTool = c.tool === "path" ? "path" : "";
        } finally {
            c.__vectorDecorating = false;
            if (observer && c.canvas.isConnected) observer.observe(c.canvas, { childList: true, subtree: true, attributes: false });
        }
    }

    function schedule(c) {
        if (!c || c.__vectorDecorateScheduled) return;
        c.__vectorDecorateScheduled = true;
        const run = () => {
            c.__vectorDecorateScheduled = false;
            decorate(c);
        };
        if (typeof requestAnimationFrame === "function") requestAnimationFrame(run);
        else setTimeout(run, 0);
    }

    function observe(c) {
        if (!c || !c.canvas || c.__vectorMutationObserver || typeof MutationObserver !== "function") return null;
        const observer = new MutationObserver(() => {
            if (!c.__vectorDecorating) schedule(c);
        });
        observer.observe(c.canvas, { childList: true, subtree: true, attributes: false });
        c.__vectorMutationObserver = observer;
        return observer;
    }

    root.VectorEditingView = Object.freeze({ decorate, schedule, observe, selectedIds, selectedObjects, screenRect });
})();
