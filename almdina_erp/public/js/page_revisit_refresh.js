(() => {
    "use strict";

    const currentApi = window.AlmdinaPageRevisit;
    if (currentApi && typeof currentApi.bindActivationLifecycle === "function") return;

    const EVENT_NAMESPACE = ".almdinaPageActivation";
    const OWNER_KEY = "__almdinaPageActivationLifecycle";

    function frappeRuntime() {
        if (window.frappe) return window.frappe;
        if (typeof frappe !== "undefined") return frappe;
        return null;
    }

    function jquery(wrapper) {
        if (typeof window.jQuery === "function") return window.jQuery(wrapper);
        if (typeof $ === "function") return $(wrapper);
        throw new Error("jQuery is required for Frappe page lifecycle events");
    }

    function isCurrentPage(wrapper) {
        const runtime = frappeRuntime();
        return Boolean(runtime && runtime.container && runtime.container.page === wrapper);
    }

    function hasVisited(wrapper) {
        return Boolean(
            wrapper
            && Object.prototype.hasOwnProperty.call(wrapper, "_route")
        );
    }

    function invoke(callback, label, context) {
        if (typeof callback !== "function") return;
        try {
            Promise.resolve(callback(context)).catch(error => {
                console.error(`Failed to ${label} Almdina page`, error);
            });
        } catch (error) {
            console.error(`Failed to ${label} Almdina page`, error);
        }
    }

    // Frappe keeps Desk page DOM mounted and only emits jQuery show/hide events
    // while navigating. This owner therefore separates the long-lived controller
    // mount from each active visit without disposing feature state on every hide.
    function bindActivationLifecycle(wrapper, callbacks = {}) {
        if (!wrapper) return null;

        const previous = wrapper[OWNER_KEY];
        if (previous && typeof previous.dispose === "function") previous.dispose();

        const $wrapper = jquery(wrapper);
        let disposed = false;
        let active = isCurrentPage(wrapper);
        let generation = active ? 1 : 0;

        function context() {
            return Object.freeze({ active, generation });
        }

        function activate() {
            if (disposed || active) return false;
            active = true;
            generation += 1;
            invoke(callbacks.onActivate, "activate", context());
            return true;
        }

        function deactivate() {
            if (disposed || !active) return false;
            active = false;
            generation += 1;
            invoke(callbacks.onDeactivate, "deactivate", context());
            return true;
        }

        function dispose() {
            if (disposed) return false;
            const wasActive = active;
            disposed = true;
            active = false;
            generation += 1;
            $wrapper.off(EVENT_NAMESPACE);
            if (wrapper[OWNER_KEY] === lifecycle) wrapper[OWNER_KEY] = null;
            if (wasActive) invoke(callbacks.onDeactivate, "deactivate", context());
            return true;
        }

        const lifecycle = Object.freeze({
            activate,
            deactivate,
            dispose,
            isActive: () => active && !disposed,
            isDisposed: () => disposed,
            generation: () => generation,
        });

        wrapper[OWNER_KEY] = lifecycle;
        $wrapper.off(EVENT_NAMESPACE);
        $wrapper.on(`show${EVENT_NAMESPACE}`, activate);
        $wrapper.on(`hide${EVENT_NAMESPACE}`, deactivate);
        return lifecycle;
    }

    // Frappe builds a desk page once and keeps its DOM alive for the rest of the
    // session. Every later visit only fires "show", so a page that fetches its
    // data inside `on_page_load` keeps presenting the first visit's snapshot
    // until the browser is reloaded. Pages register their loader here to reload
    // whenever the user comes back.
    function refreshOnRevisit(wrapper, reload) {
        if (!wrapper || typeof reload !== "function") return false;

        // `_route` is assigned by Frappe before it emits show. It records a visit
        // even when an async page bootstrap did not install this helper in time,
        // so the next show is correctly treated as a revisit rather than skipped.
        let initialVisitConsumed = hasVisited(wrapper);
        const lifecycle = bindActivationLifecycle(wrapper, {
            onActivate() {
                if (!initialVisitConsumed) {
                    initialVisitConsumed = true;
                    return;
                }
                invoke(reload, "refresh", { active: true, generation: lifecycle.generation() });
            },
        });
        if (!lifecycle) return false;
        if (lifecycle.isActive()) initialVisitConsumed = true;

        return true;
    }

    window.AlmdinaPageRevisit = Object.freeze({
        bindActivationLifecycle,
        refreshOnRevisit,
    });
})();
