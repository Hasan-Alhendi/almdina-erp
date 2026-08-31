(() => {
    "use strict";

    const root = window.AlmdinaDcoRecovery = window.AlmdinaDcoRecovery || Object.create(null);
    if (root.LocalAssetRepository) return;

    const ASSET_SCHEMA_VERSION = 1;
    const DEFAULT_MAX_ASSET_BYTES = 16 * 1024 * 1024;

    class LocalAssetRepositoryError extends Error {
        constructor(code, message, cause = null) {
            super(message);
            this.name = "LocalAssetRepositoryError";
            this.code = code;
            this.cause = cause;
        }
    }

    function succeed(value) {
        return { ok: true, value };
    }

    function fail(error) {
        return {
            ok: false,
            error: Object.freeze({
                code: String(error && error.code || "asset_storage_failure"),
                message: String(error && error.message || "Local recovery asset storage failed"),
            }),
        };
    }

    function required(value, fieldname) {
        const resolved = String(value || "").trim();
        if (!resolved) throw new LocalAssetRepositoryError("invalid_asset", `${fieldname} is required`);
        return resolved;
    }

    function segment(value) {
        return encodeURIComponent(String(value));
    }

    function create(options = {}) {
        const indexed = root.IndexedDb;
        const drafts = root.LocalDraftRepository;
        if (!indexed || !drafts) {
            throw new LocalAssetRepositoryError("dependency_unavailable", "Recovery infrastructure is incomplete");
        }
        const gateway = options.gateway || indexed.createGateway(options);
        const clock = typeof options.clock === "function" ? options.clock : () => new Date().toISOString();
        const maxAssetBytes = Math.max(1024, Number(options.maxAssetBytes) || DEFAULT_MAX_ASSET_BYTES);

        function keys(identity, assetId) {
            const draftKey = drafts.storageKey(identity);
            const resolvedAssetId = required(assetId, "asset_id");
            return {
                draftKey,
                assetId: resolvedAssetId,
                storageKey: `${draftKey}::asset::${segment(resolvedAssetId)}`,
            };
        }

        function assertBlob(blob) {
            if (!blob || typeof blob.arrayBuffer !== "function" || !Number.isFinite(Number(blob.size))) {
                throw new LocalAssetRepositoryError("invalid_asset", "Recovery asset must be a Blob");
            }
            if (blob.size <= 0) throw new LocalAssetRepositoryError("invalid_asset", "Recovery asset is empty");
            if (blob.size > maxAssetBytes) {
                throw new LocalAssetRepositoryError("asset_too_large", "Recovery asset exceeds its size limit");
            }
        }

        async function write(identity, assetId, blob, metadata = {}) {
            try {
                assertBlob(blob);
                const resolved = keys(identity, assetId);
                const contentHash = await gateway.sha256Bytes(await blob.arrayBuffer());
                const record = {
                    storage_key: resolved.storageKey,
                    draft_key: resolved.draftKey,
                    namespace_key: resolved.draftKey.slice(0, resolved.draftKey.lastIndexOf("::")),
                    schema_version: ASSET_SCHEMA_VERSION,
                    asset_id: resolved.assetId,
                    created_at: String(metadata.created_at || clock()),
                    file_name: String(metadata.file_name || ""),
                    mime_type: String(blob.type || metadata.mime_type || "application/octet-stream"),
                    byte_length: Number(blob.size),
                    content_hash: contentHash,
                    blob,
                };
                const stored = await gateway.transaction(
                    [indexed.DRAFT_STORE, indexed.ASSET_STORE],
                    "readwrite",
                    async (stores, request) => {
                        const draft = await request(stores[indexed.DRAFT_STORE].get(resolved.draftKey));
                        if (!draft) {
                            throw new LocalAssetRepositoryError(
                                "draft_not_found",
                                "Recovery asset must belong to an existing draft"
                            );
                        }
                        const assets = stores[indexed.ASSET_STORE];
                        const current = await request(assets.get(resolved.storageKey));
                        if (current && current.content_hash !== contentHash) {
                            throw new LocalAssetRepositoryError(
                                "asset_conflict",
                                "Recovery asset identity already has different content"
                            );
                        }
                        if (!current) await request(assets.put(record));
                        return current || record;
                    }
                );
                return succeed(Object.freeze({
                    asset_id: stored.asset_id,
                    file_name: stored.file_name,
                    mime_type: stored.mime_type,
                    byte_length: stored.byte_length,
                    content_hash: stored.content_hash,
                    created_at: stored.created_at,
                }));
            } catch (error) {
                return fail(error);
            }
        }

        async function read(identity, assetId) {
            try {
                const resolved = keys(identity, assetId);
                const record = await gateway.transaction(
                    [indexed.ASSET_STORE],
                    "readonly",
                    (stores, request) => request(stores[indexed.ASSET_STORE].get(resolved.storageKey))
                );
                if (!record) return succeed(null);
                if (Number(record.schema_version) > ASSET_SCHEMA_VERSION) {
                    throw new LocalAssetRepositoryError("unknown_schema", "Recovery asset uses a newer schema");
                }
                if (Number(record.schema_version) !== ASSET_SCHEMA_VERSION) {
                    throw new LocalAssetRepositoryError("incompatible_schema", "Recovery asset schema is incompatible");
                }
                assertBlob(record.blob);
                if (record.byte_length !== record.blob.size) {
                    throw new LocalAssetRepositoryError("corrupt_asset", "Recovery asset length is inconsistent");
                }
                const contentHash = await gateway.sha256Bytes(await record.blob.arrayBuffer());
                if (contentHash !== record.content_hash) {
                    throw new LocalAssetRepositoryError("integrity_mismatch", "Recovery asset integrity check failed");
                }
                return succeed(Object.freeze({
                    asset_id: record.asset_id,
                    file_name: record.file_name,
                    mime_type: record.mime_type,
                    byte_length: record.byte_length,
                    content_hash: record.content_hash,
                    created_at: record.created_at,
                    blob: record.blob,
                }));
            } catch (error) {
                return fail(error);
            }
        }

        async function remove(identity, assetId) {
            try {
                const resolved = keys(identity, assetId);
                const removed = await gateway.transaction(
                    [indexed.ASSET_STORE],
                    "readwrite",
                    async (stores, request) => {
                        const assets = stores[indexed.ASSET_STORE];
                        const current = await request(assets.get(resolved.storageKey));
                        if (!current) return false;
                        await request(assets.delete(resolved.storageKey));
                        return true;
                    }
                );
                return succeed(removed);
            } catch (error) {
                return fail(error);
            }
        }

        return Object.freeze({ maxAssetBytes, write, read, delete: remove });
    }

    root.LocalAssetRepository = Object.freeze({
        ASSET_SCHEMA_VERSION,
        DEFAULT_MAX_ASSET_BYTES,
        LocalAssetRepositoryError,
        create,
    });
})();
