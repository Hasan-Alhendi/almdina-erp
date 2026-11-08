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
        let watchedOperation = "";
        let watchedKind = "";
        let restoreSeen = false;
        let siteName = "";
        let generation = 0;
        const pendingKey = `almdina-restore:${window.location.host}`;
        try {
            watchedOperation = window.localStorage.getItem(pendingKey) || "";
            if (watchedOperation) { watchedKind = "restore"; restoreSeen = true; }
        } catch (_ignored) { /* Storage may be unavailable. */ }

        function schedulePoll() {
            if (polling || !current()) return;
            polling = window.setTimeout(() => { polling = null; refresh(); }, 5000);
        }

        function watch(id, kind) {
            watchedOperation = id;
            watchedKind = kind;
            schedulePoll();
        }

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
            openRestore(operationId, identifier, event.currentTarget.dataset.requestedOn, event.currentTarget.dataset.totalSize);
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
                siteName = String(snapshot.site || "");
                uploadLimit = Number(snapshot.upload_max_bytes || 0);
                const restore = snapshot.restore_status || {};
                restoreSeen = Boolean(restore.phase) && !["COMPLETED", "RECOVERED_AFTER_FAILURE", "MANUAL_INTERVENTION_REQUIRED"].includes(restore.phase);
                if (watchedKind === "restore" && restore.operation_id && restore.operation_id !== watchedOperation) {
                    watchedOperation = restore.operation_id;
                    try { window.localStorage.setItem(pendingKey, watchedOperation); } catch (_ignored) { /* Optional persistence. */ }
                }
                if (watchedKind === "restore" && !restore.phase) renderer.renderRestoreOffline();
                if (watchedOperation) {
                    const row = (snapshot.history || []).find(item => item.operation_id === watchedOperation);
                    if (row && ["Completed", "Failed"].includes(row.status) && watchedKind !== "restore") {
                        const succeeded = row.status === "Completed";
                        frappe.show_alert({ message: succeeded ? t("Backup operation completed.") : t("Backup operation failed."), indicator: succeeded ? "green" : "red" });
                        watchedOperation = "";
                        watchedKind = "";
                        setBusy(false);
                    } else if (watchedKind === "restore" && restore.operation_id === watchedOperation && !restoreSeen) {
                        watchedOperation = "";
                        watchedKind = "";
                        try { window.localStorage.removeItem(pendingKey); } catch (_ignored) { /* Optional persistence. */ }
                    }
                }
                if (busy) setBusy(true, $body.data("backupUploadProgress") || t("Verifying backup..."));
                const running = (snapshot.history || []).some(row =>
                    ["Queued", "Running", "Prepared"].includes(row.status) &&
                    (row.operation_type !== "Imported" || row.status === "Running"));
                if (watchedOperation || restoreSeen || running) schedulePoll();
                return snapshot;
            }).catch(error => {
                if (!current() || !requests.isCurrent(token)) return null;
                if (restoreSeen || watchedKind === "restore") renderer.renderRestoreOffline();
                else renderer.renderBackupError(errorMessage(error, t("Could not load backup management.")));
                if (watchedOperation || restoreSeen) schedulePoll();
                return null;
            });
        }

        async function uploadBackup(file) {
            if (!current() || busy) return;
            const started = generation;
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
                    if (!current() || generation !== started) throw new Error("Upload view closed");
                    const chunk = file.slice(offset, offset + chunkSize);
                    await api.uploadBackupChunk(operationId, chunk, offset, file.size, received => {
                        progress(t("Uploading backup: {0}%", [Math.min(100, Math.round(received * 100 / file.size))]));
                    });
                }
                if (!current() || generation !== started) throw new Error("Upload view closed");
                await api.finishBackupUpload(operationId, file.size);
                scheduled = true;
                progress(t("Verifying backup..."));
                watch(operationId, "import");
                await refresh();
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
            setBusy(true, t("Adding backup to the queue..."));
            api.createBackupNow({ freeze: true, freezeMessage: t("Adding backup to the queue...") })
                .then(result => {
                    if (!current()) return;
                    watch(result.operation_id, "create");
                    return refresh();
                })
                .catch(error => {
                    if (!current()) return;
                    setBusy(false);
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

        function openRestore(operationId, identifier, requestedOn, totalSize) {
            if (!current() || !operationId || !identifier) return;
            dialogs.openRestore({
                confirmationPhrase: `RESTORE ${identifier}`,
                site: siteName,
                requestedOn,
                size: totalSize,
                onSubmit: confirmation => api.requestRestore(
                    operationId,
                    confirmation,
                    { freeze: true, freezeMessage: t("Preparing the restore request...") }
                ).then(result => {
                    if (current()) {
                        try { window.localStorage.setItem(pendingKey, result.operation_id); } catch (_ignored) { /* Optional persistence. */ }
                        watch(result.operation_id, "restore");
                        refresh();
                    }
                    return result;
                }),
            });
        }

        function deactivate() {
            generation += 1;
            requests.invalidate();
            if (polling) window.clearTimeout(polling);
            polling = null;
            watchedOperation = "";
            watchedKind = "";
            restoreSeen = false;
            busy = false;
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
