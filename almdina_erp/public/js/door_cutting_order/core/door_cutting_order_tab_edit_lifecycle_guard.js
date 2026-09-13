(() => {
    "use strict";

    if (window.AlmdinaDcoTabEditLifecycleGuard) return;

    const DOCTYPE = "Door Cutting Order";
    const GUARDED_TABS = new Set(["order_tab", "results_tab", "cost_tab"]);
    const STATE_KEY = "__almdinaTabEditLifecycleGuard";
    const CLEANUP_KEY = "tab-edit-lifecycle-guard";
    const LEGACY_ROOT_KEY = "__almdinaPageEditTabListenerRoot";
    const LEGACY_HANDLER_KEY = "__almdinaPageEditTabListenerHandler";

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function editSessionCoordinator() {
        return window.AlmdinaDcoEditSessionCoordinator || null;
    }

    function isOrderForm(frm) {
        return Boolean(frm && frm.doc && frm.doctype === DOCTYPE);
    }

    function formRoot(frm) {
        const wrapper = frm && frm.wrapper;
        return wrapper && (wrapper.nodeType ? wrapper : wrapper[0]);
    }

    function tabFieldname(tab) {
        return String(tab && tab.df && tab.df.fieldname || "").trim();
    }

    function topLevelTabs(frm) {
        const tabs = frm && frm.layout && Array.isArray(frm.layout.tabs)
            ? frm.layout.tabs
            : [];
        return tabs.filter((tab) => GUARDED_TABS.has(tabFieldname(tab)));
    }

    function currentTabFieldname(frm) {
        const active = frm && typeof frm.get_active_tab === "function"
            ? frm.get_active_tab()
            : null;
        const activeFieldname = tabFieldname(active);
        if (GUARDED_TABS.has(activeFieldname)) return activeFieldname;

        const activeLayoutTab = topLevelTabs(frm).find((tab) => (
            typeof tab.is_active === "function" && tab.is_active()
        ));
        const fallback = tabFieldname(activeLayoutTab);
        return GUARDED_TABS.has(fallback) ? fallback : "order_tab";
    }

    function activeEditingKind(frm) {
        const owner = editSessionCoordinator();
        return owner && typeof owner.activeKind === "function"
            ? owner.activeKind(frm)
            : null;
    }

    function shouldBlock(frm, targetFieldname) {
        if (!GUARDED_TABS.has(targetFieldname)) return false;
        const editingKind = activeEditingKind(frm);
        if (!editingKind) return false;
        return targetFieldname !== currentTabFieldname(frm);
    }

    function showOpenEditMessage() {
        frappe.msgprint({
            title: __("التعديل ما زال مفتوحًا"),
            message: __("احفظ أو ألغِ التعديل الحالي قبل الانتقال إلى قسم آخر."),
            indicator: "orange",
        });
    }

    function retireLegacyClickGuard(frm) {
        if (!frm) return;
        const root = frm[LEGACY_ROOT_KEY];
        const handler = frm[LEGACY_HANDLER_KEY];
        if (root && handler && typeof root.removeEventListener === "function") {
            root.removeEventListener("click", handler, true);
        }
        frm[LEGACY_ROOT_KEY] = null;
        frm[LEGACY_HANDLER_KEY] = null;
    }

    function targetTabFieldname(event) {
        const target = event && event.target;
        const tabLink = target && typeof target.closest === "function"
            ? target.closest(".nav-link[data-fieldname], [data-toggle=\"tab\"][data-fieldname]")
            : null;
        if (!tabLink || typeof tabLink.getAttribute !== "function") return "";
        const fieldname = String(tabLink.getAttribute("data-fieldname") || "").trim();
        return GUARDED_TABS.has(fieldname) ? fieldname : "";
    }

    function makeCaptureClickGuard(frm) {
        return function almdinaCapturedDcoTabClick(event) {
            const targetFieldname = targetTabFieldname(event);
            if (!targetFieldname || !shouldBlock(frm, targetFieldname)) return;

            if (typeof event.preventDefault === "function") event.preventDefault();
            if (typeof event.stopImmediatePropagation === "function") event.stopImmediatePropagation();
            else if (typeof event.stopPropagation === "function") event.stopPropagation();
            showOpenEditMessage();
        };
    }

    function restoreState(frm, state) {
        if (!state) return;
        if (Array.isArray(state.bindings)) {
            state.bindings.forEach(({ tab, originalSetActive, guardedSetActive }) => {
                if (tab && tab.set_active === guardedSetActive) {
                    tab.set_active = originalSetActive;
                }
            });
        }
        if (state.clickRoot && state.clickHandler && typeof state.clickRoot.removeEventListener === "function") {
            state.clickRoot.removeEventListener("click", state.clickHandler, true);
        }
        if (frm && frm[STATE_KEY] === state) frm[STATE_KEY] = null;
    }

    function sameInstallation(state, tabs, root) {
        if (!state || !Array.isArray(state.bindings)) return false;
        if (state.bindings.length !== tabs.length) return false;
        if (state.clickRoot !== root || !state.clickHandler) return false;
        return state.bindings.every((binding, index) => (
            binding.tab === tabs[index]
            && binding.tab.set_active === binding.guardedSetActive
        ));
    }

    function install(frm) {
        if (!isOrderForm(frm)) return false;

        // Retire only the historical PageEditActionUX click interceptor. This
        // lifecycle owner installs its own capture guard below so DOM/Bootstrap
        // activation and programmatic Tab.set_active() share one authority.
        retireLegacyClickGuard(frm);

        const tabs = topLevelTabs(frm);
        const root = formRoot(frm);
        if (!tabs.length || !root || typeof root.addEventListener !== "function") return false;

        const previous = frm[STATE_KEY];
        if (sameInstallation(previous, tabs, root)) return true;
        if (previous) restoreState(frm, previous);

        const bindings = tabs
            .filter((tab) => typeof tab.set_active === "function")
            .map((tab) => {
                const targetFieldname = tabFieldname(tab);
                const originalSetActive = tab.set_active;
                const guardedSetActive = function almdinaGuardedTabSetActive(...args) {
                    if (shouldBlock(frm, targetFieldname)) {
                        showOpenEditMessage();
                        return false;
                    }

                    const result = originalSetActive.apply(this, args);
                    const owner = window.AlmdinaPageEditActionUX;
                    if (owner && typeof owner.schedule === "function") {
                        owner.schedule(frm);
                    }
                    return result;
                };
                tab.set_active = guardedSetActive;
                return Object.freeze({ tab, originalSetActive, guardedSetActive });
            });

        if (!bindings.length) return false;

        const clickHandler = makeCaptureClickGuard(frm);
        root.addEventListener("click", clickHandler, true);

        const state = Object.freeze({
            bindings: Object.freeze(bindings),
            clickRoot: root,
            clickHandler,
        });

        const context = documentContext();
        if (context && typeof context.registerCleanup === "function") {
            context.registerCleanup(frm, CLEANUP_KEY, () => restoreState(frm, state));
        }
        frm[STATE_KEY] = state;
        return true;
    }

    function refresh(frm) {
        install(frm);
    }

    frappe.ui.form.on(DOCTYPE, {
        onload_post_render(frm) { refresh(frm); },
        refresh(frm) { refresh(frm); },
    });

    window.AlmdinaDcoTabEditLifecycleGuard = Object.freeze({
        activeEditingKind,
        currentTabFieldname,
        install,
        retireLegacyClickGuard,
        shouldBlock,
        targetTabFieldname,
        topLevelTabs,
    });
})();
