(() => {
    "use strict";

    if (window.AlmdinaFactoryProductionSettingsWhatsApp) return;

    const QR_INTERVAL_MS = 5000;

    function attach(options = {}) {
        const api = options.api;
        const renderer = options.renderer;
        const dialogs = options.dialogs;
        const frontend = options.frontend;
        const lifecycle = options.lifecycle;
        const translate = options.translate;
        if (
            !api
            || !renderer
            || !dialogs
            || !frontend
            || !lifecycle
            || typeof translate !== "function"
            || typeof frontend.createLatestRequestGate !== "function"
            || typeof renderer.renderWhatsApp !== "function"
        ) {
            throw new Error("WhatsApp settings panel dependencies are unavailable");
        }
        const t = (message) => translate(message);
        const requests = frontend.createLatestRequestGate();
        let pollTimer = null;
        let qrSurface = null;

        function isActive() {
            return typeof options.isActive !== "function" || options.isActive();
        }

        function stopPoll() {
            if (pollTimer !== null) {
                window.clearInterval(pollTimer);
                pollTimer = null;
            }
        }

        function closeQr() {
            stopPoll();
            if (qrSurface && typeof qrSurface.close === "function") {
                const surface = qrSurface;
                qrSurface = null;
                surface.close();
            }
            qrSurface = null;
        }

        function errorMessage(error, fallback) {
            return frontend.errorMessage(error, fallback);
        }

        function freeze(message) {
            return { freeze: true, freezeMessage: message };
        }

        function maybeOpenQr(snapshot) {
            if (!isActive() || !snapshot || !snapshot.needs_qr) return;
            startQrPoll();
        }

        function startQrPoll() {
            stopPoll();
            if (!qrSurface) {
                qrSurface = dialogs.openQr({
                    onHide: stopPoll,
                    statusLabel: () => t("امسح الرمز من واتساب"),
                });
            }
            const tick = () => {
                if (!isActive()) {
                    closeQr();
                    return;
                }
                const token = requests.begin();
                api.getWhatsAppQr({ freeze: false }).then(payload => {
                    if (!isActive() || !requests.isCurrent(token)) return;
                    if (payload && payload.working) {
                        closeQr();
                        renderer.renderWhatsApp(payload.session
                            ? {
                                configured: true,
                                session: payload.session,
                                working: true,
                                can_create: false,
                                needs_reconnect: false,
                                needs_qr: false,
                            }
                            : payload);
                        frappe.show_alert({ message: t("تم ربط WhatsApp."), indicator: "green" }, 6);
                        return refresh();
                    }
                    if (qrSurface && typeof qrSurface.setQr === "function") {
                        qrSurface.setQr(payload && payload.qr_code, payload && payload.status);
                    }
                    return payload;
                }).catch(error => {
                    if (!isActive() || !requests.isCurrent(token)) return;
                    frappe.show_alert({
                        message: errorMessage(error, t("تعذر جلب رمز QR.")),
                        indicator: "red",
                    }, 7);
                });
            };
            tick();
            pollTimer = window.setInterval(tick, QR_INTERVAL_MS);
        }

        function refresh() {
            if (!isActive()) return Promise.resolve(null);
            const token = requests.begin();
            return api.getWhatsAppSession({ freeze: false }).then(snapshot => {
                if (!isActive() || !requests.isCurrent(token)) return null;
                renderer.renderWhatsApp(snapshot || {});
                return snapshot;
            }).catch(error => {
                if (!isActive() || !requests.isCurrent(token)) return null;
                renderer.renderWhatsApp({
                    configured: false,
                    reason: errorMessage(error, t("تعذر تحميل حالة WhatsApp.")),
                });
                return null;
            });
        }

        function create() {
            return api.createWhatsAppSession(freeze(t("جاري إنشاء جلسة WhatsApp..."))).then(snapshot => {
                if (!isActive()) return snapshot;
                renderer.renderWhatsApp(snapshot || {});
                maybeOpenQr(snapshot);
                return snapshot;
            }).catch(error => {
                frappe.show_alert({
                    message: errorMessage(error, t("تعذر إنشاء جلسة WhatsApp.")),
                    indicator: "red",
                }, 7);
                return null;
            });
        }

        function reconnect() {
            return api.reconnectWhatsAppSession(freeze(t("جاري إعادة الاتصال..."))).then(snapshot => {
                if (!isActive()) return snapshot;
                renderer.renderWhatsApp(snapshot || {});
                maybeOpenQr(snapshot);
                return snapshot;
            }).catch(error => {
                frappe.show_alert({
                    message: errorMessage(error, t("تعذر إعادة اتصال WhatsApp.")),
                    indicator: "red",
                }, 7);
                return null;
            });
        }

        function deactivate() {
            requests.invalidate();
            closeQr();
        }

        function dispose() {
            deactivate();
        }

        lifecycle.track(dispose, "production-settings-whatsapp-panel");
        return Object.freeze({ refresh, create, reconnect, deactivate, dispose, QR_INTERVAL_MS });
    }

    window.AlmdinaFactoryProductionSettingsWhatsApp = Object.freeze({
        QR_INTERVAL_MS,
        attach,
    });
})();
