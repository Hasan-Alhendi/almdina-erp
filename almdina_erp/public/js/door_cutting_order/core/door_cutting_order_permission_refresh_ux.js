(() => {
    "use strict";

    if (window.AlmdinaOrderPermissionRefreshUX) return;

    const REFRESH_TTL_MS = 30_000;

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

    function identityKey(identity) {
        if (typeof identity === "string") return identity;
        if (!identity || typeof identity !== "object") return "";
        return `${String(identity.identity || "")}::${Number(identity.generation || 0)}`;
    }

    function isCurrent(frm, identity) {
        const documentContext = context();
        if (documentContext && typeof documentContext.isCurrent === "function") {
            return documentContext.isCurrent(frm, identity);
        }
        return Boolean(window.cur_frm === frm && capture(frm) === identity);
    }

    function currentTabFieldname(frm) {
        return String(
            frm
            && frm.layout
            && frm.layout.current_tab
            && frm.layout.current_tab.df
            && frm.layout.current_tab.df.fieldname
            || ""
        );
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
        const activeTab = currentTabFieldname(frm);

        // Plan and Cost are lazy workspaces. Their empty hidden HTML containers are
        // intentional and must never make the visible Order workspace look broken.
        if (activeTab === "cost_tab" && can("view_costs")) {
            const field = frm.fields_dict.order_cost_invoice_html;
            const wrapper = field && field.$wrapper;
            if (!wrapper || !wrapper.find(".dco-cost-shell").length) return true;
        }

        if (activeTab === "results_tab" && can("view_cutting_plan")) {
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

        const production = window.AlmdinaShopFloorOrderUX;
        if (production && typeof production.reconcileProductionActions === "function") {
            production.reconcileProductionActions(frm);
        }

        const edgeBanding = window.AlmdinaMultiEdgeBanding;
        if (edgeBanding && typeof edgeBanding.schedule === "function") {
            edgeBanding.schedule(frm);
        }
    }

    function markFresh(frm, identity) {
        if (!frm) return;
        frm.__almdinaPermissionRefreshCompletedContext = identityKey(identity);
        frm.__almdinaPermissionRefreshCompletedAt = Date.now();
    }

    function hasFreshContext(frm, identity) {
        if (!frm) return false;
        const key = identityKey(identity);
        const refreshedAt = Number(frm.__almdinaPermissionRefreshCompletedAt || 0);
        return Boolean(
            key
            && frm.__almdinaPermissionRefreshCompletedContext === key
            && refreshedAt > 0
            && Date.now() - refreshedAt < REFRESH_TTL_MS
        );
    }

    function refreshPermissions(frm) {
        const options = arguments.length > 1 && arguments[1] ? arguments[1] : {};
        if (!frm || frm.doctype !== "Door Cutting Order") {
            return Promise.resolve(false);
        }

        const identity = capture(frm);
        const force = Boolean(options && options.force === true);
        if (!force && hasFreshContext(frm, identity)) {
            if (surfaceNeedsRecovery(frm, window.AlmdinaPermissions)) {
                applySurfaces(frm);
                return Promise.resolve(true);
            }
            return Promise.resolve(false);
        }

        if (
            frm.__almdinaPermissionRefreshPromise
            && isCurrent(frm, frm.__almdinaPermissionRefreshContext)
        ) {
            return frm.__almdinaPermissionRefreshPromise;
        }

        const permissions = window.AlmdinaPermissions;
        const beforeSignature = permissionSignature(permissions);
        const operation = permissions && typeof permissions.refresh === "function"
            ? permissions.refresh()
            : Promise.resolve();

        const refreshPromise = Promise.resolve(operation)
            .then(() => {
                if (!isCurrent(frm, identity)) return false;
                markFresh(frm, identity);
                const changed = permissionSignature(permissions) !== beforeSignature;
                if (changed || surfaceNeedsRecovery(frm, permissions)) {
                    applySurfaces(frm);
                    return true;
                }
                return false;
            })
            .catch(error => {
                if (isCurrent(frm, identity)) {
                    console.error("Failed to refresh Almdina permissions", error);
                }
                return false;
            })
            .finally(() => {
                if (frm.__almdinaPermissionRefreshPromise === refreshPromise) {
                    frm.__almdinaPermissionRefreshPromise = null;
                    frm.__almdinaPermissionRefreshContext = null;
                }
            });

        frm.__almdinaPermissionRefreshContext = identity;
        frm.__almdinaPermissionRefreshPromise = refreshPromise;
        return refreshPromise;
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
        if (!frm || frm.doctype !== "Door Cutting Order") return;

        // Any permission-updated event means the shared context has just been
        // refreshed from the server. Mark this document identity fresh so the
        // form hooks do not immediately issue the same request again.
        markFresh(frm, capture(frm));

        // Edge-profile selection is capability-driven too. Reconcile it on every
        // authoritative permission update even when the cost/plan surfaces are
        // already healthy, otherwise drawing-only users could require a reload
        // before their per-side profile affordance appears.
        const edgeBanding = window.AlmdinaMultiEdgeBanding;
        if (edgeBanding && typeof edgeBanding.schedule === "function") {
            edgeBanding.schedule(frm);
        }

        if (
            !frm.__almdinaPermissionRefreshPromise
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

    const documentContext = context();
    if (documentContext && typeof documentContext.registerSurface === "function") {
        documentContext.registerSurface("order-permission-surfaces", {
            isReady(frm) {
                return !surfaceNeedsRecovery(frm, window.AlmdinaPermissions);
            },
            recover(frm) {
                applySurfaces(frm);
                return true;
            },
        });
    }

    window.setTimeout(() => {
        const frm = window.cur_frm;
        if (frm && frm.doctype === "Door Cutting Order") {
            refreshPermissions(frm);
        }
    }, 0);
})();
