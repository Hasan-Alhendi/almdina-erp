(() => {
    "use strict";

    if (window.AlmdinaPlanPreviewPresenter) return;

    const STYLE_ID = "almdina-plan-preview-style";
    const TRIM_REASON_LABELS = Object.freeze({
        preferred_retained: "تم الاحتفاظ بهامش التشذيب المطلوب",
        improved_feasibility: "تم تخفيض التشذيب لإتاحة توزيع جميع القطع",
        avoided_extra_board: "تم تخفيض التشذيب لتجنب لوح إضافي غير ضروري",
    });

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        $("head").append(`
            <style id="${STYLE_ID}">
                .dco-plan-preview-banner {
                    display:flex;align-items:flex-start;justify-content:space-between;gap:12px;
                    margin:0 0 12px;padding:11px 13px;border:1px solid rgba(36,144,239,.28);
                    border-radius:11px;background:rgba(36,144,239,.065);direction:rtl;
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
                    flex:0 0 auto;padding:4px 8px;border-radius:999px;background:var(--primary,#2490ef);
                    color:#fff;font-size:10px;font-weight:800;white-space:nowrap;
                }
                .dco-plan-preview-banner.is-stale .dco-plan-preview-badge { background:#b45309; }
                .dco-plan-preview-banner.is-error .dco-plan-preview-badge { background:#b91c1c; }
                .dco-plan-preview-summary {
                    display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:9px;direction:rtl;
                }
                .dco-plan-preview-summary__item {
                    padding:10px 12px;border:1px solid rgba(36,144,239,.18);
                    border-radius:11px;background:rgba(36,144,239,.045);
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
                .dco-plan-preview-summary__item.is-cost strong { color:#14653d;direction:ltr;text-align:right; }
                .dco-plan-preview-summary__item.is-adaptive strong { color:#8a4b08; }
                .dco-plan-preview-status {
                    padding:12px 14px;border:1px dashed var(--border-color,#ccd3da);
                    border-radius:11px;background:var(--subtle-fg,#fafafa);direction:rtl;
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

    function escape(value) {
        return frappe.utils.escape_html(__(String(value ?? "")));
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
        const wrapper = planWrapper(frm);
        if (!wrapper) return;
        wrapper.find("[data-plan-tab]").each((_, element) => {
            const tab = $(element);
            const isSystem = tab.attr("data-plan-tab") === "System";
            tab.prop("disabled", !isSystem);
            if (!isSystem) {
                tab.attr("title", __("احفظ أو ألغِ تعديل خطة القص قبل تغيير مصدر الخطة."));
            } else {
                tab.removeAttr("title");
            }
        });
    }

    function statusCopy(status) {
        const copy = {
            idle: [
                "جاهز للتجربة",
                "غيّر الإعدادات ثم اضغط «إعادة الحساب بالإعدادات الحالية». الخطة المحفوظة لم تتغير.",
                "تجربة",
            ],
            stale: [
                "المعاينة السابقة أصبحت قديمة",
                "غيّرت أحد الإعدادات بعد آخر معاينة. الخطة المعروضة أدناه هي الخطة المحفوظة؛ أعد الحساب لرؤية النتيجة الجديدة.",
                "أعد الحساب",
            ],
            previewing: [
                "جاري حساب المعاينة",
                "يتم تشغيل المحرك على الإعدادات الحالية دون حفظ أي تغيير.",
                "جاري الحساب",
            ],
            error: [
                "تعذرت المعاينة",
                "لم يتم حفظ أي تغيير. راجع الإعدادات ثم أعد الحساب.",
                "لم تُحفظ",
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
            ["الخوارزمية المطلوبة", String(requested.optimization_mode || "—"), "is-trace"],
            ["الاستراتيجية المستخدمة", String(optimizer.method_label || optimizer.method_key || "—"), "is-trace"],
            ["آلة القص", String(requested.machine_type || "—"), "is-trace"],
            ["Kerf المستخدم", `${numberText(requested.kerf_mm)} مم`, "is-trace"],
            ["Trim المطلوب", `${numberText(requested.preferred_trim_mm)} مم`, "is-trace"],
            [
                "Trim الفعلي",
                `عرض ${numberText(adaptive.applied_width_trim_mm)} مم / طول ${numberText(adaptive.applied_length_trim_mm)} مم`,
                adaptive.applied ? "is-adaptive" : "is-trace",
            ],
            ["المحاولات", numberText(optimizer.attempts, 0), "is-trace"],
            ["وقت الحساب", `${numberText(optimizer.elapsed_sec, 3)} ث`, "is-trace"],
        ];
        if (adaptive.reason) {
            items.push([
                "قرار التشذيب",
                TRIM_REASON_LABELS[adaptive.reason] || String(adaptive.reason),
                adaptive.applied ? "is-adaptive" : "is-trace",
            ]);
        }
        if (optimizer.solver_status) {
            items.push(["حالة Solver", String(optimizer.solver_status), "is-trace"]);
        }
        return items;
    }

    function renderPreviewSummary(frm, summary, plan) {
        const wrapper = summaryWrapper(frm);
        if (!wrapper) return;
        const totals = (summary && summary.totals) || {};
        const quality = (summary && summary.quality) || {};
        const items = [
            ["عدد الألواح", `${Number(totals.required_boards || 0)}`, ""],
            ["نسبة الهدر", `${Number(totals.waste_percent || 0).toFixed(2)}%`, ""],
            ["خطوط القص", `${Number(quality.estimated_cut_count || 0)}`, ""],
            ...executionItems(plan),
        ];
        const cost = summary && summary.cost;
        if (cost) {
            items.push(["تكلفة الخطة المتوقعة", `$ ${money(cost.total_cost_usd)}`, "is-cost"]);
        }
        const markup = items.map(([label, value, className]) => `
            <div class="dco-plan-preview-summary__item ${className}">
                <span>${escape(label)}</span>
                <strong>${frappe.utils.escape_html(String(value))}</strong>
            </div>
        `).join("");
        wrapper.html(`<div class="dco-plan-preview-summary">${markup}</div>`);
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
                <div class="dco-plan-preview-banner${stateClass}">
                    <div><strong>${escape(title)}</strong><span>${escape(description)}</span></div>
                    <span class="dco-plan-preview-badge">${escape(badge)}</span>
                </div>
            `);
        }

        const summary = summaryWrapper(frm);
        if (summary) {
            summary.html(`
                <div class="dco-plan-preview-status">
                    <strong>${escape(title)}</strong>
                    <span>${escape(description)}</span>
                </div>
            `);
        }
        return true;
    }

    function renderPreviewPlan(frm, previewState, committable) {
        installStyles();
        const payload = previewState && previewState.payload;
        const plan = payload && payload.plan;
        const renderer = window.AlmdinaCuttingPlanRender;
        if (!plan || !Array.isArray(plan.sheets) || !plan.sheets.length || !renderer || !renderer.build) {
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
            ? "جاري حفظ المعاينة المختارة"
            : invalid
                ? "معاينة غير صالحة للحفظ"
                : "معاينة غير محفوظة";
        const description = saving
            ? "يتم الآن تثبيت نفس الخطة التي تراها دون إعادة تشغيل الخوارزمية."
            : invalid
                ? "تم عرض النتيجة للمراجعة، لكنها لم تنجح في التحقق الهندسي. جرّب إعدادات أخرى قبل الحفظ."
                : hasCost
                    ? "هذه الخطة وتكلفتها المعروضة للمعاينة فقط. ستصبحان رسميتين معًا عند الضغط على «حفظ»."
                    : "هذه الخطة للمعاينة فقط. ستصبح الخطة الجديدة رسمية عند الضغط على «حفظ».";
        const stateClass = invalid ? " is-error" : "";
        const badge = saving ? "حفظ" : invalid ? "غير صالحة" : "PREVIEW";

        content.html(`
            <div class="dco-plan-preview-banner${stateClass}">
                <div><strong>${escape(title)}</strong><span>${escape(description)}</span></div>
                <span class="dco-plan-preview-badge">${escape(badge)}</span>
            </div>
            ${renderer.build(frm, plan)}
        `);
        lockSourceTabs(frm);
        renderPreviewSummary(frm, payload.summary || {}, plan);
        return true;
    }

    function renderActionMessage(frm, editing, status, committable) {
        const wrapper = actionWrapper(frm);
        const note = wrapper && wrapper.find(".dco-plan-note").first();
        if (!note || !note.length) return;
        if (!editing) {
            note.text(__("اضغط «تعديل» لتجربة إعدادات أو خوارزميات أخرى. لن تتغير الخطة المحفوظة أثناء التجربة."));
            return;
        }
        const hasCost = previewCostVisible(frm);
        const messages = {
            idle: "عدّل الإعدادات كما تريد ثم اضغط «إعادة الحساب بالإعدادات الحالية» لمعاينة النتيجة. الحفظ لن يتفعل قبل المعاينة.",
            stale: "تم تعديل الإعدادات. أعد الحساب لمعاينة الخطة الجديدة قبل الحفظ.",
            previewing: "جاري حساب معاينة مؤقتة. لا يتم حفظ أي تغيير أثناء المعاينة.",
            saving: hasCost
                ? "جاري حفظ نفس الخطة والتكلفة التي تمت معاينتها."
                : "جاري حفظ نفس الخطة التي تمت معاينتها.",
            error: "تعذرت المعاينة. عدّل الإعدادات عند الحاجة ثم أعد الحساب.",
        };
        if (status === "ready") {
            note.text(__(committable
                ? hasCost
                    ? "المعاينة الحالية جاهزة للحفظ. التكلفة الظاهرة تقديرية لهذه الخطة، وتصبح رسمية عند الحفظ."
                    : "المعاينة الحالية جاهزة للحفظ. اضغط «حفظ» لاعتماد نفس الخطة المعروضة."
                : "تم عرض المعاينة لكنها غير صالحة للحفظ. جرّب إعدادات أخرى ثم أعد الحساب."));
            return;
        }
        note.text(__(messages[status] || messages.idle));
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