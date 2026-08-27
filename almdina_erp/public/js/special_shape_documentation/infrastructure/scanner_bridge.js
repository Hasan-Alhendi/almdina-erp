(() => {
    "use strict";

    const root = window.AlmdinaSpecialShapeDocumentation = window.AlmdinaSpecialShapeDocumentation || Object.create(null);
    const DEFAULT_BASE_URL = "http://127.0.0.1:17831";
    const INSTALLER_URL = "https://github.com/Hasan-Alhendi/almdina-erp/releases/download/scanner-bridge-latest/AlmdinaScannerBridgeSetup.exe";
    const MAX_IMAGE_BYTES = 8 * 1024 * 1024;
    const ERROR_CODES = Object.freeze({
        UNAVAILABLE: "bridge-unavailable",
        FORBIDDEN: "bridge-forbidden",
        BUSY: "scanner-busy",
        NO_SCANNER: "scanner-unavailable",
        SCAN_FAILED: "scan-failed",
        INVALID_IMAGE: "invalid-image",
        INVALID_RESPONSE: "invalid-response",
        IMAGE_TOO_LARGE: "image-too-large",
    });

    class ScannerBridgeError extends Error {
        constructor(code, message, cause = null, bridgeCode = "") {
            super(message);
            this.name = "ScannerBridgeError";
            this.code = code;
            this.cause = cause;
            this.bridgeCode = bridgeCode;
        }
    }

    function baseUrl(value) {
        let resolved;
        try { resolved = new URL(String(value || DEFAULT_BASE_URL)); }
        catch (error) { throw new ScannerBridgeError(ERROR_CODES.INVALID_RESPONSE, "Scanner bridge URL is invalid", error); }
        if (resolved.protocol !== "http:" || resolved.hostname !== "127.0.0.1") {
            throw new ScannerBridgeError(ERROR_CODES.INVALID_RESPONSE, "Scanner bridge must use IPv4 loopback");
        }
        return resolved.origin;
    }

    function fetcher(options) {
        const candidate = options.fetchImpl || window.fetch;
        if (typeof candidate !== "function") throw new ScannerBridgeError(ERROR_CODES.UNAVAILABLE, "Fetch is unavailable");
        return candidate.bind(window);
    }

    function requestOptions(options = {}) {
        return {
            mode: "cors",
            credentials: "omit",
            cache: "no-store",
            ...options,
        };
    }

    async function health(options = {}) {
        const controller = typeof AbortController === "function" ? new AbortController() : null;
        const timeoutMs = Math.max(250, Number(options.timeoutMs) || 1800);
        const timer = controller ? window.setTimeout(() => controller.abort(), timeoutMs) : null;
        try {
            const response = await fetcher(options)(`${baseUrl(options.baseUrl)}/health`, requestOptions({
                method: "GET",
                headers: { Accept: "application/json" },
                signal: controller && controller.signal,
            }));
            if (response.status === 403) throw new ScannerBridgeError(ERROR_CODES.FORBIDDEN, "Scanner bridge rejected this origin");
            if (!response.ok) throw new ScannerBridgeError(ERROR_CODES.UNAVAILABLE, `Scanner bridge health failed (${response.status})`);
            const payload = await response.json();
            if (!payload || payload.ok !== true || payload.service !== "almadina-scanner-bridge") {
                throw new ScannerBridgeError(ERROR_CODES.INVALID_RESPONSE, "Unexpected scanner bridge response");
            }
            return Object.freeze({ ok: true, version: String(payload.version || "") });
        } catch (error) {
            if (error instanceof ScannerBridgeError) throw error;
            throw new ScannerBridgeError(ERROR_CODES.UNAVAILABLE, "Scanner bridge is unavailable", error);
        } finally {
            if (timer !== null) window.clearTimeout(timer);
        }
    }

    async function scan(options = {}) {
        let response;
        try {
            response = await fetcher(options)(`${baseUrl(options.baseUrl)}/scan`, requestOptions({
                method: "POST",
                headers: { Accept: "image/jpeg" },
            }));
        } catch (error) {
            if (error instanceof ScannerBridgeError) throw error;
            throw new ScannerBridgeError(ERROR_CODES.UNAVAILABLE, "Scanner bridge is unavailable", error);
        }
        if (response.status === 204) return null;
        if (!response.ok) throw await scanResponseError(response);

        const contentType = String(response.headers.get("content-type") || "").split(";", 1)[0].trim().toLowerCase();
        if (contentType !== "image/jpeg") throw new ScannerBridgeError(ERROR_CODES.INVALID_RESPONSE, "Scanner did not return a JPEG image");
        let blob;
        try { blob = await response.blob(); }
        catch (error) { throw new ScannerBridgeError(ERROR_CODES.INVALID_RESPONSE, "Scanner image could not be read", error); }
        if (!blob.size) throw new ScannerBridgeError(ERROR_CODES.INVALID_RESPONSE, "Scanner returned an empty image");
        if (blob.size > MAX_IMAGE_BYTES) throw new ScannerBridgeError(ERROR_CODES.IMAGE_TOO_LARGE, "Scanned image is too large");

        const FileConstructor = options.FileConstructor || window.File;
        if (typeof FileConstructor !== "function") throw new ScannerBridgeError(ERROR_CODES.INVALID_RESPONSE, "File API is unavailable");
        const stamp = new Date().toISOString().replace(/[:.]/g, "-");
        return new FileConstructor([blob], `scan-${stamp}.jpg`, { type: "image/jpeg", lastModified: Date.now() });
    }

    async function scanResponseError(response) {
        let payload = null;
        const contentType = String(response.headers.get("content-type") || "").toLowerCase();
        if (contentType.includes("application/json")) {
            try { payload = await response.json(); }
            catch (error) { payload = null; }
        }
        const bridgeCode = String(payload && payload.code || "");
        const codeByBridgeError = {
            origin_not_allowed: ERROR_CODES.FORBIDDEN,
            origin_required: ERROR_CODES.FORBIDDEN,
            scanner_busy: ERROR_CODES.BUSY,
            scanner_unavailable: ERROR_CODES.NO_SCANNER,
            scan_failed: ERROR_CODES.SCAN_FAILED,
            invalid_scanner_image: ERROR_CODES.INVALID_IMAGE,
            image_too_large: ERROR_CODES.IMAGE_TOO_LARGE,
        };
        const codeByStatus = {
            403: ERROR_CODES.FORBIDDEN,
            409: ERROR_CODES.BUSY,
            413: ERROR_CODES.IMAGE_TOO_LARGE,
            503: ERROR_CODES.NO_SCANNER,
        };
        const code = codeByBridgeError[bridgeCode] || codeByStatus[response.status] || ERROR_CODES.SCAN_FAILED;
        const message = String(payload && payload.message || `Scanner acquisition failed (${response.status})`);
        return new ScannerBridgeError(code, message, null, bridgeCode);
    }

    root.ScannerBridge = Object.freeze({ DEFAULT_BASE_URL, INSTALLER_URL, ERROR_CODES, ScannerBridgeError, health, scan });
})();
