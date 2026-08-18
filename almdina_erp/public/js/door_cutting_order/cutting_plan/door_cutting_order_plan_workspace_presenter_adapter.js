(() => {
    "use strict";

    if (window.AlmdinaPlanWorkspacePresenterAdapter) return;

    function stateOwner() {
        return window.AlmdinaPlanWorkspaceState || null;
    }

    function snapshot(frm) {
        const owner = stateOwner();
        return owner && typeof owner.snapshot === "function" ? owner.snapshot(frm) : null;
    }

    function data(frm) {
        const state = snapshot(frm);
        return state && state.status === "ready" ? state.data : null;
    }

    function ensureLoad(frm) {
        const owner = stateOwner();
        if (!owner || typeof owner.load !== "function") return Promise.resolve(null);
        return Promise.resolve(owner.load(frm)).catch(() => null);
    }

    function planRow(frm, tab) {
        const payload = data(frm);
        const plans = payload && payload.plans;
        if (!plans) return null;
        if (tab === "Custom") return plans.uploaded_draft || null;
        if (tab === "Approved") return plans.approved || null;
        return plans.system_draft || null;
    }

    function parseSnapshot(row) {
        if (!row) return null;
        const raw = row.snapshot_json;
        if (!raw) return null;
        if (typeof raw === "object") return raw;
        try {
            const parsed = JSON.parse(raw);
            return parsed && typeof parsed === "object" ? parsed : null;
        } catch (error) {
            return null;
        }
    }

    function getPlanForTab(frm, tab) {
        return parseSnapshot(planRow(frm, tab));
    }

    function hasPlan(frm, tab) {
        const row = planRow(frm, tab);
        const plan = parseSnapshot(row);
        return Boolean(row && plan && Array.isArray(plan.sheets) && plan.sheets.length);
    }

    function hasApprovedPlan(frm) {
        const payload = data(frm);
        return Boolean(planRow(frm, "Approved") || (payload && payload.approved_plan));
    }

    function sourceLabel(row) {
        return row && row.source_type === "Uploaded DXF" ? "Custom" : "System";
    }

    function activeSettings(frm) {
        const owner = stateOwner();
        const active = owner && typeof owner.activePlan === "function"
            ? owner.activePlan(frm, "System")
            : null;
        return active && active.settings ? { ...active.settings } : null;
    }

    function project(frm) {
        if (!frm || !frm.doc) return false;
        const payload = data(frm);
        if (!payload) return false;

        const systemRow = planRow(frm, "System");
        const customRow = planRow(frm, "Custom");
        const approvedRow = planRow(frm, "Approved");
        const systemPlan = parseSnapshot(systemRow);
        const customPlan = parseSnapshot(customRow);
        const approvedPlan = parseSnapshot(approvedRow);

        // Transitional read-only projection for legacy renderers. The source of
        // truth is the Plan workspace store; these assignments never save DCO.
        frm.doc.system_plan_json = systemPlan;
        frm.doc.cutting_plan_json = systemPlan;
        frm.doc.custom_plan_json = customPlan;
        frm.doc.approved_plan = payload.approved_plan || (approvedRow && approvedRow.name) || null;
        frm.doc.approved_plan_source = sourceLabel(approvedRow);
        frm.__almdina_approved_plan_snapshot = approvedPlan;
        frm.__almdina_approved_plan_order = frm.doc.name;

        const settings = activeSettings(frm);
        const editor = window.AlmdinaWorkspaceFieldEditor;
        if (settings && editor && typeof editor.project === "function") {
            editor.project(frm, settings, [
                "packing_mode",
                "cutting_machine_type",
                "kerf_mm",
                "trim_margin_mm",
                "optimization_time_limit_sec",
            ]);
        }
        return true;
    }

    function pendingMessage(frm) {
        const state = snapshot(frm);
        if (state && state.status === "error") {
            return __("تعذر تحميل خطة القص. أعد المحاولة.");
        }
        return __("جاري تحميل خطة القص...");
    }

    function renderPending(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.cutting_plan_html;
        const wrapper = field && field.$wrapper;
        if (!wrapper || !wrapper.length) return false;
        wrapper.html(`
            <div class="dco-plan-workspace-state" style="padding:18px;text-align:center;color:var(--text-muted,#687481);border:1px dashed var(--border-color,#ccd3da);border-radius:12px;background:var(--subtle-fg,#fafafa);">
                ${frappe.utils.escape_html(pendingMessage(frm))}
            </div>
        `);
        ensureLoad(frm);
        return true;
    }

    function ready(frm) {
        const state = snapshot(frm);
        return Boolean(state && state.status === "ready" && state.data);
    }

    function install() {
        const legacy = window.AlmdinaPlanTabsUX;
        if (!legacy || legacy.__a52WorkspaceOwned) return false;

        const wrapped = {
            ...legacy,
            __a52WorkspaceOwned: true,
            hasCustomPlan(frm) {
                return hasPlan(frm, "Custom");
            },
            hasApprovedPlan,
            getPlanForTab,
            ensureApprovedPlanLoaded(frm) {
                return ensureLoad(frm).then(() => getPlanForTab(frm, "Approved"));
            },
            renderDualTabs(frm) {
                if (!ready(frm)) return renderPending(frm);
                project(frm);
                return legacy.renderDualTabs(frm);
            },
            printActivePlan(frm) {
                if (!ready(frm)) {
                    ensureLoad(frm);
                    frappe.msgprint(__("انتظر حتى يكتمل تحميل خطة القص ثم أعد الطباعة."));
                    return false;
                }
                project(frm);
                return legacy.printActivePlan(frm);
            },
            afterRender(frm) {
                if (!ready(frm)) return renderPending(frm);
                project(frm);
                return legacy.afterRender(frm);
            },
        };
        window.AlmdinaPlanTabsUX = Object.freeze(wrapped);
        return true;
    }

    function refreshCurrent() {
        const frm = window.cur_frm;
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        const tabs = window.AlmdinaPlanTabsUX;
        if (tabs && typeof tabs.renderDualTabs === "function" && tabs.shouldShowPlanTabs(frm)) {
            tabs.renderDualTabs(frm);
        }
    }

    window.addEventListener("almdina:plan-workspace-updated", refreshCurrent);

    window.AlmdinaPlanWorkspacePresenterAdapter = Object.freeze({
        install,
        project,
        getPlanForTab,
        hasApprovedPlan,
        activeSettings,
        ready,
    });

    install();
})();
