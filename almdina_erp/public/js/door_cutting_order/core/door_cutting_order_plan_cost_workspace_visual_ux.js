(() => {
    "use strict";

    if (window.AlmdinaPlanCostWorkspaceVisualUX) return;

    const STYLE_ID = "dco-plan-cost-workspace-visual-ux-v1";
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
        return Boolean(
            system
            && system.validation
            && system.validation.needs_recalculation
        );
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
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .${ROOT_CLASS}{
                --dco-workspace-radius:16px;
                --dco-workspace-radius-sm:11px;
                --dco-workspace-shadow:0 6px 22px rgba(15,23,42,.055);
                --dco-workspace-shadow-hover:0 10px 28px rgba(15,23,42,.085);
                --dco-workspace-ring:0 0 0 3px rgba(36,144,239,.14);
            }
            .${ROOT_CLASS} [data-almdina-workspace-kind]{
                transition:border-color .16s ease,box-shadow .16s ease,background-color .16s ease;
            }
            .${ROOT_CLASS} [data-almdina-workspace-status="error"]{
                border-inline-start:3px solid #c2413a;
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

            .${ROOT_CLASS} [data-fieldname="plan_control_actions"][data-almdina-workspace-editing="1"]::before,
            .${ROOT_CLASS} [data-fieldname="order_cost_invoice_html"][data-almdina-workspace-editing="1"]::before{
                content:"وضع التعديل مفعّل — غيّر القيم المطلوبة ثم اضغط «حفظ» من أعلى الصفحة.";
                display:flex;align-items:center;min-height:38px;margin:0 0 10px;padding:8px 12px;
                border:1px solid rgba(36,144,239,.28);border-radius:var(--dco-workspace-radius-sm);
                background:rgba(36,144,239,.075);color:var(--text-color,#26313b);font-size:11px;font-weight:800;line-height:1.55;
            }
            .${ROOT_CLASS} [data-almdina-workspace-editing="1"] .almdina-workspace-field-editor{
                padding:4px;border-radius:12px;background:rgba(36,144,239,.055);
            }
            .${ROOT_CLASS} [data-almdina-workspace-editing="1"] .almdina-workspace-field-editor .form-control{
                min-height:40px;border-radius:10px;border-color:rgba(36,144,239,.34);background:var(--card-bg,#fff);
                font-weight:750;box-shadow:0 1px 2px rgba(15,23,42,.035);
            }
            .${ROOT_CLASS} [data-almdina-workspace-editing="1"] .almdina-workspace-field-editor .form-control:focus-visible,
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .dco-plan-tabs .btn:focus-visible,
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .btn:focus-visible,
            .${ROOT_CLASS} .dco-cost-actions .btn:focus-visible{
                outline:none !important;box-shadow:var(--dco-workspace-ring) !important;
            }

            .${ROOT_CLASS} [data-fieldname="plan_controls_intro"] .dco-plan-intro{
                gap:12px !important;margin:4px 0 10px !important;
            }
            .${ROOT_CLASS} [data-fieldname="plan_controls_intro"] .dco-plan-card{
                min-height:104px;padding:14px 15px;border-radius:var(--dco-workspace-radius) !important;
                border-color:var(--border-color,#dfe5ea) !important;
                background:linear-gradient(180deg,var(--card-bg,#fff),var(--subtle-fg,#fafbfc)) !important;
                box-shadow:0 3px 12px rgba(15,23,42,.035);
            }
            .${ROOT_CLASS} [data-fieldname="plan_controls_intro"] .dco-plan-card .label{
                font-size:10.5px !important;font-weight:800 !important;letter-spacing:.01em;
            }
            .${ROOT_CLASS} [data-fieldname="plan_controls_intro"] .dco-plan-card .value{
                font-size:17px !important;line-height:1.4 !important;
            }
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
            .${ROOT_CLASS} [data-fieldname="plan_control_actions"][data-almdina-workspace-stale="1"] .dco-recalculate-plan{
                box-shadow:0 0 0 3px rgba(190,125,25,.12);
            }
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .dco-plan-tabs{
                margin-bottom:14px !important;padding:5px !important;border-radius:13px !important;
                box-shadow:0 2px 8px rgba(15,23,42,.035);
            }
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .dco-plan-tabs .btn{
                min-height:36px !important;padding-inline:13px !important;
            }
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .dco-board-gallery > .dco-sheet-card{
                border-radius:13px !important;box-shadow:0 2px 8px rgba(15,23,42,.035) !important;
            }
            .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .dco-board-gallery > .dco-sheet-card:hover{
                box-shadow:var(--dco-workspace-shadow-hover) !important;
            }

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
            .${ROOT_CLASS} .dco-cost-table tbody tr:hover td{background:rgba(36,144,239,.035)}
            .${ROOT_CLASS} .dco-special-price-card{
                border-radius:14px !important;transition:border-color .14s ease,box-shadow .14s ease,transform .14s ease;
            }
            .${ROOT_CLASS} .dco-special-price-card:hover{
                border-color:#bcc8d2 !important;box-shadow:0 5px 16px rgba(15,23,42,.055);
            }
            .${ROOT_CLASS} .dco-invoice-total-card{
                border-radius:0 0 var(--dco-workspace-radius) var(--dco-workspace-radius) !important;padding:20px 22px !important;
            }
            .${ROOT_CLASS} .dco-invoice-total-card b{font-size:30px !important;letter-spacing:.015em}

            .${ROOT_CLASS} .page-actions [data-almdina-context-edit-mode$="-edit"],
            .${ROOT_CLASS} .page-actions [data-almdina-context-edit-mode$="-save"]{
                min-height:32px;border-radius:9px;font-weight:850;
            }
            .${ROOT_CLASS} .page-actions .dco-context-edit-cancel{border-radius:9px;font-weight:800}

            @media (max-width:900px){
                .${ROOT_CLASS} [data-fieldname="plan_controls_intro"] .dco-plan-intro{
                    grid-template-columns:repeat(2,minmax(0,1fr)) !important;
                }
                .${ROOT_CLASS} [data-fieldname="plan_control_actions"] .dco-plan-actions{grid-template-columns:1fr !important}
                .${ROOT_CLASS} .dco-cost-section{border-radius:14px !important}
            }
            @media (max-width:560px){
                .${ROOT_CLASS} [data-fieldname="plan_controls_intro"] .dco-plan-intro{
                    grid-template-columns:1fr !important;gap:8px !important;
                }
                .${ROOT_CLASS} [data-fieldname="plan_controls_intro"] .dco-plan-card{min-height:86px;padding:12px 13px}
                .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .dco-plan-tabs{
                    width:100% !important;overflow-x:auto;justify-content:flex-start !important;scrollbar-width:thin;
                }
                .${ROOT_CLASS} [data-fieldname="cutting_plan_html"] .dco-plan-tabs .btn{flex:0 0 auto;white-space:nowrap}
                .${ROOT_CLASS} .dco-cost-table{min-width:680px}
                .${ROOT_CLASS} .dco-cost-table th,.${ROOT_CLASS} .dco-cost-table td{padding:8px 9px}
                .${ROOT_CLASS} .dco-invoice-total-card{padding:16px !important}
                .${ROOT_CLASS} .dco-invoice-total-card b{font-size:25px !important}
                .${ROOT_CLASS} [data-fieldname="plan_control_actions"][data-almdina-workspace-editing="1"]::before,
                .${ROOT_CLASS} [data-fieldname="order_cost_invoice_html"][data-almdina-workspace-editing="1"]::before{
                    align-items:flex-start;font-size:10.5px;
                }
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

    function refresh(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return false;
        installStyles();
        addVisualScope(formRoot(frm));
        addVisualScope(pageRoot(frm));

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
        window.requestAnimationFrame(() => {
            if (window.cur_frm === frm) refresh(frm);
        });
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
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
        refresh,
        schedule,
    });
})();
