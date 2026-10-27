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

    const CUSTOMER_BOT = "almdina_erp.almdina_erp.services.customer_bot_settings_service";

    function getCustomerBotSettings(options = {}) {
        return request(`${CUSTOMER_BOT}.get_customer_bot_settings`, {}, options).then(data => data || {});
    }

    function saveCustomerBotDraft(expectedRevision, texts, options = {}) {
        return request(`${CUSTOMER_BOT}.save_customer_bot_draft`, {
            expected_revision: expectedRevision,
            texts: JSON.stringify(texts || {}),
        }, options).then(data => data || {});
    }

    function publishCustomerBotTexts(expectedRevision, texts, options = {}) {
        return request(`${CUSTOMER_BOT}.publish_customer_bot_texts`, {
            expected_revision: expectedRevision,
            texts: JSON.stringify(texts || {}),
        }, options).then(data => data || {});
    }

    function setCustomerBotEnabled(expectedRevision, enabled, options = {}) {
        return request(`${CUSTOMER_BOT}.set_customer_bot_enabled`, {
            expected_revision: expectedRevision,
            enabled: enabled ? 1 : 0,
        }, options).then(data => data || {});
    }

    function previewCustomerBot(payload, options = {}) {
        return request(`${CUSTOMER_BOT}.preview_customer_bot`, {
            source: payload.source,
            scenario: payload.scenario,
            text: payload.text,
            state: payload.state ? JSON.stringify(payload.state) : "",
            texts: JSON.stringify(payload.texts || {}),
        }, options).then(data => data || {});
    }

    const CUSTOMER_BOT_OPERATION = "almdina_erp.almdina_erp.services.customer_bot_operation_service";

    function getCustomerBotOperationStatus(options = {}) {
        return request(`${CUSTOMER_BOT_OPERATION}.get_customer_bot_operation_status`, {}, options).then(data => data || {});
    }

    function startCustomerBotOperation(options = {}) {
        return request(`${CUSTOMER_BOT_OPERATION}.start_customer_bot_operation`, {}, options).then(data => data || {});
    }

    function stopCustomerBotOperation(options = {}) {
        return request(`${CUSTOMER_BOT_OPERATION}.stop_customer_bot_operation`, {}, options).then(data => data || {});
    }

    function checkCustomerBotOperation(options = {}) {
        return request(`${CUSTOMER_BOT_OPERATION}.check_customer_bot_operation`, {}, options).then(data => data || {});
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
        getCustomerBotSettings,
        saveCustomerBotDraft,
        publishCustomerBotTexts,
        setCustomerBotEnabled,
        previewCustomerBot,
        getCustomerBotOperationStatus,
        startCustomerBotOperation,
        stopCustomerBotOperation,
        checkCustomerBotOperation,
    });
})();
