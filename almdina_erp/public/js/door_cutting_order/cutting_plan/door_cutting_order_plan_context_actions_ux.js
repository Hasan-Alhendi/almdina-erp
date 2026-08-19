(() => {
    "use strict";

    if (window.AlmdinaPlanContextActionsUX) return;

    const STYLE_ID = "dco-plan-context-actions-css";
    const HOST_CLASS = "dco-plan-context-actions-host";
    const TAB_ROWS = Object.freeze({
        System: "system_draft",
        Custom: "uploaded_draft",
        Approved: "approved",
    });

    function permissions() {
        return window.AlmdinaPermissions || null;
    }

    function can(frm, capability) {
        const owner = permissions();
        if (!owner) return false;
        if (typeof owner.canDocument === "function") {
            return Boolean(owner.canDocument(frm, capability));
        }
        return typeof owner.can === "function" && Boolean(owner.can(capability));
    }

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function canMutateCurrentStage(frm) {
        const context = documentContext();
        if (context && typeof context.canMutateCurrentStage === "function") {
            return Boolean(context.canMutateCurrentStage(frm));
        }
        return Boolean(frm && frm.__almdina_actor_holds_stage_role);
    }

    function stateOwner() {
        return window.AlmdinaPlanWorkspaceState || null;
    }

    function snapshot(frm) {
        const owner = stateOwner();
        return owner && typeof owner.snapshot === "function" ? owner.snapshot(frm) : null;
    }

    function workspaceData(frm) {
        const state = snapshot(frm);
        return state && state.status === "ready" ? state.data : null;
    }

    function workspaceCapabilities(frm) {
        return (workspaceData(frm) && workspaceData(frm).capabilities) || {};
    }

    function isEditing(frm) {
        const editor = window.AlmdinaPlanEditSessionUX;
        return Boolean(editor && typeof editor.isEditing === "function" && editor.isEditing(frm));
    }

    function activeTab(frm) {
        return String(frm.__almdina_active_plan_tab || "System");
    }

    function rowForTab(frm, tab = activeTab(frm)) {
        const data = workspaceData(frm);
        const plans = (data && data.plans) || {};
        return plans[TAB_ROWS[tab]] || null;
    }

    function parsePlan(row) {
        if (!row || !row.snapshot_json) return null;
        if (typeof row.snapshot_json === "object") return row.snapshot_json;
        try {
            return JSON.parse(row.snapshot_json || "{}");
        } catch (error) {
            return null;
        }
    }

    function rowHasPlan(row) {
        const plan = parsePlan(row);
        return Boolean(plan && Array.isArray(plan.sheets) && plan.sheets.length);
    }

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function sourceLabel(tab) {
        if (tab === "Custom") return __("الخطة المرفوعة");
        if (tab === "Approved") return __("الخطة المعتمدة");
        return __("خطة النظام");
    }

    function approveLabel(frm, tab) {
        const hasApproved = Boolean(String((workspaceData(frm) || {}).approved_plan || "").trim());
        if (!hasApproved) {
            return tab === "Custom" ? __("اعتماد الخطة المرفوعة") : __("اعتماد خطة النظام");
        }
        return tab === "Custom"
            ? __("استبدال الخطة المعتمدة بالخطة المرفوعة")
            : __("استبدال الخطة المعتمدة بخطة النظام");
    }

    function planMetrics(row) {
        const totals = (row && row.totals) || {};
        const engine = (row && row.engine) || {};
        return {
            boards: Number(totals.required_boards || 0),
            waste: Number(totals.waste_percent || 0),
            method: String(engine.method_label || engine.method_key || "").trim(),
        };
    }

    function hasOperationalAccess(frm) {
        const routed = Boolean(String((frm.doc && frm.doc.production_path) || "").trim());
        return !routed || canMutateCurrentStage(frm);
    }

    function canApprove(frm, tab, row) {
        const caps = workspaceCapabilities(frm);
        return Boolean(
            tab !== "Approved"
            && !isEditing(frm)
            && rowHasPlan(row)
            && caps.approve
            && can(frm, "approve_dxf")
            && hasOperationalAccess(frm)
            && row.validation
            && row.validation.status === "Valid"
            && !row.validation.needs_recalculation
        );
    }

    function canCancelApproval(frm, tab) {
        const data = workspaceData(frm) || {};
        const caps = workspaceCapabilities(frm);
        return Boolean(
            tab === "Approved"
            && String(data.approved_plan || "").trim()
            && !isEditing(frm)
            && caps.approve
            && can(frm, "approve_dxf")
            && hasOperationalAccess(frm)
        );
    }

    function canPrint(frm, row) {
        const caps = workspaceCapabilities(frm);
        return Boolean(
            !isEditing(frm)
            && rowHasPlan(row)
            && caps.print
            && can(frm, "print_cutting_plan")
        );
    }

    function canExport(frm, row) {
        const caps = workspaceCapabilities(frm);
        return Boolean(
            !isEditing(frm)
            && rowHasPlan(row)
            && caps.export_dxf
            && can(frm, "export_dxf")
            && hasOperationalAccess(frm)
        );
    }

    function uploadedFile(frm) {
        const data = workspaceData(frm) || {};
        const uploaded = data.plans && data.plans.uploaded_draft;
        return String((uploaded && uploaded.dxf && uploaded.dxf.file) || "").trim();
    }

    function canUpload(frm) {
        const caps = workspaceCapabilities(frm);
        const replacing = Boolean(uploadedFile(frm));
        return Boolean(
            !isEditing(frm)
            && hasOperationalAccess(frm)
            && (replacing ? caps.replace_dxf : caps.upload_dxf)
            && can(frm, replacing ? "replace_dxf" : "upload_dxf")
        );
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .${HOST_CLASS} {
                margin: 0 0 14px;
                direction: rtl;
            }
            .dco-plan-context-bar {
                display:flex;
                align-items:center;
                justify-content:space-between;
                gap:12px;
                flex-wrap:wrap;
                padding:11px 12px;
                border:1px solid var(--border-color,#dfe3e8);
                border-radius:12px;
                background:var(--card-bg,var(--fg-color,#fff));
                box-shadow:0 3px 12px rgba(15,23,42,.035);
            }
            .dco-plan-context-primary,
            .dco-plan-context-tools,
            .dco-plan-context-summary {
                display:flex;
                align-items:center;
                gap:8px;
                flex-wrap:wrap;
            }
            .dco-plan-context-summary { gap:6px; }
            .dco-plan-context-chip {
                display:inline-flex;
                align-items:center;
                min-height:28px;
                padding:4px 9px;
                border-radius:999px;
                background:var(--subtle-fg,#f5f7f9);
                border:1px solid var(--border-color,#e2e8f0);
                color:var(--text-muted,#5f6b78);
                font-size:11px;
                font-weight:700;
                white-space:nowrap;
            }
            .dco-plan-context-chip.is-approved {
                background:#ecfdf3;
                color:#166534;
                border-color:#bbf7d0;
            }
            .dco-plan-context-bar .btn {
                min-height:34px;
                border-radius:9px;
                font-weight:750;
                box-shadow:none !important;
            }
            .dco-plan-context-primary .btn-primary,
            .dco-plan-context-primary .btn-success {
                min-width:190px;
            }
            .dco-plan-context-tools .btn {
                display:inline-flex;
                align-items:center;
                gap:5px;
                padding-inline:10px;
            }
            .dco-plan-context-cancel {
                color:#b42318 !important;
                border-color:#f1b6b0 !important;
                background:#fff !important;
            }
            .dco-plan-context-cancel:hover {
                background:#fff5f4 !important;
                border-color:#dc5a50 !important;
            }
            .dco-plan-context-edit-note {
                width:100%;
                color:var(--text-muted,#667085);
                font-size:11px;
                line-height:1.6;
            }
            [data-fieldname="plan_control_actions"] .dco-plan-document-actions,
            [data-fieldname="plan_control_actions"] .dco-approve-cutting-plan {
                display:none !important;
            }
            @media (max-width:767px) {
                .dco-plan-context-bar { align-items:stretch; }
                .dco-plan-context-primary,
                .dco-plan-context-tools { width:100%; }
                .dco-plan-context-primary .btn { width:100%; }
                .dco-plan-context-tools .btn { flex:1 1 auto; justify-content:center; }
            }
        `;
        document.head.appendChild(style);
    }

    function syncLegacyActionSurface(frm) {
        const field = frm.fields_dict && frm.fields_dict.plan_control_actions;
        if (!field || !field.$wrapper) return;
        field.$wrapper.toggle(Boolean(isEditing(frm)));
    }

    async function refreshWorkspace(frm) {
        const owner = stateOwner();
        if (owner && typeof owner.load === "function") {
            await owner.load(frm, { force: true });
        }
        const adapter = window.AlmdinaPlanWorkspacePresenterAdapter;
        if (adapter && typeof adapter.project === "function") adapter.project(frm);
        const tabs = window.AlmdinaPlanTabsUX;
        if (tabs && typeof tabs.renderDualTabs === "function") tabs.renderDualTabs(frm);
    }

    async function runApproval(frm) {
        const controls = window.AlmdinaPlanControlsUX;
        if (!controls || typeof controls.runApproval !== "function") {
            frappe.msgprint(__("تعذر تحميل أمر اعتماد خطة القص. أعد تحميل الصفحة ثم حاول مرة أخرى."));
            return false;
        }
        return controls.runApproval(frm);
    }

    async function runCancelApproval(frm) {
        const api = window.AlmdinaPlanWorkspaceAPI;
        if (!api || typeof api.cancelApproval !== "function") {
            frappe.msgprint(__("تعذر تحميل أمر إلغاء اعتماد خطة القص. أعد تحميل الصفحة ثم حاول مرة أخرى."));
            return false;
        }
        return new Promise((resolve) => {
            frappe.confirm(
                __("سيتم إلغاء اعتماد خطة الإنتاج الحالية مع الاحتفاظ بها في سجل المراجعات، ولن تتحول الخطة القديمة إلى مسودة قابلة للتعديل. هل تريد المتابعة؟"),
                async () => {
                    try {
                        await api.cancelApproval(frm.doc.name);
                        frm.__almdina_active_plan_tab = "System";
                        await refreshWorkspace(frm);
                        frappe.show_alert({
                            message: __("تم إلغاء اعتماد خطة القص مع الاحتفاظ بسجلها."),
                            indicator: "green",
                        }, 5);
                        resolve(true);
                    } catch (error) {
                        console.error("Cutting plan approval cancellation failed", error);
                        resolve(false);
                    }
                },
                () => resolve(false)
            );
        });
    }

    function runPrint(frm) {
        const tabs = window.AlmdinaPlanTabsUX;
        if (!tabs || typeof tabs.printActivePlan !== "function") return false;
        tabs.printActivePlan(frm);
        return true;
    }

    function runExport(frm) {
        if (!frappe.almdina || typeof frappe.almdina.export_order_dxf !== "function") {
            frappe.msgprint(__("تعذر تحميل خدمة تصدير DXF الآمنة."));
            return false;
        }
        return frappe.almdina.export_order_dxf(frm.doc.name, activeTab(frm));
    }

    function runUpload(frm) {
        if (!frappe.almdina || typeof frappe.almdina.upload_production_dxf !== "function") {
            frappe.msgprint(__("تعذر تحميل خدمة رفع DXF الآمنة."));
            return false;
        }
        return frappe.almdina.upload_production_dxf(frm);
    }

    function primaryActionHtml(frm, tab, row) {
        if (tab === "Approved") {
            return `
                <span class="dco-plan-context-chip is-approved">✓ ${esc(__("الخطة المعتمدة للإنتاج"))}</span>
                ${canCancelApproval(frm, tab)
                    ? `<button type="button" class="btn btn-default btn-sm dco-plan-context-cancel">${esc(__("إلغاء اعتماد الخطة"))}</button>`
                    : ""}
            `;
        }
        if (!rowHasPlan(row)) return "";
        const allowed = canApprove(frm, tab, row);
        const disabled = allowed ? "" : " disabled aria-disabled=\"true\"";
        return `<button type="button" class="btn btn-success btn-sm dco-plan-context-approve"${disabled}>${esc(approveLabel(frm, tab))}</button>`;
    }

    function toolsHtml(frm, row) {
        const print = canPrint(frm, row)
            ? `<button type="button" class="btn btn-default btn-sm dco-print-cutting-plan"><span aria-hidden="true">▣</span>${esc(__("طباعة"))}</button>`
            : "";
        const exportDxf = canExport(frm, row)
            ? `<button type="button" class="btn btn-default btn-sm dco-export-dxf"><span aria-hidden="true">↓</span>${esc(__("تصدير DXF"))}</button>`
            : "";
        const upload = canUpload(frm)
            ? `<button type="button" class="btn btn-default btn-sm dco-upload-dxf-plan"><span aria-hidden="true">↑</span>${esc(uploadedFile(frm) ? __("استبدال الخطة المرفوعة") : __("رفع خطة DXF"))}</button>`
            : "";
        return `${upload}${exportDxf}${print}`;
    }

    function render(frm, host) {
        installStyles();
        syncLegacyActionSurface(frm);
        const target = host && host.jquery ? host : $(host || []);
        if (!target.length) return false;

        const data = workspaceData(frm);
        if (!data) {
            target.empty();
            return false;
        }

        const tab = activeTab(frm);
        const row = rowForTab(frm, tab);
        const metrics = planMetrics(row);
        const editing = isEditing(frm);
        const metricChips = rowHasPlan(row)
            ? `
                <span class="dco-plan-context-chip">${esc(metrics.boards)} ${esc(__("ألواح"))}</span>
                <span class="dco-plan-context-chip">${esc(__("هدر"))} ${esc(metrics.waste.toFixed(2))}%</span>
                ${metrics.method ? `<span class="dco-plan-context-chip">${esc(metrics.method)}</span>` : ""}
            `
            : `<span class="dco-plan-context-chip">${esc(sourceLabel(tab))}</span>`;

        target.html(`
            <div class="dco-plan-context-bar" data-active-plan-source="${esc(tab)}">
                <div class="dco-plan-context-primary">
                    ${editing
                        ? `<span class="dco-plan-context-chip">${esc(__("وضع تجربة الإعدادات"))}</span>`
                        : primaryActionHtml(frm, tab, row)}
                    <div class="dco-plan-context-summary">${metricChips}</div>
                </div>
                <div class="dco-plan-context-tools">${editing ? "" : toolsHtml(frm, row)}</div>
                ${editing
                    ? `<div class="dco-plan-context-edit-note">${esc(__("أكمل تجربة الإعدادات من الأعلى. أوامر الاعتماد والطباعة والتصدير والرفع متوقفة حتى الحفظ أو الإلغاء."))}</div>`
                    : ""}
            </div>
        `);

        target.find(".dco-plan-context-approve").off("click").on("click", () => runApproval(frm));
        target.find(".dco-plan-context-cancel").off("click").on("click", () => runCancelApproval(frm));
        target.find(".dco-print-cutting-plan").off("click").on("click", () => runPrint(frm));
        target.find(".dco-export-dxf").off("click").on("click", () => runExport(frm));
        target.find(".dco-upload-dxf-plan").off("click").on("click", () => runUpload(frm));
        return true;
    }

    window.AlmdinaPlanContextActionsUX = Object.freeze({
        activeTab,
        rowForTab,
        render,
        runApproval,
        runCancelApproval,
        runPrint,
        runExport,
        runUpload,
        syncLegacyActionSurface,
    });
})();
