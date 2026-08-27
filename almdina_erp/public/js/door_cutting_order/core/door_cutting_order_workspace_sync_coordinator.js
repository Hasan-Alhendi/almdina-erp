(() => {
    "use strict";

    if (window.AlmdinaWorkspaceSyncCoordinator) return;

    const DOCTYPE = "Door Cutting Order";
    const ACTIVATION_CLEANUP_KEY = "workspace-sync-tab-activation";
    const resources = new Map();

    function normalizeNames(value) {
        const source = Array.isArray(value) ? value : [value];
        return [...new Set(source.map((name) => String(name || "").trim()).filter(Boolean))];
    }

    function formIdentity(frm) {
        const context = window.AlmdinaDocumentContext;
        if (context && typeof context.formIdentity === "function") {
            return context.formIdentity(frm);
        }
        if (!frm || !frm.doc) return "";
        return `${frm.doctype || frm.doc.doctype || ""}::${frm.doc.name || "__new__"}`;
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

    function register(name, descriptor) {
        const normalized = String(name || "").trim();
        if (!normalized || !descriptor) return false;
        resources.set(normalized, Object.freeze({ ...descriptor }));
        return true;
    }

    function descriptorFor(name) {
        return resources.get(String(name || "").trim()) || null;
    }

    function activationField(descriptor) {
        return String(descriptor && descriptor.activationField || "").trim();
    }

    function descriptorIsActive(frm, descriptor) {
        const fieldname = activationField(descriptor);
        if (!fieldname) return true;
        return currentTabFieldname(frm) === fieldname;
    }

    function isActive(frm, name) {
        const descriptor = descriptorFor(name);
        return Boolean(descriptor && descriptorIsActive(frm, descriptor));
    }

    function activeResourceNames(frm) {
        const names = [];
        resources.forEach((descriptor, name) => {
            if (!activationField(descriptor)) return;
            if (descriptorIsActive(frm, descriptor)) names.push(name);
        });
        return names;
    }

    function activationFields() {
        const fields = new Set();
        resources.forEach((descriptor) => {
            const fieldname = activationField(descriptor);
            if (fieldname) fields.add(fieldname);
        });
        return fields;
    }

    function dispatch(frm, detail) {
        window.dispatchEvent(new CustomEvent("almdina:workspace-freshness-changed", {
            detail: {
                identity: formIdentity(frm),
                orderName: frm && frm.doc ? frm.doc.name : null,
                ...(detail || {}),
            },
        }));
    }

    function dispatchActivation(frm, names) {
        window.dispatchEvent(new CustomEvent("almdina:workspace-activated", {
            detail: {
                frm,
                identity: formIdentity(frm),
                orderName: frm && frm.doc ? frm.doc.name : null,
                resources: normalizeNames(names),
            },
        }));
    }

    function invalidate(frm, names, reason = "dependency_changed") {
        const affected = [];
        normalizeNames(names).forEach((name) => {
            const descriptor = descriptorFor(name);
            if (!descriptor || typeof descriptor.invalidate !== "function") return;
            const result = descriptor.invalidate(frm, reason);
            if (result !== false) affected.push(name);
        });
        if (affected.length) {
            dispatch(frm, {
                action: "invalidate",
                resources: affected,
                reason: String(reason || "dependency_changed"),
            });
        }
        return affected;
    }

    async function refresh(frm, names, options = {}) {
        const refreshed = [];
        // Deliberately preserve caller order. Cost can depend on the canonical Plan,
        // so Plan -> Cost refreshes must not race each other through Promise.all().
        for (const name of normalizeNames(names)) {
            const descriptor = descriptorFor(name);
            if (!descriptor || typeof descriptor.load !== "function") continue;
            if (options.activeOnly === true && !descriptorIsActive(frm, descriptor)) {
                continue;
            }
            if (
                typeof descriptor.canLoad === "function"
                && !descriptor.canLoad(frm)
            ) {
                continue;
            }
            await descriptor.load(frm, { force: options.force !== false });
            refreshed.push(name);
        }
        if (refreshed.length) {
            dispatch(frm, {
                action: "refresh",
                resources: refreshed,
                reason: String(options.reason || "canonical_reload"),
            });
        }
        return refreshed;
    }

    async function activateCurrent(frm, options = {}) {
        if (!frm || !frm.doc || frm.doctype !== DOCTYPE) return [];
        const names = activeResourceNames(frm);
        if (!names.length) return [];

        // Surface owners can start their lightweight skeleton/module work in
        // parallel with the canonical data read. The workspace store remains the
        // only mutable owner and presenters remain render-only.
        dispatchActivation(frm, names);

        const loaded = [];
        for (const name of names) {
            const descriptor = descriptorFor(name);
            if (!descriptor || typeof descriptor.load !== "function") continue;
            if (
                typeof descriptor.canLoad === "function"
                && !descriptor.canLoad(frm)
            ) {
                continue;
            }
            await descriptor.load(frm, { force: options.force === true });
            loaded.push(name);
        }
        return loaded;
    }

    function scheduleActivation(frm, options = {}) {
        if (!frm || !frm.doc || frm.doctype !== DOCTYPE) return null;
        const context = window.AlmdinaDocumentContext;
        const run = () => {
            activateCurrent(frm, options).catch((error) => {
                console.error("DCO active workspace load failed", error);
            });
        };
        if (context && typeof context.scheduleFrame === "function") {
            return context.scheduleFrame(frm, "workspace-sync-active-tab", run);
        }
        return window.requestAnimationFrame(run);
    }

    function installActivationListener(frm) {
        if (!frm || !frm.doc || frm.doctype !== DOCTYPE) return false;
        const root = formRoot(frm);
        if (!root || typeof root.addEventListener !== "function") return false;
        if (frm.__almdinaWorkspaceActivationRoot === root && frm.__almdinaWorkspaceActivationHandler) {
            return true;
        }

        const previousRoot = frm.__almdinaWorkspaceActivationRoot;
        const previousHandler = frm.__almdinaWorkspaceActivationHandler;
        if (previousRoot && previousHandler && typeof previousRoot.removeEventListener === "function") {
            previousRoot.removeEventListener("click", previousHandler);
        }

        const handler = (event) => {
            const target = event && event.target && typeof event.target.closest === "function"
                ? event.target.closest("[data-fieldname]")
                : null;
            const fieldname = String(target && target.getAttribute("data-fieldname") || "");
            if (!fieldname || !activationFields().has(fieldname)) return;
            // Let Frappe finish switching current_tab first, then resolve the one
            // workspace that became visible. Keyboard activation also emits click.
            scheduleActivation(frm);
        };
        root.addEventListener("click", handler);
        frm.__almdinaWorkspaceActivationRoot = root;
        frm.__almdinaWorkspaceActivationHandler = handler;

        const context = window.AlmdinaDocumentContext;
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

    function documentIsDirty(frm) {
        return Boolean(frm && frm.is_dirty && frm.is_dirty());
    }

    function syncDocumentModified(frm, modified, options = {}) {
        const normalized = String(modified || "").trim();
        if (!frm || !frm.doc || !normalized) return false;
        if (documentIsDirty(frm) && !options.allowWhileDirty) {
            // Never hide a real optimistic-concurrency conflict. Keep the newer
            // server version visible to the caller, but do not advance the form's
            // write token while unrelated local changes still exist.
            frm.__almdina_pending_server_modified = normalized;
            return false;
        }
        frm.doc.modified = normalized;
        frm.__almdina_pending_server_modified = null;
        return true;
    }

    async function reconcile(frm, effects = {}, options = {}) {
        const changed = normalizeNames(effects.changed || effects.refresh || []);
        const invalidated = normalizeNames(effects.invalidated || []);
        const reason = String(effects.reason || options.reason || "mutation_completed");
        const modified = effects.document_modified || effects.order_modified || effects.modified;

        if (modified) syncDocumentModified(frm, modified, options);
        if (invalidated.length) invalidate(frm, invalidated, reason);
        if (changed.length) {
            invalidate(frm, changed, reason);
            await refresh(frm, changed, {
                force: true,
                activeOnly: options.activeOnly === true,
                reason,
            });
        }
        return {
            changed,
            invalidated,
            documentModifiedSynced: Boolean(modified && String(frm && frm.doc && frm.doc.modified || "") === String(modified)),
        };
    }

    function snapshot(frm, name) {
        const descriptor = descriptorFor(name);
        return descriptor && typeof descriptor.snapshot === "function"
            ? descriptor.snapshot(frm)
            : null;
    }

    window.AlmdinaWorkspaceSyncCoordinator = Object.freeze({
        register,
        invalidate,
        refresh,
        reconcile,
        syncDocumentModified,
        snapshot,
        isActive,
        activeResourceNames,
        activateCurrent,
        scheduleActivation,
        installActivationListener,
    });

    frappe.ui.form.on(DOCTYPE, {
        onload_post_render(frm) {
            installActivationListener(frm);
            scheduleActivation(frm);
        },
        refresh(frm) {
            installActivationListener(frm);
            scheduleActivation(frm);
        },
    });

    window.addEventListener("almdina:permissions-updated", () => {
        const frm = window.cur_frm;
        if (frm && frm.doctype === DOCTYPE) scheduleActivation(frm, { force: true });
    });
})();
