(() => {
    "use strict";

    function translate(message, replacements) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") {
            return locale.translate(message, replacements);
        }
        if (typeof __ === "function") {
            return replacements === undefined ? __(message) : __(message, replacements);
        }
        let text = String(message == null ? "" : message);
        if (Array.isArray(replacements)) {
            replacements.forEach((value, index) => {
                text = text.split("{" + index + "}").join(String(value));
            });
        }
        return text;
    }

    function uiDirection() {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.direction === "function") {
            const value = locale.direction();
            if (value === "ltr" || value === "rtl") return value;
        }
        const root = typeof document !== "undefined" ? document.documentElement : null;
        const dir = root && root.getAttribute("dir");
        return dir === "ltr" ? "ltr" : "rtl";
    }


    const root = window.AlmdinaDcoRecovery = window.AlmdinaDcoRecovery || Object.create(null);
    if (root.LocalCheckpoint) return;

    const CHECKPOINT_EFFECT = "dco-local-recovery-checkpoint";
    const CLEANUP_EFFECT = "dco-local-recovery-cleanup";
    const ERROR_STATUS_CLEANUP_EFFECT = "dco-local-recovery-error-status-cleanup";
    const DISCOVERY_CLEANUP_EFFECT = "dco-new-recovery-discovery-cleanup";
    const WORKSPACE_SUBSCRIPTIONS_EFFECT = "dco-local-recovery-workspace-subscriptions";
    const INACTIVE_SAVE_ERROR = "recovery_document_inactive";
    const CLEAR_ATTEMPT_MAX_TRIES = 3;
    const states = new WeakMap();
    const unownedErrorStatuses = new WeakMap();
    const initializations = new WeakMap();
    const editInitializations = new WeakMap();
    const editDismissed = new WeakSet();
    const editIneligibleNotified = new WeakSet();
    const editRestoreInProgress = new WeakSet();
    const dialogs = new WeakMap();
    const observedSaves = new WeakMap();
    const observedSaveOperations = new WeakMap();
    const workspaceSubscriptions = new WeakMap();
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

    function recoveryIdentity(draftId) {
        return {
            site: siteIdentity(),
            user: userIdentity(),
            target_doctype: "Door Cutting Order",
            draft_id: String(draftId || "").trim(),
        };
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

    function ownErrorStatusForGeneration(frm, element) {
        const context = documentContext();
        if (!frm || !element || !context || typeof context.registerCleanup !== "function") return false;
        let owner = unownedErrorStatuses.get(frm);
        if (owner) {
            owner.element = element;
            return true;
        }
        owner = { element };
        unownedErrorStatuses.set(frm, owner);
        const registered = context.registerCleanup(frm, ERROR_STATUS_CLEANUP_EFFECT, () => {
            if (owner.element && typeof owner.element.remove === "function") owner.element.remove();
            if (unownedErrorStatuses.get(frm) === owner) unownedErrorStatuses.delete(frm);
        });
        if (registered === false) {
            unownedErrorStatuses.delete(frm);
            return false;
        }
        return true;
    }

    function activeDocumentGuard(frm) {
        const context = documentContext();
        const token = context && typeof context.capture === "function"
            ? context.capture(frm)
            : null;
        return () => {
            if (context && typeof context.isCurrent === "function") {
                return context.isCurrent(frm, token);
            }
            if (
                context
                && typeof context.isSameDocument === "function"
                && !context.isSameDocument(frm, token)
            ) return false;
            return !window.cur_frm || window.cur_frm === frm;
        };
    }

    function documentTokenGuard(frm, token) {
        const context = documentContext();
        return () => {
            if (context && typeof context.isCurrent === "function") return context.isCurrent(frm, token);
            if (context && typeof context.isSameDocument === "function" && !context.isSameDocument(frm, token)) return false;
            return !window.cur_frm || window.cur_frm === frm;
        };
    }

    function abortInactiveSave() {
        const error = new Error("DCO Save was cancelled after leaving its source form");
        error.code = INACTIVE_SAVE_ERROR;
        throw error;
    }

    function quarantineExternalRevision(state, sourceCode, persistedRevision = null) {
        if (!state) return false;
        state.externalRevisionConflict = Object.freeze({
            code: "external_revision_conflict",
            source_code: String(sourceCode || "stale_revision"),
            persisted_revision: persistedRevision !== null
                && persistedRevision !== ""
                && Number.isInteger(Number(persistedRevision))
                ? Number(persistedRevision)
                : null,
        });
        return true;
    }

    async function clearProvenSaveAttempt(state, attemptedAt) {
        const expectedAttempt = String(attemptedAt || "").trim();
        if (!state || !state.session || !expectedAttempt) return false;
        const snapshot = state.session.snapshot();
        if (
            snapshot.state !== root.CheckpointSession.STATES.DISPOSED
            && snapshot.official_save_attempted_at === expectedAttempt
        ) {
            const resumed = await state.session.resumeAfterProvenFailure();
            if (resumed) return true;
        }
        const repo = repository();
        if (!repo || typeof repo.read !== "function" || typeof repo.setOfficialSaveState !== "function") {
            return false;
        }
        const identity = state.session.identity();
        for (let attempt = 0; attempt < CLEAR_ATTEMPT_MAX_TRIES; attempt += 1) {
            const current = await repo.read(identity);
            if (!current || current.ok !== true) return false;
            if (!current.value) return true;
            if (
                current.value.official_save_state !== "PENDING_RECONCILIATION"
                || current.value.official_save_attempted_at !== expectedAttempt
            ) return false;
            const result = await repo.setOfficialSaveState(
                identity,
                "ACTIVE",
                current.value.recovery_revision,
                expectedAttempt
            );
            if (
                result
                && (
                    result.ok === true
                    || (result.error && result.error.code === "draft_not_found")
                )
            ) {
                const snapshotAfterCas = state.session.snapshot();
                if (
                    result.ok === true
                    && snapshotAfterCas.state !== root.CheckpointSession.STATES.DISPOSED
                    && typeof state.session.adoptPersistedOfficialSaveState === "function"
                ) {
                    if (
                        Number(result.value && result.value.recovery_revision)
                        !== Number(snapshotAfterCas.recovery_revision)
                    ) {
                        quarantineExternalRevision(
                            state,
                            "stale_revision",
                            result.value && result.value.recovery_revision
                        );
                        return true;
                    }
                    return state.session.adoptPersistedOfficialSaveState(
                        result.value,
                        expectedAttempt
                    );
                }
                return true;
            }
            if (!result || !result.error || result.error.code !== "stale_revision") return false;
        }
        return false;
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
        if (state.statusElement) state.statusElement.remove();
        states.delete(frm);
        return null;
    }

    function domNode(value) {
        if (value && value.nodeType === 1) return value;
        if (value && typeof value.get === "function") return value.get(0) || null;
        return value && value[0] && value[0].nodeType === 1 ? value[0] : null;
    }

    function checkpointStatusText(snapshot) {
        const messages = {
            DIRTY: "Changes have not been saved locally yet.",
            LOCAL_SAVING: "Saving a local recovery copy…",
            LOCAL_SAVED: "A local recovery copy is saved; the order has not been officially saved on the server.",
            OFFICIAL_SAVING: "Saving the order officially on the server…",
            PENDING_RECONCILIATION: "The official save was sent. Its result is being verified before recovery can continue.",
            RESTORING: "Restoring the local draft…",
            COMPLETED: "The order was officially saved.",
            ERROR: "Could not save the local recovery copy. Keep this page open until the draft is resolved.",
        };
        return translate(messages[String(snapshot && snapshot.state || "")] || "");
    }

    function renderCheckpointStatus(frm, state, snapshot) {
        const message = checkpointStatusText(snapshot);
        let element = state && state.statusElement;
        if (!element || !element.isConnected) {
            const pageRoot = domNode(frm && frm.page && frm.page.wrapper);
            const formRoot = domNode(frm && (frm.$wrapper || frm.wrapper));
            const host = pageRoot && pageRoot.querySelector(".page-head") || formRoot || pageRoot;
            if (!host || typeof document.createElement !== "function") {
                if (snapshot && snapshot.state === "ERROR" && typeof frappe.show_alert === "function") {
                    frappe.show_alert({
                        message,
                        indicator: "red",
                    });
                }
                return false;
            }
            element = host.querySelector(".dco-recovery-status");
            if (!element) {
                element = document.createElement("div");
                element.className = "dco-recovery-status alert";
                element.setAttribute("role", "status");
                host.appendChild(element);
            }
        }
        if (state) state.statusElement = element;
        else if (snapshot && snapshot.state === "ERROR") ownErrorStatusForGeneration(frm, element);
        element.hidden = !message;
        element.dataset.recoveryState = String(snapshot && snapshot.state || "");
        element.className = "dco-recovery-status alert";
        if (snapshot && snapshot.state === "ERROR") {
            element.classList.add("alert-danger");
            element.setAttribute("role", "alert");
            element.setAttribute("aria-live", "assertive");
        } else if (snapshot && snapshot.state === "LOCAL_SAVED") {
            element.classList.add("alert-success");
            element.setAttribute("role", "status");
            element.setAttribute("aria-live", "polite");
        } else {
            element.classList.add("alert-info");
            element.setAttribute("role", "status");
            element.setAttribute("aria-live", "polite");
        }
        element.textContent = message;
        return element;
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

    function createState(frm, options = {}) {
        const context = documentContext();
        const repo = repository();
        const factory = root.CheckpointSession;
        if (repo && (!context || !factory || typeof factory.create !== "function")) return null;
        if (!repo) {
            renderCheckpointStatus(frm, null, { state: "ERROR" });
            return null;
        }
        if (!context || !factory || typeof factory.create !== "function") return null;
        const token = context.capture(frm);
        if (!token) return null;
        const recovered = options.record || null;
        const mode = recovered ? String(recovered.mode || "NEW") : (isNew(frm) ? "NEW" : "EDIT");
        if (recovered && mode === "EDIT" && (isNew(frm)
            || String(recovered.target_name || "") !== String(frm.doc && frm.doc.name || ""))) return null;
        const modified = mode === "EDIT" ? String(frm.doc.modified || "").trim() : null;
        if (mode === "EDIT" && !modified) return null;
        const state = {
            mode,
            documentToken: token,
            pieceKeys: new WeakMap(),
            saveWasNew: false,
            externalRevisionConflict: null,
            restored: Boolean(recovered),
            session: null,
        };
        try {
            const draftId = recovered ? String(recovered.draft_id) : uuid();
            state.session = factory.create({
                repository: repo,
                site: siteIdentity(),
                user: userIdentity(),
                mode,
                draftId,
                tabSessionId: uuid(),
                targetName: mode === "EDIT" ? String(frm.doc.name || "").trim() : null,
                sessionOriginModified: mode === "EDIT"
                    ? String(recovered && recovered.session_origin_modified || modified)
                    : null,
                expectedServerModified: mode === "EDIT"
                    ? String(recovered && recovered.expected_server_modified || modified)
                    : null,
                recoveryRevision: recovered ? Number(recovered.recovery_revision) : 0,
                savedRevision: recovered ? Number(recovered.recovery_revision) : 0,
                dirtyScope: recovered ? recovered.dirty_scope : null,
                officialSaveState: recovered
                    ? String(recovered.official_save_state || "ACTIVE")
                    : "ACTIVE",
                officialSaveAttemptedAt: recovered
                    ? recovered.official_save_attempted_at || null
                    : null,
                capture: ({ dirtyScope }) => workspaceProjection(frm, state, dirtyScope),
                onStateChange: (snapshot) => {
                    renderCheckpointStatus(frm, state, snapshot);
                    if (snapshot.state === factory.STATES.ERROR) {
                        console.debug("DCO local recovery checkpoint failed safely", snapshot.error);
                    }
                },
            });
            if (mode === "NEW") frm.doc.recovery_creation_token = draftId;
        } catch (error) {
            console.debug("DCO local recovery session is unavailable", error);
            return null;
        }
        states.set(frm, state);
        if (typeof context.registerCleanup === "function") {
            context.registerCleanup(frm, CLEANUP_EFFECT, () => {
                const active = states.get(frm);
                if (active === state) states.delete(frm);
                if (state.statusElement) state.statusElement.remove();
                const dialog = dialogs.get(frm);
                if (dialog && typeof dialog.hide === "function") dialog.hide();
                dialogs.delete(frm);
                initializations.delete(frm);
                editInitializations.delete(frm);
                restoreSaveObserver(frm);
                state.session.dispose();
            });
        }
        if (mode === "NEW") installSaveObserver(frm);
        return state;
    }

    function ensureState(frm, dirtyScope = "DCO") {
        const current = currentState(frm);
        if (current) return current;
        if (!isEligible(frm, dirtyScope)) return null;
        if (isNew(frm) && initializations.has(frm)) return null;
        return createState(frm);
    }

    function escapeHtml(value) {
        const text = String(value == null ? "" : value);
        if (frappe.utils && typeof frappe.utils.escape_html === "function") {
            return frappe.utils.escape_html(text);
        }
        return text.replace(/[&<>"']/g, (character) => ({
            "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
        })[character]);
    }

    function uiButton(options) {
        const ui = window.AlmdinaUi;
        if (!ui || typeof ui.button !== "function") {
            throw new Error("AlmdinaUi.button is required for DCO recovery actions");
        }
        return ui.button(options);
    }

    function userTimestamp(value) {
        if (frappe.datetime && typeof frappe.datetime.str_to_user === "function") {
            return frappe.datetime.str_to_user(value);
        }
        try { return new Date(value).toLocaleString("ar"); } catch (error) { return String(value || ""); }
    }

    function showRecoveryError(message) {
        if (typeof frappe.msgprint !== "function") return;
        frappe.msgprint({
            title: translate("Could not restore the draft"),
            message: String(message || translate("The local draft could not be read safely. You can start a new order.")),
            indicator: "red",
        });
    }

    async function rebuildDerivedUi(frm) {
        const rebuilders = [
            [window.AlmdinaDoorCuttingFastEntry, "render"],
            [window.AlmdinaFastEntryKeyboardUX, "install"],
            [window.AlmdinaTablePerformanceUX, "refreshAll"],
            [window.AlmdinaMeasurementToolbarUX, "polish"],
        ];
        for (const [owner, method] of rebuilders) {
            if (!owner || typeof owner[method] !== "function") continue;
            try { await owner[method](frm); } catch (error) {
                console.debug(`DCO recovered UI owner failed safely: ${method}`, error);
            }
        }
    }

    function cloneHydrationValue(value) {
        if (value === undefined) return undefined;
        const clone = typeof window.structuredClone === "function"
            ? window.structuredClone.bind(window)
            : (typeof structuredClone === "function" ? structuredClone : null);
        if (clone) {
            try { return clone(value); } catch (error) { /* fall back to JSON-safe form data */ }
        }
        return JSON.parse(JSON.stringify(value));
    }

    function captureHydrationSnapshot(frm) {
        const doc = frm && frm.doc || {};
        const headers = Object.create(null);
        root.Projection.HEADER_FIELDS.forEach((fieldname) => {
            const present = Object.prototype.hasOwnProperty.call(doc, fieldname);
            headers[fieldname] = Object.freeze({
                present,
                value: present ? cloneHydrationValue(doc[fieldname]) : undefined,
            });
        });
        const technical = Object.create(null);
        ["recovery_creation_token", "__unsaved"].forEach((fieldname) => {
            const present = Object.prototype.hasOwnProperty.call(doc, fieldname);
            technical[fieldname] = Object.freeze({
                present,
                value: present ? cloneHydrationValue(doc[fieldname]) : undefined,
            });
        });
        return Object.freeze({
            headers,
            technical,
            pieces: Array.isArray(doc.pieces)
                ? doc.pieces.map((row) => cloneHydrationValue(row))
                : [],
        });
    }

    function restoreHydrationSnapshot(frm, snapshot) {
        if (!frm || !frm.doc || !snapshot) return false;
        const doc = frm.doc;
        Object.entries(snapshot.headers || {}).forEach(([fieldname, entry]) => {
            if (entry && entry.present) doc[fieldname] = cloneHydrationValue(entry.value);
            else delete doc[fieldname];
        });
        Object.entries(snapshot.technical || {}).forEach(([fieldname, entry]) => {
            if (entry && entry.present) doc[fieldname] = cloneHydrationValue(entry.value);
            else delete doc[fieldname];
        });
        try {
            if (frappe.model && typeof frappe.model.clear_table === "function") {
                frappe.model.clear_table(doc, "pieces");
            }
        } catch (error) {
            console.debug("DCO failed hydration partial rows could not be cleared through Frappe", error);
        }
        const restoredPieces = (snapshot.pieces || []).map((row) => cloneHydrationValue(row));
        doc.pieces = restoredPieces;
        const localRegistry = typeof locals !== "undefined" ? locals : window.locals;
        if (localRegistry && typeof localRegistry === "object") {
            restoredPieces.forEach((row) => {
                const doctype = String(row && row.doctype || "").trim();
                const name = String(row && row.name || "").trim();
                if (!doctype || !name) return;
                localRegistry[doctype] = localRegistry[doctype] || {};
                localRegistry[doctype][name] = row;
            });
        }
        try {
            if (typeof frm.refresh_fields === "function") {
                frm.refresh_fields(root.Projection.HEADER_FIELDS);
            }
            if (typeof frm.refresh_field === "function") frm.refresh_field("pieces");
        } catch (error) {
            console.debug("DCO pre-hydration form was restored but refresh failed safely", error);
        }
        return true;
    }

    async function hydrateNewProjection(frm, state, dco, isCurrent = () => true) {
        if (!isCurrent()) return false;
        root.Projection.HEADER_FIELDS.forEach((fieldname) => {
            if (Object.prototype.hasOwnProperty.call(dco, fieldname)) {
                frm.doc[fieldname] = dco[fieldname];
            }
        });
        frappe.model.clear_table(frm.doc, "pieces");
        dco.pieces.forEach((piece, index) => {
            const row = frappe.model.add_child(
                frm.doc,
                "Door Cutting Order Detail",
                "pieces"
            );
            root.Projection.PIECE_FIELDS.forEach((fieldname) => {
                if (Object.prototype.hasOwnProperty.call(piece, fieldname)) {
                    row[fieldname] = piece[fieldname];
                }
            });
            row.idx = index + 1;
            row.piece_no = index + 1;
            state.pieceKeys.set(row, String(piece.piece_key));
        });
        if (typeof frm.refresh_fields === "function") {
            frm.refresh_fields(root.Projection.HEADER_FIELDS);
        }
        if (typeof frm.refresh_field === "function") frm.refresh_field("pieces");
        await rebuildDerivedUi(frm);
        if (!isCurrent()) return false;
        if (typeof frm.dirty === "function") frm.dirty();
        return true;
    }

    async function cleanupConfirmedNewDraft(frm, state, permanentName, options = {}) {
        if (typeof options.isCurrent === "function" && !options.isCurrent()) {
            return { ok: false, cancelled: true };
        }
        const snapshot = state.session.snapshot();
        const expectedRevision = options.expectedRevision == null
            ? snapshot.recovery_revision
            : Number(options.expectedRevision);
        const expectedAttemptedAt = Object.prototype.hasOwnProperty.call(
            options,
            "expectedAttemptedAt"
        )
            ? options.expectedAttemptedAt
            : snapshot.official_save_attempted_at;
        state.session.complete();
        const result = await repository().delete(
            state.session.identity(),
            expectedRevision,
            expectedAttemptedAt
        );
        if (!result || result.ok !== true) {
            console.debug("Confirmed DCO recovery cleanup remains pending", result && result.error);
        }
        state.session.dispose();
        if (states.get(frm) === state) {
            states.delete(frm);
            restoreSaveObserver(frm);
            const dialog = dialogs.get(frm);
            if (dialog && typeof dialog.hide === "function") dialog.hide();
            dialogs.delete(frm);
        }
        const mayRoute = typeof options.isCurrent !== "function" || options.isCurrent();
        if (permanentName && mayRoute && typeof frappe.set_route === "function") {
            frappe.set_route("Form", "Door Cutting Order", permanentName);
        }
        return result;
    }

    async function reconcileRecord(record) {
        const api = root.ServerReconciliation;
        if (!api || typeof api.reconcileNewCreation !== "function") {
            throw new Error("Server reconciliation is unavailable");
        }
        return api.reconcileNewCreation(record.draft_id);
    }

    function discardFailedHydration(frm, state, hydrationSnapshot = null) {
        const draftId = state.session.snapshot().draft_id;
        state.session.dispose();
        if (states.get(frm) !== state) return;
        states.delete(frm);
        restoreSaveObserver(frm);
        if (hydrationSnapshot && restoreHydrationSnapshot(frm, hydrationSnapshot)) return;
        if (frm.doc && frm.doc.recovery_creation_token === draftId) {
            frm.doc.recovery_creation_token = null;
        }
    }

    async function continueDraft(frm, record) {
        const repo = repository();
        const isCurrent = activeDocumentGuard(frm);
        let selected = record;
        if (record.official_save_state === "PENDING_RECONCILIATION") {
            const reconciliation = await reconcileRecord(record);
            if (!isCurrent()) return { cancelled: true };
            if (reconciliation.status === "CREATED") {
                const temporary = createState(frm, { record });
                if (!temporary) throw new Error("Recovery session is unavailable");
                await cleanupConfirmedNewDraft(
                    frm,
                    temporary,
                    reconciliation.door_cutting_order,
                    {
                        isCurrent,
                        expectedRevision: record.recovery_revision,
                        expectedAttemptedAt: record.official_save_attempted_at,
                    }
                );
                return { reconciled: true };
            }
            // NOT_FOUND reports the state of a single query, not the terminal
            // outcome of an earlier in-flight INSERT. Never release the marker.
            if (reconciliation.status === "NOT_FOUND") {
                showRecoveryError(translate("The official insert may still be in progress. No retry was sent. Keep this draft and check again later."));
                return { pending: true };
            }
            throw new Error(translate("Could not verify the previous save attempt. The insert was not retried."));
        }
        if (!isCurrent()) return { cancelled: true };
        const hydrationSnapshot = captureHydrationSnapshot(frm);
        const state = createState(frm, { record: selected });
        if (!state) throw new Error("Recovery session is unavailable");
        let hydration;
        try {
            hydration = await root.NewRecovery.hydrate(selected, {
                session: state.session,
                hydrationPort: (dco) => hydrateNewProjection(frm, state, dco, isCurrent),
            });
        } catch (error) {
            discardFailedHydration(frm, state, hydrationSnapshot);
            throw error;
        }
        if (!hydration.restored || !isCurrent()) {
            discardFailedHydration(frm, state, hydrationSnapshot);
            return { cancelled: true };
        }
        const dialog = dialogs.get(frm);
        if (dialog && typeof dialog.hide === "function") dialog.hide();
        dialogs.delete(frm);
        return { reconciled: false, state };
    }

    function meaningful(summary) {
        return Boolean(
            summary.piece_count
            || summary.customer
            || summary.board_description
            || summary.edge_color
            || summary.has_special_piece
        );
    }

    function discoveryHtml(summaries) {
        const cards = summaries.map((summary) => `
            <article class="dco-recovery-card" data-draft-id="${escapeHtml(summary.draft_id)}">
                <div class="dco-recovery-card__title">${escapeHtml(translate("Unsaved local draft"))}</div>
                <div><strong>${escapeHtml(translate("Last update:"))}</strong> ${escapeHtml(userTimestamp(summary.captured_at))}</div>
                <div><strong>${escapeHtml(translate("Customer:"))}</strong> ${escapeHtml(summary.customer || translate("Unspecified"))}</div>
                <div><strong>${escapeHtml(translate("Measurements:"))}</strong> ${summary.piece_count}</div>
                <div><strong>${escapeHtml(translate("Board:"))}</strong> ${escapeHtml(summary.board_description || translate("Unspecified"))}</div>
                <div><strong>${escapeHtml(translate("Edge color:"))}</strong> ${escapeHtml(summary.edge_color || translate("Unspecified"))}</div>
                ${summary.has_special_piece ? `<div class="text-warning">${escapeHtml(translate("Includes special door data"))}</div>` : ""}
                ${summary.official_save_state === "PENDING_RECONCILIATION"
                    ? `<div class="text-warning">${escapeHtml(translate("Previous official Save is pending verification. Check the result before continuing; no second insert will be sent."))}</div>`
                    : ""}
                <div class="dco-recovery-card__actions almdina-ui">
                    ${uiButton({
                        label: summary.official_save_state === "PENDING_RECONCILIATION"
                            ? translate("Check save result")
                            : translate("Continue the order"),
                        variant: "primary",
                        size: "btn-sm",
                        attrs: { "data-recovery-action": "continue" },
                    })}
                    ${uiButton({
                        label: translate("Delete the draft"),
                        variant: "danger",
                        size: "btn-sm",
                        attrs: {
                            "data-recovery-action": "delete",
                            disabled: summary.official_save_state === "PENDING_RECONCILIATION",
                        },
                    })}
                </div>
            </article>
        `).join("");
        return `
            <style>
                .dco-recovery-intro{padding:12px;border-radius:10px;background:var(--bg-light-gray);margin-bottom:12px;line-height:1.8}
                .dco-recovery-list{display:grid;gap:12px;max-height:55vh;overflow:auto}
                .dco-recovery-card{border:1px solid var(--border-color);border-radius:12px;padding:14px;display:grid;gap:6px}
                .dco-recovery-card__title{font-weight:700;color:var(--orange-700)}
                .dco-recovery-card__actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
                .dco-recovery-new{margin-top:14px;width:100%}
            </style>
            <div class="dco-recovery-intro">
                ${translate("This data is an unofficial local draft. A formal order is created only when you press Save after continuing.")}
            </div>
            <div class="dco-recovery-list">${cards}</div>
            <div class="almdina-ui">
                ${uiButton({
                    label: translate("Start a new order"),
                    variant: "secondary",
                    className: "dco-recovery-new",
                    attrs: { "data-recovery-action": "new" },
                })}
            </div>
        `;
    }

    function showDiscoveryDialog(frm, records, rejected, initialization) {
        const recovery = root.NewRecovery;
        const summaries = [];
        const accepted = new Map();
        records.forEach((record) => {
            try {
                const summary = recovery.summarize(record);
                summaries.push(summary);
                accepted.set(summary.draft_id, record);
            } catch (error) {
                rejected.push({ draft_id: String(record.draft_id || ""), code: String(error.code || "invalid_new_draft") });
            }
        });
        if (rejected.length) {
            showRecoveryError(translate("A damaged or incompatible local draft was ignored without applying any of it."));
        }
        if (!summaries.length) {
            initializations.delete(frm);
            const state = createState(frm);
            if (initialization.pendingDirty && state) markDirty(frm, "DCO");
            return null;
        }
        const displayedDraftIds = new Set(summaries.map((summary) => summary.draft_id));
        const dialog = new frappe.ui.Dialog({
            title: translate("Restore an incomplete cutting order"),
            static: true,
            fields: [{ fieldtype: "HTML", fieldname: "recovery_drafts", options: discoveryHtml(summaries) }],
        });
        dialogs.set(frm, dialog);
        dialog.show();
        if (dialog.$wrapper && typeof dialog.$wrapper.attr === "function") {
            dialog.$wrapper.attr("dir", uiDirection());
        }
        const wrapper = dialog.$wrapper && typeof dialog.$wrapper.get === "function"
            ? dialog.$wrapper.get(0)
            : dialog.$wrapper;
        if (!wrapper || typeof wrapper.addEventListener !== "function") return dialog;
        const context = documentContext();
        const ownsDiscovery = () => {
            if (initializations.get(frm) !== initialization || dialogs.get(frm) !== dialog) return false;
            const token = initialization.documentToken;
            if (!context || !token) return true;
            if (typeof context.isCurrent === "function") return context.isCurrent(frm, token);
            return typeof context.isSameDocument !== "function" || context.isSameDocument(frm, token);
        };
        if (typeof wrapper.querySelector === "function") {
            const close = wrapper.querySelector(".modal-header .btn-modal-close, .modal-header .close");
            if (close) close.hidden = true;
        }
        let actionInFlight = false;
        const frozenCards = new Set();
        const setDiscoveryActionsDisabled = (disabled) => {
            if (typeof wrapper.querySelectorAll !== "function") return;
            wrapper.querySelectorAll("[data-recovery-action]").forEach((actionButton) => {
                actionButton.disabled = disabled;
            });
        };
        const setCardActionsDisabled = (card, clickedButton, disabled) => {
            if (clickedButton) clickedButton.disabled = disabled;
            if (!card || typeof card.querySelectorAll !== "function") return;
            card.querySelectorAll("[data-recovery-action]").forEach((actionButton) => {
                actionButton.disabled = disabled;
            });
        };
        const beginDiscoveryAction = (card, button) => {
            if (actionInFlight || !ownsDiscovery()) return false;
            actionInFlight = true;
            setDiscoveryActionsDisabled(true);
            setCardActionsDisabled(card, button, true);
            return true;
        };
        const releaseDiscoveryAction = (card, button) => {
            actionInFlight = false;
            setDiscoveryActionsDisabled(false);
            setCardActionsDisabled(card, button, false);
            frozenCards.forEach((frozenCard) => setCardActionsDisabled(frozenCard, null, true));
        };
        const freezeCardActions = (card, button) => {
            frozenCards.add(card);
            setCardActionsDisabled(card, button, true);
        };
        wrapper.addEventListener("click", (event) => {
            const button = event.target.closest("[data-recovery-action]");
            if (!button || button.disabled) return;
            const action = button.dataset.recoveryAction;
            if (action === "new") {
                if (!beginDiscoveryAction(null, button)) return;
                dialog.hide();
                dialogs.delete(frm);
                const state = createState(frm);
                if (state) initializations.delete(frm);
                if (initialization.pendingDirty && state) markDirty(frm, "DCO");
                return;
            }
            const card = button.closest("[data-draft-id]");
            const record = card && accepted.get(card.dataset.draftId);
            if (!record || !beginDiscoveryAction(card, button)) return;
            if (action === "continue") {
                Promise.resolve().then(async () => {
                    const current = await repository().read(recoveryIdentity(record.draft_id));
                    if (!ownsDiscovery()) return false;
                    if (!current || current.ok !== true) {
                        throw new Error(translate("Could not verify the local draft."));
                    }
                    const currentRecord = current.value;
                    if (
                        !currentRecord
                        || Number(currentRecord.recovery_revision) !== Number(record.recovery_revision)
                        || (currentRecord.official_save_attempted_at || null)
                            !== (record.official_save_attempted_at || null)
                    ) {
                        accepted.delete(record.draft_id);
                        releaseDiscoveryAction(card, button);
                        freezeCardActions(card, button);
                        showRecoveryError(translate("The draft changed in another tab. Reopen the order before continuing it."));
                        return false;
                    }
                    const outcome = await continueDraft(frm, currentRecord);
                    if (!ownsDiscovery()) return false;
                    if (outcome && outcome.pending === true) {
                        // A query returning NOT_FOUND cannot prove the previous insert
                        // has finished. Keep discovery open and allow an explicit
                        // future recheck; deleting an unresolved attempt stays disabled.
                        releaseDiscoveryAction(card, button);
                        return false;
                    }
                    if (initializations.get(frm) === initialization) initializations.delete(frm);
                    return true;
                })
                    .catch((error) => {
                        if (!ownsDiscovery()) return;
                        releaseDiscoveryAction(card, button);
                        showRecoveryError(error && error.message);
                    });
                return;
            }
            if (action === "delete") {
                const remove = async () => {
                    const repo = repository();
                    const identity = recoveryIdentity(record.draft_id);
                    const result = await repo.delete(
                        identity,
                        record.recovery_revision,
                        record.official_save_attempted_at
                    );
                    if (!ownsDiscovery()) return;
                    if (!result || result.ok !== true) {
                        const code = String(result && result.error && result.error.code || "");
                        const ownershipConflict = ["stale_revision", "save_attempt_conflict"].includes(code);
                        if (ownershipConflict) {
                            await repo.read(identity);
                            if (!ownsDiscovery()) return;
                            accepted.delete(record.draft_id);
                            releaseDiscoveryAction(card, button);
                            freezeCardActions(card, button);
                        } else {
                            releaseDiscoveryAction(card, button);
                        }
                        showRecoveryError(
                            ownershipConflict
                                ? translate("The draft changed in another tab. Reopen the order before deleting it.")
                                : translate("Could not delete the local draft.")
                        );
                        return;
                    }
                    accepted.delete(record.draft_id);
                    displayedDraftIds.delete(record.draft_id);
                    card.remove();
                    if (!displayedDraftIds.size) {
                        dialog.hide();
                        dialogs.delete(frm);
                        initializations.delete(frm);
                        const state = createState(frm);
                        if (initialization.pendingDirty && state) markDirty(frm, "DCO");
                    } else {
                        releaseDiscoveryAction(card, button);
                    }
                };
                if (meaningful(recovery.summarize(record)) && typeof frappe.confirm === "function") {
                    frappe.confirm(
                        translate("Do you want to permanently delete this local draft?"),
                        remove,
                        () => {
                            if (ownsDiscovery()) releaseDiscoveryAction(card, button);
                        }
                    );
                } else {
                    remove();
                }
            }
        });
        return dialog;
    }

    function initializeNewForm(frm) {
        if (!isNew(frm) || currentState(frm)) return Promise.resolve(currentState(frm));
        const active = initializations.get(frm);
        if (active) return active.promise;
        const context = documentContext();
        const documentToken = context && typeof context.capture === "function"
            ? context.capture(frm)
            : null;
        const initialization = { pendingDirty: false, promise: null, documentToken };
        if (context && typeof context.registerCleanup === "function") {
            context.registerCleanup(frm, DISCOVERY_CLEANUP_EFFECT, () => {
                if (initializations.get(frm) === initialization) initializations.delete(frm);
                const dialog = dialogs.get(frm);
                if (dialog && typeof dialog.hide === "function") dialog.hide();
                dialogs.delete(frm);
            });
        }
        initialization.promise = Promise.resolve()
            .then(() => root.NewRecovery.discover(repository(), recoveryIdentity("discovery")))
            .then((result) => {
                const stillCurrent = !context
                    || (typeof context.isCurrent === "function"
                        ? context.isCurrent(frm, documentToken)
                        : (typeof context.isSameDocument !== "function"
                            || context.isSameDocument(frm, documentToken)));
                if (!stillCurrent || !isNew(frm) || currentState(frm)) return currentState(frm);
                if (!result || result.ok !== true) {
                    if (initializations.get(frm) === initialization) initializations.delete(frm);
                    const state = createState(frm);
                    if (initialization.pendingDirty && state) markDirty(frm, "DCO");
                    return state;
                }
                return showDiscoveryDialog(
                    frm,
                    [...result.value.records],
                    [...result.value.rejected],
                    initialization
                );
            })
            .catch((error) => {
                console.debug("DCO NEW recovery discovery failed safely", error);
                if (initializations.get(frm) === initialization) initializations.delete(frm);
                const stillCurrent = !context
                    || (typeof context.isCurrent === "function"
                        ? context.isCurrent(frm, documentToken)
                        : (typeof context.isSameDocument !== "function"
                            || context.isSameDocument(frm, documentToken)));
                if (!stillCurrent || !isNew(frm)) return null;
                const state = createState(frm);
                if (initialization.pendingDirty && state) markDirty(frm, "DCO");
                return state;
            });
        initializations.set(frm, initialization);
        return initialization.promise;
    }

    function editRecoveryPermission(frm) {
        const permissions = window.AlmdinaPermissions;
        const revision = window.AlmdinaOrderRevisionUX;
        return Boolean(
            frm
            && frm.doctype === "Door Cutting Order"
            && !isNew(frm)
            && Number(frm.doc && frm.doc.docstatus || 0) === 0
            && String(frm.doc && frm.doc.status || "Draft") === "Draft"
            && !String(frm.doc && frm.doc.current_production_stage || "").trim()
            && permissions
            && typeof permissions.canDocument === "function"
            && permissions.canDocument(frm, "edit_order") === true
            && revision
            && typeof revision.canOfferEditSession === "function"
            && revision.canOfferEditSession(frm) === true
        );
    }

    function lifecycleIneligibleForEditRecovery(frm) {
        return Boolean(
            !frm
            || !frm.doc
            || Number(frm.doc.docstatus || 0) !== 0
            || String(frm.doc.status || "Draft") !== "Draft"
            || String(frm.doc.current_production_stage || "").trim()
        );
    }

    function notifyRetainedEditDraft(frm) {
        if (!lifecycleIneligibleForEditRecovery(frm)
            || editIneligibleNotified.has(frm)
            || !root.EditRecovery) return Promise.resolve(null);
        const documentToken = documentContext() && documentContext().capture(frm);
        const identity = {
            ...recoveryIdentity("discovery"),
            target_name: String(frm.doc.name || "").trim(),
        };
        if (!identity.site || !identity.user || !identity.target_name) return Promise.resolve(null);
        editIneligibleNotified.add(frm);
        return root.EditRecovery.discover(repository(), identity)
            .then((result) => {
                const context = documentContext();
                const current = !context || !documentToken
                    || (typeof context.isCurrent === "function"
                        ? context.isCurrent(frm, documentToken)
                        : context.isSameDocument(frm, documentToken));
                if (!current || !result || result.ok !== true) return null;
                const retained = (result.value && result.value.records || []).some((record) => {
                    try {
                        root.EditRecovery.validateRecord(
                            record,
                            { ...identity, draft_id: record.draft_id },
                            record.expected_server_modified,
                        );
                        return true;
                    } catch (error) {
                        return false;
                    }
                });
                if (!retained) return null;
                frappe.show_alert({
                    message: translate("A local edit draft is retained. Recovery is unavailable after production dispatch. Return to Draft with permission before explicitly reviewing the draft."),
                    indicator: "orange",
                }, 8);
                return true;
            })
            .catch((error) => {
                console.debug("Ineligible DCO EDIT draft notice failed safely", error);
                return null;
            });
    }

    function cleanLoadedDocument(frm) {
        if (!frm || !frm.doc || frm.doc.__unsaved) return false;
        return typeof frm.is_dirty === "function" && frm.is_dirty() === false;
    }

    function editDiscoveryHtml(frm, summaries) {
        const cards = summaries.map((summary) => `
            <article class="dco-recovery-card" data-draft-id="${escapeHtml(summary.draft_id)}">
                <div class="dco-recovery-card__title">${escapeHtml(translate("Local edit draft"))}</div>
                <div><strong>${escapeHtml(translate("Last updated"))}</strong> ${escapeHtml(userTimestamp(summary.captured_at))}</div>
                <div><strong>${escapeHtml(translate("Customer"))}</strong> ${escapeHtml(summary.customer || translate("Not specified"))}</div>
                <div><strong>${escapeHtml(translate("Measurements"))}</strong> ${summary.piece_count}</div>
                ${summary.versionConflict
                    ? '<div class="text-warning">' + escapeHtml(translate("The server order has changed since this draft was captured. It will not be applied automatically.")) + '</div>'
                    : ""}
                <div class="dco-recovery-card__actions almdina-ui">
                    ${uiButton({
                        label: translate("Continue editing"),
                        variant: "primary",
                        size: "btn-sm",
                        attrs: {
                            "data-edit-recovery-action": "continue",
                            disabled: !cleanLoadedDocument(frm),
                        },
                    })}
                    ${uiButton({
                        label: translate("Delete draft"),
                        variant: "danger",
                        size: "btn-sm",
                        attrs: { "data-edit-recovery-action": "delete" },
                    })}
                </div>
            </article>
        `).join("");
        return `
            <div class="dco-recovery-intro">
                ${escapeHtml(translate("This local draft has not been officially saved. Its inputs will be restored only after verifying the server version. Press Save to commit officially."))}
            </div>
            <div class="dco-recovery-list">${cards}</div>
            <div class="almdina-ui" style="margin-top:12px">
                ${uiButton({
                    label: translate("Later"),
                    variant: "secondary",
                    attrs: { "data-edit-recovery-action": "dismiss" },
                })}
            </div>
        `;
    }

    function dismissEditRecoveryDialog(frm, initialization = null, markDismissed = true) {
        if (initialization && editInitializations.get(frm) !== initialization) return false;
        const dialog = dialogs.get(frm);
        if (dialog && typeof dialog.hide === "function") dialog.hide();
        if (dialogs.get(frm) === dialog) dialogs.delete(frm);
        if (!initialization || editInitializations.get(frm) === initialization) {
            editInitializations.delete(frm);
        }
        if (markDismissed) editDismissed.add(frm);
        return true;
    }

    function displayConflictValue(value) {
        if (value === null || value === undefined || value === "") return "—";
        const text = typeof value === "object" ? JSON.stringify(value) : String(value);
        return text.length > 240 ? `${text.slice(0, 237)}…` : text;
    }

    function renderEditConflict(card, details) {
        if (!card || !details || !document || typeof document.createElement !== "function") return false;
        const oldPanel = card.querySelector("[data-edit-recovery-conflict]");
        if (oldPanel) oldPanel.remove();
        const panel = document.createElement("section");
        panel.setAttribute("data-edit-recovery-conflict", "true");
        const differences = details.differences || [];
        const rows = differences.slice(0, 40).map((difference) => {
            const label = difference.section === "header"
                ? difference.identity
                : `${difference.identity}${difference.fieldname ? ` / ${difference.fieldname}` : ""}`;
            const description = difference.kind === "local_addition"
                ? translate("Local addition")
                : (difference.kind === "server_row_omitted"
                    ? translate("Server row omitted from draft")
                    : (difference.kind === "order"
                        ? translate("Server order: {0}; draft order: {1}", [displayConflictValue(difference.server_value), displayConflictValue(difference.draft_value)])
                        : `${displayConflictValue(difference.server_value)} ← ${displayConflictValue(difference.draft_value)}`));
            return `<li><strong>${escapeHtml(label)}</strong>: ${escapeHtml(description)}</li>`;
        }).join("");
        const more = differences.length > 40
            ? `<li>${escapeHtml(translate("And {0} additional differences", [differences.length - 40]))}</li>`
            : "";
        panel.innerHTML = `
            <div class="text-warning"><strong>${escapeHtml(translate("Server version conflict"))}</strong></div>
            <div>${escapeHtml(translate("Source"))} ${escapeHtml(details.source.target_doctype)} / ${escapeHtml(details.source.target_name)}</div>
            <div>${escapeHtml(translate("Draft captured"))} ${escapeHtml(details.source.captured_at || translate("Not specified"))}</div>
            <div>${escapeHtml(translate("Expected version"))} ${escapeHtml(details.versions.draft_expected)}</div>
            <div>${escapeHtml(translate("Loaded form version"))} ${escapeHtml(details.versions.loaded_form)}</div>
            <div>${escapeHtml(translate("Current server version"))} ${escapeHtml(details.versions.current_server)}</div>
            <div>${escapeHtml(translate("Allowed field differences"))}</div>
            <ul>${rows || "<li>" + escapeHtml(translate("No differences in eligible DCO fields.")) + "</li>"}${more}</ul>
            <div>${escapeHtml(translate("The draft was not applied. Copy its data or discard after review."))}</div>
            <div class="almdina-ui">${uiButton({
                label: translate("Copy draft data"),
                variant: "secondary",
                size: "btn-sm",
                attrs: { "data-edit-recovery-action": "copy" },
            })}</div>
        `;
        card.appendChild(panel);
        const continueButton = card.querySelector('[data-edit-recovery-action="continue"]');
        if (continueButton) continueButton.disabled = true;
        return true;
    }

    function currentPieceFieldStatus(frm, grid, row, fieldname) {
        const gridRow = grid.grid_rows_by_docname && grid.grid_rows_by_docname[row.name];
        if (gridRow && typeof gridRow.get_field === "function") {
            try {
                const control = gridRow.get_field(fieldname);
                if (control && typeof control.get_status === "function") return control.get_status();
            } catch (error) {
                // Off-screen or non-rendered fields fall through to Frappe's permission status.
            }
        }
        const meta = frappe.meta;
        const permissions = frappe.perm;
        if (!meta || typeof meta.get_docfield !== "function"
            || !permissions || typeof permissions.get_field_display_status !== "function") {
            return "Read";
        }
        const df = meta.get_docfield("Door Cutting Order Detail", fieldname, frm.doc.name);
        if (!df || typeof df.get_status === "function") return "Read";
        try {
            // Frappe v16.17.5: frappe/form/controls/base_control.js Control.get_status()
            // delegates to this same permission API; perm.js also checks current
            // permlevel, read-only, dependency, workflow, submit, and set-only-once state.
            return permissions.get_field_display_status(df, row, grid.perm) || "Read";
        } catch (error) {
            return "Read";
        }
    }

    function captureEditRestoreSnapshot(frm) {
        const doc = frm.doc;
        const pieces = Array.isArray(doc.pieces) ? doc.pieces : [];
        const localStore = window.locals || (frappe.model && frappe.model.locals) || null;
        const localRegistrations = localStore ? pieces.map((row) => {
            const doctype = String(row.doctype || "");
            const name = String(row.name || "");
            const table = doctype && localStore[doctype];
            return {
                doctype,
                name,
                row,
                table,
                exists: Boolean(table && Object.prototype.hasOwnProperty.call(table, name)),
                value: table && table[name],
            };
        }) : [];
        return {
            doc,
            piecesRef: doc.pieces,
            pieces: [...pieces],
            rows: pieces.map((row) => ({ row, values: Object.entries(row) })),
            headers: root.Projection.HEADER_FIELDS.map((fieldname) => ({
                fieldname,
                exists: Object.prototype.hasOwnProperty.call(doc, fieldname),
                value: doc[fieldname],
            })),
            unsavedExists: Object.prototype.hasOwnProperty.call(doc, "__unsaved"),
            unsaved: doc.__unsaved,
            frmDirtyExists: Object.prototype.hasOwnProperty.call(frm, "dirtyState"),
            frmDirty: frm.dirtyState,
            localStore,
            localRegistrations,
        };
    }

    function restoreEditRestoreSnapshot(frm, snapshot, addedRows = [], canRefresh = () => true) {
        if (!snapshot || frm.doc !== snapshot.doc) return false;
        snapshot.rows.forEach(({ row, values }) => {
            Object.keys(row).forEach((key) => { delete row[key]; });
            values.forEach(([key, value]) => { row[key] = value; });
        });
        if (Array.isArray(snapshot.piecesRef)) {
            snapshot.piecesRef.splice(0, snapshot.piecesRef.length, ...snapshot.pieces);
        }
        frm.doc.pieces = snapshot.piecesRef;
        snapshot.headers.forEach(({ fieldname, exists, value }) => {
            if (exists) frm.doc[fieldname] = value;
            else delete frm.doc[fieldname];
        });
        if (snapshot.unsavedExists) frm.doc.__unsaved = snapshot.unsaved;
        else delete frm.doc.__unsaved;
        if (snapshot.frmDirtyExists) frm.dirtyState = snapshot.frmDirty;
        else delete frm.dirtyState;
        if (snapshot.localStore) {
            snapshot.localRegistrations.forEach((saved) => {
                if (!saved.doctype || !saved.name) return;
                let table = snapshot.localStore[saved.doctype];
                if (!table && saved.table) {
                    table = saved.table;
                    snapshot.localStore[saved.doctype] = table;
                }
                if (!table) return;
                if (saved.exists) table[saved.name] = saved.value;
                else if (table[saved.name] === saved.row) delete table[saved.name];
            });
            addedRows.forEach((row) => {
                const doctype = String(row && row.doctype || "");
                const name = String(row && row.name || "");
                const table = doctype && snapshot.localStore[doctype];
                if (table && name && table[name] === row) delete table[name];
            });
        }
        try {
            if (canRefresh() && typeof frm.refresh_fields === "function") {
                frm.refresh_fields(root.Projection.HEADER_FIELDS);
            }
            if (canRefresh() && typeof frm.refresh_field === "function") frm.refresh_field("pieces");
            const grid = frm.fields_dict && frm.fields_dict.pieces && frm.fields_dict.pieces.grid;
            if (canRefresh() && grid && typeof grid.refresh === "function") grid.refresh();
        } catch (error) {
            console.debug("DCO form controls could not refresh after recovery rollback", error);
        }
        return true;
    }

    async function applyEditProjection(frm, selected, patch, guards) {
        const existingState = currentState(frm);
        const state = existingState || createState(frm, { record: selected });
        if (!state || state.mode !== "EDIT") throw new Error("Recovery session is unavailable");
        const grid = frm.fields_dict && frm.fields_dict.pieces && frm.fields_dict.pieces.grid;
        const current = () => Boolean(
            guards
            && typeof guards.isCurrent === "function"
            && guards.isCurrent()
            && typeof guards.isSessionCurrent === "function"
            && guards.isSessionCurrent()
            && typeof guards.canEdit === "function"
            && guards.canEdit()
        );
        const freshPreDispatchOwnership = async () => {
            if (!current()
                || typeof guards.refreshCapabilities !== "function"
                || typeof guards.fetchServerDocument !== "function") return false;
            let serverDoc;
            try {
                serverDoc = await guards.fetchServerDocument();
            } catch (error) {
                return false;
            }
            let capabilities;
            try {
                capabilities = await guards.refreshCapabilities();
            } catch (error) {
                return false;
            }
            if (!current()
                || !capabilities
                || !capabilities.capabilities
                || capabilities.capabilities.edit_order !== true) return false;
            return Boolean(
                serverDoc
                && Object.prototype.hasOwnProperty.call(serverDoc, "docstatus")
                && Object.prototype.hasOwnProperty.call(serverDoc, "status")
                && Object.prototype.hasOwnProperty.call(serverDoc, "current_production_stage")
                && Object.prototype.hasOwnProperty.call(serverDoc, "revision_state")
                && Object.prototype.hasOwnProperty.call(serverDoc, "modified")
                && String(serverDoc.name || "") === String(frm.doc.name || "")
                && Number(serverDoc.docstatus || 0) === 0
                && String(serverDoc.status) === "Draft"
                && !String(serverDoc.current_production_stage || "").trim()
                && String(serverDoc.revision_state || "Current") !== "Superseded"
                && String(serverDoc.modified || "") === String(guards.expectedModified || "")
                && current()
            );
        };
        if (!grid
            || !grid.df
            || String(grid.df.fieldname || "") !== "pieces"
            || String(grid.df.options || "") !== "Door Cutting Order Detail") {
            throw new Error("The DCO pieces table is unavailable in the current form");
        }
        if (!current()) throw new Error("DCO edit permission or form ownership changed before restore");

        const originalRows = [...(frm.doc.pieces || [])];
        const rowsByName = new Map(originalRows.map((row) => [String(row.name || ""), row]));
        const desiredExistingNames = new Set(patch.pieces
            .filter((item) => item.existing_name)
            .map((item) => String(item.existing_name)));
        const removedRows = originalRows.filter((row) => !desiredExistingNames.has(String(row.name || "")));
        const addsRows = patch.pieces.some((item) => !item.existing_name);
        if (removedRows.length && (
            !frappe.model
            || typeof frappe.model.clear_doc !== "function"
            || !frm.script_manager
            || typeof frm.script_manager.trigger !== "function"
        )) {
            throw new Error("Frappe child-row removal is unavailable");
        }
        if (addsRows && (
            typeof frm.add_child !== "function"
            || !frm.script_manager
            || typeof frm.script_manager.trigger !== "function"
            || grid.cannot_add_rows
            || (grid.df && grid.df.cannot_add_rows)
        )) {
            throw new Error("Frappe cannot create a restored DCO piece row");
        }

        const rollback = captureEditRestoreSnapshot(frm);
        const addedRows = [];
        const pendingPieceKeys = [];
        editRestoreInProgress.add(frm);
        try {

        // Match Frappe GridRow.remove's documented lifecycle while keeping it awaitable.
        // Its remove() wrapper does not return the run_serially promise.
        for (const row of removedRows) {
            if (!current()) throw new Error("DCO edit permission changed during row removal checks");
            await frm.script_manager.trigger("before_pieces_remove", row.doctype, row.name);
            if (!current()) throw new Error("The DCO edit session changed during row removal checks");
            // The authoritative server guard below runs once after all
            // pre-remove hooks. Per-row fetches cause O(rows) HTTP requests.
            if (!current()) throw new Error("DCO identity or edit session changed during row removal checks");
        }
        if (!current()) throw new Error("DCO edit permission changed before applying the restored rows");
        if (!await freshPreDispatchOwnership()) {
            throw new Error("DCO lifecycle, capability, or revision changed before applying the restored rows");
        }

        for (const row of removedRows) {
            if (!frappe.model || typeof frappe.model.clear_doc !== "function") {
                throw new Error("Frappe child-row removal is unavailable");
            }
            frappe.model.clear_doc(row.doctype, row.name);
        }

        const restoredRows = [];
        for (const item of patch.pieces) {
            if (!current()) throw new Error("DCO edit permission changed while applying the restored rows");
            let row = item.existing_name ? rowsByName.get(item.existing_name) : null;
            if (!row) {
                if (typeof frm.add_child !== "function") {
                    throw new Error("Frappe cannot create a restored DCO piece row");
                }
                row = frm.add_child("pieces");
                if (!row || !row.name || !Array.isArray(frm.doc.pieces)
                    || !frm.doc.pieces.includes(row)) {
                    throw new Error("Frappe did not create the restored DCO piece row");
                }
                row.__unedited = true;
                addedRows.push(row);
                pendingPieceKeys.push({ row, pieceKey: item.piece_key });
                await frm.script_manager.trigger("pieces_add", row.doctype, row.name);
                if (!current()) throw new Error("The DCO edit session changed while creating a restored piece");
                // Keep the local generation/permission fence after each
                // awaited hook; one final server verification covers the batch.
                if (!current()) throw new Error("DCO edit permission or identity changed while adding a restored piece");
            }
            Object.entries(item.values).forEach(([fieldname, value]) => {
                if (currentPieceFieldStatus(frm, grid, row, fieldname) === "Write") {
                    row[fieldname] = cloneHydrationValue(value);
                }
            });
            restoredRows.push(row);
        }

        const rows = frm.doc.pieces;
        restoredRows.forEach((row, index) => {
            const currentIndex = rows.indexOf(row);
            if (currentIndex < 0) throw new Error("A restored DCO piece lost its model identity");
            if (currentIndex !== index) rows.splice(index, 0, rows.splice(currentIndex, 1)[0]);
            row.idx = index + 1;
            row.piece_no = index + 1;
        });

        Object.entries(patch.headers).forEach(([fieldname, value]) => {
            const field = typeof frm.get_field === "function"
                ? frm.get_field(fieldname)
                : (frm.fields_dict && frm.fields_dict[fieldname]);
            if (field && typeof field.get_status === "function" && field.get_status() === "Write") {
                frm.doc[fieldname] = cloneHydrationValue(value);
            }
        });
        if (removedRows.length) {
            for (const row of removedRows) {
                if (!current()) throw new Error("The DCO edit session changed before the row removal hook");
                await frm.script_manager.trigger("pieces_remove", row.doctype, row.name);
                if (!current()) throw new Error("The DCO edit session changed during the row removal hook");
                if (!current()) throw new Error("DCO identity or edit session changed during the row removal hook");
            }
        }
        if (!current()) throw new Error("The DCO edit session changed before refreshing the restored form");
        if (typeof frm.refresh_fields === "function") frm.refresh_fields(root.Projection.HEADER_FIELDS);
        if (!current()) throw new Error("The DCO edit session changed before refreshing restored rows");
        if (typeof frm.refresh_field === "function") frm.refresh_field("pieces");
        if (!current()) throw new Error("The DCO edit session changed before rebuilding derived UI");
        await rebuildDerivedUi(frm);
        if (!current()) throw new Error("The DCO edit session changed while rebuilding derived UI");
        if (!await freshPreDispatchOwnership()) {
            throw new Error("DCO lifecycle, capability, or revision changed while rebuilding derived UI");
        }
        pendingPieceKeys.forEach(({ row, pieceKey }) => state.pieceKeys.set(row, pieceKey));
        if (!current()) throw new Error("The DCO edit session changed before marking the restore dirty");
        if (typeof frm.dirty === "function") frm.dirty();
        try {
            if (!current()) throw new Error("The DCO edit session changed before checkpointing the restore");
            state.session.markDirty("DCO");
            if (!current()) throw new Error("The DCO edit session changed before scheduling the recovery checkpoint");
            scheduleFlush(frm, state);
        } catch (error) {
            if (!current()) throw error;
            console.debug("Restored DCO edit remains in the form but could not be checkpointed", error);
        }
        return true;
        } catch (error) {
            if (typeof guards.isCurrent === "function" && guards.isCurrent()) {
                restoreEditRestoreSnapshot(frm, rollback, addedRows, guards.isCurrent);
                if (!existingState && states.get(frm) === state) {
                    states.delete(frm);
                    if (state.statusElement) state.statusElement.remove();
                    state.session.dispose();
                }
            }
            throw error;
        } finally {
            editRestoreInProgress.delete(frm);
        }
    }

    function showEditRecoveryDialog(frm, records, initialization) {
        const app = root.EditRecovery;
        const identity = {
            ...recoveryIdentity(""),
            target_name: String(frm.doc.name || "").trim(),
        };
        const summaries = [];
        const accepted = new Map();
        records.forEach((record) => {
            try {
                const dco = app.validateRecord(
                    record,
                    { ...identity, draft_id: record.draft_id },
                    record.expected_server_modified
                );
                const summary = Object.freeze({
                    draft_id: String(record.draft_id),
                    captured_at: String(record.captured_at),
                    customer: String(dco.customer || "").trim(),
                    piece_count: dco.pieces.length,
                    versionConflict: String(record.expected_server_modified || "")
                        !== String(frm.doc.modified || ""),
                });
                summaries.push(summary);
                accepted.set(summary.draft_id, record);
            } catch (error) {
                console.debug("Ignoring invalid DCO edit recovery record", error && error.code);
            }
        });
        if (!summaries.length) {
            editInitializations.delete(frm);
            return null;
        }
        const dialog = new frappe.ui.Dialog({
            title: translate("Local edit drafts"),
            static: true,
            fields: [{ fieldtype: "HTML", fieldname: "edit_recovery_drafts", options: editDiscoveryHtml(frm, summaries) }],
        });
        dialogs.set(frm, dialog);
        dialog.show();
        const wrapper = dialog.$wrapper && typeof dialog.$wrapper.get === "function"
            ? dialog.$wrapper.get(0)
            : dialog.$wrapper;
        if (!wrapper || typeof wrapper.addEventListener !== "function") return dialog;
        const context = documentContext();
        const ownsDiscovery = () => Boolean(
            editInitializations.get(frm) === initialization
            && dialogs.get(frm) === dialog
            && (!context || !initialization.documentToken
                || (typeof context.isCurrent === "function"
                    ? context.isCurrent(frm, initialization.documentToken)
                    : (typeof context.isSameDocument !== "function"
                        || context.isSameDocument(frm, initialization.documentToken))))
        );
        let actionInFlight = false;
        const buttons = () => typeof wrapper.querySelectorAll === "function"
            ? [...wrapper.querySelectorAll("[data-edit-recovery-action]")]
            : [];
        const lockButtons = (locked) => buttons().forEach((button) => { button.disabled = locked; });
        wrapper.addEventListener("click", (event) => {
            const button = event.target.closest("[data-edit-recovery-action]");
            if (!button || button.disabled || actionInFlight || !ownsDiscovery()) return;
            const action = button.dataset.editRecoveryAction;
            if (action === "dismiss") {
                dismissEditRecoveryDialog(frm, initialization);
                return;
            }
            const card = button.closest("[data-draft-id]");
            const selected = card && accepted.get(card.dataset.draftId);
            if (!selected) return;
            if (action === "copy") {
                try {
                    const scopedIdentity = { ...identity, draft_id: selected.draft_id };
                    const contents = root.EditRecovery.exportDcoProjection(selected, scopedIdentity);
                    if (!frappe.utils || typeof frappe.utils.copy_to_clipboard !== "function") {
                        throw new Error("Clipboard copy is unavailable");
                    }
                    frappe.utils.copy_to_clipboard(contents, translate("Local draft data copied."));
                } catch (error) {
                    showRecoveryError(translate("Could not copy local draft data."));
                }
                return;
            }
            actionInFlight = true;
            lockButtons(true);
            if (action === "continue") {
                let started = false;
                const guard = documentTokenGuard(frm, initialization.documentToken);
                const token = initialization.documentToken;
                const coordinator = window.AlmdinaDcoEditSessionCoordinator;
                let restoreGeneration = initialization.activeOrderSession
                    ? Number(initialization.sessionGeneration)
                    : null;
                const capability = () => editRecoveryPermission(frm);
                const isSessionCurrent = () => {
                    return restoreGeneration !== null
                        && coordinator
                        && typeof coordinator.isSessionCurrent === "function"
                        && coordinator.isSessionCurrent(frm, {
                            kind: "order",
                            document: token,
                            sessionGeneration: restoreGeneration,
                        });
                };
                const scopedIdentity = { ...identity, draft_id: selected.draft_id };
                const isSessionGenerationCurrent = () => {
                    if (!coordinator || typeof coordinator.snapshot !== "function") return false;
                    const snapshot = coordinator.snapshot(frm);
                    return Number(snapshot.sessionGeneration) === Number(
                        restoreGeneration === null ? initialization.sessionGeneration : restoreGeneration,
                    )
                        && snapshot.phase === (restoreGeneration === null ? "idle" : "editing")
                        && snapshot.activeKind === (restoreGeneration === null ? null : "order");
                };
                const operation = root.EditRecovery.restore(selected, {
                    repository: repository(),
                    identity: scopedIdentity,
                    modified: String(frm.doc.modified || ""),
                    currentModified: () => String(frm.doc.modified || ""),
                    doc: frm.doc,
                    isCurrent: guard,
                    isClean: () => cleanLoadedDocument(frm),
                    isSessionGenerationCurrent,
                    fetchServerDocument: async () => {
                        const response = await frappe.call({
                            method: "frappe.client.get",
                            type: "GET",
                            args: { doctype: "Door Cutting Order", name: identity.target_name },
                        });
                        return response && response.message;
                    },
                    canEdit: capability,
                    refreshCapabilities: async () => {
                        const permissions = window.AlmdinaPermissions;
                        if (!permissions || typeof permissions.refresh !== "function") return null;
                        return permissions.refresh();
                    },
                    expectedModified: String(frm.doc.modified || ""),
                    reuseSession: () => Boolean(
                        initialization.activeOrderSession
                        && isSessionGenerationCurrent()
                        && isSessionCurrent()
                    ),
                    canStart: () => Boolean(
                        coordinator
                        && typeof coordinator.canStart === "function"
                        && coordinator.canStart(frm, "order")
                    ),
                    startEdit: async () => {
                        if (initialization.activeOrderSession) return isSessionCurrent();
                        const result = await coordinator.start(frm, "order");
                        if (result !== true) return false;
                        const snapshot = coordinator.snapshot(frm);
                        if (!snapshot
                            || snapshot.phase !== "editing"
                            || snapshot.activeKind !== "order"
                            || Number(snapshot.sessionGeneration) !== Number(initialization.sessionGeneration) + 1) return false;
                        // Bind once, immediately after this restore successfully starts its session.
                        restoreGeneration = Number(snapshot.sessionGeneration);
                        started = true;
                        return isSessionCurrent();
                    },
                    isSessionCurrent,
                    apply: (patch) => {
                        if (!guard() || !isSessionCurrent() || !capability()) {
                            throw new Error("DCO edit permission or form ownership changed before restore");
                        }
                        const active = currentState(frm) || null;
                        if (active && active.session.snapshot().mode !== "EDIT") {
                            throw new Error("The active recovery session does not own this DCO edit");
                        }
                        return applyEditProjection(frm, selected, patch, {
                            isCurrent: guard,
                            isSessionCurrent,
                            canEdit: capability,
                            refreshCapabilities: async () => {
                                const permissions = window.AlmdinaPermissions;
                                if (!permissions || typeof permissions.refresh !== "function") return null;
                                return permissions.refresh();
                            },
                            fetchServerDocument: async () => {
                                const response = await frappe.call({
                                    method: "frappe.client.get",
                                    type: "GET",
                                    args: { doctype: "Door Cutting Order", name: identity.target_name },
                                });
                                return response && response.message;
                            },
                            expectedModified: String(frm.doc.modified || ""),
                        });
                    },
                });
                Promise.resolve(operation)
                    .then((result) => {
                        if (!ownsDiscovery()) return;
                        dismissEditRecoveryDialog(frm, initialization);
                        frappe.show_alert({
                            message: translate("The draft is restored into Edit mode. Press Save to commit it officially."),
                            indicator: "blue",
                        }, 6);
                        return result;
                    })
                    .catch(async (error) => {
                        if (started && guard() && isSessionCurrent()) {
                            try { await coordinator.cancel(frm, "order"); } catch (cancelError) { /* recovery draft remains */ }
                        }
                        if (!ownsDiscovery()) return;
                        actionInFlight = false;
                        lockButtons(false);
                        if (error && error.code === "version_conflict" && error.details) {
                            renderEditConflict(card, error.details);
                        }
                        const message = error && error.code === "dirty_document"
                            ? translate("Save or cancel current form changes before restoring the draft.")
                            : (error && error.code === "version_conflict"
                                ? translate("The server order has changed. The draft was retained and not applied.")
                                : String(error && error.message || translate("Could not restore the local draft.")));
                        showRecoveryError(message);
                    });
                return;
            }
            if (action === "delete") {
                const discard = async () => {
                    if (!ownsDiscovery()) return;
                    let result;
                    try {
                        result = await repository().delete(
                            { ...identity, draft_id: selected.draft_id },
                            selected.recovery_revision,
                            selected.official_save_attempted_at
                        );
                    } catch (error) {
                        if (!ownsDiscovery()) return;
                        actionInFlight = false;
                        lockButtons(false);
                        showRecoveryError(translate("Could not confirm local draft deletion. The draft was retained for review."));
                        return;
                    }
                    if (!ownsDiscovery()) return;
                    if (!result || result.ok !== true) {
                        actionInFlight = false;
                        lockButtons(false);
                        showRecoveryError(translate("The draft changed or could not be deleted. It was retained for review."));
                        return;
                    }
                    accepted.delete(selected.draft_id);
                    card.remove();
                    if (!accepted.size) dismissEditRecoveryDialog(frm, initialization);
                    else {
                        actionInFlight = false;
                        lockButtons(false);
                    }
                };
                if (typeof frappe.confirm === "function") {
                    frappe.confirm(translate("Delete this local edit draft permanently?"), discard, () => {
                        if (!ownsDiscovery()) return;
                        actionInFlight = false;
                        lockButtons(false);
                    });
                } else {
                    actionInFlight = false;
                    lockButtons(false);
                }
            }
        });
        return dialog;
    }

    function initializeEditForm(frm) {
        if (lifecycleIneligibleForEditRecovery(frm)) {
            notifyRetainedEditDraft(frm);
            return Promise.resolve(null);
        }
        if (!frm || isNew(frm) || currentState(frm) || editDismissed.has(frm) || !editRecoveryPermission(frm)) {
            return Promise.resolve(currentState(frm));
        }
        const active = editInitializations.get(frm);
        if (active) return active.promise;
        const context = documentContext();
        const documentToken = context && typeof context.capture === "function"
            ? context.capture(frm)
            : null;
        const identity = {
            ...recoveryIdentity("discovery"),
            target_name: String(frm.doc.name || "").trim(),
        };
        if (!identity.site || !identity.user || !identity.target_name) return Promise.resolve(null);
        const coordinator = window.AlmdinaDcoEditSessionCoordinator;
        const sessionSnapshot = coordinator && typeof coordinator.snapshot === "function"
            ? coordinator.snapshot(frm)
            : null;
        const revision = window.AlmdinaOrderRevisionUX;
        const legacyOrderSessionActive = Boolean(
            revision
            && typeof revision.isEditSessionActive === "function"
            && revision.isEditSessionActive(frm)
        );
        const coordinatorOrderSessionActive = Boolean(
            sessionSnapshot
            && sessionSnapshot.activeKind === "order"
            && sessionSnapshot.phase === "editing"
            && legacyOrderSessionActive
        );
        if (legacyOrderSessionActive && !coordinatorOrderSessionActive) return Promise.resolve(null);
        const initialization = {
            promise: null,
            documentToken,
            sessionGeneration: sessionSnapshot && sessionSnapshot.sessionGeneration,
            activeOrderSession: coordinatorOrderSessionActive,
        };
        if (context && typeof context.registerCleanup === "function") {
            context.registerCleanup(frm, `${DISCOVERY_CLEANUP_EFFECT}-edit`, () => {
                if (editInitializations.get(frm) === initialization) editInitializations.delete(frm);
                const dialog = dialogs.get(frm);
                if (dialog && typeof dialog.hide === "function") dialog.hide();
                if (dialogs.get(frm) === dialog) dialogs.delete(frm);
            });
        }
        initialization.promise = Promise.resolve()
            .then(() => root.EditRecovery.discover(repository(), identity))
            .then((result) => {
                const guard = documentTokenGuard(frm, documentToken);
                if (!guard() || !editRecoveryPermission(frm) || currentState(frm)) return null;
                const currentSnapshot = coordinator && coordinator.snapshot(frm);
                const expectedPhase = initialization.activeOrderSession ? "editing" : "idle";
                const expectedKind = initialization.activeOrderSession ? "order" : null;
                if (!currentSnapshot
                    || currentSnapshot.phase !== expectedPhase
                    || currentSnapshot.activeKind !== expectedKind
                    || Number(currentSnapshot.sessionGeneration) !== Number(initialization.sessionGeneration)) return null;
                if (!result || result.ok !== true) return null;
                return showEditRecoveryDialog(frm, [...result.value.records], initialization);
            })
            .catch((error) => {
                console.debug("DCO EDIT recovery discovery failed safely", error);
                if (editInitializations.get(frm) === initialization) editInitializations.delete(frm);
                return null;
            });
        editInitializations.set(frm, initialization);
        return initialization.promise;
    }

    function flushState(frm, state = currentState(frm)) {
        if (!state) return Promise.resolve({ ok: true, value: null });
        return state.session.flush()
            .catch((error) => ({
                ok: false,
                error: { code: String(error && error.code || "storage_failure"), message: String(error && error.message || error) },
            }))
            .then((result) => {
                const code = String(result && result.error && result.error.code || "");
                if (["stale_revision", "revision_conflict", "save_attempt_conflict"].includes(code)) {
                    quarantineExternalRevision(state, code);
                }
                return result;
            });
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
        let state = currentState(frm);
        if (!state && isNew(frm)) {
            const initialization = initializations.get(frm);
            if (initialization) initialization.pendingDirty = true;
            else initializeNewForm(frm);
            return false;
        }
        state = state || ensureState(frm, dirtyScope);
        if (!state) return false;
        if (state.externalRevisionConflict) return false;
        try {
            if (state.session.snapshot().state === root.CheckpointSession.STATES.RESTORING) return false;
            state.session.markDirty(dirtyScope);
            scheduleFlush(frm, state);
            return true;
        } catch (error) {
            renderCheckpointStatus(frm, null, { state: "ERROR" });
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

    function ensureWorkspaceSubscriptions(frm) {
        if (!frm || workspaceSubscriptions.has(frm)) return Boolean(frm);
        const unsubscribers = [
            ["PLAN", window.AlmdinaPlanWorkspaceState],
            ["COST", window.AlmdinaCostWorkspaceState],
        ].flatMap(([dirtyScope, owner]) => {
            const store = owner && typeof owner.storeFor === "function" ? owner.storeFor(frm) : null;
            if (!store || typeof store.subscribe !== "function") return [];
            return [store.subscribe((snapshot) => {
                if (!snapshot || snapshot.editing !== true || snapshot.dirty !== true) return;
                markDirty(frm, dirtyScope);
            })];
        });
        if (!unsubscribers.length) return false;
        workspaceSubscriptions.set(frm, unsubscribers);
        const context = documentContext();
        if (context && typeof context.registerCleanup === "function") {
            context.registerCleanup(frm, WORKSPACE_SUBSCRIPTIONS_EFFECT, () => {
                const current = workspaceSubscriptions.get(frm) || [];
                current.forEach((unsubscribe) => {
                    if (typeof unsubscribe === "function") unsubscribe();
                });
                workspaceSubscriptions.delete(frm);
            });
        }
        return true;
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

    function provesNoInsert(error) {
        const xhr = error && (error.xhr || error.request || error);
        const response = xhr && xhr.responseJSON || error && error.responseJSON;
        const exceptionType = String(response && response.exc_type || "");
        return Boolean(
            Number(xhr && xhr.status || 0) > 0
            && response
            && (response.exc_type || response.exception || response.exc)
            && !["DuplicateEntryError", "UniqueValidationError"].includes(exceptionType)
        );
    }

    async function handleOfficialSaveFailure(operation, error) {
        const state = operation && operation.state;
        const attemptedAt = String(operation && operation.attemptedAt || "").trim();
        if (!state || !operation.saveWasNew || state.mode !== "NEW") return;
        if (error && error.code === INACTIVE_SAVE_ERROR) {
            return;
        }
        if (provesNoInsert(error)) {
            if (!attemptedAt) return;
            const resumed = await clearProvenSaveAttempt(state, attemptedAt);
            const snapshot = state.session.snapshot();
            if (
                !resumed
                && snapshot.official_save_attempted_at === attemptedAt
                && snapshot.state !== root.CheckpointSession.STATES.DISPOSED
            ) state.session.markPendingReconciliation();
            return;
        }
        const snapshot = state.session.snapshot();
        if (
            attemptedAt
            && snapshot.official_save_attempted_at === attemptedAt
            && snapshot.state !== root.CheckpointSession.STATES.DISPOSED
        ) state.session.markPendingReconciliation();
    }

    async function handleOfficialSaveSuccess(frm, operation) {
        const state = operation && operation.state;
        if (
            !state
            || !operation.saveWasNew
            || operation.nativeInsertAllowed !== true
            || state.mode !== "NEW"
        ) return;
        await cleanupConfirmedNewDraft(frm, state, null, {
            expectedRevision: operation.attemptedRevision,
            expectedAttemptedAt: operation.cleanupAttemptedAt,
        });
    }

    function bindObservedSaveOperation(frm, state) {
        const operations = observedSaveOperations.get(frm);
        if (!operations) return null;
        const operation = [...operations].find((candidate) => (
            candidate.state === state && candidate.beforeSaveBound !== true
        ));
        if (!operation) return null;
        operation.beforeSaveBound = true;
        return operation;
    }

    function installSaveObserver(frm) {
        if (!frm || typeof frm.save !== "function" || observedSaves.has(frm)) return false;
        const original = frm.save;
        const operations = observedSaveOperations.get(frm) || new Set();
        observedSaveOperations.set(frm, operations);
        const entry = { original, observed: null, operations };
        const observed = function observedRecoverySave(...args) {
            const state = currentState(frm);
            const snapshot = state && state.session.snapshot();
            const operation = {
                state,
                saveWasNew: Boolean(
                    state
                    && state.saveWasNew
                    && state.mode === "NEW"
                    && snapshot.state === root.CheckpointSession.STATES.OFFICIAL_SAVING
                ),
                attemptedAt: snapshot && snapshot.state === root.CheckpointSession.STATES.OFFICIAL_SAVING
                    ? snapshot.official_save_attempted_at
                    : null,
                cleanupAttemptedAt: snapshot && snapshot.state === root.CheckpointSession.STATES.OFFICIAL_SAVING
                    ? snapshot.official_save_attempted_at
                    : null,
                attemptedRevision: snapshot && snapshot.state === root.CheckpointSession.STATES.OFFICIAL_SAVING
                    ? snapshot.recovery_revision
                    : null,
                beforeSaveBound: Boolean(
                    snapshot && snapshot.state === root.CheckpointSession.STATES.OFFICIAL_SAVING
                ),
                nativeInsertAllowed: Boolean(
                    snapshot && snapshot.state === root.CheckpointSession.STATES.OFFICIAL_SAVING
                ),
            };
            entry.operations.add(operation);
            const release = () => {
                entry.operations.delete(operation);
                if (
                    entry.operations.size === 0
                    && observedSaveOperations.get(frm) === entry.operations
                    && !observedSaves.has(frm)
                ) observedSaveOperations.delete(frm);
            };
            let result;
            try {
                result = original.apply(this, args);
            } catch (error) {
                return Promise.resolve(handleOfficialSaveFailure(operation, error))
                    .then(() => { throw error; })
                    .finally(release);
            }
            return Promise.resolve(result).then(
                async (value) => {
                    await handleOfficialSaveSuccess(frm, operation);
                    return value;
                },
                async (error) => {
                    await handleOfficialSaveFailure(operation, error);
                    throw error;
                }
            ).finally(release);
        };
        entry.observed = observed;
        observedSaves.set(frm, entry);
        frm.save = observed;
        return true;
    }

    function restoreSaveObserver(frm) {
        const entry = frm && observedSaves.get(frm);
        if (!entry) return false;
        if (frm.save === entry.observed) frm.save = entry.original;
        observedSaves.delete(frm);
        if (entry.operations.size === 0 && observedSaveOperations.get(frm) === entry.operations) {
            observedSaveOperations.delete(frm);
        }
        return true;
    }

    async function reconcilePendingState(frm, state, isCurrent) {
        const reconciledSnapshot = state.session.snapshot();
        const reconciledAttempt = reconciledSnapshot.official_save_attempted_at;
        const result = await root.ServerReconciliation.reconcileNewCreation(
            state.session.snapshot().draft_id
        );
        if (!isCurrent()) abortInactiveSave();
        if (result.status === "CREATED") {
            await cleanupConfirmedNewDraft(
                frm,
                state,
                result.door_cutting_order,
                {
                    isCurrent,
                    expectedRevision: reconciledSnapshot.recovery_revision,
                    expectedAttemptedAt: reconciledAttempt,
                }
            );
            if (!isCurrent()) abortInactiveSave();
            frappe.validated = false;
            return false;
        }
        // Server-side NOT_FOUND is not a proof of a completed failed insert.
        // The same creation token and pending marker must remain untouched.
        if (result.status === "NOT_FOUND") {
            frappe.validated = false;
            showRecoveryError(translate("The official insert may still be in progress. No retry was sent. Keep this draft and check again later."));
            return false;
        }
        throw new Error(translate("Could not verify the previous save attempt. The insert was not retried."));
    }

    async function beforeSave(frm) {
        let state = currentState(frm);
        if (!state && isNew(frm) && !initializations.has(frm)) initializeNewForm(frm);
        const initialization = !state && isNew(frm) ? initializations.get(frm) : null;
        if (initialization) {
            const isCurrent = activeDocumentGuard(frm);
            await initialization.promise;
            if (!isCurrent()) abortInactiveSave();
            state = currentState(frm);
            const discoveryOwnsForm = initializations.get(frm) === initialization && dialogs.has(frm);
            if (!state && !discoveryOwnsForm) return;
            frappe.validated = false;
            showRecoveryError(
                state
                    ? translate("Local save preparation finished. Press Save again to finish creating the order.")
                    : translate("Choose Continue a local draft or Start a new order before saving.")
            );
            return;
        }
        if (!state) return;
        const saveOperation = bindObservedSaveOperation(frm, state);
        const isCurrent = activeDocumentGuard(frm);
        if (state.externalRevisionConflict) {
            if (!isCurrent()) abortInactiveSave();
            frappe.validated = false;
            showRecoveryError(translate("A newer copy of this draft exists in another tab. Reopen the order to restore it before saving."));
            return;
        }
        state.saveWasNew = state.mode === "NEW" && isNew(frm);
        if (saveOperation) {
            saveOperation.saveWasNew = state.saveWasNew;
            saveOperation.attemptedAt = null;
            saveOperation.cleanupAttemptedAt = null;
            saveOperation.attemptedRevision = null;
            saveOperation.nativeInsertAllowed = false;
        }
        if (!state.saveWasNew) return;

        if (state.session.snapshot().recovery_revision === 0) {
            state.session.markDirty("DCO");
        }
        const flushed = await flushState(frm, state);
        if (!isCurrent()) abortInactiveSave();
        if (!flushed || flushed.ok !== true) {
            const code = String(flushed && flushed.error && flushed.error.code || "");
            if (["stale_revision", "revision_conflict", "save_attempt_conflict"].includes(code)) {
                quarantineExternalRevision(state, code);
                frappe.validated = false;
                showRecoveryError(
                    code === "save_attempt_conflict"
                        ? translate("Another tab is verifying a save attempt for this draft. Reopen the order to check it.")
                        : translate("A newer copy of this draft exists in another tab. Reopen the order before saving.")
                );
                return;
            }
            // Recovery is fail-safe: the native explicit Save remains usable.
            console.debug("Latest NEW checkpoint could not be flushed before official Save", flushed && flushed.error);
        }
        const current = state.session.snapshot();
        if (current.official_save_state === "PENDING_RECONCILIATION") {
            try {
                if (await reconcilePendingState(frm, state, isCurrent) !== true) return;
            } catch (error) {
                if (error && error.code === INACTIVE_SAVE_ERROR) throw error;
                if (!isCurrent()) abortInactiveSave();
                frappe.validated = false;
                showRecoveryError(translate("Could not verify the previous save attempt. The insert was not retried."));
                return;
            }
        }
        frm.doc.recovery_creation_token = state.session.snapshot().draft_id;
        const preAttempt = state.session.snapshot();
        if (saveOperation) {
            saveOperation.cleanupAttemptedAt = preAttempt.official_save_attempted_at;
            saveOperation.attemptedRevision = preAttempt.saved_revision;
        }
        const started = await state.session.beginOfficialSave();
        if (saveOperation && started && started.ok === true) {
            saveOperation.attemptedAt = started.value && started.value.official_save_attempted_at;
            saveOperation.cleanupAttemptedAt = saveOperation.attemptedAt;
            saveOperation.attemptedRevision = Number(
                started.value && started.value.recovery_revision
            );
        }
        if (!isCurrent()) {
            if (started && started.ok === true) {
                await clearProvenSaveAttempt(
                    state,
                    started.value && started.value.official_save_attempted_at
                );
            }
            abortInactiveSave();
        }
        if (!started || started.ok !== true) {
            if (started && started.error && started.error.code === "stale_revision") {
                quarantineExternalRevision(state, "stale_revision");
                frappe.validated = false;
                showRecoveryError(translate("A newer copy of this draft exists in another tab. Reopen the order before saving."));
                return;
            }
            if (started && started.error && started.error.code === "save_attempt_conflict") {
                quarantineExternalRevision(state, "save_attempt_conflict");
                frappe.validated = false;
                showRecoveryError(translate("A newer save attempt for this draft exists in another tab. Reopen the order to check it."));
                return;
            }
            // The server-side unique token still protects retries in this form;
            // local recovery failure must not disable ordinary explicit Save.
            console.debug("NEW official Save could not persist its local reconciliation marker", started && started.error);
        }
        if (saveOperation) saveOperation.nativeInsertAllowed = true;
    }

    async function afterSave(frm) {
        const state = currentState(frm);
        if (!state) return;
        if (state.saveWasNew && state.mode === "NEW") {
            const operations = observedSaveOperations.get(frm);
            if (operations && [...operations].some((operation) => (
                operation.state === state && operation.saveWasNew
            ))) return;
            const permanentName = String(frm.doc && frm.doc.name || "").trim();
            if (!isNew(frm) && permanentName) {
                await cleanupConfirmedNewDraft(frm, state, null);
            } else {
                state.session.markPendingReconciliation();
            }
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
        onload(frm) {
            if (isNew(frm)) return initializeNewForm(frm);
            if (lifecycleIneligibleForEditRecovery(frm)) notifyRetainedEditDraft(frm);
            if (!root.EditRecovery) return ensureState(frm);
            if (currentState(frm)) return ensureState(frm);
            if (isEditSessionActive(frm)) {
                const coordinator = window.AlmdinaDcoEditSessionCoordinator;
                const snapshot = coordinator && typeof coordinator.snapshot === "function"
                    ? coordinator.snapshot(frm) : null;
                if (!snapshot || snapshot.phase !== "editing" || snapshot.activeKind !== "order") return null;
                if (!root.EditRecovery) return ensureState(frm);
            }
            return initializeEditForm(frm);
        },
        refresh(frm) {
            if (isNew(frm)) return initializeNewForm(frm);
            if (lifecycleIneligibleForEditRecovery(frm)) notifyRetainedEditDraft(frm);
            if (!root.EditRecovery) return ensureState(frm);
            if (currentState(frm)) return ensureState(frm);
            if (isEditSessionActive(frm)) {
                const coordinator = window.AlmdinaDcoEditSessionCoordinator;
                const snapshot = coordinator && typeof coordinator.snapshot === "function"
                    ? coordinator.snapshot(frm) : null;
                if (!snapshot || snapshot.phase !== "editing" || snapshot.activeKind !== "order") return null;
                if (!root.EditRecovery) return ensureState(frm);
            }
            return initializeEditForm(frm);
        },
        almdina_edit_session_changed(frm) {
            ensureWorkspaceSubscriptions(frm);
            captureDirtyWorkspace(frm);
        },
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
        window.addEventListener("almdina:permissions-updated", () => {
            const frm = window.cur_frm;
            if (!frm || frm.doctype !== "Door Cutting Order" || isNew(frm)) return;
            if (editRecoveryPermission(frm)) initializeEditForm(frm);
            else dismissEditRecoveryDialog(frm, null, false);
        });
        window.addEventListener("pagehide", () => { flushState(window.cur_frm); });
    }
    if (typeof document !== "undefined" && document.addEventListener) {
        document.addEventListener("visibilitychange", () => {
            if (document.visibilityState === "hidden") flushState(window.cur_frm);
        });
    }

    root.LocalCheckpoint = Object.freeze({
        ensureState,
        initializeNewForm,
        continueDraft,
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
