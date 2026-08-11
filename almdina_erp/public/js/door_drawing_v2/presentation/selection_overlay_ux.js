(() => {
    "use strict";

    const rootV2 = window.AlmdinaDoorDrawingV2 = window.AlmdinaDoorDrawingV2 || Object.create(null);
    const documents = rootV2.DocumentModel;
    const geometry = rootV2.Geometry;
    const selectionManager = rootV2.SelectionManager;
    const transformManager = rootV2.TransformManager;
    const bridge = rootV2.LegacyRuntimeBridge;
    const baseEditor = window.AlmdinaSpecialShapeEditor;
    const history = window.AlmdinaSketchHistory;
    if (!documents || !geometry || !selectionManager || !transformManager || !bridge || !baseEditor || !history) {
        console.error("Door Drawing V2 selection dependencies are missing");
        return;
    }
    if (baseEditor.__doorDrawingV2SelectionIntegrated) return;

    const SVG_NS = "http://www.w3.org/2000/svg";
    const MOUNT_RETRIES = 28;

    function clone(value) {
        return value == null ? value : JSON.parse(JSON.stringify(value));
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

    function runtime(controller) {
        const state = liveState(controller);
        if (!state) return null;
        const document = bridge.documentFromLegacy(controller.row, state.elements, {
            orderId: controller.frm && controller.frm.doc && controller.frm.doc.name,
        });
        const selectedId = String(state.selectedId || "");
        const object = document.objects.find(item => item.id === selectedId) || null;
        controller.selection = selectionManager.prune(
            document,
            object ? selectionManager.selectOnly(controller.selection, object.id) : selectionManager.clear()
        );
        return { state, document, object };
    }

    function svgPoint(controller, event) {
        const point = baseEditor.clientPointToCanvas(controller.svg, event.clientX, event.clientY);
        return [Number(point.x), Number(point.y)];
    }

    function worldPoint(controller, event) {
        return bridge.canvasPointToWorldMm(controller.row, svgPoint(controller, event));
    }

    function canvasPoint(controller, world) {
        return bridge.worldMmToCanvas(controller.row, world);
    }

    function mm(value, decimals = 1) {
        const number = Number(value);
        if (!Number.isFinite(number)) return "0";
        const factor = 10 ** decimals;
        const rounded = Math.round(number * factor) / factor;
        return Number.isInteger(rounded) ? String(rounded) : String(rounded);
    }

    function currentPreviewObject(controller, fallback) {
        return controller.drag && controller.drag.previewObject
            ? controller.drag.previewObject
            : fallback;
    }

    function labelGroup(x, y, text) {
        const group = document.createElementNS(SVG_NS, "g");
        group.setAttribute("class", "dco-v2-selection-length");
        const width = Math.max(58, String(text).length * 7 + 14);
        const rect = document.createElementNS(SVG_NS, "rect");
        rect.setAttribute("x", String(x - width / 2));
        rect.setAttribute("y", String(y - 26));
        rect.setAttribute("width", String(width));
        rect.setAttribute("height", "22");
        rect.setAttribute("rx", "4");
        const label = document.createElementNS(SVG_NS, "text");
        label.setAttribute("x", String(x));
        label.setAttribute("y", String(y - 15));
        label.textContent = text;
        group.appendChild(rect);
        group.appendChild(label);
        return group;
    }

    function endpointHandle(role, point, active) {
        const group = document.createElementNS(SVG_NS, "g");
        group.setAttribute("data-v2-endpoint", role);
        group.setAttribute("class", `dco-v2-endpoint-handle${active ? " is-active" : ""}`);
        const hit = document.createElementNS(SVG_NS, "circle");
        hit.setAttribute("cx", String(point[0]));
        hit.setAttribute("cy", String(point[1]));
        hit.setAttribute("r", "12");
        hit.setAttribute("class", "dco-v2-endpoint-hit");
        const square = document.createElementNS(SVG_NS, "rect");
        square.setAttribute("x", String(point[0] - 4));
        square.setAttribute("y", String(point[1] - 4));
        square.setAttribute("width", "8");
        square.setAttribute("height", "8");
        square.setAttribute("class", "dco-v2-endpoint-square");
        group.appendChild(hit);
        group.appendChild(square);
        return group;
    }

    function renderInspector(controller, object) {
        if (!controller.inspector) return;
        if (!object || object.type !== "line") {
            if (controller.inspector.dataset.v2Owned === "1") {
                controller.inspector.innerHTML = `<div class="dco-figma-empty"><b>خصائص العنصر</b>حدد مستقيمًا دقيقًا لتعديل قياسه بالـ mm.</div>`;
            }
            return;
        }
        controller.inspector.dataset.v2Owned = "1";
        const length = geometry.lineLength(object.geometry);
        const angle = geometry.lineAngleDeg(object.geometry);
        const start = object.geometry.start;
        const end = object.geometry.end;
        controller.inspector.innerHTML = `
            <div class="dco-v2-inspector-section">
                <div class="dco-v2-inspector-section-title"><span>Line</span><small>EXACT · mm</small></div>
                <div class="dco-v2-inspector-grid">
                    <label><span>الطول</span><div><input type="number" min="0.001" step="1" value="${mm(length, 3)}" data-v2-length><b>mm</b></div></label>
                    <label><span>الزاوية</span><div><input type="number" step="1" value="${mm(angle, 2)}" data-v2-angle><b>°</b></div></label>
                </div>
                <button type="button" class="dco-v2-inspector-apply" data-v2-apply>تطبيق</button>
            </div>
            <div class="dco-v2-inspector-section">
                <div class="dco-v2-inspector-section-title"><span>Position</span><small>mm</small></div>
                <div class="dco-v2-point-row"><span>البداية</span><b>X ${mm(start.x)} · Y ${mm(start.y)}</b></div>
                <div class="dco-v2-point-row"><span>النهاية</span><b>X ${mm(end.x)} · Y ${mm(end.y)}</b></div>
                <div class="dco-v2-inspector-hint">اسحب المربع الأزرق عند أي نهاية. لا توجد حدود مكانية للرسم. Shift يجعل الحركة أفقية أو عمودية.</div>
            </div>`;
    }

    function render(controller) {
        if (controller.rendering) return;
        controller.rendering = true;
        if (controller.observer) controller.observer.disconnect();
        try {
            const existing = controller.svg.querySelector(".dco-v2-selection-overlay");
            if (existing) existing.remove();
            const runtimeState = runtime(controller);
            const rawObject = runtimeState && runtimeState.object;
            const object = currentPreviewObject(controller, rawObject);
            renderInspector(controller, object);
            if (!object || object.type !== "line") return;

            const start = canvasPoint(controller, object.geometry.start);
            const end = canvasPoint(controller, object.geometry.end);
            const group = document.createElementNS(SVG_NS, "g");
            group.setAttribute("class", "dco-v2-selection-overlay");

            const hit = document.createElementNS(SVG_NS, "line");
            hit.setAttribute("x1", String(start[0]));
            hit.setAttribute("y1", String(start[1]));
            hit.setAttribute("x2", String(end[0]));
            hit.setAttribute("y2", String(end[1]));
            hit.setAttribute("class", "dco-v2-selection-move-hit");
            hit.setAttribute("data-v2-move", "1");
            group.appendChild(hit);

            const line = document.createElementNS(SVG_NS, "line");
            line.setAttribute("x1", String(start[0]));
            line.setAttribute("y1", String(start[1]));
            line.setAttribute("x2", String(end[0]));
            line.setAttribute("y2", String(end[1]));
            line.setAttribute("class", "dco-v2-selected-line");
            group.appendChild(line);

            const midpoint = [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2];
            group.appendChild(labelGroup(midpoint[0], midpoint[1], `${mm(geometry.lineLength(object.geometry))} mm`));
            group.appendChild(endpointHandle("start", start, controller.drag && controller.drag.role === "start"));
            group.appendChild(endpointHandle("end", end, controller.drag && controller.drag.role === "end"));
            controller.svg.appendChild(group);
        } finally {
            controller.rendering = false;
            if (controller.observer) controller.observer.observe(controller.svg, { childList: true });
        }
    }

    function commitObject(controller, object, originalElements) {
        const state = liveState(controller);
        if (!state || !object) return false;
        const legacy = state.elements.find(item => String(item.id || "") === String(object.id));
        if (!legacy) return false;
        const replacement = bridge.applyLineObjectToLegacy(object, legacy, controller.row);
        const nextElements = bridge.replaceLegacyElement(state.elements, object.id, replacement);
        const transition = history.snapshot(state, originalElements);
        if (transition && transition.changed) Object.assign(state, transition.patch);
        state.elements = nextElements;
        state.selectedId = object.id;
        state.hasChanges = true;
        if (history.activateState) history.activateState(state);
        const select = controller.root.querySelector('.dco-sketch-tool[data-tool="select"]');
        if (select) select.click();
        if (history.activateState) history.activateState(state);
        window.setTimeout(() => render(controller), 0);
        return true;
    }

    function beginEndpointDrag(controller, event, role) {
        const rt = runtime(controller);
        if (!rt || !rt.object || rt.object.type !== "line") return false;
        controller.drag = {
            type: "endpoint",
            role,
            pointerId: event.pointerId,
            objectId: rt.object.id,
            document: rt.document,
            previewObject: rt.object,
            originalElements: clone(rt.state.elements),
        };
        try { controller.svg.setPointerCapture(event.pointerId); } catch (error) { /* optional */ }
        render(controller);
        return true;
    }

    function beginMoveDrag(controller, event) {
        const rt = runtime(controller);
        if (!rt || !rt.object || rt.object.type !== "line") return false;
        controller.drag = {
            type: "move",
            pointerId: event.pointerId,
            objectId: rt.object.id,
            document: rt.document,
            previewObject: rt.object,
            startWorld: worldPoint(controller, event),
            originalElements: clone(rt.state.elements),
        };
        try { controller.svg.setPointerCapture(event.pointerId); } catch (error) { /* optional */ }
        render(controller);
        return true;
    }

    function updateDrag(controller, event) {
        const drag = controller.drag;
        if (!drag || drag.pointerId !== event.pointerId) return false;
        try {
            let nextDocument;
            if (drag.type === "endpoint") {
                nextDocument = transformManager.setLineEndpoint(
                    drag.document,
                    drag.objectId,
                    drag.role,
                    worldPoint(controller, event),
                    { axisLock: event.shiftKey ? "dominant" : null }
                );
            } else {
                const current = worldPoint(controller, event);
                nextDocument = transformManager.translateSelection(
                    drag.document,
                    [drag.objectId],
                    current.x - drag.startWorld.x,
                    current.y - drag.startWorld.y
                );
            }
            drag.previewObject = nextDocument.objects.find(item => item.id === drag.objectId) || drag.previewObject;
            render(controller);
        } catch (error) {
            // Keep the last valid preview while the pointer crosses a degenerate position.
        }
        return true;
    }

    function finishDrag(controller, event) {
        const drag = controller.drag;
        if (!drag || drag.pointerId !== event.pointerId) return false;
        if (event.type !== "pointercancel" && drag.previewObject) {
            commitObject(controller, drag.previewObject, drag.originalElements);
        }
        controller.drag = null;
        try { controller.svg.releasePointerCapture(event.pointerId); } catch (error) { /* optional */ }
        render(controller);
        return true;
    }

    function applyInspector(controller) {
        const rt = runtime(controller);
        if (!rt || !rt.object || rt.object.type !== "line") return false;
        const length = controller.inspector.querySelector("[data-v2-length]");
        const angle = controller.inspector.querySelector("[data-v2-angle]");
        try {
            const nextDocument = transformManager.setLineLength(rt.document, rt.object.id, Number(length && length.value), {
                anchor: "start",
                angleDeg: Number(angle && angle.value),
            });
            const object = nextDocument.objects.find(item => item.id === rt.object.id);
            return commitObject(controller, object, clone(rt.state.elements));
        } catch (error) {
            if (window.frappe) frappe.show_alert({ message: "تحقق من قيمة الطول والزاوية", indicator: "orange" }, 3);
            return false;
        }
    }

    function bind(controller) {
        controller.svg.addEventListener("pointerdown", event => {
            const endpoint = event.target.closest && event.target.closest("[data-v2-endpoint]");
            const move = event.target.closest && event.target.closest("[data-v2-move]");
            if (!endpoint && !move) {
                window.setTimeout(() => render(controller), 0);
                return;
            }
            const started = endpoint
                ? beginEndpointDrag(controller, event, endpoint.dataset.v2Endpoint)
                : beginMoveDrag(controller, event);
            if (started) {
                event.preventDefault();
                event.stopImmediatePropagation();
            }
        }, true);

        controller.svg.addEventListener("pointermove", event => {
            if (!updateDrag(controller, event)) return;
            event.preventDefault();
            event.stopImmediatePropagation();
        }, true);

        ["pointerup", "pointercancel"].forEach(type => controller.svg.addEventListener(type, event => {
            if (!finishDrag(controller, event)) return;
            event.preventDefault();
            event.stopImmediatePropagation();
        }, true));

        if (controller.inspector) {
            controller.inspector.addEventListener("click", event => {
                if (event.target.closest && event.target.closest("[data-v2-apply]")) applyInspector(controller);
            });
            controller.inspector.addEventListener("keydown", event => {
                if (event.key !== "Enter") return;
                if (!event.target.closest || !event.target.closest("[data-v2-length],[data-v2-angle]")) return;
                event.preventDefault();
                applyInspector(controller);
            });
        }
    }

    function cleanup(controller) {
        if (controller.observer) controller.observer.disconnect();
    }

    function mount(frm, row) {
        const modal = visibleModal();
        if (!modal) return false;
        const root = modal.querySelector(".dco-special-sketch-shell");
        const svg = root && root.querySelector(".dco-sketch-paper");
        const inspector = root && root.querySelector(".dco-figma-selection-properties");
        if (!root || !svg || !inspector) return false;
        if (root.dataset.dcoV2Selection === "1") return true;

        root.dataset.dcoV2Selection = "1";
        const controller = {
            frm,
            row,
            modal,
            root,
            svg,
            inspector,
            selection: selectionManager.clear(),
            observer: null,
            rendering: false,
            drag: null,
        };
        root.__almdinaDoorDrawingV2SelectionController = controller;
        bind(controller);
        controller.observer = new MutationObserver(() => {
            if (controller.rendering) return;
            window.setTimeout(() => render(controller), 0);
        });
        controller.observer.observe(svg, { childList: true });
        render(controller);

        if (window.jQuery) {
            window.jQuery(modal).one("hidden.bs.modal.dco-v2-selection", () => cleanup(controller));
        }
        return true;
    }

    function scheduleMount(frm, row, attempt = 0) {
        window.setTimeout(() => {
            if (mount(frm, row)) return;
            if (attempt + 1 < MOUNT_RETRIES) scheduleMount(frm, row, attempt + 1);
        }, attempt ? 45 : 0);
    }

    function open(frm, row, options = {}) {
        const result = baseEditor.open(frm, row, options);
        if (!options.readOnly) scheduleMount(frm, row);
        return result;
    }

    function view(frm, row) {
        return baseEditor.view(frm, row);
    }

    window.AlmdinaSpecialShapeEditor = Object.freeze({
        ...baseEditor,
        __doorDrawingV2SelectionIntegrated: true,
        open,
        view,
    });

    rootV2.SelectionOverlayUX = Object.freeze({ mount, render });
})();
