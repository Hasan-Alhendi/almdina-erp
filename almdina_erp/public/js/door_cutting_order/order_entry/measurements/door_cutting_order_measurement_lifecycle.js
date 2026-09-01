(() => {
    "use strict";

    const frontend = window.AlmdinaFrontend;
    if (!frontend || typeof frontend.createLifecycleScope !== "function") {
        throw new Error("AlmdinaFrontend.createLifecycleScope is required before measurement lifecycle");
    }
    const documentContext = window.AlmdinaDocumentContext;
    if (
        !documentContext
        || typeof documentContext.capture !== "function"
        || typeof documentContext.isCurrent !== "function"
    ) {
        throw new Error("AlmdinaDocumentContext is required before measurement lifecycle");
    }

    const scopesByForm = new WeakMap();
    const featureOwners = new Map();
    const RENDER_REVISION_FIELD = "__almdinaMeasurementRenderRevision";
    const READY_STATE_FIELD = "__almdinaMeasurementReadyState";
    const FEATURE_REGISTRATION_KEY = "measurement-feature-registration";
    let featureRevision = 0;

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
        const documentToken = documentContext.capture(frm);

        function isCurrent() {
            return !scope.isDisposed()
                && documentContext.isCurrent(frm, documentToken);
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

    function measurementField(frm) {
        const fields = frm && frm.fields_dict;
        if (!fields || !Object.prototype.hasOwnProperty.call(fields, "pieces_fast_entry")) {
            return null;
        }
        return fields.pieces_fast_entry || null;
    }

    function measurementRoot(frm) {
        const field = measurementField(frm);
        if (!field || !field.$wrapper) return null;
        if (typeof field.$wrapper.get === "function") return field.$wrapper.get(0) || null;
        return field.$wrapper.nodeType ? field.$wrapper : (field.$wrapper[0] || null);
    }

    function surfaceState(frm) {
        const field = measurementField(frm);
        if (!field) {
            return { applicable: false, ready: true, root: null };
        }

        const root = measurementRoot(frm);
        if (!root || typeof root.querySelector !== "function") {
            return { applicable: true, ready: false, root };
        }

        const shells = typeof root.querySelectorAll === "function"
            ? root.querySelectorAll(".dco-fast-entry-shell")
            : [];
        const shell = shells.length === 1 ? shells[0] : null;
        const ready = Boolean(
            shell
            && root.querySelector(".dco-fast-entry-toolbar")
            && root.querySelector(".dco-fast-entry-scroll")
            && root.querySelector(".dco-fast-table")
            && root.querySelector(".dco-fast-table thead tr")
            && root.querySelector(".dco-fast-table tbody")
        );
        return { applicable: true, ready, root };
    }

    function markRendered(frm) {
        const state = surfaceState(frm);
        if (!state.applicable || !state.root) return false;
        state.root[RENDER_REVISION_FIELD] = (
            Number(state.root[RENDER_REVISION_FIELD] || 0) + 1
        );
        state.root[READY_STATE_FIELD] = null;
        return true;
    }

    function reconcile(frm) {
        const token = documentContext.capture(frm);
        if (!token || !documentContext.isCurrent(frm, token)) return false;

        const state = surfaceState(frm);
        if (!state.applicable) return true;
        if (!state.ready || !state.root) return false;

        const root = state.root;
        const renderRevision = Number(root[RENDER_REVISION_FIELD] || 0);
        const registryRevision = featureRevision;
        let complete = true;

        featureOwners.forEach((owner, key) => {
            if (!documentContext.isCurrent(frm, token)) {
                complete = false;
                return;
            }
            try {
                if (owner.reconcile(frm, root) === false) complete = false;
            } catch (error) {
                complete = false;
                console.error(`Measurement surface reconciliation failed: ${key}`, error);
            }
        });

        const settled = surfaceState(frm);
        if (
            !complete
            || !settled.ready
            || settled.root !== root
            || Number(root[RENDER_REVISION_FIELD] || 0) !== renderRevision
            || featureRevision !== registryRevision
            || !documentContext.isCurrent(frm, token)
        ) {
            root[READY_STATE_FIELD] = null;
            return false;
        }

        root[READY_STATE_FIELD] = Object.freeze({
            token: documentContext.capture(frm),
            renderRevision,
            featureRevision: registryRevision,
        });
        return true;
    }

    function isReady(frm) {
        const state = surfaceState(frm);
        if (!state.applicable) return true;
        if (!state.ready || !state.root) return false;

        const readyState = state.root[READY_STATE_FIELD];
        return Boolean(
            readyState
            && readyState.token
            && documentContext.isCurrent(frm, readyState.token)
            && Number(readyState.renderRevision) === Number(state.root[RENDER_REVISION_FIELD] || 0)
            && Number(readyState.featureRevision) === featureRevision
        );
    }

    function recover(frm) {
        let state = surfaceState(frm);
        if (!state.applicable) return true;
        if (!state.ready) {
            const renderer = window.AlmdinaDoorCuttingFastEntry;
            if (!renderer) return false;
            if (typeof renderer.recover === "function") renderer.recover(frm);
            else if (typeof renderer.render === "function") renderer.render(frm);
            else return false;
            state = surfaceState(frm);
        }
        if (!state.ready) return false;
        if (isReady(frm)) return true;
        return reconcile(frm);
    }

    function rendered(frm) {
        if (!markRendered(frm)) return false;
        return reconcile(frm);
    }

    function registerFeature(key, owner) {
        const resolvedKey = String(key || "").trim();
        const reconcileFeature = typeof owner === "function"
            ? owner
            : (owner && owner.reconcile);
        if (!resolvedKey || typeof reconcileFeature !== "function") return false;

        featureOwners.set(resolvedKey, Object.freeze({ reconcile: reconcileFeature }));
        featureRevision += 1;

        const frm = window.cur_frm;
        if (frm && frm.doctype === "Door Cutting Order") {
            schedule(
                frm,
                FEATURE_REGISTRATION_KEY,
                () => reconcile(frm),
                { immediate: false, frame: true }
            );
        }
        return true;
    }

    window.AlmdinaMeasurementLifecycle = Object.freeze({
        schedule,
        retry,
        cancel,
        cancelAll,
        registerFeature,
        rendered,
        reconcile,
        recover,
        isReady,
    });

    const fastKeyboard = window.AlmdinaFastEntryKeyboardUX;
    if (fastKeyboard && typeof fastKeyboard.install === "function") {
        registerFeature("fast-entry-keyboard", frm => fastKeyboard.install(frm));
    }

    if (typeof documentContext.registerSurface === "function") {
        documentContext.registerSurface("measurement-table", {
            isReady,
            recover,
        });
    }
})();
