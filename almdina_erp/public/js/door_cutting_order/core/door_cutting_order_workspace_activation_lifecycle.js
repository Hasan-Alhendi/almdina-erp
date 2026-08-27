(() => {
    "use strict";

    if (window.AlmdinaDcoWorkspaceActivationLifecycle) return;

    const DOCTYPE = "Door Cutting Order";
    const ACTIVATION_FRAME_KEY = "workspace-sync-active-tab";
    const ACTIVATION_CLEANUP_KEY = "workspace-sync-tab-activation";

    function coordinator() {
        return window.AlmdinaWorkspaceSyncCoordinator || null;
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

    function activationFields() {
        const owner = coordinator();
        if (!owner || typeof owner.activationFields !== "function") return new Set();
        return new Set(owner.activationFields());
    }

    function activate(frm, options = {}) {
        const owner = coordinator();
        if (!isOrderForm(frm) || !owner || typeof owner.activateCurrent !== "function") {
            return Promise.resolve([]);
        }
        return Promise.resolve(owner.activateCurrent(frm, options));
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
            // the derived workspace read on the next frame so activation observes
            // the final tab identity and never races the native tab transition.
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
