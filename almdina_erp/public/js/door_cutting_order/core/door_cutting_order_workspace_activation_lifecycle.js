(() => {
    "use strict";

    if (window.AlmdinaDcoWorkspaceActivationLifecycle) return;

    const DOCTYPE = "Door Cutting Order";
    const ACTIVATION_FRAME_KEY = "workspace-sync-active-tab";
    const ACTIVATION_CLEANUP_KEY = "workspace-sync-tab-activation";

    function coordinator() {
        return window.AlmdinaWorkspaceSyncCoordinator || null;
    }

    function assetRegistry() {
        return window.AlmdinaDcoWorkspaceAssetRegistry || null;
    }

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function isOrderForm(frm) {
        return Boolean(frm && frm.doc && frm.doctype === DOCTYPE);
    }

    function formRoot(frm) {
        const wrapper = frm && frm.wrapper;
        return wrapper && (wrapper.nodeType ? wrapper : wrapper[0]);
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

    function activationFields() {
        const registry = assetRegistry();
        if (registry && typeof registry.activationFields === "function") {
            return new Set(registry.activationFields());
        }
        const owner = coordinator();
        if (!owner || typeof owner.activationFields !== "function") return new Set();
        return new Set(owner.activationFields());
    }

    function capture(frm) {
        const context = documentContext();
        if (context && typeof context.capture === "function") return context.capture(frm);
        return null;
    }

    function activationStillCurrent(frm, identity, fieldname) {
        if (!isOrderForm(frm) || currentTabFieldname(frm) !== fieldname) return false;
        const context = documentContext();
        if (identity && context && typeof context.isCurrent === "function") {
            return context.isCurrent(frm, identity);
        }
        return window.cur_frm === frm;
    }

    function reconcileLoadedFeature(frm) {
        const permissionOwner = window.AlmdinaOrderPermissionRefreshUX;
        if (permissionOwner && typeof permissionOwner.applySurfaces === "function") {
            permissionOwner.applySurfaces(frm);
        }
    }

    async function activate(frm, options = {}) {
        const owner = coordinator();
        if (!isOrderForm(frm) || !owner || typeof owner.activateCurrent !== "function") {
            return [];
        }

        const fieldname = currentTabFieldname(frm);
        const identity = capture(frm);
        const registry = assetRegistry();
        if (registry && typeof registry.ensureForTab === "function") {
            await registry.ensureForTab(fieldname);
            // Downloading a feature may outlive the tab click or even the document.
            // Keep the cached assets, but never activate stale workspace data.
            if (!activationStillCurrent(frm, identity, fieldname)) return [];
            reconcileLoadedFeature(frm);
        }

        return owner.activateCurrent(frm, options);
    }

    function schedule(frm, options = {}) {
        if (!isOrderForm(frm)) return null;
        const context = documentContext();
        const run = () => {
            activate(frm, options).catch((error) => {
                console.error("DCO active workspace load failed", error);
            });
        };
        if (context && typeof context.scheduleFrame === "function") {
            return context.scheduleFrame(frm, ACTIVATION_FRAME_KEY, run);
        }
        const requestFrame = window.requestAnimationFrame || window.setTimeout;
        return requestFrame.call(window, run);
    }

    function install(frm) {
        if (!isOrderForm(frm)) return false;
        const root = formRoot(frm);
        if (!root || typeof root.addEventListener !== "function") return false;
        if (
            frm.__almdinaWorkspaceActivationRoot === root
            && frm.__almdinaWorkspaceActivationHandler
        ) {
            return true;
        }

        const previousRoot = frm.__almdinaWorkspaceActivationRoot;
        const previousHandler = frm.__almdinaWorkspaceActivationHandler;
        if (
            previousRoot
            && previousHandler
            && typeof previousRoot.removeEventListener === "function"
        ) {
            previousRoot.removeEventListener("click", previousHandler);
        }

        const handler = (event) => {
            const target = event && event.target && typeof event.target.closest === "function"
                ? event.target.closest("[data-fieldname]")
                : null;
            const fieldname = String(target && target.getAttribute("data-fieldname") || "");
            if (!fieldname || !activationFields().has(fieldname)) return;

            // Frappe updates layout.current_tab as part of the same click. Schedule
            // feature loading on the next frame so it observes the final tab identity.
            schedule(frm);
        };

        root.addEventListener("click", handler);
        frm.__almdinaWorkspaceActivationRoot = root;
        frm.__almdinaWorkspaceActivationHandler = handler;

        const context = documentContext();
        if (context && typeof context.registerCleanup === "function") {
            context.registerCleanup(frm, ACTIVATION_CLEANUP_KEY, () => {
                if (typeof root.removeEventListener === "function") {
                    root.removeEventListener("click", handler);
                }
                if (frm.__almdinaWorkspaceActivationRoot === root) {
                    frm.__almdinaWorkspaceActivationRoot = null;
                    frm.__almdinaWorkspaceActivationHandler = null;
                }
            });
        }
        return true;
    }

    function activateOnLifecycle(frm) {
        install(frm);
        schedule(frm);
    }

    frappe.ui.form.on(DOCTYPE, {
        onload_post_render(frm) {
            activateOnLifecycle(frm);
        },
        refresh(frm) {
            activateOnLifecycle(frm);
        },
    });

    window.addEventListener("almdina:permissions-updated", () => {
        const frm = window.cur_frm;
        if (isOrderForm(frm)) schedule(frm, { force: true });
    });

    window.AlmdinaDcoWorkspaceActivationLifecycle = Object.freeze({
        activationFields,
        activate,
        schedule,
        install,
    });
})();
