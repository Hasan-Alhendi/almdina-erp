(() => {
    "use strict";

    if (window.AlmdinaFactoryPermissionsInteractions) return;

    const EVENT_NAMESPACE = ".almdinaFactoryPermissions";

    function bind(options = {}) {
        const $main = options.$main;
        const lifecycle = options.lifecycle;
        const callbacks = options.callbacks || {};
        if (!$main || !lifecycle) {
            throw new Error("Factory permissions interaction dependencies are unavailable");
        }

        $main.off(EVENT_NAMESPACE);

        $main.on(`change${EVENT_NAMESPACE}`, ".apc-capability-input", function () {
            callbacks.onCapabilityChanged(
                String($(this).attr("data-capability") || ""),
                $(this).is(":checked")
            );
        });
        $main.on(`click${EVENT_NAMESPACE}`, ".apc-select-all-group", function () {
            callbacks.onGroupToggle(String($(this).attr("data-group") || ""));
        });
        $main.on(`click${EVENT_NAMESPACE}`, ".apc-select-all-global", () => callbacks.onGlobalToggle());
        $main.on(`click${EVENT_NAMESPACE}`, ".apc-export", () => callbacks.onExport());
        $main.on(`click${EVENT_NAMESPACE}`, ".apc-import", () => {
            if (callbacks.onImport) callbacks.onImport();
        });
        $main.on(`click${EVENT_NAMESPACE}`, ".apc-reset", () => callbacks.onReset());
        $main.on(`click${EVENT_NAMESPACE}`, ".apc-save", () => callbacks.onSave());

        lifecycle.track(() => $main.off(EVENT_NAMESPACE), "permissions-main-events");

        return Object.freeze({
            dispose() {
                $main.off(EVENT_NAMESPACE);
            },
        });
    }

    window.AlmdinaFactoryPermissionsInteractions = Object.freeze({ bind });
})();
