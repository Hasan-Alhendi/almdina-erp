(() => {
    "use strict";

    if (window.AlmdinaPlanPreviewEditUX) return;

    const legacy = window.AlmdinaPlanEditSessionUX;
    if (!legacy) return;

    const SYNC_KEY = "__almdinaPlanPreviewEditSyncScheduled";
    const STYLE_ID = "almdina-plan-preview-edit-style";

    function previewOwner() {
        return window.AlmdinaPlanPreviewSession || null;
    }

    function workspaceState(frm) {
        const owner = window.AlmdinaPlanWorkspaceState;
        return owner && typeof owner.snapshot === "function" ? owner.snapshot(frm) : null;
    }

    function draftSettings(frm) {
        const state = workspaceState(frm);
        return state && state.editing && state.draft ? { ...state.draft } : null;
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        $("head").append(`
            <style id="${STYLE_ID}">
                .dco-plan-preview-banner {
                    display:flex;
                    align-items:flex-start;
                    justify-content:space-between;
                    gap:12px;
                    margin:0 0 12px;
                    padding:11px 13px;
                    border:1px solid rgba(36,144,239,.28);
                    border-radius:11px;
                    background:rgba(36,144,239,.065);
                    direction:rtl;
                }
                .dco-plan-preview-banner.is-stale {
                    border-color:rgba(217,119,6,.30);
                    background:rgba(245,158,11,.075);
                }
                .dco-plan-preview-banner.is-error {
                    border-color:rgba(220,38,38,.26);
                    background:rgba(239,68,68,.065);
                }
                .dco-plan-preview-banner strong { font-size:12px; }
                .dco-plan-preview-banner span {
                    display:block;
                    margin-top:3px;
                    color:var(--text-muted,#687481);
                    font-size:10.5px;
                    line-height:1.55;
                }
                .dco-plan-preview-badge {
                    flex:0 0 auto;
                    padding:4px 8px;
                    border-radius:999px;
                    background:var(--primary,#2490ef);
                    color:#fff;
                    font-size:10px;
                    font-weight:800;
                    white-space:nowrap;
                }
                .dco-plan-preview-banner.is-stale .dco-plan-preview-badge {
                    background:#b45309;
                }
                .dco-plan-preview-banner.is-error .dco-plan-preview-badge {
                    background:#b91c1c;
                }
                .dco-plan-preview-summary {
                    display:grid;
                    grid-template-columns:repeat(4,minmax(0,1fr));
                    gap:9px;
                    direction:rtl;
                }
                .dco-plan-preview-summary__item {
                    padding:10px 12px;
                    border:1px solid rgba(36,144,239,.18);
                    border-radius:11px;
                    background:rgba(36,144,239,.045);
                }
                .dco-plan-preview-summary__item span {
                    display:block;
                    color:var(--text-muted,#687481);
                    font-size:10px;
                    font-weight:700;
                }
                .dco-plan-preview-summary__item strong {
                    display:block;
                    margin-top:4px;
                    font-size:13px;
                    font-weight:850;
                }
                .dco-plan-preview-status {
                    padding:12px 14px;
                    border:1px dashed var(--border-color,#ccd3da);
                    border-radius:11px;
                    background:var(--subtle-fg,#fafafa);
                    direction:rtl;
                }
                .dco-plan-preview-status strong {
                    display:block;
                    font-size:12px;
                    font-weight:850;
                }
                .dco-plan-preview-status span {
                    display:block;
                    margin-top:4px;
                    color:var(--text-muted,#687481);
                    font-size:10.5px;
                    line-height:1.6;
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

    function actionWrapper(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.plan_control_actions;
        return field && field.$wrapper && field.$wrapper.length ? field.$wrapper : null;
    }

    function planToolbar(frm) {
        const root = frm && frm.wrapper;
        const node = root && (root.nodeType ? root : root[0]);
        return node && node.querySelector
            ? node.querySelector('.dco-tab-edit-toolbar[data-almdina-tab-edit-kind="plan"]')
            : null;
    }

    function editing(frm) {
        return Boolean(legacy.isEditing && legacy.isEditing(frm));
    }

    function previewSnapshot(frm) {
        const owner = previewOwner();
        return owner && typeof owner.snapshot === "function"
            ? owner.snapshot(frm)
            : { status: "idle", payload: null };
    }

    function canSaveEditing(frm) {
        const owner = previewOwner();
        return Boolean(editing(frm) && owner && owner.isReady(frm) && !owner.isBusy(frm));
    }

    function saveBlockedReason(frm) {
        const state = previewSnapshot(frm);
        if (state.status === "previewing") return "انتظر حتى تكتمل معاينة الخطة.";
        if (state.status === "saving") return "جاري حفظ الخطة المختارة.";
        if (state.status === "stale") return "تم تعديل الإعدادات. أعد الحساب لمعاينة الخطة الجديدة قبل الحفظ.";
        if (state.status === "error") return "تعذرت المعاينة السابقة. أعد الحساب ثم احفظ.";
        return "أعد الحساب بهذه الإعدادات أولًا، ثم احفظ الخطة التي تظهر أمامك.";
    }

    function syncSaveButton(frm) {
        const toolbar = planToolbar(frm);
        if (!toolbar || !editing(frm)) return;
        const button = toolbar.querySelector(".dco-tab-edit-save");
        if (!button) return;
        const allowed = canSaveEditing(frm);
        button.disabled = !allowed;
        button.setAttribute("aria-disabled", allowed ? "false" : "true");
        button.title = __(allowed
            ? "حفظ نفس خطة المعاينة المعروضة الآن"
            : saveBlockedReason(frm));
    }

    function bindPreviewButton(frm) {
        const wrapper = actionWrapper(frm);
        if (!wrapper) return;
        const button = wrapper.find(".dco-recalculate-plan").first();
        if (!button.length) return;

        const owner = previewOwner();
        const active = editing(frm);
        const busy = Boolean(owner && owner.isBusy(frm));
        const allowed = active && !busy && Boolean(draftSettings(frm));
        button.prop("disabled", !allowed).attr("aria-disabled", allowed ? "false" : "true");
        button.attr(
            "title",
            allowed
                ? __("معاينة مؤقتة فقط — لن يتم حفظ الخطة حتى تضغط «حفظ».")
                : active
                    ? __("انتظر حتى تكتمل العملية الحالية.")
                    : __("اضغط «تعديل» لبدء تجربة إعدادات وخوارزميات مختلفة.")
        );

        button.off("click");
        if (allowed) {
            button.on("click.almdinaPlanPreview", async (event) => {
                event.preventDefault();
                event.stopImmediatePropagation();
                const settings = draftSettings(frm);
                if (!settings || !owner) return;
                try {
                    const ok = await owner.preview(frm, settings);
                    if (ok) {
                        frappe.show_alert({
                            message: __("تم إنشاء معاينة جديدة. لم يتم حفظ أي تغيير بعد."),
                            indicator: "blue",
                        }, 4);
                    }
                } catch (error) {
                    console.error("Cutting plan preview failed", error);
                } finally {
                    schedule(frm);
                }
            });
        }
    }

    function bindDraftInvalidation(frm) {
        const wrapper = actionWrapper(frm);
        if (!wrapper) return;
        wrapper
            .off("input.almdinaPreviewInvalidation change.almdinaPreviewInvalidation")
            .on(
                "input.almdinaPreviewInvalidation change.almdinaPreviewInvalidation",
                "[data-almdina-plan-setting]",
                () => {
                    const owner = previewOwner();
                    const changed = Boolean(owner && owner.invalidate(frm));
                    if (changed) {
                        schedule(frm);
                        return;
                    }
                    // Once stale, later keystrokes do not require rebuilding the
                    // persisted plan canvas. Keep only action guidance in sync.
                    syncSaveButton(frm);
                    syncMessage(frm);
                }
            );
    }

    function renderPreviewSummary(frm, summary) {
        const field = frm && frm.fields_dict && frm.fields_dict.plan_controls_intro;
        const wrapper = field && field.$wrapper;
        if (!wrapper || !wrapper.length) return;
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
                <span>${frappe.utils.escape_html(__(label))}</span>
                <strong>${frappe.utils.escape_html(value)}</strong>
            </div>
        `).join("");
        wrapper.html(`<div class="dco-plan-preview-summary">${items}</div>`);
    }

    function previewStatusCopy(status) {
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

    function lockSourceTabs(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.cutting_plan_html;
        const wrapper = field && field.$wrapper;
        if (!wrapper || !wrapper.length) return;
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

    function renderPersistedEditingState(frm, status) {
        const tabs = window.AlmdinaPlanTabsUX;
        frm.__almdina_active_plan_tab = "System";
        if (tabs && typeof tabs.renderDualTabs === "function") tabs.renderDualTabs(frm);
        lockSourceTabs(frm);

        const field = frm.fields_dict && frm.fields_dict.cutting_plan_html;
        const wrapper = field && field.$wrapper;
        const content = wrapper && wrapper.find(".dco-plan-tab-content").first();
        const [title, description, badge] = previewStatusCopy(status);
        if (content && content.length) {
            const stateClass = status === "stale"
                ? " is-stale"
                : status === "error"
                    ? " is-error"
                    : "";
            content.prepend(`
                <div class="dco-plan-preview-banner${stateClass}">
                    <div>
                        <strong>${frappe.utils.escape_html(__(title))}</strong>
                        <span>${frappe.utils.escape_html(__(description))}</span>
                    </div>
                    <span class="dco-plan-preview-badge">${frappe.utils.escape_html(__(badge))}</span>
                </div>
            `);
        }

        const summaryField = frm.fields_dict && frm.fields_dict.plan_controls_intro;
        const summaryWrapper = summaryField && summaryField.$wrapper;
        if (summaryWrapper && summaryWrapper.length) {
            summaryWrapper.html(`
                <div class="dco-plan-preview-status">
                    <strong>${frappe.utils.escape_html(__(title))}</strong>
                    <span>${frappe.utils.escape_html(__(description))}</span>
                </div>
            `);
        }
        return true;
    }

    function renderPreviewPlan(frm) {
        const owner = previewOwner();
        const state = owner && typeof owner.snapshot === "function" ? owner.snapshot(frm) : null;
        const payload = state && state.payload;
        const plan = payload && payload.plan;
        const renderer = window.AlmdinaCuttingPlanRender;
        if (!plan || !Array.isArray(plan.sheets) || !plan.sheets.length || !renderer || !renderer.build) {
            return false;
        }

        const tabs = window.AlmdinaPlanTabsUX;
        frm.__almdina_active_plan_tab = "System";
        if (tabs && typeof tabs.renderDualTabs === "function") tabs.renderDualTabs(frm);

        const field = frm.fields_dict && frm.fields_dict.cutting_plan_html;
        const wrapper = field && field.$wrapper;
        if (!wrapper || !wrapper.length) return false;
        const content = wrapper.find(".dco-plan-tab-content").first();
        if (!content.length) return false;
        const saving = state.status === "saving";
        content.html(`
            <div class="dco-plan-preview-banner">
                <div>
                    <strong>${frappe.utils.escape_html(__(saving ? "جاري حفظ المعاينة المختارة" : "معاينة غير محفوظة"))}</strong>
                    <span>${frappe.utils.escape_html(__(saving
                        ? "يتم الآن تثبيت نفس الخطة التي تراها دون إعادة تشغيل الخوارزمية."
                        : "هذه هي الخطة التي سيتم حفظها حرفيًا عند الضغط على «حفظ». يمكنك تجربة خوارزمية أخرى قبل ذلك."))}</span>
                </div>
                <span class="dco-plan-preview-badge">${frappe.utils.escape_html(__(saving ? "حفظ" : "PREVIEW"))}</span>
            </div>
            ${renderer.build(frm, plan)}
        `);
        lockSourceTabs(frm);
        renderPreviewSummary(frm, payload.summary || {});
        return true;
    }

    function restorePersistedPresentation(frm) {
        const tabs = window.AlmdinaPlanTabsUX;
        if (editing(frm)) frm.__almdina_active_plan_tab = "System";
        if (tabs && typeof tabs.renderDualTabs === "function") tabs.renderDualTabs(frm);
        const planUx = window.AlmdinaDoorCuttingPlanUX;
        if (planUx && typeof planUx.refresh === "function") planUx.refresh(frm);
    }

    function syncMessage(frm) {
        const wrapper = actionWrapper(frm);
        if (!wrapper) return;
        const note = wrapper.find(".dco-plan-note").first();
        if (!note.length) return;
        if (!editing(frm)) {
            note.text(__("اضغط «تعديل» لتجربة إعدادات أو خوارزميات أخرى. لن تتغير الخطة المحفوظة أثناء التجربة."));
            return;
        }
        const state = previewSnapshot(frm);
        const messages = {
            idle: "عدّل الإعدادات كما تريد ثم اضغط «إعادة الحساب بالإعدادات الحالية» لمعاينة النتيجة. الحفظ لن يتفعل قبل المعاينة.",
            stale: "تم تعديل الإعدادات. أعد الحساب لمعاينة الخطة الجديدة قبل الحفظ.",
            previewing: "جاري حساب معاينة مؤقتة. لا يتم حفظ أي تغيير أثناء المعاينة.",
            ready: "المعاينة الحالية جاهزة للحفظ. يمكنك حفظها الآن أو تجربة خوارزمية أخرى.",
            saving: "جاري حفظ نفس الخطة التي تمت معاينتها.",
            error: "تعذرت المعاينة. عدّل الإعدادات عند الحاجة ثم أعد الحساب.",
        };
        note.text(__(messages[state.status] || messages.idle));
    }

    function sync(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        installStyles();
        bindDraftInvalidation(frm);
        bindPreviewButton(frm);
        syncSaveButton(frm);
        syncMessage(frm);

        const owner = previewOwner();
        if (!editing(frm) || !owner) return;
        const state = owner.snapshot(frm);
        if ((state.status === "ready" || state.status === "saving") && state.payload && state.payload.plan) {
            renderPreviewPlan(frm);
            return;
        }
        renderPersistedEditingState(frm, state.status);
    }

    function schedule(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order" || frm[SYNC_KEY]) return;
        frm[SYNC_KEY] = true;
        window.requestAnimationFrame(() => {
            frm[SYNC_KEY] = false;
            if (window.cur_frm === frm) sync(frm);
        });
    }

    async function startEditing(frm) {
        const owner = previewOwner();
        if (owner) owner.reset(frm);
        const result = await Promise.resolve(legacy.startEditing(frm));
        schedule(frm);
        return result;
    }

    async function cancelEditing(frm) {
        const owner = previewOwner();
        if (owner) owner.reset(frm);
        const result = await Promise.resolve(legacy.cancelEditing(frm));
        restorePersistedPresentation(frm);
        schedule(frm);
        return result;
    }

    async function saveEditing(frm) {
        const owner = previewOwner();
        if (!owner || !owner.isReady(frm)) {
            frappe.msgprint(__(saveBlockedReason(frm)));
            schedule(frm);
            return false;
        }
        try {
            await owner.commit(frm);
            if (legacy.isEditing(frm)) await Promise.resolve(legacy.cancelEditing(frm));

            const controls = window.AlmdinaPlanControlsUX;
            if (controls && typeof controls.refreshWorkspaceOwners === "function") {
                await controls.refreshWorkspaceOwners(frm);
            } else {
                const workspace = window.AlmdinaPlanWorkspaceState;
                if (workspace && typeof workspace.load === "function") {
                    await workspace.load(frm, { force: true });
                }
            }
            restorePersistedPresentation(frm);
            frappe.show_alert({
                message: __("تم حفظ نفس خطة المعاينة التي اخترتها."),
                indicator: "green",
            }, 5);
            schedule(frm);
            return true;
        } catch (error) {
            console.error("Cutting plan preview commit failed", error);
            schedule(frm);
            return false;
        }
    }

    window.AlmdinaPlanEditSessionUX = Object.freeze({
        ...legacy,
        startEditing,
        cancelEditing,
        saveEditing,
        canSaveEditing,
    });

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
        almdina_edit_session_changed(frm) { schedule(frm); },
        refresh_plan_controls(frm) { schedule(frm); },
    });

    [
        "almdina:plan-preview-updated",
        "almdina:plan-workspace-updated",
        "almdina:permissions-updated",
        "almdina:stage-context-ready",
    ].forEach((eventName) => {
        window.addEventListener(eventName, () => {
            const frm = window.cur_frm;
            if (frm && frm.doctype === "Door Cutting Order") schedule(frm);
        });
    });

    window.AlmdinaPlanPreviewEditUX = Object.freeze({
        canSaveEditing,
        renderPreviewPlan,
        renderPersistedEditingState,
        schedule,
        sync,
    });
})();
