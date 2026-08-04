(() => {
    "use strict";

    if (window.__almdinaPlanPrintPermissionGuardLoaded) return;
    window.__almdinaPlanPrintPermissionGuardLoaded = true;

    function canPrint(frm) {
        const permissions = window.AlmdinaPermissions;
        if (!permissions) return false;
        return Boolean(
            frm && typeof permissions.canDocument === "function"
                ? permissions.canDocument(frm, "print_cutting_plan")
                : typeof permissions.can === "function"
                    && permissions.can("print_cutting_plan")
        );
    }

    function denied() {
        frappe.msgprint(__("ليس لديك صلاحية طباعة خطة القص."));
        return false;
    }

    function protectRenderer() {
        const renderer = window.AlmdinaCuttingPlanRender;
        if (!renderer || renderer.__almdinaPrintPermissionGuarded || typeof renderer.print !== "function") {
            return;
        }
        const originalPrint = renderer.print.bind(renderer);
        renderer.print = frm => canPrint(frm || window.cur_frm)
            ? originalPrint(frm || window.cur_frm)
            : denied();
        renderer.__almdinaPrintPermissionGuarded = true;
    }

    function protectTabs() {
        const tabs = window.AlmdinaPlanTabsUX;
        if (!tabs || tabs.__almdinaPrintPermissionGuarded || typeof tabs.printActivePlan !== "function") {
            return;
        }
        const originalPrint = tabs.printActivePlan.bind(tabs);
        tabs.printActivePlan = frm => canPrint(frm || window.cur_frm)
            ? originalPrint(frm || window.cur_frm)
            : denied();
        tabs.__almdinaPrintPermissionGuarded = true;
    }

    function apply() {
        protectRenderer();
        protectTabs();
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render() { apply(); },
        refresh() { apply(); },
    });

    window.addEventListener("almdina:permissions-updated", apply);
    apply();
})();
