(() => {
    "use strict";

    if (window.AlmdinaFrontend) return;

    function frappeRuntime() {
        if (window.frappe) return window.frappe;
        if (typeof frappe !== "undefined") return frappe;
        return null;
    }

    function errorMessage(error, fallback = "") {
        if (error && typeof error === "object") {
            const candidates = [
                error.message,
                error.exc,
                error._server_messages,
            ];
            const value = candidates.find(candidate => typeof candidate === "string" && candidate.trim());
            if (value) return value.trim();
        }
        if (typeof error === "string" && error.trim()) return error.trim();
        return String(fallback || "");
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
        createLatestRequestGate,
        createLifecycleScope,
        ensureStylesheet,
    });
})();
