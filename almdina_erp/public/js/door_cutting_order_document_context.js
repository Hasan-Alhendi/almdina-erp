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

    function formIdentity(frm) {
        const doc = frm && frm.doc;
        if (!doc) return "";
        const doctype = String(doc.doctype || frm.doctype || "").trim();
        const name = String(doc.name || "__new__").trim();
        return `${doctype}::${name}`;
    }

    function capture(frm) {
        return formIdentity(frm);
    }

    function isCurrent(frm, identity) {
        if (!identity || formIdentity(frm) !== identity) return false;

        const activeForm = window.cur_frm;
        if (!activeForm) return true;
        return activeForm === frm || formIdentity(activeForm) === identity;
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

    function resetDocumentState(frm) {
        if (frm._dco_calc_timer) {
            window.clearTimeout(frm._dco_calc_timer);
            frm._dco_calc_timer = null;
        }
        frm._dco_calc_version = Number(frm._dco_calc_version || 0) + 1;

        frm._dco_selected_piece_rows = new Set();
        frm._dco_edge_color_map = {};
        frm._dco_cost_render_deferred = false;
        frm._dco_piece_type_restore_token = null;
        frm._dco_plan_recalculation_running = false;
        frm._dcoTextBoardPlanBusy = false;
        frm.__almdina_active_plan_tab = null;
        frm.__almdina_stage_type = null;

        delete frm._almdina_factory_defaults_loaded;
        delete frm._dco_added_buttons;
    }

    function synchronize(frm) {
        const identity = formIdentity(frm);
        if (!identity || frm._almdinaDocumentContextIdentity === identity) {
            return false;
        }

        frm._almdinaDocumentContextIdentity = identity;
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
