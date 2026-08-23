(() => {
    "use strict";

    if (window.AlmdinaFactoryProductionSettingsInteractions) return;

    const EVENT_NAMESPACE = ".almdinaFactoryProductionSettings";

    function bind(options = {}) {
        const $body = options.$body;
        const lifecycle = options.lifecycle;
        const callbacks = options.callbacks || {};
        if (!$body || !lifecycle || typeof lifecycle.track !== "function") {
            throw new Error("Production Settings interaction dependencies are unavailable");
        }

        $body.off(EVENT_NAMESPACE);
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-edit", event => {
            const section = String(event.currentTarget.dataset.section || "");
            if (callbacks.onEditSection) callbacks.onEditSection(section);
        });
        lifecycle.track(() => $body.off(EVENT_NAMESPACE), "production-settings-interactions");
        return true;
    }

    window.AlmdinaFactoryProductionSettingsInteractions = Object.freeze({
        EVENT_NAMESPACE,
        bind,
    });
})();
