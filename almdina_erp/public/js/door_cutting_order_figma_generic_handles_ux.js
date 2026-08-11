(() => {
    "use strict";

    const baseEditor = window.AlmdinaSpecialShapeEditor;
    const history = window.AlmdinaSketchHistory;
    const engine = window.AlmdinaSketchEngine;
    const lineModel = window.AlmdinaExactLineModel;
    const arcModel = window.AlmdinaExactArcModel;
    if (!baseEditor || !history || !engine || !lineModel || !arcModel) {
        console.error("Generic handle dependencies must load before figma generic handles UX");
        return;
    }
    if (baseEditor.__figmaGenericHandlesIntegrated) return;

    const STYLE_ID = "dco-figma-generic-handles-css";
    const SVG_NS = "http://www.w3.org/2000/svg";
    const MOUNT_RETRIES = 24;
    const MIN_SIZE = 4;

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-figma-generic-handles{pointer-events:none}.dco-figma-generic-outline{fill:none;stroke:#0d99ff;stroke-width:2;stroke-dasharray:5 4;vector-effect:non-scaling-stroke;pointer-events:none}
            .dco-figma-generic-hit{fill:transparent;stroke:transparent;stroke-width:18;pointer-events:stroke;cursor:crosshair}.dco-figma-generic-dot{fill:#fff;stroke:#0d99ff;stroke-width:2.3;vector-effect:non-scaling-stroke;pointer-events:none}.dco-figma-generic-dot.is-active{fill:#0d99ff;stroke:#fff;stroke-width:3}
        `;
        document.head.appendChild(style);
    }

    function visibleModal() {
        return Array.from(document.querySelectorAll(".dco-special-shape-modal")).reverse().find(modal =>
            !modal.classList.contains("dco-special-shape-readonly")
            && (modal.classList.contains("show") || modal.style.display === "block")
        ) || null;
    }

    function liveState(controller) {
        const state = history.getActiveState ? history.getActiveState() : null;
        return state && state.root === controller.root && state.svg === controller.svg ? state : null;
    }

    function selected(controller) {
        const state = liveState(controller);
        if (!state || state.tool !== "select") return null;
        return (state.elements || []).find(item => String(item && item.id) === String(state.selectedId || "")) || null;
    }

    function isExact(element) {
        return Boolean(lineModel.exactMeta(element) || arcModel.arcMeta(element));
    }

    function handlesFor(element) {
        if (!element || isExact(element)) return [];
        if (element.smart_template_editable) return [];
        if (element.type === "line" || element.type === "dimension") {
            return [
                { role: "start", x: Number(element.x1), y: Number(element.y1) },
                { role: "end", x: Number(element.x2), y: Number(element.y2) },
            ];
        }
        if (element.type === "rectangle") {
            const x = Number(element.x), y = Number(element.y), w = Number(element.width), h = Number(element.height);
            return [
                { role: "nw", x, y }, { role: "ne", x: x + w, y },
                { role: "se", x: x + w, y: y + h }, { role: "sw", x, y: y + h },
            ];
        }
        if (element.type === "ellipse") {
            const cx = Number(element.cx), cy = Number(element.cy), rx = Number(element.rx), ry = Number(element.ry);
            return [
                { role: "east", x: cx + rx, y: cy }, { role: "west", x: cx - rx, y: cy },
                { role: "north", x: cx, y: cy - ry }, { role: "south", x: cx, y: cy + ry },
            ];
        }
        if (element.type === "note") return [{ role: "anchor", x: Number(element.x), y: Number(element.y) }];
        return [];
    }

    function outlineMarkup(element) {
        if (!element) return null;
        if (element.type === "line" || element.type === "dimension") {
            return { type: "line", attrs: { x1: element.x1, y1: element.y1, x2: element.x2, y2: element.y2 } };
        }
        if (element.type === "rectangle") return { type: "rect", attrs: { x: element.x, y: element.y, width: element.width, height: element.height } };
        if (element.type === "ellipse") return { type: "ellipse", attrs: { cx: element.cx, cy: element.cy, rx: element.rx, ry: element.ry } };
        return null;
    }

    function pointFromEvent(controller, event) {
        const mapped = baseEditor.clientPointToCanvas(controller.svg, event.clientX, event.clientY);
        return [
            Math.max(0, Math.min(engine.DEFAULT_CANVAS.width, Number(mapped.x))),
            Math.max(0, Math.min(engine.DEFAULT_CANVAS.height, Number(mapped.y))),
        ];
    }

    function updatedElement(element, role, point) {
        const next = clone(element);
        const x = Number(point[0]), y = Number(point[1]);
        if (next.type === "line" || next.type === "dimension") {
            if (role === "start") { next.x1 = x; next.y1 = y; }
            else { next.x2 = x; next.y2 = y; }
            return next;
        }
        if (next.type === "rectangle") {
            const left = Number(next.x), top = Number(next.y), right = left + Number(next.width), bottom = top + Number(next.height);
            const opposite = {
                nw: [right, bottom], ne: [left, bottom], se: [left, top], sw: [right, top],
            }[role];
            if (!opposite) return next;
            const x1 = Math.min(x, opposite[0]), y1 = Math.min(y, opposite[1]);
            const x2 = Math.max(x, opposite[0]), y2 = Math.max(y, opposite[1]);
            next.x = x1; next.y = y1; next.width = Math.max(MIN_SIZE, x2 - x1); next.height = Math.max(MIN_SIZE, y2 - y1);
            return next;
        }
        if (next.type === "ellipse") {
            if (role === "east" || role === "west") next.rx = Math.max(MIN_SIZE, Math.abs(x - Number(next.cx)));
            if (role === "north" || role === "south") next.ry = Math.max(MIN_SIZE, Math.abs(y - Number(next.cy)));
            return next;
        }
        if (next.type === "note" && role === "anchor") {
            next.x = x; next.y = y;
            return next;
        }
        return next;
    }

    function quickRender(controller, element) {
        const overlay = controller.svg.querySelector(".dco-figma-generic-handles");
        if (overlay) overlay.remove();
        render(controller, element);
    }

    function render(controller, overrideElement = null) {
        if (controller.rendering) return;
        controller.rendering = true;
        if (controller.observer) controller.observer.disconnect();
        try {
            const old = controller.svg.querySelector(".dco-figma-generic-handles");
            if (old) old.remove();
            const element = overrideElement || selected(controller);
            if (!element || isExact(element) || element.smart_template_editable) return;
            const handles = handlesFor(element);
            if (!handles.length) return;
            const group = document.createElementNS(SVG_NS, "g");
            group.setAttribute("class", "dco-figma-generic-handles");
            const outline = outlineMarkup(element);
            if (outline) {
                const shape = document.createElementNS(SVG_NS, outline.type);
                shape.setAttribute("class", "dco-figma-generic-outline");
                Object.entries(outline.attrs).forEach(([key, value]) => shape.setAttribute(key, String(value)));
                group.appendChild(shape);
            }
            handles.forEach(handle => {
                const hit = document.createElementNS(SVG_NS, "circle");
                hit.setAttribute("class", "dco-figma-generic-hit"); hit.setAttribute("data-figma-generic-handle", handle.role); hit.setAttribute("cx", String(handle.x)); hit.setAttribute("cy", String(handle.y)); hit.setAttribute("r", "8");
                group.appendChild(hit);
                const dot = document.createElementNS(SVG_NS, "circle");
                dot.setAttribute("class", `dco-figma-generic-dot${controller.drag && controller.drag.role === handle.role ? " is-active" : ""}`); dot.setAttribute("cx", String(handle.x)); dot.setAttribute("cy", String(handle.y)); dot.setAttribute("r", "5.5");
                group.appendChild(dot);
            });
            controller.svg.appendChild(group);
        } finally {
            controller.rendering = false;
            if (controller.observer) controller.observer.observe(controller.svg, { childList: true });
        }
    }

    function refresh(controller) {
        const state = liveState(controller);
        const select = controller.root.querySelector('.dco-sketch-tool[data-tool="select"]');
        if (select) select.click();
        if (history.activateState && state) history.activateState(state);
    }

    function bindDragging(controller) {
        controller.svg.addEventListener("pointerdown", event => {
            const handle = event.target.closest && event.target.closest("[data-figma-generic-handle]");
            if (!handle) return;
            const state = liveState(controller);
            const element = selected(controller);
            if (!state || !element) return;
            controller.drag = { pointerId: event.pointerId, elementId: element.id, role: handle.dataset.figmaGenericHandle, original: clone(state.elements), preview: clone(element) };
            try { controller.svg.setPointerCapture(event.pointerId); } catch (error) { /* optional */ }
            event.preventDefault(); event.stopImmediatePropagation();
        }, true);
        controller.svg.addEventListener("pointermove", event => {
            const drag = controller.drag;
            if (!drag || drag.pointerId !== event.pointerId) return;
            const element = selected(controller);
            if (!element || String(element.id) !== String(drag.elementId)) return;
            drag.preview = updatedElement(element, drag.role, pointFromEvent(controller, event));
            quickRender(controller, drag.preview);
            event.preventDefault(); event.stopImmediatePropagation();
        }, true);
        const finish = event => {
            const drag = controller.drag;
            if (!drag || drag.pointerId !== event.pointerId) return;
            const state = liveState(controller);
            if (event.type !== "pointercancel" && state && drag.preview) {
                const index = state.elements.findIndex(item => String(item && item.id) === String(drag.elementId));
                if (index >= 0) {
                    const transition = history.snapshot(state, drag.original);
                    if (transition && transition.changed) Object.assign(state, transition.patch);
                    const next = clone(state.elements);
                    next[index] = clone(drag.preview);
                    state.elements = next; state.selectedId = drag.elementId; state.hasChanges = true;
                    if (history.activateState) history.activateState(state);
                    refresh(controller);
                }
            }
            controller.drag = null;
            try { controller.svg.releasePointerCapture(event.pointerId); } catch (error) { /* optional */ }
            window.setTimeout(() => render(controller), 0);
            event.preventDefault(); event.stopImmediatePropagation();
        };
        controller.svg.addEventListener("pointerup", finish, true);
        controller.svg.addEventListener("pointercancel", finish, true);
    }

    function mount() {
        installStyles();
        const modal = visibleModal();
        const root = modal && modal.querySelector(".dco-special-sketch-shell.dco-figma-editor");
        const svg = root && root.querySelector(".dco-sketch-paper");
        if (!modal || !root || !svg) return false;
        if (root.dataset.dcoFigmaGenericHandles === "1") return true;
        root.dataset.dcoFigmaGenericHandles = "1";
        const controller = { modal, root, svg, observer: null, rendering: false, drag: null };
        bindDragging(controller);
        svg.addEventListener("pointerdown", () => window.setTimeout(() => render(controller), 0), false);
        controller.observer = new MutationObserver(() => {
            if (controller.rendering) return;
            window.setTimeout(() => render(controller), 0);
        });
        controller.observer.observe(svg, { childList: true });
        render(controller);
        if (window.jQuery) window.jQuery(modal).one("hidden.bs.modal.dco-figma-generic-handles", () => controller.observer && controller.observer.disconnect());
        return true;
    }

    function scheduleMount(attempt = 0) {
        window.setTimeout(() => {
            if (mount()) return;
            if (attempt + 1 < MOUNT_RETRIES) scheduleMount(attempt + 1);
        }, attempt ? 45 : 0);
    }

    function open(frm, row, options = {}) {
        const result = baseEditor.open(frm, row, options);
        if (!options.readOnly) scheduleMount();
        return result;
    }

    function view(frm, row) { return baseEditor.view(frm, row); }

    window.AlmdinaSpecialShapeEditor = Object.freeze({ ...baseEditor, __figmaGenericHandlesIntegrated: true, open, view });
    window.AlmdinaFigmaGenericHandlesUX = Object.freeze({ installStyles, handlesFor, updatedElement, mount });
})();
