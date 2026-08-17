(() => {
    "use strict";

    if (window.AlmdinaPlanFieldAccessAdapter) return;

    const PLAN_SETTING_FIELDS = Object.freeze([
        "packing_mode",
        "cutting_machine_type",
        "kerf_mm",
        "trim_margin_mm",
        "optimization_time_limit_sec",
    ]);

    const STATUS_KEY = "__almdinaFocusedPlanStatus";
    const STATUS_OWNER_KEY = "__almdinaFocusedPlanStatusOwnerInstalled";

    function controlsOwner() {
        return window.AlmdinaPlanControlsUX || null;
    }

    function installNativeStatusOwner(field) {
        if (!field || !field.df || field.df[STATUS_OWNER_KEY]) return;

        const df = field.df;
        const previousGetStatus = typeof df.get_status === "function"
            ? df.get_status
            : null;

        // Frappe v16 consults df.get_status before it derives field status from
        // the broad DocType write permission. Plan fields intentionally have a
        // narrower capability model, so this is the stable framework extension
        // point for translating the PlanControls decision into the native input.
        df.get_status = function almdinaFocusedPlanFieldStatus(control) {
            if (this.hidden || this.hidden_due_to_dependency) return "None";

            if (previousGetStatus) {
                const previousStatus = previousGetStatus.call(this, control);
                if (previousStatus === "None") return "None";
            }

            return this[STATUS_KEY] === "Write" ? "Write" : "Read";
        };
        df[STATUS_OWNER_KEY] = true;
    }

    function syncNativeStatus(field) {
        if (!field || !field.df) return;
        installNativeStatusOwner(field);

        // PlanControls is the one policy owner. It has just projected the
        // capability + lifecycle/stage decision to df.read_only; persist that
        // decision separately so an unrelated order-edit refresh cannot replace
        // it with the broad Door Cutting Order write state afterwards.
        field.df[STATUS_KEY] = Number(field.df.read_only || 0) === 0
            ? "Write"
            : "Read";

        if (typeof field.refresh === "function") field.refresh();
    }

    function apply(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order" || !frm.fields_dict) return false;

        const controls = controlsOwner();
        if (!controls || typeof controls.applyOptimizerFieldAccess !== "function") {
            return false;
        }

        controls.applyOptimizerFieldAccess(frm);
        PLAN_SETTING_FIELDS.forEach((fieldname) => {
            syncNativeStatus(frm.fields_dict[fieldname]);
        });
        return true;
    }

    function schedule(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        const context = window.AlmdinaDocumentContext;
        if (context && typeof context.scheduleFrame === "function") {
            context.scheduleFrame(frm, "focused-plan-field-access", () => apply(frm));
            return;
        }
        window.requestAnimationFrame(() => {
            if (window.cur_frm === frm) apply(frm);
        });
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
        almdina_edit_session_changed(frm) { schedule(frm); },
        refresh_plan_controls(frm) { schedule(frm); },
        packing_mode(frm) { schedule(frm); },
        cutting_machine_type(frm) { schedule(frm); },
        kerf_mm(frm) { schedule(frm); },
        trim_margin_mm(frm) { schedule(frm); },
        optimization_time_limit_sec(frm) { schedule(frm); },
    });

    window.addEventListener("almdina:permissions-updated", () => {
        const frm = window.cur_frm;
        if (frm && frm.doctype === "Door Cutting Order") schedule(frm);
    });

    window.addEventListener("almdina:stage-context-ready", (event) => {
        const frm = event.detail && event.detail.frm;
        if (frm && frm === window.cur_frm) schedule(frm);
    });

    window.AlmdinaPlanFieldAccessAdapter = Object.freeze({
        apply,
        schedule,
    });
})();
