(() => {
    "use strict";

    if (window.AlmdinaFactoryProductionSettingsCncPresets) return;

    function attach(options = {}) {
        const api = options.api;
        const dialogs = options.dialogs;
        const translate = options.translate;
        const freezeOptions = options.freezeOptions;
        const editable = options.editable;
        const presets = options.presets;
        const reload = options.reload;
        if (!api || !dialogs || typeof translate !== "function" || typeof reload !== "function") {
            throw new Error("CNC tool preset dependencies are unavailable");
        }

        function currentPreset(name) {
            const rows = typeof presets === "function" ? presets() : [];
            return (rows || []).find(row => row && row.name === name) || null;
        }

        function afterSave(data) {
            return reload().then(() => data);
        }

        function open(name) {
            if (typeof editable === "function" && !editable()) return null;
            const preset = name ? currentPreset(name) : null;
            return dialogs.openToolPreset({
                preset,
                onSubmit: values => api.saveCncToolPreset(
                    values,
                    typeof freezeOptions === "function" ? freezeOptions(translate("Saving tool preset...")) : {}
                ).then(afterSave),
            });
        }

        function setEnabled(name, enabled) {
            if (typeof editable === "function" && !editable()) return Promise.resolve(null);
            return api.setCncToolPresetEnabled(
                name,
                enabled,
                typeof freezeOptions === "function" ? freezeOptions(translate("Saving tool preset...")) : {}
            ).then(afterSave);
        }

        function remove(name) {
            if (typeof editable === "function" && !editable()) return Promise.resolve(null);
            const preset = currentPreset(name);
            const label = preset && (preset.preset_name || preset.name) || name;
            const confirmed = window.frappe && typeof frappe.confirm === "function"
                ? new Promise(resolve => {
                    frappe.confirm(translate("Delete the unused tool preset {0}?", [label]), () => resolve(true), () => resolve(false));
                })
                : Promise.resolve(true);
            return confirmed.then(accepted => {
                if (!accepted) return null;
                return api.deleteCncToolPreset(
                    name,
                    typeof freezeOptions === "function" ? freezeOptions(translate("Deleting tool preset...")) : {}
                ).then(afterSave);
            });
        }

        return Object.freeze({ open, setEnabled, remove });
    }

    window.AlmdinaFactoryProductionSettingsCncPresets = Object.freeze({ attach });
})();
