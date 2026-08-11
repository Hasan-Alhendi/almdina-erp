(() => {
    "use strict";

    const rootV2 = window.AlmdinaDoorDrawingV2 = window.AlmdinaDoorDrawingV2 || Object.create(null);
    const baseEditor = window.AlmdinaSpecialShapeEditor;
    const history = window.AlmdinaSketchHistory;
    const lineModel = window.AlmdinaExactLineModel;
    if (!baseEditor || !history || !lineModel) {
        console.error("Door Drawing V2 Figma shell dependencies are missing");
        return;
    }
    if (baseEditor.__doorDrawingV2FigmaExactIntegrated) return;

    const STYLE_ID = "dco-door-drawing-v2-figma-exact-css";
    const STYLE_HREF = "/assets/almdina_erp/css/door_drawing_v2_figma_exact.css";
    const MOUNT_RETRIES = 30;

    function ensureStylesheet() {
        if (document.getElementById(STYLE_ID)) return;
        const link = document.createElement("link");
        link.id = STYLE_ID;
        link.rel = "stylesheet";
        link.href = STYLE_HREF;
        document.head.appendChild(link);
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

    function icon(name) {
        const icons = {
            page: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 2.8h7l3 3V17H5z"/><path d="M12 2.8V6h3"/></svg>',
            line: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 15.5 16 4.5"/></svg>',
            arc: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3.5 14.5c3.2-8 9.8-8 13 0"/></svg>',
            rectangle: '<svg viewBox="0 0 20 20" aria-hidden="true"><rect x="4" y="4" width="12" height="12" rx=".5"/></svg>',
            ellipse: '<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="6"/></svg>',
            pen: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="m4 15.5 1.2-4.1 7.9-7.9 3.4 3.4-7.9 7.9z"/><path d="m11.8 4.8 3.4 3.4"/></svg>',
            note: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 4h10M10 4v12M7 16h6"/></svg>',
            dimension: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 10h14M3 7v6M17 7v6M6 8l-3 2 3 2M14 8l3 2-3 2"/></svg>',
            template: '<svg viewBox="0 0 20 20" aria-hidden="true"><rect x="3.5" y="3.5" width="5.5" height="5.5"/><rect x="11" y="3.5" width="5.5" height="5.5"/><rect x="3.5" y="11" width="5.5" height="5.5"/><path d="M11 11h5.5v5.5H11z"/></svg>',
            select: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 2.8 15 10l-5 .8-2.7 4.5z"/></svg>',
            undo: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M7 6H3v-4"/><path d="M3.5 6.2A7 7 0 1 1 5 14.7"/></svg>',
            redo: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M13 6h4v-4"/><path d="M16.5 6.2A7 7 0 1 0 15 14.7"/></svg>',
            reference: '<svg viewBox="0 0 20 20" aria-hidden="true"><rect x="3" y="4" width="14" height="12" rx="1.5"/><circle cx="7" cy="8" r="1.5"/><path d="m5 14 4-4 2.5 2.5 1.5-1.5 2 3"/></svg>',
        };
        return icons[name] || icons.rectangle;
    }

    function elementKind(element) {
        if (lineModel.exactMeta(element)) return "line";
        if (window.AlmdinaExactArcModel && window.AlmdinaExactArcModel.arcMeta(element)) return "arc";
        if (element && element.smart_template_key) return "template";
        const type = String(element && element.type || "").toLowerCase();
        return ["line", "rectangle", "ellipse", "pen", "note", "dimension"].includes(type)
            ? type
            : "rectangle";
    }

    function elementLabel(element, index) {
        const kind = elementKind(element);
        const labels = {
            line: "Line",
            arc: "Arc",
            rectangle: "Rectangle",
            ellipse: "Ellipse",
            pen: "Pen",
            note: "Text",
            dimension: "Dimension",
            template: element && element.smart_template_label ? String(element.smart_template_label) : "Shape",
        };
        return `${labels[kind] || "Object"} ${index + 1}`;
    }

    function leftPanelHtml() {
        return `
            <aside class="dco-v2-left-panel" aria-label="Layers and Assets">
                <div class="dco-v2-left-tabs" role="tablist">
                    <button type="button" class="dco-v2-left-tab is-active" data-v2-figma-tab="layers" role="tab" aria-selected="true">Layers</button>
                    <button type="button" class="dco-v2-left-tab" data-v2-figma-tab="assets" role="tab" aria-selected="false">Assets</button>
                </div>
                <div class="dco-v2-left-content">
                    <div class="dco-v2-left-pane" data-v2-figma-pane="layers">
                        <div class="dco-v2-page-row"><span class="dco-v2-page-icon">${icon("page")}</span><span>Door drawing</span></div>
                        <div data-v2-figma-layers></div>
                    </div>
                    <div class="dco-v2-left-pane" data-v2-figma-pane="assets" hidden>
                        <button type="button" class="dco-v2-asset-row" data-v2-figma-assets="templates"><span class="dco-v2-asset-icon">${icon("template")}</span><span class="dco-v2-asset-name">Templates</span></button>
                        <button type="button" class="dco-v2-asset-row" data-v2-figma-assets="reference"><span class="dco-v2-asset-icon">${icon("reference")}</span><span class="dco-v2-asset-name">Reference image</span></button>
                    </div>
                </div>
                <div class="dco-v2-left-footer">
                    <div class="dco-v2-path-line"><span>Path</span><b data-v2-figma-path-status>—</b></div>
                    <button type="button" class="dco-v2-path-close" data-v2-figma-close-path>إغلاق المسار</button>
                </div>
            </aside>`;
    }

    function patchHeader(controller) {
        controller.modal.classList.add("dco-v2-figma-exact-modal");
        const context = controller.modal.querySelector(".dco-v2-header-context");
        if (!context) return;
        Array.from(context.children).forEach(child => {
            if (!child.classList.contains("dco-v2-mm-badge")) child.textContent = "";
        });
    }

    function patchInspectorHeader(controller) {
        const head = controller.root.querySelector(".dco-figma-properties-head");
        if (!head || head.dataset.v2FigmaExact === "1") return;
        head.dataset.v2FigmaExact = "1";
        head.innerHTML = '<div class="dco-v2-inspector-tabs" aria-label="Inspector"><span class="dco-v2-inspector-tab is-active">Design</span></div>';
    }

    function dockIcon(tool) {
        const map = {
            select: ["select", "Move · V"],
            "exact-line": ["line", "Line · L"],
            pen: ["pen", "Pen · P"],
            rectangle: ["rectangle", "Rectangle · R"],
            ellipse: ["ellipse", "Ellipse · O"],
            dimension: ["dimension", "Dimension · D"],
            note: ["note", "Text · N"],
            templates: ["template", "Templates"],
            undo: ["undo", "Undo · Ctrl+Z"],
            redo: ["redo", "Redo"],
        };
        return map[tool] || ["rectangle", String(tool || "Tool")];
    }

    function patchDock(controller) {
        const dock = controller.paperWrap.querySelector(".dco-figma-dock");
        if (!dock) return false;
        dock.setAttribute("aria-label", "Drawing tools");
        dock.querySelectorAll("[data-figma-tool]").forEach(button => {
            if (button.dataset.v2FigmaIcon === "1") return;
            const [name, title] = dockIcon(button.dataset.figmaTool);
            button.dataset.v2FigmaIcon = "1";
            button.classList.remove("dco-figma-wide");
            button.title = title;
            button.setAttribute("aria-label", title);
            button.innerHTML = icon(name);
        });
        return true;
    }

    function renderLayers(controller) {
        controller.layerRenderPending = false;
        if (!controller.root.isConnected) return;
        const state = liveState(controller);
        const host = controller.leftPanel.querySelector("[data-v2-figma-layers]");
        if (!host || !state) return;
        const elements = Array.isArray(state.elements) ? state.elements : [];
        if (!elements.length) {
            host.innerHTML = '<div class="dco-v2-left-empty">ابدأ بالرسم. ستظهر العناصر هنا كطبقات من دون بطاقات تغطي مساحة العمل.</div>';
            return;
        }
        host.innerHTML = elements.map((element, index) => {
            const selected = String(element && element.id || "") === String(state.selectedId || "");
            const kind = elementKind(element);
            const safeId = String(element.id || "").replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
            return `<button type="button" class="dco-v2-layer-row${selected ? " is-selected" : ""}" data-v2-figma-layer-id="${safeId}">
                <span class="dco-v2-layer-icon">${icon(kind)}</span>
                <span class="dco-v2-layer-name">${elementLabel(element, index)}</span>
                <span class="dco-v2-layer-index">${index + 1}</span>
            </button>`;
        }).join("");
    }

    function scheduleLayers(controller) {
        if (controller.layerRenderPending) return;
        controller.layerRenderPending = true;
        window.requestAnimationFrame(() => renderLayers(controller));
    }

    function selectLayer(controller, id) {
        const state = liveState(controller);
        if (!state || !id) return;
        const exists = state.elements.some(item => String(item && item.id || "") === String(id));
        if (!exists) return;
        const select = controller.root.querySelector('.dco-sketch-tool[data-tool="select"]');
        if (select) select.click();
        state.selectedId = String(id);
        if (history.activateState) history.activateState(state);
        const selectionController = controller.root.__almdinaDoorDrawingV2SelectionController;
        if (selectionController && rootV2.SelectionOverlayUX && typeof rootV2.SelectionOverlayUX.render === "function") {
            rootV2.SelectionOverlayUX.render(selectionController);
        }
        scheduleLayers(controller);
    }

    function syncPathStatus(controller) {
        const status = controller.leftPanel.querySelector("[data-v2-figma-path-status]");
        const close = controller.leftPanel.querySelector("[data-v2-figma-close-path]");
        if (!status || !close) return;
        const badge = controller.root.querySelector(".dco-exact-shape-badge");
        const legacyClose = controller.root.querySelector(".dco-exact-shape-action");
        status.textContent = badge && badge.textContent ? badge.textContent.trim() : "—";
        close.classList.toggle("is-visible", Boolean(legacyClose && !legacyClose.hidden));
    }

    function setTab(controller, name) {
        controller.leftPanel.querySelectorAll("[data-v2-figma-tab]").forEach(tab => {
            const active = tab.dataset.v2FigmaTab === name;
            tab.classList.toggle("is-active", active);
            tab.setAttribute("aria-selected", active ? "true" : "false");
        });
        controller.leftPanel.querySelectorAll("[data-v2-figma-pane]").forEach(pane => {
            pane.hidden = pane.dataset.v2FigmaPane !== name;
        });
    }

    function activateAsset(controller, name) {
        if (name === "templates") {
            const button = controller.paperWrap.querySelector('.dco-figma-dock [data-figma-tool="templates"]')
                || controller.root.querySelector(".dco-drawing-workspace-template-launcher");
            if (button) button.click();
            return;
        }
        if (name === "reference") {
            const button = controller.paperWrap.querySelector("[data-v2-reference-toggle]");
            if (button) button.click();
        }
    }

    function bindLeftPanel(controller) {
        controller.leftPanel.addEventListener("click", event => {
            const tab = event.target.closest && event.target.closest("[data-v2-figma-tab]");
            if (tab) return setTab(controller, tab.dataset.v2FigmaTab);
            const layer = event.target.closest && event.target.closest("[data-v2-figma-layer-id]");
            if (layer) return selectLayer(controller, layer.dataset.v2FigmaLayerId);
            const asset = event.target.closest && event.target.closest("[data-v2-figma-assets]");
            if (asset) return activateAsset(controller, asset.dataset.v2FigmaAssets);
            const close = event.target.closest && event.target.closest("[data-v2-figma-close-path]");
            if (!close) return;
            const legacy = controller.root.querySelector(".dco-exact-shape-action");
            if (legacy && !legacy.hidden) legacy.click();
        });
    }

    function exactLineActive(controller) {
        const button = controller.root.querySelector(".dco-exact-line-tool");
        return Boolean(button && button.classList.contains("is-active"));
    }

    function exactLineCount(state) {
        return state && Array.isArray(state.elements)
            ? state.elements.filter(element => lineModel.exactMeta(element)).length
            : 0;
    }

    function newestExactLine(state, previousCount) {
        if (!state || !Array.isArray(state.elements)) return null;
        const lines = state.elements.filter(element => lineModel.exactMeta(element));
        return lines.length > previousCount ? lines[lines.length - 1] : null;
    }

    function selectCreatedLine(controller, previousCount) {
        const state = liveState(controller);
        const created = newestExactLine(state, previousCount);
        if (!state || !created) return false;
        const select = controller.root.querySelector('.dco-sketch-tool[data-tool="select"]');
        if (select) select.click();
        state.selectedId = String(created.id || "");
        if (history.activateState) history.activateState(state);
        const selectionController = controller.root.__almdinaDoorDrawingV2SelectionController;
        if (selectionController && rootV2.SelectionOverlayUX && typeof rootV2.SelectionOverlayUX.render === "function") {
            rootV2.SelectionOverlayUX.render(selectionController);
        }
        scheduleLayers(controller);
        return true;
    }

    function bindOneShotLine(controller) {
        controller.paperWrap.addEventListener("pointerdown", event => {
            if (!exactLineActive(controller) || !controller.svg.contains(event.target)) return;
            const state = liveState(controller);
            controller.lineGesture = { pointerId: event.pointerId, exactCount: exactLineCount(state) };
        }, false);

        controller.paperWrap.addEventListener("pointerup", event => {
            const gesture = controller.lineGesture;
            if (!gesture || gesture.pointerId !== event.pointerId) return;
            controller.lineGesture = null;
            // V2 commits the drag in a zero-delay callback; select it one frame later.
            window.setTimeout(() => selectCreatedLine(controller, gesture.exactCount), 36);
        }, false);

        controller.paperWrap.addEventListener("pointercancel", event => {
            if (controller.lineGesture && controller.lineGesture.pointerId === event.pointerId) {
                controller.lineGesture = null;
            }
        }, false);
    }

    function bindObservers(controller) {
        controller.svgObserver = new MutationObserver(() => {
            scheduleLayers(controller);
            window.setTimeout(() => syncPathStatus(controller), 0);
        });
        controller.svgObserver.observe(controller.svg, { childList: true });

        const pathCard = controller.root.querySelector(".dco-exact-shape-card");
        if (pathCard) {
            controller.pathObserver = new MutationObserver(() => syncPathStatus(controller));
            controller.pathObserver.observe(pathCard, { childList: true, subtree: true, attributes: true });
        }
    }

    function cleanup(controller) {
        if (controller.svgObserver) controller.svgObserver.disconnect();
        if (controller.pathObserver) controller.pathObserver.disconnect();
    }

    function mount(frm, row) {
        ensureStylesheet();
        const modal = visibleModal();
        if (!modal) return false;
        const root = modal.querySelector(".dco-special-sketch-shell.dco-v2-editor-shell");
        const paperWrap = root && root.querySelector(".dco-sketch-paper-wrap");
        const svg = root && root.querySelector(".dco-sketch-paper");
        const properties = root && root.querySelector(".dco-figma-properties");
        if (!root || !paperWrap || !svg || !properties) return false;
        if (root.dataset.dcoV2FigmaExact === "1") return true;

        root.dataset.dcoV2FigmaExact = "1";
        root.classList.add("dco-v2-figma-exact");
        patchHeader({ modal });
        patchInspectorHeader({ root });
        root.insertAdjacentHTML("afterbegin", leftPanelHtml());

        const controller = {
            frm,
            row,
            modal,
            root,
            paperWrap,
            svg,
            properties,
            leftPanel: root.querySelector(".dco-v2-left-panel"),
            svgObserver: null,
            pathObserver: null,
            lineGesture: null,
            layerRenderPending: false,
        };
        root.__almdinaDoorDrawingV2FigmaExactController = controller;

        patchDock(controller);
        bindLeftPanel(controller);
        bindOneShotLine(controller);
        bindObservers(controller);
        renderLayers(controller);
        syncPathStatus(controller);

        if (window.jQuery) {
            window.jQuery(modal).one("hidden.bs.modal.dco-v2-figma-exact", () => cleanup(controller));
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
        __doorDrawingV2FigmaExactIntegrated: true,
        open,
        view,
    });

    rootV2.FigmaExactShellUX = Object.freeze({
        ensureStylesheet,
        mount,
        renderLayers,
        patchDock,
        selectCreatedLine,
    });
})();
