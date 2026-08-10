(() => {
    "use strict";

    const history = window.AlmdinaSketchHistory;
    const edgeModel = window.AlmdinaSketchEdgeModel;
    const engine = window.AlmdinaSketchEngine;
    if (!history || !edgeModel || !engine) {
        console.error("Smart edge feature dependencies are missing");
        return;
    }

    const STYLE_ID = "dco-smart-edge-features-css";
    const MOUNT_RETRIES = 14;

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-smart-edge-feature-card{margin-top:9px;padding-top:9px;border-top:1px solid #e7ebef}
            .dco-smart-edge-feature-title{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:7px}
            .dco-smart-edge-feature-title strong{font-size:9px;color:#334155}
            .dco-smart-edge-feature-title span{font-size:7.5px;color:#64748b}
            .dco-smart-edge-feature-fields{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:7px}
            .dco-smart-edge-feature-field label{display:block;margin-bottom:3px;color:#64748b;font-size:7.5px;font-weight:800}
            .dco-smart-edge-feature-shell{display:flex;align-items:center;border:1px solid #d8e0e7;border-radius:8px;background:#fff;overflow:hidden}
            .dco-smart-edge-feature-shell input{min-width:0;width:100%;height:31px;border:0!important;box-shadow:none!important;padding:4px 6px;text-align:center;font-size:11px;font-weight:900}
            .dco-smart-edge-feature-shell span{padding:0 6px;border-right:1px solid #e7ebef;color:#718096;font-size:7px;white-space:nowrap}
            .dco-smart-edge-feature-actions{display:grid;grid-template-columns:1fr 1fr;gap:6px}
            .dco-smart-edge-feature-action{min-height:35px;border:1px solid #d8e0e7;border-radius:9px;background:#fff;color:#334155;cursor:pointer;font-size:8px;font-weight:900}
            .dco-smart-edge-feature-action:hover{border-color:#0f9f6e;color:#087a54;background:#f2fbf7}
            .dco-smart-edge-feature-action.is-notch{border-color:#a7e3cc;background:#f1fbf7;color:#087a54}
            .dco-smart-edge-feature-action.is-protrusion{border-color:#c4b5fd;background:#f8f6ff;color:#6d28d9}
            .dco-smart-edge-feature-hint{margin-top:6px;color:#64748b;font-size:7.2px;line-height:1.5}
        `;
        document.head.appendChild(style);
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
        ) || null;
    }

    function selectedEdgeIndex(root) {
        const selected = root.querySelector(".dco-smart-edge.is-selected [data-smart-template-edge]");
        if (!selected) return -1;
        return Number(selected.dataset.smartTemplateEdge);
    }

    function featureHtml(edgeLength) {
        const width = Math.max(
            edgeModel.MIN_FEATURE_WIDTH,
            Math.round(Math.min(90, Math.max(edgeModel.MIN_FEATURE_WIDTH, edgeLength * 0.35)))
        );
        return `
            <div class="dco-smart-edge-feature-card">
                <div class="dco-smart-edge-feature-title">
                    <strong>إضافة نقرة أو درجة</strong>
                    <span>تُنشأ في منتصف الضلع</span>
                </div>
                <div class="dco-smart-edge-feature-fields">
                    <div class="dco-smart-edge-feature-field">
                        <label>العرض على الرسم</label>
                        <div class="dco-smart-edge-feature-shell"><input type="number" min="${edgeModel.MIN_FEATURE_WIDTH}" max="800" step="1" value="${width}" data-smart-feature-width><span>رسم</span></div>
                    </div>
                    <div class="dco-smart-edge-feature-field">
                        <label>العمق على الرسم</label>
                        <div class="dco-smart-edge-feature-shell"><input type="number" min="${edgeModel.MIN_FEATURE_DEPTH}" max="260" step="1" value="55" data-smart-feature-depth><span>رسم</span></div>
                    </div>
                </div>
                <div class="dco-smart-edge-feature-actions">
                    <button type="button" class="dco-smart-edge-feature-action is-notch" data-smart-edge-feature="notch">⌑ نقرة للداخل</button>
                    <button type="button" class="dco-smart-edge-feature-action is-protrusion" data-smart-edge-feature="protrusion">▣ بروز للخارج</button>
                </div>
                <div class="dco-smart-edge-feature-hint">يحدد النظام اتجاه داخل الدرفة تلقائيًا حتى لو كان الضلع مائلًا. بعد الإنشاء تستطيع سحب النقاط الجديدة وتعديلها مثل بقية القالب.</div>
            </div>`;
    }

    function ensureFeatureCard(root) {
        const panel = root.querySelector(".dco-smart-edge-panel.is-visible");
        const state = activeState();
        const element = selectedTemplate(state);
        const index = selectedEdgeIndex(root);
        if (!panel || !element || index < 0) return false;
        if (panel.querySelector(".dco-smart-edge-feature-card")) return true;
        const value = edgeModel.edge(element.points, index);
        if (!value) return false;
        const body = panel.querySelector(".dco-smart-edge-body");
        if (!body) return false;
        body.insertAdjacentHTML("beforeend", featureHtml(value.length));
        return true;
    }

    function refreshThroughEditor(root) {
        const active = root.querySelector(".dco-sketch-tool.is-active")
            || root.querySelector('.dco-sketch-tool[data-tool="select"]');
        if (active) active.click();
    }

    function applyFeature(root, type) {
        const state = activeState();
        const element = selectedTemplate(state);
        const index = selectedEdgeIndex(root);
        if (!state || !element || index < 0) return false;
        const widthInput = root.querySelector("[data-smart-feature-width]");
        const depthInput = root.querySelector("[data-smart-feature-depth]");
        const featureWidth = Number(widthInput && widthInput.value);
        const featureDepth = Number(depthInput && depthInput.value);
        const operation = type === "protrusion"
            ? edgeModel.createProtrusion
            : edgeModel.createNotch;
        const originalElements = clone(state.elements);
        const result = operation(element.points, index, {
            featureWidth,
            featureDepth,
            ...engine.DEFAULT_CANVAS,
        });
        if (!result || !result.changed) {
            if (window.frappe) {
                frappe.show_alert({
                    message: "هذا الضلع قصير جدًا لإضافة النقرة بهذا الشكل.",
                    indicator: "orange",
                });
            }
            return false;
        }
        const transition = history.snapshot(state, originalElements);
        if (transition && transition.changed) Object.assign(state, transition.patch);
        element.points = result.points;
        element.smart_template_variant_modified = 1;
        state.hasChanges = true;
        refreshThroughEditor(root);
        if (window.frappe) {
            frappe.show_alert({
                message: type === "protrusion"
                    ? "تم إنشاء البروز. اسحب نقاطه الزرقاء لمطابقة صورة المرجع."
                    : "تم إنشاء النقرة. اسحب نقاطها الزرقاء لمطابقة صورة المرجع.",
                indicator: "green",
            }, 5);
        }
        const notice = root.querySelector(".dco-sketch-notice-text");
        if (notice) {
            notice.textContent = "تمت إضافة الميزة هندسيًا على الضلع. يمكنك الآن ضبط نقاطها بالـ Snap ثم إضافة القياسات الحقيقية.";
        }
        return true;
    }

    function mount() {
        installStyles();
        const modals = Array.from(document.querySelectorAll(".dco-special-shape-modal"));
        const modal = modals.reverse().find(item =>
            !item.classList.contains("dco-special-shape-readonly")
            && (item.classList.contains("show") || item.style.display === "block")
        );
        if (!modal) return false;
        const root = modal.querySelector(".dco-special-sketch-shell");
        if (!root) return false;
        if (root.dataset.dcoSmartEdgeFeatures === "1") return true;
        root.dataset.dcoSmartEdgeFeatures = "1";

        root.addEventListener("click", event => {
            const button = event.target.closest && event.target.closest("[data-smart-edge-feature]");
            if (!button) return;
            event.preventDefault();
            event.stopPropagation();
            applyFeature(root, button.dataset.smartEdgeFeature);
        });

        const observer = new MutationObserver(() => {
            window.setTimeout(() => ensureFeatureCard(root), 0);
        });
        const paperWrap = root.querySelector(".dco-sketch-paper-wrap");
        if (paperWrap) observer.observe(paperWrap, { childList: true, subtree: true });
        ensureFeatureCard(root);

        if (window.jQuery) {
            window.jQuery(modal).one("hidden.bs.modal.dco-smart-edge-features", () => observer.disconnect());
        }
        return true;
    }

    function scheduleMount(attempt = 0) {
        window.setTimeout(() => {
            if (mount()) return;
            if (attempt + 1 < MOUNT_RETRIES) scheduleMount(attempt + 1);
        }, attempt ? 35 : 0);
    }

    const baseEditor = window.AlmdinaSpecialShapeEditor;
    if (baseEditor && !baseEditor.__smartEdgeFeaturesIntegrated) {
        const openBase = baseEditor.open;
        const viewBase = baseEditor.view;
        window.AlmdinaSpecialShapeEditor = Object.freeze({
            ...baseEditor,
            __smartEdgeFeaturesIntegrated: true,
            open(frm, row, options = {}) {
                const result = openBase(frm, row, options);
                if (!options.readOnly) scheduleMount();
                return result;
            },
            view(frm, row) {
                return viewBase(frm, row);
            },
        });
    }

    window.AlmdinaSmartEdgeFeaturesUX = Object.freeze({
        installStyles,
        featureHtml,
        selectedEdgeIndex,
        applyFeature,
        mount,
    });
})();
