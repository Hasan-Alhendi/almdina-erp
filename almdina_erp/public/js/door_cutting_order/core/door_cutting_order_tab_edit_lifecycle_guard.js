(() => {
    "use strict";

    if (window.AlmdinaDcoTabEditLifecycleGuard) return;

    const DOCTYPE = "Door Cutting Order";
    const GUARDED_TABS = new Set(["order_tab", "results_tab", "cost_tab"]);
    const KIND_TAB = Object.freeze({
        order: "order_tab",
        plan: "results_tab",
        cost: "cost_tab",
    });
    const STATE_KEY = "__almdinaTabEditLifecycleGuard";
    const CLEANUP_KEY = "tab-edit-lifecycle-guard";
    const RECONCILING_KEY = "__almdinaTabEditLifecycleReconciling";
    const LEGACY_ROOT_KEY = "__almdinaPageEditTabListenerRoot";
    const LEGACY_HANDLER_KEY = "__almdinaPageEditTabListenerHandler";
    const LOCK_CLASS = "dco-edit-navigation-locked";
    const LOCK_TITLE = "احفظ أو ألغِ التعديل الحالي قبل الانتقال إلى قسم آخر.";

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function editSessionCoordinator() {
        return window.AlmdinaDcoEditSessionCoordinator || null;
    }

    function isOrderForm(frm) {
        return Boolean(frm && frm.doc && frm.doctype === DOCTYPE);
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

    function sessionTabFieldname(frm) {
        return KIND_TAB[activeEditingKind(frm)] || null;
    }

    function shouldBlock(frm, targetFieldname) {
        if (!GUARDED_TABS.has(targetFieldname)) return false;
        const ownerTabFieldname = sessionTabFieldname(frm);
        if (!ownerTabFieldname) return false;
        return targetFieldname !== ownerTabFieldname;
    }

    function showOpenEditMessage() {
        frappe.msgprint({
            title: __("التعديل ما زال مفتوحًا"),
            message: __(LOCK_TITLE),
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

    function tabLinkControl(tab) {
        const container = tab && tab.tab_link;
        if (!container || typeof container.find !== "function") return null;
        const control = container.find(".nav-link[data-fieldname]");
        return control && control.length ? control : null;
    }

    function attributeSnapshot(control, name) {
        const value = control && typeof control.attr === "function"
            ? control.attr(name)
            : undefined;
        return Object.freeze({
            present: value !== undefined && value !== null,
            value,
        });
    }

    function restoreAttribute(control, name, snapshot) {
        if (!control || !snapshot || typeof control.attr !== "function") return;
        if (snapshot.present) {
            control.attr(name, snapshot.value);
        } else if (typeof control.removeAttr === "function") {
            control.removeAttr(name);
        }
    }

    function suspendBootstrapAutoActivation(tab) {
        const control = tabLinkControl(tab);
        if (!control || typeof control.attr !== "function" || typeof control.removeAttr !== "function") {
            return Object.freeze({ control: null, hadDataToggle: false, dataToggleValue: null });
        }

        const value = control.attr("data-toggle");
        const hadDataToggle = value !== undefined && value !== null;
        if (hadDataToggle) control.removeAttr("data-toggle");
        return Object.freeze({ control, hadDataToggle, dataToggleValue: value });
    }

    function restoreBootstrapAutoActivation(binding) {
        const control = binding && binding.bootstrapControl;
        if (!control || typeof control.attr !== "function") return;
        if (binding.hadDataToggle) {
            control.attr("data-toggle", binding.dataToggleValue);
        }
    }

    function lockNavigation(binding) {
        const control = binding && binding.bootstrapControl;
        const lockState = binding && binding.lockState;
        if (!control || !lockState || lockState.locked) return;
        if (typeof control.prop !== "function" || typeof control.attr !== "function") return;

        lockState.locked = true;
        lockState.disabled = Boolean(control.prop("disabled"));
        lockState.ariaDisabled = attributeSnapshot(control, "aria-disabled");
        lockState.tabIndex = attributeSnapshot(control, "tabindex");
        lockState.title = attributeSnapshot(control, "title");
        lockState.hadDisabledClass = Boolean(
            typeof control.hasClass === "function" && control.hasClass("disabled")
        );

        control.prop("disabled", true);
        control.attr("aria-disabled", "true");
        control.attr("tabindex", "-1");
        control.attr("title", __(LOCK_TITLE));
        if (typeof control.addClass === "function") {
            control.addClass("disabled").addClass(LOCK_CLASS);
        }
    }

    function unlockNavigation(binding) {
        const control = binding && binding.bootstrapControl;
        const lockState = binding && binding.lockState;
        if (!control || !lockState || !lockState.locked) return;

        if (typeof control.prop === "function") control.prop("disabled", Boolean(lockState.disabled));
        restoreAttribute(control, "aria-disabled", lockState.ariaDisabled);
        restoreAttribute(control, "tabindex", lockState.tabIndex);
        restoreAttribute(control, "title", lockState.title);
        if (typeof control.removeClass === "function") {
            control.removeClass(LOCK_CLASS);
            if (!lockState.hadDisabledClass) control.removeClass("disabled");
        }

        lockState.locked = false;
        lockState.disabled = false;
        lockState.ariaDisabled = null;
        lockState.tabIndex = null;
        lockState.title = null;
        lockState.hadDisabledClass = false;
    }

    function syncBindingLocks(frm, state) {
        const ownerTabFieldname = sessionTabFieldname(frm);
        state.bindings.forEach((binding) => {
            const locked = Boolean(
                ownerTabFieldname
                && tabFieldname(binding.tab) !== ownerTabFieldname
            );
            if (locked) lockNavigation(binding);
            else unlockNavigation(binding);
        });
        return ownerTabFieldname;
    }

    function reconcileOwnerTab(frm, state, ownerTabFieldname) {
        if (!ownerTabFieldname || frm[RECONCILING_KEY]) return false;
        const ownerBinding = state.bindings.find(
            (binding) => tabFieldname(binding.tab) === ownerTabFieldname
        );
        if (!ownerBinding) return false;

        const visualActive = typeof ownerBinding.tab.is_active === "function"
            ? ownerBinding.tab.is_active()
            : currentTabFieldname(frm) === ownerTabFieldname;
        const hostActive = currentTabFieldname(frm) === ownerTabFieldname;
        if (visualActive && hostActive) return false;

        frm[RECONCILING_KEY] = true;
        try {
            ownerBinding.guardedSetActive.call(ownerBinding.tab);
        } finally {
            frm[RECONCILING_KEY] = false;
        }
        return true;
    }

    function restoreState(frm, state) {
        if (!state || !Array.isArray(state.bindings)) return;
        state.bindings.forEach((binding) => {
            unlockNavigation(binding);
            const { tab, originalSetActive, guardedSetActive } = binding;
            if (tab && tab.set_active === guardedSetActive) {
                tab.set_active = originalSetActive;
            }
            restoreBootstrapAutoActivation(binding);
        });
        if (frm) frm[RECONCILING_KEY] = false;
        if (frm && frm[STATE_KEY] === state) frm[STATE_KEY] = null;
    }

    function sameInstallation(state, tabs) {
        if (!state || !Array.isArray(state.bindings)) return false;
        if (state.bindings.length !== tabs.length) return false;
        return state.bindings.every((binding, index) => (
            binding.tab === tabs[index]
            && binding.tab.set_active === binding.guardedSetActive
        ));
    }

    function syncNavigationLock(frm) {
        if (!isOrderForm(frm)) return false;
        const state = frm[STATE_KEY];
        if (!state || !Array.isArray(state.bindings)) return install(frm);
        const ownerTabFieldname = syncBindingLocks(frm, state);
        reconcileOwnerTab(frm, state, ownerTabFieldname);
        return true;
    }

    function install(frm) {
        if (!isOrderForm(frm)) return false;

        // Retire the historical DOM interceptor. Frappe's own click listener calls
        // Tab.set_active(), which remains the semantic programmatic boundary below.
        // Bootstrap's data-api path is also disabled on these buttons. During an
        // active edit, native button.disabled then closes the user-click path before
        // any framework listener can run.
        retireLegacyClickGuard(frm);

        const tabs = topLevelTabs(frm);
        if (!tabs.length) return false;

        const previous = frm[STATE_KEY];
        if (sameInstallation(previous, tabs)) {
            const ownerTabFieldname = syncBindingLocks(frm, previous);
            reconcileOwnerTab(frm, previous, ownerTabFieldname);
            return true;
        }
        if (previous) restoreState(frm, previous);

        const bindings = tabs
            .filter((tab) => typeof tab.set_active === "function")
            .map((tab) => {
                const targetFieldname = tabFieldname(tab);
                const originalSetActive = tab.set_active;
                const bootstrap = suspendBootstrapAutoActivation(tab);
                const binding = {
                    tab,
                    originalSetActive,
                    guardedSetActive: null,
                    bootstrapControl: bootstrap.control,
                    hadDataToggle: bootstrap.hadDataToggle,
                    dataToggleValue: bootstrap.dataToggleValue,
                    lockState: {
                        locked: false,
                        disabled: false,
                        ariaDisabled: null,
                        tabIndex: null,
                        title: null,
                        hadDisabledClass: false,
                    },
                };
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
                binding.guardedSetActive = guardedSetActive;
                tab.set_active = guardedSetActive;
                return binding;
            });

        if (!bindings.length) return false;
        const state = Object.freeze({ bindings: Object.freeze(bindings) });
        frm[STATE_KEY] = state;

        const context = documentContext();
        if (context && typeof context.registerCleanup === "function") {
            context.registerCleanup(frm, CLEANUP_KEY, () => restoreState(frm, state));
        }

        const ownerTabFieldname = syncBindingLocks(frm, state);
        reconcileOwnerTab(frm, state, ownerTabFieldname);
        return true;
    }

    function refresh(frm) {
        install(frm);
    }

    frappe.ui.form.on(DOCTYPE, {
        onload_post_render(frm) { refresh(frm); },
        refresh(frm) { refresh(frm); },
        almdina_edit_session_changed(frm) { syncNavigationLock(frm); },
        on_tab_change(frm) {
            if (!frm[RECONCILING_KEY]) syncNavigationLock(frm);
        },
    });

    window.AlmdinaDcoTabEditLifecycleGuard = Object.freeze({
        activeEditingKind,
        currentTabFieldname,
        install,
        retireLegacyClickGuard,
        sessionTabFieldname,
        shouldBlock,
        suspendBootstrapAutoActivation,
        syncNavigationLock,
        topLevelTabs,
    });
})();
