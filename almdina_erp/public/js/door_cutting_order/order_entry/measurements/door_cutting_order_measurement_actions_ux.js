(() => {
    "use strict";

    const STYLE_ID = "dco-measurement-actions-css";
    const EDITOR_CLASS = "dco-measurement-entry-window";

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function orderEdgeColor(frm) {
        return String(frm.doc.edge_color || "").trim() || "غير محدد";
    }

    function printMeasurements(frm) {
        const documents = window.AlmdinaOrderDocumentPrint;
        if (!documents || typeof documents.printMeasurements !== "function") {
            frappe.msgprint("تعذر تجهيز طباعة القياسات. أعد تحميل الصفحة ثم حاول مرة أخرى.");
            return Promise.resolve(false);
        }
        return Promise.resolve(documents.printMeasurements(frm));
    }

    function measurementRoot(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.pieces_fast_entry;
        return field && field.$wrapper ? field.$wrapper.get(0) : null;
    }

    function updateEditorState(frm) {
        const state = frm && frm._dcoMeasurementEntryWindow;
        if (!state || !state.overlay || !state.overlay.isConnected) return;
        const status = state.overlay.querySelector(".dco-entry-window-status");
        const saveButton = state.overlay.querySelector(".dco-entry-window-save");
        const dirty = typeof frm.is_dirty === "function" ? frm.is_dirty() : Boolean(frm.dirty);
        if (status) {
            status.classList.toggle("is-dirty", dirty);
            status.innerHTML = dirty
                ? '<span class="dot"></span><span>توجد تعديلات غير محفوظة</span>'
                : '<span class="dot"></span><span>جميع التعديلات محفوظة</span>';
        }
        if (saveButton) saveButton.disabled = !dirty || state.saving;
    }

    function ensureEditorRootMounted(frm) {
        const state = frm && frm._dcoMeasurementEntryWindow;
        if (!state || !state.overlay || !state.overlay.isConnected) return;
        const currentRoot = measurementRoot(frm);
        if (!currentRoot) return;
        if (currentRoot !== state.root) state.root = currentRoot;
        if (state.root.parentNode !== state.host) state.host.appendChild(state.root);
        updateEditorState(frm);
    }

    function closeEditableMeasurements(frm) {
        const state = frm && frm._dcoMeasurementEntryWindow;
        if (!state) return;

        if (state.root && state.placeholder && state.placeholder.parentNode) {
            state.placeholder.parentNode.insertBefore(state.root, state.placeholder);
            state.placeholder.remove();
        }
        if (state.overlay && state.overlay.parentNode) state.overlay.remove();
        document.body.classList.remove("dco-measurement-entry-open");
        frm._dcoMeasurementEntryWindow = null;
        requestAnimationFrame(() => ensureActions(frm));
    }

    async function saveFromEditor(frm) {
        const state = frm && frm._dcoMeasurementEntryWindow;
        if (!state || state.saving) return;
        state.saving = true;
        const saveButton = state.overlay.querySelector(".dco-entry-window-save");
        const originalLabel = saveButton ? saveButton.textContent : "";
        if (saveButton) {
            saveButton.disabled = true;
            saveButton.textContent = "جارٍ الحفظ…";
        }
        try {
            await Promise.resolve(frm.save());
            requestAnimationFrame(() => ensureEditorRootMounted(frm));
            setTimeout(() => ensureEditorRootMounted(frm), 120);
            frappe.show_alert({ message: "تم حفظ الطلب.", indicator: "green" });
        } catch (error) {
            console.error("Measurement entry save failed", error);
        } finally {
            state.saving = false;
            if (saveButton) saveButton.textContent = originalLabel || "حفظ الطلب";
            updateEditorState(frm);
        }
    }

    function openEditableMeasurements(frm) {
        installStyles();
        const existing = frm._dcoMeasurementEntryWindow;
        if (existing && existing.overlay && existing.overlay.isConnected) {
            existing.overlay.querySelector(".dco-entry-window-close")?.focus();
            return;
        }

        const root = measurementRoot(frm);
        const shell = root && root.querySelector(".dco-fast-entry-shell");
        if (!root || !shell || !root.parentNode) {
            frappe.msgprint("تعذر فتح جدول الإدخال. أعد تحميل الطلب ثم حاول مرة أخرى.");
            return;
        }

        const placeholder = document.createComment("dco-measurement-entry-origin");
        root.parentNode.insertBefore(placeholder, root);

        const overlay = document.createElement("section");
        overlay.className = EDITOR_CLASS;
        overlay.setAttribute("role", "dialog");
        overlay.setAttribute("aria-modal", "true");
        overlay.setAttribute("aria-label", "جدول إدخال قياسات الدرف");
        overlay.innerHTML = `
            <header class="dco-entry-window-header">
                <div class="dco-entry-window-title">
                    <strong>جدول إدخال الدرف</strong>
                    <span>${esc(frm.doc.name || "مسودة")} · ${esc(frm.doc.customer || "بدون عميل")}</span>
                </div>
                <div class="dco-entry-window-meta">
                    <span>نوع القشاط: <b>${esc(frm.doc.default_edge_type || "—")}</b></span>
                    <span>لون القشاط: <b>${esc(orderEdgeColor(frm))}</b></span>
                    <span class="dco-entry-window-status"><span class="dot"></span><span>جميع التعديلات محفوظة</span></span>
                </div>
                <div class="dco-entry-window-actions">
                    <button type="button" class="btn btn-default dco-entry-window-print">طباعة القياسات</button>
                    <button type="button" class="btn btn-primary dco-entry-window-save">حفظ الطلب</button>
                    <button type="button" class="btn btn-default dco-entry-window-close">إغلاق والعودة</button>
                </div>
            </header>
            <div class="dco-entry-window-body">
                <div class="dco-entry-window-host"></div>
            </div>`;

        document.body.appendChild(overlay);
        const host = overlay.querySelector(".dco-entry-window-host");
        host.appendChild(root);
        document.body.classList.add("dco-measurement-entry-open");

        const state = { overlay, host, root, placeholder, saving: false, stateFrame: null };
        frm._dcoMeasurementEntryWindow = state;

        overlay.addEventListener("click", event => {
            if (event.target.closest(".dco-entry-window-close")) {
                event.preventDefault();
                closeEditableMeasurements(frm);
                return;
            }
            if (event.target.closest(".dco-entry-window-print")) {
                event.preventDefault();
                printMeasurements(frm);
                return;
            }
            if (event.target.closest(".dco-entry-window-save")) {
                event.preventDefault();
                saveFromEditor(frm);
            }
        });

        overlay.addEventListener("keydown", event => {
            if (event.key === "Escape" && !document.querySelector(".modal.show")) {
                event.preventDefault();
                closeEditableMeasurements(frm);
            }
        });

        const scheduleState = () => {
            if (state.stateFrame) return;
            state.stateFrame = requestAnimationFrame(() => {
                state.stateFrame = null;
                updateEditorState(frm);
            });
        };
        overlay.addEventListener("input", scheduleState, true);
        overlay.addEventListener("change", scheduleState, true);

        updateEditorState(frm);
        requestAnimationFrame(() => {
            const scroller = root.querySelector(".dco-fast-entry-scroll");
            if (scroller) scroller.focus({ preventScroll: true });
        });
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-measurement-table-actions{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-inline-start:auto}
            .dco-measurement-table-actions .btn{border-radius:8px!important;font-weight:800!important;white-space:nowrap}
            .dco-measurement-table-actions .dco-open-measurements-window{display:inline-flex;align-items:center;gap:5px}
            body.dco-measurement-entry-open{overflow:hidden!important}
            .${EDITOR_CLASS}{position:fixed;inset:0;z-index:1040;display:flex;flex-direction:column;direction:rtl;background:var(--bg-color,#f4f6f8);color:var(--text-color,#172033)}
            .dco-entry-window-header{display:grid;grid-template-columns:minmax(220px,1fr) auto auto;align-items:center;gap:12px;padding:10px 16px;border-bottom:1px solid var(--border-color,#dfe3e8);background:var(--card-bg,#fff);box-shadow:0 4px 18px rgba(15,23,42,.08)}
            .dco-entry-window-title{display:flex;flex-direction:column;gap:2px;min-width:0}.dco-entry-window-title strong{font-size:17px;font-weight:900}.dco-entry-window-title span{font-size:11px;color:var(--text-muted,#66717e);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
            .dco-entry-window-meta{display:flex;align-items:center;justify-content:center;gap:7px;flex-wrap:wrap}.dco-entry-window-meta>span{display:inline-flex;align-items:center;gap:4px;padding:5px 8px;border:1px solid var(--border-color,#dfe3e8);border-radius:999px;background:var(--subtle-fg,#f7f9fb);font-size:10px;white-space:nowrap}
            .dco-entry-window-status .dot{width:7px;height:7px;border-radius:50%;background:#209454}.dco-entry-window-status.is-dirty{border-color:rgba(218,146,21,.35);background:rgba(218,146,21,.08);color:#8a5a08}.dco-entry-window-status.is-dirty .dot{background:#d99215}
            .dco-entry-window-actions{display:flex;align-items:center;justify-content:flex-start;gap:7px;flex-wrap:wrap}.dco-entry-window-actions .btn{min-height:36px;border-radius:9px!important;font-weight:850!important;white-space:nowrap}
            .dco-entry-window-body{flex:1;min-height:0;padding:10px}.dco-entry-window-host{height:100%;min-height:0}.dco-entry-window-host>[data-fieldname="pieces_fast_entry"],.dco-entry-window-host>.frappe-control{height:100%;margin:0!important}.dco-entry-window-host .dco-fast-entry-shell{height:100%;display:flex;flex-direction:column;border-radius:12px}.dco-entry-window-host .dco-fast-entry-toolbar{flex:0 0 auto}.dco-entry-window-host .dco-fast-entry-scroll{flex:1 1 auto;max-height:none!important;height:auto!important;min-height:0;overflow:auto!important}.dco-entry-window-host .dco-fast-table{min-width:1180px}.dco-entry-window-host .dco-measurement-table-actions{display:none!important}
            @media(max-width:1000px){.dco-entry-window-header{grid-template-columns:1fr auto}.dco-entry-window-meta{grid-column:1/-1;grid-row:2}.dco-entry-window-actions{grid-column:2;grid-row:1}}
            @media(max-width:760px){.dco-measurement-table-actions{width:100%;margin-inline-start:0}.dco-measurement-table-actions .btn{flex:1 1 auto}.dco-entry-window-header{grid-template-columns:1fr;padding:9px}.dco-entry-window-title,.dco-entry-window-meta,.dco-entry-window-actions{grid-column:1;grid-row:auto}.dco-entry-window-actions .btn{flex:1 1 auto}.dco-entry-window-body{padding:6px}}
        `;
        document.head.appendChild(style);
    }

    function ensureActions(frm) {
        installStyles();
        const root = measurementRoot(frm);
        const toolbar = root && root.querySelector(".dco-fast-entry-toolbar");
        if (!toolbar) return;
        let actions = toolbar.querySelector(".dco-measurement-table-actions");
        if (!actions) {
            actions = document.createElement("div");
            actions.className = "dco-measurement-table-actions";
            actions.innerHTML = `
                <button type="button" class="btn btn-default btn-sm dco-print-measurements">طباعة القياسات</button>
                <button type="button" class="btn btn-default btn-sm dco-open-measurements-window"><span aria-hidden="true">⛶</span><span>فتح جدول الإدخال في نافذة مستقلة</span></button>`;
            toolbar.appendChild(actions);
        }
        if (!root._dcoMeasurementActionsBound) {
            root._dcoMeasurementActionsBound = true;
            root.addEventListener("click", event => {
                const printButton = event.target.closest(".dco-print-measurements");
                if (printButton && root.contains(printButton)) {
                    event.preventDefault();
                    printMeasurements(frm);
                    return;
                }
                const openButton = event.target.closest(".dco-open-measurements-window");
                if (openButton && root.contains(openButton)) {
                    event.preventDefault();
                    openEditableMeasurements(frm);
                }
            });
        }
        if (!root._dcoMeasurementActionsObserver) {
            let scheduled = false;
            const observer = new MutationObserver(() => {
                if (scheduled) return;
                scheduled = true;
                requestAnimationFrame(() => { scheduled = false; ensureActions(frm); });
            });
            observer.observe(root, { childList: true, subtree: true });
            root._dcoMeasurementActionsObserver = observer;
        }
    }

    function schedule(frm) {
        const lifecycle = window.AlmdinaMeasurementLifecycle;
        if (!lifecycle) {
            ensureActions(frm);
            requestAnimationFrame(() => ensureActions(frm));
            setTimeout(() => ensureActions(frm), 180);
            setTimeout(() => ensureActions(frm), 600);
            if (frm._dcoMeasurementEntryWindow) {
                requestAnimationFrame(() => ensureEditorRootMounted(frm));
            }
            return;
        }

        lifecycle.schedule(
            frm,
            "measurement-actions",
            () => ensureActions(frm),
            { delays: [180, 600] }
        );
        if (frm._dcoMeasurementEntryWindow) {
            lifecycle.schedule(
                frm,
                "measurement-editor-remount",
                () => ensureEditorRootMounted(frm),
                { immediate: false }
            );
        }
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
    });

    window.AlmdinaMeasurementActions = {
        print: printMeasurements,
        open: openEditableMeasurements,
        close: closeEditableMeasurements,
    };
})();