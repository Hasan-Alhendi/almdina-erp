(() => {
    "use strict";

    const baseEditor = window.AlmdinaSpecialShapeEditor;
    const history = window.AlmdinaSketchHistory;
    const engine = window.AlmdinaSketchEngine;
    const edgeModel = window.AlmdinaSketchEdgeModel;
    if (!baseEditor || !history || !engine || !edgeModel) {
        console.error("Smart edge dependencies must load before smart template edge UX");
        return;
    }
    if (baseEditor.__smartTemplateEdgesIntegrated) return;

    const STYLE_ID = "dco-smart-template-edge-css";
    const SVG_NS = "http://www.w3.org/2000/svg";
    const MOUNT_RETRIES = 12;
    let sequence = 0;

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-smart-edge-hit{stroke:transparent;stroke-width:18;vector-effect:non-scaling-stroke;cursor:move;pointer-events:stroke}
            .dco-smart-edge-visible{stroke:transparent;stroke-width:3;vector-effect:non-scaling-stroke;pointer-events:none;transition:.1s ease}
            .dco-smart-edge.is-selected .dco-smart-edge-visible{stroke:#7c3aed}
            .dco-smart-edge-mid{fill:#fff;stroke:#64748b;stroke-width:1.8;vector-effect:non-scaling-stroke;cursor:move;filter:drop-shadow(0 1px 2px rgba(15,23,42,.15))}
            .dco-smart-edge:hover .dco-smart-edge-mid,.dco-smart-edge.is-selected .dco-smart-edge-mid{fill:#7c3aed;stroke:#fff;stroke-width:2.4}
            .dco-smart-edge-label{fill:#fff;stroke:#cbd5e1;stroke-width:1;vector-effect:non-scaling-stroke;pointer-events:none}
            .dco-smart-edge-label-text{fill:#475569;font-family:Tahoma,Arial,sans-serif;font-size:11px;font-weight:800;text-anchor:middle;dominant-baseline:central;pointer-events:none}
            .dco-smart-edge-panel{position:absolute;z-index:7;top:24px;right:24px;width:245px;display:none;direction:rtl;border:1px solid #d8e0e7;border-radius:14px;background:rgba(255,255,255,.97);box-shadow:0 12px 34px rgba(15,23,42,.14);backdrop-filter:blur(7px);overflow:hidden}
            .dco-smart-edge-panel.is-visible{display:block}
            .dco-smart-edge-head{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 11px;border-bottom:1px solid #e7ebef;background:#f8fafc}
            .dco-smart-edge-head strong{font-size:11px;color:#172033}
            .dco-smart-edge-badge{padding:4px 7px;border-radius:999px;background:#f1eafe;color:#6d28d9;font-size:8px;font-weight:900}
            .dco-smart-edge-body{padding:10px}
            .dco-smart-edge-help{margin-bottom:9px;color:#64748b;font-size:8.5px;line-height:1.6}
            .dco-smart-edge-length-row{display:grid;grid-template-columns:1fr auto;align-items:end;gap:7px;margin-bottom:8px}
            .dco-smart-edge-field label{display:block;margin-bottom:4px;color:#64748b;font-size:8px;font-weight:800}
            .dco-smart-edge-input-shell{display:flex;align-items:center;border:1px solid #d8e0e7;border-radius:9px;overflow:hidden;background:#fff}
            .dco-smart-edge-input-shell input{width:100%;height:34px;border:0!important;box-shadow:none!important;padding:5px 7px;text-align:center;font-size:12px;font-weight:900}
            .dco-smart-edge-input-shell span{padding:0 7px;border-right:1px solid #e7ebef;color:#718096;font-size:7.5px;white-space:nowrap}
            .dco-smart-edge-apply{height:34px;border:1px solid #cbd5e1;border-radius:9px;background:#fff;color:#334155;padding:0 9px;cursor:pointer;font-size:8px;font-weight:900}
            .dco-smart-edge-apply:hover{border-color:#7c3aed;color:#6d28d9;background:#faf8ff}
            .dco-smart-edge-actions{display:grid;grid-template-columns:1fr 1fr;gap:6px}
            .dco-smart-edge-action{min-height:34px;border:1px solid #d9e0e6;border-radius:9px;background:#fff;color:#334155;cursor:pointer;font-size:8.5px;font-weight:900}
            .dco-smart-edge-action:hover{border-color:#7c3aed;color:#6d28d9;background:#faf8ff}
            .dco-smart-edge-action.is-primary{grid-column:1/-1;border-color:#c4b5fd;background:#f5f3ff;color:#6d28d9}
            .dco-smart-edge-note{margin-top:8px;padding:7px 8px;border-radius:8px;background:#f8fafc;color:#64748b;font-size:7.5px;line-height:1.55}
            @media(max-width:700px){.dco-smart-edge-panel{display:none!important}}
        `;
        document.head.appendChild(style);
    }

    function visibleModal() {
        const modals = Array.from(document.querySelectorAll(".dco-special-shape-modal"));
        return modals.reverse().find(modal =>
            modal.classList.contains("show")
            || modal.style.display === "block"
            || modal.getAttribute("aria-hidden") !== "true"
        ) || null;
    }

    function activeState() {
        return history.getActiveState ? history.getActiveState() : null;
    }

    function selectedTemplate(state) {
        if (!state || state.tool !== "select") return null;
        return (state.elements || []).find(element =>
            String(element && element.id) === String(state.selectedId || "")
            && element.type === "pen"
            && element.smart_template_editable
            && element.smart_template_key
        ) || null;
    }

    function orientationLabel(value) {
        return {
            horizontal: "أفقي",
            vertical: "عمودي",
            angled: "مائل",
        }[value] || "ضلع";
    }

    function svgPoint(svg, event) {
        try {
            const point = svg.createSVGPoint();
            point.x = Number(event.clientX);
            point.y = Number(event.clientY);
            const matrix = svg.getScreenCTM();
            if (matrix) {
                const transformed = point.matrixTransform(matrix.inverse());
                return [transformed.x, transformed.y];
            }
        } catch (error) {
            // Use the bounding box fallback while the modal is resizing.
        }
        const rect = svg.getBoundingClientRect();
        return [
            (Number(event.clientX) - rect.left) * engine.DEFAULT_CANVAS.width / Math.max(1, rect.width),
            (Number(event.clientY) - rect.top) * engine.DEFAULT_CANVAS.height / Math.max(1, rect.height),
        ];
    }

    function refreshThroughEditor(root) {
        const active = root.querySelector(".dco-sketch-tool.is-active")
            || root.querySelector('.dco-sketch-tool[data-tool="select"]');
        if (active) active.click();
    }

    function quickPathUpdate(controller, element) {
        const safeId = String(element.id).replace(/"/g, '\\"');
        const path = controller.svg.querySelector(`[data-element-id="${safeId}"]`);
        if (!path || String(path.tagName).toLowerCase() !== "path") return;
        const d = engine.sanitizePoints(element.points).map((point, index) =>
            `${index ? "L" : "M"} ${point[0].toFixed(1)} ${point[1].toFixed(1)}`
        ).join(" ");
        path.setAttribute("d", d);
    }

    function selectedEdgeValue(controller, state, element) {
        if (!element || controller.edgeIndex === null) return null;
        const value = edgeModel.edge(element.points, controller.edgeIndex);
        if (!value) controller.edgeIndex = null;
        return value;
    }

    function panelHtml(controller, state, element) {
        const value = selectedEdgeValue(controller, state, element);
        if (!value) return "";
        const axis = edgeModel.orientation(element.points, value.index);
        return `
            <div class="dco-smart-edge-head">
                <strong>الضلع ${value.index + 1}</strong>
                <span class="dco-smart-edge-badge">${orientationLabel(axis)}</span>
            </div>
            <div class="dco-smart-edge-body">
                <div class="dco-smart-edge-help">اسحب المقبض البنفسجي في منتصف الضلع لتحريك الضلع كاملًا. الأضلاع الأفقية تتحرك رأسيًا والعمودية تتحرك أفقيًا تلقائيًا.</div>
                <div class="dco-smart-edge-length-row">
                    <div class="dco-smart-edge-field">
                        <label>الطول البصري على الرسم</label>
                        <div class="dco-smart-edge-input-shell"><input type="number" min="4" max="1600" step="1" value="${Math.round(value.length)}" data-smart-edge-length><span>وحدة رسم</span></div>
                    </div>
                    <button type="button" class="dco-smart-edge-apply" data-smart-edge-apply-length>تطبيق</button>
                </div>
                <div class="dco-smart-edge-actions">
                    <button type="button" class="dco-smart-edge-action" data-smart-edge-align="horizontal">↔ جعله أفقيًا</button>
                    <button type="button" class="dco-smart-edge-action" data-smart-edge-align="vertical">↕ جعله عموديًا</button>
                    <button type="button" class="dco-smart-edge-action" data-smart-edge-midpoint>＋ نقطة في المنتصف</button>
                    <button type="button" class="dco-smart-edge-action is-primary" data-smart-edge-dimension>↔ إضافة القياس الحقيقي</button>
                </div>
                <div class="dco-smart-edge-note">«الطول البصري» يغيّر شكل الرسم فقط. القياس الحقيقي يبقى منفصلًا حتى لا يتحول رسم الموظف إلى مسار CNC بالخطأ.</div>
            </div>`;
    }

    function renderPanel(controller, state, element) {
        const visible = Boolean(element && controller.edgeIndex !== null);
        controller.panel.classList.toggle("is-visible", visible);
        controller.panel.innerHTML = visible ? panelHtml(controller, state, element) : "";
    }

    function renderOverlay(controller, force = false) {
        if (controller.rendering) return;
        const state = activeState();
        const element = selectedTemplate(state);
        const existing = controller.svg.querySelector(".dco-smart-template-edges");
        if (existing && !force) {
            renderPanel(controller, state, element);
            return;
        }
        controller.rendering = true;
        try {
            if (existing) existing.remove();
            if (!element) {
                controller.edgeIndex = null;
                renderPanel(controller, state, null);
                return;
            }
            const points = edgeModel.uniqueClosedPoints(element.points);
            if (points.length < 3) return;
            if (controller.edgeIndex !== null) {
                controller.edgeIndex = edgeModel.normalizeIndex(points, controller.edgeIndex);
            }

            const group = document.createElementNS(SVG_NS, "g");
            group.setAttribute("class", "dco-smart-template-edges");
            points.forEach((point, index) => {
                const next = points[(index + 1) % points.length];
                const value = edgeModel.edge(points, index);
                const edgeGroup = document.createElementNS(SVG_NS, "g");
                edgeGroup.setAttribute("class", `dco-smart-edge ${controller.edgeIndex === index ? "is-selected" : ""}`);

                const visible = document.createElementNS(SVG_NS, "line");
                visible.setAttribute("class", "dco-smart-edge-visible");
                visible.setAttribute("x1", point[0]);
                visible.setAttribute("y1", point[1]);
                visible.setAttribute("x2", next[0]);
                visible.setAttribute("y2", next[1]);
                edgeGroup.appendChild(visible);

                const hit = document.createElementNS(SVG_NS, "line");
                hit.setAttribute("class", "dco-smart-edge-hit");
                hit.setAttribute("data-smart-template-edge", String(index));
                hit.setAttribute("x1", point[0]);
                hit.setAttribute("y1", point[1]);
                hit.setAttribute("x2", next[0]);
                hit.setAttribute("y2", next[1]);
                edgeGroup.appendChild(hit);

                const middle = document.createElementNS(SVG_NS, "circle");
                middle.setAttribute("class", "dco-smart-edge-mid");
                middle.setAttribute("data-smart-template-edge", String(index));
                middle.setAttribute("cx", value.midpoint[0]);
                middle.setAttribute("cy", value.midpoint[1]);
                middle.setAttribute("r", controller.edgeIndex === index ? "6" : "4.5");
                edgeGroup.appendChild(middle);

                if (controller.edgeIndex === index) {
                    const labelWidth = 66;
                    const rect = document.createElementNS(SVG_NS, "rect");
                    rect.setAttribute("class", "dco-smart-edge-label");
                    rect.setAttribute("x", value.midpoint[0] - labelWidth / 2);
                    rect.setAttribute("y", value.midpoint[1] - 28);
                    rect.setAttribute("width", labelWidth);
                    rect.setAttribute("height", "19");
                    rect.setAttribute("rx", "6");
                    edgeGroup.appendChild(rect);
                    const text = document.createElementNS(SVG_NS, "text");
                    text.setAttribute("class", "dco-smart-edge-label-text");
                    text.setAttribute("x", value.midpoint[0]);
                    text.setAttribute("y", value.midpoint[1] - 18.5);
                    text.textContent = `${Math.round(value.length)} رسم`;
                    edgeGroup.appendChild(text);
                }
                group.appendChild(edgeGroup);
            });
            const vertexOverlay = controller.svg.querySelector(".dco-smart-template-vertices");
            if (vertexOverlay && vertexOverlay.parentNode === controller.svg) {
                controller.svg.insertBefore(group, vertexOverlay);
            } else {
                controller.svg.appendChild(group);
            }
            renderPanel(controller, state, element);
        } finally {
            controller.rendering = false;
        }
    }

    function commitMutation(controller, mutate) {
        const state = activeState();
        const element = selectedTemplate(state);
        if (!state || !element || controller.edgeIndex === null) return false;
        const originalElements = clone(state.elements);
        const changed = mutate(element, state);
        if (!changed) return false;
        const transition = history.snapshot(state, originalElements);
        if (transition && transition.changed) Object.assign(state, transition.patch);
        state.hasChanges = true;
        refreshThroughEditor(controller.root);
        window.setTimeout(() => renderOverlay(controller, true), 0);
        return true;
    }

    function addRealDimension(controller) {
        const state = activeState();
        const element = selectedTemplate(state);
        const value = selectedEdgeValue(controller, state, element);
        if (!value || !window.frappe) return;
        frappe.prompt(
            [{
                fieldname: "text",
                fieldtype: "Data",
                label: "القياس الحقيقي مع الوحدة",
                reqd: 1,
                default: " سم",
            }],
            values => {
                const text = String(values.text || "").trim();
                if (!text) return;
                const originalElements = clone(state.elements);
                const transition = history.snapshot(state, originalElements);
                if (transition && transition.changed) Object.assign(state, transition.patch);
                sequence += 1;
                state.elements.push({
                    id: `smart-edge-dimension-${Date.now()}-${sequence}`,
                    type: "dimension",
                    x1: value.start[0],
                    y1: value.start[1],
                    x2: value.end[0],
                    y2: value.end[1],
                    text: text.slice(0, 500),
                    color: "#172033",
                });
                state.hasChanges = true;
                refreshThroughEditor(controller.root);
                window.setTimeout(() => renderOverlay(controller, true), 0);
                frappe.show_alert({ message: "تمت إضافة القياس الحقيقي على الضلع.", indicator: "green" });
            },
            "قياس الضلع",
            "إضافة القياس"
        );
    }

    function bindPanel(controller) {
        controller.panel.addEventListener("click", event => {
            const align = event.target.closest && event.target.closest("[data-smart-edge-align]");
            if (align) {
                commitMutation(controller, element => {
                    element.points = edgeModel.alignEdge(
                        element.points,
                        controller.edgeIndex,
                        align.dataset.smartEdgeAlign,
                        engine.DEFAULT_CANVAS
                    );
                    return true;
                });
                return;
            }
            if (event.target.closest && event.target.closest("[data-smart-edge-midpoint]")) {
                commitMutation(controller, element => {
                    element.points = edgeModel.insertMidpoint(element.points, controller.edgeIndex);
                    return true;
                });
                return;
            }
            if (event.target.closest && event.target.closest("[data-smart-edge-apply-length]")) {
                const input = controller.panel.querySelector("[data-smart-edge-length]");
                const length = Number(input && input.value);
                if (!Number.isFinite(length) || length < 4) return;
                commitMutation(controller, element => {
                    element.points = edgeModel.setEdgeLength(
                        element.points,
                        controller.edgeIndex,
                        length,
                        { ...engine.DEFAULT_CANVAS, anchor: "center" }
                    );
                    return true;
                });
                return;
            }
            if (event.target.closest && event.target.closest("[data-smart-edge-dimension]")) {
                addRealDimension(controller);
            }
        });
        controller.panel.addEventListener("keydown", event => {
            if (event.key !== "Enter" || !event.target.matches("[data-smart-edge-length]")) return;
            event.preventDefault();
            const apply = controller.panel.querySelector("[data-smart-edge-apply-length]");
            if (apply) apply.click();
        });
    }

    function bindEdgeDragging(controller) {
        controller.svg.addEventListener("pointerdown", event => {
            if (event.target.closest && event.target.closest("[data-smart-template-vertex]")) return;
            const target = event.target.closest && event.target.closest("[data-smart-template-edge]");
            if (!target) return;
            const state = activeState();
            const element = selectedTemplate(state);
            if (!state || !element) return;
            const index = edgeModel.normalizeIndex(element.points, Number(target.dataset.smartTemplateEdge));
            if (index < 0) return;
            controller.edgeIndex = index;
            const start = svgPoint(controller.svg, event);
            controller.drag = {
                pointerId: event.pointerId,
                elementId: element.id,
                index,
                start,
                originalPoints: clone(element.points),
                originalElements: clone(state.elements),
                moved: false,
            };
            try { controller.svg.setPointerCapture(event.pointerId); } catch (error) { /* optional */ }
            renderOverlay(controller, true);
            event.preventDefault();
            event.stopImmediatePropagation();
        }, true);

        controller.svg.addEventListener("pointermove", event => {
            const drag = controller.drag;
            if (!drag || drag.pointerId !== event.pointerId) return;
            const state = activeState();
            const element = selectedTemplate(state);
            if (!state || !element || String(element.id) !== String(drag.elementId)) return;
            const point = svgPoint(controller.svg, event);
            const rawDx = point[0] - drag.start[0];
            const rawDy = point[1] - drag.start[1];
            const delta = edgeModel.perpendicularDragDelta(
                drag.originalPoints,
                drag.index,
                rawDx,
                rawDy,
                Boolean(event.shiftKey)
            );
            drag.moved = drag.moved || Math.hypot(delta.dx, delta.dy) >= 1.2;
            element.points = edgeModel.moveEdge(
                drag.originalPoints,
                drag.index,
                delta.dx,
                delta.dy,
                engine.DEFAULT_CANVAS
            );
            state.hasChanges = true;
            quickPathUpdate(controller, element);
            renderOverlay(controller, true);
            event.preventDefault();
            event.stopImmediatePropagation();
        }, true);

        const finish = event => {
            const drag = controller.drag;
            if (!drag || drag.pointerId !== event.pointerId) return;
            const state = activeState();
            if (state) {
                if (event.type === "pointercancel") {
                    state.elements = clone(drag.originalElements);
                } else if (drag.moved) {
                    const transition = history.snapshot(state, drag.originalElements);
                    if (transition && transition.changed) Object.assign(state, transition.patch);
                }
            }
            controller.drag = null;
            try { controller.svg.releasePointerCapture(event.pointerId); } catch (error) { /* already released */ }
            refreshThroughEditor(controller.root);
            window.setTimeout(() => renderOverlay(controller, true), 0);
            if (drag.moved && event.type !== "pointercancel") {
                const notice = controller.root.querySelector(".dco-sketch-notice-text");
                if (notice) notice.textContent = "تم تحريك الضلع كاملًا. يمكنك ضبطه أفقيًا/عموديًا أو إضافة قياسه الحقيقي من البطاقة.";
            }
            event.preventDefault();
            event.stopImmediatePropagation();
        };
        controller.svg.addEventListener("pointerup", finish, true);
        controller.svg.addEventListener("pointercancel", finish, true);
    }

    function mount() {
        installStyles();
        const modal = visibleModal();
        if (!modal || modal.classList.contains("dco-special-shape-readonly")) return false;
        const root = modal.querySelector(".dco-special-sketch-shell");
        if (!root || root.dataset.dcoSmartEdges === "1") return Boolean(root);
        const svg = root.querySelector(".dco-sketch-paper");
        const paperWrap = root.querySelector(".dco-sketch-paper-wrap");
        if (!svg || !paperWrap) return false;
        root.dataset.dcoSmartEdges = "1";

        const panel = document.createElement("section");
        panel.className = "dco-smart-edge-panel";
        panel.setAttribute("aria-label", "تحرير الضلع الذكي");
        paperWrap.appendChild(panel);
        const controller = {
            modal,
            root,
            svg,
            panel,
            edgeIndex: null,
            drag: null,
            rendering: false,
            observer: null,
        };
        bindPanel(controller);
        bindEdgeDragging(controller);

        controller.observer = new MutationObserver(() => {
            window.setTimeout(() => renderOverlay(controller), 0);
        });
        controller.observer.observe(svg, { childList: true });
        renderOverlay(controller, true);

        if (window.jQuery) {
            window.jQuery(modal).one("hidden.bs.modal.dco-smart-template-edges", () => {
                if (controller.observer) controller.observer.disconnect();
            });
        }
        return true;
    }

    function scheduleMount(attempt = 0) {
        window.setTimeout(() => {
            if (mount()) return;
            if (attempt + 1 < MOUNT_RETRIES) scheduleMount(attempt + 1);
        }, attempt ? 35 : 0);
    }

    function open(frm, row, options = {}) {
        const result = baseEditor.open(frm, row, options);
        if (!options.readOnly) scheduleMount();
        return result;
    }

    function view(frm, row) {
        return baseEditor.view(frm, row);
    }

    window.AlmdinaSpecialShapeEditor = Object.freeze({
        ...baseEditor,
        __smartTemplateEdgesIntegrated: true,
        open,
        view,
    });
    window.AlmdinaSmartTemplateEdges = Object.freeze({
        installStyles,
        selectedTemplate,
        orientationLabel,
        panelHtml,
        mount,
    });
})();
