(() => {
    "use strict";

    if (window.AlmdinaPlanSettingsSummaryUX) return;

    const SUMMARY_CLASS = "dco-plan-settings-readonly";
    const OWNER_ATTR = "data-almdina-plan-settings-summary-owner";
    const STYLE_ID = "dco-plan-settings-summary-owner-css";
    const TIME_LIMIT_HELP = "أقصى مدة يمنحها النظام لمحرك التحسين للبحث عن توزيع أفضل. قد ينتهي البحث قبلها، وزيادتها قد تحسن بعض الخطط المعقدة لكنها تجعل المعاينة أبطأ.";

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function wrapperNode(wrapper) {
        if (!wrapper) return null;
        if (wrapper.nodeType) return wrapper;
        if (wrapper[0] && wrapper[0].nodeType) return wrapper[0];
        return null;
    }

    function formRoot(frm) {
        return wrapperNode(frm && frm.wrapper);
    }

    function anchorNode(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.plan_actions_section;
        return wrapperNode(field && (field.$wrapper || field.wrapper));
    }

    function workspaceReady(frm) {
        const owner = window.AlmdinaPlanWorkspaceState;
        const state = owner && typeof owner.snapshot === "function"
            ? owner.snapshot(frm)
            : null;
        return Boolean(state && state.status === "ready");
    }

    function isPlanEditing(frm) {
        const editor = window.AlmdinaPlanEditSessionUX;
        return Boolean(
            editor
            && typeof editor.isEditing === "function"
            && editor.isEditing(frm)
        );
    }

    function activeSettings(frm) {
        const adapter = window.AlmdinaPlanWorkspacePresenterAdapter;
        if (adapter && typeof adapter.activeSettings === "function") {
            return adapter.activeSettings(frm);
        }
        const owner = window.AlmdinaPlanWorkspaceState;
        const row = owner && typeof owner.activePlan === "function"
            ? owner.activePlan(frm, "System")
            : null;
        return row && row.settings ? { ...row.settings } : null;
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            [data-fieldname="plan_control_actions"] > .${SUMMARY_CLASS},
            [data-fieldname="plan_control_actions"] .form-control > .${SUMMARY_CLASS} {
                display:none !important;
            }
            .dco-plan-settings-readonly__label-help {
                display:inline-flex;
                align-items:center;
                justify-content:center;
                width:16px;
                height:16px;
                margin-inline-start:4px;
                border-radius:50%;
                border:1px solid var(--border-color,#dfe3e8);
                color:var(--text-muted,#667085);
                font-size:10px;
                cursor:help;
                vertical-align:middle;
            }
        `;
        document.head.appendChild(style);
    }

    function ownedSummary(frm) {
        const root = formRoot(frm);
        return root && root.querySelector
            ? root.querySelector(`.${SUMMARY_CLASS}[${OWNER_ATTR}="stable"]`)
            : null;
    }

    function removeOwnedSummary(frm) {
        const summary = ownedSummary(frm);
        if (summary) summary.remove();
    }

    function valueText(value, suffix = "") {
        if (value === null || value === undefined || String(value).trim() === "") {
            return "—";
        }
        return `${String(value)}${suffix}`;
    }

    function summaryMarkup(settings) {
        const values = [
            { label: "الخوارزمية", value: valueText(settings.packing_mode || "Auto Pro") },
            { label: "آلة القص", value: valueText(settings.cutting_machine_type || "Auto") },
            { label: "سماكة القص Kerf", value: valueText(settings.kerf_mm, " مم") },
            { label: "هامش التشذيب", value: valueText(settings.trim_margin_mm, " مم") },
            {
                label: "مهلة التحسين",
                value: valueText(settings.optimization_time_limit_sec, " ث"),
                help: TIME_LIMIT_HELP,
            },
        ];
        const items = values.map((item) => {
            const help = item.help
                ? `<span class="dco-plan-settings-readonly__label-help" title="${frappe.utils.escape_html(__(item.help))}" aria-label="${frappe.utils.escape_html(__(item.help))}">?</span>`
                : "";
            return `
                <div class="dco-plan-settings-readonly__item"${item.help ? ` title="${frappe.utils.escape_html(__(item.help))}"` : ""}>
                    <span class="dco-plan-settings-readonly__label">${frappe.utils.escape_html(__(item.label))}${help}</span>
                    <strong class="dco-plan-settings-readonly__value">${frappe.utils.escape_html(item.value)}</strong>
                </div>
            `;
        }).join("");
        return `
            <div class="dco-plan-settings-readonly__header">
                <div>
                    <h4 class="dco-plan-settings-readonly__title">${frappe.utils.escape_html(__("إعدادات خطة القص"))}</h4>
                    <p class="dco-plan-settings-readonly__help">${frappe.utils.escape_html(__("القيم المحفوظة في خطة القص الحالية. اضغط «تعديل» في هذا القسم لتغييرها."))}</p>
                </div>
            </div>
            <div class="dco-plan-settings-readonly__grid">${items}</div>
        `;
    }

    function render(frm) {
        if (!frm || !frm.doc || frm.doctype !== "Door Cutting Order") return false;
        installStyles();
        if (!workspaceReady(frm) || isPlanEditing(frm)) {
            removeOwnedSummary(frm);
            return false;
        }

        const settings = activeSettings(frm);
        const anchor = anchorNode(frm);
        if (!settings || !anchor || !anchor.parentNode) {
            removeOwnedSummary(frm);
            return false;
        }

        let summary = ownedSummary(frm);
        if (!summary) {
            summary = document.createElement("section");
            summary.className = SUMMARY_CLASS;
            summary.setAttribute(OWNER_ATTR, "stable");
            anchor.parentNode.insertBefore(summary, anchor);
        }
        summary.setAttribute("data-almdina-order", String(frm.doc.name || ""));
        summary.innerHTML = summaryMarkup(settings);
        return true;
    }

    function schedule(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        const context = documentContext();
        if (context && typeof context.scheduleFrame === "function") {
            context.scheduleFrame(frm, "plan-settings-summary-owner", () => render(frm));
            return;
        }
        window.requestAnimationFrame(() => {
            if (window.cur_frm === frm) render(frm);
        });
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
        almdina_edit_session_changed(frm) { schedule(frm); },
        refresh_plan_controls(frm) { schedule(frm); },
    });

    [
        "almdina:permissions-updated",
        "almdina:surfaces-settled",
        "almdina:plan-workspace-updated",
    ].forEach((eventName) => {
        window.addEventListener(eventName, () => {
            const frm = window.cur_frm;
            if (frm && frm.doctype === "Door Cutting Order") schedule(frm);
        });
    });

    window.AlmdinaPlanSettingsSummaryUX = Object.freeze({
        TIME_LIMIT_HELP,
        activeSettings,
        render,
        schedule,
    });
})();