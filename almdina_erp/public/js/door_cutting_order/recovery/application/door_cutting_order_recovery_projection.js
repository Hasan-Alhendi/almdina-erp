(() => {
    "use strict";

    const root = window.AlmdinaDcoRecovery = window.AlmdinaDcoRecovery || Object.create(null);
    if (root.Projection) return;

    const PROJECTION_VERSION = 1;
    const DIRTY_SCOPES = Object.freeze(["DCO", "PLAN", "COST", "SPECIAL_SHAPE"]);
    const HEADER_FIELDS = Object.freeze([
        "customer",
        "order_date",
        "order_notes",
        "board_description",
        "board_length_cm",
        "board_width_cm",
        "default_edge_type",
        "edge_color",
    ]);
    const PIECE_FIELDS = Object.freeze([
        "piece_type",
        "extra_double",
        "extra_full_door_double",
        "extra_liner",
        "extra_back_groove",
        "extra_recessed_handle_cutout",
        "clipped_corner_position",
        "clipped_corner_width_cm",
        "clipped_corner_length_cm",
        "width_cm",
        "length_cm",
        "qty",
        "allow_rotation",
        "edge_long_right",
        "edge_long_left",
        "edge_width_top",
        "edge_width_bottom",
        "edge_long_right_type_override",
        "edge_long_left_type_override",
        "edge_width_top_type_override",
        "edge_width_bottom_type_override",
        "notes",
        "special_shape_drawing_json",
        "special_shape_geometry_json",
    ]);
    const PLAN_DRAFT_FIELDS = Object.freeze([
        "packing_mode",
        "cutting_machine_type",
        "optimization_time_limit_sec",
        "kerf_mm",
        "trim_margin_mm",
    ]);
    const COST_DRAFT_FIELDS = Object.freeze([
        "board_rate_usd",
        "cutting_cost_per_board_usd",
    ]);

    class RecoveryProjectionError extends Error {
        constructor(code, message) {
            super(message);
            this.name = "RecoveryProjectionError";
            this.code = code;
        }
    }

    function clone(value) {
        if (value === undefined) return undefined;
        if (value === null) return null;
        if (typeof structuredClone === "function") return structuredClone(value);
        return JSON.parse(JSON.stringify(value));
    }

    function canonicalize(value) {
        if (value === null || typeof value !== "object") return value;
        if (Array.isArray(value)) return value.map(canonicalize);
        return Object.keys(value).sort().reduce((result, key) => {
            if (value[key] !== undefined) result[key] = canonicalize(value[key]);
            return result;
        }, {});
    }

    function canonicalStringify(value) {
        return JSON.stringify(canonicalize(value));
    }

    function assertDurableValue(value, path = "payload") {
        if (value === null || value === undefined) return;
        const objectTag = Object.prototype.toString.call(value);
        if (objectTag === "[object Blob]" || objectTag === "[object File]") {
            throw new RecoveryProjectionError("transient_asset", `${path} contains binary asset data`);
        }
        if (typeof value === "string") {
            const normalized = value.trim();
            if (/^blob:/i.test(normalized) || /^data:[^,]{0,128},/i.test(normalized)) {
                throw new RecoveryProjectionError("transient_asset", `${path} contains a transient URL`);
            }
            return;
        }
        if (typeof value === "number") {
            if (!Number.isFinite(value)) {
                throw new RecoveryProjectionError("unsupported_value", `${path} contains a non-finite number`);
            }
            return;
        }
        if (typeof value === "boolean") return;
        if (Array.isArray(value)) {
            value.forEach((item, index) => assertDurableValue(item, `${path}[${index}]`));
            return;
        }
        if (typeof value !== "object" || objectTag !== "[object Object]") {
            throw new RecoveryProjectionError("unsupported_value", `${path} is not plain recovery data`);
        }
        Object.entries(value).forEach(([key, item]) => assertDurableValue(item, `${path}.${key}`));
    }

    function pick(source, fields) {
        const result = {};
        fields.forEach((fieldname) => {
            const value = source && source[fieldname];
            if (value !== undefined) result[fieldname] = clone(value);
        });
        return result;
    }

    function assertEmbeddedJsonDurable(value, path) {
        const serialized = String(value || "").trim();
        if (!serialized) return;
        let parsed;
        try {
            parsed = JSON.parse(serialized);
        } catch (error) {
            throw new RecoveryProjectionError("corrupt_projection", `${path} is not valid JSON`);
        }
        assertDurableValue(parsed, path);
    }

    function createDcoInput(doc, options = {}) {
        if (!doc || typeof doc !== "object") {
            throw new RecoveryProjectionError("invalid_dco", "DCO source is unavailable");
        }
        const pieceKey = typeof options.pieceKey === "function"
            ? options.pieceKey
            : (row) => String(row && row.name || "").trim();
        const pieces = (Array.isArray(doc.pieces) ? doc.pieces : []).map((row, index) => {
            const key = String(pieceKey(row, index) || "").trim();
            if (!key) {
                throw new RecoveryProjectionError("missing_piece_key", `Piece ${index} has no recovery identity`);
            }
            const piece = { piece_key: key, ...pick(row, PIECE_FIELDS) };
            assertEmbeddedJsonDurable(piece.special_shape_drawing_json, `pieces[${index}].special_shape_drawing_json`);
            assertEmbeddedJsonDurable(piece.special_shape_geometry_json, `pieces[${index}].special_shape_geometry_json`);
            return piece;
        });
        const projection = {
            projection_version: PROJECTION_VERSION,
            ...pick(doc, HEADER_FIELDS),
            pieces,
        };
        assertDurableValue(projection);
        return projection;
    }

    function requireDirtyWorkspace(snapshot, scope) {
        if (!snapshot || snapshot.editing !== true || snapshot.dirty !== true) {
            throw new RecoveryProjectionError(
                "workspace_not_dirty",
                `${scope} recovery requires the current WorkspaceStore dirty draft`
            );
        }
    }

    function createPlanWorkspaceDraft(snapshot, baselineDescriptor = {}) {
        requireDirtyWorkspace(snapshot, "PLAN");
        const baseline = snapshot.baseline || {};
        const projection = {
            projection_version: PROJECTION_VERSION,
            baseline: {
                plan_name: baselineDescriptor.plan_name == null
                    ? (baseline.name || null)
                    : baselineDescriptor.plan_name,
                plan_modified: baselineDescriptor.plan_modified == null
                    ? (baseline.modified || null)
                    : baselineDescriptor.plan_modified,
                normalized_settings_hash: String(baselineDescriptor.normalized_settings_hash || ""),
            },
            draft: pick(snapshot.draft || {}, PLAN_DRAFT_FIELDS),
        };
        if (!projection.baseline.normalized_settings_hash) {
            throw new RecoveryProjectionError("missing_baseline_hash", "PLAN baseline hash is required");
        }
        assertDurableValue(projection);
        return projection;
    }

    function createCostWorkspaceDraft(snapshot, baselineDescriptor = {}) {
        requireDirtyWorkspace(snapshot, "COST");
        const baseline = snapshot.baseline || {};
        const projection = {
            projection_version: PROJECTION_VERSION,
            baseline: {
                cutting_plan: baselineDescriptor.cutting_plan == null
                    ? (baseline.cutting_plan || null)
                    : baselineDescriptor.cutting_plan,
                normalized_settings_hash: String(baselineDescriptor.normalized_settings_hash || ""),
            },
            draft: pick(snapshot.draft || {}, COST_DRAFT_FIELDS),
        };
        if (!projection.baseline.normalized_settings_hash) {
            throw new RecoveryProjectionError("missing_baseline_hash", "COST baseline hash is required");
        }
        assertDurableValue(projection);
        return projection;
    }

    function createSpecialShapeDraft(value) {
        const projection = {
            projection_version: PROJECTION_VERSION,
            order_name: String(value && value.order_name || "").trim(),
            piece_name: String(value && value.piece_name || "").trim(),
            document: clone(value && value.document),
            asset_refs: Array.isArray(value && value.asset_refs)
                ? value.asset_refs.map((item) => String(item || "").trim()).filter(Boolean)
                : [],
        };
        if (!projection.order_name || !projection.piece_name || !projection.document) {
            throw new RecoveryProjectionError("invalid_special_shape", "Special-shape identity/document is incomplete");
        }
        assertDurableValue(projection);
        return projection;
    }

    function assertAllowedKeys(value, allowed, path) {
        if (!value || Object.prototype.toString.call(value) !== "[object Object]") {
            throw new RecoveryProjectionError("corrupt_projection", `${path} is not an object`);
        }
        Object.keys(value).forEach((key) => {
            if (!allowed.includes(key)) {
                throw new RecoveryProjectionError(
                    "unexpected_projection_field",
                    `${path}.${key} is outside the recovery contract`
                );
            }
        });
    }

    function validatePayload(payload, dirtyScope = null) {
        assertAllowedKeys(payload, [
            "projection_version",
            "dco",
            "plan_workspace_draft",
            "cost_workspace_draft",
            "special_shape_drafts",
        ], "payload");
        if (Number(payload.projection_version) !== PROJECTION_VERSION) {
            throw new RecoveryProjectionError("incompatible_projection", "Recovery projection version is incompatible");
        }
        assertAllowedKeys(payload.dco, ["projection_version", ...HEADER_FIELDS, "pieces"], "payload.dco");
        if (
            Number(payload.dco.projection_version) !== PROJECTION_VERSION
            || !Array.isArray(payload.dco.pieces)
        ) {
            throw new RecoveryProjectionError("corrupt_projection", "DCO recovery projection is invalid");
        }
        payload.dco.pieces.forEach((piece, index) => {
            assertAllowedKeys(piece, ["piece_key", ...PIECE_FIELDS], `payload.dco.pieces[${index}]`);
            if (!String(piece.piece_key || "").trim()) {
                throw new RecoveryProjectionError("missing_piece_key", `Piece ${index} has no recovery identity`);
            }
        });
        if (payload.plan_workspace_draft !== null) {
            const plan = payload.plan_workspace_draft;
            assertAllowedKeys(plan, ["projection_version", "baseline", "draft"], "payload.plan_workspace_draft");
            assertAllowedKeys(
                plan.baseline,
                ["plan_name", "plan_modified", "normalized_settings_hash"],
                "payload.plan_workspace_draft.baseline"
            );
            assertAllowedKeys(plan.draft, PLAN_DRAFT_FIELDS, "payload.plan_workspace_draft.draft");
            if (
                Number(plan.projection_version) !== PROJECTION_VERSION
                || !String(plan.baseline.normalized_settings_hash || "").trim()
            ) {
                throw new RecoveryProjectionError("corrupt_projection", "PLAN recovery projection is invalid");
            }
        }
        if (payload.cost_workspace_draft !== null) {
            const cost = payload.cost_workspace_draft;
            assertAllowedKeys(cost, ["projection_version", "baseline", "draft"], "payload.cost_workspace_draft");
            assertAllowedKeys(
                cost.baseline,
                ["cutting_plan", "normalized_settings_hash"],
                "payload.cost_workspace_draft.baseline"
            );
            assertAllowedKeys(cost.draft, COST_DRAFT_FIELDS, "payload.cost_workspace_draft.draft");
            if (
                Number(cost.projection_version) !== PROJECTION_VERSION
                || !String(cost.baseline.normalized_settings_hash || "").trim()
            ) {
                throw new RecoveryProjectionError("corrupt_projection", "COST recovery projection is invalid");
            }
        }
        if (!Array.isArray(payload.special_shape_drafts)) {
            throw new RecoveryProjectionError("corrupt_projection", "Special-shape recovery projection is invalid");
        }
        payload.special_shape_drafts.forEach((draft, index) => {
            assertAllowedKeys(
                draft,
                ["projection_version", "order_name", "piece_name", "document", "asset_refs"],
                `payload.special_shape_drafts[${index}]`
            );
            assertAllowedKeys(
                draft.document,
                ["schema", "version", "canvas", "reference", "elements", "notes", "source", "templateId"],
                `payload.special_shape_drafts[${index}].document`
            );
            if (
                Number(draft.projection_version) !== PROJECTION_VERSION
                || !String(draft.order_name || "").trim()
                || !String(draft.piece_name || "").trim()
                || !Array.isArray(draft.asset_refs)
            ) {
                throw new RecoveryProjectionError("corrupt_projection", "Special-shape recovery draft is invalid");
            }
        });
        if (dirtyScope) {
            const scope = String(dirtyScope).toUpperCase();
            const matches = {
                DCO: payload.plan_workspace_draft === null
                    && payload.cost_workspace_draft === null
                    && payload.special_shape_drafts.length === 0,
                PLAN: payload.plan_workspace_draft !== null
                    && payload.cost_workspace_draft === null
                    && payload.special_shape_drafts.length === 0,
                COST: payload.plan_workspace_draft === null
                    && payload.cost_workspace_draft !== null
                    && payload.special_shape_drafts.length === 0,
                SPECIAL_SHAPE: payload.plan_workspace_draft === null
                    && payload.cost_workspace_draft === null
                    && payload.special_shape_drafts.length > 0,
            };
            if (!matches[scope]) {
                throw new RecoveryProjectionError(
                    "multiple_dirty_owners",
                    "Recovery payload does not match its single dirty owner"
                );
            }
        }
        assertDurableValue(payload);
        return payload;
    }

    function createPayload({ dco, dirtyScope, planWorkspaceDraft = null, costWorkspaceDraft = null, specialShapeDrafts = [] }) {
        const scope = String(dirtyScope || "").toUpperCase();
        if (!DIRTY_SCOPES.includes(scope)) {
            throw new RecoveryProjectionError("invalid_dirty_scope", "Recovery dirty scope is invalid");
        }
        const payload = {
            projection_version: PROJECTION_VERSION,
            dco: clone(dco),
            plan_workspace_draft: scope === "PLAN" ? clone(planWorkspaceDraft) : null,
            cost_workspace_draft: scope === "COST" ? clone(costWorkspaceDraft) : null,
            special_shape_drafts: scope === "SPECIAL_SHAPE" ? clone(specialShapeDrafts) : [],
        };
        if (!payload.dco || Number(payload.dco.projection_version) !== PROJECTION_VERSION) {
            throw new RecoveryProjectionError("invalid_dco", "DCO recovery projection is required");
        }
        if (scope === "PLAN" && !payload.plan_workspace_draft) {
            throw new RecoveryProjectionError("missing_scope_projection", "PLAN recovery projection is required");
        }
        if (scope === "COST" && !payload.cost_workspace_draft) {
            throw new RecoveryProjectionError("missing_scope_projection", "COST recovery projection is required");
        }
        if (scope === "SPECIAL_SHAPE" && !payload.special_shape_drafts.length) {
            throw new RecoveryProjectionError("missing_scope_projection", "Special-shape recovery projection is required");
        }
        return validatePayload(payload, scope);
    }

    function serialize(payload) {
        assertDurableValue(payload);
        return canonicalStringify(payload);
    }

    function deserialize(value, dirtyScope = null) {
        let payload;
        try {
            payload = typeof value === "string" ? JSON.parse(value) : clone(value);
        } catch (error) {
            throw new RecoveryProjectionError("corrupt_projection", "Recovery projection is unreadable");
        }
        return validatePayload(payload, dirtyScope);
    }

    root.Projection = Object.freeze({
        PROJECTION_VERSION,
        DIRTY_SCOPES,
        HEADER_FIELDS,
        PIECE_FIELDS,
        PLAN_DRAFT_FIELDS,
        COST_DRAFT_FIELDS,
        RecoveryProjectionError,
        canonicalStringify,
        assertDurableValue,
        createDcoInput,
        createPlanWorkspaceDraft,
        createCostWorkspaceDraft,
        createSpecialShapeDraft,
        createPayload,
        validatePayload,
        serialize,
        deserialize,
    });
})();
