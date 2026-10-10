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
                renderer.renderBackupError(errorMessage(error, t("تعذر تحميل إدارة النسخ.")));
                return null;
            });
        }

        function createBackup() {
            if (!current()) return;
            api.createBackupNow({ freeze: true, freezeMessage: t("جاري إضافة النسخة إلى قائمة الانتظار...") })
                .then(() => {
                    if (!current()) return;
                    frappe.show_alert({ message: t("تمت جدولة النسخة المحلية في الخلفية."), indicator: "green" });
                    return refresh();
                })
                .catch(error => {
                    if (!current()) return;
                    frappe.msgprint({ title: t("تعذر إنشاء النسخة"), message: errorMessage(error, t("فشلت جدولة النسخة.")), indicator: "red" });
                });
        }

        function testConnection() {
            if (!current()) return;
            api.testSshConnection({ freeze: true, freezeMessage: t("جاري اختبار اتصال SSH والمسار البعيد...") })
                .then(() => {
                    if (current()) frappe.show_alert({ message: t("اتصال SSH والمسار البعيد صالحان."), indicator: "green" });
                })
                .catch(error => {
                    if (!current()) return;
                    frappe.msgprint({ title: t("فشل اختبار SSH"), message: errorMessage(error, t("تعذر الاتصال بالخادم البعيد.")), indicator: "red" });
                });
        }

        function openRestore(operationId, identifier) {
            if (!current() || !operationId || !identifier) return;
            dialogs.openRestore({
                confirmationPhrase: `RESTORE ${identifier}`,
                onSubmit: confirmation => api.requestRestore(
                    operationId,
                    confirmation,
                    { freeze: true, freezeMessage: t("جاري تجهيز طلب الاستعادة...") }
                ).then(result => {
                    if (current()) {
                        frappe.show_alert({ message: t("بدأ تجهيز نسخة الأمان والاستعادة في الخلفية."), indicator: "orange" }, 10);
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
