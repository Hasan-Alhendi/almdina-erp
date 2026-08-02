(() => {
    "use strict";

    if (window.AlmdinaOrderPermissionRefreshUX) return;

    function context() {
        return window.AlmdinaDocumentContext || null;
    }

    function capture(frm) {
        const documentContext = context();
        if (documentContext && typeof documentContext.capture === "function") {
            return documentContext.capture(frm);
        }
        return `${frm.doctype || ""}::${frm.doc && frm.doc.name || "__new__"}`;
    }

    function isCurrent(frm, identity) {
        const documentContext = context();
        if (documentContext && typeof documentContext.isCurrent === "function") {
            return documentContext.isCurrent(frm, identity);
        }
        return Boolean(window.cur_frm === frm && capture(frm) === identity);
    }

    function applySurfaces(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;

        const cost = window.AlmdinaCostPermissionsUX;
        if (cost && typeof cost.apply === "function") {
            cost.apply(frm);
        }

        const plans = window.AlmdinaPlanTabsUX;
        if (plans && typeof plans.afterRender === "function") {
            const shown = plans.afterRender(frm);
            if (!shown) {
                const field = frm.fields_dict.cutting_plan_html;
                if (field && field.$wrapper) field.$wrapper.empty();
            }
        }
    }

    function refreshPermissions(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") {
            return Promise.resolve(false);
        }
        if (frm.__almdinaPermissionRefreshPromise) {
            return frm.__almdinaPermissionRefreshPromise;
        }

        const identity = capture(frm);
        const permissions = window.AlmdinaPermissions;
        const operation = permissions && typeof permissions.refresh === "function"
            ? permissions.refresh()
            : Promise.resolve();

        frm.__almdinaPermissionRefreshPromise = Promise.resolve(operation)
            .then(() => {
                if (!isCurrent(frm, identity)) return false;
                applySurfaces(frm);
                return true;
            })
            .catch(error => {
                console.error("Failed to refresh Almdina permissions", error);
                return false;
            })
            .finally(() => {
                frm.__almdinaPermissionRefreshPromise = null;
            });

        return frm.__almdinaPermissionRefreshPromise;
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) {
            window.setTimeout(() => refreshPermissions(frm), 0);
        },
        refresh(frm) {
            window.setTimeout(() => refreshPermissions(frm), 0);
        },
    });

    window.addEventListener("almdina:permissions-updated", () => {
        const frm = window.cur_frm;
        if (
            frm
            && frm.doctype === "Door Cutting Order"
            && !frm.__almdinaPermissionRefreshPromise
        ) {
            applySurfaces(frm);
        }
    });

    window.AlmdinaOrderPermissionRefreshUX = Object.freeze({
        applySurfaces,
        refreshPermissions,
    });
})();
