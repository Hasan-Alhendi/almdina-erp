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
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-whatsapp-create", event => {
            event.preventDefault();
            if (callbacks.onCreateWhatsApp) callbacks.onCreateWhatsApp();
        });
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-whatsapp-reconnect", event => {
            event.preventDefault();
            if (callbacks.onReconnectWhatsApp) callbacks.onReconnectWhatsApp();
        });
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-cnc-preset-add", event => {
            event.preventDefault();
            if (callbacks.onAddToolPreset) callbacks.onAddToolPreset();
        });
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-cnc-preset-edit", event => {
            event.preventDefault();
            if (callbacks.onEditToolPreset) callbacks.onEditToolPreset(event.currentTarget.dataset.preset || "");
        });
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-cnc-preset-enabled", event => {
            event.preventDefault();
            if (callbacks.onSetToolPresetEnabled) {
                callbacks.onSetToolPresetEnabled(
                    event.currentTarget.dataset.preset || "",
                    event.currentTarget.dataset.enabled === "1"
                );
            }
        });
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-cnc-preset-delete", event => {
            event.preventDefault();
            if (callbacks.onDeleteToolPreset) callbacks.onDeleteToolPreset(event.currentTarget.dataset.preset || "");
        });
        lifecycle.track(() => $body.off(EVENT_NAMESPACE), "production-settings-interactions");
        return true;
    }

    window.AlmdinaFactoryProductionSettingsInteractions = Object.freeze({
        EVENT_NAMESPACE,
        bind,
    });
})();
