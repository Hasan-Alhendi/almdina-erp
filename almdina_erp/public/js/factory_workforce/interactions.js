(() => {
    "use strict";

    if (window.AlmdinaFactoryWorkforceInteractions) return;

    const EVENT_NAMESPACE = ".almdinaFactoryWorkforce";

    function bind(options = {}) {
        const $main = options.$main;
        const lifecycle = options.lifecycle;
        const callbacks = options.callbacks || {};
        if (!$main || !lifecycle || typeof lifecycle.track !== "function") {
            throw new Error("Factory workforce interaction dependencies are unavailable");
        }

        $main.off(EVENT_NAMESPACE);

        $main.on(`input${EVENT_NAMESPACE}`, ".aw-search", event => {
            const value = String(event.currentTarget.value || "").trim();
            lifecycle.timeout(
                () => callbacks.onSearch && callbacks.onSearch(value),
                350,
                "workforce-search"
            );
        });

        $main.on(`change${EVENT_NAMESPACE}`, ".aw-enabled-filter", event => {
            if (callbacks.onEnabledChanged) {
                callbacks.onEnabledChanged(String(event.currentTarget.value || "all"));
            }
        });

        $main.on(`click${EVENT_NAMESPACE}`, ".aw-refresh", () => {
            if (callbacks.onRefresh) callbacks.onRefresh();
        });
        $main.on(`click${EVENT_NAMESPACE}`, ".aw-edit", event => {
            if (callbacks.onEdit) callbacks.onEdit(String(event.currentTarget.dataset.user || ""));
        });
        $main.on(`click${EVENT_NAMESPACE}`, ".aw-password", event => {
            if (callbacks.onPassword) callbacks.onPassword(String(event.currentTarget.dataset.user || ""));
        });
        $main.on(`click${EVENT_NAMESPACE}`, ".aw-toggle", event => {
            if (callbacks.onToggle) {
                callbacks.onToggle(
                    String(event.currentTarget.dataset.user || ""),
                    event.currentTarget.dataset.enabled === "1"
                );
            }
        });
        $main.on(`click${EVENT_NAMESPACE}`, ".aw-audit-open", event => {
            if (callbacks.onAudit) callbacks.onAudit(String(event.currentTarget.dataset.user || ""));
        });
        $main.on(`click${EVENT_NAMESPACE}`, ".aw-adopt-user", event => {
            if (callbacks.onAdopt) callbacks.onAdopt(String(event.currentTarget.dataset.user || ""));
        });

        lifecycle.track(() => $main.off(EVENT_NAMESPACE), "workforce-interactions");
        return true;
    }

    window.AlmdinaFactoryWorkforceInteractions = Object.freeze({
        EVENT_NAMESPACE,
        bind,
    });
})();
