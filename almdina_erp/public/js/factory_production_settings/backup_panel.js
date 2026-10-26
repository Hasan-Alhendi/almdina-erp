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

        $body.off(EVENT_NAMESPACE);
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-backup-create", event => {
            event.preventDefault();
            createBackup();
        });
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-backup-test", event => {
            event.preventDefault();
            testConnection();
        });
        $body.on(`click${EVENT_NAMESPACE}`, ".aps-backup-restore", event => {
            event.preventDefault();
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
                    frappe.msgprint({ title: t("Could not create the backup"), message: errorMessage(error, t("Backup scheduling failed.")), indicator: "red" });
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
                    frappe.msgprint({ title: t("SSH test failed"), message: errorMessage(error, t("Could not connect to the remote server.")), indicator: "red" });
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
