(() => {
    "use strict";

    if (window.AlmdinaFactoryProductionSettingsApi) return;

    const BASE = "almdina_erp.almdina_erp.services.production_settings_service";
    const METHODS = Object.freeze({
        get: `${BASE}.get_production_settings`,
        update: `${BASE}.update_production_settings`,
        audit: `${BASE}.get_factory_settings_audit`,
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

    function getSettings(options = {}) {
        return request(METHODS.get, {}, options).then(data => data || {});
    }

    function updateSettings(values, options = {}) {
        return request(
            METHODS.update,
            { values: JSON.stringify(values || {}) },
            options
        ).then(data => data || {});
    }

    function getAudit(options = {}) {
        return request(METHODS.audit, { limit: 50 }, options).then(rows => (
            Array.isArray(rows) ? rows : []
        ));
    }

    const WHATSAPP = "almdina_erp.almdina_erp.services.whatsapp_service";
    const BACKUPS = "almdina_erp.almdina_erp.services.backup_restore_service";

    function getWhatsAppSession(options = {}) {
        return request(`${WHATSAPP}.get_whatsapp_session`, {}, options).then(data => data || {});
    }

    function createWhatsAppSession(options = {}) {
        return request(`${WHATSAPP}.create_whatsapp_session`, {}, options).then(data => data || {});
    }

    function reconnectWhatsAppSession(options = {}) {
        return request(`${WHATSAPP}.reconnect_whatsapp_session`, {}, options).then(data => data || {});
    }

    function getWhatsAppQr(options = {}) {
        return request(`${WHATSAPP}.get_whatsapp_qr`, {}, options).then(data => data || {});
    }

    function getBackupContext(options = {}) {
        return request(`${BACKUPS}.get_backup_context`, {}, options).then(data => data || {});
    }

    function createBackupNow(options = {}) {
        return request(`${BACKUPS}.create_backup_now`, {}, options).then(data => data || {});
    }

    function testSshConnection(options = {}) {
        return request(`${BACKUPS}.test_ssh_connection`, {}, options).then(data => data || {});
    }

    function requestRestore(operationId, confirmation, options = {}) {
        return request(`${BACKUPS}.request_restore`, {
            operation_id: operationId,
            confirmation,
        }, options).then(data => data || {});
    }

    window.AlmdinaFactoryProductionSettingsApi = Object.freeze({
        getSettings,
        updateSettings,
        getAudit,
        getWhatsAppSession,
        createWhatsAppSession,
        reconnectWhatsAppSession,
        getWhatsAppQr,
        getBackupContext,
        createBackupNow,
        testSshConnection,
        requestRestore,
    });
})();
