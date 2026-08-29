(() => {
    "use strict";

    const root = window.AlmdinaDcoRecovery = window.AlmdinaDcoRecovery || Object.create(null);
    if (root.LocalCheckpoint) return;

    const CHECKPOINT_EFFECT = "dco-local-recovery-checkpoint";
    const CLEANUP_EFFECT = "dco-local-recovery-cleanup";
    const states = new WeakMap();
    let draftRepository = null;
    let assetRepository = null;
    let persistenceRequested = false;

    function uuid() {
        const repo = repository();
        if (!repo || typeof repo.createIdentity !== "function") {
            throw new Error("Secure recovery identity generation is unavailable");
        }
        return repo.createIdentity();
    }

    function siteIdentity() {
        return String(
            frappe && frappe.boot && (frappe.boot.sitename || frappe.boot.site_name)
            || window.location && window.location.host
            || ""
        ).trim();
    }

    function userIdentity() {
        return String(frappe && frappe.session && frappe.session.user || "").trim();
    }

    function repository() {
        if (draftRepository) return draftRepository;
        const factory = root.LocalDraftRepository;
        if (!factory || typeof factory.create !== "function") return null;
        try {
            draftRepository = factory.create();
            if (!persistenceRequested) {
                persistenceRequested = true;
                Promise.resolve(draftRepository.requestPersistence()).catch(() => false);
            }
            return draftRepository;
        } catch (error) {
            console.debug("DCO local recovery repository is unavailable", error);
            return null;
        }
    }

    function assets() {
        if (assetRepository) return assetRepository;
        const factory = root.LocalAssetRepository;
        if (!factory || typeof factory.create !== "function") return null;
        try {
            assetRepository = factory.create();
            return assetRepository;
        } catch (error) {
            console.debug("DCO local recovery asset repository is unavailable", error);
            return null;
        }
    }

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function isNew(frm) {
        return Boolean(frm && typeof frm.is_new === "function" && frm.is_new());
    }

    function isEditSessionActive(frm) {
        const owner = window.AlmdinaOrderRevisionUX;
        return Boolean(
            owner
            && typeof owner.isEditSessionActive === "function"
            && owner.isEditSessionActive(frm)
        );
    }

    function isEligible(frm, dirtyScope = "DCO") {
        const scope = String(dirtyScope || "DCO").toUpperCase();
        const hasDocument = Boolean(
            frm
            && frm.doc
            && frm.doctype === "Door Cutting Order"
        );
        if (!hasDocument) return false;
        if (["PLAN", "COST", "SPECIAL_SHAPE"].includes(scope)) return !isNew(frm);
        return Boolean(
            isNew(frm) || isEditSessionActive(frm)
        );
    }

    function rowNeedsRecoveryKey(row, mode) {
        if (mode === "NEW") return true;
        const name = String(row && row.name || "").trim();
        return !name || Boolean(row && row.__islocal) || /^new-/i.test(name);
    }

    function pieceKey(state, row) {
        if (!rowNeedsRecoveryKey(row, state.mode)) return String(row.name).trim();
        if (!state.pieceKeys.has(row)) state.pieceKeys.set(row, uuid());
        return state.pieceKeys.get(row);
    }

    function currentState(frm) {
        const state = states.get(frm);
        const context = documentContext();
        if (!state || !context || typeof context.isSameDocument !== "function") return state || null;
        if (context.isSameDocument(frm, state.documentToken)) return state;
        state.session.dispose();
        states.delete(frm);
        return null;
    }

    async function workspaceProjection(frm, state, dirtyScope) {
        const projection = root.Projection;
        const repo = repository();
        if (!projection || !repo) throw new Error("Recovery projection infrastructure is unavailable");
        const dco = projection.createDcoInput(frm.doc, {
            pieceKey: (row) => pieceKey(state, row),
        });
        let planWorkspaceDraft = null;
        let costWorkspaceDraft = null;
        if (dirtyScope === "PLAN") {
            const owner = window.AlmdinaPlanWorkspaceState;
            const snapshot = owner && typeof owner.snapshot === "function" ? owner.snapshot(frm) : null;
            const baseline = snapshot && snapshot.baseline || {};
            const activePlan = owner && typeof owner.activePlan === "function"
                ? owner.activePlan(frm, "System")
                : null;
            const normalizedSettingsHash = await repo.hashCanonical(
                Object.fromEntries(projection.PLAN_DRAFT_FIELDS.map((key) => [key, baseline[key]]))
            );
            planWorkspaceDraft = projection.createPlanWorkspaceDraft(snapshot, {
                plan_name: activePlan && activePlan.name || null,
                plan_modified: activePlan && activePlan.modified || null,
                normalized_settings_hash: normalizedSettingsHash,
            });
        }
        if (dirtyScope === "COST") {
            const owner = window.AlmdinaCostWorkspaceState;
            const snapshot = owner && typeof owner.snapshot === "function" ? owner.snapshot(frm) : null;
            const baseline = snapshot && snapshot.baseline || {};
            const normalizedSettingsHash = await repo.hashCanonical(
                Object.fromEntries(projection.COST_DRAFT_FIELDS.map((key) => [key, baseline[key]]))
            );
            costWorkspaceDraft = projection.createCostWorkspaceDraft(snapshot, {
                cutting_plan: snapshot && snapshot.data && snapshot.data.cutting_plan || null,
                normalized_settings_hash: normalizedSettingsHash,
            });
        }
        return {
            payload: projection.createPayload({
                dco,
                dirtyScope,
                planWorkspaceDraft,
                costWorkspaceDraft,
            }),
            asset_refs: [],
        };
    }

    function createState(frm) {
        const context = documentContext();
        const repo = repository();
        const factory = root.CheckpointSession;
        if (!context || !repo || !factory || typeof factory.create !== "function") return null;
        const token = context.capture(frm);
        if (!token) return null;
        const mode = isNew(frm) ? "NEW" : "EDIT";
        const modified = mode === "EDIT" ? String(frm.doc.modified || "").trim() : null;
        if (mode === "EDIT" && !modified) return null;
        const state = {
            mode,
            documentToken: token,
            pieceKeys: new WeakMap(),
            saveWasNew: false,
            session: null,
        };
        try {
            state.session = factory.create({
                repository: repo,
                site: siteIdentity(),
                user: userIdentity(),
                mode,
                draftId: uuid(),
                tabSessionId: uuid(),
                targetName: mode === "EDIT" ? String(frm.doc.name || "").trim() : null,
                sessionOriginModified: modified,
                expectedServerModified: modified,
                capture: ({ dirtyScope }) => workspaceProjection(frm, state, dirtyScope),
                onStateChange: (snapshot) => {
                    if (snapshot.state === factory.STATES.ERROR) {
                        console.debug("DCO local recovery checkpoint failed safely", snapshot.error);
                    }
                },
            });
        } catch (error) {
            console.debug("DCO local recovery session is unavailable", error);
            return null;
        }
        states.set(frm, state);
        if (typeof context.registerCleanup === "function") {
            context.registerCleanup(frm, CLEANUP_EFFECT, () => {
                const active = states.get(frm);
                if (active === state) states.delete(frm);
                state.session.dispose();
            });
        }
        return state;
    }

    function ensureState(frm, dirtyScope = "DCO") {
        const current = currentState(frm);
        if (current) return current;
        if (!isEligible(frm, dirtyScope)) return null;
        return createState(frm);
    }

    function flushState(frm, state = currentState(frm)) {
        if (!state) return Promise.resolve({ ok: true, value: null });
        return state.session.flush().catch((error) => ({
            ok: false,
            error: { code: String(error && error.code || "storage_failure"), message: String(error && error.message || error) },
        }));
    }

    function scheduleFlush(frm, state) {
        const context = documentContext();
        if (context && typeof context.scheduleFrame === "function") {
            context.scheduleFrame(frm, CHECKPOINT_EFFECT, () => { flushState(frm, state); });
            return;
        }
        Promise.resolve().then(() => flushState(frm, state));
    }

    function markDirty(frm, dirtyScope = "DCO") {
        if (!isEligible(frm, dirtyScope)) return false;
        const state = ensureState(frm, dirtyScope);
        if (!state) return false;
        try {
            state.session.markDirty(dirtyScope);
            scheduleFlush(frm, state);
            return true;
        } catch (error) {
            console.debug("DCO local recovery mutation was not checkpointed", error);
            return false;
        }
    }

    function workspaceChanged(event, dirtyScope) {
        const frm = window.cur_frm;
        if (!frm || !isEligible(frm, dirtyScope)) return;
        const detail = event && event.detail || {};
        const context = documentContext();
        if (
            context
            && typeof context.formIdentity === "function"
            && detail.identity
            && detail.identity !== context.formIdentity(frm)
        ) return;
        const snapshot = detail.snapshot;
        if (!snapshot || snapshot.editing !== true || snapshot.dirty !== true) return;
        markDirty(frm, dirtyScope);
    }

    function captureDirtyWorkspace(frm) {
        const candidates = [
            ["PLAN", window.AlmdinaPlanWorkspaceState],
            ["COST", window.AlmdinaCostWorkspaceState],
        ].filter(([, owner]) => {
            const snapshot = owner && typeof owner.snapshot === "function" ? owner.snapshot(frm) : null;
            return Boolean(snapshot && snapshot.editing === true && snapshot.dirty === true);
        });
        if (candidates.length !== 1) return false;
        return markDirty(frm, candidates[0][0]);
    }

    function beforeSave(frm) {
        const state = currentState(frm);
        if (!state) return;
        state.saveWasNew = state.mode === "NEW" && isNew(frm);
    }

    function afterSave(frm) {
        const state = currentState(frm);
        if (!state) return;
        if (state.saveWasNew) {
            // First-insert identity binding/reconciliation belongs to ALMADINA-129.
            // Keep the existing local record discoverable, but stop this NEW session
            // from writing under a now-promoted server document identity.
            state.session.dispose();
            states.delete(frm);
            return;
        }
        if (state.mode !== "EDIT") return;
        const modified = String(frm.doc && frm.doc.modified || "").trim();
        if (!modified) return;
        // Both ordinary acknowledged Save and the characterized internal pre-plan
        // checkpoint may advance only expected_server_modified. The immutable
        // session-origin token remains owned by CheckpointSession.
        if (state.session.advanceExpectedServerModified(modified)) {
            scheduleFlush(frm, state);
        }
    }

    const orderHandlers = {
        onload(frm) { ensureState(frm); },
        refresh(frm) { ensureState(frm); },
        almdina_edit_session_changed(frm) { captureDirtyWorkspace(frm); },
        before_save: beforeSave,
        after_save: afterSave,
    };
    root.Projection.HEADER_FIELDS.forEach((fieldname) => {
        orderHandlers[fieldname] = (frm) => markDirty(frm, "DCO");
    });
    frappe.ui.form.on("Door Cutting Order", orderHandlers);

    const pieceHandlers = {
        pieces_add: (frm) => markDirty(frm, "DCO"),
        pieces_remove: (frm) => markDirty(frm, "DCO"),
    };
    root.Projection.PIECE_FIELDS.forEach((fieldname) => {
        pieceHandlers[fieldname] = (frm) => markDirty(frm, "DCO");
    });
    frappe.ui.form.on("Door Cutting Order Detail", pieceHandlers);

    if (typeof window.addEventListener === "function") {
        window.addEventListener("almdina:plan-workspace-updated", (event) => workspaceChanged(event, "PLAN"));
        window.addEventListener("almdina:cost-workspace-updated", (event) => workspaceChanged(event, "COST"));
        window.addEventListener("pagehide", () => { flushState(window.cur_frm); });
    }
    if (typeof document !== "undefined" && document.addEventListener) {
        document.addEventListener("visibilitychange", () => {
            if (document.visibilityState === "hidden") flushState(window.cur_frm);
        });
    }

    root.LocalCheckpoint = Object.freeze({
        ensureState,
        markDirty,
        flush: flushState,
        snapshot: (frm) => {
            const state = currentState(frm);
            return state ? state.session.snapshot() : null;
        },
        repository,
        assets,
    });
})();
