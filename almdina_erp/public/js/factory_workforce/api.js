(() => {
    "use strict";

    if (window.AlmdinaFactoryWorkforceApi) return;

    const BASE = "almdina_erp.almdina_erp.services.workforce_service";
    const METHODS = Object.freeze({
        console: `${BASE}.get_workforce_console`,
        create: `${BASE}.create_workforce_user`,
        adopt: `${BASE}.adopt_workforce_user`,
        update: `${BASE}.update_workforce_user`,
        password: `${BASE}.reset_workforce_password`,
        enabled: `${BASE}.set_workforce_user_enabled`,
        audit: `${BASE}.get_workforce_user_audit`,
    });

    function foundation() {
        const api = window.AlmdinaFrontend;
        if (!api || typeof api.rpc !== "function") {
            throw new Error("Almdina frontend foundation is unavailable");
        }
        return api;
    }

    function request(method, args = {}, options = {}) {
        return foundation().rpc(method, args, options).then(message => message || {});
    }

    function getConsole(search, enabled, options = {}) {
        return request(METHODS.console, {
            search: String(search || ""),
            enabled: String(enabled || "all"),
            limit: 150,
        }, options);
    }

    function createUser(data, options = {}) {
        return request(METHODS.create, { data: data || {} }, options);
    }

    function adoptUser(user, options = {}) {
        return request(METHODS.adopt, { user }, options);
    }

    function updateUser(user, data, options = {}) {
        return request(METHODS.update, { user, data: data || {} }, options);
    }

    function resetPassword(user, temporaryPassword, options = {}) {
        return request(METHODS.password, {
            user,
            temporary_password: temporaryPassword,
        }, options);
    }

    function setEnabled(user, enabled, options = {}) {
        return request(METHODS.enabled, { user, enabled: enabled ? 1 : 0 }, options);
    }

    function getAudit(user, options = {}) {
        return request(METHODS.audit, { user, limit: 30 }, options);
    }

    window.AlmdinaFactoryWorkforceApi = Object.freeze({
        getConsole,
        createUser,
        adoptUser,
        updateUser,
        resetPassword,
        setEnabled,
        getAudit,
    });
})();
