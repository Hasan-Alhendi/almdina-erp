(() => {
    "use strict";

    if (window.AlmdinaFactoryPermissionsApi) return;

    const METHODS = Object.freeze({
        console: "almdina_erp.almdina_erp.services.permission_management_service.get_permission_console",
        role: "almdina_erp.almdina_erp.services.permission_management_service.get_role_permissions",
        preview: "almdina_erp.almdina_erp.services.permission_management_service.preview_role_permissions",
        export: "almdina_erp.almdina_erp.services.permission_management_service.export_role_permissions",
        import: "almdina_erp.almdina_erp.services.permission_management_service.preview_permission_import",
        update: "almdina_erp.almdina_erp.services.permission_management_service.update_role_permissions",
    });

    function foundation() {
        const api = window.AlmdinaFrontend;
        if (!api || typeof api.rpc !== "function") {
            throw new Error("Almdina frontend foundation is unavailable");
        }
        return api;
    }

    function request(method, args = {}, options = {}) {
        return foundation().rpc(method, args, options);
    }

    function getConsole(options = {}) {
        return request(METHODS.console, {}, options);
    }

    function getRole(role, options = {}) {
        return request(METHODS.role, { role }, options);
    }

    function previewRole(role, capabilities, options = {}) {
        return request(
            METHODS.preview,
            { role, capabilities: JSON.stringify(capabilities || {}) },
            options
        );
    }

    function exportRole(role, options = {}) {
        return request(METHODS.export, { role }, options);
    }

    function previewImport(role, payload, options = {}) {
        return request(METHODS.import, { role, payload }, options);
    }

    function updateRole(role, capabilities, confirmSelfLockout, options = {}) {
        return request(
            METHODS.update,
            {
                role,
                capabilities: JSON.stringify(capabilities || {}),
                confirm_self_lockout: confirmSelfLockout ? 1 : 0,
            },
            options
        );
    }

    window.AlmdinaFactoryPermissionsApi = Object.freeze({
        getConsole,
        getRole,
        previewRole,
        exportRole,
        previewImport,
        updateRole,
    });
})();
