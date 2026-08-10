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

    function permissionSignature(permissions) {
        const snapshot = permissions && typeof permissions.snapshot === "function"
            ? permissions.snapshot()
            : null;
        const capabilities = snapshot && snapshot.capabilities
            ? snapshot.capabilities
            : {};
        return JSON.stringify(capabilities);
    }

    function surfaceNeedsRecovery(frm, permissions) {
        if (!frm || !permissions) return false;

        const can = capability => (
            typeof permissions.canDocument === "function"
                ? permissions.canDocument(frm, capability)
                : permissions.can(capability)
        );

        if (can("view_costs")) {
            const field = frm.fields_dict.order_cost_invoice_html;
            const wrapper = field && field.$wrapper;
            if (!wrapper || !wrapper.find(".dco-cost-shell").length) return true;
        }

        if (can("view_cutting_plan")) {
            const field = frm.fields_dict.cutting_plan_html;
            const wrapper = field && field.$wrapper;
            if (!wrapper || !wrapper.children().length) return true;
        }

        return false;
    }

    function applySurfaces(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;

        const cost = window.AlmdinaCostPermissionsUX;
        if (cost && typeof cost.apply === "function") {
            cost.apply(frm);
        }

        const plans = window.AlmdinaPlanTabsUX;
        if (plans && typeof plans.afterRender === "function") {
            plans.afterRender(frm);
        }

        const tabs = window.AlmdinaOrderTabPermissionsUX;
        if (tabs && typeof tabs.apply === "function") {
            tabs.apply(frm);
        }

        const revision = window.AlmdinaOrderRevisionUX;
        if (revision && typeof revision.applyImmutableFields === "function") {
            revision.applyImmutableFields(frm);
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
        const beforeSignature = permissionSignature(permissions);
        const operation = permissions && typeof permissions.refresh === "function"
            ? permissions.refresh()
            : Promise.resolve();

        frm.__almdinaPermissionRefreshPromise = Promise.resolve(operation)
            .then(() => {
                if (!isCurrent(frm, identity)) return false;
                const changed = permissionSignature(permissions) !== beforeSignature;
                if (changed || surfaceNeedsRecovery(frm, permissions)) {
                    applySurfaces(frm);
                    return true;
                }
                return false;
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
            && surfaceNeedsRecovery(frm, window.AlmdinaPermissions)
        ) {
            applySurfaces(frm);
        }
    });

    window.AlmdinaOrderPermissionRefreshUX = Object.freeze({
        applySurfaces,
        refreshPermissions,
        surfaceNeedsRecovery,
    });

    window.setTimeout(() => {
        const frm = window.cur_frm;
        if (frm && frm.doctype === "Door Cutting Order") {
            refreshPermissions(frm);
        }
    }, 0);
})();
