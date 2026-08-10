(() => {
    "use strict";

    const baseEditor = window.AlmdinaSpecialShapeEditor;
    const history = window.AlmdinaSketchHistory;
    const lineModel = window.AlmdinaExactLineModel;
    const editModel = window.AlmdinaExactLineEditModel;
    if (!baseEditor || !history || !lineModel || !editModel) {
        console.error("Exact-line inspector dependencies must load before inspector UX");
        return;
    }
    if (baseEditor.__exactLineInspectorIntegrated) return;

    const STYLE_ID = "dco-exact-line-inspector-css";
    const MOUNT_RETRIES = 14;

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-exact-line-inspector{position:absolute;z-index:9;top:20px;right:20px;width:300px;display:none;direction:rtl;border:1px solid #cbd9e4;border-radius:14px;background:rgba(255,255,255,.985);box-shadow:0 12px 36px rgba(15,23,42,.15);backdrop-filter:blur(8px);overflow:hidden}
            .dco-exact-line-inspector.is-visible{display:block}
            .dco-exact-inspector-head{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 11px;background:#f6f9fb;border-bottom:1px solid #e3e9ee}
            .dco-exact-inspector-head strong{font-size:10px;color:#183c56}.dco-exact-inspector-head span{padding:4px 7px;border-radius:999px;background:#e7f6ef;color:#12633f;font-size:7.5px;font-weight:900}
            .dco-exact-inspector-body{padding:10px}.dco-exact-inspector-status{margin-bottom:8px;padding:7px 8px;border-radius:9px;background:#f8fafc;color:#5b6e7b;font-size:8px;line-height:1.55}
            .dco-exact-inspector-status.is-error{background:#fff1ef;color:#a33126}.dco-exact-inspector-status.is-success{background:#edf9f3;color:#12633f}
            .dco-exact-inspector-section{padding:8px;border:1px solid #e1e7ec;border-radius:10px;margin-bottom:8px}.dco-exact-inspector-section-title{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:7px;font-size:8.5px;font-weight:900;color:#38556a}
            .dco-exact-inspector-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}.dco-exact-inspector-field label{display:block;margin-bottom:3px;color:#6b7b87;font-size:7px;font-weight:900}
            .dco-exact-inspector-shell{display:flex;align-items:center;border:1px solid #d7e0e6;border-radius:8px;overflow:hidden;background:#fff}.dco-exact-inspector-shell input{min-width:0;width:100%;height:34px;border:0!important;box-shadow:none!important;padding:5px 6px;text-align:center;font-size:11px;font-weight:900;color:#172033}.dco-exact-inspector-shell span{padding:0 6px;border-right:1px solid #e6ebef;color:#6b7b87;font-size:7px}
            .dco-exact-inspector-anchor,.dco-exact-inspector-axis{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-top:6px}.dco-exact-inspector-anchor button,.dco-exact-inspector-axis button,.dco-exact-inspector-apply{min-height:32px;border:1px solid #d6e0e7;border-radius:8px;background:#fff;color:#334155;cursor:pointer;font-size:7.8px;font-weight:900}.dco-exact-inspector-anchor button:hover,.dco-exact-inspector-axis button:hover,.dco-exact-inspector-apply:hover{border-color:#2490ef;color:#0e639d;background:#f4faff}.dco-exact-inspector-anchor button.is-active{border-color:#2490ef;background:#e9f6ff;color:#0e639d}
            .dco-exact-inspector-apply{width:100%;margin-top:6px;background:#1769aa;border-color:#1769aa;color:#fff}.dco-exact-inspector-apply:hover{background:#0f5f92!important;color:#fff!important}
            .dco-exact-inspector-link{display:flex;align-items:flex-start;gap:6px;padding:6px 7px;margin-top:6px;border-radius:8px;background:#f8fafc;color:#64748b;font-size:7.2px;line-height:1.45}.dco-exact-inspector-link input{margin-top:1px;accent-color:#1769aa}
            .dco-exact-inspector-summary{display:flex;align-items:center;justify-content:space-between;gap:8px;color:#64748b;font-size:7.5px}.dco-exact-inspector-summary b{color:#23465f;font-variant-numeric:tabular-nums}
            @media(max-width:700px){.dco-exact-line-inspector{left:12px;right:12px;top:12px;width:auto;max-height:calc(100vh - 110px);overflow:auto}}
        `;
        document.head.appendChild(style);
    }

    function visibleModal() {
        const modals = Array.from(document.querySelectorAll(".dco-special-shape-modal"));
        return modals.reverse().find(modal =>
            !modal.classList.contains("dco-special-shape-readonly")
            && (modal.classList.contains("show") || modal.style.display === "block")
        ) || null;
    }

    function liveState(controller) {
        const state = history.getActiveState ? history.getActiveState() : null;
        return state && state.root === controller.root && state.svg === controller.svg ? state : null;
    }

    function selectedExactLine(controller) {
        const state = liveState(controller);
        if (!state || state.tool !== "select") return null;
        const element = (state.elements || []).find(item => String(item && item.id) === String(state.selectedId || ""));
        return element && lineModel.exactMeta(element) ? element : null;
    }

    function refreshEditor(controller) {
        const button = controller.root.querySelector('.dco-sketch-tool[data-tool="select"]');
        if (button) button.click();
        if (history.activateState) {
            const state = history.getActiveState ? history.getActiveState() : null;
            if (state) history.activateState(state);
        }
    }

    function setStatus(controller, text, type = "") {
        controller.status.className = `dco-exact-inspector-status${type ? ` is-${type}` : ""}`;
        controller.status.textContent = text;
    }

    function format(value) {
        return String(lineModel.rounded(value, 3));
    }

    function hydrate(controller, element) {
        const meta = lineModel.exactMeta(element);
        if (!meta) return;
        controller.length.value = format(meta.length_cm);
        controller.angle.value = format(meta.angle_deg);
        controller.startX.value = format(meta.start_cm[0]);
        controller.startY.value = format(meta.start_cm[1]);
        controller.endX.value = format(meta.end_cm[0]);
        controller.endY.value = format(meta.end_cm[1]);
        const state = liveState(controller);
        const startConnections = editModel.connectedCount(state && state.elements, element.id, meta.start_cm);
        const endConnections = editModel.connectedCount(state && state.elements, element.id, meta.end_cm);
        controller.summary.innerHTML = `<span>اتصالات البداية <b>${startConnections}</b></span><span>اتصالات النهاية <b>${endConnections}</b></span>`;
        setStatus(controller, `خط دقيق ${lineModel.rounded(meta.length_cm, 2)} سم · ${lineModel.rounded(meta.angle_deg, 1)}°. عدّل القيم ثم طبّق.`);
    }

    function syncVisibility(controller) {
        const creationActive = Boolean(controller.root.querySelector(".dco-exact-line-tool.is-active"));
        const element = creationActive ? null : selectedExactLine(controller);
        const id = element ? String(element.id) : "";
        controller.panel.classList.toggle("is-visible", Boolean(element));
        if (!element) {
            controller.selectedId = "";
            return;
        }
        if (controller.selectedId !== id) {
            controller.selectedId = id;
            hydrate(controller, element);
        }
    }

    function snapshotAndApply(controller, nextElement) {
        const state = liveState(controller);
        const selected = selectedExactLine(controller);
        if (!state || !selected || !nextElement) return false;
        const original = clone(state.elements);
        const result = editModel.applyEdit(
            state.elements,
            selected.id,
            nextElement,
            controller.transform,
            { preserveConnections: controller.preserveConnections.checked }
        );
        if (!result.valid) {
            setStatus(controller, result.reason === "connected-line-invalid"
                ? "التعديل سيجعل خطًا متصلًا غير صالح. ألغِ حفظ الاتصال أو غيّر القياسات."
                : "تعذر تطبيق التعديل على هذا الخط.", "error");
            return false;
        }
        const transition = history.snapshot(state, original);
        if (transition && transition.changed) Object.assign(state, transition.patch);
        state.elements = result.elements;
        state.selectedId = String(selected.id);
        state.hasChanges = true;
        if (history.activateState) history.activateState(state);
        refreshEditor(controller);
        controller.selectedId = "";
        window.setTimeout(() => {
            syncVisibility(controller);
            setStatus(controller, result.changedIds.length > 1
                ? `تم التعديل مع الحفاظ على ${result.changedIds.length - 1} خط متصل.`
                : "تم تحديث الخط مع بقاء القياسات الحقيقية محفوظة.", "success");
        }, 0);
        const notice = controller.root.querySelector(".dco-sketch-notice-text");
        if (notice) notice.textContent = "تم تعديل الخط الدقيق رقميًا. القياس الظاهر هو القياس الحقيقي بالسنتيمتر.";
        return true;
    }

    function applyLengthAngle(controller) {
        const element = selectedExactLine(controller);
        if (!element) return false;
        const result = editModel.resize(
            element,
            controller.transform,
            controller.length.value,
            controller.angle.value,
            controller.anchor
        );
        if (!result.valid) {
            setStatus(controller, result.reason === "outside-piece"
                ? "الطول أو الزاوية الجديدة تخرج الخط خارج حدود الدرفة."
                : "أدخل طولًا صحيحًا أكبر من صفر.", "error");
            return false;
        }
        return snapshotAndApply(controller, result.element);
    }

    function applyEndpoints(controller) {
        const element = selectedExactLine(controller);
        if (!element) return false;
        const result = editModel.buildFromEndpoints(
            element,
            controller.transform,
            [controller.startX.value, controller.startY.value],
            [controller.endX.value, controller.endY.value]
        );
        if (!result.valid) {
            setStatus(controller, "الإحداثيات غير صالحة أو تجعل طول الخط صفرًا.", "error");
            return false;
        }
        return snapshotAndApply(controller, result.element);
    }

    function applyAxis(controller, axis) {
        const element = selectedExactLine(controller);
        const meta = element && lineModel.exactMeta(element);
        if (!element || !meta) return false;
        const angle = editModel.axisAngle(element, axis);
        controller.angle.value = String(angle);
        const result = editModel.resize(element, controller.transform, meta.length_cm, angle, controller.anchor);
        if (!result.valid) {
            setStatus(controller, "لا يمكن جعل الخط بهذا الاتجاه من موضعه الحالي دون الخروج من حدود الدرفة.", "error");
            return false;
        }
        return snapshotAndApply(controller, result.element);
    }

    function selectExactLineWithoutDragging(controller, event) {
        if (controller.root.querySelector(".dco-exact-line-tool.is-active")) return false;
        const target = event.target && event.target.closest ? event.target.closest("[data-element-id]") : null;
        if (!target) return false;
        const state = liveState(controller);
        if (!state || state.tool !== "select") return false;
        const element = (state.elements || []).find(item => String(item && item.id) === String(target.dataset.elementId || ""));
        if (!element || !lineModel.exactMeta(element)) return false;
        const transition = history.selectElement(state, element.id);
        if (transition && transition.changed) Object.assign(state, transition.patch);
        if (history.activateState) history.activateState(state);
        refreshEditor(controller);
        controller.selectedId = "";
        window.setTimeout(() => syncVisibility(controller), 0);
        event.preventDefault();
        event.stopImmediatePropagation();
        return true;
    }

    function panelHtml() {
        return `<section class="dco-exact-line-inspector" aria-label="تعديل الخط الدقيق">
            <div class="dco-exact-inspector-head"><strong>خصائص الخط الدقيق</strong><span>CM · EXACT</span></div>
            <div class="dco-exact-inspector-body">
                <div class="dco-exact-inspector-status"></div>
                <div class="dco-exact-inspector-section">
                    <div class="dco-exact-inspector-section-title"><span>الطول والاتجاه</span><span>ثبّت طرفًا ثم عدّل</span></div>
                    <div class="dco-exact-inspector-grid">
                        <div class="dco-exact-inspector-field"><label>الطول الحقيقي</label><div class="dco-exact-inspector-shell"><input type="number" min="0.1" step="0.1" data-edit-length><span>سم</span></div></div>
                        <div class="dco-exact-inspector-field"><label>الزاوية</label><div class="dco-exact-inspector-shell"><input type="number" step="1" data-edit-angle><span>°</span></div></div>
                    </div>
                    <div class="dco-exact-inspector-anchor"><button type="button" class="is-active" data-edit-anchor="start">ثبّت البداية</button><button type="button" data-edit-anchor="end">ثبّت النهاية</button></div>
                    <div class="dco-exact-inspector-axis"><button type="button" data-edit-axis="horizontal">↔ أفقي</button><button type="button" data-edit-axis="vertical">↕ عمودي</button></div>
                    <button type="button" class="dco-exact-inspector-apply" data-apply-length>تطبيق الطول والزاوية</button>
                </div>
                <div class="dco-exact-inspector-section">
                    <div class="dco-exact-inspector-section-title"><span>نقاط الخط</span><span>X / Y بالسنتيمتر</span></div>
                    <div class="dco-exact-inspector-grid">
                        <div class="dco-exact-inspector-field"><label>X البداية</label><div class="dco-exact-inspector-shell"><input type="number" step="0.1" data-start-x><span>سم</span></div></div>
                        <div class="dco-exact-inspector-field"><label>Y البداية</label><div class="dco-exact-inspector-shell"><input type="number" step="0.1" data-start-y><span>سم</span></div></div>
                        <div class="dco-exact-inspector-field"><label>X النهاية</label><div class="dco-exact-inspector-shell"><input type="number" step="0.1" data-end-x><span>سم</span></div></div>
                        <div class="dco-exact-inspector-field"><label>Y النهاية</label><div class="dco-exact-inspector-shell"><input type="number" step="0.1" data-end-y><span>سم</span></div></div>
                    </div>
                    <button type="button" class="dco-exact-inspector-apply" data-apply-points>تطبيق الإحداثيات</button>
                    <label class="dco-exact-inspector-link"><input type="checkbox" checked data-preserve-connections><span><b>حافظ على اتصال الخطوط</b><br>إذا كانت البداية أو النهاية مشتركة مع خط دقيق آخر، تتحرك النقطة المشتركة معه تلقائيًا.</span></label>
                </div>
                <div class="dco-exact-inspector-summary" data-edit-summary></div>
            </div>
        </section>`;
    }

    function mount(row) {
        installStyles();
        const modal = visibleModal();
        if (!modal) return false;
        const root = modal.querySelector(".dco-special-sketch-shell");
        if (!root || root.dataset.dcoExactInspector === "1") return Boolean(root);
        const svg = root.querySelector(".dco-sketch-paper");
        const paperWrap = root.querySelector(".dco-sketch-paper-wrap");
        if (!svg || !paperWrap) return false;
        const dimensions = lineModel.pieceDimensions(row);
        const transform = lineModel.createTransform(dimensions.width, dimensions.length);
        if (!transform) return false;

        root.dataset.dcoExactInspector = "1";
        const wrapper = document.createElement("div");
        wrapper.innerHTML = panelHtml();
        const panel = wrapper.firstElementChild;
        paperWrap.appendChild(panel);
        const controller = {
            modal,
            root,
            svg,
            row,
            transform,
            panel,
            status: panel.querySelector(".dco-exact-inspector-status"),
            length: panel.querySelector("[data-edit-length]"),
            angle: panel.querySelector("[data-edit-angle]"),
            startX: panel.querySelector("[data-start-x]"),
            startY: panel.querySelector("[data-start-y]"),
            endX: panel.querySelector("[data-end-x]"),
            endY: panel.querySelector("[data-end-y]"),
            preserveConnections: panel.querySelector("[data-preserve-connections]"),
            summary: panel.querySelector("[data-edit-summary]"),
            anchor: "start",
            selectedId: "",
            observer: null,
        };

        panel.addEventListener("pointerdown", event => event.stopPropagation());
        panel.addEventListener("click", event => event.stopPropagation());
        panel.querySelectorAll("[data-edit-anchor]").forEach(button => button.addEventListener("click", () => {
            controller.anchor = button.dataset.editAnchor;
            panel.querySelectorAll("[data-edit-anchor]").forEach(item => item.classList.toggle("is-active", item === button));
        }));
        panel.querySelector("[data-apply-length]").addEventListener("click", () => applyLengthAngle(controller));
        panel.querySelector("[data-apply-points]").addEventListener("click", () => applyEndpoints(controller));
        panel.querySelectorAll("[data-edit-axis]").forEach(button => button.addEventListener("click", () => applyAxis(controller, button.dataset.editAxis)));
        panel.querySelectorAll("input[type=number]").forEach(input => input.addEventListener("keydown", event => {
            if (event.key !== "Enter") return;
            event.preventDefault();
            event.stopPropagation();
            if (input.matches("[data-start-x],[data-start-y],[data-end-x],[data-end-y]")) applyEndpoints(controller);
            else applyLengthAngle(controller);
        }));

        svg.addEventListener("pointerdown", event => selectExactLineWithoutDragging(controller, event), true);
        controller.observer = new MutationObserver(() => window.setTimeout(() => syncVisibility(controller), 0));
        controller.observer.observe(svg, { childList: true, subtree: false });
        syncVisibility(controller);

        if (window.jQuery) {
            window.jQuery(modal).one("hidden.bs.modal.dco-exact-line-inspector", () => {
                if (controller.observer) controller.observer.disconnect();
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
        __exactLineInspectorIntegrated: true,
        open,
        view,
    });
    window.AlmdinaExactLineInspectorUX = Object.freeze({
        installStyles,
        panelHtml,
        mount,
        editModel,
    });
})();