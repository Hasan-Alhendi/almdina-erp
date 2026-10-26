(() => {
    "use strict";

    const EDITABLE_ORDER_STATUSES = new Set(["Draft", "Pending Review", "Rejected"]);

    const DUPLICATED_ACTIONS = [
        ".dco-auto-pro-plan",
        ".dco-deep-plan",
        ".dco-optimal-plan",
        ".dco-algorithm-palette",
    ].join(",");

    const OPTIMIZER_FIELDS = [
        "packing_mode",
        "cutting_machine_type",
        "kerf_mm",
        "trim_margin_mm",
        "optimization_time_limit_sec",
    ];

    function can(frm, capability) {
        const permissions = window.AlmdinaPermissions;
        if (!permissions) return false;
        if (frm && typeof permissions.canDocument === "function") {
            return Boolean(permissions.canDocument(frm, capability));
        }
        return typeof permissions.can === "function" && Boolean(permissions.can(capability));
    }

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function stateOwner() {
        return window.AlmdinaPlanWorkspaceState || null;
    }

    function api() {
        return window.AlmdinaPlanWorkspaceAPI || null;
    }

    function previewOwner() {
        return window.AlmdinaPlanPreviewSession || null;
    }

    function workspaceSnapshot(frm) {
        const owner = stateOwner();
        return owner && typeof owner.snapshot === "function" ? owner.snapshot(frm) : null;
    }

    function workspaceData(frm) {
        const state = workspaceSnapshot(frm);
        const keeper = window.AlmdinaWorkspaceKeepPaint;
        if (keeper && typeof keeper.presentationData === "function") {
            return keeper.presentationData(state);
        }
        return state && state.status === "ready" ? state.data : null;
    }

    function workspaceReady(frm) {
        return Boolean(workspaceData(frm));
    }

    function workspaceEditing(frm) {
        const state = workspaceSnapshot(frm);
        return Boolean(state && state.editing);
    }

    function plans(frm) {
        const data = workspaceData(frm);
        return (data && data.plans) || {};
    }

    function hasSystemDraft(frm) {
        const row = plans(frm).system_draft;
        const owner = stateOwner();
        return Boolean(row && (owner && typeof owner.isCurrentDraftRow === "function"
            ? owner.isCurrentDraftRow(row)
            : String(row.status || "") === "Draft"));
    }

    function activePlan(frm) {
        const owner = stateOwner();
        return owner && typeof owner.activePlan === "function"
            ? owner.activePlan(frm, "System")
            : null;
    }

    function activeSettings(frm) {
        const state = workspaceSnapshot(frm);
        if (state && state.editing && state.draft) return { ...state.draft };
        const row = activePlan(frm);
        if (row && row.settings) return { ...row.settings };
        const data = workspaceData(frm);
        return data && data.calculation_settings
            ? { ...data.calculation_settings }
            : null;
    }

    function approvedPlanName(frm) {
        const data = workspaceData(frm);
        return String((data && data.approved_plan) || "").trim();
    }

    function setTextIfChanged(target, value) {
        if (!target || !target.length) return;
        if (String(target.text() || "") !== String(value || "")) target.text(value);
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

    function installStyles() {
        if (document.getElementById("dco-simple-plan-controls-css")) return;
        $("head").append(`
            <style id="dco-simple-plan-controls-css">
                [data-fieldname="plan_control_actions"] .dco-plan-actions {
                    display:flex !important;align-items:center !important;justify-content:flex-start !important;
                    gap:8px !important;flex-wrap:wrap !important;
                }
                [data-fieldname="plan_control_actions"] .dco-plan-document-actions {
                    display:flex !important;align-items:center !important;gap:8px !important;flex-wrap:wrap !important;
                }
                [data-fieldname="plan_control_actions"] .dco-recalculate-plan,
                [data-fieldname="plan_control_actions"] .dco-approve-cutting-plan {
                    min-width:210px;min-height:40px !important;font-weight:850 !important;border-radius:10px !important;
                }
                [data-fieldname="plan_control_actions"] .dco-print-cutting-plan,
                [data-fieldname="plan_control_actions"] .dco-export-dxf,
                [data-fieldname="plan_control_actions"] .dco-upload-dxf-plan {
                    min-height:36px !important;border-radius:10px !important;font-weight:800 !important;
                }
                [data-fieldname="plan_control_actions"] .dco-plan-actions-title { margin-bottom:10px !important; }
                @media (max-width:560px) {
                    [data-fieldname="plan_control_actions"] .dco-recalculate-plan,
                    [data-fieldname="plan_control_actions"] .dco-approve-cutting-plan,
                    [data-fieldname="plan_control_actions"] .dco-print-cutting-plan,
                    [data-fieldname="plan_control_actions"] .dco-export-dxf,
                    [data-fieldname="plan_control_actions"] .dco-upload-dxf-plan { width:100%;min-width:0; }
                }
            </style>
        `);
    }

    function applyOptimizerFieldAccess(frm) {
        OPTIMIZER_FIELDS.forEach((fieldname) => {
            const field = frm.fields_dict && frm.fields_dict[fieldname];
            if (!field || !field.df) return;
            if (Number(field.df.read_only || 0) !== 1) {
                frm.set_df_property(fieldname, "read_only", 1);
            }
        });
    }

    function isCurrentAssignee(frm) {
        if (!frm || !frm.doc) return false;
        if (!frm.doc.current_production_stage) {
            if (String(frm.doc.status || "Draft").trim() === "Draft") return true;
            return !String(frm.doc.production_path || "").trim();
        }
        const stage = frm.__almdina_stage_context || {};
        if (stage.actor_can_operate_current_stage !== undefined) {
            return Boolean(stage.actor_can_operate_current_stage);
        }
        if (stage.actor_is_current_assignee !== undefined) {
            return Boolean(stage.actor_is_current_assignee);
        }
        return Boolean(frm.__almdina_actor_holds_stage_role);
    }

    function canMutateCurrentStage(frm) {
        return isCurrentAssignee(frm);
    }

    function isPlanningStage(frm) {
        if (!frm || !frm.doc) return false;
        if (String(frm.doc.status || "").trim() === "At Drawing") return true;
        const context = frm.__almdina_stage_context || {};
        const stageType = String(
            frm.__almdina_stage_type || context.active_stage_type || ""
        ).trim();
        const routeStages = Array.isArray(context.route_stages) ? context.route_stages : [];
        return routeStages.some((stage) => (
            String(stage.stage_type || "").trim() === stageType
            && Boolean(stage.is_planning_stage)
        ));
    }

    function canTuneCuttingAlgorithm(frm) {
        if (!frm || frm.is_new()) return false;
        if (Number(frm.doc.docstatus || 0) !== 0) return false;
        if (String(frm.doc.revision_state || "Current") === "Superseded") return false;
        if (!workspaceReady(frm)) return false;

        const approved = approvedPlanName(frm);
        if (approved && isPlanningStage(frm)) return canMutateCurrentStage(frm);
        const status = String(frm.doc.status || "Draft").trim();
        if (approved && status === "Draft" && !String(frm.doc.current_production_stage || "").trim()) {
            return canMutateCurrentStage(frm);
        }
        if (approved) return false;
        if (!canMutateCurrentStage(frm)) return false;
        if (frm.doc.current_production_stage) return isPlanningStage(frm);
        return EDITABLE_ORDER_STATUSES.has(frm.doc.status || "Draft");
    }

    function stageMutationBlockReason(frm) {
        if (!frm || !frm.doc) return "";
        if (!frm.doc.current_production_stage) {
            if (String(frm.doc.status || "Draft").trim() === "Draft") return "";
            return String(frm.doc.production_path || "").trim()
                ? "The order has left the active production stages and the cutting plan cannot be edited."
                : "";
        }
        const stage = frm.__almdina_stage_context || {};
        if (stage.actor_can_operate_current_stage === true) return "";
        if (stage.actor_can_operate_current_stage === undefined && stage.actor_is_current_assignee === true) return "";
        if (stage.active_stage_assigned_to) {
            return "You can only view the plan because the current stage is assigned to another user.";
        }
        return "Assign the current stage to a user before editing the cutting plan.";
    }

    function canCalculate(frm) {
        const previews = previewOwner();
        const transport = api();
        const firstPlan = !hasSystemDraft(frm);
        const canRun = firstPlan
            ? Boolean(transport && typeof transport.bootstrapPlan === "function")
            : Boolean(previews && typeof previews.preview === "function");
        return Boolean(
            workspaceReady(frm)
            && (firstPlan || workspaceEditing(frm))
            && canTuneCuttingAlgorithm(frm)
            && can(frm, "recalculate_plan")
            && canRun
            && !(previews && typeof previews.isBusy === "function" && previews.isBusy(frm))
        );
    }

    function recalculationDisabledReason(frm) {
        if (frm.is_new()) return "Save the order before calculating the cutting plan.";
        if (!workspaceReady(frm)) return "Wait until the cutting plan finishes loading.";
        const firstPlan = !hasSystemDraft(frm);
        if (!firstPlan && !workspaceEditing(frm)) {
            return "Press “Edit” to try new settings, then recalculate to preview.";
        }
        const previews = previewOwner();
        if (previews && typeof previews.isBusy === "function" && previews.isBusy(frm)) {
            return "Wait until the current preview or save finishes.";
        }
        const approved = approvedPlanName(frm);
        const status = String(frm.doc.status || "Draft").trim();
        const preDispatchDraft = status === "Draft"
            && !String(frm.doc.current_production_stage || "").trim();
        if (approved && !isPlanningStage(frm) && !preDispatchDraft) {
            return "The approved plan cannot be recalculated outside the planning stage.";
        }
        if (!can(frm, "recalculate_plan")) return "You need the “Recalculate plan” permission to run the engine.";
        const stageReason = stageMutationBlockReason(frm);
        if (stageReason) return stageReason;
        return "";
    }

    async function preparePlanInputs(frm) {
        const compatibility = window.AlmdinaTextBoardPlanUX;
        if (compatibility && typeof compatibility.preparePlanInputs === "function") {
            return Boolean(await compatibility.preparePlanInputs(frm));
        }
        const boardUX = window.AlmdinaBoardTextUX;
        if (boardUX && typeof boardUX.syncInputs === "function") await boardUX.syncInputs(frm);
        if (!boardUX || !boardUX.canCalculatePlan(frm)) {
            frappe.msgprint(translate("Enter the board item, its dimensions, and at least one valid measurement before calculating the cutting plan."));
            return false;
        }
        return true;
    }

    async function persistPendingOrderInputs(frm) {
        const fastSave = window.AlmdinaFastSaveUX;
        if (fastSave && typeof fastSave.persistPendingOrderInputs === "function") {
            return Boolean(await fastSave.persistPendingOrderInputs(frm));
        }
        if (frm && frm.is_dirty && frm.is_dirty()) {
            frappe.msgprint(translate("Could not persist the measurement changes before calculating the cutting plan. Reload the page and try again."));
            return false;
        }
        return true;
    }

    async function ensureWorkspaceLoaded(frm) {
        const owner = stateOwner();
        if (!owner || typeof owner.load !== "function") return null;
        if (workspaceReady(frm)) return workspaceSnapshot(frm);
        return owner.load(frm);
    }

    async function refreshWorkspaceOwners(frm) {
        const planOwner = stateOwner();
        if (planOwner && typeof planOwner.load === "function") {
            await planOwner.load(frm, { force: true });
        }
        const costOwner = window.AlmdinaCostWorkspaceState;
        if (costOwner && typeof costOwner.load === "function" && costOwner.canView(frm)) {
            await costOwner.load(frm, { force: true });
        }
        const adapter = window.AlmdinaPlanWorkspacePresenterAdapter;
        if (adapter && typeof adapter.project === "function") adapter.project(frm);
    }

    async function runRecalculation(frm) {
        await ensureWorkspaceLoaded(frm);
        if (!canCalculate(frm)) {
            const reason = recalculationDisabledReason(frm);
            frappe.msgprint(reason ? translate(reason) : reason);
            return false;
        }

        const settings = activeSettings(frm);
        const previews = previewOwner();
        const transport = api();
        if (!settings || !transport) {
            frappe.msgprint(translate("Could not prepare the cutting plan service. Reload the page and try again."));
            return false;
        }
        if (!(await preparePlanInputs(frm))) return false;
        if (!(await persistPendingOrderInputs(frm))) return false;

        try {
            if (!hasSystemDraft(frm)) {
                if (typeof transport.bootstrapPlan !== "function") return false;
                await transport.bootstrapPlan(frm.doc.name, settings);
                if (previews && typeof previews.reset === "function") previews.reset(frm);
                await refreshWorkspaceOwners(frm);
                frappe.show_alert({
                    message: translate("The first cutting plan was created, saved, and the cost was updated."),
                    indicator: "green",
                }, 5);
                return true;
            }

            if (!previews || typeof previews.preview !== "function") return false;
            const ok = await previews.preview(frm, settings);
            if (ok) {
                frappe.show_alert({
                    message: translate("A new preview was created. Review it, then press “Save” to apply this change to the plan."),
                    indicator: "blue",
                }, 5);
            }
            return Boolean(ok);
        } catch (error) {
            console.error("Cutting plan calculation failed", error);
            throw error;
        }
    }

    function rowHasPlan(row) {
        if (!row || !row.snapshot_json) return false;
        try {
            const plan = typeof row.snapshot_json === "object"
                ? row.snapshot_json
                : JSON.parse(row.snapshot_json);
            return Boolean(plan && Array.isArray(plan.sheets) && plan.sheets.length);
        } catch (error) {
            return false;
        }
    }

    function approvalSource(frm) {
        const available = plans(frm);
        if (frm.__almdina_active_plan_tab === "Custom" && rowHasPlan(available.uploaded_draft)) {
            return "Custom";
        }
        return "System";
    }

    function approvalRow(frm, source) {
        const available = plans(frm);
        return source === "Custom" ? available.uploaded_draft : available.system_draft;
    }

    function approvalAllowed(frm, source) {
        const row = approvalRow(frm, source);
        return Boolean(
            workspaceReady(frm)
            && !workspaceEditing(frm)
            && can(frm, "approve_dxf")
            && !frm.is_new()
            && canMutateCurrentStage(frm)
            && rowHasPlan(row)
            && String(row.status || "") === "Draft"
            && !(row && row.validation && row.validation.needs_recalculation)
        );
    }

    async function runApproval(frm) {
        await ensureWorkspaceLoaded(frm);
        const source = approvalSource(frm);
        if (!approvalAllowed(frm, source)) {
            const row = approvalRow(frm, source);
            if (workspaceEditing(frm)) {
                frappe.msgprint(translate("Save or cancel the plan settings edit before approval."));
            } else if (row && row.validation && row.validation.needs_recalculation) {
                frappe.msgprint(translate(
                    source === "Custom"
                        ? "The order data changed. Upload a new DXF that matches the current measurements, then approve the plan."
                        : "Recalculate the cutting plan and review the new result before approval."
                ));
            } else if (!can(frm, "approve_dxf")) {
                frappe.msgprint(translate("You do not have permission to approve the cutting plan."));
            } else {
                const reason = stageMutationBlockReason(frm);
                frappe.msgprint(translate(reason || "There is no valid plan to approve in the current state."));
            }
            return false;
        }

        const sourceLabel = translate(source === "Custom" ? "Uploaded DXF plan" : "Current system plan");
        const warning = translate(approvedPlanName(frm)
            ? "An approval already exists. Continuing will create a new approval and replace the current approved plan."
            : "This plan will be fixed as the final production copy.");
        const transport = api();
        if (!transport || typeof transport.approve !== "function") return false;

        return new Promise((resolve) => {
            frappe.confirm(
                `${warning}<br><br><b>${sourceLabel}</b>`,
                async () => {
                    try {
                        await transport.approve(frm.doc.name, source);
                        await refreshWorkspaceOwners(frm);
                        const context = documentContext();
                        if (context && typeof context.refreshStageContext === "function") {
                            await context.refreshStageContext(frm);
                        } else if (context && typeof context.ensureStageContext === "function") {
                            await context.ensureStageContext(frm, { force: true });
                        }
                        frappe.show_alert({ message: translate("The cutting plan was approved for production."), indicator: "green" }, 5);
                        resolve(true);
                    } catch (error) {
                        console.error("Cutting plan approval failed", error);
                        resolve(false);
                        throw error;
                    }
                },
                () => resolve(false)
            );
        });
    }

    function approvalButtonState(frm, button) {
        const source = approvalSource(frm);
        const row = approvalRow(frm, source);
        const allowed = approvalAllowed(frm, source);
        if (button.prop("disabled") === allowed) button.prop("disabled", !allowed);
        button.attr("aria-disabled", allowed ? "false" : "true");
        setTextIfChanged(button, translate(source === "Custom" ? "Approve DXF plan" : "Approve cutting plan"));
        if (!allowed) {
            button.attr(
                "title",
                translate(row && row.validation && row.validation.needs_recalculation
                    ? (
                        source === "Custom"
                            ? "Upload a new DXF that matches the current order data before approval"
                            : "Recalculate the plan before approving it"
                    )
                    : "Approval is unavailable in the current order state, or you do not have permission")
            );
        } else button.removeAttr("title");
    }

    function installApprovalAction(frm, shell) {
        if (!can(frm, "approve_dxf") || !canMutateCurrentStage(frm)) {
            shell.find(".dco-approve-cutting-plan").remove();
            return;
        }
        let host = shell.find(".dco-plan-actions").first();
        if (!host.length) host = shell;
        let button = shell.find(".dco-approve-cutting-plan").first();
        if (!button.length) {
            button = $('<button type="button" class="btn btn-success btn-sm dco-approve-cutting-plan"></button>');
            host.append(button);
        }
        approvalButtonState(frm, button);
        const element = button.get(0);
        if (element && !element.__almdinaApprovePlanBound) {
            button.off("click");
            button.on("click.almdinaApprovePlan", (event) => {
                event.preventDefault();
                event.stopImmediatePropagation();
                runApproval(frm);
            });
            element.__almdinaApprovePlanBound = true;
        }
    }

    function bindRecalculationAction(frm, button) {
        if (!button || !button.length) return;
        const firstPlan = !hasSystemDraft(frm);
        setTextIfChanged(
            button,
            translate(firstPlan ? "Calculate the cutting plan" : "Recalculate with the current settings")
        );
        const allowed = canCalculate(frm);
        if (button.prop("disabled") === allowed) button.prop("disabled", !allowed);
        button.attr("aria-disabled", allowed ? "false" : "true");
        button.attr(
            "title",
            translate(
                recalculationDisabledReason(frm)
                || (firstPlan
                    ? "Create and save the first cutting plan and update the cost automatically"
                    : "Create a temporary preview with these settings before saving the change")
            )
        );
        const element = button.get(0);
        if (element && !element.__almdinaPlanCommandBound) {
            button.off("click");
            button.on("click.almdinaPlanCommand", (event) => {
                event.preventDefault();
                event.stopImmediatePropagation();
                runRecalculation(frm);
            });
            element.__almdinaPlanCommandBound = true;
        }
    }

    function simplifyActions(frm) {
        const field = frm.fields_dict && frm.fields_dict.plan_control_actions;
        if (!field || !field.$wrapper) return;
        if (!workspaceReady(frm)) return;

        const shell = field.$wrapper.children(".dco-plan-actions-shell").first();
        if (!shell.length) {
            const presenter = window.AlmdinaDoorCuttingPlanUX;
            if (presenter && typeof presenter.refresh === "function") presenter.refresh(frm);
            return;
        }

        shell.attr("dir", uiDirection());
        const duplicated = shell.find(DUPLICATED_ACTIONS);
        if (duplicated.length) duplicated.remove();
        bindRecalculationAction(frm, shell.find(".dco-recalculate-plan").first());
        installApprovalAction(frm, shell);

        const note = shell.find(".dco-plan-note").first();
        if (note.length) {
            let message;
            if (!hasSystemDraft(frm) && can(frm, "recalculate_plan")) {
                message = can(frm, "edit_optimizer_settings")
                    ? "Start with “Calculate the cutting plan”. You can edit the settings first or use the current factory settings. The plan will be saved and the cost updated automatically."
                    : "Start with “Calculate the cutting plan”. The current plan settings or factory settings will be used and the cost will update automatically. Changing the settings needs a separate permission.";
            } else if (can(frm, "edit_optimizer_settings")) {
                message = "Press “Edit” to try algorithms and settings. Recalculation creates a preview, and the change is not saved until you press “Save”.";
            } else if (can(frm, "recalculate_plan")) {
                message = "The engine can be run again with the saved settings. Changing the algorithm, kerf, or trim needs the “Edit cutting algorithm” permission.";
            } else {
                message = "You need the “Recalculate plan” permission to run the cutting plan engine.";
            }
            note.attr("dir", uiDirection());
            setTextIfChanged(note, translate(message));
        }
    }

    function apply(frm) {
        installStyles();
        applyOptimizerFieldAccess(frm);
        simplifyActions(frm);
    }

    function scheduleSimplify(frm) {
        if (frm.__dcoSimplePlanControlsScheduled) return;
        frm.__dcoSimplePlanControlsScheduled = true;
        const run = () => {
            frm.__dcoSimplePlanControlsScheduled = false;
            simplifyActions(frm);
        };
        const context = documentContext();
        if (context && typeof context.scheduleFrame === "function") {
            context.scheduleFrame(frm, "simple-plan-controls", run);
            return;
        }
        requestAnimationFrame(() => {
            if (window.cur_frm === frm) run();
        });
    }

    function observeActions(frm) {
        const field = frm.fields_dict && frm.fields_dict.plan_control_actions;
        const node = field && field.$wrapper && field.$wrapper[0];
        if (!node || frm.__dcoSimplePlanControlsObserver) return;
        frm.__dcoSimplePlanControlsObserver = new MutationObserver(() => scheduleSimplify(frm));
        frm.__dcoSimplePlanControlsObserver.observe(node, { childList: true, subtree: true });
        const context = documentContext();
        if (context && typeof context.registerObserver === "function") {
            context.registerObserver(frm, "simple-plan-controls-observer", frm.__dcoSimplePlanControlsObserver);
        }
    }

    function refresh(frm) {
        const context = documentContext();
        const token = context && typeof context.capture === "function" ? context.capture(frm) : null;
        const run = () => {
            if (context && !context.isCurrent(frm, token)) return;
            apply(frm);
            observeActions(frm);
        };
        if (context && typeof context.ensureStageContext === "function") {
            context.ensureStageContext(frm).then(run);
            return;
        }
        run();
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { refresh(frm); },
        refresh(frm) { refresh(frm); },
        board_description(frm) { refresh(frm); },
        board_length_cm(frm) { refresh(frm); },
        board_width_cm(frm) { refresh(frm); },
        almdina_edit_session_changed(frm) { refresh(frm); },
        refresh_plan_controls(frm) { refresh(frm); },
    });

    [
        "almdina:permissions-updated",
        "almdina:stage-context-ready",
        "almdina:plan-workspace-updated",
        "almdina:plan-preview-updated",
    ].forEach((eventName) => {
        window.addEventListener(eventName, (event) => {
            const frm = eventName === "almdina:stage-context-ready"
                ? event.detail && event.detail.frm
                : window.cur_frm;
            if (frm && frm.doctype === "Door Cutting Order" && frm === window.cur_frm) refresh(frm);
        });
    });

    window.AlmdinaPlanControlsUX = Object.freeze({
        apply,
        applyOptimizerFieldAccess,
        canCalculate,
        preparePlanInputs,
        persistPendingOrderInputs,
        runRecalculation,
        runApproval,
        refreshWorkspaceOwners,
    });
})();
