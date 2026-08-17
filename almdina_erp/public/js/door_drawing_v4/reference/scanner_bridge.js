(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingReference = window.AlmdinaDoorDrawingReference || Object.create(null);

    const DEFAULT_BASE_URL = "http://127.0.0.1:17654";
    const REQUEST_HEADER = "X-Almdina-Scanner-Bridge";
    const REQUEST_HEADER_VALUE = "1";

    class ScannerBridgeError extends Error {
        constructor(code, message, cause = null) {
            super(message);
            this.name = "ScannerBridgeError";
            this.code = code;
            this.cause = cause || null;
        }
    }

    function baseUrl() {
        const configured = String(window.ALMDINA_SCANNER_BRIDGE_URL || "").trim();
        return (configured || DEFAULT_BASE_URL).replace(/\/$/, "");
    }

    async function request(path, options = {}) {
        const controller = typeof AbortController === "function" ? new AbortController() : null;
        const timeoutMs = Math.max(1000, Number(options.timeoutMs || 4000));
        const timer = controller ? window.setTimeout(() => controller.abort(), timeoutMs) : null;
        try {
            const response = await fetch(`${baseUrl()}${path}`, {
                method: options.method || "GET",
                mode: "cors",
                cache: "no-store",
                credentials: "omit",
                signal: controller ? controller.signal : undefined,
                headers: {
                    "Accept": "application/json",
                    [REQUEST_HEADER]: REQUEST_HEADER_VALUE,
                    ...(options.body ? { "Content-Type": "application/json" } : {}),
                },
                body: options.body ? JSON.stringify(options.body) : undefined,
            });
            if (!response.ok) {
                let detail = "";
                try { detail = String((await response.json()).message || ""); } catch (_) { /* no-op */ }
                throw new ScannerBridgeError(
                    response.status === 403 ? "origin-denied" : "bridge-error",
                    detail || `Scanner bridge returned HTTP ${response.status}.`
                );
            }
            return await response.json();
        } catch (error) {
            if (error instanceof ScannerBridgeError) throw error;
            if (error && error.name === "AbortError") {
                throw new ScannerBridgeError("bridge-timeout", "انتهت مهلة الاتصال ببرنامج Scanner المحلي.", error);
            }
            throw new ScannerBridgeError(
                "bridge-unavailable",
                "برنامج الربط المحلي للـScanner غير متصل على هذا الجهاز.",
                error
            );
        } finally {
            if (timer) window.clearTimeout(timer);
        }
    }

    function base64ToFile(payload) {
        const base64 = String(payload && payload.data_base64 || "");
        if (!base64) throw new ScannerBridgeError("empty-scan", "لم يرجع الـScanner أي صورة.");
        let binary;
        try { binary = window.atob(base64); }
        catch (error) { throw new ScannerBridgeError("invalid-scan", "بيانات الصورة القادمة من الـScanner غير صالحة.", error); }
        const bytes = new Uint8Array(binary.length);
        for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
        const mime = String(payload.mime_type || "image/jpeg");
        const blob = new Blob([bytes], { type: mime });
        const filename = String(payload.filename || `scanner-${Date.now()}.jpg`);
        return new File([blob], filename, { type: mime, lastModified: Date.now() });
    }

    async function health() {
        const result = await request("/health", { timeoutMs: 2500 });
        const deviceCount = Math.max(0, Number(result && result.device_count || 0));
        return Object.freeze({
            ok: Boolean(result && result.ok),
            version: String(result && result.version || ""),
            provider: String(result && result.provider || "wia"),
            ready: Boolean(result && result.ready) && deviceCount > 0,
            deviceCount,
        });
    }

    async function scan(options = {}) {
        const dpi = Math.max(75, Math.min(1200, Math.round(Number(options.dpi || 300))));
        const result = await request("/scan", {
            method: "POST",
            timeoutMs: Math.max(120000, Number(options.timeoutMs || 300000)),
            body: {
                dpi,
                show_ui: options.showUi !== false,
                color_mode: options.colorMode || "color",
            },
        });
        const file = base64ToFile(result);
        return Object.freeze({
            file,
            scanner: Object.freeze({
                provider: String(result.provider || "local-wia-bridge"),
                device: String(result.device || ""),
                dpi: Number(result.dpi || dpi),
            }),
        });
    }

    root.ScannerBridge = Object.freeze({
        DEFAULT_BASE_URL,
        ScannerBridgeError,
        health,
        scan,
    });
})();