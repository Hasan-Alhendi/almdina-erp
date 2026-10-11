(() => {
    "use strict";

    const root = window.AlmdinaDcoRecovery = window.AlmdinaDcoRecovery || Object.create(null);
    if (root.EditRecovery) return;

    class EditRecoveryError extends Error {
        constructor(code, message) {
            super(message);
            this.name = "EditRecoveryError";
            this.code = code;
        }
    }

    function fail(code, message) {
        throw new EditRecoveryError(code, message);
    }

    function validateRecord(record, identity, modified) {
        if (
            !record
            || record.mode !== "EDIT"
            || record.dirty_scope !== "DCO"
            || record.target_doctype !== "Door Cutting Order"
            || identity.target_doctype !== "Door Cutting Order"
            || String(record.target_name || "") !== String(identity && identity.target_name || "")
            || !identity
            || !identity.site
            || !identity.user
            || !identity.draft_id
            || String(record.draft_id || "") !== String(identity.draft_id)
            || !String(record.session_origin_modified || "").trim()
            || !Number.isSafeInteger(Number(record.recovery_revision))
        ) {
            fail("invalid_edit_draft", "Only this user's matching DCO edit draft can be restored");
        }
        if (String(record.expected_server_modified || "") !== String(modified || "")) {
            fail("version_conflict", "The server DCO changed after this edit draft was captured");
        }
        const projection = root.Projection;
        if (!projection) fail("dependency_unavailable", "Recovery projection is unavailable");
        let payload;
        try {
            payload = projection.deserialize(record.payload, "DCO");
        } catch (error) {
            fail(String(error && error.code || "invalid_edit_draft"), "The DCO edit draft is invalid");
        }
        if (
            payload.plan_workspace_draft !== null
            || payload.cost_workspace_draft !== null
            || payload.special_shape_drafts.length !== 0
        ) {
            fail("invalid_edit_draft", "EDIT recovery accepts DCO requirements only");
        }
        return payload.dco;
    }

    function buildAllowlistedPatch(doc, dco) {
        const projection = root.Projection;
        if (!projection || !doc || !Array.isArray(doc.pieces) || !Array.isArray(dco && dco.pieces)) {
            fail("invalid_edit_document", "The current DCO rows are unavailable");
        }
        const currentRows = doc.pieces;
        const rowsByName = new Map();
        currentRows.forEach((row) => {
            const name = String(row && row.name || "").trim();
            if (!name || rowsByName.has(name)) {
                fail("row_identity_conflict", "The current DCO contains an invalid piece identity");
            }
            rowsByName.set(name, row);
        });
        const seen = new Set();
        const piecePatches = dco.pieces.map((piece, index) => {
            const key = String(piece && piece.piece_key || "").trim();
            if (!key || seen.has(key)) {
                fail("row_identity_conflict", "The DCO edit draft contains a duplicate piece identity");
            }
            seen.add(key);
            const existing = rowsByName.has(key);
            if (!existing && !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(key)) {
                fail("row_identity_conflict", `Piece ${index} has no current or recovery-local identity`);
            }
            const values = {};
            projection.PIECE_FIELDS.forEach((fieldname) => {
                if (Object.prototype.hasOwnProperty.call(piece, fieldname)) {
                    values[fieldname] = piece[fieldname];
                }
            });
            return Object.freeze({
                piece_key: key,
                existing_name: existing ? key : null,
                values: Object.freeze(values),
            });
        });
        const headers = {};
        projection.HEADER_FIELDS.forEach((fieldname) => {
            if (Object.prototype.hasOwnProperty.call(dco, fieldname)) {
                headers[fieldname] = dco[fieldname];
            }
        });
        return Object.freeze({
            headers: Object.freeze(headers),
            pieces: Object.freeze(piecePatches),
        });
    }

    function conflictDetails(record, identity, serverDoc, loadedModified) {
        const projection = root.Projection;
        const localDco = validateRecord(record, identity, record.expected_server_modified);
        if (!serverDoc || serverDoc.doctype !== "Door Cutting Order"
            || String(serverDoc.name || "") !== String(identity.target_name || "")
            || !String(serverDoc.modified || "").trim()) {
            fail("version_check_unavailable", "The current server DCO version could not be verified");
        }
        const differences = [];
        const same = (left, right) => JSON.stringify(left === undefined ? null : left)
            === JSON.stringify(right === undefined ? null : right);
        projection.HEADER_FIELDS.forEach((fieldname) => {
            if (Object.prototype.hasOwnProperty.call(localDco, fieldname)
                && !same(localDco[fieldname], serverDoc[fieldname])) {
                differences.push(Object.freeze({
                    section: "header",
                    identity: fieldname,
                    server_value: serverDoc[fieldname] ?? null,
                    draft_value: localDco[fieldname] ?? null,
                }));
            }
        });
        const localKeys = new Set(localDco.pieces.map((piece) => String(piece.piece_key)));
        const serverRows = Array.isArray(serverDoc.pieces) ? serverDoc.pieces : [];
        const serverByName = new Map(serverRows.map((row) => [String(row && row.name || ""), row]));
        localDco.pieces.forEach((piece) => {
            const key = String(piece.piece_key || "");
            const serverRow = serverByName.get(key);
            if (!serverRow) {
                differences.push(Object.freeze({ section: "piece", identity: key, kind: "local_addition" }));
                return;
            }
            projection.PIECE_FIELDS.forEach((fieldname) => {
                if (Object.prototype.hasOwnProperty.call(piece, fieldname)
                    && !same(piece[fieldname], serverRow[fieldname])) {
                    differences.push(Object.freeze({
                        section: "piece",
                        identity: key,
                        fieldname,
                        server_value: serverRow[fieldname] ?? null,
                        draft_value: piece[fieldname] ?? null,
                    }));
                }
            });
        });
        const localPersistedOrder = localDco.pieces
            .map((piece) => String(piece.piece_key || ""))
            .filter((name) => serverByName.has(name));
        const serverPersistedOrder = serverRows
            .map((row) => String(row && row.name || ""))
            .filter((name) => localKeys.has(name));
        if (!same(localPersistedOrder, serverPersistedOrder)) {
            differences.push(Object.freeze({
                section: "piece",
                identity: "ترتيب الصفوف المحفوظة",
                kind: "order",
                server_value: serverPersistedOrder,
                draft_value: localPersistedOrder,
            }));
        }
        serverRows.forEach((row) => {
            const name = String(row && row.name || "");
            if (name && !localKeys.has(name)) {
                differences.push(Object.freeze({ section: "piece", identity: name, kind: "server_row_omitted" }));
            }
        });
        return Object.freeze({
            source: Object.freeze({
                target_doctype: "Door Cutting Order",
                target_name: String(identity.target_name),
                captured_at: String(record.captured_at || ""),
                tab_session_id: String(record.tab_session_id || ""),
            }),
            versions: Object.freeze({
                draft_expected: String(record.expected_server_modified || ""),
                loaded_form: String(loadedModified || ""),
                current_server: String(serverDoc.modified),
            }),
            differences: Object.freeze(differences),
        });
    }

    function exportDcoProjection(record, identity) {
        const dco = validateRecord(record, identity, record && record.expected_server_modified);
        return JSON.stringify(dco, null, 2);
    }

    async function discover(repository, identity) {
        if (!repository || typeof repository.discover !== "function") {
            return { ok: false, error: { code: "storage_unavailable", message: "Recovery storage is unavailable" } };
        }
        return repository.discover({
            site: identity.site,
            user: identity.user,
            target_doctype: "Door Cutting Order",
            target_name: identity.target_name,
            mode: "EDIT",
        });
    }

    async function restore(record, options = {}) {
        const repository = options.repository;
        const identity = options.identity;
        const modified = options.modified;
        if (!repository || typeof repository.read !== "function") {
            fail("storage_unavailable", "Recovery storage is unavailable");
        }
        if (typeof options.isCurrent !== "function" || !options.isCurrent()) {
            fail("stale_document", "The DCO form changed before this edit draft could be restored");
        }
        if (typeof options.isClean !== "function" || !options.isClean()) {
            fail("dirty_document", "Save or discard current DCO changes before restoring a local draft");
        }
        const read = await repository.read(identity);
        if (!options.isCurrent()) fail("stale_document", "The DCO form changed during local draft verification");
        if (!read || read.ok !== true || !read.value) {
            fail("storage_unavailable", "The selected local edit draft could not be verified");
        }
        const selected = read.value;
        if (
            String(selected.draft_id || "") !== String(record && record.draft_id || "")
            || Number(selected.recovery_revision) !== Number(record && record.recovery_revision)
            || (selected.official_save_attempted_at || null) !== (record.official_save_attempted_at || null)
        ) {
            fail("stale_revision", "The local edit draft changed in another tab");
        }
        if (!options.isClean()) {
            fail("dirty_document", "Save or discard current DCO changes before restoring a local draft");
        }
        const dco = validateRecord(selected, identity, selected.expected_server_modified);
        const patch = buildAllowlistedPatch(options.doc, dco);

        if (typeof options.fetchServerDocument !== "function") {
            fail("version_check_unavailable", "The current server DCO version could not be verified");
        }
        if (!options.isSessionGenerationCurrent || options.isSessionGenerationCurrent() !== true) {
            fail("stale_session", "The DCO edit session changed before server version verification");
        }
        let serverDoc;
        try {
            serverDoc = await options.fetchServerDocument();
        } catch (error) {
            fail("version_check_unavailable", "The current server DCO version could not be verified");
        }
        if (!options.isCurrent()) fail("stale_document", "The DCO form changed during server version verification");
        if (options.isSessionGenerationCurrent() !== true) {
            fail("stale_session", "The DCO edit session changed during server version verification");
        }
        if (typeof options.isClean !== "function" || options.isClean() !== true) {
            fail("dirty_document", "The DCO changed while its server version was being checked");
        }
        const serverModified = String(serverDoc && serverDoc.modified || "");
        if (!serverModified) fail("version_check_unavailable", "The current server DCO version could not be verified");
        const loadedModified = typeof options.currentModified === "function"
            ? String(options.currentModified() || "")
            : String(modified || "");
        if (
            serverModified !== loadedModified
            || serverModified !== String(selected.expected_server_modified || "")
        ) {
            const conflict = new EditRecoveryError("version_conflict", "The server DCO changed after this edit draft was captured");
            conflict.details = conflictDetails(selected, identity, serverDoc, loadedModified);
            throw conflict;
        }

        if (!options.isCurrent()) fail("stale_document", "The DCO form changed before the edit session could start");
        if (!options.canEdit || options.canEdit() !== true) {
            fail("permission_denied", "Current DCO edit permission is required to restore this draft");
        }
        const reusingSession = typeof options.reuseSession === "function" && options.reuseSession() === true;
        if (!reusingSession && (!options.canStart || options.canStart() !== true)) {
            fail("session_unavailable", "The current DCO edit session cannot be started");
        }
        if (typeof options.startEdit !== "function" || await options.startEdit() !== true) {
            fail("session_unavailable", "The current DCO edit session could not be started");
        }

        if (!options.isCurrent()) fail("stale_document", "The DCO form changed while the edit session was starting");
        if (typeof options.isSessionCurrent !== "function" || options.isSessionCurrent() !== true) {
            fail("session_unavailable", "The DCO edit session no longer owns this form");
        }
        if (!options.canEdit || options.canEdit() !== true) {
            fail("permission_denied", "DCO edit permission changed before this draft could be applied");
        }
        if (typeof options.apply !== "function") fail("restore_unavailable", "DCO edit restore is unavailable");
        await options.apply(patch);
        return Object.freeze({
            draft_id: String(selected.draft_id),
            recovery_revision: Number(selected.recovery_revision),
            piece_count: patch.pieces.length,
        });
    }

    root.EditRecovery = Object.freeze({
        EditRecoveryError,
        validateRecord,
        buildAllowlistedPatch,
        conflictDetails,
        exportDcoProjection,
        discover,
        restore,
    });
})();
