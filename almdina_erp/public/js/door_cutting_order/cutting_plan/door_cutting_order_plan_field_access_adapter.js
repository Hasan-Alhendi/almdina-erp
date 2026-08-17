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

    function controlsOwner() {
        return window.AlmdinaPlanControlsUX || null;
    }

    function installStatusBridge(field) {
        if (
            !field
            || field.__almdinaPlanFieldStatusBridgeInstalled
            || typeof field.get_status !== "function"
        ) {
            return;
        }

        const frameworkGetStatus = field.get_status.bind(field);
        field.__almdinaPlanFieldFrameworkGetStatus = frameworkGetStatus;
        field.get_status = function almdinaFocusedPlanFieldStatus(explain) {
            const frameworkStatus = frameworkGetStatus(explain);
            if (frameworkStatus === "None") return "None";

            // PlanControls is the policy owner. It sets df.read_only from the
            // document capability + lifecycle/stage decision. This adapter only
            // bridges that focused decision into Frappe's native display status,
            // which otherwise requires broad Door Cutting Order write access.
            return Number((this.df && this.df.read_only) || 0) === 0
                ? "Write"
                : "Read";
        };
        field.__almdinaPlanFieldStatusBridgeInstalled = true;
    }

    function apply(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order" || !frm.fields_dict) return false;

        const controls = controlsOwner();
        if (!controls || typeof controls.applyOptimizerFieldAccess !== "function") {
            return false;
        }

        // Keep one permission-policy owner. The adapter never reads roles or
        // capabilities directly; it consumes the owner's field-access result.
        controls.applyOptimizerFieldAccess(frm);

        PLAN_SETTING_FIELDS.forEach((fieldname) => {
            const field = frm.fields_dict[fieldname];
            if (!field) return;
            installStatusBridge(field);
            if (typeof field.refresh === "function") field.refresh();
        });
        return true;
    }

    function schedule(frm) {
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

    window.AlmdinaPlanFieldAccessAdapter = Object.freeze({ apply });
})();
