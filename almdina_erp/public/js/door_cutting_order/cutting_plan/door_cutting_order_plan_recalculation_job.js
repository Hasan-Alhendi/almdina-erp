(() => {
    "use strict";

    if (window.AlmdinaPlanRecalculationJob) return;

    const ENQUEUE_METHOD =
        "almdina_erp.almdina_erp.services.cutting_plan_recalculation_job_service.enqueue_system_plan_recalculation";
    const STATUS_METHOD =
        "almdina_erp.almdina_erp.services.cutting_plan_recalculation_job_service.get_system_plan_recalculation_status";
    const REALTIME_EVENT = "almdina_system_plan_recalculation";
    const LOCAL_EVENT = "almdina:plan-recalculation-updated";
    const STATE_KEY = "__almdinaPlanRecalcJob";
    const LISTENER_KEY = "__almdinaPlanRecalcRealtimeBound";
    const POLL_MS = 2500;
    const QUEUE_STALL_MS = 60000;
    const ACTIVE = new Set(["queued", "running"]);

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function can(frm, capability) {
        const permissions = window.AlmdinaPermissions;
        if (!permissions) return false;
        if (frm && typeof permissions.canDocument === "function") {
            return Boolean(permissions.canDocument(frm, capability));
        }
        return typeof permissions.can === "function" && Boolean(permissions.can(capability));
    }

    function emptyState() {
        return {
            status: "idle",
            generation: 0,
            pending_rerun: false,
            error: "",
            queuedAt: 0,
            stalled: false,
        };
    }

    function snapshot(frm) {
        return (frm && frm[STATE_KEY]) || emptyState();
    }

    function isActive(frm) {
        return ACTIVE.has(String(snapshot(frm).status || "idle"));
    }

    function dispatch(frm) {
        window.dispatchEvent(new CustomEvent(LOCAL_EVENT, {
            detail: {
                frm,
                orderName: frm && frm.doc ? frm.doc.name : null,
                state: snapshot(frm),
            },
        }));
    }

    function applyState(frm, payload, options = {}) {
        if (!frm || !frm.doc) return snapshot(frm);
        const incomingGeneration = Number(payload && payload.generation || 0);
        const current = snapshot(frm);
        if (
            !options.force
            && incomingGeneration
            && Number(current.generation || 0) > incomingGeneration
        ) {
            return current;
        }
        const next = {
            status: String((payload && payload.status) || "idle"),
            generation: incomingGeneration || Number(current.generation || 0),
            pending_rerun: Boolean(payload && payload.pending_rerun),
            error: String((payload && payload.error) || ""),
            queuedAt: ACTIVE.has(String((payload && payload.status) || ""))
                ? (current.queuedAt || Date.now())
                : 0,
            stalled: false,
        };
        if (next.status === "queued" && next.queuedAt && (Date.now() - next.queuedAt) >= QUEUE_STALL_MS) {
            next.stalled = true;
        }
        frm[STATE_KEY] = next;
        dispatch(frm);
        return next;
    }

    async function call(method, args) {
        const response = await frappe.call({
            method,
            args,
            freeze: false,
        });
        return response && response.message !== undefined ? response.message : null;
    }

    function syncCoordinator() {
        return window.AlmdinaWorkspaceSyncCoordinator || null;
    }

    async function refreshWorkspaces(frm) {
        const coordinator = syncCoordinator();
        if (!coordinator || typeof coordinator.refresh !== "function") return;
        await coordinator.refresh(frm, ["plan", "cost"], {
            force: true,
            activeOnly: false,
            reason: "background_recalculation",
        });
    }

    function stopPolling(frm) {
        const context = documentContext();
        if (context && typeof context.cancelEffect === "function") {
            context.cancelEffect(frm, "plan-recalculation-poll");
        }
    }

    function schedulePoll(frm) {
        if (!isActive(frm)) {
            stopPolling(frm);
            return;
        }
        const context = documentContext();
        if (!context || typeof context.schedule !== "function") return;
        context.schedule(frm, "plan-recalculation-poll", async () => {
            if (!window.cur_frm || window.cur_frm !== frm) return;
            await fetchStatus(frm);
            if (isActive(frm)) schedulePoll(frm);
        }, POLL_MS);
    }

    async function fetchStatus(frm) {
        if (!frm || !frm.doc || !frm.doc.name || (frm.is_new && frm.is_new())) return snapshot(frm);
        try {
            const payload = await call(STATUS_METHOD, { order_name: frm.doc.name });
            const previous = snapshot(frm);
            const next = applyState(frm, payload || emptyState(), { force: true });
            if (ACTIVE.has(previous.status) && !ACTIVE.has(next.status)) {
                await refreshWorkspaces(frm);
            } else if (isActive(frm)) {
                schedulePoll(frm);
            }
            return next;
        } catch (error) {
            console.debug("System plan recalculation status read failed", error);
            return snapshot(frm);
        }
    }

    function onRealtime(payload) {
        const frm = window.cur_frm;
        if (!frm || frm.doctype !== "Door Cutting Order" || !payload) return;
        if (String(payload.order_name || "") !== String(frm.doc && frm.doc.name || "")) return;
        const context = documentContext();
        const token = context && typeof context.capture === "function" ? context.capture(frm) : null;
        if (context && token && typeof context.isCurrent === "function" && !context.isCurrent(frm, token)) {
            return;
        }
        const previous = snapshot(frm);
        const next = applyState(frm, payload);
        if (ACTIVE.has(next.status)) {
            schedulePoll(frm);
            return;
        }
        stopPolling(frm);
        if (ACTIVE.has(previous.status) && !ACTIVE.has(next.status)) {
            refreshWorkspaces(frm).catch((error) => {
                console.debug("Workspace refresh after background recalc failed", error);
            });
        }
    }

    function unbindRealtime() {
        if (!window[LISTENER_KEY]) return;
        if (frappe.realtime && typeof frappe.realtime.off === "function") {
            frappe.realtime.off(REALTIME_EVENT, onRealtime);
        }
        window[LISTENER_KEY] = false;
    }

    function bindRealtime() {
        if (window[LISTENER_KEY]) return;
        if (!frappe.realtime || typeof frappe.realtime.on !== "function") return;
        frappe.realtime.on(REALTIME_EVENT, onRealtime);
        window[LISTENER_KEY] = true;
    }

    function overlayFromPlan(frm) {
        const owner = window.AlmdinaPlanWorkspaceState;
        const state = owner && typeof owner.snapshot === "function" ? owner.snapshot(frm) : null;
        return state && state.data && state.data.background_recalculation
            ? state.data.background_recalculation
            : null;
    }

    function bind(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return false;
        bindRealtime();
        const context = documentContext();
        if (context && typeof context.registerCleanup === "function") {
            context.registerCleanup(frm, "plan-recalculation-job", () => {
                stopPolling(frm);
            });
        }
        const overlay = overlayFromPlan(frm);
        if (overlay && ACTIVE.has(String(overlay.status || ""))) {
            applyState(frm, overlay);
        }
        if (isActive(frm)) schedulePoll(frm);
        return true;
    }

    function shouldEnqueueAfterSave(frm, impact) {
        if (!frm || frm.doctype !== "Door Cutting Order") return false;
        if (frm.is_new && frm.is_new()) return false;
        if (frm.__almdina_preserve_edit_session_after_save) return false;
        if (frm.__almdina_order_checkpoint_save_in_progress) return false;
        if (!can(frm, "recalculate_plan")) return false;
        const resources = (impact && impact.resources) || [];
        return resources.includes("plan");
    }

    async function enqueueAfterSave(frm, impact) {
        if (!shouldEnqueueAfterSave(frm, impact)) return snapshot(frm);
        try {
            const payload = await call(ENQUEUE_METHOD, { order_name: frm.doc.name });
            const next = applyState(frm, payload || emptyState(), { force: true });
            if (isActive(frm)) schedulePoll(frm);
            if (payload && payload.queued) {
                const coordinator = syncCoordinator();
                if (coordinator && typeof coordinator.invalidate === "function") {
                    coordinator.invalidate(frm, ["cost"], "plan_recalculation_required");
                }
            }
            return next;
        } catch (error) {
            console.error("Background system plan recalculation enqueue failed", error);
            return snapshot(frm);
        }
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload(frm) { bind(frm); },
        refresh(frm) { bind(frm); },
    });

    window.addEventListener("almdina:workspace-freshness-changed", () => {
        const frm = window.cur_frm;
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        const overlay = overlayFromPlan(frm);
        if (!overlay) return;
        applyState(frm, overlay);
        if (isActive(frm)) schedulePoll(frm);
        else stopPolling(frm);
    });

    window.AlmdinaPlanRecalculationJob = Object.freeze({
        ENQUEUE_METHOD,
        STATUS_METHOD,
        REALTIME_EVENT,
        QUEUE_STALL_MS,
        snapshot,
        isActive,
        shouldEnqueueAfterSave,
        enqueueAfterSave,
        fetchStatus,
        bind,
        applyState,
    });
})();
