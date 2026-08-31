(() => {
    "use strict";

    const root = window.AlmdinaDcoRecovery = window.AlmdinaDcoRecovery || Object.create(null);
    if (root.CheckpointSession) return;

    const STATES = Object.freeze({
        READY_CLEAN: "READY_CLEAN",
        DIRTY: "DIRTY",
        LOCAL_SAVING: "LOCAL_SAVING",
        LOCAL_SAVED: "LOCAL_SAVED",
        ERROR: "ERROR",
        RESTORING: "RESTORING",
        DISPOSED: "DISPOSED",
    });

    class CheckpointSessionError extends Error {
        constructor(code, message) {
            super(message);
            this.name = "CheckpointSessionError";
            this.code = code;
        }
    }

    function required(value, fieldname) {
        const resolved = String(value || "").trim();
        if (!resolved) throw new CheckpointSessionError("invalid_session", `${fieldname} is required`);
        return resolved;
    }

    function create(options = {}) {
        const repository = options.repository;
        if (!repository || typeof repository.write !== "function") {
            throw new CheckpointSessionError("invalid_session", "Local draft repository is required");
        }
        if (typeof options.capture !== "function") {
            throw new CheckpointSessionError("invalid_session", "Recovery projection capture is required");
        }
        const mode = String(options.mode || "").toUpperCase();
        if (!["NEW", "EDIT"].includes(mode)) {
            throw new CheckpointSessionError("invalid_session", "Recovery mode is invalid");
        }
        const identity = Object.freeze({
            site: required(options.site, "site"),
            user: required(options.user, "user"),
            target_doctype: "Door Cutting Order",
            draft_id: required(options.draftId, "draft_id"),
        });
        const tabSessionId = required(options.tabSessionId, "tab_session_id");
        const targetName = mode === "EDIT" ? required(options.targetName, "target_name") : null;
        const sessionOriginModified = mode === "EDIT"
            ? required(options.sessionOriginModified, "session_origin_modified")
            : null;
        let expectedServerModified = mode === "EDIT"
            ? required(options.expectedServerModified, "expected_server_modified")
            : null;
        const notify = typeof options.onStateChange === "function" ? options.onStateChange : () => {};

        let state = STATES.READY_CLEAN;
        let revision = 0;
        let savedRevision = 0;
        let dirtyScope = null;
        let lastError = null;
        let inFlight = null;
        let disposed = false;

        function snapshot() {
            return Object.freeze({
                state,
                mode,
                draft_id: identity.draft_id,
                tab_session_id: tabSessionId,
                target_name: targetName,
                session_origin_modified: sessionOriginModified,
                expected_server_modified: expectedServerModified,
                recovery_revision: revision,
                saved_revision: savedRevision,
                dirty_scope: dirtyScope,
                error: lastError,
            });
        }

        function transition(next, error = null) {
            state = next;
            lastError = error;
            const current = snapshot();
            try { notify(current); } catch (notifyError) { /* status observers are non-authoritative */ }
            return current;
        }

        function markDirty(scope = "DCO") {
            if (disposed) return snapshot();
            const resolved = String(scope || "").toUpperCase();
            const projection = root.Projection;
            if (!projection || !projection.DIRTY_SCOPES.includes(resolved)) {
                throw new CheckpointSessionError("invalid_dirty_scope", "Recovery dirty scope is invalid");
            }
            if (dirtyScope && dirtyScope !== resolved && savedRevision < revision) {
                throw new CheckpointSessionError(
                    "multiple_dirty_owners",
                    "Recovery cannot checkpoint competing dirty owners"
                );
            }
            dirtyScope = resolved;
            revision += 1;
            return transition(STATES.DIRTY);
        }

        function advanceExpectedServerModified(modified) {
            if (disposed || mode !== "EDIT") return false;
            const resolved = required(modified, "expected_server_modified");
            if (resolved === expectedServerModified) return false;
            expectedServerModified = resolved;
            markDirty(dirtyScope || "DCO");
            return true;
        }

        async function runFlush() {
            if (disposed) return { ok: false, error: { code: "disposed", message: "Recovery session is disposed" } };
            if (!dirtyScope || savedRevision >= revision) {
                if (state !== STATES.LOCAL_SAVED) transition(STATES.READY_CLEAN);
                return { ok: true, value: null };
            }
            const captureRevision = revision;
            const captureScope = dirtyScope;
            transition(STATES.LOCAL_SAVING);
            let capture;
            try {
                capture = await options.capture({
                    dirtyScope: captureScope,
                    recoveryRevision: captureRevision,
                    session: snapshot(),
                });
            } catch (error) {
                return failFlush(error, "capture_failure");
            }
            if (disposed) return { ok: false, error: { code: "disposed", message: "Recovery session is disposed" } };
            let result;
            try {
                result = await repository.write({
                    ...identity,
                    mode,
                    dirty_scope: captureScope,
                    target_name: targetName,
                    session_origin_modified: sessionOriginModified,
                    expected_server_modified: expectedServerModified,
                    tab_session_id: tabSessionId,
                    recovery_revision: captureRevision,
                    payload: capture && capture.payload,
                    asset_refs: capture && capture.asset_refs || [],
                });
            } catch (error) {
                return failFlush(error, "storage_failure");
            }
            if (!result || result.ok !== true) {
                const error = result && result.error || { code: "storage_failure", message: "Local checkpoint failed" };
                transition(STATES.ERROR, Object.freeze({ ...error }));
                return result || { ok: false, error };
            }
            savedRevision = Math.max(savedRevision, captureRevision);
            if (revision === captureRevision) {
                transition(STATES.LOCAL_SAVED);
                return result;
            }
            transition(STATES.DIRTY);
            return runFlush();
        }

        function failFlush(error, fallbackCode) {
            const failure = {
                ok: false,
                error: Object.freeze({
                    code: String(error && error.code || fallbackCode),
                    message: String(error && error.message || "Local checkpoint failed"),
                }),
            };
            transition(STATES.ERROR, failure.error);
            return failure;
        }

        function flush() {
            if (inFlight) return inFlight;
            inFlight = Promise.resolve()
                .then(runFlush)
                .finally(() => { inFlight = null; });
            return inFlight;
        }

        function dispose() {
            if (disposed) return false;
            disposed = true;
            transition(STATES.DISPOSED);
            return true;
        }

        return Object.freeze({
            identity: () => identity,
            snapshot,
            markDirty,
            advanceExpectedServerModified,
            flush,
            dispose,
        });
    }

    root.CheckpointSession = Object.freeze({ STATES, CheckpointSessionError, create });
})();
