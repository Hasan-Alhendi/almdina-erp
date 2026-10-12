(() => {
    "use strict";

    if (window.AlmdinaPlanPreviewPresenter) return;

    const STYLE_ID = "almdina-plan-preview-style";
    const TRIM_REASON_LABELS = Object.freeze({
        preferred_retained: "The requested trim margin was kept",
        improved_feasibility: "Trim was reduced so every piece could be placed",
        avoided_extra_board: "Trim was reduced to avoid an unnecessary extra board",
    });
    const SETTING_MESSAGE_IDS = Object.freeze({
        optimization_mode: Object.freeze({
            auto: "Automatic",
            auto_pro: "Auto Pro (recommended)",
            deep_search: "Deep Search",
            optimal: "Optimal Search",
            maxrects: "MaxRects",
            guillotine: "Guillotine",
            shelf: "Shelf packing",
            skyline: "Skyline",
            cp_sat_ortools: "Constraint programming — CP-SAT",
            mip_cbc: "Mixed-integer programming — CBC",
            scip: "SCIP solver",
            highs: "HiGHS solver",
            gecode: "Gecode constraint solver",
            chuffed: "Chuffed constraint solver",
            genetic: "Genetic algorithm",
            simulated_annealing: "Simulated annealing",
        }),
        machine_type: Object.freeze({
            Auto: "Automatic",
            "CNC Router": "CNC Router",
            "Panel Saw": "Panel Saw",
        }),
    });

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        $("head").append(`
            <style id="${STYLE_ID}">
                .dco-plan-preview-banner {
                    display:flex;align-items:flex-start;justify-content:space-between;gap:12px;
                    margin:0 0 12px;padding:11px 13px;border:1px solid color-mix(in srgb, var(--alm-primary, #172033) 28%, transparent);
                    border-radius:11px;background:color-mix(in srgb, var(--alm-primary, #172033) 6%, transparent);
                }
                .dco-plan-preview-banner.is-stale {
                    border-color:rgba(217,119,6,.30);background:rgba(245,158,11,.075);
                }
                .dco-plan-preview-banner.is-error {
                    border-color:rgba(220,38,38,.26);background:rgba(239,68,68,.065);
                }
                .dco-plan-preview-banner strong { font-size:12px; }
                .dco-plan-preview-banner span {
                    display:block;margin-top:3px;color:var(--text-muted,#687481);
                    font-size:10.5px;line-height:1.55;
                }
                .dco-plan-preview-badge {
                    flex:0 0 auto;padding:4px 8px;border-radius:999px;background:var(--alm-primary,#172033);
                    color:#fff !important;font-size:10px;font-weight:800;white-space:nowrap;
                }
                .dco-plan-preview-banner .dco-plan-preview-badge {
                    display:inline-flex;align-items:center;margin-top:0;color:#fff !important;
                }
                .dco-plan-preview-banner.is-stale .dco-plan-preview-badge { background:#b45309; }
                .dco-plan-preview-banner.is-error .dco-plan-preview-badge { background:#b91c1c; }
                .dco-plan-preview-summary {
                    display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:9px;
                }
                .dco-plan-preview-summary__item {
                    padding:10px 12px;border:1px solid color-mix(in srgb, var(--alm-primary, #172033) 18%, transparent);
                    border-radius:11px;background:color-mix(in srgb, var(--alm-primary, #172033) 4%, transparent);
                }
                .dco-plan-preview-summary__item.is-cost {
                    border-color:rgba(31,130,82,.24);background:rgba(31,130,82,.055);
                }
                .dco-plan-preview-summary__item.is-trace {
                    border-color:rgba(82,82,91,.18);background:rgba(82,82,91,.035);
                }
                .dco-plan-preview-summary__item.is-adaptive {
                    border-color:rgba(217,119,6,.24);background:rgba(245,158,11,.06);
                }
                .dco-plan-preview-summary__item span {
                    display:block;color:var(--text-muted,#687481);font-size:10px;font-weight:700;
                }
                .dco-plan-preview-summary__item strong {
                    display:block;margin-top:4px;font-size:13px;font-weight:850;
                }
                .dco-plan-preview-summary__item.is-cost strong { color:#14653d;direction:ltr;text-align:start; }
                .dco-plan-preview-summary__item.is-adaptive strong { color:#8a4b08; }
                .dco-plan-preview-status {
                    padding:12px 14px;border:1px dashed var(--border-color,#ccd3da);
                    border-radius:11px;background:var(--subtle-fg,#fafafa);
                }
                .dco-plan-preview-status strong { display:block;font-size:12px;font-weight:850; }
                .dco-plan-preview-status span {
                    display:block;margin-top:4px;color:var(--text-muted,#687481);
                    font-size:10.5px;line-height:1.6;
                }
                @media (max-width:480px) {
                    .dco-plan-preview-banner { display:block; }
                    .dco-plan-preview-badge { display:inline-flex;margin-top:8px; }
                    .dco-plan-preview-summary { grid-template-columns:1fr; }
                }
            </style>
        `);
    }

    function translate(message, replacements) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") {
            return locale.translate(message, replacements);
        }
        if (typeof __ === "function") {
            return replacements === undefined ? __(message) : __(message, replacements);
        }
        return String(message == null ? "" : message);
    }

    function uiDirection() {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.direction === "function") {
            const value = locale.direction();
            if (value === "ltr" || value === "rtl") return value;
        }
        const dir = document.documentElement && document.documentElement.getAttribute("dir");
        return dir === "ltr" ? "ltr" : "rtl";
    }

    function escapeHtml(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function htmlMessage(message, replacements) {
        return escapeHtml(translate(message, replacements));
    }

    function knownSettingText(kind, value) {
        const raw = String(value || "").trim();
        if (!raw) return "—";
        const catalog = SETTING_MESSAGE_IDS[kind] || {};
        return catalog[raw] ? translate(catalog[raw]) : raw;
    }

    function money(value) {
        const numeric = Number(value || 0);
        return numeric.toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    function numberText(value, decimals = 2) {
        const numeric = Number(value);
        if (!Number.isFinite(numeric)) return "—";
        return numeric.toLocaleString("en-US", {
            maximumFractionDigits: decimals,
        });
    }

    function hasTraceValue(value) {
        return value !== null && value !== undefined && value !== "";
    }

    function actionWrapper(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.plan_control_actions;
        return field && field.$wrapper && field.$wrapper.length ? field.$wrapper : null;
    }

    function planWrapper(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.cutting_plan_html;
        const wrapper = field && field.$wrapper;
        return wrapper && wrapper.length ? wrapper : null;
    }

    function summaryWrapper(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.plan_controls_intro;
        const wrapper = field && field.$wrapper;
        return wrapper && wrapper.length ? wrapper : null;
    }

    function currentPreviewSummary(frm) {
        const owner = window.AlmdinaPlanPreviewSession;
        const state = owner && typeof owner.snapshot === "function"
            ? owner.snapshot(frm)
            : null;
        return state && state.payload && state.payload.summary
            ? state.payload.summary
            : null;
    }

    function previewCostVisible(frm) {
        return Boolean(currentPreviewSummary(frm) && currentPreviewSummary(frm).cost);
    }

    function lockSourceTabs(frm) {
        const tabs = window.AlmdinaPlanTabsUX;
        if (tabs && typeof tabs.lockSourceTabs === "function") {
            tabs.lockSourceTabs(frm);
            return;
        }
        const wrapper = planWrapper(frm);
        if (!wrapper) return;
        wrapper.find("[data-plan-tab]").each((_, element) => {
            const tab = $(element);
            const isSystem = tab.attr("data-plan-tab") === "System";
            tab.prop("disabled", !isSystem);
            if (!isSystem) {
                tab.attr("title", translate("Save or cancel the cutting plan edit before changing the plan source."));
            } else {
                tab.removeAttr("title");
            }
        });
    }

    function statusCopy(status) {
        const copy = {
            idle: [
                "Ready to try",
                "Change the settings, then press “Recalculate with the current settings”. The saved plan has not changed.",
                "Trial",
            ],
            stale: [
                "The previous preview is out of date",
                "You changed a setting after the last preview. The plan shown below is the saved plan; recalculate to see the new result.",
                "Recalculate",
            ],
            previewing: [
                "Calculating the preview",
                "The engine is running on the current settings without saving any change.",
                "Calculating",
            ],
            error: [
                "The preview failed",
                "Nothing was saved. Review the settings, then recalculate.",
                "Not saved",
            ],
        };
        return copy[status] || copy.idle;
    }

    function executionItems(plan) {
        const trace = plan && plan.execution_trace;
        if (!trace || Number(trace.version || 0) < 1) return [];
        const requested = trace.requested || {};
        const adaptive = trace.adaptive_trim || {};
        const optimizer = trace.optimizer || {};
        const items = [
            ["Requested algorithm", knownSettingText("optimization_mode", requested.optimization_mode), "is-trace"],
            ["Strategy used", String(optimizer.method_label || optimizer.method_key || "—"), "is-trace"],
            ["Cutting machine", knownSettingText("machine_type", requested.machine_type), "is-trace"],
            ["Kerf used", translate("{0} mm", [numberText(requested.kerf_mm)]), "is-trace"],
            ["Requested trim", translate("{0} mm", [numberText(requested.preferred_trim_mm)]), "is-trace"],
            [
                "Applied trim",
                translate("Width {0} mm / length {1} mm", [
                    numberText(adaptive.applied_width_trim_mm),
                    numberText(adaptive.applied_length_trim_mm),
                ]),
                adaptive.applied ? "is-adaptive" : "is-trace",
            ],
        ];
        if (hasTraceValue(optimizer.attempts)) {
            items.push(["Attempts", numberText(optimizer.attempts, 0), "is-trace"]);
        }
        if (hasTraceValue(optimizer.elapsed_sec)) {
            items.push(["Calculation time", translate("{0} s", [numberText(optimizer.elapsed_sec, 3)]), "is-trace"]);
        }
        if (adaptive.reason) {
            const reasonId = TRIM_REASON_LABELS[adaptive.reason];
            items.push([
                "Trim decision",
                reasonId ? translate(reasonId) : String(adaptive.reason),
                adaptive.applied ? "is-adaptive" : "is-trace",
            ]);
        }
        if (optimizer.solver_status) {
            items.push(["Solver status", String(optimizer.solver_status), "is-trace"]);
        }
        return items;
    }

    function renderPreviewSummary(frm, summary, plan) {
        const wrapper = summaryWrapper(frm);
        if (!wrapper) return;
        const totals = (summary && summary.totals) || {};
        const quality = (summary && summary.quality) || {};
        const items = [
            ["Board count", `${Number(totals.required_boards || 0)}`, ""],
            ["Waste percent", `${Number(totals.waste_percent || 0).toFixed(2)}%`, ""],
            ["Cut lines", `${Number(quality.estimated_cut_count || 0)}`, ""],
            ...executionItems(plan),
        ];
        const cost = summary && summary.cost;
        if (cost) {
            items.push(["Expected plan cost", `$ ${money(cost.total_cost_usd)}`, "is-cost"]);
        }
        const markup = items.map(([label, value, className]) => `
            <div class="dco-plan-preview-summary__item ${className}">
                <span>${htmlMessage(label)}</span>
                <strong>${frappe.utils.escape_html(String(value))}</strong>
            </div>
        `).join("");
        wrapper.html(`<div class="dco-plan-preview-summary" dir="${escapeHtml(uiDirection())}">${markup}</div>`);
    }

    function renderPersistedEditingState(frm, status) {
        installStyles();
        const tabs = window.AlmdinaPlanTabsUX;
        frm.__almdina_active_plan_tab = "System";
        if (tabs && typeof tabs.renderDualTabs === "function") tabs.renderDualTabs(frm);
        lockSourceTabs(frm);

        const wrapper = planWrapper(frm);
        const content = wrapper && wrapper.find(".dco-plan-tab-content").first();
        const [title, description, badge] = statusCopy(status);
        if (content && content.length) {
            const stateClass = status === "stale"
                ? " is-stale"
                : status === "error"
                    ? " is-error"
                    : "";
            content.prepend(`
                <div class="dco-plan-preview-banner${stateClass}" dir="${escapeHtml(uiDirection())}">
                    <div><strong>${htmlMessage(title)}</strong><span>${htmlMessage(description)}</span></div>
                    <span class="dco-plan-preview-badge">${htmlMessage(badge)}</span>
                </div>
            `);
        }

        const summary = summaryWrapper(frm);
        if (summary) {
            summary.html(`
                <div class="dco-plan-preview-status" dir="${escapeHtml(uiDirection())}">
                    <strong>${htmlMessage(title)}</strong>
                    <span>${htmlMessage(description)}</span>
                </div>
            `);
        }
        return true;
    }

    function renderPreviewPlan(frm, previewState, committable) {
        installStyles();
        const payload = previewState && previewState.payload;
        const plan = payload && payload.plan;
        if (!plan || !Array.isArray(plan.sheets) || !plan.sheets.length) {
            return false;
        }

        const tabs = window.AlmdinaPlanTabsUX;
        frm.__almdina_active_plan_tab = "System";
        if (tabs && typeof tabs.renderDualTabs === "function") tabs.renderDualTabs(frm);

        const wrapper = planWrapper(frm);
        const content = wrapper && wrapper.find(".dco-plan-tab-content").first();
        if (!content || !content.length) return false;

        const saving = previewState.status === "saving";
        const invalid = !saving && !committable;
        const hasCost = Boolean(payload.summary && payload.summary.cost);
        const title = saving
            ? "Saving the selected preview"
            : invalid
                ? "Preview cannot be saved"
                : "Unsaved preview";
        const description = saving
            ? "The same plan you see is being saved without running the algorithm again."
            : invalid
                ? "The result is shown for review, but it did not pass the engineering check. Try other settings before saving."
                : hasCost
                    ? "This plan and its cost are only a preview. They both become official when you press “Save”."
                    : "This plan is only a preview. The new plan becomes official when you press “Save”.";
        const stateClass = invalid ? " is-error" : "";
        const badge = saving ? "Save" : invalid ? "Not valid" : "PREVIEW";

        // Tabs render the displayed plan through the workspace owner. This
        // presenter owns only the transient status and summary around it.
        content.prepend(`
            <div class="dco-plan-preview-banner${stateClass}" dir="${escapeHtml(uiDirection())}">
                <div><strong>${htmlMessage(title)}</strong><span>${htmlMessage(description)}</span></div>
                <span class="dco-plan-preview-badge">${htmlMessage(badge)}</span>
            </div>
        `);
        lockSourceTabs(frm);
        const decorations = window.AlmdinaPlanContentUX;
        if (decorations && typeof decorations.apply === "function") decorations.apply(frm);
        renderPreviewSummary(frm, payload.summary || {}, plan);
        return true;
    }

    function renderActionMessage(frm, editing, status, committable) {
        const wrapper = actionWrapper(frm);
        const note = wrapper && wrapper.find(".dco-plan-note").first();
        if (!note || !note.length) return;
        note.attr("dir", uiDirection());
        if (!editing) {
            note.text(translate("Press “Edit” to try other settings or algorithms. The saved plan will not change while you are trying them."));
            return;
        }
        const hasCost = previewCostVisible(frm);
        const messages = {
            idle: "Change the settings as you like, then press “Recalculate with the current settings” to preview the result. Saving stays unavailable until you preview.",
            stale: "The settings were changed. Recalculate to preview the new plan before saving.",
            previewing: "A temporary preview is being calculated. Nothing is saved during the preview.",
            saving: hasCost
                ? "Saving the same plan and cost that were previewed."
                : "Saving the same plan that was previewed.",
            error: "The preview failed. Adjust the settings if needed, then recalculate.",
        };
        if (status === "ready") {
            note.text(translate(committable
                ? hasCost
                    ? "The current preview is ready to save. The cost shown is an estimate for this plan and becomes official when you save."
                    : "The current preview is ready to save. Press “Save” to adopt the same plan shown."
                : "The preview was shown but cannot be saved. Try other settings, then recalculate."));
            return;
        }
        note.text(translate(messages[status] || messages.idle));
    }

    function restorePersistedPresentation(frm) {
        const tabs = window.AlmdinaPlanTabsUX;
        if (tabs && typeof tabs.renderDualTabs === "function") tabs.renderDualTabs(frm);
        const planUx = window.AlmdinaDoorCuttingPlanUX;
        if (planUx && typeof planUx.refresh === "function") planUx.refresh(frm);
    }

    window.AlmdinaPlanPreviewPresenter = Object.freeze({
        renderActionMessage,
        renderPersistedEditingState,
        renderPreviewPlan,
        restorePersistedPresentation,
    });
})();
