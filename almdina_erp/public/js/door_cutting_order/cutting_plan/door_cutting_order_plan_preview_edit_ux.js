(() => {
    "use strict";

    if (window.AlmdinaPlanPreviewEditUX) return;

    const legacy = window.AlmdinaPlanEditSessionUX;
    if (!legacy) return;

    const SYNC_KEY = "__almdinaPlanPreviewEditSyncScheduled";

    function previewOwner() {
        return window.AlmdinaPlanPreviewSession || null;
    }

    function presenter() {
        return window.AlmdinaPlanPreviewPresenter || null;
    }

    function planToolbar(frm) {
        const root = frm && frm.wrapper;
        const node = root && (root.nodeType ? root : root[0]);
        return node && node.querySelector
            ? node.querySelector('.dco-tab-edit-toolbar[data-almdina-tab-edit-kind="plan"]')
            : null;
    }

    function actionWrapper(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.plan_control_actions;
        return field && field.$wrapper && field.$wrapper.length ? field.$wrapper : null;
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
        return Boolean(
            editing(frm)
            && owner
            && typeof owner.isCommittable === "function"
            && owner.isCommittable(frm)
            && !owner.isBusy(frm)
        );
    }

    function saveBlockedReason(frm) {
        const owner = previewOwner();
        const state = previewSnapshot(frm);
        if (state.status === "previewing") return "انتظر حتى تكتمل معاينة الخطة.";
        if (state.status === "saving") return "جاري حفظ الخطة المختارة.";
        if (state.status === "stale") return "تم تعديل الإعدادات. أعد الحساب لمعاينة الخطة الجديدة قبل الحفظ.";
        if (state.status === "error") return "تعذرت المعاينة السابقة. أعد الحساب ثم احفظ.";
        if (state.status === "ready" && owner && !owner.isCommittable(frm)) {
            return "المعاينة الحالية لم تنجح في التحقق الهندسي. جرّب إعدادات أخرى ثم أعد الحساب.";
        }
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
                    syncSaveButton(frm);
                    const view = presenter();
                    if (view && typeof view.renderActionMessage === "function") {
                        view.renderActionMessage(frm, true, previewSnapshot(frm).status, false);
                    }
                }
            );
    }

    function syncPresentation(frm) {
        const view = presenter();
        const owner = previewOwner();
        const active = editing(frm);
        const state = previewSnapshot(frm);
        const committable = Boolean(owner && owner.isCommittable && owner.isCommittable(frm));

        if (view && typeof view.renderActionMessage === "function") {
            view.renderActionMessage(frm, active, state.status, committable);
        }
        if (!active || !view || !owner) return;

        if ((state.status === "ready" || state.status === "saving") && state.payload && state.payload.plan) {
            view.renderPreviewPlan(frm, state, committable);
            return;
        }
        view.renderPersistedEditingState(frm, state.status);
    }

    function sync(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        bindDraftInvalidation(frm);
        syncSaveButton(frm);
        syncPresentation(frm);
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
        const view = presenter();
        if (view && typeof view.restorePersistedPresentation === "function") {
            view.restorePersistedPresentation(frm);
        }
        schedule(frm);
        return result;
    }

    async function refreshCommittedWorkspaces(frm) {
        const coordinator = window.AlmdinaWorkspaceSyncCoordinator;
        if (
            coordinator
            && typeof coordinator.invalidate === "function"
            && typeof coordinator.refresh === "function"
        ) {
            coordinator.invalidate(frm, ["plan", "cost"], "plan_changed");
            await coordinator.refresh(frm, ["plan", "cost"], {
                force: true,
                reason: "plan_changed",
            });
            const adapter = window.AlmdinaPlanWorkspacePresenterAdapter;
            if (adapter && typeof adapter.project === "function") adapter.project(frm);
            return true;
        }

        // Compatibility fallback for assets from before the shared coordinator.
        const controls = window.AlmdinaPlanControlsUX;
        if (controls && typeof controls.refreshWorkspaceOwners === "function") {
            await controls.refreshWorkspaceOwners(frm);
            return true;
        }
        const workspace = window.AlmdinaPlanWorkspaceState;
        if (workspace && typeof workspace.load === "function") {
            await workspace.load(frm, { force: true });
            return true;
        }
        return false;
    }

    async function saveEditing(frm) {
        const owner = previewOwner();
        if (!owner || !owner.isCommittable(frm)) {
            frappe.msgprint(__(saveBlockedReason(frm)));
            schedule(frm);
            return false;
        }
        try {
            const committed = await owner.commit(frm);
            if (!committed) return false;
            if (legacy.isEditing(frm)) await Promise.resolve(legacy.cancelEditing(frm));

            await refreshCommittedWorkspaces(frm);
            const view = presenter();
            if (view && typeof view.restorePersistedPresentation === "function") {
                view.restorePersistedPresentation(frm);
            }
            frappe.show_alert({
                message: __("تم حفظ خطة المعاينة وتحديث التكلفة المرتبطة بها."),
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
        refreshCommittedWorkspaces,
        schedule,
        sync,
    });
})();