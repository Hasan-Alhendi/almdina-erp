(() => {
    "use strict";

    if (window.AlmdinaPlanPreviewEditUX) return;

    const legacy = window.AlmdinaPlanEditSessionUX;
    if (!legacy) return;

    const SYNC_KEY = "__almdinaPlanPreviewEditSyncScheduled";
    let baseCoordinatorAdapter = null;

    function previewOwner() {
        return window.AlmdinaPlanPreviewSession || null;
    }

    function presenter() {
        return window.AlmdinaPlanPreviewPresenter || null;
    }

    function editSessionCoordinator() {
        return window.AlmdinaDcoEditSessionCoordinator || null;
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

    const OPTIMIZER_FIELDS = Object.freeze([
        "packing_mode",
        "cutting_machine_type",
        "kerf_mm",
        "trim_margin_mm",
        "optimization_time_limit_sec",
        "deduct_edge_thickness",
    ]);
    const DIAMETER_FIELDS = Object.freeze([
        "liner_tool_diameter_mm",
        "handle_recess_tool_diameter_mm",
        "rear_groove_tool_diameter_mm",
    ]);

    function editDraft(frm) {
        const owner = window.AlmdinaPlanWorkspaceState;
        const store = owner && typeof owner.storeFor === "function" ? owner.storeFor(frm) : null;
        const state = store && typeof store.snapshot === "function" ? store.snapshot() : null;
        return state && state.draft ? state.draft : null;
    }

    function persistedEditableSettings(frm) {
        const adapter = window.AlmdinaPlanWorkspacePresenterAdapter;
        return adapter && typeof adapter.activeSettings === "function"
            ? adapter.activeSettings(frm)
            : null;
    }

    function edgeDeductionOff(value) {
        return value === false || value === 0 || value === "0" || String(value || "").toLowerCase() === "false";
    }

    function sameSetting(fieldname, left, right) {
        if (fieldname === "deduct_edge_thickness") {
            return edgeDeductionOff(left) === edgeDeductionOff(right);
        }
        if (fieldname === "packing_mode" || fieldname === "cutting_machine_type") {
            return String(left ?? "").trim() === String(right ?? "").trim();
        }
        const leftNumber = Number(left);
        const rightNumber = Number(right);
        if (!Number.isFinite(leftNumber) && !Number.isFinite(rightNumber)) return true;
        if (!Number.isFinite(leftNumber) || !Number.isFinite(rightNumber)) return false;
        return Math.abs(leftNumber - rightNumber) < 0.000001;
    }

    function optimizerDirty(draft, persisted) {
        return OPTIMIZER_FIELDS.some((fieldname) => !sameSetting(fieldname, draft[fieldname], persisted[fieldname]));
    }

    function changedDiameters(draft, persisted) {
        const updates = {};
        DIAMETER_FIELDS.forEach((fieldname) => {
            if (!sameSetting(fieldname, draft[fieldname], persisted ? persisted[fieldname] : undefined)) {
                updates[fieldname] = draft[fieldname];
            }
        });
        return updates;
    }

    function sessionStillCurrent(frm, sessionContext) {
        if (!sessionContext) return window.cur_frm === frm;
        const coordinator = editSessionCoordinator();
        return Boolean(
            coordinator
            && typeof coordinator.isSessionCurrent === "function"
            && coordinator.isSessionCurrent(frm, sessionContext)
        );
    }

    function nestingCommitAllowed(frm) {
        const owner = previewOwner();
        return Boolean(
            editing(frm)
            && owner
            && typeof owner.isCommittable === "function"
            && owner.isCommittable(frm)
            && !owner.isBusy(frm)
        );
    }

    function canSaveEditing(frm) {
        if (!editing(frm)) return false;
        const owner = previewOwner();
        if (owner && typeof owner.isBusy === "function" && owner.isBusy(frm)) return false;
        const draft = editDraft(frm);
        const persisted = persistedEditableSettings(frm);
        if (draft && persisted && !optimizerDirty(draft, persisted) && Object.keys(changedDiameters(draft, persisted)).length) {
            return true;
        }
        return nestingCommitAllowed(frm);
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

    function saveBlockedReason(frm) {
        const owner = previewOwner();
        const state = previewSnapshot(frm);
        if (state.status === "previewing") return "Wait until the plan preview finishes.";
        if (state.status === "saving") return "Saving the selected plan.";
        if (state.status === "stale") return "The settings were changed. Recalculate to preview the new plan before saving.";
        if (state.status === "error") return "The previous preview failed. Recalculate, then save.";
        if (state.status === "ready" && owner && !owner.isCommittable(frm)) {
            return "The current preview did not pass the engineering check. Try other settings, then recalculate.";
        }
        return "Recalculate with these settings first, then save the plan shown in front of you.";
    }

    function syncSaveButton(frm) {
        const toolbar = planToolbar(frm);
        if (!toolbar || !editing(frm)) return;
        const button = toolbar.querySelector(".dco-tab-edit-save");
        if (!button) return;
        const allowed = canSaveEditing(frm);
        button.disabled = !allowed;
        button.setAttribute("aria-disabled", allowed ? "false" : "true");
        button.title = translate(allowed
            ? "Save the preview plan shown now"
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
                function onDraftSettingChanged() {
                    if (legacy.draftCanChange && !legacy.draftCanChange(frm)) return;
                    const node = this;
                    const fieldname = String(
                        (node && typeof node.getAttribute === "function" && node.getAttribute("data-almdina-plan-setting"))
                        || (node && typeof node.attr === "function" && node.attr("data-almdina-plan-setting"))
                        || ""
                    );
                    // A layer bit does not move doors. Leave the current nesting
                    // preview valid so Save can persist the bit without a new layout.
                    if (DIAMETER_FIELDS.includes(fieldname)) {
                        syncSaveButton(frm);
                        return;
                    }
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
        if (legacy.syncPhaseLocks) legacy.syncPhaseLocks(frm);
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

    function runBaseCommand(command, frm, sessionContext = null) {
        const base = baseCoordinatorAdapter;
        const operation = base && base[command];
        if (typeof operation === "function") {
            return operation(frm, sessionContext);
        }

        const fallback = command === "start"
            ? legacy.startEditing
            : command === "cancel"
                ? legacy.cancelEditing
                : legacy.saveEditing;
        return typeof fallback === "function" ? fallback(frm) : false;
    }

    function firstPlanPreviewAllowed(frm) {
        const data = window.AlmdinaPlanWorkspaceState?.snapshot?.(frm)?.data;
        return Boolean(data && !data.plans?.system_draft
            && window.AlmdinaPlanControlsUX?.canCalculate?.(frm) === true
            && window.AlmdinaPermissions?.canDocument?.(frm, "recalculate_plan"));
    }

    async function startEditingCommand(frm, sessionContext = null) {
        if (legacy.syncPhaseLocks) legacy.syncPhaseLocks(frm);
        const owner = previewOwner();
        if (owner) owner.reset(frm);
        let result;
        if (firstPlanPreviewAllowed(frm) && !legacy.canEditPlanSettings?.(frm)) {
            const store = window.AlmdinaPlanWorkspaceState?.storeFor?.(frm);
            const settings = window.AlmdinaPlanWorkspacePresenterAdapter?.activeSettings?.(frm);
            if (!store || !settings) return false;
            store.beginEdit(settings);
            frm.trigger?.("almdina_edit_session_changed");
            result = true;
        } else {
            result = await Promise.resolve(runBaseCommand("start", frm, sessionContext));
        }
        schedule(frm);
        return result;
    }

    async function cancelEditingCommand(frm, sessionContext = null) {
        if (legacy.syncPhaseLocks) legacy.syncPhaseLocks(frm);
        const owner = previewOwner();
        if (owner) owner.reset(frm);
        const result = await Promise.resolve(runBaseCommand("cancel", frm, sessionContext));
        const workspace = window.AlmdinaPlanWorkspaceState;
        const current = workspace && workspace.snapshot && workspace.snapshot(frm);
        if (result && current && current.freshness === "stale" && workspace.load) {
            await workspace.load(frm, { force: true });
        }
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

    function showCommittedResult(workspacesRefreshed, reconciled = false) {
        frappe.show_alert({
            message: translate(reconciled
                ? "The plan was verified on the server after its save response was lost."
                : workspacesRefreshed
                ? "The preview plan was saved and its related cost was updated."
                : "The preview plan was saved, but the view could not be refreshed. Reload the page to see the latest plan and cost."),
            indicator: reconciled || !workspacesRefreshed ? "orange" : "green",
        }, reconciled || !workspacesRefreshed ? 7 : 5);
    }

    async function persistToolDiameters(frm, updates) {
        const api = window.AlmdinaPlanWorkspaceAPI;
        if (!api || typeof api.saveSettings !== "function") {
            throw new Error("Could not persist tool diameters");
        }
        await api.saveSettings(frm.doc.name, updates || {});
    }

    async function finishToolDiameterSave(frm, sessionContext) {
        const owner = previewOwner();
        if (owner && typeof owner.reset === "function") owner.reset(frm);
        if (legacy.isEditing(frm)) {
            await Promise.resolve(runBaseCommand("cancel", frm, sessionContext));
        }
        const workspace = window.AlmdinaPlanWorkspaceState;
        if (workspace && typeof workspace.load === "function") {
            await workspace.load(frm, { force: true });
        }
        const view = presenter();
        if (view && typeof view.restorePersistedPresentation === "function") {
            view.restorePersistedPresentation(frm);
        }
        frappe.show_alert({
            message: translate("The cutting plan settings were saved. Recalculate to update the result."),
            indicator: "green",
        }, 5);
        schedule(frm);
        return true;
    }

    async function saveEditingCommand(frm, sessionContext = null) {
        if (legacy.syncPhaseLocks) legacy.syncPhaseLocks(frm);
        const draft = editDraft(frm);
        const persisted = persistedEditableSettings(frm);
        const nestingChanged = Boolean(draft && persisted && optimizerDirty(draft, persisted));
        const diameterUpdates = draft && persisted ? changedDiameters(draft, persisted) : {};
        const orderName = frm && frm.doc ? frm.doc.name : null;

        // A bit-only edit must not commit a nesting preview. The settings command
        // writes the System Draft and leaves the saved layout untouched.
        if (!nestingChanged && Object.keys(diameterUpdates).length) {
            try {
                await persistToolDiameters(frm, diameterUpdates);
            } catch (error) {
                console.error("Cutting plan tool diameter save failed", error);
                schedule(frm);
                return false;
            }
            if (!sessionStillCurrent(frm, sessionContext) || (frm.doc && frm.doc.name) !== orderName) return false;
            return finishToolDiameterSave(frm, sessionContext);
        }

        const owner = previewOwner();
        if (!owner || !owner.isCommittable(frm)) {
            frappe.msgprint(translate(saveBlockedReason(frm)));
            schedule(frm);
            return false;
        }

        let committed = false;
        try {
            committed = await owner.commit(frm, diameterUpdates);
        } catch (error) {
            console.error("Cutting plan preview commit failed", error);
            schedule(frm);
            return false;
        }
        if (!committed) return false;

        // The durable mutation is complete at this point. Close the same Plan edit
        // session through the undecorated base adapter so workspace state and the
        // coordinator transition finish atomically; never recurse through the public
        // coordinated cancel command while the coordinator is in its saving phase.
        if (legacy.isEditing(frm)) {
            try {
                await Promise.resolve(runBaseCommand("cancel", frm, sessionContext));
            } catch (error) {
                console.error("Cutting plan post-commit edit-session cleanup failed", error);
            }
        }

        let workspacesRefreshed = false;
        try {
            workspacesRefreshed = await refreshCommittedWorkspaces(frm);
        } catch (error) {
            console.error("Cutting plan post-commit workspace refresh failed", error);
        }

        const view = presenter();
        if (view && typeof view.restorePersistedPresentation === "function") {
            view.restorePersistedPresentation(frm);
        }
        showCommittedResult(workspacesRefreshed, committed.reconciled_commit === true);
        schedule(frm);
        return true;
    }

    function coordinated(command, frm, fallback) {
        const coordinator = editSessionCoordinator();
        if (!coordinator || typeof coordinator[command] !== "function") return fallback();
        return coordinator[command](frm, "plan");
    }

    function startEditing(frm) {
        return coordinated("start", frm, () => startEditingCommand(frm));
    }

    function cancelEditing(frm) {
        return coordinated("cancel", frm, () => cancelEditingCommand(frm));
    }

    function saveEditing(frm) {
        return coordinated("save", frm, () => saveEditingCommand(frm));
    }

    const coordinator = editSessionCoordinator();
    if (coordinator && typeof coordinator.decorate === "function") {
        coordinator.decorate("plan", (base) => {
            baseCoordinatorAdapter = base;
            return {
                ...base,
                canStart: frm => firstPlanPreviewAllowed(frm) || base.canStart?.(frm) === true,
                start: startEditingCommand,
                save: saveEditingCommand,
                cancel: cancelEditingCommand,
            };
        });
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
