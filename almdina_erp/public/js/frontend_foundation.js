(() => {
    "use strict";

    if (window.AlmdinaFrontend) return;

    const pendingAssetGroups = new Map();
    const normalizedErrors = new WeakSet();

    function frappeRuntime() {
        if (window.frappe) return window.frappe;
        if (typeof frappe !== "undefined") return frappe;
        return null;
    }

    function translate(message) {
        return typeof __ === "function" ? __(message) : message;
    }

    function publicText(value, limit = 2000) {
        if (typeof value !== "string") return "";
        // Legacy Frappe messages can contain markup. Return plain text; HTML
        // consumers must still use the design system's escapeHtml boundary.
        return value.slice(0, limit)
            .replace(/<br\s*\/?\s*>/gi, "\n")
            .replace(/<\/?[a-z!][^>]*>/gi, "")
            .trim();
    }

    function parseMessages(value) {
        if (typeof value === "string") {
            try { value = JSON.parse(value); } catch (_error) { return []; }
        }
        if (!Array.isArray(value)) return [];
        return value.slice(0, 10).map(item => {
            if (typeof item === "string") {
                try { item = JSON.parse(item); } catch (_error) { return publicText(item); }
            }
            return publicText(item && item.message);
        }).filter(Boolean);
    }

    function numericPreview(value) {
        if (!value || !Array.isArray(value.paths) || value.paths.length !== 2) return null;
        const points = [];
        const paths = [];
        for (const rings of value.paths) {
            if (!Array.isArray(rings) || !rings.length) return null;
            const result = [];
            for (const ring of rings) {
                if (!Array.isArray(ring) || ring.length < 3) return null;
                const copy = [];
                for (const point of ring) {
                    if (!Array.isArray(point) || point.length !== 2
                        || point.some(n => typeof n !== "number" || !Number.isFinite(n) || Math.abs(n) > 1e8)) return null;
                    points.push(point);
                    if (points.length > 512) return null;
                    copy.push([point[0], point[1]]);
                }
                result.push(copy);
            }
            paths.push(result);
        }
        const xs = points.map(p => p[0]), ys = points.map(p => p[1]);
        return { paths, bounds: [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)] };
    }

    function normalizeError(error, options = {}) {
        if (error && typeof error === "object" && normalizedErrors.has(error)) return error;
        const response = error && error.responseJSON || error || {};
        const status = Number(error && error.status) || 0;
        const envelope = response && response.almdina_error;
        const supported = envelope && envelope.schema_version === 1
            && Array.isArray(envelope.issues);
        const issues = supported ? envelope.issues.slice(0, 100)
            .filter(item => item && typeof item.code === "string" && /^[A-Z][A-Z0-9_]{0,79}$/.test(item.code))
            .map(item => Object.freeze({
                code: item.code,
                problem: publicText(item.problem), target: publicText(item.target),
                action: publicText(item.action), category: publicText(item.category, 80),
                highlight: publicText(item.highlight),
                table: Array.isArray(item.table) ? item.table.slice(0, 100).filter(Array.isArray)
                    .map(row => row.slice(0, 20).map(cell => publicText(cell, 200))) : [],
                details: Array.isArray(item.details) ? item.details.slice(0, 20).map(line => publicText(line)).filter(Boolean) : [],
                preview: numericPreview(item.preview),
            })) : [];
        const exceptionType = typeof response.exc_type === "string" ? response.exc_type : "";
        const knownException = !exceptionType || [
            "ValidationError", "PermissionError", "AuthenticationError", "DoesNotExistError",
            "TimestampMismatchError", "DuplicateEntryError", "MandatoryError", "LinkValidationError",
        ].includes(exceptionType);
        const messages = knownException && status < 500
            ? parseMessages(response._server_messages || response.messages) : [];
        const statusMessages = {
            401: translate("Your session has expired. Sign in again."),
            403: translate("You do not have permission to perform this action."),
            404: translate("The requested resource is unavailable."),
            413: translate("The uploaded file exceeds the server's size limit."),
            429: translate("Too many requests. Wait a moment before trying again."),
            502: translate("The server is temporarily unavailable. Check the current status before repeating the operation."),
            503: translate("The server is temporarily unavailable. Check the current status before repeating the operation."),
            504: translate("The request timed out. Check the current status before repeating the operation."),
        };
        const fallback = statusMessages[status] || publicText(options.fallback)
            || translate("The operation could not be completed. Please try again or contact support.");
        // Error.message/stack/exception/exc are diagnostics, not public copy.
        // Only a protocol message or a legacy server-message list is eligible
        // for display; even an unstructured string can contain private details.
        const message = issues[0] && issues[0].problem || messages.join("\n") || fallback;
        const normalized = Object.freeze({
            isAlmdinaError: true, status, exceptionType,
            code: issues[0] && issues[0].code || "OPERATION_FAILED",
            title: supported ? publicText(envelope.title, 200) : "",
            message, issues,
            outcome: supported && ["rejected", "partial", "unknown"].includes(envelope.outcome)
                ? envelope.outcome : "unknown",
            requestReference: supported && typeof envelope.request_reference === "string"
                && /^[a-zA-Z0-9-]{1,80}$/.test(envelope.request_reference)
                ? envelope.request_reference
                : typeof options.requestReference === "string" && /^[a-zA-Z0-9-]{1,80}$/.test(options.requestReference)
                    ? options.requestReference : null,
            hasMore: Boolean(supported && envelope.has_more),
            partialValidation: Boolean(supported && envelope.validation_coverage === "partial"),
        });
        normalizedErrors.add(normalized);
        return normalized;
    }

    function errorMessage(error, fallback = "") {
        return normalizeError(error, { fallback }).message;
    }

    async function ownedRpc(method, args = {}, options = {}) {
        // Explicit opt-in for app-owned surfaces only. Native Frappe calls keep
        // their existing transport and message ownership. fetch prevents native
        // HTTP handlers from showing a second/stale dialog before our owner runs.
        const runtime = frappeRuntime();
        if (!/^[a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)+$/.test(String(method || ""))
            || !runtime || !runtime.csrf_token || typeof window.fetch !== "function") {
            throw normalizeError(null, options);
        }
        const body = new URLSearchParams();
        Object.entries(args).forEach(([key, value]) => {
            if (value !== undefined) body.set(key, value !== null && typeof value === "object" ? JSON.stringify(value) : String(value == null ? "" : value));
        });
        let frozen = false;
        try {
            if (options.freeze && runtime.dom && typeof runtime.dom.freeze === "function") {
                runtime.dom.freeze(options.freezeMessage || "");
                frozen = true;
            }
            const response = await window.fetch(`/api/method/${method}`, {
                method: "POST", credentials: "same-origin", body,
                headers: {
                    "X-Frappe-CSRF-Token": runtime.csrf_token,
                    "X-Requested-With": "XMLHttpRequest",
                    Accept: "application/json",
                },
            });
            const data = await response.json().catch(() => null);
            if (response.status === 401 || data && data.session_expired
                || response.status === 403 && runtime.session && runtime.session.user === "Guest"
                    && runtime.session.logged_in_user !== "Guest") {
                if (runtime.app && typeof runtime.app.handle_session_expired === "function") {
                    runtime.app.handle_session_expired();
                }
            }
            if (!response.ok || !data || data.exc_type || data.exc || data.session_expired) {
                throw normalizeError({ responseJSON: data || {}, status: response.status }, {
                    ...options,
                    requestReference: response.headers && response.headers.get("X-Frappe-Request-Id"),
                });
            }
            if (data.__messages && runtime._messages) Object.assign(runtime._messages, data.__messages);
            return options.raw === true ? data : data.message;
        } catch (error) {
            throw normalizeError(error, options);
        } finally {
            if (frozen) runtime.dom.unfreeze();
        }
    }

    function rpc(method, args = {}, options = {}) {
        const runtime = frappeRuntime();
        const resolvedMethod = String(method || "").trim();
        if (!resolvedMethod) return Promise.reject(new Error("RPC method is required"));
        if (!runtime || typeof runtime.call !== "function") {
            return Promise.reject(new Error("Frappe RPC is unavailable"));
        }

        const request = {
            method: resolvedMethod,
            args: args && typeof args === "object" ? args : {},
        };
        if (options.freeze !== undefined) request.freeze = options.freeze === true;
        if (options.freezeMessage) request.freeze_message = String(options.freezeMessage);

        return Promise.resolve(runtime.call(request)).then(response => {
            if (options.raw === true) return response;
            if (!response || !Object.prototype.hasOwnProperty.call(response, "message")) return null;
            return response.message;
        });
    }

    function normalizeAssets(items) {
        const source = Array.isArray(items) ? items : [items];
        const seen = new Set();
        const assets = [];
        source.forEach(item => {
            const asset = String(item || "").trim();
            if (!asset || seen.has(asset)) return;
            seen.add(asset);
            assets.push(asset);
        });
        return assets;
    }

    function requireAssets(items) {
        const runtime = frappeRuntime();
        if (!runtime || typeof runtime.require !== "function") {
            return Promise.reject(new Error("Frappe asset loader is unavailable"));
        }

        const assets = normalizeAssets(items);
        if (!assets.length) return Promise.resolve([]);

        // Frappe v16 freezes/unfreezes the Desk once per frappe.require() call.
        // Always submit a whole dependency group in one call so cold page loads
        // cannot flash once per module. The group promise also prevents duplicate
        // concurrent requests when Frappe fires overlapping page lifecycle hooks.
        const key = assets.join("\n");
        if (pendingAssetGroups.has(key)) return pendingAssetGroups.get(key);

        const pending = Promise.resolve(runtime.require(assets))
            .then(() => assets)
            .catch(error => {
                pendingAssetGroups.delete(key);
                throw error;
            });
        pendingAssetGroups.set(key, pending);
        return pending;
    }

    function createLatestRequestGate() {
        let generation = 0;

        function begin(meta = null) {
            generation += 1;
            return Object.freeze({ generation, meta });
        }

        function isCurrent(token) {
            return Boolean(
                token
                && typeof token === "object"
                && Number(token.generation) === generation
            );
        }

        function invalidate() {
            generation += 1;
            return generation;
        }

        return Object.freeze({
            begin,
            isCurrent,
            invalidate,
            generation: () => generation,
        });
    }

    function createLifecycleScope() {
        let disposed = false;
        const cleanups = new Map();
        let sequence = 0;

        function resolvedKey(key) {
            const value = String(key || "").trim();
            if (value) return value;
            sequence += 1;
            return `cleanup:${sequence}`;
        }

        function runCleanup(key) {
            if (!cleanups.has(key)) return false;
            const cleanup = cleanups.get(key);
            cleanups.delete(key);
            try {
                cleanup();
            } catch (error) {
                console.debug(`Almdina frontend cleanup failed: ${key}`, error);
            }
            return true;
        }

        function track(cleanup, key = "") {
            if (typeof cleanup !== "function") return null;
            if (disposed) {
                cleanup();
                return null;
            }
            const resolved = resolvedKey(key);
            runCleanup(resolved);
            cleanups.set(resolved, cleanup);
            return resolved;
        }

        function listen(target, eventName, handler, options, key = "") {
            if (!target || typeof target.addEventListener !== "function" || typeof handler !== "function") {
                return null;
            }
            const event = String(eventName || "").trim();
            if (!event) return null;
            target.addEventListener(event, handler, options);
            return track(() => target.removeEventListener(event, handler, options), key || `event:${event}`);
        }

        function timeout(callback, delay = 0, key = "") {
            if (disposed || typeof callback !== "function") return null;
            const timerKey = resolvedKey(key || "timer");
            runCleanup(timerKey);
            const timer = window.setTimeout(() => {
                cleanups.delete(timerKey);
                if (!disposed) callback();
            }, Math.max(0, Number(delay) || 0));
            cleanups.set(timerKey, () => window.clearTimeout(timer));
            return timer;
        }

        function observe(observer, key = "observer") {
            if (!observer || typeof observer.disconnect !== "function") return null;
            return track(() => observer.disconnect(), key);
        }

        function dispose() {
            if (disposed) return false;
            disposed = true;
            Array.from(cleanups.keys()).forEach(runCleanup);
            return true;
        }

        return Object.freeze({
            track,
            listen,
            timeout,
            observe,
            dispose,
            isDisposed: () => disposed,
            cleanupCount: () => cleanups.size,
        });
    }

    function ensureStylesheet(href, options = {}) {
        const resolvedHref = String(href || "").trim();
        if (!resolvedHref) return Promise.reject(new Error("Stylesheet href is required"));
        if (!window.document || !window.document.head) {
            return Promise.reject(new Error("Document head is unavailable"));
        }

        const id = String(options.id || "").trim();
        let existing = id ? window.document.getElementById(id) : null;
        if (!existing && typeof window.document.querySelector === "function") {
            existing = window.document.querySelector(`link[rel="stylesheet"][href="${resolvedHref}"]`);
        }
        if (existing) return Promise.resolve(existing);

        return new Promise((resolve, reject) => {
            const link = window.document.createElement("link");
            link.rel = "stylesheet";
            link.href = resolvedHref;
            if (id) link.id = id;
            link.onload = () => resolve(link);
            link.onerror = () => reject(new Error(`Failed to load stylesheet: ${resolvedHref}`));
            window.document.head.appendChild(link);
        });
    }

    window.AlmdinaFrontend = Object.freeze({
        rpc,
        errorMessage,
        normalizeError,
        ownedRpc,
        requireAssets,
        createLatestRequestGate,
        createLifecycleScope,
        ensureStylesheet,
    });
})();
