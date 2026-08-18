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
    const DRAFT_LIKE = new Set(["Draft", "Pending Review", "Rejected"]);
    const ACTIVE_ROUTED_STATUSES = new Set([
        "At Sharyoun",
        "At Drawing",
        "At CNC",
        "At Sanding",
    ]);
    const BLOCKED_PLAN_ACTIONS = [
        ".dco-recalculate-plan",
        ".dco-approve-cutting-plan",
        ".dco-print-cutting-plan",
        ".dco-export-dxf",
        ".dco-upload-dxf-plan",
    ].join(",");
    const ORIGINAL_DISABLED_ATTR = "data-almdina-plan-edit-original-disabled";

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

    function editor() {
        return window.AlmdinaWorkspaceFieldEditor || null;
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
        if (String(frm.doc.approved_plan || "").trim() && !isDrawingStage(frm)) return false;
        if (hasProductionRoute(frm)) return hasActiveRoutedLifecycle(frm);
        return DRAFT_LIKE.has(frm.doc.status || "Draft");
    }

    function canEditPlanSettings(frm) {
        return Boolean(can(frm, "edit_optimizer_settings") && lifecycleAllowsEdit(frm));
    }

    function workspaceSnapshot(frm) {
        const store = storeFor(frm);
        return store ? store.snapshot() : null;
    }

    function isEditing(frm) {
        const state = workspaceSnapshot(frm);
        return Boolean(state && state.editing);
    }

    function planSettingsMayWrite(frm) {
        // Native Frappe controls remain read-only. A5.2 mounts detached controls
        // backed by the Plan workspace draft, so DCO never owns mutable plan state.
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

    function mountDraftControls(frm) {
        const store = storeFor(frm);
        const fieldEditor = editor();
        const state = store && store.snapshot();
        if (!store || !fieldEditor || !state || !state.editing) return false;
        fieldEditor.mount(frm, PLAN_SETTING_FIELDS, state.draft || {}, (patch) => {
            store.patchDraft(patch);
        });
        return true;
    }

    function unmountDraftControls(frm) {
        const fieldEditor = editor();
        if (fieldEditor && typeof fieldEditor.unmount === "function") {
            fieldEditor.unmount(frm, PLAN_SETTING_FIELDS);
        }
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
        if (!canEditPlanSettings(frm)) {
            frappe.msgprint(__("لا تملك صلاحية تعديل إعدادات خطة القص أو أن حالة الطلب الحالية لا تسمح بذلك."));
            return false;
        }
        if (frm.is_dirty && frm.is_dirty()) {
            frappe.msgprint(__("احفظ أو ألغِ تعديلات الطلب الحالية قبل فتح تعديل إعدادات خطة القص."));
            return false;
        }

        await ensureLoaded(frm);
        const store = storeFor(frm);
        const seed = activeSettings(frm);
        if (!store || !seed) {
            frappe.msgprint(__("لا توجد خطة قص قابلة لتعديل الإعدادات حاليًا."));
            return false;
        }
        store.beginEdit(seed);
        refreshFieldAccess(frm);
        mountDraftControls(frm);
        setPlanActionsSuspended(frm, true);
        signalEditChanged(frm);
        const fieldEditor = editor();
        if (fieldEditor && typeof fieldEditor.focus === "function") {
            fieldEditor.focus(frm, "kerf_mm");
        }
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
            frappe.msgprint(__("لم تعد حالة الطلب الحالية تسمح لك بتعديل إعدادات خطة القص."));
            return false;
        }

        const store = storeFor(frm);
        const state = store && store.snapshot();
        const api = window.AlmdinaPlanWorkspaceAPI;
        if (!store || !state || !api || typeof api.saveSettings !== "function") return false;

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
            message: __("تم حفظ إعدادات خطة القص. أعد الحساب لتحديث النتيجة."),
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
        canEditPlanSettings,
        isEditing,
        planSettingsMayWrite,
        startEditing,
        cancelEditing,
        saveEditing,
        schedule,
    });
})();
