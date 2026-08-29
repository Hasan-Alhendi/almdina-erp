(() => {
    "use strict";

    const root = window.AlmdinaDcoRecovery = window.AlmdinaDcoRecovery || Object.create(null);
    if (root.IndexedDb) return;

    const DATABASE_NAME = "almdina_erp_dco_recovery";
    const DATABASE_VERSION = 1;
    const DRAFT_STORE = "dco_recovery_drafts";
    const ASSET_STORE = "dco_recovery_assets";

    class RecoveryStorageError extends Error {
        constructor(code, message, cause = null) {
            super(message);
            this.name = "RecoveryStorageError";
            this.code = code;
            this.cause = cause;
        }
    }

    function errorCode(error, fallback = "storage_failure") {
        const name = String(error && error.name || "");
        if (name === "QuotaExceededError") return "quota_exceeded";
        if (name === "VersionError") return "unknown_schema";
        if (name === "DataError" || name === "DataCloneError") return "invalid_record";
        if (name === "TransactionInactiveError" || name === "AbortError") return "transaction_failure";
        if (name === "NotFoundError") return "schema_failure";
        return fallback;
    }

    function storageError(error, fallback, message) {
        if (error instanceof RecoveryStorageError) return error;
        return new RecoveryStorageError(errorCode(error, fallback), message, error || null);
    }

    function requestPromise(request, fallback = "transaction_failure") {
        return new Promise((resolve, reject) => {
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(storageError(
                request.error,
                fallback,
                "IndexedDB request failed"
            ));
        });
    }

    function ensureIndex(store, name, keyPath, options = {}) {
        if (!store.indexNames.contains(name)) store.createIndex(name, keyPath, options);
    }

    function installSchema(database, upgradeTransaction) {
        let drafts;
        if (!database.objectStoreNames.contains(DRAFT_STORE)) {
            drafts = database.createObjectStore(DRAFT_STORE, { keyPath: "storage_key" });
        } else {
            drafts = upgradeTransaction.objectStore(DRAFT_STORE);
        }
        ensureIndex(drafts, "namespace_key", "namespace_key");
        ensureIndex(drafts, "target_key", "target_key");
        ensureIndex(drafts, "captured_at", "captured_at");

        let assets;
        if (!database.objectStoreNames.contains(ASSET_STORE)) {
            assets = database.createObjectStore(ASSET_STORE, { keyPath: "storage_key" });
        } else {
            assets = upgradeTransaction.objectStore(ASSET_STORE);
        }
        ensureIndex(assets, "draft_key", "draft_key");
        ensureIndex(assets, "namespace_key", "namespace_key");
    }

    function createGateway(options = {}) {
        const indexedDb = options.indexedDB === undefined ? window.indexedDB : options.indexedDB;
        const cryptoImpl = options.crypto === undefined ? window.crypto : options.crypto;
        const TextEncoderImpl = options.TextEncoder || window.TextEncoder;
        let openPromise = null;

        function open() {
            if (!indexedDb || typeof indexedDb.open !== "function") {
                return Promise.reject(new RecoveryStorageError(
                    "api_unavailable",
                    "IndexedDB is unavailable"
                ));
            }
            if (openPromise) return openPromise;
            openPromise = new Promise((resolve, reject) => {
                let request;
                try {
                    request = indexedDb.open(DATABASE_NAME, DATABASE_VERSION);
                } catch (error) {
                    reject(storageError(error, "open_failure", "IndexedDB could not be opened"));
                    return;
                }
                request.onupgradeneeded = () => {
                    try {
                        installSchema(request.result, request.transaction);
                    } catch (error) {
                        try { request.transaction.abort(); } catch (abortError) { /* best effort */ }
                        reject(storageError(error, "schema_failure", "Recovery schema could not be installed"));
                    }
                };
                request.onsuccess = () => {
                    const database = request.result;
                    database.onversionchange = () => {
                        database.close();
                        openPromise = null;
                    };
                    resolve(database);
                };
                request.onerror = () => {
                    openPromise = null;
                    reject(storageError(request.error, "open_failure", "IndexedDB open failed"));
                };
                request.onblocked = () => {
                    openPromise = null;
                    reject(new RecoveryStorageError(
                        "open_blocked",
                        "IndexedDB upgrade is blocked by another tab"
                    ));
                };
            });
            return openPromise;
        }

        async function transaction(storeNames, mode, operation) {
            const database = await open();
            return new Promise((resolve, reject) => {
                let tx;
                let result;
                let operationSettled = false;
                try {
                    tx = database.transaction(storeNames, mode);
                } catch (error) {
                    reject(storageError(error, "transaction_failure", "Recovery transaction could not start"));
                    return;
                }
                tx.oncomplete = () => {
                    if (operationSettled) resolve(result);
                    else reject(new RecoveryStorageError(
                        "transaction_failure",
                        "Recovery transaction completed before its operation"
                    ));
                };
                tx.onerror = () => reject(storageError(
                    tx.error,
                    "transaction_failure",
                    "Recovery transaction failed"
                ));
                tx.onabort = () => reject(storageError(
                    tx.error,
                    "transaction_failure",
                    "Recovery transaction was aborted"
                ));
                const stores = Object.fromEntries(
                    storeNames.map((name) => [name, tx.objectStore(name)])
                );
                try {
                    Promise.resolve(operation(stores, requestPromise, tx))
                        .then((value) => {
                            result = value;
                            operationSettled = true;
                        })
                        .catch((error) => {
                            try { tx.abort(); } catch (abortError) { /* already inactive */ }
                            reject(storageError(error, "transaction_failure", "Recovery operation failed"));
                        });
                } catch (error) {
                    try { tx.abort(); } catch (abortError) { /* already inactive */ }
                    reject(storageError(error, "transaction_failure", "Recovery operation failed"));
                }
            });
        }

        function digestHex(digest) {
            return Array.from(new Uint8Array(digest))
                .map((byte) => byte.toString(16).padStart(2, "0"))
                .join("");
        }

        async function sha256Bytes(value) {
            if (
                !cryptoImpl
                || !cryptoImpl.subtle
                || typeof cryptoImpl.subtle.digest !== "function"
            ) {
                throw new RecoveryStorageError("api_unavailable", "SHA-256 browser API is unavailable");
            }
            let digest;
            try {
                digest = await cryptoImpl.subtle.digest("SHA-256", value);
            } catch (error) {
                throw storageError(error, "integrity_failure", "Recovery payload hash failed");
            }
            return digestHex(digest);
        }

        async function sha256(value) {
            if (typeof TextEncoderImpl !== "function") {
                throw new RecoveryStorageError("api_unavailable", "TextEncoder is unavailable");
            }
            return sha256Bytes(new TextEncoderImpl().encode(String(value)));
        }

        async function requestPersistence() {
            const storage = window.navigator && window.navigator.storage;
            if (!storage || typeof storage.persist !== "function") return false;
            try {
                return Boolean(await storage.persist());
            } catch (error) {
                return false;
            }
        }

        function randomUUID() {
            if (!cryptoImpl || typeof cryptoImpl.randomUUID !== "function") {
                throw new RecoveryStorageError(
                    "api_unavailable",
                    "Secure recovery identity generation is unavailable"
                );
            }
            return cryptoImpl.randomUUID();
        }

        return Object.freeze({
            open,
            transaction,
            sha256,
            sha256Bytes,
            randomUUID,
            requestPersistence,
        });
    }

    root.IndexedDb = Object.freeze({
        DATABASE_NAME,
        DATABASE_VERSION,
        DRAFT_STORE,
        ASSET_STORE,
        RecoveryStorageError,
        errorCode,
        requestPromise,
        createGateway,
    });
})();
