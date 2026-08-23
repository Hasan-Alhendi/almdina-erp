(() => {
    "use strict";

    if (window.AlmdinaPlanEditSessionUX) return;

    const PLAN_SETTING_FIELDS = Object.freeze([
        "packing_mode",
        "cutting_machine_type",
        "kerf_mm",
        "trim_margin_mm",
        "optimization_time_limit_sec",
    ]);
    const PLAN_SETTING_SPECS = Object.freeze([
        Object.freeze({
            fieldname: "kerf_mm",
            label: "سماكة شفرة القص (Kerf)",
            fieldtype: "Float",
            min: 0,
            step: "0.1",
            suffix: "مم",
        }),
        Object.freeze({
            fieldname: "trim_margin_mm",
            label: "هامش تشذيب اللوح",
            fieldtype: "Float",
            min: 0,
            step: "0.1",
            suffix: "مم",
        }),
        Object.freeze({
            fieldname: "packing_mode",
            label: "خوارزمية توزيع القطع",
            fieldtype: "Select",
            options: Object.freeze([
                Object.freeze({ value: "Auto", label: "تلقائي" }),
                Object.freeze({ value: "Auto Pro", label: "تلقائي متقدم (موصى به)" }),
                Object.freeze({ value: "Deep Search", label: "بحث معمق" }),
                Object.freeze({ value: "Optimal Search", label: "بحث أمثل" }),
                Object.freeze({ value: "MaxRects Best Short Side", label: "MaxRects Best Short Side" }),
                Object.freeze({ value: "MaxRects Best Area", label: "MaxRects Best Area" }),
                Object.freeze({ value: "MaxRects Bottom Left", label: "MaxRects Bottom Left" }),
                Object.freeze({ value: "MaxRects Contact Point", label: "MaxRects Contact Point" }),
                Object.freeze({ value: "MaxRects Width", label: "MaxRects Width" }),
                Object.freeze({ value: "MaxRects Length", label: "MaxRects Length" }),
                Object.freeze({ value: "Shelf Horizontal", label: "Shelf Horizontal" }),
                Object.freeze({ value: "Shelf Vertical", label: "Shelf Vertical" }),
                Object.freeze({ value: "Shelf First Fit", label: "Shelf First Fit" }),
                Object.freeze({ value: "Shelf Next Fit", label: "Shelf Next Fit" }),
                Object.freeze({ value: "Guillotine Short Axis", label: "Guillotine Short Axis" }),
                Object.freeze({ value: "Guillotine Long Axis", label: "Guillotine Long Axis" }),
                Object.freeze({ value: "Guillotine Best Area Fit", label: "Guillotine Best Area Fit" }),
                Object.freeze({ value: "Guillotine Best Short Side Fit", label: "Guillotine Best Short Side Fit" }),
                Object.freeze({ value: "Guillotine Best Long Side Fit", label: "Guillotine Best Long Side Fit" }),
                Object.freeze({ value: "Skyline Bottom Left", label: "Skyline Bottom Left" }),
                Object.freeze({ value: "Skyline Best Fit", label: "Skyline Best Fit" }),
            ]),
        }),
        Object.freeze({
            fieldname: "cutting_machine_type",
            label: "نوع آلة القص",
            fieldtype: "Select",
            options: Object.freeze([
                Object.freeze({ value: "Auto", label: "تلقائي" }),
                Object.freeze({ value: "CNC Router", label: "CNC Router" }),
                Object.freeze({ value: "Panel Saw", label: "منشار ألواح" }),
            ]),
        }),
        Object.freeze({
            fieldname: "optimization_time_limit_sec",
            label: "مهلة التحسين",
            fieldtype: "Float",
            min: 0,
            step: "1",
            suffix: "ثانية",
        }),
    ]);
    const DRAFT_LIKE = new Set(["Draft", "Pending Review", "Rejected"]);
    const ACTIVE_ROUTED_STATUSES = new Set([
        "At Sharyoun",
        "At Drawing",
        "At CNC",
        "At Sanding",
    ]);
    const BLOCKED_PLAN_ACTIONS = [
        // Preview/recalculation remains active while editing; all operations that
        // depend on a persisted plan stay suspended until Save/Cancel.
        ".dco-approve-cutting-plan",
        ".dco-print-cutting-plan",
        ".dco-export-dxf",
        ".dco-upload-dxf-plan",
    ].join(",");
    const ORIGINAL_DISABLED_ATTR = "data-almdina-plan-edit-original-disabled";
    const EDITOR_SELECTOR = ".dco-plan-settings-editor";
    const STYLE_ID = "almdina-plan-settings-editor-style";

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function stateOwner() {
        return window.AlmdinaPlanWorkspaceState || null;
    }

    function storeFor(frm) {
        const owner = stateOwner();
        return owner && typeof owner.storeFor === "function" ? owner.storeFor(frm) : null;
    }

    function workspaceSnapshot(frm) {
        const store = storeFor(frm);
        return store ? store.snapshot() : null;
    }

    function approvedPlanName(frm) {
        const state = workspaceSnapshot(frm);
        if (!state || state.status !== "ready" || !state.data) return null;
        return String(state.data.approved_plan || "").trim();
    }

    function presenterAdapter() {
        return window.AlmdinaPlanWorkspacePresenterAdapter || null;
    }

    function can(frm, capability) {
        const permissions = window.AlmdinaPermissions;
        if (!permissions) return false;
        if (frm && typeof permissions.canDocument === "function") {
            return Boolean(permissions.canDocument(frm, capability));
        }
        return typeof permissions.can === "function" && Boolean(permissions.can(capability));
    }

    function hasActiveProductionStage(frm) {
        return Boolean(String(
            (frm && frm.doc && frm.doc.current_production_stage) || ""
        ).trim());
    }

    function hasProductionRoute(frm) {
        return Boolean(
            hasActiveProductionStage(frm)
            || String((frm && frm.doc && frm.doc.production_path) || "").trim()
        );
    }

    function hasActiveRoutedLifecycle(frm) {
        if (hasActiveProductionStage(frm)) return true;
        const status = String((frm && frm.doc && frm.doc.status) || "").trim();
        return ACTIVE_ROUTED_STATUSES.has(status);
    }

    function isDrawingStage(frm) {
        if (!frm || !frm.doc) return false;
        const status = String(frm.doc.status || "").trim();
        const stageType = String(
            frm.__almdina_stage_type
            || (frm.__almdina_stage_context && frm.__almdina_stage_context.active_stage_type)
            || ""
        ).trim();
        return status === "At Drawing" || stageType === "Drawing";
    }

    function lifecycleAllowsEdit(frm) {
        if (!frm || !frm.doc || frm.doctype !== "Door Cutting Order") return false;
        if (frm.is_new && frm.is_new()) return false;
        if (Number(frm.doc.docstatus || 0) !== 0) return false;
        if ((frm.doc.revision_state || "Current") === "Superseded") return false;

        const approved = approvedPlanName(frm);
        if (approved === null) return false;
        if (approved && !isDrawingStage(frm)) return false;

        if (hasProductionRoute(frm)) return hasActiveRoutedLifecycle(frm);
        return DRAFT_LIKE.has(frm.doc.status || "Draft");
    }

    function canEditPlanSettings(frm) {
        return Boolean(can(frm, "edit_optimizer_settings") && lifecycleAllowsEdit(frm));
    }

    function isEditing(frm) {
        const state = workspaceSnapshot(frm);
        return Boolean(state && state.editing);
    }

    function planSettingsMayWrite() {
        // Plan settings are edited only through the canonical Cutting Plan workspace.
        // Retired DCO plan fields must never be restored as mutable controls.
        return false;
    }

    function activeSettings(frm) {
        const adapter = presenterAdapter();
        if (adapter && typeof adapter.activeSettings === "function") {
            return adapter.activeSettings(frm);
        }
        const owner = stateOwner();
        const active = owner && typeof owner.activePlan === "function"
            ? owner.activePlan(frm, "System")
            : null;
        return active && active.settings ? { ...active.settings } : null;
    }

    function signalEditChanged(frm) {
        if (frm && typeof frm.trigger === "function") {
            frm.trigger("almdina_edit_session_changed");
        }
    }

    function refreshFieldAccess(frm) {
        const adapter = window.AlmdinaPlanFieldAccessAdapter;
        if (adapter && typeof adapter.apply === "function") adapter.apply(frm);
    }

    function actionSurface(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.plan_control_actions;
        const wrapper = field && field.$wrapper;
        return wrapper && wrapper.length ? wrapper : null;
    }

    function setPlanActionsSuspended(frm, suspended) {
        const wrapper = actionSurface(frm);
        if (!wrapper) return;
        wrapper.find(BLOCKED_PLAN_ACTIONS).each((_, element) => {
            const button = $(element);
            if (suspended) {
                if (button.attr(ORIGINAL_DISABLED_ATTR) === undefined) {
                    button.attr(ORIGINAL_DISABLED_ATTR, button.prop("disabled") ? "1" : "0");
                }
                button.prop("disabled", true).attr("aria-disabled", "true");
                return;
            }
            const original = button.attr(ORIGINAL_DISABLED_ATTR);
            if (original === undefined) return;
            button.prop("disabled", original === "1");
            button.attr("aria-disabled", original === "1" ? "true" : "false");
            button.removeAttr(ORIGINAL_DISABLED_ATTR);
        });
    }

    function translate(value) {
        const text = String(value ?? "");
        return typeof __ === "function" ? __(text) : text;
    }

    function escapeHtml(value) {
        if (frappe.utils && typeof frappe.utils.escape_html === "function") {
            return frappe.utils.escape_html(String(value ?? ""));
        }
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function installEditorStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-plan-settings-editor {
                margin: 0 0 14px;
                padding: 14px;
                border: 1px solid var(--border-color, #d1d8dd);
                border-radius: 12px;
                background: var(--card-bg, #fff);
                direction: rtl;
            }
            .dco-plan-settings-editor__header {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: 12px;
                margin-bottom: 12px;
            }
            .dco-plan-settings-editor__title {
                margin: 0;
                font-size: 14px;
                font-weight: 700;
            }
            .dco-plan-settings-editor__help {
                margin: 4px 0 0;
                color: var(--text-muted, #687481);
                font-size: 12px;
                line-height: 1.6;
            }
            .dco-plan-settings-editor__badge {
                flex: 0 0 auto;
                padding: 4px 8px;
                border-radius: 999px;
                background: var(--yellow-100, #fff3cd);
                color: var(--yellow-900, #664d03);
                font-size: 11px;
                font-weight: 600;
                opacity: 0;
                transition: opacity .15s ease;
            }
            .dco-plan-settings-editor.is-dirty .dco-plan-settings-editor__badge {
                opacity: 1;
            }
            .dco-plan-settings-editor__grid {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 12px;
            }
            .dco-plan-settings-editor__field {
                min-width: 0;
            }
            .dco-plan-settings-editor__field label {
                display: block;
                margin-bottom: 6px;
                font-size: 12px;
                font-weight: 600;
                color: var(--text-color, #36414c);
            }
            .dco-plan-settings-editor__input-wrap {
                position: relative;
            }
            .dco-plan-settings-editor .form-control {
                width: 100%;
                min-height: 36px;
                text-align: start;
            }
            .dco-plan-settings-editor__input-wrap.has-suffix .form-control {
                padding-inline-end: 52px;
            }
            .dco-plan-settings-editor__suffix {
                position: absolute;
                inset-inline-end: 10px;
                top: 50%;
                transform: translateY(-50%);
                pointer-events: none;
                color: var(--text-muted, #687481);
                font-size: 11px;
            }
            @media (max-width: 991px) {
                .dco-plan-settings-editor__grid {
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                }
            }
            @media (max-width: 575px) {
                .dco-plan-settings-editor__header {
                    display: block;
                }
                .dco-plan-settings-editor__badge {
                    display: inline-block;
                    margin-top: 8px;
                }
                .dco-plan-settings-editor__grid {
                    grid-template-columns: 1fr;
                }
            }
        `;
        document.head.appendChild(style);
    }

    function selectOptions(spec, value) {
        return (spec.options || []).map((option) => {
            const selected = String(option.value) === String(value ?? "") ? " selected" : "";
            return `<option value="${escapeHtml(option.value)}"${selected}>${escapeHtml(translate(option.label))}</option>`;
        }).join("");
    }

    function fieldMarkup(spec, value) {
        const fieldname = escapeHtml(spec.fieldname);
        const label = escapeHtml(translate(spec.label));
        if (spec.fieldtype === "Select") {
            return `
                <div class="dco-plan-settings-editor__field" data-fieldname="${fieldname}">
                    <label for="dco-plan-setting-${fieldname}">${label}</label>
                    <div class="dco-plan-settings-editor__input-wrap">
                        <select id="dco-plan-setting-${fieldname}" class="form-control" data-almdina-plan-setting="${fieldname}">
                            ${selectOptions(spec, value)}
                        </select>
                    </div>
                </div>
            `;
        }
        const suffix = spec.suffix ? escapeHtml(translate(spec.suffix)) : "";
        const inputClass = suffix ? "dco-plan-settings-editor__input-wrap has-suffix" : "dco-plan-settings-editor__input-wrap";
        return `
            <div class="dco-plan-settings-editor__field" data-fieldname="${fieldname}">
                <label for="dco-plan-setting-${fieldname}">${label}</label>
                <div class="${inputClass}">
                    <input
                        id="dco-plan-setting-${fieldname}"
                        class="form-control"
                        type="number"
                        inputmode="decimal"
                        min="${escapeHtml(spec.min ?? 0)}"
                        step="${escapeHtml(spec.step || "any")}"
                        value="${escapeHtml(value ?? "")}"
                        data-almdina-plan-setting="${fieldname}"
                    >
                    ${suffix ? `<span class="dco-plan-settings-editor__suffix">${suffix}</span>` : ""}
                </div>
            </div>
        `;
    }

    function editorHost(frm) {
        const wrapper = actionSurface(frm);
        if (!wrapper) return null;
        const shell = wrapper.find(".dco-plan-actions-shell").first();
        return shell.length ? shell : null;
    }

    function markEditorDirty(host, dirty) {
        if (!host || !host.length) return;
        host.find(EDITOR_SELECTOR).toggleClass("is-dirty", Boolean(dirty));
    }

    function patchFromControl(store, control) {
        const input = $(control);
        const fieldname = String(input.attr("data-almdina-plan-setting") || "");
        if (!PLAN_SETTING_FIELDS.includes(fieldname)) return;
        const spec = PLAN_SETTING_SPECS.find((entry) => entry.fieldname === fieldname);
        if (!spec) return;
        const raw = input.val();
        const value = spec.fieldtype === "Float"
            ? (String(raw ?? "").trim() === "" ? null : Number(raw))
            : String(raw ?? "");
        store.patchDraft({ [fieldname]: value });
    }

    function mountDraftControls(frm) {
        const store = storeFor(frm);
        const state = store && store.snapshot();
        const host = editorHost(frm);
        if (!store || !state || !state.editing || !host) return false;

        installEditorStyles();
        host.find(EDITOR_SELECTOR).remove();
        const fields = PLAN_SETTING_SPECS
            .map((spec) => fieldMarkup(spec, (state.draft || {})[spec.fieldname]))
            .join("");
        host.prepend(`
            <section class="dco-plan-settings-editor${state.dirty ? " is-dirty" : ""}" aria-label="${escapeHtml(translate("إعدادات خطة القص"))}">
                <div class="dco-plan-settings-editor__header">
                    <div>
                        <h4 class="dco-plan-settings-editor__title">${escapeHtml(translate("إعدادات خطة القص"))}</h4>
                        <p class="dco-plan-settings-editor__help">${escapeHtml(translate("هذه التعديلات مستقلة عن معلومات الطلب والتكلفة، ولا تُحفظ إلا عند الضغط على حفظ خطة القص."))}</p>
                    </div>
                    <span class="dco-plan-settings-editor__badge">${escapeHtml(translate("تغييرات غير محفوظة"))}</span>
                </div>
                <div class="dco-plan-settings-editor__grid">${fields}</div>
            </section>
        `);
        const editor = host.find(EDITOR_SELECTOR).first();
        editor.find("[data-almdina-plan-setting]")
            .off("input.almdinaPlanEdit change.almdinaPlanEdit")
            .on("input.almdinaPlanEdit change.almdinaPlanEdit", function onSettingChanged() {
                patchFromControl(store, this);
                const current = store.snapshot();
                markEditorDirty(host, Boolean(current && current.dirty));
            });
        return true;
    }

    function unmountDraftControls(frm) {
        const wrapper = actionSurface(frm);
        if (wrapper) wrapper.find(EDITOR_SELECTOR).remove();
    }

    function focusDraftControl(frm, fieldname) {
        const host = editorHost(frm);
        if (!host) return false;
        const control = host.find(`[data-almdina-plan-setting="${fieldname}"]`).first();
        if (!control.length) return false;
        control.trigger("focus");
        if (control.is("input") && control[0] && typeof control[0].select === "function") {
            control[0].select();
        }
        return true;
    }

    function validateDraft(draft) {
        const values = draft || {};
        for (const spec of PLAN_SETTING_SPECS) {
            const value = values[spec.fieldname];
            if (spec.fieldtype === "Select") {
                const normalized = String(value ?? "").trim();
                const allowed = (spec.options || []).some((option) => option.value === normalized);
                if (!normalized || !allowed) {
                    return translate("يجب تحديد قيمة صالحة للحقل «{0}».").replace("{0}", translate(spec.label));
                }
                continue;
            }
            if (value === null || value === undefined || value === "" || !Number.isFinite(Number(value))) {
                return translate("القيمة المدخلة في «{0}» غير صالحة.").replace("{0}", translate(spec.label));
            }
            if (Number(value) < Number(spec.min || 0)) {
                return translate("لا يمكن أن تكون قيمة «{0}» سالبة.").replace("{0}", translate(spec.label));
            }
        }
        return "";
    }

    function projectCurrent(frm) {
        const adapter = presenterAdapter();
        if (adapter && typeof adapter.project === "function") adapter.project(frm);
    }

    async function ensureLoaded(frm) {
        const owner = stateOwner();
        const state = workspaceSnapshot(frm);
        if (state && state.status === "ready") return state;
        if (!owner || typeof owner.load !== "function") return state;
        return owner.load(frm);
    }

    async function startEditing(frm) {
        if (!can(frm, "edit_optimizer_settings")) {
            frappe.msgprint(translate("لا تملك صلاحية تعديل إعدادات خطة القص."));
            return false;
        }
        if (frm.is_dirty && frm.is_dirty()) {
            frappe.msgprint(translate("احفظ أو ألغِ تعديلات الطلب الحالية قبل فتح تعديل إعدادات خطة القص."));
            return false;
        }

        await ensureLoaded(frm);
        if (!lifecycleAllowsEdit(frm)) {
            frappe.msgprint(translate("حالة الطلب الحالية لا تسمح بتعديل إعدادات خطة القص."));
            return false;
        }

        const store = storeFor(frm);
        const seed = activeSettings(frm);
        if (!store || !seed) {
            frappe.msgprint(translate("لا توجد خطة قص قابلة لتعديل الإعدادات حاليًا."));
            return false;
        }
        store.beginEdit(seed);
        refreshFieldAccess(frm);
        setPlanActionsSuspended(frm, true);
        signalEditChanged(frm);
        schedule(frm);
        window.requestAnimationFrame(() => focusDraftControl(frm, "kerf_mm"));
        return true;
    }

    async function cancelEditing(frm) {
        if (!isEditing(frm)) return false;
        const store = storeFor(frm);
        if (store) store.cancelEdit();
        unmountDraftControls(frm);
        setPlanActionsSuspended(frm, false);
        projectCurrent(frm);
        refreshFieldAccess(frm);
        signalEditChanged(frm);
        return true;
    }

    async function saveEditing(frm) {
        if (!isEditing(frm)) return false;
        if (!canEditPlanSettings(frm)) {
            await cancelEditing(frm);
            frappe.msgprint(translate("لم تعد حالة الطلب الحالية تسمح لك بتعديل إعدادات خطة القص."));
            return false;
        }

        const store = storeFor(frm);
        const state = store && store.snapshot();
        const api = window.AlmdinaPlanWorkspaceAPI;
        if (!store || !state || !api || typeof api.saveSettings !== "function") return false;

        const validationMessage = validateDraft(state.draft || {});
        if (validationMessage) {
            frappe.msgprint(validationMessage);
            focusDraftControl(
                frm,
                PLAN_SETTING_SPECS.find((spec) => {
                    const value = (state.draft || {})[spec.fieldname];
                    if (spec.fieldtype === "Select") {
                        return !(spec.options || []).some((option) => option.value === String(value ?? "").trim());
                    }
                    return value === null || value === undefined || value === ""
                        || !Number.isFinite(Number(value)) || Number(value) < Number(spec.min || 0);
                })?.fieldname || "kerf_mm"
            );
            return false;
        }

        if (state.dirty) {
            await api.saveSettings(frm.doc.name, state.draft || {});
        }

        unmountDraftControls(frm);
        setPlanActionsSuspended(frm, false);
        const owner = stateOwner();
        if (owner && typeof owner.load === "function") {
            await owner.load(frm, { force: true });
        } else {
            store.cancelEdit();
        }
        projectCurrent(frm);
        refreshFieldAccess(frm);
        signalEditChanged(frm);
        frappe.show_alert({
            message: translate("تم حفظ إعدادات خطة القص. أعد الحساب لتحديث النتيجة."),
            indicator: "green",
        }, 5);
        return true;
    }

    function sync(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        if (isEditing(frm) && !canEditPlanSettings(frm)) {
            const store = storeFor(frm);
            if (store) store.cancelEdit();
            unmountDraftControls(frm);
            setPlanActionsSuspended(frm, false);
            refreshFieldAccess(frm);
            signalEditChanged(frm);
            return;
        }
        if (isEditing(frm)) {
            refreshFieldAccess(frm);
            mountDraftControls(frm);
            setPlanActionsSuspended(frm, true);
            return;
        }
        unmountDraftControls(frm);
        setPlanActionsSuspended(frm, false);
        projectCurrent(frm);
        refreshFieldAccess(frm);
    }

    function schedule(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        const context = documentContext();
        if (context && typeof context.scheduleFrame === "function") {
            context.scheduleFrame(frm, "plan-settings-edit-session", () => sync(frm));
            return;
        }
        window.requestAnimationFrame(() => {
            if (window.cur_frm === frm) sync(frm);
        });
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
        almdina_edit_session_changed(frm) { schedule(frm); },
    });

    [
        "almdina:permissions-updated",
        "almdina:stage-context-ready",
        "almdina:surfaces-settled",
        "almdina:plan-workspace-updated",
    ].forEach((eventName) => {
        window.addEventListener(eventName, () => {
            const frm = window.cur_frm;
            if (frm && frm.doctype === "Door Cutting Order") schedule(frm);
        });
    });

    window.AlmdinaPlanEditSessionUX = Object.freeze({
        PLAN_SETTING_FIELDS,
        PLAN_SETTING_SPECS,
        canEditPlanSettings,
        isEditing,
        planSettingsMayWrite,
        startEditing,
        cancelEditing,
        saveEditing,
        validateDraft,
        schedule,
    });
})();
