(() => {
    "use strict";

    const frontend = window.AlmdinaFrontend;
    if (!frontend || typeof frontend.createLifecycleScope !== "function") {
        throw new Error("AlmdinaFrontend.createLifecycleScope is required before measurement lifecycle");
    }

    const scopesByForm = new WeakMap();

    function featureScopes(frm) {
        let scopes = scopesByForm.get(frm);
        if (!scopes) {
            scopes = new Map();
            scopesByForm.set(frm, scopes);
        }
        return scopes;
    }

    function cancel(frm, key) {
        if (!frm) return false;
        const scopes = scopesByForm.get(frm);
        if (!scopes) return false;
        const scope = scopes.get(key);
        if (!scope) return false;
        scopes.delete(key);
        scope.dispose();
        if (!scopes.size) scopesByForm.delete(frm);
        return true;
    }

    function begin(frm, key) {
        if (!frm) throw new Error("Measurement lifecycle requires a form");
        const resolvedKey = String(key || "").trim();
        if (!resolvedKey) throw new Error("Measurement lifecycle requires a feature key");

        cancel(frm, resolvedKey);
        const scope = frontend.createLifecycleScope();
        featureScopes(frm).set(resolvedKey, scope);
        const documentName = String((frm.doc && frm.doc.name) || "");

        function isCurrent() {
            return !scope.isDisposed()
                && String((frm.doc && frm.doc.name) || "") === documentName;
        }

        return { scope, isCurrent, key: resolvedKey };
    }

    function safeRun(task, callback) {
        if (!task.isCurrent() || typeof callback !== "function") return false;
        try {
            callback();
            return true;
        } catch (error) {
            console.error(`Measurement lifecycle task failed: ${task.key}`, error);
            return false;
        }
    }

    function scheduleFrame(task, callback, cleanupKey = "frame") {
        if (!task.isCurrent()) return null;
        if (typeof window.requestAnimationFrame !== "function") {
            return task.scope.timeout(() => safeRun(task, callback), 0, cleanupKey);
        }
        const frame = window.requestAnimationFrame(() => safeRun(task, callback));
        task.scope.track(() => window.cancelAnimationFrame(frame), cleanupKey);
        return frame;
    }

    function schedule(frm, key, callback, options = {}) {
        const task = begin(frm, key);
        const immediate = options.immediate !== false;
        const frame = options.frame !== false;
        const delays = Array.isArray(options.delays) ? options.delays : [];

        if (immediate) safeRun(task, callback);
        if (frame) scheduleFrame(task, callback);
        delays.forEach((delay, index) => {
            task.scope.timeout(
                () => safeRun(task, callback),
                Math.max(0, Number(delay) || 0),
                `delay:${index}:${delay}`
            );
        });
        return task;
    }

    function retry(frm, key, callback, options = {}) {
        const task = begin(frm, key);
        const maxAttempts = Math.max(1, Number(options.maxAttempts) || 1);
        const delay = Math.max(0, Number(options.delay) || 0);
        let attempt = 0;

        function runAttempt() {
            if (!task.isCurrent()) return;
            attempt += 1;
            let complete = false;
            try {
                complete = callback(attempt) === true;
            } catch (error) {
                console.error(`Measurement lifecycle retry failed: ${task.key}`, error);
                complete = true;
            }
            if (complete || attempt >= maxAttempts || !task.isCurrent()) return;
            task.scope.timeout(
                () => scheduleFrame(task, runAttempt, `retry-frame:${attempt + 1}`),
                delay,
                `retry-delay:${attempt + 1}`
            );
        }

        scheduleFrame(task, runAttempt, "retry-frame:1");
        return task;
    }

    function cancelAll(frm) {
        const scopes = frm && scopesByForm.get(frm);
        if (!scopes) return 0;
        const keys = Array.from(scopes.keys());
        keys.forEach(key => cancel(frm, key));
        return keys.length;
    }

    window.AlmdinaMeasurementLifecycle = Object.freeze({
        schedule,
        retry,
        cancel,
        cancelAll,
    });
})();