(() => {
    "use strict";

    if (window.AlmdinaDocumentContext) return;

    const HTML_FIELDS = Object.freeze([
        "operator_status_strip",
        "pieces_fast_entry",
        "order_cost_invoice_html",
        "plan_control_actions",
        "plan_controls_intro",
        "cutting_plan_html",
    ]);
    const TIMER_FIELDS = Object.freeze([
        "_dco_calc_timer",
        "__almdinaPlanSurfaceTimer",
    ]);
    const TIMER_MAP_FIELDS = Object.freeze([
        "_dco_fast_trigger_timers",
        "_dco_piece_type_trigger_timers",
    ]);
    const OBSERVER_FIELDS = Object.freeze([
        "_dcoToolbarObserver",
        "__almdina_financial_observer",
        "__almdina_cost_actions_observer",
        "__dcoSimplePlanControlsObserver",
        "__dcoMobileCardsObserver",
        "_almdina_secure_dxf_observer",
    ]);

    function formIdentity(frm) {
        const doc = frm && frm.doc;
        if (!doc) return "";
        const doctype = String(doc.doctype || frm.doctype || "").trim();
        const name = String(doc.name || "__new__").trim();
        return `${doctype}::${name}`;
    }

    function capture(frm) {
        const identity = formIdentity(frm);
        if (!identity) return null;
        return Object.freeze({
            identity,
            generation: Number(frm._almdinaDocumentContextGeneration || 0),
        });
    }

    function tokenIdentity(token) {
        if (typeof token === "string") return token;
        return token && typeof token === "object" ? String(token.identity || "") : "";
    }

    function tokenGeneration(token) {
        if (!token || typeof token !== "object") return null;
        const generation = Number(token.generation);
        return Number.isFinite(generation) ? generation : null;
    }

    function isCurrent(frm, token) {
        const identity = tokenIdentity(token);
        if (!identity || formIdentity(frm) !== identity) return false;

        const generation = tokenGeneration(token);
        if (
            generation !== null
            && Number(frm._almdinaDocumentContextGeneration || 0) !== generation
        ) {
            return false;
        }

        const activeForm = window.cur_frm;
        if (!activeForm) return true;
        return activeForm === frm;
    }

    function fieldWrapper(frm, fieldname) {
        const field = frm && frm.fields_dict && frm.fields_dict[fieldname];
        return field && (field.$wrapper || field.wrapper);
    }

    function clearWrapper(wrapper) {
        if (!wrapper) return;
        if (typeof wrapper.empty === "function") {
            wrapper.empty();
            return;
        }
        if (typeof wrapper.html === "function") {
            wrapper.html("");
            return;
        }

        const node = wrapper.nodeType ? wrapper : (wrapper[0] || null);
        if (!node) return;
        if (typeof node.replaceChildren === "function") {
            node.replaceChildren();
        } else {
            node.innerHTML = "";
        }
    }

    function clearDocumentHtml(frm) {
        HTML_FIELDS.forEach(fieldname => clearWrapper(fieldWrapper(frm, fieldname)));
    }

    function clearTimer(frm, fieldname) {
        const timer = frm[fieldname];
        if (!timer) return;
        window.clearTimeout(timer);
        frm[fieldname] = null;
    }

    function clearTimerMap(frm, fieldname) {
        const timers = frm[fieldname];
        if (!timers || typeof timers !== "object") return;
        Object.values(timers).forEach(timer => {
            if (timer) window.clearTimeout(timer);
        });
        frm[fieldname] = {};
    }

    function disconnectObserver(frm, fieldname) {
        const observer = frm[fieldname];
        if (observer && typeof observer.disconnect === "function") {
            observer.disconnect();
        }
        frm[fieldname] = null;
    }

    function cancelDocumentEffects(frm) {
        TIMER_FIELDS.forEach(fieldname => clearTimer(frm, fieldname));
        TIMER_MAP_FIELDS.forEach(fieldname => clearTimerMap(frm, fieldname));
        OBSERVER_FIELDS.forEach(fieldname => disconnectObserver(frm, fieldname));
    }

    function resetDocumentState(frm) {
        cancelDocumentEffects(frm);
        frm._dco_calc_version = Number(frm._dco_calc_version || 0) + 1;

        frm._dco_selected_piece_rows = new Set();
        frm._dco_edge_color_map = {};
        frm._dco_cost_render_deferred = false;
        frm._dco_piece_type_restore_token = null;
        frm._dco_plan_recalculation_running = false;
        frm._dcoTextBoardPlanBusy = false;
        frm.__almdina_active_plan_tab = null;
        frm.__almdina_stage_type = null;
        frm.__almdina_cost_snapshot_order = null;
        frm.__almdinaCostSnapshotPromise = null;
        frm.__almdinaCostSnapshotContext = null;
        frm.__almdinaPermissionRefreshPromise = null;
        frm.__almdinaPermissionRefreshContext = null;
        frm.__almdinaProductionRouteName = null;
        frm.__almdinaProductionRouteSteps = [];
        frm.__almdinaProductionActionsPromise = null;
        frm.__almdinaProductionActionsContext = null;
        frm._dcoToolbarObservedHead = null;

        delete frm._almdina_factory_defaults_loaded;
        delete frm._dco_added_buttons;
    }

    function synchronize(frm) {
        const identity = formIdentity(frm);
        if (!identity || frm._almdinaDocumentContextIdentity === identity) {
            return false;
        }

        frm._almdinaDocumentContextIdentity = identity;
        frm._almdinaDocumentContextGeneration = (
            Number(frm._almdinaDocumentContextGeneration || 0) + 1
        );
        resetDocumentState(frm);
        clearDocumentHtml(frm);
        return true;
    }

    window.AlmdinaDocumentContext = Object.freeze({
        HTML_FIELDS,
        formIdentity,
        capture,
        isCurrent,
        synchronize,
    });

    frappe.ui.form.on("Door Cutting Order", {
        before_load(frm) { synchronize(frm); },
        onload(frm) { synchronize(frm); },
        refresh(frm) { synchronize(frm); },
    });
})();
