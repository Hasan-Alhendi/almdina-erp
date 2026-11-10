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
        $body.on(`click${EVENT_NAMESPACE}`, "[data-aps-tab]", event => {
            event.preventDefault();
            const tab = String(event.currentTarget.dataset.apsTab || "");
            if (callbacks.onSelectTab) callbacks.onSelectTab(tab);
        });
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
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-cnc-preset-manage", event => {
            event.preventDefault();
            if (callbacks.onManageToolPresets) callbacks.onManageToolPresets();
        });
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-cnc-preset-add", event => {
            event.preventDefault();
            if (callbacks.onAddToolPreset) callbacks.onAddToolPreset();
        });
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-cnc-artcam-edit", event => {
            event.preventDefault();
            const name = String(event.currentTarget.dataset.presetName || "");
            if (callbacks.onEditArtcamTool) callbacks.onEditArtcamTool(name);
        });
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-cnc-tool-delete", event => {
            event.preventDefault();
            const name = String(event.currentTarget.dataset.presetName || "");
            if (callbacks.onDeleteToolPreset) callbacks.onDeleteToolPreset(name);
        });
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-cnc-machine-manage", event => {
            event.preventDefault();
            if (callbacks.onManageCncMachines) callbacks.onManageCncMachines();
        });
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-cnc-machine-add", event => {
            event.preventDefault();
            if (callbacks.onAddCncMachine) callbacks.onAddCncMachine();
        });
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-cnc-profile-add", event => {
            event.preventDefault();
            if (callbacks.onAddMachiningProfile) callbacks.onAddMachiningProfile();
        });
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-cnc-profile-edit", event => {
            event.preventDefault();
            const profileId = String(event.currentTarget.dataset.profileId || "");
            if (callbacks.onEditMachiningProfile) callbacks.onEditMachiningProfile(profileId);
        });
        lifecycle.track(() => $body.off(EVENT_NAMESPACE), "production-settings-interactions");
        return true;
    }

    window.AlmdinaFactoryProductionSettingsInteractions = Object.freeze({
        EVENT_NAMESPACE,
        bind,
    });
})();
