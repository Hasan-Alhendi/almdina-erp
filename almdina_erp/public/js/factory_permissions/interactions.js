(() => {
    "use strict";

    if (window.AlmdinaFactoryPermissionsInteractions) return;

    const EVENT_NAMESPACE = ".almdinaFactoryPermissions";

    function bind(options = {}) {
        const $main = options.$main;
        const lifecycle = options.lifecycle;
        const renderer = options.renderer;
        const callbacks = options.callbacks || {};
        if (!$main || !lifecycle || !renderer) {
            throw new Error("Factory permissions interaction dependencies are unavailable");
        }

        $main.off(EVENT_NAMESPACE);
        $(document).off(EVENT_NAMESPACE);

        $main.on(`focus${EVENT_NAMESPACE} input${EVENT_NAMESPACE}`, ".apc-role-picker", function () {
            callbacks.onRoleQuery(String($(this).val() || ""));
            renderer.openRoleMenu();
        });

        $main.on(`keydown${EVENT_NAMESPACE}`, ".apc-role-picker", event => {
            const $options = $main.find(".apc-role-option");
            if (event.key === "Escape") {
                callbacks.onRoleMenuClose(true);
                return;
            }
            if (event.key === "Enter") {
                const $active = $options.filter(".is-active").first();
                const $target = $active.length ? $active : $options.first();
                if ($target.length) {
                    event.preventDefault();
                    callbacks.onRoleSelected(String($target.attr("data-role") || ""));
                }
                return;
            }
            if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
            event.preventDefault();
            if (!$options.length) return;
            let index = $options.index($options.filter(".is-active").first());
            if (event.key === "ArrowDown") index = Math.min($options.length - 1, index + 1);
            else index = index <= 0 ? 0 : index - 1;
            $options.removeClass("is-active").eq(index).addClass("is-active").get(0).scrollIntoView({ block: "nearest" });
        });

        $main.on(`click${EVENT_NAMESPACE}`, ".apc-role-toggle", () => {
            const $menu = $main.find(".apc-role-menu");
            if ($menu.prop("hidden")) {
                callbacks.onRoleQuery("");
                renderer.openRoleMenu();
                $main.find(".apc-role-picker").trigger("focus");
            } else {
                callbacks.onRoleMenuClose(true);
            }
        });

        $main.on(`click${EVENT_NAMESPACE}`, ".apc-role-option", function () {
            callbacks.onRoleSelected(String($(this).attr("data-role") || ""));
        });

        $(document).on(`mousedown${EVENT_NAMESPACE}`, event => {
            if (!$(event.target).closest(".apc-role-combo").length) callbacks.onRoleMenuClose(true);
        });

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
        $main.on(`click${EVENT_NAMESPACE}`, ".apc-import", () => $main.find(".apc-import-file").trigger("click"));
        $main.on(`change${EVENT_NAMESPACE}`, ".apc-import-file", function () {
            const file = this.files && this.files[0];
            this.value = "";
            callbacks.onImportFile(file || null);
        });
        $main.on(`click${EVENT_NAMESPACE}`, ".apc-reset", () => callbacks.onReset());
        $main.on(`click${EVENT_NAMESPACE}`, ".apc-save", () => callbacks.onSave());

        lifecycle.track(() => $main.off(EVENT_NAMESPACE), "permissions-main-events");
        lifecycle.track(() => $(document).off(EVENT_NAMESPACE), "permissions-document-events");

        return Object.freeze({
            dispose() {
                $main.off(EVENT_NAMESPACE);
                $(document).off(EVENT_NAMESPACE);
            },
        });
    }

    window.AlmdinaFactoryPermissionsInteractions = Object.freeze({ bind });
})();
