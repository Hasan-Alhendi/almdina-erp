(() => {
    "use strict";

    if (window.AlmdinaFactoryProductionSettingsBackups) return;

    const EVENT_NAMESPACE = ".almdinaFactoryProductionSettingsBackups";

    function attach(options = {}) {
        const api = options.api;
        const renderer = options.renderer;
        const dialogs = options.dialogs;
        const frontend = options.frontend;
        const lifecycle = options.lifecycle;
        const isActive = options.isActive;
        const translate = options.translate;
        const $body = options.$body;
        if (!api || !renderer || !dialogs || !frontend || !lifecycle || typeof isActive !== "function" || typeof translate !== "function" || !$body) {
            throw new Error("Backup panel dependencies are unavailable");
        }
        const t = translate;
        const requests = frontend.createLatestRequestGate();
        let disposed = false;
        let busy = false;
        let uploadLimit = 0;
        let polling = null;

        function setBusy(value, message = "") {
            busy = value;
            $body.find(".aps-backup-actions button, .aps-backup-row button").prop("disabled", value);
            $body.find(".aps-backup-upload-progress").text(message);
        }

        $body.off(EVENT_NAMESPACE);
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-backup-create", event => {
            event.preventDefault();
            if (busy) return;
            createBackup();
        });
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-backup-upload", event => {
            event.preventDefault();
            if (busy) return;
            const input = document.createElement("input");
            input.type = "file";
            input.accept = ".zip,application/zip";
            input.addEventListener("change", () => { if (input.files.length === 1) uploadBackup(input.files[0]); }, { once: true });
            input.click();
        });
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-backup-download", event => {
            event.preventDefault();
            if (busy) return;
            const id = String(event.currentTarget.dataset.operationId || "");
            if (!/^[0-9a-f]{32}$/.test(id)) return;
            const link = document.createElement("a");
            link.href = `/api/method/almdina_erp.almdina_erp.services.backup_restore_service.download_backup_zip?operation_id=${encodeURIComponent(id)}`;
            document.body.appendChild(link);
            link.click();
            link.remove();
        });
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-backup-test", event => {
            event.preventDefault();
            if (busy) return;
            testConnection();
        });
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-backup-restore", event => {
            event.preventDefault();
            if (busy) return;
            const operationId = String(event.currentTarget.dataset.operationId || "");
            const identifier = String(event.currentTarget.dataset.backupIdentifier || "");
            openRestore(operationId, identifier);
        });
        lifecycle.track(() => $body.off(EVENT_NAMESPACE), "production-settings-backup-interactions");

        function current() {
            return !disposed && isActive();
        }

        function errorMessage(error, fallback) {
            return frontend.errorMessage(error, fallback);
        }

        function refresh() {
            if (!current()) return Promise.resolve(null);
            const token = requests.begin();
            return api.getBackupContext({ freeze: false }).then(snapshot => {
                if (!current() || !requests.isCurrent(token)) return null;
                renderer.renderBackup(snapshot || {});
                uploadLimit = Number(snapshot.upload_max_bytes || 0);
                if (busy) setBusy(true, $body.data("backupUploadProgress") || t("Verifying backup..."));
                return snapshot;
            }).catch(error => {
                if (!current() || !requests.isCurrent(token)) return null;
                renderer.renderBackupError(errorMessage(error, t("Could not load backup management.")));
                return null;
            });
        }

        async function uploadBackup(file) {
            if (!current() || busy) return;
            if (!file.name.toLowerCase().endsWith(".zip") || !file.size || file.size > uploadLimit) {
                frappe.msgprint({ title: t("Could not upload backup"), message: t("Select one ZIP within the configured upload limit."), indicator: "red" });
                return;
            }
            let operationId = "";
            let scheduled = false;
            const progress = message => {
                $body.data("backupUploadProgress", message);
                if (current()) setBusy(true, message);
            };
            try {
                progress(t("Preparing backup upload..."));
                const session = await api.beginBackupUpload(file.size);
                operationId = session.operation_id;
                const chunkSize = Number(session.max_chunk_bytes);
                if (!Number.isInteger(chunkSize) || chunkSize <= 0) throw new Error("Invalid chunk size");
                for (let offset = 0; offset < file.size; offset += chunkSize) {
                    const chunk = file.slice(offset, offset + chunkSize);
                    await api.uploadBackupChunk(operationId, chunk, offset, file.size, received => {
                        progress(t("Uploading backup: {0}%", [Math.min(100, Math.round(received * 100 / file.size))]));
                    });
                }
                await api.finishBackupUpload(operationId, file.size);
                scheduled = true;
                progress(t("Verifying backup..."));
                await refresh();
                const poll = async () => {
                    const snapshot = await refresh();
                    const row = (snapshot && snapshot.history || []).find(item => item.operation_id === operationId);
                    if (!current()) return;
                    if (row && (row.status === "Completed" || row.status === "Failed")) {
                        setBusy(false);
                        frappe.show_alert({ message: row.status === "Completed" ? t("Backup import completed.") : t("Backup verification failed."), indicator: row.status === "Completed" ? "green" : "red" });
                    } else polling = window.setTimeout(poll, 5000);
                };
                polling = window.setTimeout(poll, 5000);
            } catch (error) {
                if (operationId && !scheduled) {
                    try { await api.cancelBackupUpload(operationId); } catch (_ignored) { /* The server owns cleanup. */ }
                }
                if (current()) {
                    setBusy(false);
                    frappe.msgprint({ title: t("Could not upload backup"), message: t("Backup upload failed. Please try again."), indicator: "red" });
                    refresh();
                }
            }
        }

        function createBackup() {
            if (!current()) return;
            api.createBackupNow({ freeze: true, freezeMessage: t("Adding backup to the queue...") })
                .then(() => {
                    if (!current()) return;
                    frappe.show_alert({ message: t("Local backup scheduled in the background."), indicator: "green" });
                    return refresh();
                })
                .catch(error => {
                    if (!current()) return;
                    frappe.msgprint({ title: t("Could not create the backup"), message: frappe.utils.escape_html(errorMessage(error, t("Backup scheduling failed."))), indicator: "red" });
                });
        }

        function testConnection() {
            if (!current()) return;
            api.testSshConnection({ freeze: true, freezeMessage: t("Testing SSH connection and remote path...") })
                .then(() => {
                    if (current()) frappe.show_alert({ message: t("SSH connection and remote path are valid."), indicator: "green" });
                })
                .catch(error => {
                    if (!current()) return;
                    frappe.msgprint({ title: t("SSH test failed"), message: frappe.utils.escape_html(errorMessage(error, t("Could not connect to the remote server."))), indicator: "red" });
                });
        }

        function openRestore(operationId, identifier) {
            if (!current() || !operationId || !identifier) return;
            dialogs.openRestore({
                confirmationPhrase: `RESTORE ${identifier}`,
                onSubmit: confirmation => api.requestRestore(
                    operationId,
                    confirmation,
                    { freeze: true, freezeMessage: t("Preparing the restore request...") }
                ).then(result => {
                    if (current()) {
                        frappe.show_alert({ message: t("Preparation of the backup and restore started in the background."), indicator: "orange" }, 10);
                        refresh();
                    }
                    return result;
                }),
            });
        }

        function deactivate() {
            requests.invalidate();
            if (polling) window.clearTimeout(polling);
            polling = null;
        }

        function dispose() {
            if (disposed) return;
            disposed = true;
            deactivate();
            $body.off(EVENT_NAMESPACE);
        }

        return Object.freeze({ refresh, deactivate, dispose });
    }

    window.AlmdinaFactoryProductionSettingsBackups = Object.freeze({ attach });
})();
