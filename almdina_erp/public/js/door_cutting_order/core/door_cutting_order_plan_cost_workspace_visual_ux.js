(() => {
    "use strict";

    if (window.AlmdinaPlanCostWorkspaceVisualUX) return;

    const STYLE_ID = "dco-plan-cost-workspace-visual-ux-v8";
    const LEGACY_STYLE_IDS = [
        "dco-plan-cost-workspace-visual-ux-v1",
        "dco-plan-cost-workspace-visual-ux-v2",
        "dco-plan-cost-workspace-visual-ux-v3",
        "dco-plan-cost-workspace-visual-ux-v4",
        "dco-plan-cost-workspace-visual-ux-v5",
        "dco-plan-cost-workspace-visual-ux-v6",
        "dco-plan-cost-workspace-visual-ux-v7",
    ];
    const TAB_ACTIVE_CLASS = "dco-results-tab-active";
    const ROOT_CLASS = "dco-a53-workspace-polish";
    const PLAN_FIELDS = Object.freeze([
        "plan_controls_intro",
        "plan_control_actions",
        "cutting_plan_html",
        "packing_mode",
        "cutting_machine_type",
        "kerf_mm",
        "trim_margin_mm",
        "optimization_time_limit_sec",
    ]);
    const COST_FIELDS = Object.freeze([
        "order_cost_invoice_html",
        "board_rate_usd",
        "cutting_cost_per_board_usd",
    ]);

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function unwrap(wrapper) {
        return wrapper && (wrapper.nodeType ? wrapper : wrapper[0]);
    }

    function formRoot(frm) {
        return unwrap(frm && frm.wrapper);
    }

    function pageRoot(frm) {
        return unwrap(frm && frm.page && frm.page.wrapper);
    }

    function activeTabFieldname(frm) {
        const activeTab = frm && typeof frm.get_active_tab === "function"
            ? frm.get_active_tab()
            : null;
        const fromActive = String(
            activeTab
            && activeTab.df
            && activeTab.df.fieldname
            || ""
        ).trim();
        if (fromActive) return fromActive;
        return String(
            frm
            && frm.layout
            && frm.layout.current_tab
            && frm.layout.current_tab.df
            && frm.layout.current_tab.df.fieldname
            || ""
        ).trim();
    }

    function stateFrom(owner, frm) {
        return owner && typeof owner.snapshot === "function" ? owner.snapshot(frm) : null;
    }

    function planState(frm) {
        return stateFrom(window.AlmdinaPlanWorkspaceState, frm);
    }

    function costState(frm) {
        return stateFrom(window.AlmdinaCostWorkspaceState, frm);
    }

    function normalizedStatus(state) {
        const status = String((state && state.status) || "idle");
        return ["idle", "loading", "ready", "error"].includes(status) ? status : "idle";
    }

    function planIsStale(state) {
        if (!state || state.status !== "ready" || !state.data) return false;
        const plans = state.data.plans || {};
        const system = plans.system_draft || null;
        return Boolean(system && system.validation && system.validation.needs_recalculation);
    }

    function fieldNode(frm, fieldname) {
        const field = frm && frm.fields_dict && frm.fields_dict[fieldname];
        const wrapper = field && field.$wrapper;
        return wrapper && wrapper.length ? wrapper[0] : null;
    }

    function applySurfaceState(frm, kind, fieldnames, state, options = {}) {
        const status = normalizedStatus(state);
        const editing = Boolean(state && state.editing);
        fieldnames.forEach((fieldname) => {
            const node = fieldNode(frm, fieldname);
            if (!node) return;
            node.setAttribute("data-almdina-workspace-kind", kind);
            node.setAttribute("data-almdina-workspace-status", status);
            node.setAttribute("data-almdina-workspace-editing", editing ? "1" : "0");
            if (options.stale) node.setAttribute("data-almdina-workspace-stale", "1");
            else node.removeAttribute("data-almdina-workspace-stale");
            if (status === "loading") node.setAttribute("aria-busy", "true");
            else node.removeAttribute("aria-busy");
            if (["cutting_plan_html", "order_cost_invoice_html"].includes(fieldname)) {
                node.setAttribute("aria-live", "polite");
            }
        });
    }

    function installStyles() {
        LEGACY_STYLE_IDS.forEach((id) => {
            const legacy = document.getElementById(id);
            if (legacy) legacy.remove();
        });
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .${ROOT_CLASS}{
                --dco-workspace-radius:16px;
                --dco-workspace-radius-sm:11px;
                --dco-workspace-shadow:0 6px 22px rgba(15,23,42,.055);
                --dco-workspace-shadow-hover:0 10px 28px rgba(15,23,42,.085);
                --dco-workspace-ring:0 0 0 3px color-mix(in srgb, var(--alm-primary, #172033) 14%, transparent);
                --dco-plan-card-inset-inline:18px;
                --dco-plan-card-inset-block-start:16px;
                --dco-plan-card-inset-block-end:14px;
                --dco-plan-section-gap: var(--dco-section-stack-gap, 8px);
            }
            .${ROOT_CLASS} .layout-main-section .form-page,
            .${ROOT_CLASS} .layout-main-section-wrapper .form-page,
            .layout-main-section.${ROOT_CLASS} .form-page,
            .layout-main-section-wrapper.${ROOT_CLASS} .form-page,
            body:has(.dco-operator-form.${TAB_ACTIVE_CLASS}) .layout-main-section .form-page,
            body:has(.dco-operator-form.${TAB_ACTIVE_CLASS}) .layout-main-section-wrapper .form-page,
            body:has(.dco-operator-form.${TAB_ACTIVE_CLASS}) .dco-order-tab-layout .layout-main-section .form-page {
                max-width: none !important;
                margin-inline: 0 !important;
                width: 100% !important;
                padding-inline: 16px !important;
                box-sizing: border-box !important;
            }
            body:has(.dco-operator-form.${TAB_ACTIVE_CLASS}) .dco-operator-form {
                --dco-tab-card-inset-inline: 18px;
            }
            .dco-operator-form .form-section:has([data-fieldname="plan_control_actions"]) .form-column,
            .dco-operator-form .form-section:has([data-fieldname="cutting_plan_html"]) .form-column,
            .${ROOT_CLASS} .form-section:has([data-fieldname="plan_control_actions"]) .form-column,
            .${ROOT_CLASS} .form-section:has([data-fieldname="cutting_plan_html"]) .form-column {
                width: 100% !important;
                max-width: none !important;
                flex: 0 0 100% !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] {
                width: 100% !important;
                max-width: 100% !important;
                box-sizing: border-box !important;
                padding: 0 !important;
                margin: 0 !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] > .frappe-control,
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] > .form-group {
                padding: 0 !important;
                margin: 0 !important;
            }
            .dco-operator-form .dco-plan-settings-readonly[data-almdina-plan-settings-summary-owner="stable"],
            .${ROOT_CLASS} .dco-plan-settings-readonly[data-almdina-plan-settings-summary-owner="stable"] {
                width: 100% !important;
                max-width: none !important;
                box-sizing: border-box !important;
                margin-inline: 0 !important;
                margin-block: 0 var(--dco-section-stack-gap, 8px) !important;
                padding: 6px 12px !important;
                border: 1px solid var(--alm-card-border, #e4e8ee) !important;
                border-radius: var(--alm-radius-sm, 10px) !important;
                background: var(--alm-card, #fff) !important;
                box-shadow: none !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-readonly,
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-editor {
                width: 100% !important;
                max-width: none !important;
                box-sizing: border-box !important;
                margin-inline: 0 !important;
                margin-block: 0 var(--dco-plan-section-gap) !important;
                padding: 0 !important;
                border: 1px solid var(--border-color,#e2e8f0) !important;
                border-radius: var(--dco-workspace-radius) !important;
                background: var(--card-bg,#fff) !important;
                box-shadow: var(--dco-workspace-shadow) !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-readonly {
                padding-block: 8px 8px !important;
                padding-inline: var(--dco-plan-card-inset-inline) !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-editor__header,
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-editor__grid {
                padding-inline: var(--dco-plan-card-inset-inline) !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-editor__header {
                padding-top: var(--dco-plan-card-inset-block-start) !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-editor__action-bar {
                padding-inline: var(--dco-plan-card-inset-inline) !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"]:has(.dco-plan-settings-editor) .dco-plan-actions-shell {
                display: none !important;
            }
            .${ROOT_CLASS} .dco-plan-settings-readonly[data-almdina-plan-settings-summary-owner="stable"] .dco-plan-settings-readonly__strip,
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-readonly .dco-plan-settings-readonly__strip {
                display: flex !important;
                flex-wrap: nowrap !important;
                align-items: center !important;
                gap: 6px !important;
                width: 100% !important;
                min-width: 0 !important;
                overflow-x: auto !important;
                font-size: 11px !important;
                line-height: 1.2 !important;
            }
            .dco-operator-form .dco-plan-section-card.dco-layout-card > .section-head,
            .dco-operator-form .dco-plan-section-card.dco-layout-card > .section-body,
            .dco-operator-form .dco-plan-section-card.dco-layout-card .form-column,
            .dco-operator-form [data-fieldname="cutting_plan_html"] {
                max-width: none !important;
                width: 100% !important;
                margin-inline: 0 !important;
                box-sizing: border-box !important;
            }
            .dco-operator-form .dco-plan-actions-section.form-section,
            .dco-operator-form .form-section:has([data-fieldname="plan_control_actions"]) {
                border: none !important;
                border-bottom: none !important;
                margin: 0 !important;
                padding: 0 !important;
                min-height: 0 !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-readonly__header,
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-editor__header {
                margin-bottom: 8px !important;
                padding-inline: 0 !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-readonly__grid {
                gap: 5px !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-readonly__item {
                padding: 5px 7px !important;
                border-radius: 7px !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-readonly__label {
                font-size: 9px !important;
                margin-bottom: 1px !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-readonly__value {
                font-size: 10.5px !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-editor {
                padding-block: 6px !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-editor__lead {
                display: none !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-editor__grid {
                gap: 6px !important;
                grid-template-columns: none !important;
                flex-wrap: nowrap !important;
                padding-bottom: 0 !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-editor .form-control,
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-editor select.form-control {
                min-height: 28px !important;
                height: 28px !important;
                padding: 2px 8px !important;
                font-size: 11px !important;
                border: 1px solid var(--border-color, #d0d5dd) !important;
                border-radius: 8px !important;
                background: var(--card-bg, #fff) !important;
                box-shadow: none !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-editor__field label {
                margin: 0 !important;
                margin-bottom: 0 !important;
                font-size: 11px !important;
                font-weight: 700 !important;
                color: var(--text-muted,#667085) !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-editor__help {
                display: none !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-editor__header {
                margin-bottom: 14px !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-editor__title {
                font-size: 15px !important;
                font-weight: 800 !important;
                letter-spacing: -.01em !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-editor__subtitle {
                font-size: 10.5px !important;
                font-weight: 600 !important;
                color: var(--text-muted,#98a2b3) !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-editor__action-bar {
                padding-block: 11px !important;
                min-height: 52px !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-editor__stale-copy {
                font-size: 11px !important;
                font-weight: 700 !important;
                line-height: 1.6 !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-editor__recalc-btn.btn {
                min-height: 36px !important;
                height: 36px !important;
                padding: 0 12px !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-stale-banner {
                margin: 0 0 6px !important;
                padding: 6px 10px !important;
                font-size: 10.5px !important;
                line-height: 1.45 !important;
                align-items: center !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-actions-shell {
                padding-block: 8px 10px !important;
                padding-inline: 14px !important;
            }
            /* Beat Frappe: body:not(.full-width) .std-form-layout .section-body { max-width: 900px } */
            body:not(.full-width) .${ROOT_CLASS} .std-form-layout .dco-plan-actions-section > .section-head,
            body:not(.full-width) .${ROOT_CLASS} .std-form-layout .dco-plan-actions-section > .section-body,
            body:not(.full-width) .${ROOT_CLASS} .std-form-layout .dco-plan-section-card.dco-layout-card > .section-head,
            body:not(.full-width) .${ROOT_CLASS} .std-form-layout .dco-plan-section-card.dco-layout-card > .section-body,
            body:not(.full-width) .${ROOT_CLASS} .std-form-layout .form-section:has([data-fieldname="plan_control_actions"]) > .section-head,
            body:not(.full-width) .${ROOT_CLASS} .std-form-layout .form-section:has([data-fieldname="plan_control_actions"]) > .section-body,
            body:not(.full-width) .${ROOT_CLASS} .std-form-layout .form-section:has([data-fieldname="cutting_plan_html"]) > .section-head,
            body:not(.full-width) .${ROOT_CLASS} .std-form-layout .form-section:has([data-fieldname="cutting_plan_html"]) > .section-body {
                max-width: none !important;
                width: 100% !important;
                margin: 0 !important;
                margin-inline: 0 !important;
                box-sizing: border-box !important;
            }
            .${ROOT_CLASS} .dco-plan-actions-section > .section-body,
            .${ROOT_CLASS} .dco-plan-section-card.dco-layout-card > .section-body,
            .${ROOT_CLASS} .dco-plan-actions-section .form-column,
            .${ROOT_CLASS} .dco-plan-section-card.dco-layout-card .form-column,
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] > .frappe-control,
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] > .form-group,
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] > .frappe-control,
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] > .form-group,
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .control-input-wrapper {
                width: 100% !important;
                max-width: none !important;
                margin-inline: 0 !important;
                flex: 1 1 100% !important;
                box-sizing: border-box !important;
            }
            .${ROOT_CLASS} .dco-plan-actions-section > .section-body,
            .${ROOT_CLASS} .dco-plan-section-card.dco-layout-card > .section-body {
                margin: 0 !important;
                padding-top: 0 !important;
            }
            body:has(.dco-operator-form.${TAB_ACTIVE_CLASS}) .dco-operator-form {
                --page-max-width: none;
            }
            .${ROOT_CLASS} .dco-plan-section-card.dco-layout-card {
                margin-block: 0 var(--dco-plan-section-gap) !important;
                margin-inline: 0 !important;
                width: 100% !important;
                max-width: none !important;
            }
            .${ROOT_CLASS} .dco-plan-section-card.dco-layout-card.dco-ui-card {
                padding: 0 !important;
            }
            .${ROOT_CLASS} .dco-plan-section-card.dco-layout-card > .section-head {
                padding: var(--dco-plan-card-inset-block-start) var(--dco-plan-card-inset-inline) 0 !important;
                border-bottom: none !important;
                margin-bottom: 0 !important;
            }
            .${ROOT_CLASS} .dco-plan-section-card.dco-layout-card > .section-body {
                padding: 0 var(--dco-plan-card-inset-inline) var(--dco-plan-card-inset-block-end) !important;
            }
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"],
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .dco-plan-context-actions-host,
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .dco-plan-tab-content,
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .dco-cutting-plan,
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .dco-plan-context-bar {
                width: 100% !important;
                max-width: none !important;
                box-sizing: border-box !important;
            }
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .dco-plan-tabs {
                width: 100% !important;
                max-width: none !important;
                margin: 0 0 var(--dco-section-stack-gap, 8px) 0 !important;
                box-sizing: border-box !important;
            }
            .${ROOT_CLASS} .dco-plan-actions-section.form-section {
                width: 100% !important;
                max-width: none !important;
                padding: 0 !important;
                margin: 0 !important;
                border: none !important;
                border-bottom: none !important;
            }
            .${ROOT_CLASS} .dco-plan-actions-section > .section-head {
                display: none !important;
            }
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .dco-plan-meta-strip,
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .dco-plan-tab-content,
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .dco-extra-addon-legend,
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .dco-margin-policy-alert,
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .dco-board-gallery {
                width: 100% !important;
                max-width: none !important;
                box-sizing: border-box !important;
            }
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .dco-board-gallery > .dco-sheet-card {
                width: 100% !important;
                max-width: none !important;
            }
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .dco-board-gallery .dco-sheet-board {
                width: 100% !important;
                max-width: none !important;
                margin: 0 !important;
            }
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .frappe-control,
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .control-input-wrapper {
                padding-inline: 0 !important;
            }
            .${ROOT_CLASS} [data-almdina-workspace-kind]{
                transition:border-color .16s ease,box-shadow .16s ease,background-color .16s ease;
            }
            .${ROOT_CLASS} [data-almdina-workspace-status="error"]{border-inline-start:3px solid #c2413a;}

            /* The outer HTML-field surface owns page height while lazy assets/data
               are loading. This keeps Comments/Activity below the workspace and
               removes the first-visit layout jump without delays or hiding content. */
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"][data-almdina-workspace-status="loading"],
            .${ROOT_CLASS} [data-fieldname="order_cost_invoice_html"][data-almdina-workspace-status="loading"]{
                min-height:240px;
            }
            .${ROOT_CLASS} [data-almdina-workspace-status="loading"] .dco-plan-workspace-state,
            .${ROOT_CLASS} [data-almdina-workspace-status="loading"] .dco-cost-empty{
                position:relative;overflow:hidden;min-height:72px;display:flex;align-items:center;justify-content:center;
                border:1px dashed var(--border-color,#d9e0e6);border-radius:var(--dco-workspace-radius-sm);
                background:linear-gradient(180deg,var(--subtle-fg,#f8fafc),var(--card-bg,#fff));font-weight:750;
            }
            .${ROOT_CLASS} [data-almdina-workspace-status="loading"] .dco-plan-workspace-state::after,
            .${ROOT_CLASS} [data-almdina-workspace-status="loading"] .dco-cost-empty::after{
                content:"";position:absolute;inset:0;transform:translateX(-110%);
                background:linear-gradient(100deg,transparent,rgba(255,255,255,.62),transparent);
                animation:dco-a53-workspace-shimmer 1.25s ease-in-out infinite;pointer-events:none;
            }
            @keyframes dco-a53-workspace-shimmer{to{transform:translateX(110%)}}

            .${ROOT_CLASS} [data-fieldname="plan_controls_intro"][data-almdina-workspace-editing="1"]{
                display:none !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"][data-almdina-workspace-editing="1"]::before{
                content:none !important;
                display:none !important;
            }
            .${ROOT_CLASS} [data-fieldname="order_cost_invoice_html"][data-almdina-workspace-editing="1"]::before{
                content:"وضع التعديل مفعّل — غيّر القيم المطلوبة ثم اضغط «حفظ» من أعلى الصفحة.";
                display:flex;align-items:center;min-height:38px;margin:0 0 10px;padding:8px 12px;
                border:1px solid color-mix(in srgb, var(--alm-primary, #172033) 28%, transparent);border-radius:var(--dco-workspace-radius-sm);
                background:color-mix(in srgb, var(--alm-primary, #172033) 8%, transparent);color:var(--text-color,#26313b);font-size:11px;font-weight:800;line-height:1.55;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"][data-almdina-workspace-editing="1"] .dco-plan-stale-banner{
                margin:0 0 6px !important;
            }
            .${ROOT_CLASS} [data-almdina-workspace-editing="1"] .almdina-workspace-field-editor{
                padding:4px;border-radius:12px;background:color-mix(in srgb, var(--alm-primary, #172033) 6%, transparent);
            }
            .${ROOT_CLASS} [data-almdina-workspace-editing="1"] .almdina-workspace-field-editor .form-control{
                min-height:32px;border-radius:8px;border:1px solid var(--border-color,#cfd6de) !important;border-color:color-mix(in srgb, var(--alm-primary, #172033) 34%, transparent);background:var(--card-bg,#fff);
                font-weight:750;box-shadow:inset 0 1px 2px rgba(15,23,42,.03);
            }
            .${ROOT_CLASS} [data-almdina-workspace-editing="1"] .almdina-workspace-field-editor .form-control:focus-visible,
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .dco-plan-tabs .btn:focus-visible,
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .btn:focus-visible,
            .${ROOT_CLASS} .dco-cost-actions .btn:focus-visible{
                outline:none !important;box-shadow:var(--dco-workspace-ring) !important;
            }

            .${ROOT_CLASS} [data-fieldname="plan_controls_intro"] .dco-plan-intro{gap:12px !important;margin:4px 0 10px !important;}
            .${ROOT_CLASS} [data-fieldname="plan_controls_intro"] .dco-plan-card{
                min-height:104px;padding:14px 15px;border-radius:var(--dco-workspace-radius) !important;
                border-color:var(--border-color,#dfe5ea) !important;
                background:linear-gradient(180deg,var(--card-bg,#fff),var(--subtle-fg,#fafbfc)) !important;
                box-shadow:0 3px 12px rgba(15,23,42,.035);
            }
            .${ROOT_CLASS} [data-fieldname="plan_controls_intro"] .dco-plan-card .label{font-size:10.5px !important;font-weight:800 !important;letter-spacing:.01em;}
            .${ROOT_CLASS} [data-fieldname="plan_controls_intro"] .dco-plan-card .value{font-size:17px !important;line-height:1.4 !important;}
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-actions-shell{
                border-radius:var(--dco-workspace-radius) !important;border-color:var(--border-color,#dce3e8) !important;
                background:var(--card-bg,#fff) !important;box-shadow:var(--dco-workspace-shadow) !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-actions > .btn,
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-document-actions .btn{
                transition:transform .14s ease,box-shadow .14s ease,border-color .14s ease;
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-actions > .btn:hover:not(:disabled),
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-document-actions .btn:hover:not(:disabled){
                transform:translateY(-1px);box-shadow:0 5px 14px rgba(15,23,42,.08);
            }
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"][data-almdina-workspace-stale="1"] .dco-recalculate-plan{box-shadow:0 0 0 3px rgba(190,125,25,.12);}
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .dco-plan-tabs{
                margin-bottom:var(--dco-section-stack-gap, 8px) !important;
                padding:0 !important;
                border-radius:0 !important;
                box-shadow:none;
                background:transparent;
            }
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .dco-plan-tabs .btn{
                min-height:36px !important;
                padding-inline:12px !important;
            }
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .dco-board-gallery > .dco-sheet-card{
                border-radius:13px !important;box-shadow:0 2px 8px rgba(15,23,42,.035) !important;
            }
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .dco-board-gallery > .dco-sheet-card:hover{box-shadow:var(--dco-workspace-shadow-hover) !important;}

            .${ROOT_CLASS} .dco-cost-shell{max-width:1360px;padding:6px 0 22px}
            .${ROOT_CLASS} .dco-cost-section{
                margin-top:14px;border-radius:var(--dco-workspace-radius) !important;border-color:var(--border-color,#dce3e8) !important;
                box-shadow:var(--dco-workspace-shadow);
            }
            .${ROOT_CLASS} .dco-cost-section-title{
                min-height:50px;padding:14px 16px !important;
                background:linear-gradient(180deg,var(--subtle-fg,#f8fafc),var(--card-bg,#fff)) !important;
            }
            .${ROOT_CLASS} .dco-cost-section-title h4{font-size:14.5px !important;letter-spacing:.005em}
            .${ROOT_CLASS} .dco-cost-table-wrap{scrollbar-gutter:stable}
            .${ROOT_CLASS} .dco-cost-table th{
                position:sticky;top:0;z-index:2;background:var(--subtle-fg,#f7f9fb) !important;
                box-shadow:0 1px 0 var(--border-color,#e7ebef);
            }
            .${ROOT_CLASS} .dco-cost-table tbody tr{transition:background-color .12s ease}
            .${ROOT_CLASS} .dco-cost-table tbody tr:hover td{background:color-mix(in srgb, var(--alm-primary, #172033) 4%, transparent)}
            .${ROOT_CLASS} .dco-special-price-card{
                border-radius:14px !important;transition:border-color .14s ease,box-shadow .14s ease,transform .14s ease;
            }
            .${ROOT_CLASS} .dco-special-price-card:hover{border-color:#bcc8d2 !important;box-shadow:0 5px 16px rgba(15,23,42,.055);}
            .${ROOT_CLASS} .dco-invoice-total-card{
                border-radius:0 0 var(--dco-workspace-radius) var(--dco-workspace-radius) !important;padding:20px 22px !important;
            }
            .${ROOT_CLASS} .dco-invoice-total-card b{font-size:30px !important;letter-spacing:.015em}

            .${ROOT_CLASS} .page-actions [data-almdina-context-edit-mode$="-edit"],
            .${ROOT_CLASS} .page-actions [data-almdina-context-edit-mode$="-save"]{min-height:32px;border-radius:9px;font-weight:850;}
            .${ROOT_CLASS} .page-actions .dco-context-edit-cancel{border-radius:9px;font-weight:800}

            @media (max-width:900px){
                .${ROOT_CLASS} [data-fieldname="plan_controls_intro"] .dco-plan-intro{grid-template-columns:repeat(2,minmax(0,1fr)) !important;}
                .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-actions{grid-template-columns:1fr !important}
                .${ROOT_CLASS} .dco-cost-section{border-radius:14px !important}
                .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-readonly,
                .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-editor,
                .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-actions-shell,
                .${ROOT_CLASS} .dco-plan-section-card.dco-layout-card > .section-head,
                .${ROOT_CLASS} .dco-plan-section-card.dco-layout-card > .section-body{
                    padding-inline:var(--dco-tab-card-inset-inline, 36px) !important;
                }
                .${ROOT_CLASS} .dco-plan-settings-readonly[data-almdina-plan-settings-summary-owner="stable"]{
                    padding:6px 12px !important;
                }
            }
            @media (max-width:560px){
                .${ROOT_CLASS} [data-fieldname="cutting_plan_html"][data-almdina-workspace-status="loading"],
                .${ROOT_CLASS} [data-fieldname="order_cost_invoice_html"][data-almdina-workspace-status="loading"]{min-height:170px;}
                .${ROOT_CLASS} [data-fieldname="plan_controls_intro"] .dco-plan-intro{grid-template-columns:1fr !important;gap:8px !important;}
                .${ROOT_CLASS} [data-fieldname="plan_controls_intro"] .dco-plan-card{min-height:86px;padding:12px 13px}
                .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-readonly,
                .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-settings-editor,
                .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-actions-shell,
                .${ROOT_CLASS} .dco-plan-section-card.dco-layout-card > .section-head,
                .${ROOT_CLASS} .dco-plan-section-card.dco-layout-card > .section-body{
                    padding-inline:var(--dco-tab-card-inset-inline, 32px) !important;
                }
                .${ROOT_CLASS} .dco-plan-settings-readonly[data-almdina-plan-settings-summary-owner="stable"]{
                    padding:6px 12px !important;
                }
                .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .dco-plan-tabs{
                    width:100% !important;overflow-x:auto;justify-content:flex-start !important;scrollbar-width:thin;
                }
                .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .dco-plan-tabs .btn{flex:0 0 auto;white-space:nowrap}
                .${ROOT_CLASS} .dco-cost-table{min-width:680px}
                .${ROOT_CLASS} .dco-cost-table th,.${ROOT_CLASS} .dco-cost-table td{padding:8px 9px}
                .${ROOT_CLASS} .dco-invoice-total-card{padding:16px !important}
                .${ROOT_CLASS} .dco-invoice-total-card b{font-size:25px !important}
                .${ROOT_CLASS} [data-fieldname="order_cost_invoice_html"][data-almdina-workspace-editing="1"]::before{align-items:flex-start;font-size:10.5px;}
            }
            @media (prefers-reduced-motion:reduce){
                .${ROOT_CLASS} *, .${ROOT_CLASS} *::before, .${ROOT_CLASS} *::after{
                    scroll-behavior:auto !important;animation-duration:.001ms !important;
                    animation-iteration-count:1 !important;transition-duration:.001ms !important;
                }
            }
        `;
        document.head.appendChild(style);
    }

    function addVisualScope(node) {
        if (node && node.classList) node.classList.add(ROOT_CLASS);
    }

    function syncTabScope(frm) {
        const root = formRoot(frm);
        const onPlanTab = activeTabFieldname(frm) === "results_tab";
        if (root && root.classList) {
            root.classList.toggle(TAB_ACTIVE_CLASS, onPlanTab);
        }
        if (typeof document !== "undefined" && document.body && document.body.classList) {
            document.body.classList.toggle("dco-plan-results-tab-active", onPlanTab);
        }
        return onPlanTab;
    }

    function scopeLayoutAncestors(frm) {
        const root = formRoot(frm);
        if (!root) return;
        addVisualScope(root);
        let node = root.parentElement;
        while (node) {
            if (
                node.classList
                && (
                    node.classList.contains("layout-main-section")
                    || node.classList.contains("layout-main-section-wrapper")
                    || node.classList.contains("form-page")
                )
            ) {
                addVisualScope(node);
            }
            node = node.parentElement;
        }
        addVisualScope(pageRoot(frm));
    }

    function refresh(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return false;
        installStyles();
        syncTabScope(frm);
        scopeLayoutAncestors(frm);
        const plan = planState(frm);
        const cost = costState(frm);
        applySurfaceState(frm, "plan", PLAN_FIELDS, plan, { stale: planIsStale(plan) });
        applySurfaceState(frm, "cost", COST_FIELDS, cost);
        return true;
    }

    function schedule(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        const context = documentContext();
        if (context && typeof context.scheduleFrame === "function") {
            context.scheduleFrame(frm, "a53-plan-cost-workspace-visuals", () => refresh(frm));
            return;
        }
        if (window.requestAnimationFrame) {
            window.requestAnimationFrame(() => {
                if (window.cur_frm === frm) refresh(frm);
            });
            return;
        }
        if (window.cur_frm === frm) refresh(frm);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
        on_tab_change(frm) { schedule(frm); },
        almdina_edit_session_changed(frm) { schedule(frm); },
        refresh_plan_controls(frm) { schedule(frm); },
    });

    [
        "almdina:plan-workspace-updated",
        "almdina:cost-workspace-updated",
        "almdina:permissions-updated",
        "almdina:surfaces-settled",
    ].forEach((eventName) => {
        window.addEventListener(eventName, () => {
            const frm = window.cur_frm;
            if (frm && frm.doctype === "Door Cutting Order") schedule(frm);
        });
    });

    window.AlmdinaPlanCostWorkspaceVisualUX = Object.freeze({
        PLAN_FIELDS,
        COST_FIELDS,
        TAB_ACTIVE_CLASS,
        refresh,
        schedule,
    });
})();