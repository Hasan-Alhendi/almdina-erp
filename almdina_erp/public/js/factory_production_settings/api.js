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

    function saveArtcamTool(values, options = {}) {
        return request(`${BASE}.save_artcam_tool`, {
            values: JSON.stringify(values || {}),
        }, options).then(data => data || {});
    }

    function saveMachiningProfile(values, options = {}) {
        return request(`${BASE}.save_cnc_machining_profile`, {
            values: JSON.stringify(values || {}),
        }, options).then(data => data || {});
    }

    function saveCncToolPreset(values, options = {}) {
        return request(`${BASE}.save_cnc_tool_preset`, {
            values: JSON.stringify(values || {}),
        }, options).then(data => data || {});
    }

    function setCncToolPresetEnabled(name, enabled, options = {}) {
        return request(`${BASE}.set_cnc_tool_preset_enabled`, {
            name,
            enabled: enabled ? 1 : 0,
        }, options).then(data => data || {});
    }

    function deleteCncToolPreset(name, options = {}) {
        return request(`${BASE}.delete_cnc_tool_preset`, { name }, options).then(data => data || {});
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

    function beginBackupUpload(size) {
        return request(`${BACKUPS}.begin_backup_upload`, { file_size: size });
    }

    function finishBackupUpload(operationId, size) {
        return request(`${BACKUPS}.finish_backup_upload`, { operation_id: operationId, file_size: size });
    }

    function cancelBackupUpload(operationId) {
        return request(`${BACKUPS}.cancel_backup_upload`, { operation_id: operationId });
    }

    function uploadBackupChunk(operationId, chunk, offset, size, onProgress) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            xhr.open("POST", `/api/method/${BACKUPS}.upload_backup_chunk`);
            xhr.setRequestHeader("X-Frappe-CSRF-Token", frappe.csrf_token);
            xhr.upload.onprogress = event => {
                if (event.lengthComputable) onProgress(offset + Math.min(event.loaded, chunk.size));
            };
            xhr.onload = () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    try { resolve(JSON.parse(xhr.responseText).message); } catch (error) { reject(error); }
                } else reject(new Error("Backup upload failed."));
            };
            xhr.onerror = () => reject(new Error("Backup upload failed."));
            const data = new FormData();
            data.append("operation_id", operationId);
            data.append("offset", String(offset));
            data.append("file_size", String(size));
            data.append("file", chunk, "backup.zip");
            xhr.send(data);
        });
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
        saveArtcamTool,
        saveMachiningProfile,
        saveCncToolPreset,
        setCncToolPresetEnabled,
        deleteCncToolPreset,
        getWhatsAppSession,
        createWhatsAppSession,
        reconnectWhatsAppSession,
        getWhatsAppQr,
        getBackupContext,
        createBackupNow,
        beginBackupUpload,
        uploadBackupChunk,
        finishBackupUpload,
        cancelBackupUpload,
        testSshConnection,
        requestRestore,
    });
})();
