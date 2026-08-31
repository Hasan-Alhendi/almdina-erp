(() => {
    "use strict";

    const root = window.AlmdinaDcoRecovery = window.AlmdinaDcoRecovery || Object.create(null);
    if (root.NewRecovery) return;

    class NewRecoveryError extends Error {
        constructor(code, message) {
            super(message);
            this.name = "NewRecoveryError";
            this.code = code;
        }
    }

    function requireNewRecord(record) {
        if (!record || record.mode !== "NEW" || record.dirty_scope !== "DCO") {
            throw new NewRecoveryError("invalid_new_draft", "Only a NEW DCO input draft can be restored here");
        }
        const projection = root.Projection;
        if (!projection) throw new NewRecoveryError("dependency_unavailable", "Recovery projection is unavailable");
        const payload = projection.deserialize(record.payload, "DCO");
        if (
            payload.plan_workspace_draft !== null
            || payload.cost_workspace_draft !== null
            || payload.special_shape_drafts.length !== 0
        ) {
            throw new NewRecoveryError("invalid_new_draft", "NEW recovery cannot hydrate canonical Plan or Cost state");
        }
        return payload.dco;
    }

    function summarize(record) {
        const dco = requireNewRecord(record);
        const pieces = Array.isArray(dco.pieces) ? dco.pieces : [];
        return Object.freeze({
            draft_id: String(record.draft_id),
            captured_at: String(record.captured_at),
            customer: String(dco.customer || "").trim(),
            board_description: String(dco.board_description || "").trim(),
            edge_color: String(dco.edge_color || "").trim(),
            piece_count: pieces.length,
            has_special_piece: pieces.some((piece) => (
                String(piece.piece_type || "") === "Special"
                || Boolean(String(piece.special_shape_drawing_json || "").trim())
                || Boolean(String(piece.special_shape_geometry_json || "").trim())
            )),
            official_save_state: String(record.official_save_state || "ACTIVE"),
        });
    }

    async function discover(repository, identity) {
        if (!repository || typeof repository.discover !== "function") {
            return { ok: false, error: { code: "storage_unavailable", message: "Recovery storage is unavailable" } };
        }
        return repository.discover({
            site: identity.site,
            user: identity.user,
            target_doctype: "Door Cutting Order",
            mode: "NEW",
        });
    }

    async function hydrate(record, options = {}) {
        const dco = requireNewRecord(record);
        const session = options.session;
        const hydrationPort = options.hydrationPort;
        if (
            !session
            || typeof session.beginRestore !== "function"
            || typeof hydrationPort !== "function"
        ) {
            throw new NewRecoveryError("restore_unavailable", "NEW recovery lifecycle is unavailable");
        }
        if (!session.beginRestore()) {
            throw new NewRecoveryError("restore_unavailable", "NEW recovery session cannot enter RESTORING");
        }
        try {
            const restored = await hydrationPort(dco) !== false;
            session.completeRestore();
            return Object.freeze({
                draft_id: String(record.draft_id),
                piece_count: dco.pieces.length,
                asset_refs: Object.freeze([...(record.asset_refs || [])]),
                restored,
            });
        } catch (error) {
            session.completeRestore();
            throw error;
        }
    }

    root.NewRecovery = Object.freeze({
        NewRecoveryError,
        summarize,
        discover,
        hydrate,
    });
})();
