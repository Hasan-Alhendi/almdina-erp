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
        OFFICIAL_SAVING: "OFFICIAL_SAVING",
        PENDING_RECONCILIATION: "PENDING_RECONCILIATION",
        COMPLETED: "COMPLETED",
        DISPOSED: "DISPOSED",
    });
    const OFFICIAL_SAVE_STATES = Object.freeze({
        ACTIVE: "ACTIVE",
        PENDING_RECONCILIATION: "PENDING_RECONCILIATION",
        COMPLETED: "COMPLETED",
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

        let revision = Number(options.recoveryRevision || 0);
        let savedRevision = Number(options.savedRevision == null ? revision : options.savedRevision);
        let dirtyScope = options.dirtyScope == null
            ? null
            : String(options.dirtyScope).toUpperCase();
        let officialSaveState = String(
            options.officialSaveState || OFFICIAL_SAVE_STATES.ACTIVE
        );
        let officialSaveAttemptedAt = options.officialSaveAttemptedAt == null
            ? null
            : required(options.officialSaveAttemptedAt, "official_save_attempted_at");
        if (
            !Number.isSafeInteger(revision)
            || !Number.isSafeInteger(savedRevision)
            || revision < 0
            || savedRevision < 0
            || savedRevision > revision
        ) {
            throw new CheckpointSessionError("invalid_session", "Recovery revisions are invalid");
        }
        if (
            dirtyScope !== null
            && (!root.Projection || !root.Projection.DIRTY_SCOPES.includes(dirtyScope))
        ) {
            throw new CheckpointSessionError("invalid_dirty_scope", "Recovery dirty scope is invalid");
        }
        if (!Object.values(OFFICIAL_SAVE_STATES).includes(officialSaveState)) {
            throw new CheckpointSessionError("invalid_session", "Official Save state is invalid");
        }
        let state = officialSaveState === OFFICIAL_SAVE_STATES.PENDING_RECONCILIATION
            ? STATES.PENDING_RECONCILIATION
            : (savedRevision > 0 ? STATES.LOCAL_SAVED : STATES.READY_CLEAN);
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
                official_save_state: officialSaveState,
                official_save_attempted_at: officialSaveAttemptedAt,
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
            if (state === STATES.RESTORING || officialSaveState === OFFICIAL_SAVE_STATES.COMPLETED) {
                return snapshot();
            }
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
            if (officialSaveState === OFFICIAL_SAVE_STATES.PENDING_RECONCILIATION) {
                return transition(STATES.PENDING_RECONCILIATION);
            }
            return transition(STATES.DIRTY);
        }

        function beginRestore() {
            if (disposed || mode !== "NEW") return false;
            if (officialSaveState === OFFICIAL_SAVE_STATES.COMPLETED) return false;
            transition(STATES.RESTORING);
            return true;
        }

        function completeRestore() {
            if (disposed || state !== STATES.RESTORING) return false;
            transition(
                officialSaveState === OFFICIAL_SAVE_STATES.PENDING_RECONCILIATION
                    ? STATES.PENDING_RECONCILIATION
                    : STATES.READY_CLEAN
            );
            return true;
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
                if (![STATES.RESTORING, STATES.OFFICIAL_SAVING, STATES.COMPLETED].includes(state)) {
                    transition(
                        officialSaveState === OFFICIAL_SAVE_STATES.PENDING_RECONCILIATION
                            ? STATES.PENDING_RECONCILIATION
                            : (savedRevision > 0 ? STATES.LOCAL_SAVED : STATES.READY_CLEAN)
                    );
                }
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
            const storedOfficialSaveState = String(
                result.value && result.value.official_save_state || ""
            );
            if (
                mode === "NEW"
                && [
                    OFFICIAL_SAVE_STATES.ACTIVE,
                    OFFICIAL_SAVE_STATES.PENDING_RECONCILIATION,
                ].includes(storedOfficialSaveState)
            ) {
                officialSaveState = storedOfficialSaveState;
                officialSaveAttemptedAt = result.value.official_save_attempted_at || null;
            }
            savedRevision = Math.max(savedRevision, captureRevision);
            if (revision === captureRevision) {
                transition(
                    officialSaveState === OFFICIAL_SAVE_STATES.PENDING_RECONCILIATION
                        ? STATES.PENDING_RECONCILIATION
                        : STATES.LOCAL_SAVED
                );
                return result;
            }
            transition(
                officialSaveState === OFFICIAL_SAVE_STATES.PENDING_RECONCILIATION
                    ? STATES.PENDING_RECONCILIATION
                    : STATES.DIRTY
            );
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

        async function beginOfficialSave() {
            if (disposed || mode !== "NEW") {
                return { ok: false, error: { code: "invalid_mode", message: "Official first Save is NEW-only" } };
            }
            if (savedRevision < revision) {
                return { ok: false, error: { code: "checkpoint_required", message: "Latest recovery checkpoint is not saved" } };
            }
            if (typeof repository.setOfficialSaveState !== "function") {
                return { ok: false, error: { code: "storage_failure", message: "Official Save state storage is unavailable" } };
            }
            const result = await repository.setOfficialSaveState(
                identity,
                OFFICIAL_SAVE_STATES.PENDING_RECONCILIATION,
                revision,
                officialSaveAttemptedAt
            );
            if (!result || result.ok !== true) return result;
            if (disposed) return { ...result, disposed: true };
            officialSaveState = OFFICIAL_SAVE_STATES.PENDING_RECONCILIATION;
            officialSaveAttemptedAt = result.value.official_save_attempted_at;
            transition(STATES.OFFICIAL_SAVING);
            return result;
        }

        function markPendingReconciliation() {
            if (disposed || mode !== "NEW") return false;
            officialSaveState = OFFICIAL_SAVE_STATES.PENDING_RECONCILIATION;
            transition(STATES.PENDING_RECONCILIATION);
            return true;
        }

        async function resumeAfterProvenFailure() {
            if (disposed || mode !== "NEW") return false;
            const reconciledAttempt = officialSaveAttemptedAt;
            const result = typeof repository.setOfficialSaveState === "function"
                ? await repository.setOfficialSaveState(
                    identity,
                    OFFICIAL_SAVE_STATES.ACTIVE,
                    revision,
                    reconciledAttempt
                )
                : { ok: false };
            if (
                !result
                || (result.ok !== true && (!result.error || result.error.code !== "draft_not_found"))
            ) return false;
            officialSaveState = OFFICIAL_SAVE_STATES.ACTIVE;
            officialSaveAttemptedAt = result.value
                ? result.value.official_save_attempted_at || null
                : reconciledAttempt;
            transition(savedRevision >= revision ? STATES.LOCAL_SAVED : STATES.DIRTY);
            return true;
        }

        function adoptPersistedOfficialSaveState(record, expectedAttemptedAt) {
            if (disposed || mode !== "NEW" || !record) return false;
            const recordRevision = Number(record.recovery_revision);
            const expectedAttempt = String(expectedAttemptedAt || "").trim();
            if (
                !Number.isInteger(recordRevision)
                || recordRevision !== revision
                || String(record.official_save_state || "") !== OFFICIAL_SAVE_STATES.ACTIVE
                || String(record.official_save_attempted_at || "").trim() !== expectedAttempt
            ) return false;
            savedRevision = recordRevision;
            dirtyScope = null;
            officialSaveState = OFFICIAL_SAVE_STATES.ACTIVE;
            officialSaveAttemptedAt = record.official_save_attempted_at || null;
            transition(STATES.LOCAL_SAVED);
            return true;
        }

        function complete() {
            if (disposed || mode !== "NEW") return false;
            officialSaveState = OFFICIAL_SAVE_STATES.COMPLETED;
            transition(STATES.COMPLETED);
            return true;
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
            beginRestore,
            completeRestore,
            advanceExpectedServerModified,
            flush,
            beginOfficialSave,
            markPendingReconciliation,
            resumeAfterProvenFailure,
            adoptPersistedOfficialSaveState,
            complete,
            dispose,
        });
    }

    root.CheckpointSession = Object.freeze({
        STATES,
        OFFICIAL_SAVE_STATES,
        CheckpointSessionError,
        create,
    });
})();
