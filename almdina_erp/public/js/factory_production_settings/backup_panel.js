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
        const getSettingsPage = typeof options.getSettingsPage === "function"
            ? options.getSettingsPage
            : () => null;
        if (!api || !renderer || !dialogs || !frontend || !lifecycle || typeof isActive !== "function" || typeof translate !== "function" || !$body) {
            throw new Error("Backup panel dependencies are unavailable");
        }
        const t = translate;
        const requests = frontend.createLatestRequestGate();
        let disposed = false;
        let latestSnapshot = null;
        let listFilters = { query: "", type: "", source: "", status: "", sort: "date_desc" };

        $body.off(EVENT_NAMESPACE);
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-backup-create", event => {
            event.preventDefault();
            createBackup();
        });
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-backup-import", event => {
            event.preventDefault();
            importBackup();
        });
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-backup-test", event => {
            event.preventDefault();
            testConnection();
        });
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-backup-test-db", event => {
            event.preventDefault();
            testDbConnection();
        });
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-db-restore-save", event => {
            event.preventDefault();
            saveDbRestoreSettings();
        });
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-backup-row", event => {
            if (event.target.closest("button, a, input, select, textarea, label, .aps-backup-row-actions")) {
                return;
            }
            const operationId = String(event.currentTarget.dataset.operationId || "");
            openDetails(operationId);
        });
        $body.on(`keydown${EVENT_NAMESPACE}`, ".aps-backup-row.is-clickable", event => {
            if (event.key !== "Enter" && event.key !== " ") return;
            if (event.target.closest("button, a, input, select, textarea, label, .aps-backup-row-actions")) {
                return;
            }
            event.preventDefault();
            const operationId = String(event.currentTarget.dataset.operationId || "");
            openDetails(operationId);
        });
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-backup-restore", event => {
            event.preventDefault();
            event.stopPropagation();
            const operationId = String(event.currentTarget.dataset.operationId || "");
            const identifier = String(event.currentTarget.dataset.backupIdentifier || "");
            openRestore(operationId, identifier);
        });
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-backup-download", event => {
            event.preventDefault();
            event.stopPropagation();
            const operationId = String(event.currentTarget.dataset.operationId || "");
            downloadBackup(operationId);
        });
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-backup-delete", event => {
            event.preventDefault();
            event.stopPropagation();
            const operationId = String(event.currentTarget.dataset.operationId || "");
            const identifier = String(event.currentTarget.dataset.backupIdentifier || "");
            const target = String(event.currentTarget.dataset.backupTarget || "");
            confirmDelete(operationId, identifier, target);
        });
        $body.on(`input${EVENT_NAMESPACE} change${EVENT_NAMESPACE}`, "[data-backup-filter]", () => {
            captureFiltersFromDom();
            if (typeof renderer.renderBackupList === "function") {
                renderer.renderBackupList(latestSnapshot || {}, listFilters);
            } else {
                paint(latestSnapshot || {});
            }
        });
        lifecycle.track(() => $body.off(EVENT_NAMESPACE), "production-settings-backup-interactions");

        function current() {
            return !disposed && isActive();
        }

        function errorMessage(error, fallback) {
            return frontend.errorMessage(error, fallback);
        }

        function captureFiltersFromDom() {
            const $root = $body.find("[data-backup-root]");
            const read = name => String($root.find(`[data-backup-filter="${name}"]`).val() || "").trim();
            listFilters = {
                query: read("query"),
                type: read("type"),
                source: read("source"),
                status: read("status"),
                sort: read("sort") || "date_desc",
            };
        }

        function paint(snapshot) {
            const page = getSettingsPage() || {};
            renderer.renderBackup(snapshot || {}, {
                filters: listFilters,
                scheduleSection: page.backupScheduleSection || null,
            });
        }

        function refresh() {
            if (!current()) return Promise.resolve(null);
            const token = requests.begin();
            return api.getBackupContext({ freeze: false }).then(snapshot => {
                if (!current() || !requests.isCurrent(token)) return null;
                latestSnapshot = snapshot || {};
                paint(latestSnapshot);
                return snapshot;
            }).catch(error => {
                if (!current() || !requests.isCurrent(token)) return null;
                renderer.renderBackupError(errorMessage(error, t("Could not load backup management.")));
                return null;
            });
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

        function importBackup() {
            if (!current()) return;
            const ui = window.AlmdinaUi;
            if (!ui || typeof ui.fileUploader !== "function" || typeof api.importBackupZip !== "function") {
                frappe.msgprint({
                    title: t("Could not import the backup"),
                    message: frappe.utils.escape_html(t("The backup import service is not ready.")),
                    indicator: "red",
                });
                return;
            }
            ui.fileUploader({
                preset: "securePrivate",
                restrictions: {
                    allowed_file_types: [".zip"],
                },
                on_success(file) {
                    if (!current()) return null;
                    const fileUrl = file && (file.file_url || file.file_name);
                    const fileId = file && file.name;
                    if (!fileUrl) {
                        frappe.msgprint({
                            title: t("Could not import the backup"),
                            message: frappe.utils.escape_html(t("The uploaded backup file was not found.")),
                            indicator: "red",
                        });
                        return null;
                    }
                    return api.importBackupZip(fileUrl, fileId, {
                        freeze: true,
                        freezeMessage: t("Validating and importing the backup package..."),
                    }).then(result => {
                        if (!current()) return null;
                        frappe.show_alert({
                            message: t("Backup imported successfully."),
                            indicator: "green",
                        }, 6);
                        return refresh().then(() => result);
                    }).catch(error => {
                        if (!current()) return null;
                        frappe.msgprint({
                            title: t("Could not import the backup"),
                            message: frappe.utils.escape_html(errorMessage(error, t("Could not import the backup package."))),
                            indicator: "red",
                        });
                        return null;
                    });
                },
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

        function readDbRestoreForm() {
            const $root = $body.find("[data-db-restore-settings]");
            const read = fieldname => String($root.find(`[data-db-restore-field="${fieldname}"]`).val() || "").trim();
            const payload = {
                db_restore_type: read("db_restore_type"),
                db_restore_host: read("db_restore_host"),
                db_restore_root_username: read("db_restore_root_username"),
            };
            const portRaw = read("db_restore_port");
            if (portRaw) payload.db_restore_port = Number(portRaw);
            const password = String($root.find('[data-db-restore-field="db_restore_root_password"]').val() || "");
            if (password) payload.db_restore_root_password = password;
            return payload;
        }

        function saveDbRestoreSettings() {
            if (!current()) return;
            const payload = readDbRestoreForm();
            api.updateSettings(payload, { freeze: true, freezeMessage: t("Saving database settings...") })
                .then(() => {
                    if (!current()) return;
                    frappe.show_alert({ message: t("Database restore settings saved."), indicator: "green" });
                    return refresh();
                })
                .catch(error => {
                    if (!current()) return;
                    frappe.msgprint({
                        title: t("Could not save"),
                        message: frappe.utils.escape_html(errorMessage(error, t("Could not save database restore settings."))),
                        indicator: "red",
                    });
                });
        }

        function testDbConnection() {
            if (!current()) return;
            api.testDbConnection({ freeze: true, freezeMessage: t("Testing database root connection...") })
                .then(result => {
                    if (!current()) return;
                    const privileged = result && result.has_restore_privileges;
                    frappe.show_alert({
                        message: privileged
                            ? t("Database connection succeeded with restore privileges.")
                            : t("Database connection succeeded."),
                        indicator: "green",
                    });
                })
                .catch(error => {
                    if (!current()) return;
                    frappe.msgprint({
                        title: t("Database connection test failed"),
                        message: frappe.utils.escape_html(errorMessage(error, t("Could not verify the database root connection."))),
                        indicator: "red",
                    });
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

        function findRow(operationId) {
            const rows = latestSnapshot && Array.isArray(latestSnapshot.history) ? latestSnapshot.history : [];
            return rows.find(row => String(row.operation_id || "") === String(operationId || "")) || null;
        }

        function openDetails(operationId) {
            if (!current() || !operationId) return;
            const row = findRow(operationId);
            if (!row) {
                frappe.msgprint({
                    title: t("Backup details"),
                    message: frappe.utils.escape_html(t("Backup was not found.")),
                    indicator: "orange",
                });
                return;
            }
            if (typeof dialogs.openBackupDetails === "function") {
                dialogs.openBackupDetails({ row });
                return;
            }
            frappe.msgprint({
                title: t("Backup details"),
                message: frappe.utils.escape_html(String(row.backup_identifier || row.operation_id || "")),
                indicator: "blue",
            });
        }

        function confirmDelete(operationId, identifier, target) {
            if (!current() || !operationId || typeof api.deleteBackup !== "function") return;
            const name = identifier || operationId;
            if (typeof dialogs.openBackupDelete !== "function") {
                frappe.confirm(
                    t("Delete backup {0}?", [name]),
                    () => runDelete(operationId)
                );
                return;
            }
            dialogs.openBackupDelete({
                backupName: name,
                target,
                onConfirm: () => runDelete(operationId),
            });
        }

        function runDelete(operationId) {
            if (!current()) return Promise.resolve(null);
            return api.deleteBackup(operationId, {
                freeze: true,
                freezeMessage: t("Deleting backup..."),
            }).then(result => {
                if (!current()) return null;
                const message = result && result.message
                    ? String(result.message)
                    : t("Backup files and history were deleted.");
                frappe.show_alert({ message, indicator: "green" }, 8);
                return refresh();
            }).catch(error => {
                if (!current()) return null;
                frappe.msgprint({
                    title: t("Could not delete the backup"),
                    message: frappe.utils.escape_html(errorMessage(error, t("Could not delete the backup."))),
                    indicator: "red",
                });
                return null;
            });
        }

        function parseDownloadErrorPayload(rawText) {
            const text = String(rawText || "").trim();
            if (!text) return "";
            try {
                const payload = JSON.parse(text);
                if (payload && typeof payload.message === "string" && payload.message.trim()) {
                    return payload.message.trim();
                }
                if (payload && payload._server_messages) {
                    const encoded = JSON.parse(payload._server_messages);
                    const messages = Array.isArray(encoded) ? encoded : [encoded];
                    for (const entry of messages) {
                        const item = typeof entry === "string" ? JSON.parse(entry) : entry;
                        if (item && item.message) return String(item.message);
                    }
                }
                if (payload && payload.exc_type) {
                    return t("Could not prepare the backup download.");
                }
            } catch (_error) {
                if (/^\s*\{/.test(text)) {
                    return t("Could not prepare the backup download.");
                }
            }
            return "";
        }

        function downloadBackup(operationId) {
            if (!current() || !operationId) return;
            if (typeof api.downloadBackupZipMethod !== "function") {
                frappe.msgprint({
                    title: t("Could not download the backup"),
                    message: frappe.utils.escape_html(t("Could not prepare the backup download.")),
                    indicator: "red",
                });
                return;
            }

            const method = api.downloadBackupZipMethod();
            const frameName = `almdina-backup-download-${Date.now()}`;
            const iframe = document.createElement("iframe");
            iframe.name = frameName;
            iframe.setAttribute("aria-hidden", "true");
            iframe.style.display = "none";

            const form = document.createElement("form");
            form.method = "POST";
            form.action = `/api/method/${method}`;
            form.target = frameName;
            form.style.display = "none";

            const operationInput = document.createElement("input");
            operationInput.type = "hidden";
            operationInput.name = "operation_id";
            operationInput.value = String(operationId);
            form.appendChild(operationInput);

            const csrf = document.createElement("input");
            csrf.type = "hidden";
            csrf.name = "csrf_token";
            csrf.value = String((frappe.csrf_token || (frappe.boot && frappe.boot.csrf_token) || ""));
            form.appendChild(csrf);

            let settled = false;
            const cleanup = () => {
                if (settled) return;
                settled = true;
                try { frappe.dom.unfreeze(); } catch (_error) { /* ignore */ }
                form.remove();
                iframe.remove();
            };

            const fail = (message) => {
                cleanup();
                if (!current()) return;
                frappe.msgprint({
                    title: t("Could not download the backup"),
                    message: frappe.utils.escape_html(message || t("Could not prepare the backup download.")),
                    indicator: "red",
                });
            };

            iframe.addEventListener("load", () => {
                if (settled || !current()) {
                    cleanup();
                    return;
                }
                let raw = "";
                try {
                    raw = String(
                        (iframe.contentDocument
                            && iframe.contentDocument.body
                            && iframe.contentDocument.body.innerText)
                        || ""
                    );
                } catch (_error) {
                    cleanup();
                    return;
                }
                const message = parseDownloadErrorPayload(raw);
                if (message) {
                    fail(message);
                    return;
                }
                cleanup();
                if (current()) {
                    frappe.show_alert({ message: t("Backup download started."), indicator: "green" }, 5);
                }
            });

            document.body.appendChild(iframe);
            document.body.appendChild(form);
            frappe.dom.freeze(t("Preparing backup download..."));
            try {
                form.submit();
            } catch (_error) {
                fail(t("Could not prepare the backup download."));
            }
        }

        function deactivate() {
            requests.invalidate();
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
