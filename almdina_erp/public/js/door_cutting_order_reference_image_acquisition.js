(() => {
    "use strict";

    const contract = window.AlmdinaReferenceImageContract;
    if (!contract) {
        console.error("AlmdinaReferenceImageContract must load before reference acquisition");
        return;
    }

    const MAX_FILE_BYTES = 12 * 1024 * 1024;
    const ALLOWED_TYPES = Object.freeze([
        "image/jpeg",
        "image/png",
        "image/webp",
    ]);
    const DEFAULT_BRIDGE_URL = "http://127.0.0.1:17831";
    const BRIDGE_TIMEOUT_MS = 3500;
    const SCAN_TIMEOUT_MS = 120000;

    function error(code, message, cause = null) {
        const result = new Error(message);
        result.code = code;
        result.cause = cause || undefined;
        return result;
    }

    function validateImage(file) {
        if (!file) throw error("missing-file", "لم يتم اختيار صورة.");
        const type = String(file.type || "").toLowerCase();
        if (!ALLOWED_TYPES.includes(type)) {
            throw error("unsupported-file", "اختر صورة بصيغة JPG أو PNG أو WebP.");
        }
        if (Number(file.size) > MAX_FILE_BYTES) {
            throw error("file-too-large", "حجم صورة المرجع يجب ألا يتجاوز 12 MB.");
        }
        return file;
    }

    function pickImageFile() {
        return new Promise(resolve => {
            const input = document.createElement("input");
            let settled = false;
            let focusTimer = null;
            const finish = file => {
                if (settled) return;
                settled = true;
                if (focusTimer) window.clearTimeout(focusTimer);
                window.removeEventListener("focus", handleWindowFocus);
                input.remove();
                resolve(file || null);
            };
            const handleWindowFocus = () => {
                focusTimer = window.setTimeout(() => {
                    const file = input.files && input.files[0] || null;
                    if (file) finish(file);
                    else finish(null);
                }, 250);
            };
            input.type = "file";
            input.accept = ALLOWED_TYPES.join(",");
            input.style.position = "fixed";
            input.style.left = "-10000px";
            input.style.top = "-10000px";
            input.addEventListener("change", () => {
                finish(input.files && input.files[0] || null);
            }, { once: true });
            input.addEventListener("cancel", () => finish(null), { once: true });
            window.addEventListener("focus", handleWindowFocus, { once: true });
            document.body.appendChild(input);
            input.click();
        });
    }

    function csrfToken() {
        return String(
            window.frappe && (
                frappe.csrf_token
                || frappe.boot && frappe.boot.csrf_token
            )
            || window.csrf_token
            || ""
        );
    }

    async function responseMessage(response) {
        try {
            const payload = await response.clone().json();
            if (payload && payload.message && typeof payload.message === "string") {
                return payload.message;
            }
            if (payload && payload.exc_type) return payload.exc_type;
            if (payload && payload._server_messages) {
                const messages = JSON.parse(payload._server_messages);
                const first = messages && messages[0] ? JSON.parse(messages[0]) : null;
                if (first && first.message) return first.message;
            }
        } catch (parseError) {
            // Keep the user-facing fallback below.
        }
        return `تعذر رفع الصورة (HTTP ${response.status}).`;
    }

    async function uploadImage(file, frm, source = "file") {
        validateImage(file);
        const body = new FormData();
        body.append("file", file, file.name || "special-shape-reference.jpg");
        body.append("is_private", "1");
        body.append("folder", "Home/Attachments");
        const isNew = frm && typeof frm.is_new === "function" ? frm.is_new() : false;
        const docname = frm && frm.doc && frm.doc.name;
        if (frm && frm.doctype && docname && !isNew) {
            body.append("doctype", frm.doctype);
            body.append("docname", docname);
        }
        const headers = {};
        const token = csrfToken();
        if (token) headers["X-Frappe-CSRF-Token"] = token;

        let response;
        try {
            response = await fetch("/api/method/upload_file", {
                method: "POST",
                body,
                headers,
                credentials: "same-origin",
            });
        } catch (cause) {
            throw error("upload-network", "تعذر الاتصال بالخادم لرفع صورة المرجع.", cause);
        }
        if (!response.ok) {
            throw error("upload-failed", await responseMessage(response));
        }
        const payload = await response.json();
        const uploaded = payload && payload.message || {};
        const normalized = contract.normalize({
            file_url: uploaded.file_url,
            file_name: uploaded.file_name || file.name,
            source,
            opacity: contract.DEFAULT_OPACITY,
            visible: true,
        });
        if (!normalized) {
            throw error("upload-invalid-response", "تم الرفع لكن الخادم لم يُرجع رابط صورة صالحًا.");
        }
        return normalized;
    }

    function bridgeUrl() {
        const configured = String(window.AlmdinaScannerBridgeUrl || "").trim().replace(/\/$/, "");
        return configured || DEFAULT_BRIDGE_URL;
    }

    async function fetchWithTimeout(url, options = {}, timeoutMs = BRIDGE_TIMEOUT_MS) {
        const controller = new AbortController();
        const timer = window.setTimeout(() => controller.abort(), timeoutMs);
        try {
            return await fetch(url, {
                ...options,
                signal: controller.signal,
                cache: "no-store",
            });
        } finally {
            window.clearTimeout(timer);
        }
    }

    async function scannerHealth() {
        let response;
        try {
            response = await fetchWithTimeout(`${bridgeUrl()}/health`, {
                method: "GET",
                headers: { Accept: "application/json" },
            });
        } catch (cause) {
            throw error(
                "scanner-bridge-unavailable",
                "خدمة المسح الضوئي غير متصلة بهذا اللابتوب.",
                cause
            );
        }
        if (!response.ok) {
            throw error("scanner-bridge-unavailable", "خدمة المسح الضوئي لا تستجيب بشكل صحيح.");
        }
        return response.json().catch(() => ({ ok: true }));
    }

    async function scanFromPrinter() {
        await scannerHealth();
        let response;
        try {
            response = await fetchWithTimeout(`${bridgeUrl()}/scan`, {
                method: "POST",
                headers: {
                    Accept: "image/jpeg,image/png",
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    format: "jpeg",
                    use_common_ui: true,
                }),
            }, SCAN_TIMEOUT_MS);
        } catch (cause) {
            if (cause && cause.name === "AbortError") {
                throw error("scanner-timeout", "انتهت مهلة المسح. أعد المحاولة بعد التأكد من الطابعة.", cause);
            }
            throw error("scanner-failed", "تعذر الحصول على الصورة من الماسح الضوئي.", cause);
        }
        if (response.status === 204) {
            throw error("scanner-cancelled", "تم إلغاء عملية المسح الضوئي.");
        }
        if (!response.ok) {
            let message = "تعذر المسح من الطابعة.";
            try {
                const payload = await response.json();
                if (payload && payload.message) message = String(payload.message);
            } catch (parseError) {
                // Use fallback message.
            }
            throw error("scanner-failed", message);
        }
        const blob = await response.blob();
        const type = String(blob.type || "image/jpeg").toLowerCase();
        const extension = type === "image/png" ? "png" : "jpg";
        const file = new File(
            [blob],
            `scan-${new Date().toISOString().replace(/[:.]/g, "-")}.${extension}`,
            { type }
        );
        return validateImage(file);
    }

    window.AlmdinaReferenceImageAcquisition = Object.freeze({
        MAX_FILE_BYTES,
        ALLOWED_TYPES,
        DEFAULT_BRIDGE_URL,
        validateImage,
        pickImageFile,
        uploadImage,
        bridgeUrl,
        scannerHealth,
        scanFromPrinter,
    });
})();
