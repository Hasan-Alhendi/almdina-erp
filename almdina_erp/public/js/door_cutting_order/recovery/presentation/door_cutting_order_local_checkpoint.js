(() => {
    "use strict";

    const root = window.AlmdinaDcoRecovery = window.AlmdinaDcoRecovery || Object.create(null);
    if (root.LocalCheckpoint) return;

    const CHECKPOINT_EFFECT = "dco-local-recovery-checkpoint";
    const CLEANUP_EFFECT = "dco-local-recovery-cleanup";
    const DISCOVERY_CLEANUP_EFFECT = "dco-new-recovery-discovery-cleanup";
    const WORKSPACE_SUBSCRIPTIONS_EFFECT = "dco-local-recovery-workspace-subscriptions";
    const INACTIVE_SAVE_ERROR = "recovery_document_inactive";
    const CLEAR_ATTEMPT_MAX_TRIES = 3;
    const states = new WeakMap();
    const initializations = new WeakMap();
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

    function createState(frm, options = {}) {
        const context = documentContext();
        const repo = repository();
        const factory = root.CheckpointSession;
        if (!context || !repo || !factory || typeof factory.create !== "function") return null;
        const token = context.capture(frm);
        if (!token) return null;
        const recovered = options.record || null;
        const mode = recovered ? "NEW" : (isNew(frm) ? "NEW" : "EDIT");
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
                sessionOriginModified: modified,
                expectedServerModified: modified,
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
                const dialog = dialogs.get(frm);
                if (dialog && typeof dialog.hide === "function") dialog.hide();
                dialogs.delete(frm);
                initializations.delete(frm);
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

    function userTimestamp(value) {
        if (frappe.datetime && typeof frappe.datetime.str_to_user === "function") {
            return frappe.datetime.str_to_user(value);
        }
        try { return new Date(value).toLocaleString("ar"); } catch (error) { return String(value || ""); }
    }

    function showRecoveryError(message) {
        if (typeof frappe.msgprint !== "function") return;
        frappe.msgprint({
            title: "تعذر استعادة المسودة",
            message: String(message || "تعذر قراءة المسودة المحلية بأمان. يمكنك بدء طلب جديد."),
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
            const resumed = await repo.setOfficialSaveState(
                recoveryIdentity(record.draft_id),
                "ACTIVE",
                record.recovery_revision,
                record.official_save_attempted_at
            );
            if (!resumed || resumed.ok !== true) {
                throw new Error("تعذر تأكيد جاهزية المسودة للمتابعة.");
            }
            if (!isCurrent()) return { cancelled: true };
            selected = resumed.value;
        }
        if (!isCurrent()) return { cancelled: true };
        const state = createState(frm, { record: selected });
        if (!state) throw new Error("Recovery session is unavailable");
        const hydration = await root.NewRecovery.hydrate(selected, {
            session: state.session,
            hydrationPort: (dco) => hydrateNewProjection(frm, state, dco, isCurrent),
        });
        if (!hydration.restored || !isCurrent()) return { cancelled: true };
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
                <div class="dco-recovery-card__title">مسودة غير محفوظة محليًا</div>
                <div><strong>آخر تحديث:</strong> ${escapeHtml(userTimestamp(summary.captured_at))}</div>
                <div><strong>العميل:</strong> ${escapeHtml(summary.customer || "غير محدد")}</div>
                <div><strong>القياسات:</strong> ${summary.piece_count}</div>
                <div><strong>اللوح:</strong> ${escapeHtml(summary.board_description || "غير محدد")}</div>
                <div><strong>لون القشاط:</strong> ${escapeHtml(summary.edge_color || "غير محدد")}</div>
                ${summary.has_special_piece ? '<div class="text-warning">تتضمن بيانات درفة خاصة</div>' : ""}
                <div class="dco-recovery-card__actions">
                    <button class="btn btn-primary btn-sm" data-recovery-action="continue">متابعة الطلب</button>
                    <button class="btn btn-danger btn-sm" data-recovery-action="delete">حذف المسودة</button>
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
                هذه البيانات <strong>مسودة محلية غير محفوظة رسميًا</strong>. لن يُنشأ طلب رسمي إلا عند ضغط «حفظ» بعد المتابعة.
            </div>
            <div class="dco-recovery-list">${cards}</div>
            <button class="btn btn-default dco-recovery-new" data-recovery-action="new">بدء طلب جديد</button>
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
            showRecoveryError("تم تجاهل مسودة محلية تالفة أو غير متوافقة دون تطبيق أي جزء منها.");
        }
        if (!summaries.length) {
            initializations.delete(frm);
            const state = createState(frm);
            if (initialization.pendingDirty && state) markDirty(frm, "DCO");
            return null;
        }
        const dialog = new frappe.ui.Dialog({
            title: "استعادة طلب قص غير مكتمل",
            static: true,
            fields: [{ fieldtype: "HTML", fieldname: "recovery_drafts", options: discoveryHtml(summaries) }],
        });
        dialogs.set(frm, dialog);
        dialog.show();
        const wrapper = dialog.$wrapper && typeof dialog.$wrapper.get === "function"
            ? dialog.$wrapper.get(0)
            : dialog.$wrapper;
        if (!wrapper || typeof wrapper.addEventListener !== "function") return dialog;
        if (typeof wrapper.querySelector === "function") {
            const close = wrapper.querySelector(".modal-header .btn-modal-close, .modal-header .close");
            if (close) close.hidden = true;
        }
        wrapper.addEventListener("click", (event) => {
            const button = event.target.closest("[data-recovery-action]");
            if (!button || button.disabled) return;
            const action = button.dataset.recoveryAction;
            if (action === "new") {
                dialog.hide();
                dialogs.delete(frm);
                initializations.delete(frm);
                const state = createState(frm);
                if (initialization.pendingDirty && state) markDirty(frm, "DCO");
                return;
            }
            const card = button.closest("[data-draft-id]");
            const record = card && accepted.get(card.dataset.draftId);
            if (!record) return;
            if (action === "continue") {
                button.disabled = true;
                Promise.resolve(continueDraft(frm, record))
                    .then(() => initializations.delete(frm))
                    .catch((error) => {
                        button.disabled = false;
                        showRecoveryError(error && error.message);
                    });
                return;
            }
            if (action === "delete") {
                const remove = async () => {
                    button.disabled = true;
                    const result = await repository().delete(recoveryIdentity(record.draft_id));
                    if (!result || result.ok !== true) {
                        button.disabled = false;
                        showRecoveryError("تعذر حذف المسودة المحلية.");
                        return;
                    }
                    accepted.delete(record.draft_id);
                    card.remove();
                    if (!accepted.size) {
                        dialog.hide();
                        dialogs.delete(frm);
                        initializations.delete(frm);
                        const state = createState(frm);
                        if (initialization.pendingDirty && state) markDirty(frm, "DCO");
                    }
                };
                if (meaningful(recovery.summarize(record)) && typeof frappe.confirm === "function") {
                    frappe.confirm("هل تريد حذف هذه المسودة المحلية نهائيًا؟", remove);
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
                    initializations.delete(frm);
                    return createState(frm);
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
                initializations.delete(frm);
                const stillCurrent = !context
                    || (typeof context.isCurrent === "function"
                        ? context.isCurrent(frm, documentToken)
                        : (typeof context.isSameDocument !== "function"
                            || context.isSameDocument(frm, documentToken)));
                return stillCurrent && isNew(frm) ? createState(frm) : null;
            });
        initializations.set(frm, initialization);
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
            expectedAttemptedAt: operation.attemptedAt,
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
        if (!isCurrent()) {
            if (result.status === "NOT_FOUND") {
                await clearProvenSaveAttempt(state, reconciledAttempt);
            }
            abortInactiveSave();
        }
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
        const resumed = await state.session.resumeAfterProvenFailure();
        if (!isCurrent()) abortInactiveSave();
        if (!resumed) throw new Error("تعذر تثبيت نتيجة المصالحة محليًا.");
        return true;
    }

    async function beforeSave(frm) {
        const state = currentState(frm);
        if (!state) return;
        const saveOperation = bindObservedSaveOperation(frm, state);
        const isCurrent = activeDocumentGuard(frm);
        if (state.externalRevisionConflict) {
            if (!isCurrent()) abortInactiveSave();
            frappe.validated = false;
            showRecoveryError("توجد نسخة أحدث من هذه المسودة في تبويب آخر. أعد فتح الطلب لاستعادتها قبل الحفظ.");
            return;
        }
        state.saveWasNew = state.mode === "NEW" && isNew(frm);
        if (saveOperation) {
            saveOperation.saveWasNew = state.saveWasNew;
            saveOperation.attemptedAt = null;
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
                        ? "توجد محاولة حفظ قيد التحقق لهذه المسودة في تبويب آخر. أعد فتح الطلب للتحقق منها."
                        : "توجد نسخة أحدث من هذه المسودة في تبويب آخر. أعد فتح الطلب قبل الحفظ."
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
                showRecoveryError("تعذر التحقق من نتيجة محاولة الحفظ السابقة. لم تتم إعادة الإدراج.");
                return;
            }
        }
        frm.doc.recovery_creation_token = state.session.snapshot().draft_id;
        const started = await state.session.beginOfficialSave();
        if (saveOperation && started && started.ok === true) {
            saveOperation.attemptedAt = started.value && started.value.official_save_attempted_at;
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
                showRecoveryError("توجد نسخة أحدث من هذه المسودة في تبويب آخر. أعد فتح الطلب قبل الحفظ.");
                return;
            }
            if (started && started.error && started.error.code === "save_attempt_conflict") {
                state.session.markPendingReconciliation();
                frappe.validated = false;
                showRecoveryError("توجد محاولة حفظ أحدث لهذه المسودة في تبويب آخر. أعد فتح الطلب للتحقق منها.");
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
        onload(frm) { return isNew(frm) ? initializeNewForm(frm) : ensureState(frm); },
        refresh(frm) { return isNew(frm) ? initializeNewForm(frm) : ensureState(frm); },
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
