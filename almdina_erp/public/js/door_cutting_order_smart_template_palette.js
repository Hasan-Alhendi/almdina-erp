(() => {
    "use strict";

    const catalog = window.AlmdinaSketchTemplateCatalog;
    const baseEditor = window.AlmdinaSpecialShapeEditor;
    const history = window.AlmdinaSketchHistory;
    const engine = window.AlmdinaSketchEngine;
    const smartGuides = window.AlmdinaSketchSmartGuides;
    if (!catalog || !baseEditor || !history || !engine || !smartGuides) {
        console.error("Smart template dependencies must load before smart template palette");
        return;
    }
    if (baseEditor.__smartTemplatePaletteIntegrated) return;

    const STYLE_ID = "dco-smart-template-palette-css";
    const MOUNT_RETRIES = 12;
    const SVG_NS = "http://www.w3.org/2000/svg";

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function esc(value) {
        if (window.frappe && frappe.utils && frappe.utils.escape_html) {
            return frappe.utils.escape_html(String(value ?? ""));
        }
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-smart-template-palette{margin:3px 0 5px;padding:8px;border:1px solid var(--border-color,#dce3e8);border-radius:11px;background:var(--subtle-fg,#f8fafb)}
            .dco-smart-template-head{display:flex;align-items:center;justify-content:space-between;gap:6px;margin-bottom:7px}
            .dco-smart-template-head strong{font-size:10px;color:var(--text-color,#172033)}
            .dco-smart-template-head span{font-size:8px;color:var(--text-muted,#71808e)}
            .dco-smart-template-list{display:grid;grid-template-columns:1fr 1fr;gap:5px;max-height:228px;overflow:auto;padding:1px}
            .dco-smart-template-card{display:flex;align-items:center;gap:6px;min-height:43px;padding:5px 6px;border:1px solid #dce3e8;border-radius:9px;background:#fff;color:inherit;cursor:pointer;text-align:right;transition:.12s ease}
            .dco-smart-template-card:hover{border-color:#2490ef;background:#f4faff;box-shadow:0 0 0 2px rgba(36,144,239,.07)}
            .dco-smart-template-card-icon{display:grid;place-items:center;width:25px;height:25px;border-radius:7px;background:#edf5fb;color:#1769aa;font-size:15px;font-weight:900;flex:0 0 auto}
            .dco-smart-template-card strong{display:block;font-size:8.5px;line-height:1.2}
            .dco-smart-template-card small{display:block;margin-top:2px;font-size:7px;line-height:1.15;color:#71808e}
            .dco-smart-template-more{width:100%;margin-top:6px;min-height:30px;border:1px dashed #b8c5cf;border-radius:8px;background:#fff;color:#36566c;cursor:pointer;font-size:8.5px;font-weight:900}
            .dco-smart-template-more:hover{border-color:#2490ef;color:#1769aa;background:#f7fbff}
            .dco-smart-template-palette:not(.is-expanded) .dco-smart-template-card[data-common="0"]{display:none}
            .dco-sketch-template-grid.dco-smart-template-proxy{display:none!important}
            .dco-sketch-snap-point{filter:drop-shadow(0 0 3px rgba(21,142,91,.32))}
            .dco-special-shape-modal .dco-smart-axis-guide{animation:dco-smart-guide-in .12s ease-out}
            .dco-smart-template-vertex{fill:#fff;stroke:#2490ef;stroke-width:2.4;vector-effect:non-scaling-stroke;cursor:grab;filter:drop-shadow(0 2px 3px rgba(23,105,170,.2))}
            .dco-smart-template-vertex:hover,.dco-smart-template-vertex.is-active{fill:#2490ef;stroke:#fff;stroke-width:3}
            .dco-smart-template-guide{stroke:#2490ef;stroke-width:1.4;stroke-dasharray:7 6;opacity:.75;vector-effect:non-scaling-stroke;pointer-events:none}
            .dco-smart-template-guide-label{fill:#2490ef;font-family:Tahoma,Arial,sans-serif;font-size:12px;font-weight:800;pointer-events:none}
            .dco-smart-template-hint{position:absolute;top:22px;left:50%;transform:translateX(-50%);z-index:4;display:none;align-items:center;gap:6px;padding:6px 10px;border:1px solid rgba(36,144,239,.28);border-radius:999px;background:rgba(255,255,255,.94);box-shadow:0 5px 16px rgba(31,71,103,.1);color:#24526f;font-size:9px;font-weight:800;pointer-events:none}
            .dco-smart-template-hint.is-visible{display:flex}
            .dco-smart-template-hint b{color:#1674c5}
            @keyframes dco-smart-guide-in{from{opacity:.25}to{opacity:1}}
            @media(max-width:700px){.dco-smart-template-palette{display:none}.dco-smart-template-hint{top:14px;white-space:nowrap}}
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

    function cardHtml(item) {
        return `<button type="button" class="dco-smart-template-card" data-smart-template="${esc(item.key)}" data-common="${item.common ? "1" : "0"}" title="${esc(item.hint)}">
            <span class="dco-smart-template-card-icon" aria-hidden="true">${esc(item.icon)}</span>
            <span><strong>${esc(item.label)}</strong><small>${esc(item.hint)}</small></span>
        </button>`;
    }

    function panelHtml() {
        return `<section class="dco-smart-template-palette" aria-label="قوالب الدرف الذكية">
            <div class="dco-smart-template-head"><strong>قوالب ذكية</strong><span>اختر ثم عدّل بالنقاط</span></div>
            <div class="dco-smart-template-list">${catalog.all().map(cardHtml).join("")}</div>
            <button type="button" class="dco-smart-template-more">عرض كل القوالب</button>
        </section>`;
    }

    function proxyTemplateClick(grid, key) {
        const proxy = grid.querySelector(".dco-sketch-template");
        if (!proxy) return false;
        const previous = proxy.dataset.template;
        proxy.dataset.template = key;
        try {
            proxy.click();
            return true;
        } finally {
            proxy.dataset.template = previous;
        }
    }

    function selectTool(root, tool) {
        const button = root.querySelector(`.dco-sketch-tool[data-tool="${tool}"]`);
        if (!button) return false;
        button.click();
        return true;
    }

    function selectedElement(state) {
        if (!state) return null;
        return (state.elements || []).find(element =>
            String(element && element.id) === String(state.selectedId || "")
        ) || null;
    }

    function editableTemplate(state) {
        const element = selectedElement(state);
        return element
            && element.type === "pen"
            && element.smart_template_editable
            && element.smart_template_key
            ? element
            : null;
    }

    function markSelectedTemplate(state, key) {
        const element = selectedElement(state);
        const item = catalog.find(key);
        if (!element || element.type !== "pen" || !item) return null;
        element.smart_template_key = catalog.resolveKey(key);
        element.smart_template_label = item.label;
        element.smart_template_editable = 1;
        element.smart_template_version = 1;
        state.hasChanges = true;
        return element;
    }

    function refreshThroughEditor(root) {
        const active = root.querySelector(".dco-sketch-tool.is-active")
            || root.querySelector('.dco-sketch-tool[data-tool="select"]');
        if (active) active.click();
    }

    function svgPoint(svg, event) {
        try {
            const point = svg.createSVGPoint();
            point.x = Number(event.clientX);
            point.y = Number(event.clientY);
            const matrix = svg.getScreenCTM();
            if (matrix) {
                const transformed = point.matrixTransform(matrix.inverse());
                return [
                    Math.max(0, Math.min(engine.DEFAULT_CANVAS.width, transformed.x)),
                    Math.max(0, Math.min(engine.DEFAULT_CANVAS.height, transformed.y)),
                ];
            }
        } catch (error) {
            // Fall through to bounding-rect conversion while the SVG is resizing.
        }
        const rect = svg.getBoundingClientRect();
        return [
            Math.max(0, Math.min(engine.DEFAULT_CANVAS.width,
                (Number(event.clientX) - rect.left) * engine.DEFAULT_CANVAS.width / Math.max(1, rect.width))),
            Math.max(0, Math.min(engine.DEFAULT_CANVAS.height,
                (Number(event.clientY) - rect.top) * engine.DEFAULT_CANVAS.height / Math.max(1, rect.height))),
        ];
    }

    function externalAnchors(state, selectedId) {
        const anchors = [];
        (state.elements || []).forEach(element => {
            if (String(element.id) === String(selectedId)) return;
            engine.elementAnchorPoints(element).forEach(point => anchors.push(point));
        });
        return anchors;
    }

    function quickPathUpdate(controller, element) {
        const path = controller.svg.querySelector(`[data-element-id="${String(element.id).replace(/"/g, '\\"')}"]`);
        if (!path || String(path.tagName).toLowerCase() !== "path") return;
        const d = engine.sanitizePoints(element.points).map((point, index) =>
            `${index ? "L" : "M"} ${point[0].toFixed(1)} ${point[1].toFixed(1)}`
        ).join(" ");
        path.setAttribute("d", d);
    }

    function updateHint(controller, state) {
        const hint = controller.hint;
        if (!hint) return;
        const element = editableTemplate(state);
        const visible = Boolean(element) && state.tool === "select";
        hint.classList.toggle("is-visible", visible);
        if (visible) {
            hint.innerHTML = `<span>●</span><span><b>${esc(element.smart_template_label || "قالب")}</b> — اسحب النقاط الزرقاء · Shift يحصر الحركة أفقيًا/عموديًا</span>`;
        }
    }

    function renderVertexOverlay(controller, force = false) {
        if (controller.renderingOverlay) return;
        const state = history.getActiveState && history.getActiveState();
        if (!state) return;
        const existing = controller.svg.querySelector(".dco-smart-template-vertices");
        if (existing && !force) {
            updateHint(controller, state);
            return;
        }
        controller.renderingOverlay = true;
        try {
            if (existing) existing.remove();
            updateHint(controller, state);
            const element = editableTemplate(state);
            if (!element || state.tool !== "select") return;
            const points = smartGuides.uniqueClosedPoints(element.points);
            if (points.length < 3) return;

            const group = document.createElementNS(SVG_NS, "g");
            group.setAttribute("class", "dco-smart-template-vertices");
            const guides = state.__smartTemplateGuides || {};
            if (Number.isFinite(guides.x)) {
                const line = document.createElementNS(SVG_NS, "line");
                line.setAttribute("class", "dco-smart-template-guide");
                line.setAttribute("x1", String(guides.x));
                line.setAttribute("x2", String(guides.x));
                line.setAttribute("y1", "0");
                line.setAttribute("y2", String(engine.DEFAULT_CANVAS.height));
                group.appendChild(line);
            }
            if (Number.isFinite(guides.y)) {
                const line = document.createElementNS(SVG_NS, "line");
                line.setAttribute("class", "dco-smart-template-guide");
                line.setAttribute("x1", "0");
                line.setAttribute("x2", String(engine.DEFAULT_CANVAS.width));
                line.setAttribute("y1", String(guides.y));
                line.setAttribute("y2", String(guides.y));
                group.appendChild(line);
            }
            points.forEach((point, index) => {
                const circle = document.createElementNS(SVG_NS, "circle");
                circle.setAttribute("class", `dco-smart-template-vertex ${controller.drag && controller.drag.index === index ? "is-active" : ""}`);
                circle.setAttribute("data-smart-template-vertex", String(index));
                circle.setAttribute("cx", String(point[0]));
                circle.setAttribute("cy", String(point[1]));
                circle.setAttribute("r", "7");
                circle.setAttribute("aria-label", `نقطة تعديل ${index + 1}`);
                group.appendChild(circle);
            });
            controller.svg.appendChild(group);
        } finally {
            controller.renderingOverlay = false;
        }
    }

    function bindVertexEditing(controller) {
        const stateForEvent = () => history.getActiveState && history.getActiveState();

        controller.svg.addEventListener("pointerdown", event => {
            const handle = event.target.closest && event.target.closest("[data-smart-template-vertex]");
            if (!handle) return;
            const state = stateForEvent();
            const element = editableTemplate(state);
            if (!state || !element || state.tool !== "select") return;
            const index = Number(handle.dataset.smartTemplateVertex);
            const points = smartGuides.uniqueClosedPoints(element.points);
            if (!points[index]) return;
            controller.drag = {
                pointerId: event.pointerId,
                elementId: element.id,
                index,
                originalPoint: points[index].slice(),
                originalElements: clone(state.elements),
                externalAnchors: externalAnchors(state, element.id),
                moved: false,
            };
            state.__smartTemplateGuides = {};
            try { controller.svg.setPointerCapture(event.pointerId); } catch (error) { /* optional */ }
            renderVertexOverlay(controller, true);
            event.preventDefault();
            event.stopImmediatePropagation();
        }, true);

        controller.svg.addEventListener("pointermove", event => {
            const drag = controller.drag;
            if (!drag || drag.pointerId !== event.pointerId) return;
            const state = stateForEvent();
            const element = selectedElement(state);
            if (!state || !element || String(element.id) !== String(drag.elementId)) return;
            const rawPoint = svgPoint(controller.svg, event);
            const threshold = Math.max(5, smartGuides.DEFAULT_VERTEX_SNAP_THRESHOLD / Math.max(1, Number(state.zoom) || 1));
            const resolved = smartGuides.snapTemplateVertex(
                element.points,
                drag.index,
                rawPoint,
                {
                    originalPoint: drag.originalPoint,
                    shiftKey: Boolean(event.shiftKey),
                    threshold,
                    width: engine.DEFAULT_CANVAS.width,
                    height: engine.DEFAULT_CANVAS.height,
                    externalAnchors: drag.externalAnchors,
                }
            );
            const previous = smartGuides.uniqueClosedPoints(element.points)[drag.index];
            drag.moved = drag.moved || !previous
                || Math.hypot(resolved.point[0] - previous[0], resolved.point[1] - previous[1]) > 0.15;
            element.points = smartGuides.applyClosedVertex(element.points, drag.index, resolved.point);
            state.__smartTemplateGuides = resolved.guides;
            state.hasChanges = true;
            quickPathUpdate(controller, element);
            renderVertexOverlay(controller, true);
            event.preventDefault();
            event.stopImmediatePropagation();
        }, true);

        const finish = event => {
            const drag = controller.drag;
            if (!drag || drag.pointerId !== event.pointerId) return;
            const state = stateForEvent();
            if (state) {
                if (event.type === "pointercancel") {
                    state.elements = clone(drag.originalElements);
                } else if (drag.moved) {
                    const transition = history.snapshot(state, drag.originalElements);
                    if (transition && transition.changed) Object.assign(state, transition.patch);
                }
                state.__smartTemplateGuides = {};
            }
            controller.drag = null;
            try { controller.svg.releasePointerCapture(event.pointerId); } catch (error) { /* already released */ }
            refreshThroughEditor(controller.root);
            renderVertexOverlay(controller, true);
            const notice = controller.root.querySelector(".dco-sketch-notice-text");
            if (notice && drag.moved && event.type !== "pointercancel") {
                notice.textContent = "تم تعديل القالب. النقاط تلتقط المحاور والزوايا القريبة تلقائيًا؛ أضف القياسات الحقيقية بعد مطابقة الشكل.";
            }
            event.preventDefault();
            event.stopImmediatePropagation();
        };
        controller.svg.addEventListener("pointerup", finish, true);
        controller.svg.addEventListener("pointercancel", finish, true);
    }

    function bindShortcuts(modal, root) {
        if (modal.dataset.dcoSmartShortcuts === "1") return;
        modal.dataset.dcoSmartShortcuts = "1";
        const handler = event => {
            if (!modal.classList.contains("show") && modal.style.display !== "block") return;
            const target = event.target;
            if (target && (/INPUT|TEXTAREA|SELECT/.test(target.tagName) || target.isContentEditable)) return;
            if (event.ctrlKey || event.metaKey || event.altKey) return;
            const tool = {
                l: "line",
                r: "rectangle",
                o: "ellipse",
                d: "dimension",
                n: "note",
            }[String(event.key || "").toLowerCase()];
            if (!tool) return;
            if (selectTool(root, tool)) event.preventDefault();
        };
        document.addEventListener("keydown", handler, true);
        const cleanup = () => document.removeEventListener("keydown", handler, true);
        if (window.jQuery) {
            window.jQuery(modal).one("hidden.bs.modal.dco-smart-template-shortcuts", cleanup);
        } else {
            modal.addEventListener("hidden.bs.modal", cleanup, { once: true });
        }
    }

    function mount(row) {
        installStyles();
        const modal = visibleModal();
        if (!modal || modal.classList.contains("dco-special-shape-readonly")) return false;
        const root = modal.querySelector(".dco-special-sketch-shell");
        if (!root) return false;
        const grid = root.querySelector(".dco-sketch-template-grid");
        const svg = root.querySelector(".dco-sketch-paper");
        const paperWrap = root.querySelector(".dco-sketch-paper-wrap");
        if (!grid || !svg || !paperWrap) return false;
        if (root.querySelector(".dco-smart-template-palette")) return true;

        const wrapper = document.createElement("div");
        wrapper.innerHTML = panelHtml();
        const panel = wrapper.firstElementChild;
        grid.classList.add("dco-smart-template-proxy");
        grid.parentNode.insertBefore(panel, grid);

        const hint = document.createElement("div");
        hint.className = "dco-smart-template-hint";
        paperWrap.appendChild(hint);
        const controller = {
            modal,
            root,
            svg,
            hint,
            drag: null,
            renderingOverlay: false,
            observer: null,
        };

        panel.addEventListener("click", event => {
            const more = event.target.closest && event.target.closest(".dco-smart-template-more");
            if (more) {
                panel.classList.toggle("is-expanded");
                more.textContent = panel.classList.contains("is-expanded")
                    ? "عرض الأكثر استخدامًا فقط"
                    : "عرض كل القوالب";
                return;
            }
            const button = event.target.closest && event.target.closest("[data-smart-template]");
            if (!button) return;
            const key = button.dataset.smartTemplate;
            if (!proxyTemplateClick(grid, key)) return;
            const state = history.getActiveState && history.getActiveState();
            const item = catalog.find(key);
            markSelectedTemplate(state, key);
            refreshThroughEditor(root);
            renderVertexOverlay(controller, true);
            const notice = root.querySelector(".dco-sketch-notice-text");
            if (notice && item) {
                notice.textContent = `تمت إضافة «${item.label}». اسحب النقاط الزرقاء حتى تطابق صورة المرجع؛ المحاذاة والالتقاط يعملان تلقائيًا.`;
            }
        });

        bindVertexEditing(controller);
        controller.observer = new MutationObserver(() => {
            window.setTimeout(() => renderVertexOverlay(controller), 0);
        });
        controller.observer.observe(svg, { childList: true });
        renderVertexOverlay(controller, true);

        const keyHint = root.querySelector(".dco-sketch-key-hint");
        if (keyHint) {
            keyHint.textContent = "Shift: أفقي/عمودي · نقاط القالب مغناطيسية · L خط · R مستطيل · O دائرة · Ctrl + عجلة: تكبير";
        }
        const lineTool = root.querySelector('.dco-sketch-tool[data-tool="line"] small');
        if (lineTool) lineTool.textContent = "Shift يقفل أفقي/عمودي + Snap للنهايات";
        bindShortcuts(modal, root);

        if (window.jQuery) {
            window.jQuery(modal).one("hidden.bs.modal.dco-smart-template-vertices", () => {
                if (controller.observer) controller.observer.disconnect();
                const state = history.getActiveState && history.getActiveState();
                if (state) delete state.__smartTemplateGuides;
            });
        }
        return true;
    }

    function scheduleMount(row, attempt = 0) {
        window.setTimeout(() => {
            if (mount(row)) return;
            if (attempt + 1 < MOUNT_RETRIES) scheduleMount(row, attempt + 1);
        }, attempt ? 35 : 0);
    }

    function open(frm, row, options = {}) {
        const result = baseEditor.open(frm, row, options);
        if (!options.readOnly) scheduleMount(row);
        return result;
    }

    function view(frm, row) {
        return baseEditor.view(frm, row);
    }

    window.AlmdinaSpecialShapeEditor = Object.freeze({
        ...baseEditor,
        __smartTemplatePaletteIntegrated: true,
        open,
        view,
    });
    window.AlmdinaSmartTemplatePalette = Object.freeze({
        installStyles,
        panelHtml,
        proxyTemplateClick,
        markSelectedTemplate,
        renderVertexOverlay,
        mount,
    });
})();