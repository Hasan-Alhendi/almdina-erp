(() => {
    "use strict";

    const rootV2 = window.AlmdinaDoorDrawingV2 = window.AlmdinaDoorDrawingV2 || Object.create(null);
    const labelGeometry = rootV2.LineLabelGeometry;
    const bridge = rootV2.LegacyRuntimeBridge;
    const baseEditor = window.AlmdinaSpecialShapeEditor;
    if (!labelGeometry || !bridge || !baseEditor) {
        console.error("Door Drawing V2 line UX dependencies are missing");
        return;
    }
    if (baseEditor.__doorDrawingV2LineUXIntegrated) return;

    const SVG_NS = "http://www.w3.org/2000/svg";
    const STYLE_ID = "dco-door-drawing-v2-line-css";
    const STYLE_HREF = "/assets/almdina_erp/css/door_drawing_v2_line.css";
    const MOUNT_RETRIES = 28;
    const DRAG_THRESHOLD_PX = 5;

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

    function number(value, fallback = 0) {
        const parsed = Number(String(value ?? "").trim().replace(",", "."));
        return Number.isFinite(parsed) ? parsed : fallback;
    }

    function rounded(value, decimals = 1) {
        const factor = 10 ** decimals;
        return Math.round(number(value) * factor) / factor;
    }

    function formatMm(value) {
        const numeric = rounded(value, 1);
        return Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(1).replace(/\.0$/, "");
    }

    function formatAngle(value) {
        const numeric = rounded(value, 1);
        return Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(1).replace(/\.0$/, "");
    }

    function isExactActive(controller) {
        return Boolean(controller.exactButton && controller.exactButton.classList.contains("is-active"));
    }

    function legacyInputs(controller) {
        return {
            length: controller.exactHud && controller.exactHud.querySelector("[data-exact-length]"),
            angle: controller.exactHud && controller.exactHud.querySelector("[data-exact-angle]"),
        };
    }

    function dispatchInput(input) {
        if (!input) return;
        input.dispatchEvent(new Event("input", { bubbles: true, cancelable: false }));
    }

    function setLegacyInput(input, value) {
        if (!input) return;
        input.value = String(value ?? "");
        dispatchInput(input);
    }

    function previewLine(controller) {
        return controller.svg.querySelector(".dco-exact-line-overlay .dco-exact-line-preview");
    }

    function previewMetrics(controller) {
        const line = previewLine(controller);
        if (!line) return null;
        const startCanvas = [number(line.getAttribute("x1")), number(line.getAttribute("y1"))];
        const endCanvas = [number(line.getAttribute("x2")), number(line.getAttribute("y2"))];
        try {
            const start = bridge.canvasPointToWorldMm(controller.row, startCanvas);
            const end = bridge.canvasPointToWorldMm(controller.row, endCanvas);
            const dx = end.x - start.x;
            const dy = end.y - start.y;
            const lengthMm = Math.hypot(dx, dy);
            if (!Number.isFinite(lengthMm) || lengthMm <= 0.001) return null;
            return {
                line,
                startCanvas,
                endCanvas,
                start,
                end,
                lengthMm,
                angleDeg: Math.atan2(dy, dx) * 180 / Math.PI,
            };
        } catch (error) {
            return null;
        }
    }

    function createDraftPanel(controller) {
        const panel = document.createElement("section");
        panel.className = "dco-v2-line-draft-panel";
        panel.hidden = true;
        panel.innerHTML = `
            <div class="dco-v2-line-draft-title"><span>Line</span><small>EXACT · mm</small></div>
            <div class="dco-v2-line-draft-grid">
                <label class="dco-v2-line-draft-field">
                    <span>الطول</span>
                    <div class="dco-v2-line-draft-input"><input type="text" inputmode="decimal" autocomplete="off" placeholder="214" data-v2-draft-length><b>mm</b></div>
                </label>
                <label class="dco-v2-line-draft-field">
                    <span>الزاوية</span>
                    <div class="dco-v2-line-draft-input"><input type="number" step="1" value="0" data-v2-draft-angle><b>°</b></div>
                </label>
            </div>
            <div class="dco-v2-line-draft-hint" data-v2-line-hint>اسحب لرسم مستقيم، أو انقر نقطة البداية ثم أدخل الطول.</div>`;
        controller.toolOptions.insertBefore(panel, controller.exactHud || null);
        controller.panel = panel;
        controller.lengthInput = panel.querySelector("[data-v2-draft-length]");
        controller.angleInput = panel.querySelector("[data-v2-draft-angle]");
        controller.hint = panel.querySelector("[data-v2-line-hint]");
    }

    function syncDraftPanel(controller, metrics = previewMetrics(controller)) {
        const active = isExactActive(controller);
        controller.root.classList.toggle("is-v2-line-drawing", active);
        controller.panel.hidden = !active;
        if (!active) return;

        if (!controller.editingLength) {
            controller.lengthInput.value = metrics ? formatMm(metrics.lengthMm) : "";
        }
        if (!controller.editingAngle) {
            controller.angleInput.value = metrics ? formatAngle(metrics.angleDeg) : "0";
        }
        controller.hint.innerHTML = metrics
            ? `<strong>${formatMm(metrics.lengthMm)} mm</strong> · Enter للتثبيت · Shift أفقي/عمودي`
            : "اسحب لرسم مستقيم، أو انقر نقطة البداية ثم أدخل الطول.";
    }

    function measurementGroup(metrics, className, text) {
        const placement = labelGeometry.placement(metrics.startCanvas, metrics.endCanvas, { offsetPx: 18 });
        if (!placement.valid) return null;
        const width = Math.max(46, String(text).length * 6.1 + 14);
        const group = document.createElementNS(SVG_NS, "g");
        group.setAttribute("class", className);
        group.setAttribute("transform", `translate(${placement.x} ${placement.y}) rotate(${placement.angleDeg})`);
        group.setAttribute("pointer-events", "none");

        const rect = document.createElementNS(SVG_NS, "rect");
        rect.setAttribute("x", String(-width / 2));
        rect.setAttribute("y", "-9");
        rect.setAttribute("width", String(width));
        rect.setAttribute("height", "18");
        rect.setAttribute("rx", "3");
        group.appendChild(rect);

        const label = document.createElementNS(SVG_NS, "text");
        label.setAttribute("x", "0");
        label.setAttribute("y", "0");
        label.textContent = text;
        group.appendChild(label);
        return group;
    }

    function renderDraftMeasurement(controller, metrics = previewMetrics(controller)) {
        if (controller.svgObserver) controller.svgObserver.disconnect();
        try {
            const previous = controller.svg.querySelector(".dco-v2-line-draft-measurement");
            if (previous) previous.remove();
            if (!isExactActive(controller) || !metrics) return;
            const group = measurementGroup(metrics, "dco-v2-line-draft-measurement", `${formatMm(metrics.lengthMm)} mm`);
            if (group) controller.svg.appendChild(group);
        } finally {
            if (controller.svgObserver) controller.svgObserver.observe(controller.svg, { childList: true });
        }
    }

    function decorateSelectionMeasurement(controller) {
        const overlay = controller.svg.querySelector(".dco-v2-selection-overlay");
        const line = overlay && overlay.querySelector(".dco-v2-selected-line");
        const label = overlay && overlay.querySelector(".dco-v2-selection-length");
        if (!line || !label) return;
        const start = [number(line.getAttribute("x1")), number(line.getAttribute("y1"))];
        const end = [number(line.getAttribute("x2")), number(line.getAttribute("y2"))];
        const placement = labelGeometry.placement(start, end, { offsetPx: 18 });
        if (!placement.valid) return;
        const rect = label.querySelector("rect");
        const text = label.querySelector("text");
        if (!rect || !text) return;
        const width = Math.max(46, String(text.textContent || "").length * 6.1 + 14);
        label.setAttribute("transform", `translate(${placement.x} ${placement.y}) rotate(${placement.angleDeg})`);
        rect.setAttribute("x", String(-width / 2));
        rect.setAttribute("y", "-9");
        rect.setAttribute("width", String(width));
        rect.setAttribute("height", "18");
        rect.setAttribute("rx", "3");
        text.setAttribute("x", "0");
        text.setAttribute("y", "0");

        overlay.querySelectorAll(".dco-v2-endpoint-square").forEach(square => {
            const handle = square.parentElement;
            const hit = handle && handle.querySelector(".dco-v2-endpoint-hit");
            const cx = hit ? number(hit.getAttribute("cx")) : number(square.getAttribute("x")) + 4;
            const cy = hit ? number(hit.getAttribute("cy")) : number(square.getAttribute("y")) + 4;
            square.setAttribute("x", String(cx - 3));
            square.setAttribute("y", String(cy - 3));
            square.setAttribute("width", "6");
            square.setAttribute("height", "6");
        });
    }

    function refresh(controller) {
        controller.pendingRefresh = false;
        if (!controller.root.isConnected) return;
        const metrics = previewMetrics(controller);
        syncDraftPanel(controller, metrics);
        renderDraftMeasurement(controller, metrics);
        decorateSelectionMeasurement(controller);
    }

    function scheduleRefresh(controller) {
        if (controller.pendingRefresh) return;
        controller.pendingRefresh = true;
        window.requestAnimationFrame(() => refresh(controller));
    }

    function suppressLegacySuccessAlert(callback) {
        if (!window.frappe || typeof frappe.show_alert !== "function") return callback();
        const original = frappe.show_alert;
        frappe.show_alert = function (...args) {
            const payload = args[0];
            const message = typeof payload === "string" ? payload : payload && payload.message;
            if (typeof message === "string" && /^خط\s+.+\s+سم$/.test(message.trim())) return undefined;
            return original.apply(this, args);
        };
        try {
            return callback();
        } finally {
            frappe.show_alert = original;
        }
    }

    function commitDraft(controller, metrics = previewMetrics(controller)) {
        if (!isExactActive(controller)) return false;
        const legacy = legacyInputs(controller);
        const lengthMm = number(controller.lengthInput.value, metrics && metrics.lengthMm);
        const angleDeg = number(controller.angleInput.value, metrics && metrics.angleDeg);
        if (!(lengthMm > 0)) return false;

        setLegacyInput(legacy.length, lengthMm);
        if (Number.isFinite(angleDeg)) setLegacyInput(legacy.angle, angleDeg);
        const event = new KeyboardEvent("keydown", {
            key: "Enter",
            code: "Enter",
            bubbles: true,
            cancelable: true,
        });
        suppressLegacySuccessAlert(() => legacy.length && legacy.length.dispatchEvent(event));
        controller.editingLength = false;
        controller.editingAngle = false;
        controller.lengthInput.value = "";
        scheduleRefresh(controller);
        return true;
    }

    function bindDraftPanel(controller) {
        const legacy = legacyInputs(controller);
        controller.lengthInput.addEventListener("focus", () => {
            controller.editingLength = true;
            controller.lengthInput.select();
        });
        controller.angleInput.addEventListener("focus", () => {
            controller.editingAngle = true;
            controller.angleInput.select();
        });
        controller.lengthInput.addEventListener("input", () => {
            setLegacyInput(legacy.length, controller.lengthInput.value);
            scheduleRefresh(controller);
        });
        controller.angleInput.addEventListener("input", () => {
            setLegacyInput(legacy.angle, controller.angleInput.value);
            scheduleRefresh(controller);
        });
        [controller.lengthInput, controller.angleInput].forEach(input => {
            input.addEventListener("keydown", event => {
                if (event.key !== "Enter") return;
                event.preventDefault();
                event.stopImmediatePropagation();
                commitDraft(controller);
            });
            input.addEventListener("blur", () => {
                if (input === controller.lengthInput) controller.editingLength = false;
                if (input === controller.angleInput) controller.editingAngle = false;
                scheduleRefresh(controller);
            });
        });
    }

    function bindDrawingGesture(controller) {
        controller.paperWrap.addEventListener("pointerdown", event => {
            if (!isExactActive(controller) || !controller.svg.contains(event.target)) return;
            const before = previewMetrics(controller);
            controller.gesture = {
                pointerId: event.pointerId,
                startX: event.clientX,
                startY: event.clientY,
                moved: false,
                hadPreviewBeforeDown: Boolean(before && before.lengthMm > 0.5),
            };
        }, true);

        controller.paperWrap.addEventListener("pointermove", event => {
            const gesture = controller.gesture;
            if (!gesture || gesture.pointerId !== event.pointerId) return;
            if (Math.hypot(event.clientX - gesture.startX, event.clientY - gesture.startY) >= DRAG_THRESHOLD_PX) {
                gesture.moved = true;
            }
        }, true);

        controller.paperWrap.addEventListener("pointerup", event => {
            const gesture = controller.gesture;
            if (!gesture || gesture.pointerId !== event.pointerId) return;
            controller.gesture = null;
            window.setTimeout(() => {
                if (!isExactActive(controller)) return;
                const metrics = previewMetrics(controller);
                if (metrics && (gesture.moved || gesture.hadPreviewBeforeDown)) {
                    controller.lengthInput.value = formatMm(metrics.lengthMm);
                    controller.angleInput.value = formatAngle(metrics.angleDeg);
                    commitDraft(controller, metrics);
                    return;
                }
                controller.lengthInput.focus({ preventScroll: true });
            }, 0);
        }, true);

        controller.paperWrap.addEventListener("pointercancel", event => {
            if (controller.gesture && controller.gesture.pointerId === event.pointerId) controller.gesture = null;
        }, true);
    }

    function bindSelectionInspector(controller) {
        controller.inspector.addEventListener("change", event => {
            const field = event.target && event.target.closest
                ? event.target.closest("[data-v2-length],[data-v2-angle]")
                : null;
            if (!field) return;
            const apply = controller.inspector.querySelector("[data-v2-apply]");
            if (apply) apply.click();
        });
    }

    function bindObservers(controller) {
        controller.svgObserver = new MutationObserver(() => scheduleRefresh(controller));
        controller.svgObserver.observe(controller.svg, { childList: true });
        controller.buttonObserver = new MutationObserver(() => scheduleRefresh(controller));
        controller.buttonObserver.observe(controller.exactButton, { attributes: true, attributeFilter: ["class"] });
    }

    function cleanup(controller) {
        if (controller.svgObserver) controller.svgObserver.disconnect();
        if (controller.buttonObserver) controller.buttonObserver.disconnect();
        controller.root.classList.remove("is-v2-line-drawing");
    }

    function mount(frm, row) {
        ensureStylesheet();
        const modal = visibleModal();
        if (!modal) return false;
        const root = modal.querySelector(".dco-special-sketch-shell.dco-v2-editor-shell");
        const svg = root && root.querySelector(".dco-sketch-paper");
        const paperWrap = root && root.querySelector(".dco-sketch-paper-wrap");
        const toolOptions = root && root.querySelector(".dco-figma-tool-options");
        const inspector = root && root.querySelector(".dco-figma-selection-properties");
        const exactHud = root && root.querySelector(".dco-exact-line-hud");
        const exactButton = root && root.querySelector(".dco-exact-line-tool");
        if (!root || !svg || !paperWrap || !toolOptions || !inspector || !exactHud || !exactButton) return false;
        if (root.dataset.dcoV2LineUx === "1") return true;

        root.dataset.dcoV2LineUx = "1";
        const controller = {
            frm,
            row,
            modal,
            root,
            svg,
            paperWrap,
            toolOptions,
            inspector,
            exactHud,
            exactButton,
            panel: null,
            lengthInput: null,
            angleInput: null,
            hint: null,
            editingLength: false,
            editingAngle: false,
            gesture: null,
            pendingRefresh: false,
            svgObserver: null,
            buttonObserver: null,
        };
        root.__almdinaDoorDrawingV2LineController = controller;
        exactHud.classList.add("dco-v2-legacy-line-controller");
        createDraftPanel(controller);
        bindDraftPanel(controller);
        bindDrawingGesture(controller);
        bindSelectionInspector(controller);
        bindObservers(controller);
        scheduleRefresh(controller);

        if (window.jQuery) {
            window.jQuery(modal).one("hidden.bs.modal.dco-v2-line-ux", () => cleanup(controller));
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
        __doorDrawingV2LineUXIntegrated: true,
        open,
        view,
    });

    rootV2.LineToolUX = Object.freeze({
        ensureStylesheet,
        mount,
        previewMetrics,
        measurementGroup,
    });
})();
