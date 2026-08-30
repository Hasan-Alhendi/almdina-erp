(() => {
    "use strict";

    const root = window.AlmdinaDcoRecovery = window.AlmdinaDcoRecovery || Object.create(null);
    if (root.LocalDraftRepository) return;

    const RECORD_SCHEMA_VERSION = 2;
    const LEGACY_RECORD_SCHEMA_VERSION = 1;
    const DEFAULT_MAX_PAYLOAD_BYTES = 512 * 1024;
    const TARGET_DOCTYPE = "Door Cutting Order";
    const OFFICIAL_SAVE_STATES = Object.freeze({
        ACTIVE: "ACTIVE",
        PENDING_RECONCILIATION: "PENDING_RECONCILIATION",
    });

    class LocalDraftRepositoryError extends Error {
        constructor(code, message, cause = null) {
            super(message);
            this.name = "LocalDraftRepositoryError";
            this.code = code;
            this.cause = cause;
        }
    }

    function fail(error, fallback = "storage_failure") {
        return {
            ok: false,
            error: Object.freeze({
                code: String(error && error.code || fallback),
                message: String(error && error.message || "Local recovery storage failed"),
            }),
        };
    }

    function succeed(value) {
        return { ok: true, value };
    }

    function required(value, fieldname) {
        const resolved = String(value || "").trim();
        if (!resolved) {
            throw new LocalDraftRepositoryError("invalid_identity", `${fieldname} is required`);
        }
        return resolved;
    }

    function segment(value) {
        return encodeURIComponent(String(value));
    }

    function namespaceOf(identity) {
        const site = required(identity && identity.site, "site");
        const user = required(identity && identity.user, "user");
        const targetDoctype = required(
            identity && identity.target_doctype || TARGET_DOCTYPE,
            "target_doctype"
        );
        if (targetDoctype !== TARGET_DOCTYPE) {
            throw new LocalDraftRepositoryError("invalid_identity", "Local repository is bounded to Door Cutting Order");
        }
        return {
            site,
            user,
            target_doctype: targetDoctype,
            namespace_key: [site, user, targetDoctype].map(segment).join("::"),
        };
    }

    function storageKey(identity) {
        const namespace = namespaceOf(identity);
        const draftId = required(identity && identity.draft_id, "draft_id");
        return `${namespace.namespace_key}::${segment(draftId)}`;
    }

    function isTimestamp(value) {
        return typeof value === "string" && Number.isFinite(Date.parse(value));
    }

    function recordEnvelope(record) {
        return Object.freeze({
            schema_version: record.schema_version,
            draft_id: record.draft_id,
            mode: record.mode,
            dirty_scope: record.dirty_scope,
            target_doctype: record.target_doctype,
            target_name: record.target_name,
            session_origin_modified: record.session_origin_modified,
            expected_server_modified: record.expected_server_modified,
            tab_session_id: record.tab_session_id,
            recovery_revision: record.recovery_revision,
            created_at: record.created_at,
            captured_at: record.captured_at,
            official_save_state: record.official_save_state,
            official_save_attempted_at: record.official_save_attempted_at,
            payload_hash: record.payload_hash,
            payload: record.payload,
            asset_refs: Object.freeze([...(record.asset_refs || [])]),
        });
    }

    function create(options = {}) {
        const indexed = root.IndexedDb;
        const projection = root.Projection;
        if (!indexed || !projection) {
            throw new LocalDraftRepositoryError("dependency_unavailable", "Recovery infrastructure is incomplete");
        }
        const gateway = options.gateway || indexed.createGateway(options);
        const clock = typeof options.clock === "function" ? options.clock : () => new Date().toISOString();
        const maxPayloadBytes = Math.max(1024, Number(options.maxPayloadBytes) || DEFAULT_MAX_PAYLOAD_BYTES);
        const TextEncoderImpl = options.TextEncoder || window.TextEncoder;

        function payloadBytes(serialized) {
            if (typeof TextEncoderImpl === "function") {
                return new TextEncoderImpl().encode(serialized).byteLength;
            }
            return serialized.length;
        }

        function sameRevisionContent(left, right) {
            const comparable = (record) => ({
                schema_version: record.schema_version,
                draft_id: record.draft_id,
                mode: record.mode,
                dirty_scope: record.dirty_scope,
                target_doctype: record.target_doctype,
                target_name: record.target_name,
                session_origin_modified: record.session_origin_modified,
                expected_server_modified: record.expected_server_modified,
                tab_session_id: record.tab_session_id,
                recovery_revision: record.recovery_revision,
                official_save_state: record.official_save_state,
                official_save_attempted_at: record.official_save_attempted_at,
                payload_hash: record.payload_hash,
                asset_refs: record.asset_refs || [],
            });
            return projection.canonicalStringify(comparable(left))
                === projection.canonicalStringify(comparable(right));
        }

        function nextSaveAttemptTimestamp(previousAttemptedAt) {
            const current = String(clock() || "");
            if (!isTimestamp(current)) {
                throw new LocalDraftRepositoryError(
                    "invalid_timestamp",
                    "Recovery official Save timestamp is invalid"
                );
            }
            if (
                previousAttemptedAt
                && Date.parse(current) <= Date.parse(previousAttemptedAt)
            ) {
                return new Date(Date.parse(previousAttemptedAt) + 1).toISOString();
            }
            return current;
        }

        async function verifyRecord(record, expectedNamespace = null) {
            if (!record || typeof record !== "object") {
                throw new LocalDraftRepositoryError("corrupt_record", "Recovery record is unreadable");
            }
            if (Number(record.schema_version) > RECORD_SCHEMA_VERSION) {
                throw new LocalDraftRepositoryError("unknown_schema", "Recovery record uses a newer schema");
            }
            if (![LEGACY_RECORD_SCHEMA_VERSION, RECORD_SCHEMA_VERSION].includes(Number(record.schema_version))) {
                throw new LocalDraftRepositoryError("incompatible_schema", "Recovery record schema is incompatible");
            }
            const officialSaveState = Number(record.schema_version) === LEGACY_RECORD_SCHEMA_VERSION
                ? OFFICIAL_SAVE_STATES.ACTIVE
                : String(record.official_save_state || "");
            const officialSaveAttemptedAt = Number(record.schema_version) === LEGACY_RECORD_SCHEMA_VERSION
                ? null
                : record.official_save_attempted_at;
            if (!Object.values(OFFICIAL_SAVE_STATES).includes(officialSaveState)) {
                throw new LocalDraftRepositoryError("corrupt_record", "Recovery official Save state is invalid");
            }
            if (officialSaveAttemptedAt !== null && !isTimestamp(officialSaveAttemptedAt)) {
                throw new LocalDraftRepositoryError("corrupt_record", "Recovery official Save timestamp is invalid");
            }
            if (
                officialSaveState === OFFICIAL_SAVE_STATES.PENDING_RECONCILIATION
                && officialSaveAttemptedAt === null
            ) {
                throw new LocalDraftRepositoryError(
                    "corrupt_record",
                    "Pending recovery is missing its official Save attempt"
                );
            }
            const namespace = namespaceOf(record);
            if (expectedNamespace && namespace.namespace_key !== expectedNamespace) {
                throw new LocalDraftRepositoryError("identity_mismatch", "Recovery namespace does not match");
            }
            if (record.storage_key !== storageKey(record)) {
                throw new LocalDraftRepositoryError("corrupt_record", "Recovery storage identity is inconsistent");
            }
            if (!["NEW", "EDIT"].includes(record.mode)) {
                throw new LocalDraftRepositoryError("corrupt_record", "Recovery mode is invalid");
            }
            if (!projection.DIRTY_SCOPES.includes(record.dirty_scope)) {
                throw new LocalDraftRepositoryError("corrupt_record", "Recovery dirty scope is invalid");
            }
            if (!Number.isSafeInteger(record.recovery_revision) || record.recovery_revision < 1) {
                throw new LocalDraftRepositoryError("corrupt_record", "Recovery revision is invalid");
            }
            required(record.draft_id, "draft_id");
            required(record.tab_session_id, "tab_session_id");
            if (!isTimestamp(record.created_at) || !isTimestamp(record.captured_at)) {
                throw new LocalDraftRepositoryError("corrupt_record", "Recovery timestamp is invalid");
            }
            if (record.mode === "NEW") {
                if (
                    record.target_name !== null
                    || record.session_origin_modified !== null
                    || record.expected_server_modified !== null
                ) {
                    throw new LocalDraftRepositoryError("invalid_new_identity", "Unreconciled NEW recovery has server identity");
                }
            } else if (
                !String(record.target_name || "").trim()
                || !String(record.session_origin_modified || "").trim()
                || !String(record.expected_server_modified || "").trim()
            ) {
                throw new LocalDraftRepositoryError("invalid_edit_identity", "EDIT recovery version identity is incomplete");
            }
            if (!Array.isArray(record.asset_refs) || record.asset_refs.some((item) => !String(item || "").trim())) {
                throw new LocalDraftRepositoryError("corrupt_record", "Recovery asset references are invalid");
            }
            const payload = projection.deserialize(record.payload, record.dirty_scope);
            const serialized = projection.serialize(payload);
            if (payloadBytes(serialized) > maxPayloadBytes) {
                throw new LocalDraftRepositoryError("payload_too_large", "Recovery payload exceeds its size limit");
            }
            const digest = await gateway.sha256(serialized);
            if (digest !== record.payload_hash) {
                throw new LocalDraftRepositoryError("integrity_mismatch", "Recovery payload integrity check failed");
            }
            return {
                ...record,
                official_save_state: officialSaveState,
                official_save_attempted_at: officialSaveAttemptedAt,
                payload,
            };
        }

        async function write(input) {
            try {
                const namespace = namespaceOf(input);
                const mode = String(input && input.mode || "").toUpperCase();
                const dirtyScope = String(input && input.dirty_scope || "").toUpperCase();
                const draftId = required(input && input.draft_id, "draft_id");
                const tabSessionId = required(input && input.tab_session_id, "tab_session_id");
                const revision = Number(input && input.recovery_revision);
                const expectedRevision = Number(input && input.expected_recovery_revision);
                const capturedAt = String(input && input.captured_at || clock());
                if (!["NEW", "EDIT"].includes(mode)) {
                    throw new LocalDraftRepositoryError("invalid_mode", "Recovery mode is invalid");
                }
                if (!projection.DIRTY_SCOPES.includes(dirtyScope)) {
                    throw new LocalDraftRepositoryError("invalid_dirty_scope", "Recovery dirty scope is invalid");
                }
                if (!Number.isSafeInteger(revision) || revision < 1) {
                    throw new LocalDraftRepositoryError("invalid_revision", "Recovery revision must be a positive integer");
                }
                if (
                    !Number.isSafeInteger(expectedRevision)
                    || expectedRevision < 0
                    || expectedRevision >= revision
                ) {
                    throw new LocalDraftRepositoryError(
                        "invalid_expected_revision",
                        "Expected recovery revision must precede the write revision"
                    );
                }
                if (!isTimestamp(capturedAt)) {
                    throw new LocalDraftRepositoryError("invalid_timestamp", "Recovery capture timestamp is invalid");
                }
                const targetName = mode === "EDIT" ? required(input.target_name, "target_name") : null;
                const sessionOrigin = mode === "EDIT"
                    ? required(input.session_origin_modified, "session_origin_modified")
                    : null;
                const expectedServer = mode === "EDIT"
                    ? required(input.expected_server_modified, "expected_server_modified")
                    : null;
                if (mode === "NEW" && (
                    input.target_name != null
                    || input.session_origin_modified != null
                    || input.expected_server_modified != null
                )) {
                    throw new LocalDraftRepositoryError("invalid_new_identity", "NEW recovery server identity must remain null");
                }
                const payload = projection.deserialize(input.payload, dirtyScope);
                const serialized = projection.serialize(payload);
                if (payloadBytes(serialized) > maxPayloadBytes) {
                    throw new LocalDraftRepositoryError("payload_too_large", "Recovery payload exceeds its size limit");
                }
                const payloadHash = await gateway.sha256(serialized);
                const key = storageKey({ ...namespace, draft_id: draftId });
                const now = capturedAt;
                const next = {
                    storage_key: key,
                    namespace_key: namespace.namespace_key,
                    target_key: `${namespace.namespace_key}::${mode}::${segment(targetName || "")}`,
                    schema_version: RECORD_SCHEMA_VERSION,
                    site: namespace.site,
                    user: namespace.user,
                    target_doctype: namespace.target_doctype,
                    draft_id: draftId,
                    mode,
                    dirty_scope: dirtyScope,
                    target_name: targetName,
                    session_origin_modified: sessionOrigin,
                    expected_server_modified: expectedServer,
                    tab_session_id: tabSessionId,
                    recovery_revision: revision,
                    created_at: now,
                    captured_at: now,
                    official_save_state: OFFICIAL_SAVE_STATES.ACTIVE,
                    official_save_attempted_at: null,
                    payload_hash: payloadHash,
                    payload,
                    asset_refs: [...new Set((input.asset_refs || []).map((item) => required(item, "asset_id")))].sort(),
                };
                const stored = await gateway.transaction(
                    [indexed.DRAFT_STORE],
                    "readwrite",
                    async (stores, request) => {
                        const drafts = stores[indexed.DRAFT_STORE];
                        const current = await request(drafts.get(key));
                        if (current) {
                            next.official_save_state = String(
                                current.official_save_state || OFFICIAL_SAVE_STATES.ACTIVE
                            );
                            next.official_save_attempted_at = current.official_save_attempted_at || null;
                        }
                        if (current && Number(current.recovery_revision) > revision) {
                            throw new LocalDraftRepositoryError("stale_revision", "A newer local checkpoint already exists");
                        }
                        if (current && Number(current.recovery_revision) === revision) {
                            if (sameRevisionContent(current, next)) return current;
                            throw new LocalDraftRepositoryError("revision_conflict", "Recovery revision has different content");
                        }
                        if (!current && expectedRevision !== 0) {
                            throw new LocalDraftRepositoryError("stale_revision", "Recovery draft base no longer exists");
                        }
                        if (current && Number(current.recovery_revision) !== expectedRevision) {
                            throw new LocalDraftRepositoryError("stale_revision", "Recovery draft changed from its expected base");
                        }
                        if (current) next.created_at = current.created_at;
                        await request(drafts.put(next));
                        return next;
                    }
                );
                return succeed(recordEnvelope(stored));
            } catch (error) {
                return fail(error);
            }
        }

        async function read(identity) {
            try {
                const namespace = namespaceOf(identity);
                const key = storageKey(identity);
                const record = await gateway.transaction(
                    [indexed.DRAFT_STORE],
                    "readonly",
                    (stores, request) => request(stores[indexed.DRAFT_STORE].get(key))
                );
                if (!record) return succeed(null);
                return succeed(recordEnvelope(await verifyRecord(record, namespace.namespace_key)));
            } catch (error) {
                return fail(error);
            }
        }

        async function discover(identity = {}) {
            try {
                const namespace = namespaceOf(identity);
                const records = await gateway.transaction(
                    [indexed.DRAFT_STORE],
                    "readonly",
                    (stores, request) => request(
                        stores[indexed.DRAFT_STORE].index("namespace_key").getAll(namespace.namespace_key)
                    )
                );
                const accepted = [];
                const rejected = [];
                for (const record of records || []) {
                    if (identity.mode && record.mode !== String(identity.mode).toUpperCase()) continue;
                    if (identity.target_name !== undefined && record.target_name !== identity.target_name) continue;
                    try {
                        accepted.push(recordEnvelope(await verifyRecord(record, namespace.namespace_key)));
                    } catch (error) {
                        rejected.push({
                            draft_id: String(record && record.draft_id || ""),
                            code: String(error && error.code || "corrupt_record"),
                        });
                    }
                }
                accepted.sort((left, right) => {
                    const time = Date.parse(right.captured_at) - Date.parse(left.captured_at);
                    return time || right.recovery_revision - left.recovery_revision || left.draft_id.localeCompare(right.draft_id);
                });
                return succeed(Object.freeze({ records: accepted, rejected }));
            } catch (error) {
                return fail(error);
            }
        }

        async function setOfficialSaveState(
            identity,
            saveState,
            expectedRevision = null,
            expectedAttemptedAt = undefined
        ) {
            try {
                const resolvedState = String(saveState || "");
                if (!Object.values(OFFICIAL_SAVE_STATES).includes(resolvedState)) {
                    throw new LocalDraftRepositoryError("invalid_save_state", "Recovery official Save state is invalid");
                }
                if (expectedAttemptedAt === undefined) {
                    throw new LocalDraftRepositoryError(
                        "invalid_save_attempt",
                        "Recovery official Save transition requires its expected attempt"
                    );
                }
                const expectedAttempt = expectedAttemptedAt == null
                    ? null
                    : String(expectedAttemptedAt);
                if (expectedAttempt !== null && !isTimestamp(expectedAttempt)) {
                    throw new LocalDraftRepositoryError(
                        "invalid_timestamp",
                        "Recovery expected official Save timestamp is invalid"
                    );
                }
                const key = storageKey(identity);
                const stored = await gateway.transaction(
                    [indexed.DRAFT_STORE],
                    "readwrite",
                    async (stores, request) => {
                        const drafts = stores[indexed.DRAFT_STORE];
                        const current = await request(drafts.get(key));
                        if (!current) {
                            throw new LocalDraftRepositoryError("draft_not_found", "Recovery draft does not exist");
                        }
                        if (current.mode !== "NEW") {
                            throw new LocalDraftRepositoryError("invalid_mode", "Official Save reconciliation is NEW-only");
                        }
                        if (
                            expectedRevision !== null
                            && Number(current.recovery_revision) !== Number(expectedRevision)
                        ) {
                            throw new LocalDraftRepositoryError("stale_revision", "Recovery draft changed before official Save");
                        }
                        const currentState = Number(current.schema_version) === LEGACY_RECORD_SCHEMA_VERSION
                            ? OFFICIAL_SAVE_STATES.ACTIVE
                            : String(current.official_save_state || "");
                        const currentAttempt = Number(current.schema_version) === LEGACY_RECORD_SCHEMA_VERSION
                            ? null
                            : (current.official_save_attempted_at || null);
                        const requiredCurrentState = resolvedState === OFFICIAL_SAVE_STATES.PENDING_RECONCILIATION
                            ? OFFICIAL_SAVE_STATES.ACTIVE
                            : OFFICIAL_SAVE_STATES.PENDING_RECONCILIATION;
                        if (
                            currentState !== requiredCurrentState
                            || currentAttempt !== expectedAttempt
                        ) {
                            throw new LocalDraftRepositoryError(
                                "save_attempt_conflict",
                                "Recovery official Save attempt changed before reconciliation"
                            );
                        }
                        const attemptedAt = resolvedState === OFFICIAL_SAVE_STATES.PENDING_RECONCILIATION
                            ? nextSaveAttemptTimestamp(currentAttempt)
                            : currentAttempt;
                        const next = {
                            ...current,
                            schema_version: RECORD_SCHEMA_VERSION,
                            official_save_state: resolvedState,
                            official_save_attempted_at: attemptedAt,
                        };
                        await request(drafts.put(next));
                        return next;
                    }
                );
                return succeed(recordEnvelope(stored));
            } catch (error) {
                return fail(error);
            }
        }

        async function remove(identity) {
            try {
                const key = storageKey(identity);
                const removed = await gateway.transaction(
                    [indexed.DRAFT_STORE, indexed.ASSET_STORE],
                    "readwrite",
                    async (stores, request) => {
                        const drafts = stores[indexed.DRAFT_STORE];
                        const assets = stores[indexed.ASSET_STORE];
                        const current = await request(drafts.get(key));
                        if (!current) return false;
                        const assetKeys = await request(assets.index("draft_key").getAllKeys(key));
                        for (const assetKey of assetKeys || []) await request(assets.delete(assetKey));
                        await request(drafts.delete(key));
                        return true;
                    }
                );
                return succeed(removed);
            } catch (error) {
                return fail(error);
            }
        }

        return Object.freeze({
            schemaVersion: RECORD_SCHEMA_VERSION,
            maxPayloadBytes,
            storageKey,
            createIdentity: () => gateway.randomUUID(),
            hashCanonical: (value) => gateway.sha256(projection.canonicalStringify(value)),
            write,
            read,
            discover,
            setOfficialSaveState,
            delete: remove,
            requestPersistence: () => gateway.requestPersistence(),
        });
    }

    root.LocalDraftRepository = Object.freeze({
        RECORD_SCHEMA_VERSION,
        LEGACY_RECORD_SCHEMA_VERSION,
        DEFAULT_MAX_PAYLOAD_BYTES,
        TARGET_DOCTYPE,
        OFFICIAL_SAVE_STATES,
        LocalDraftRepositoryError,
        create,
        storageKey,
    });
})();
