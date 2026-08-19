(() => {
    "use strict";

    if (window.AlmdinaPlanPreviewPresenter) return;

    const STYLE_ID = "almdina-plan-preview-style";

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
                    display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px;direction:rtl;
                }
                .dco-plan-preview-summary__item {
                    padding:10px 12px;border:1px solid rgba(36,144,239,.18);
                    border-radius:11px;background:rgba(36,144,239,.045);
                }
                .dco-plan-preview-summary__item span {
                    display:block;color:var(--text-muted,#687481);font-size:10px;font-weight:700;
                }
                .dco-plan-preview-summary__item strong {
                    display:block;margin-top:4px;font-size:13px;font-weight:850;
                }
                .dco-plan-preview-status {
                    padding:12px 14px;border:1px dashed var(--border-color,#ccd3da);
                    border-radius:11px;background:var(--subtle-fg,#fafafa);direction:rtl;
                }
                .dco-plan-preview-status strong { display:block;font-size:12px;font-weight:850; }
                .dco-plan-preview-status span {
                    display:block;margin-top:4px;color:var(--text-muted,#687481);
                    font-size:10.5px;line-height:1.6;
                }
                @media (max-width:700px) {
                    .dco-plan-preview-summary { grid-template-columns:repeat(2,minmax(0,1fr)); }
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

    function renderPreviewSummary(frm, summary) {
        const wrapper = summaryWrapper(frm);
        if (!wrapper) return;
        const totals = (summary && summary.totals) || {};
        const engine = (summary && summary.engine) || {};
        const quality = (summary && summary.quality) || {};
        const items = [
            ["عدد الألواح", `${Number(totals.required_boards || 0)}`],
            ["نسبة الهدر", `${Number(totals.waste_percent || 0).toFixed(2)}%`],
            ["الخوارزمية الفعلية", String(engine.method_label || engine.method_key || "—")],
            ["خطوط القص", `${Number(quality.estimated_cut_count || 0)}`],
        ].map(([label, value]) => `
            <div class="dco-plan-preview-summary__item">
                <span>${escape(label)}</span>
                <strong>${frappe.utils.escape_html(value)}</strong>
            </div>
        `).join("");
        wrapper.html(`<div class="dco-plan-preview-summary">${items}</div>`);
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
        const title = saving
            ? "جاري حفظ المعاينة المختارة"
            : invalid
                ? "معاينة غير صالحة للحفظ"
                : "معاينة غير محفوظة";
        const description = saving
            ? "يتم الآن تثبيت نفس الخطة التي تراها دون إعادة تشغيل الخوارزمية."
            : invalid
                ? "تم عرض النتيجة للمراجعة، لكنها لم تنجح في التحقق الهندسي. جرّب إعدادات أخرى قبل الحفظ."
                : "هذه هي الخطة التي سيتم حفظها حرفيًا عند الضغط على «حفظ». يمكنك تجربة خوارزمية أخرى قبل ذلك.";
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
        renderPreviewSummary(frm, payload.summary || {});
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
        const messages = {
            idle: "عدّل الإعدادات كما تريد ثم اضغط «إعادة الحساب بالإعدادات الحالية» لمعاينة النتيجة. الحفظ لن يتفعل قبل المعاينة.",
            stale: "تم تعديل الإعدادات. أعد الحساب لمعاينة الخطة الجديدة قبل الحفظ.",
            previewing: "جاري حساب معاينة مؤقتة. لا يتم حفظ أي تغيير أثناء المعاينة.",
            saving: "جاري حفظ نفس الخطة التي تمت معاينتها.",
            error: "تعذرت المعاينة. عدّل الإعدادات عند الحاجة ثم أعد الحساب.",
        };
        if (status === "ready") {
            note.text(__(committable
                ? "المعاينة الحالية جاهزة للحفظ. يمكنك حفظها الآن أو تجربة خوارزمية أخرى."
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
