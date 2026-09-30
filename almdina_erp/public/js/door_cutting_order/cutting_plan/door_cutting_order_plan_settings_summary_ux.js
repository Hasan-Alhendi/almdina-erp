(() => {
    "use strict";

    if (window.AlmdinaPlanSettingsSummaryUX) return;

    const SUMMARY_CLASS = "dco-plan-settings-readonly";
    const OWNER_ATTR = "data-almdina-plan-settings-summary-owner";
    const STYLE_ID = "dco-plan-settings-summary-owner-css-v2";
    const LEGACY_STYLE_IDS = ["dco-plan-settings-summary-owner-css"];
    const TIME_LIMIT_HELP = "أقصى مدة يمنحها النظام لمحرك التحسين للبحث عن توزيع أفضل. قد ينتهي البحث قبلها، وزيادتها قد تحسن بعض الخطط المعقدة لكنها تجعل المعاينة أبطأ.";
    const FALLBACK_SPECS = Object.freeze([
        Object.freeze({ fieldname: "kerf_mm", shortLabel: "الشفرة", fieldtype: "Float", suffix: "مم" }),
        Object.freeze({ fieldname: "trim_margin_mm", shortLabel: "التشذيب", fieldtype: "Float", suffix: "مم" }),
        Object.freeze({ fieldname: "packing_mode", shortLabel: "الخوارزمية", fieldtype: "Select" }),
        Object.freeze({ fieldname: "cutting_machine_type", shortLabel: "الآلة", fieldtype: "Select" }),
        Object.freeze({
            fieldname: "optimization_time_limit_sec",
            shortLabel: "المهلة",
            fieldtype: "Float",
            suffix: "ث",
            help: TIME_LIMIT_HELP,
        }),
    ]);

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

    function settingSpecs(frm, settings) {
        const editor = window.AlmdinaPlanEditSessionUX;
        if (editor && typeof editor.planSettingSpecs === "function") {
            return editor.planSettingSpecs(frm, settings || {});
        }
        return FALLBACK_SPECS;
    }

    function displayValue(spec, settings) {
        const raw = settings ? settings[spec.fieldname] : null;
        if (spec.fieldtype === "Select") {
            const normalized = String(raw ?? "").trim();
            const option = (spec.options || []).find((entry) => String(entry.value) === normalized);
            if (option && option.label) return String(option.label);
            if (normalized) return normalized;
            if (spec.fieldname === "packing_mode") return "Auto Pro";
            if (spec.fieldname === "cutting_machine_type") return "Auto";
            return "—";
        }
        if (raw === null || raw === undefined || String(raw).trim() === "") return "—";
        return String(raw);
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
            .${SUMMARY_CLASS}[${OWNER_ATTR}="stable"] {
                display:block !important;
                width:100% !important;
                max-width:none !important;
                box-sizing:border-box !important;
                margin:0 0 var(--dco-section-stack-gap, 8px) !important;
                margin-inline:0 !important;
                padding:6px 12px !important;
                border:1px solid var(--alm-card-border,#e4e8ee) !important;
                border-radius:var(--alm-radius-sm,10px) !important;
                background:var(--alm-card,#fff) !important;
                box-shadow:none !important;
                direction:rtl;
            }
            .${SUMMARY_CLASS} .dco-plan-settings-readonly__strip {
                display:flex !important;
                flex-wrap:nowrap !important;
                align-items:center !important;
                gap:6px !important;
                width:100% !important;
                min-width:0 !important;
                overflow-x:auto !important;
                font-size:11px;
                line-height:1.2;
                color:var(--text-color,#1f272e);
            }
            .${SUMMARY_CLASS} .dco-plan-settings-readonly__lead {
                display:none !important;
            }
            .${SUMMARY_CLASS} .dco-plan-settings-readonly__field {
                display:inline-flex !important;
                flex:0 0 auto !important;
                flex-direction:row !important;
                align-items:center !important;
                gap:4px !important;
                margin:0 !important;
                padding:0 !important;
                border:0 !important;
                background:transparent !important;
                min-width:0 !important;
            }
            .${SUMMARY_CLASS} .dco-plan-settings-readonly__field label {
                margin:0 !important;
                font-size:11px !important;
                font-weight:700 !important;
                color:var(--text-muted,#667085) !important;
                white-space:nowrap !important;
            }
            .${SUMMARY_CLASS} .dco-plan-settings-readonly__input-wrap {
                position:relative;
                flex:0 1 auto;
                min-width:0;
            }
            .${SUMMARY_CLASS} .dco-plan-settings-readonly__input-wrap .form-control {
                width:auto !important;
                min-width:3.25em !important;
                max-width:9.5em !important;
                min-height:28px !important;
                height:28px !important;
                padding:2px 8px !important;
                border:1px solid var(--border-color,#d0d5dd) !important;
                border-radius:var(--alm-radius-button,8px) !important;
                background:var(--alm-card,#fff) !important;
                box-shadow:none !important;
                font-size:11px !important;
                font-weight:700 !important;
                color:var(--text-color,#1f272e) !important;
                line-height:1.2 !important;
                cursor:default !important;
                pointer-events:none !important;
            }
            .${SUMMARY_CLASS} .dco-plan-settings-readonly__field[data-fieldtype="Select"] .form-control {
                min-width:7em !important;
                max-width:10.5em !important;
            }
            .${SUMMARY_CLASS} .dco-plan-settings-readonly__input-wrap.has-suffix .form-control {
                padding-inline-start:26px !important;
                padding-inline-end:8px !important;
            }
            .${SUMMARY_CLASS} .dco-plan-settings-readonly__suffix {
                position:absolute;
                inset-inline-start:8px;
                top:50%;
                transform:translateY(-50%);
                color:var(--text-muted,#667085);
                font-size:10px;
                font-weight:700;
                pointer-events:none;
            }
            @media (max-width:560px) {
                .${SUMMARY_CLASS} .dco-plan-settings-readonly__strip {
                    flex-wrap:wrap !important;
                    gap:6px !important;
                }
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

    function restorePlanToolbar(frm) {
        return true;
    }

    function attachPlanToolbar(frm, summary) {
        return true;
    }

    function removeOwnedSummary(frm) {
        restorePlanToolbar(frm);
        const summary = ownedSummary(frm);
        if (summary) summary.remove();
    }

    function summaryMarkup(frm, settings) {
        const fields = settingSpecs(frm, settings).map((spec) => {
            const label = frappe.utils.escape_html(__(spec.shortLabel || spec.label));
            const value = frappe.utils.escape_html(displayValue(spec, settings));
            const helpText = spec.fieldname === "optimization_time_limit_sec" ? TIME_LIMIT_HELP : spec.help;
            const help = helpText
                ? `<span class="dco-plan-settings-readonly__label-help" title="${frappe.utils.escape_html(__(helpText))}" aria-label="${frappe.utils.escape_html(__(helpText))}">?</span>`
                : "";
            const suffix = spec.suffix
                ? `<span class="dco-plan-settings-readonly__suffix">${frappe.utils.escape_html(__(spec.suffix))}</span>`
                : "";
            const wrapClass = spec.suffix
                ? "dco-plan-settings-readonly__input-wrap has-suffix"
                : "dco-plan-settings-readonly__input-wrap";
            const fieldname = frappe.utils.escape_html(spec.fieldname);
            return `
                <div class="dco-plan-settings-readonly__field" data-fieldname="${fieldname}" data-fieldtype="${frappe.utils.escape_html(spec.fieldtype || "Data")}">
                    <label for="dco-plan-settings-ro-${fieldname}">${label}${help}:</label>
                    <div class="${wrapClass}">
                        <input
                            id="dco-plan-settings-ro-${fieldname}"
                            class="form-control"
                            type="text"
                            value="${value}"
                            readonly
                            tabindex="-1"
                            aria-readonly="true"
                        >
                        ${suffix}
                    </div>
                </div>
            `;
        }).join("");
        return `
            <div class="dco-plan-settings-readonly__strip" role="group" aria-label="${frappe.utils.escape_html(__("إعدادات الخطة"))}">
                ${fields}
            </div>
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
        summary.innerHTML = summaryMarkup(frm, settings);
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
        attachPlanToolbar,
        restorePlanToolbar,
        render,
        schedule,
    });
})();
