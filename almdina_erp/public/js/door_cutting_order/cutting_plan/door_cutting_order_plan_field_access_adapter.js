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

    function editSessionOwner() {
        return window.AlmdinaPlanEditSessionUX || null;
    }

    function installNativeStatusOwner(field) {
        if (!field || !field.df || field.df[STATUS_OWNER_KEY]) return;

        const df = field.df;
        const previousGetStatus = typeof df.get_status === "function"
            ? df.get_status
            : null;

        df.get_status = function almdinaFocusedPlanFieldStatus(control) {
            if (this.hidden || this.hidden_due_to_dependency) return "None";

            if (previousGetStatus) {
                const previousStatus = previousGetStatus.call(this, control);
                if (previousStatus === "None") return "None";
            }

            if (this[STATUS_KEY] !== "Write") return "Read";
            const editor = editSessionOwner();
            const frm = control && control.frm;
            if (
                !editor
                || typeof editor.planSettingsMayWrite !== "function"
                || !editor.planSettingsMayWrite(frm)
            ) {
                return "Read";
            }
            return "Write";
        };
        df[STATUS_OWNER_KEY] = true;
    }

    function syncNativeStatus(frm, field) {
        if (!field || !field.df) return;
        installNativeStatusOwner(field);

        const editor = editSessionOwner();
        const editingAllowed = Boolean(
            editor
            && typeof editor.planSettingsMayWrite === "function"
            && editor.planSettingsMayWrite(frm)
        );
        field.df[STATUS_KEY] = Number(field.df.read_only || 0) === 0
            && editingAllowed
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
            syncNativeStatus(frm, frm.fields_dict[fieldname]);
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
