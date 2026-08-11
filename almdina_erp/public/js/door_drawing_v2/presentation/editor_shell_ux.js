(() => {
    "use strict";

    const rootV2 = window.AlmdinaDoorDrawingV2 = window.AlmdinaDoorDrawingV2 || Object.create(null);
    const precision = rootV2.Precision;
    const viewportModel = rootV2.ViewportModel;
    const baseEditor = window.AlmdinaSpecialShapeEditor;
    if (!precision || !viewportModel || !baseEditor) {
        console.error("Door Drawing V2 viewport dependencies must load before EditorShellUX");
        return;
    }
    if (baseEditor.__doorDrawingV2ShellIntegrated) return;

    const STYLE_ID = "dco-door-drawing-v2-shell-css";
    const STYLE_HREF = "/assets/almdina_erp/css/door_drawing_v2_editor.css";
    const MOUNT_RETRIES = 24;

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
            modal.classList.contains("show")
            || modal.style.display === "block"
            || modal.getAttribute("aria-hidden") !== "true"
        ) || null;
    }

    function rowDimensionsMm(row) {
        return {
            width: Math.max(0, precision.cmToMm(row && row.width_cm)),
            height: Math.max(0, precision.cmToMm(row && row.length_cm)),
        };
    }

    function formattedMm(value) {
        const number = Number(value);
        if (!Number.isFinite(number)) return "0";
        return Number.isInteger(number) ? String(number) : String(precision.display(number));
    }

    function moveFooterActions(controller) {
        const footer = controller.modal.querySelector(".modal-footer");
        const header = controller.modal.querySelector(".modal-header");
        if (!footer || !header) return;
        let actions = header.querySelector(".dco-v2-header-actions");
        if (!actions) {
            actions = document.createElement("div");
            actions.className = "dco-v2-header-actions";
            header.appendChild(actions);
        }
        Array.from(footer.querySelectorAll("button")).forEach(button => {
            if (button.closest(".dco-v2-header-actions")) return;
            actions.appendChild(button);
        });
    }

    function ensureHeaderContext(controller) {
        const header = controller.modal.querySelector(".modal-header");
        if (!header || header.querySelector(".dco-v2-header-context")) return;
        const dimensions = rowDimensionsMm(controller.row);
        const context = document.createElement("div");
        context.className = "dco-v2-header-context";
        context.innerHTML = `
            <span class="dco-v2-mm-badge">${formattedMm(dimensions.width)} × ${formattedMm(dimensions.height)} mm</span>
            <span>Door Drawing V2</span>`;
        const actions = header.querySelector(".dco-v2-header-actions");
        header.insertBefore(context, actions || null);
    }

    function ensureInspectorHeader(controller) {
        const head = controller.root.querySelector(".dco-figma-properties-head");
        if (!head || head.dataset.v2Ready === "1") return;
        head.dataset.v2Ready = "1";
        head.innerHTML = `
            <div class="dco-v2-inspector-tabs" aria-label="وضع الخصائص">
                <span class="dco-v2-inspector-tab is-active">Design</span>
            </div>
            <div class="dco-v2-inspector-heading">
                <span>الخصائص</span>
                <small>mm</small>
            </div>`;
    }

    function ensureCanvasChrome(controller) {
        let chrome = controller.paperWrap.querySelector(".dco-v2-canvas-chrome");
        if (chrome) return chrome;
        const dimensions = rowDimensionsMm(controller.row);
        chrome = document.createElement("div");
        chrome.className = "dco-v2-canvas-chrome";
        chrome.innerHTML = `
            <div class="dco-v2-chrome-group">
                <button type="button" class="dco-v2-canvas-button" data-v2-reference-toggle title="صورة الورقة المرجعية">▧</button>
                <span class="dco-v2-chip is-mm">${formattedMm(dimensions.width)} × ${formattedMm(dimensions.height)} mm</span>
                <span class="dco-v2-chip is-hint">Space + سحب للتحريك · Ctrl + عجلة للتكبير</span>
            </div>
            <div class="dco-v2-chrome-group dco-v2-zoom-host"></div>`;
        controller.paperWrap.appendChild(chrome);

        const zoom = controller.root.querySelector(".dco-sketch-zoom");
        const host = chrome.querySelector(".dco-v2-zoom-host");
        if (zoom && host) {
            host.appendChild(zoom);
            const reset = zoom.querySelector(".dco-sketch-zoom-reset");
            if (reset) reset.title = "ملاءمة الرسم داخل الشاشة";
        }
        return chrome;
    }

    function prepareReferencePanel(controller) {
        const panel = controller.root.querySelector(".dco-reference-panel");
        if (!panel) return;
        panel.classList.add("dco-v2-reference-popover");
        controller.referencePanel = panel;
    }

    function closeReference(controller) {
        if (!controller.referencePanel) return;
        controller.referencePanel.classList.remove("is-v2-open");
        const button = controller.paperWrap.querySelector("[data-v2-reference-toggle]");
        if (button) button.classList.remove("is-active");
    }

    function toggleReference(controller) {
        if (!controller.referencePanel) return;
        const next = !controller.referencePanel.classList.contains("is-v2-open");
        controller.referencePanel.classList.toggle("is-v2-open", next);
        const button = controller.paperWrap.querySelector("[data-v2-reference-toggle]");
        if (button) button.classList.toggle("is-active", next);
    }

    function bindChrome(controller) {
        controller.paperWrap.addEventListener("click", event => {
            const toggle = event.target.closest && event.target.closest("[data-v2-reference-toggle]");
            if (!toggle) return;
            event.preventDefault();
            event.stopPropagation();
            toggleReference(controller);
        });

        controller.documentClickHandler = event => {
            if (!controller.referencePanel || !controller.referencePanel.classList.contains("is-v2-open")) return;
            if (controller.referencePanel.contains(event.target)) return;
            if (event.target.closest && event.target.closest("[data-v2-reference-toggle]")) return;
            closeReference(controller);
        };
        document.addEventListener("pointerdown", controller.documentClickHandler, true);

        controller.keyHandler = event => {
            if (!controller.modal.classList.contains("show") && controller.modal.style.display !== "block") return;
            const target = event.target;
            if (target && (/INPUT|TEXTAREA|SELECT/.test(target.tagName) || target.isContentEditable)) return;
            if (event.shiftKey && event.key === "1") {
                const reset = controller.root.querySelector(".dco-sketch-zoom-reset");
                if (reset) {
                    event.preventDefault();
                    reset.click();
                }
            }
            if (event.key === "Escape") closeReference(controller);
        };
        document.addEventListener("keydown", controller.keyHandler, true);
    }

    function updateViewportState(controller) {
        const dimensions = rowDimensionsMm(controller.row);
        const width = Math.max(1, controller.paperWrap.clientWidth || 1);
        const height = Math.max(1, controller.paperWrap.clientHeight || 1);
        if (!dimensions.width || !dimensions.height) {
            controller.viewport = null;
            return;
        }
        controller.viewport = viewportModel.create({
            viewportWidthPx: width,
            viewportHeightPx: height,
            worldWidthMm: dimensions.width,
            worldHeightMm: dimensions.height,
            paddingPx: Math.max(42, Math.min(90, Math.min(width, height) * 0.08)),
        });
        controller.root.dataset.v2ViewportScale = String(controller.viewport.scale);
        controller.root.dataset.v2ViewportUnits = "mm";
    }

    function bindResize(controller) {
        updateViewportState(controller);
        if (typeof ResizeObserver === "undefined") return;
        controller.resizeObserver = new ResizeObserver(() => updateViewportState(controller));
        controller.resizeObserver.observe(controller.paperWrap);
    }

    function addViewportHint(controller) {
        if (controller.paperWrap.querySelector(".dco-v2-viewport-hint")) return;
        const hint = document.createElement("div");
        hint.className = "dco-v2-viewport-hint";
        hint.textContent = "العرض فقط يتغير مع Zoom؛ القياسات الهندسية تبقى بوحدة mm";
        controller.paperWrap.appendChild(hint);
        window.setTimeout(() => {
            if (hint.isConnected) hint.style.opacity = "0";
        }, 4500);
    }

    function cleanup(controller) {
        if (controller.resizeObserver) controller.resizeObserver.disconnect();
        if (controller.documentClickHandler) document.removeEventListener("pointerdown", controller.documentClickHandler, true);
        if (controller.keyHandler) document.removeEventListener("keydown", controller.keyHandler, true);
    }

    function mount(frm, row) {
        ensureStylesheet();
        const modal = visibleModal();
        if (!modal) return false;
        const root = modal.querySelector(".dco-special-sketch-shell");
        const paperWrap = root && root.querySelector(".dco-sketch-paper-wrap");
        if (!root || !paperWrap) return false;
        if (root.dataset.dcoV2Shell === "1") return true;

        root.dataset.dcoV2Shell = "1";
        root.classList.add("dco-v2-editor-shell");
        modal.classList.add("dco-v2-modal");
        const controller = {
            frm,
            row,
            modal,
            root,
            paperWrap,
            viewport: null,
            referencePanel: null,
            resizeObserver: null,
            documentClickHandler: null,
            keyHandler: null,
        };
        root.__almdinaDoorDrawingV2ShellController = controller;

        moveFooterActions(controller);
        ensureHeaderContext(controller);
        ensureInspectorHeader(controller);
        ensureCanvasChrome(controller);
        prepareReferencePanel(controller);
        bindChrome(controller);
        bindResize(controller);
        addViewportHint(controller);

        if (window.jQuery) {
            window.jQuery(modal).one("hidden.bs.modal.dco-v2-shell", () => cleanup(controller));
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
        scheduleMount(frm, row);
        return result;
    }

    function view(frm, row) {
        const result = baseEditor.view(frm, row);
        scheduleMount(frm, row);
        return result;
    }

    window.AlmdinaSpecialShapeEditor = Object.freeze({
        ...baseEditor,
        __doorDrawingV2ShellIntegrated: true,
        open,
        view,
    });

    root.EditorShellUX = Object.freeze({
        ensureStylesheet,
        mount,
        rowDimensionsMm,
        updateViewportState,
    });
})();
