(() => {
    "use strict";

    const HTML_FIELDS = Object.freeze([
        "operator_status_strip",
        "pieces_fast_entry",
        "plan_controls_intro",
        "plan_control_actions",
        "cutting_plan_html",
        "order_cost_invoice_html",
    ]);
    const SURFACE_ORDER = Object.freeze(["input", "cost", "plan"]);
    const STAGE_CONTEXT_TTL_MS = 30000;

    function formIdentity(frm) {
        return `${frm && frm.doctype || ""}::${frm && frm.doc && frm.doc.name || "__new__"}`;
    }

    function documentToken(frm) {
        return {
            frm,
            doctype: frm && frm.doctype,
            name: frm && frm.doc && frm.doc.name,
            generation: Number(frm && frm._almdinaDocumentContextGeneration || 0),
        };
    }

    function capture(frm) {
        return documentToken(frm);
    }

    function isCurrent(frm, token) {
        if (!frm || !token || token.frm !== frm) return false;
        return (
            token.doctype === frm.doctype
            && token.name === (frm.doc && frm.doc.name)
            && token.generation === Number(frm._almdinaDocumentContextGeneration || 0)
        );
    }

    function isSameDocument(frm, token) {
        if (!frm || !token) return false;
        return (
            token.doctype === frm.doctype
            && token.name === (frm.doc && frm.doc.name)
        );
    }

    function formRoot(frm) {
        if (!frm) return $();
        if (frm.wrapper) return $(frm.wrapper);
        if (frm.page && frm.page.wrapper) return $(frm.page.wrapper);
        return $();
    }

    function clearDocumentHtml(frm) {
        HTML_FIELDS.forEach(fieldname => {
            const field = frm && frm.fields_dict && frm.fields_dict[fieldname];
            if (field && field.$wrapper) field.$wrapper.empty();
        });
    }

    function disconnectObserver(value) {
        if (value && typeof value.disconnect === "function") value.disconnect();
    }

    function resetDocumentState(frm) {
        disconnectObserver(frm.__almdina_cost_actions_observer);
        disconnectObserver(frm.__almdina_financial_observer);
        disconnectObserver(frm.__almdina_invoice_button_observer);
        disconnectObserver(frm.__almdina_cost_render_observer);
        disconnectObserver(frm.__dcoSimplePlanControlsObserver);

        frm.__almdina_cost_actions_observer = null;
        frm.__almdina_financial_observer = null;
        frm.__almdina_invoice_button_observer = null;
        frm.__almdina_cost_render_observer = null;
        frm.__dcoSimplePlanControlsObserver = null;
        frm.__dcoSimplePlanControlsScheduled = false;

        frm.__almdina_stage_context_promise = null;
        frm.__almdina_stage_context_identity = null;
        frm.__almdina_stage_context_loaded_at = 0;
        frm.__almdina_stage_context_pending = false;
        frm.__almdina_stage_context_error = null;
        frm.__almdina_stage_type = "";
        frm.__almdina_stage_role = "";
        frm.__almdina_actor_holds_stage_role = false;
        frm.__almdina_can_mutate_stage = false;
        frm.__almdina_stage_mutation_block_reason = "";

        frm.__almdinaCostSnapshotPromise = null;
        frm.__almdinaCostSnapshotContext = null;
        frm.__almdina_cost_snapshot_order = null;
        frm.__almdina_invoice_cost_reconcile_promise = null;
        frm.__almdina_invoice_cost_reconcile_identity = null;

        frm.__almdina_approved_plan_snapshot = null;
        frm.__almdina_approved_plan_order = null;
        frm.__almdina_approved_plan_loading = null;
        frm.__almdina_approved_plan_context = null;
        frm.__almdina_active_plan_tab = null;
        frm.__almdina_algorithm_preview = null;

        frm.__almdina_surface_pending = new Set();
        frm.__almdina_surface_settle_timer = null;
        frm.__almdina_surface_settle_running = false;
        frm.__almdina_surface_settle_again = false;
    }

    function synchronize(frm) {
        if (!frm) return false;
        const identity = formIdentity(frm);
        if (frm._almdinaDocumentIdentity === identity) return false;

        frm._almdinaDocumentIdentity = identity;
        frm._almdinaDocumentContextGeneration = (
            Number(frm._almdinaDocumentContextGeneration || 0) + 1
        );
        resetDocumentState(frm);
        clearDocumentHtml(frm);
        return true;
    }

    function permissions() {
        return window.AlmdinaPermissions || null;
    }

    function canDocument(frm, capability) {
        const context = permissions();
        if (!context) return false;
        return Boolean(
            typeof context.canDocument === "function"
                ? context.canDocument(frm, capability)
                : context.can(capability)
        );
    }

    function stageContextFresh(frm) {
        if (!frm || !frm.__almdina_stage_context_loaded_at) return false;
        return Date.now() - frm.__almdina_stage_context_loaded_at < STAGE_CONTEXT_TTL_MS;
    }

    function stageContextFromResponse(response) {
        const message = (response && response.message) || {};
        return {
            stageType: String(message.stage_type || ""),
            stageRole: String(message.required_role || ""),
            holdsRole: Boolean(message.actor_holds_operational_role),
            canMutate: Boolean(message.can_mutate_current_stage),
            blockReason: String(message.stage_mutation_block_reason || ""),
        };
    }

    function applyStageContext(frm, response) {
        const resolved = stageContextFromResponse(response);
        frm.__almdina_stage_type = resolved.stageType;
        frm.__almdina_stage_role = resolved.stageRole;
        frm.__almdina_actor_holds_stage_role = resolved.holdsRole;
        frm.__almdina_can_mutate_stage = resolved.canMutate;
        frm.__almdina_stage_mutation_block_reason = resolved.blockReason;
        frm.__almdina_stage_context_loaded_at = Date.now();
        frm.__almdina_stage_context_pending = false;
        frm.__almdina_stage_context_error = null;
    }

    function fallbackStageContext(frm) {
        const noStage = !String(frm && frm.doc && frm.doc.current_production_stage || "").trim();
        const editable = Boolean(
            frm
            && frm.doc
            && Number(frm.doc.docstatus || 0) === 0
            && ["Draft", "Pending Review", "Rejected"].includes(frm.doc.status || "Draft")
        );
        frm.__almdina_stage_type = "";
        frm.__almdina_stage_role = "";
        frm.__almdina_actor_holds_stage_role = noStage && editable;
        frm.__almdina_can_mutate_stage = noStage && editable;
        frm.__almdina_stage_mutation_block_reason = "";
        frm.__almdina_stage_context_loaded_at = Date.now();
        frm.__almdina_stage_context_pending = false;
    }

    function ensureStageContext(frm, force = false) {
        synchronize(frm);
        if (!frm || !frm.doc || frm.is_new && frm.is_new()) {
            fallbackStageContext(frm);
            return Promise.resolve(true);
        }
        if (!force && stageContextFresh(frm)) return Promise.resolve(true);
        if (
            frm.__almdina_stage_context_promise
            && isCurrent(frm, frm.__almdina_stage_context_identity)
        ) {
            return frm.__almdina_stage_context_promise;
        }

        const identity = capture(frm);
        const orderName = frm.doc.name;
        frm.__almdina_stage_context_pending = true;
        const request = Promise.resolve(frappe.call({
            method: "almdina_erp.almdina_erp.services.shop_floor_service.get_order_stage_context",
            args: { order_name: orderName },
        }))
            .then(response => {
                if (!isCurrent(frm, identity)) return false;
                applyStageContext(frm, response);
                if (window && typeof window.dispatchEvent === "function" && typeof CustomEvent === "function") {
                    window.dispatchEvent(new CustomEvent("almdina:stage-context-ready", { detail: { frm } }));
                }
                return true;
            })
            .catch(error => {
                if (!isCurrent(frm, identity)) return false;
                console.error("Failed to load order stage context", error);
                frm.__almdina_stage_context_error = error;
                fallbackStageContext(frm);
                return false;
            })
            .finally(() => {
                if (frm.__almdina_stage_context_promise === request) {
                    frm.__almdina_stage_context_promise = null;
                    frm.__almdina_stage_context_identity = null;
                }
            });

        frm.__almdina_stage_context_identity = identity;
        frm.__almdina_stage_context_promise = request;
        return request;
    }

    function afterStageContext(frm, callback) {
        const identity = capture(frm);
        return ensureStageContext(frm).then(() => {
            if (!isCurrent(frm, identity)) return false;
            if (typeof callback === "function") callback(frm);
            return true;
        });
    }

    function holdsStageOperationalRole(frm) {
        return Boolean(frm && frm.__almdina_actor_holds_stage_role);
    }

    function canMutateCurrentStage(frm) {
        if (!frm || !frm.doc) return false;
        if (isStageContextPending(frm)) return false;
        if (frm.__almdina_stage_context_loaded_at) {
            return Boolean(frm.__almdina_can_mutate_stage);
        }
        return holdsStageOperationalRole(frm);
    }

    function canTuneCuttingAlgorithm(frm) {
        if (!frm || !frm.doc || frm.is_new && frm.is_new() || frm.doc.approved_plan) return false;
        if (!canMutateCurrentStage(frm)) return false;
        if (frm.doc.current_production_stage) return true;
        return ["Draft", "Pending Review", "Rejected"].includes(frm.doc.status || "Draft");
    }

    function canPreviewCuttingAlgorithm(frm) {
        return Boolean(
            frm
            && frm.doc
            && !(frm.is_new && frm.is_new())
            && !frm.doc.approved_plan
            && canDocument(frm, "edit_optimizer_settings")
        );
    }

    function isStageContextPending(frm) {
        return Boolean(frm && frm.__almdina_stage_context_pending);
    }

    function stageMutationBlockReason(frm) {
        if (!frm || !frm.doc) return "";
        if (isStageContextPending(frm)) return __("جاري التحقق من صلاحية مرحلة الإنتاج...");
        return String(frm.__almdina_stage_mutation_block_reason || "");
    }

    function surfaceRegistry(frm) {
        if (!(frm.__almdina_surface_pending instanceof Set)) {
            frm.__almdina_surface_pending = new Set();
        }
        return frm.__almdina_surface_pending;
    }

    function registerSurface(frm, surface) {
        if (!frm || !SURFACE_ORDER.includes(surface)) return;
        surfaceRegistry(frm).add(surface);
        scheduleSettle(frm, 0);
    }

    function pendingSurfaces(frm) {
        return SURFACE_ORDER.filter(surface => surfaceRegistry(frm).has(surface));
    }

    function settleSurface(frm, surface) {
        if (surface === "input") {
            const input = window.AlmdinaInputStability;
            if (input && typeof input.apply === "function") input.apply(frm);
            return;
        }
        if (surface === "cost") {
            const cost = window.AlmdinaCostPermissionsUX;
            if (cost && typeof cost.apply === "function") cost.apply(frm);
            return;
        }
        if (surface === "plan") {
            const tabs = window.AlmdinaPlanTabsUX;
            if (tabs && typeof tabs.afterRender === "function" && tabs.afterRender(frm)) return;
            const plan = window.AlmdinaDoorCuttingPlanUX;
            if (plan && typeof plan.refresh === "function") plan.refresh(frm);
        }
    }

    function settleSurfaces(frm) {
        if (!frm) return;
        if (frm.__almdina_surface_settle_running) {
            frm.__almdina_surface_settle_again = true;
            return;
        }
        frm.__almdina_surface_settle_running = true;
        try {
            let pending = pendingSurfaces(frm);
            surfaceRegistry(frm).clear();
            pending.forEach(surface => settleSurface(frm, surface));
            pending = pendingSurfaces(frm);
            if (pending.length) frm.__almdina_surface_settle_again = true;
        } finally {
            frm.__almdina_surface_settle_running = false;
        }
        if (frm.__almdina_surface_settle_again) {
            frm.__almdina_surface_settle_again = false;
            scheduleSettle(frm, 0);
        }
    }

    function scheduleSettle(frm, delay = 0) {
        if (!frm) return;
        if (frm.__almdina_surface_settle_timer) {
            clearTimeout(frm.__almdina_surface_settle_timer);
        }
        frm.__almdina_surface_settle_timer = setTimeout(() => {
            frm.__almdina_surface_settle_timer = null;
            const current = window.cur_frm;
            if (current && current !== frm) return;
            settleSurfaces(frm);
        }, delay);
    }

    window.AlmdinaDocumentContext = Object.freeze({
        HTML_FIELDS,
        formIdentity,
        capture,
        isCurrent,
        isSameDocument,
        synchronize,
        ensureStageContext,
        afterStageContext,
        holdsStageOperationalRole,
        canMutateCurrentStage,
        canTuneCuttingAlgorithm,
        canPreviewCuttingAlgorithm,
        isStageContextPending,
        stageMutationBlockReason,
        registerSurface,
        pendingSurfaces,
        scheduleSettle,
        settleSurfaces,
    });

    frappe.ui.form.on("Door Cutting Order", {
        before_load(frm) { synchronize(frm); },
        onload(frm) { synchronize(frm); },
        refresh(frm) {
            synchronize(frm);
            ensureStageContext(frm);
            scheduleSettle(frm, 0);
        },
        onload_post_render(frm) { scheduleSettle(frm, 0); },
        after_save(frm) { scheduleSettle(frm, 0); },
    });

    if (window && typeof window.addEventListener === "function") {
        window.addEventListener("almdina:permissions-updated", () => {
            scheduleSettle(window.cur_frm, 0);
        });
    }
})();