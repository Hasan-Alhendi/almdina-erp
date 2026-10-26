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
                text = text.split(`{${index}}`).join(String(value));
            });
        }
        return text;
    }

    if (window.AlmdinaCostEditSessionUX) return;

    const COST_SETTING_FIELDS = Object.freeze([
        "board_rate_usd",
        "cutting_cost_per_board_usd",
    ]);
    const OFFCUT_PRICE_FIELD = "offcut_price_usd";
    const REQUIRED_COST_LABELS = Object.freeze({
        board_rate_usd: "Board price",
        cutting_cost_per_board_usd: "Cutting charge / board",
    });
    const STATUS_KEY = "__almdinaFocusedCostStatus";
    const STATUS_OWNER_KEY = "__almdinaFocusedCostStatusOwnerInstalled";

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function captureDocument(frm) {
        const context = documentContext();
        if (context && typeof context.capture === "function") {
            return context.capture(frm);
        }
        return Object.freeze({
            name: String(frm && frm.doc && frm.doc.name || ""),
        });
    }

    function documentStillCurrent(frm, token) {
        const context = documentContext();
        if (context && typeof context.isCurrent === "function") {
            return context.isCurrent(frm, token);
        }
        return Boolean(
            window.cur_frm === frm
            && String(frm && frm.doc && frm.doc.name || "") === String(token && token.name || "")
        );
    }

    function stateOwner() {
        return window.AlmdinaCostWorkspaceState || null;
    }

    function storeFor(frm) {
        const owner = stateOwner();
        return owner && typeof owner.storeFor === "function" ? owner.storeFor(frm) : null;
    }

    function editor() {
        return window.AlmdinaWorkspaceFieldEditor || null;
    }

    function presenterAdapter() {
        return window.AlmdinaCostWorkspacePresenterAdapter || null;
    }

    function priceOwner() {
        return window.AlmdinaCostPermissionsUX || null;
    }

    function can(frm, capability) {
        const permissions = window.AlmdinaPermissions;
        if (!permissions) return false;
        if (frm && typeof permissions.canDocument === "function") {
            return Boolean(permissions.canDocument(frm, capability));
        }
        return typeof permissions.can === "function" && Boolean(permissions.can(capability));
    }

    function baseDocumentEditable(frm) {
        if (!frm || !frm.doc || frm.doctype !== "Door Cutting Order") return false;
        if (frm.is_new && frm.is_new()) return false;
        if (Number(frm.doc.docstatus || 0) !== 0) return false;
        if (String(frm.doc.revision_state || "Current") === "Superseded") return false;
        return true;
    }

    function serverAllowsCostSettingsEdit(frm) {
        const state = workspaceSnapshot(frm);
        if (!state || state.status !== "ready" || !state.data) return null;
        if (!Object.prototype.hasOwnProperty.call(state.data, "can_edit_cost_settings")) {
            return null;
        }
        return Boolean(state.data.can_edit_cost_settings);
    }

    function canEditCostSettings(frm) {
        if (!baseDocumentEditable(frm)) return false;
        if (!hasCostSettingsCapability(frm)) return false;
        // The snapshot is the same effective document-level decision enforced by
        // the financial command. Missing/stale authority fails closed until reload.
        return serverAllowsCostSettingsEdit(frm) === true;
    }

    function hasCostSettingsCapability(frm) {
        return Boolean(can(frm, "view_costs") && can(frm, "edit_cost_settings"));
    }

    function canEditPiecePrices(frm) {
        return canEditCostSettings(frm);
    }

    function canEditCostWorkspace(frm) {
        return canEditCostSettings(frm);
    }

    function workspaceSnapshot(frm) {
        const store = storeFor(frm);
        return store ? store.snapshot() : null;
    }

    function isEditing(frm) {
        const state = workspaceSnapshot(frm);
        return Boolean(state && state.editing);
    }

    function costSettingsMayWrite() {
        // A5.2 keeps native DCO financial fields read-only. Detached workspace
        // controls own the editable draft instead of the Frappe document model.
        return false;
    }

    function installNativeStatusOwner(field) {
        if (!field || !field.df || field.df[STATUS_OWNER_KEY]) return;
        const df = field.df;
        const previousGetStatus = typeof df.get_status === "function" ? df.get_status : null;
        df.get_status = function almdinaFocusedCostFieldStatus(control) {
            if (this.hidden || this.hidden_due_to_dependency) return "None";
            if (previousGetStatus) {
                const previousStatus = previousGetStatus.call(this, control);
                if (previousStatus === "None") return "None";
            }
            return this[STATUS_KEY] === "Write" ? "Write" : "Read";
        };
        df[STATUS_OWNER_KEY] = true;
    }

    function applyFieldAccess(frm) {
        if (!frm || !frm.fields_dict) return false;
        COST_SETTING_FIELDS.forEach((fieldname) => {
            const field = frm.fields_dict[fieldname];
            if (!field || !field.df) return;
            installNativeStatusOwner(field);
            field.df[STATUS_KEY] = "Read";
            if (typeof field.refresh === "function") field.refresh();
        });
        return true;
    }

    function signalEditChanged(frm) {
        if (frm && typeof frm.trigger === "function") {
            frm.trigger("almdina_edit_session_changed");
        }
    }

    function currentSettings(frm) {
        const owner = stateOwner();
        return owner && typeof owner.settings === "function" ? owner.settings(frm) : null;
    }

    async function ensureLoaded(frm) {
        const owner = stateOwner();
        const state = workspaceSnapshot(frm);
        if (state && state.status === "ready") return state;
        if (!owner || typeof owner.load !== "function") return state;
        return owner.load(frm);
    }

    function markRequiredDraftControls(frm) {
        COST_SETTING_FIELDS.forEach((fieldname) => {
            const field = frm && frm.fields_dict && frm.fields_dict[fieldname];
            const wrapper = field && field.$wrapper;
            if (!wrapper || !wrapper.length) return;
            const control = wrapper.find(".almdina-workspace-field-editor .form-control").first();
            if (!control || !control.length) return;
            control.attr("required", "required");
            control.attr("aria-required", "true");
        });
    }

    function mountDraftControls(frm) {
        if (!canEditCostSettings(frm)) {
            unmountDraftControls(frm);
            return false;
        }
        const store = storeFor(frm);
        const fieldEditor = editor();
        const state = store && store.snapshot();
        if (!store || !fieldEditor || !state || !state.editing) return false;
        fieldEditor.mount(frm, COST_SETTING_FIELDS, state.draft || {}, (patch) => {
            store.patchDraft(patch);
        });
        markRequiredDraftControls(frm);
        mountOffcutPriceControl(frm, state);
        return true;
    }

    function offcutPriceInput(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.order_cost_invoice_html;
        const wrapper = field && field.$wrapper;
        if (!wrapper || !wrapper.length) return null;
        const input = wrapper.find("[data-offcut-price-input]").first();
        return input && input.length ? input : null;
    }

    function mountOffcutPriceControl(frm, state) {
        if (!state || !state.draft || !state.draft.offcut_price_applicable) {
            unmountOffcutPriceControl(frm);
            return false;
        }
        const input = offcutPriceInput(frm);
        if (!input) return false;
        const value = state.draft[OFFCUT_PRICE_FIELD] ?? 0;
        input.off(".almdinaOffcutPrice");
        input.val(value);
        input.prop("disabled", false);
        input.prop("readOnly", false);
        input.on("input.almdinaOffcutPrice", event => {
            const store = storeFor(frm);
            if (store) store.patchDraft({ [OFFCUT_PRICE_FIELD]: event.currentTarget.value });
        });
        return true;
    }

    function unmountOffcutPriceControl(frm) {
        const input = offcutPriceInput(frm);
        if (!input) return false;
        input.off(".almdinaOffcutPrice");
        input.prop("disabled", true);
        input.prop("readOnly", true);
        const settings = currentSettings(frm);
        const value = settings && Object.prototype.hasOwnProperty.call(settings, OFFCUT_PRICE_FIELD)
            ? settings[OFFCUT_PRICE_FIELD]
            : (frm && frm.doc ? frm.doc[OFFCUT_PRICE_FIELD] : 0);
        input.val(value ?? 0);
        return true;
    }

    function unmountDraftControls(frm) {
        const fieldEditor = editor();
        if (fieldEditor && typeof fieldEditor.unmount === "function") {
            fieldEditor.unmount(frm, COST_SETTING_FIELDS);
        }
        unmountOffcutPriceControl(frm);
    }

    function projectCurrent(frm) {
        const adapter = presenterAdapter();
        if (adapter && typeof adapter.project === "function") adapter.project(frm);
    }

    function draftControlValue(frm, fieldname, draft) {
        const field = frm && frm.fields_dict && frm.fields_dict[fieldname];
        const wrapper = field && field.$wrapper;
        const control = wrapper && wrapper.length
            ? wrapper.find(".almdina-workspace-field-editor .form-control").first()
            : null;
        if (control && control.length) return control.val();
        return draft ? draft[fieldname] : null;
    }

    function captureCostSettings(frm, draft) {
        const values = Object.fromEntries(
            COST_SETTING_FIELDS.map((fieldname) => [
                fieldname,
                draftControlValue(frm, fieldname, draft),
            ])
        );
        const input = offcutPriceInput(frm);
        if (input && input.length) {
            values[OFFCUT_PRICE_FIELD] = input.val();
        } else if (draft && Object.prototype.hasOwnProperty.call(draft, OFFCUT_PRICE_FIELD)) {
            values[OFFCUT_PRICE_FIELD] = draft[OFFCUT_PRICE_FIELD];
        }
        return values;
    }

    function normalizeCostSettings(values) {
        const normalized = Object.fromEntries(
            COST_SETTING_FIELDS.map((fieldname) => {
                const raw = values ? values[fieldname] : null;
                if (raw === null || raw === undefined || String(raw).trim() === "") {
                    return [fieldname, raw];
                }
                return [fieldname, Number(raw)];
            })
        );
        if (values && Object.prototype.hasOwnProperty.call(values, OFFCUT_PRICE_FIELD)) {
            normalized[OFFCUT_PRICE_FIELD] = Number(values[OFFCUT_PRICE_FIELD] || 0);
        }
        return normalized;
    }

    function validateRequiredCostSettings(frm, values) {
        const missing = COST_SETTING_FIELDS.filter((fieldname) => {
            const value = values ? values[fieldname] : null;
            return value === null || value === undefined || String(value).trim() === "";
        });
        if (!missing.length) return true;

        const labels = missing.map((fieldname) => REQUIRED_COST_LABELS[fieldname] || fieldname);
        frappe.msgprint({
            title: translate("Required fields"),
            message: translate("Enter these cost-page values before saving: {0}", [
                labels.map(label => translate(label)).join(", "),
            ]),
            indicator: "orange",
        });
        const fieldEditor = editor();
        if (fieldEditor && typeof fieldEditor.focus === "function") {
            fieldEditor.focus(frm, missing[0]);
        }
        return false;
    }

    function validSavedSnapshot(payload) {
        return Boolean(
            payload
            && payload.order
            && Object.prototype.hasOwnProperty.call(payload.order, "board_rate_usd")
            && Object.prototype.hasOwnProperty.call(payload.order, "cutting_cost_per_board_usd")
        );
    }

    function pendingPricePieces(frm) {
        const owner = priceOwner();
        if (!owner || typeof owner.pendingPricePieces !== "function") return [];
        return owner.pendingPricePieces(frm) || [];
    }

    function pendingSpecialPrices(frm) {
        const owner = priceOwner();
        if (!owner || typeof owner.pendingSpecialPrices !== "function") return [];
        return owner.pendingSpecialPrices(frm) || [];
    }

    function clearPendingSpecialPrices(frm) {
        const owner = priceOwner();
        if (owner && typeof owner.clearPendingSpecialPrices === "function") {
            owner.clearPendingSpecialPrices(frm);
        }
    }

    async function flushPendingPriceEdits(frm, options = {}) {
        const owner = priceOwner();
        if (!owner || typeof owner.flushPendingPriceEdits !== "function") return false;
        return Boolean(await owner.flushPendingPriceEdits(frm, options));
    }

    async function discardPendingPriceEdits(frm, options = {}) {
        const owner = priceOwner();
        if (!owner || typeof owner.discardPendingPriceEdits !== "function") return false;
        return Boolean(await owner.discardPendingPriceEdits(frm, options));
    }

    function sessionIsCurrent(frm, sessionContext) {
        if (!sessionContext) return documentStillCurrent(frm, captureDocument(frm));
        const coordinator = editSessionCoordinator();
        return Boolean(
            coordinator
            && typeof coordinator.isSessionCurrent === "function"
            && coordinator.isSessionCurrent(frm, sessionContext)
        );
    }

    async function startEditing(frm, sessionContext = null) {
        // A read-only snapshot is needed to obtain the server's document-level
        // decision. Local capability checks may start that GET, but never grant
        // the edit session until the returned decision is true.
        if (!baseDocumentEditable(frm) || !hasCostSettingsCapability(frm)) {
            frappe.msgprint(translate("You do not have permission to edit the cost or special-door prices for this document."));
            return false;
        }
        if (frm.is_dirty && frm.is_dirty()) {
            frappe.msgprint(translate("Save or cancel the current order edits before opening cost editing."));
            return false;
        }

        const token = captureDocument(frm);
        try {
            await ensureLoaded(frm);
        } catch (error) {
            if (!documentStillCurrent(frm, token)) return false;
            console.error("Cost workspace load failed while starting edit", error);
            frappe.msgprint({
                title: translate("Could not load the cost"),
                message: translate("Could not load the current cost data. Reload the order and try again."),
                indicator: "red",
            });
            return false;
        }
        if (!documentStillCurrent(frm, token)) return false;
        if (!sessionIsCurrent(frm, sessionContext)) return false;
        if (!canEditCostWorkspace(frm)) {
            frappe.msgprint(translate("Your permissions or this document state no longer allow editing this section."));
            return false;
        }

        const store = storeFor(frm);
        const seed = currentSettings(frm);
        if (!store || !seed) {
            frappe.msgprint(translate("Could not load the current cost data."));
            return false;
        }

        const started = store.beginEdit(seed);
        const startedState = store.snapshot();
        if (!started || !startedState || startedState.editing !== true) {
            frappe.msgprint({
                title: translate("Could not start editing"),
                message: translate("The cost data is not ready for editing. Try again after loading finishes."),
                indicator: "orange",
            });
            return false;
        }

        // Reconcile the Cost-owned controls synchronously from the canonical store
        // before broadcasting the edit-state change to page/visual owners.
        sync(frm);
        revealCostSettings(frm);
        signalEditChanged(frm);
        if (canEditCostSettings(frm)) {
            const fieldEditor = editor();
            if (fieldEditor && typeof fieldEditor.focus === "function") {
                fieldEditor.focus(frm, "board_rate_usd");
            }
        }
        return true;
    }

    async function cancelEditing(frm, sessionContext = null) {
        if (!sessionIsCurrent(frm, sessionContext)) return false;
        if (!isEditing(frm)) return false;
        const token = captureDocument(frm);
        const store = storeFor(frm);
        if (store) store.cancelEdit();
        unmountDraftControls(frm);

        // Cancel restores the authoritative snapshot already held by the store.
        // Discard inline price markers without starting a network read that could
        // compete with the edit-session transition.
        await discardPendingPriceEdits(frm, { refresh: false });
        if (!documentStillCurrent(frm, token)) return false;
        if (!sessionIsCurrent(frm, sessionContext)) return false;

        sync(frm);
        signalEditChanged(frm);
        return true;
    }

    async function saveEditing(frm, sessionContext = null) {
        if (!sessionIsCurrent(frm, sessionContext)) return false;
        if (!isEditing(frm)) return false;
        if (!canEditCostWorkspace(frm)) {
            await cancelEditing(frm, sessionContext);
            if (!sessionIsCurrent(frm, sessionContext)) return false;
            if (window.cur_frm === frm) {
                frappe.msgprint(translate("Your permissions or this document state no longer allow editing this section."));
            }
            return false;
        }

        const token = captureDocument(frm);
        const orderName = String(frm.doc.name || "");
        const store = storeFor(frm);
        const state = store && store.snapshot();
        const owner = stateOwner();
        if (!store || !state) return false;

        const offcutUx = window.AlmdinaCostOffcutAssignmentUX;
        let pendingOffcutPrice = null;
        const hasPendingOffcut = Boolean(
            offcutUx
            && typeof offcutUx.hasPending === "function"
            && offcutUx.hasPending(frm)
        );
        if (hasPendingOffcut) {
            // Capture the price before the classification mutation refreshes the
            // read projection; then restore the edit draft before saving settings.
            const capturedBeforeOffcut = captureCostSettings(frm, state.draft || {});
            pendingOffcutPrice = capturedBeforeOffcut.offcut_price_usd;
            store.replaceDraft(normalizeCostSettings(capturedBeforeOffcut));
            const savedOffcut = await offcutUx.savePending(frm);
            if (!savedOffcut) return false;
            if (!documentStillCurrent(frm, token)) return false;
            if (!sessionIsCurrent(frm, sessionContext)) return false;
            sync(frm);
            // The aggregate OFFCUT price is valid only while at least one
            // physical piece remains FACTORY→FACTORY. Clear the hidden draft
            // value before saving a new non-factory classification.
            if (typeof offcutUx.hasFactorySelection === "function"
                && !offcutUx.hasFactorySelection(frm)) {
                pendingOffcutPrice = 0;
                const priceInput = offcutPriceInput(frm);
                if (priceInput && priceInput.length) priceInput.val(0);
                store.patchDraft({ [OFFCUT_PRICE_FIELD]: 0 });
            }
        }

        if (canEditCostSettings(frm)) {
            const api = window.AlmdinaCostWorkspaceAPI;
            if (!api || typeof api.saveWorkspace !== "function") return false;

            // Capture the visible controls exactly once. Validation, dirty detection,
            // and transport all consume this same payload so the UI can never show
            // one value while the workspace saves a stale draft.
            const currentState = store.snapshot() || state;
            // Keep the original capture contract explicit for static lifecycle checks.
            // const captured = captureCostSettings(frm, state.draft || {});
            const captured = captureCostSettings(frm, currentState.draft || {});
            if (pendingOffcutPrice !== null && pendingOffcutPrice !== undefined
                && String(pendingOffcutPrice).trim() !== "") {
                captured.offcut_price_usd = pendingOffcutPrice;
            }
            const payload = normalizeCostSettings(captured);
            store.replaceDraft(payload);
            const pending = store.snapshot();
            const specialPrices = pendingSpecialPrices(frm);

            if (pending.dirty && !canEditCostSettings(frm)) {
                frappe.msgprint({
                    title: translate("Missing permission"),
                    message: translate("You do not have permission to edit cost settings."),
                    indicator: "orange",
                });
                return false;
            }

            if (pending.dirty && !validateRequiredCostSettings(frm, captured)) {
                return false;
            }

            if (pending.dirty || specialPrices.length) {
                const expectedModified = String(
                    currentState.data && currentState.data.order_modified
                    || frm.doc.modified
                    || ""
                ).trim();
                if (!expectedModified) {
                    frappe.msgprint({
                        title: translate("Could not save the cost"),
                        message: translate("Could not verify the current order revision. Reload the order and try again."),
                        indicator: "red",
                    });
                    return false;
                }
                const saved = await api.saveWorkspace(
                    orderName,
                    {
                        cost_settings: pending.dirty ? payload : null,
                        special_prices: specialPrices,
                    },
                    expectedModified
                );
                if (!documentStillCurrent(frm, token)) return false;
                if (!sessionIsCurrent(frm, sessionContext)) return false;
                if (!validSavedSnapshot(saved)) {
                    frappe.msgprint({
                        title: translate("Could not save the cost"),
                        message: translate("The server did not return the saved cost data. Editing was not closed."),
                        indicator: "red",
                    });
                    return false;
                }
                clearPendingSpecialPrices(frm);
                if (owner && typeof owner.commit === "function") {
                    owner.commit(frm, saved);
                } else {
                    store.commit(saved);
                }
                const approvalUx = window.AlmdinaFinalPriceApprovalUX;
                if (approvalUx && typeof approvalUx.consumeInvalidationSignal === "function") {
                    approvalUx.consumeInvalidationSignal(frm, saved, token);
                }
            } else {
                store.cancelEdit();
            }
        } else {
            // Price-only authority owns no board/cutting settings draft.
            store.cancelEdit();
        }

        if (!documentStillCurrent(frm, token)) return false;
        if (!sessionIsCurrent(frm, sessionContext)) return false;
        unmountDraftControls(frm);
        projectCurrent(frm);
        applyFieldAccess(frm);

        // Clipped-corner pricing keeps its independent command. Special prices
        // were already part of the unified Cost save above; flush only remaining
        // clipped edits and reload one authoritative snapshot.
        const hadPendingPrices = pendingPricePieces(frm).length > 0;
        if (hadPendingPrices) {
            const flushed = await flushPendingPriceEdits(frm, { refresh: false });
            if (!documentStillCurrent(frm, token)) return false;
            if (!sessionIsCurrent(frm, sessionContext)) return false;
            if (!flushed) return false;
            if (owner && typeof owner.load === "function") {
                await owner.load(frm, { force: true });
                if (!documentStillCurrent(frm, token)) return false;
                if (!sessionIsCurrent(frm, sessionContext)) return false;
            } else {
                projectCurrent(frm);
            }
        }

        sync(frm);
        signalEditChanged(frm);
        frappe.show_alert({
            message: translate("The cost and special door price edits were saved and the section returned to read-only."),
            indicator: "green",
        }, 5);
        return true;
    }

    function coordinatorSnapshot(frm) {
        const coordinator = editSessionCoordinator();
        return coordinator && typeof coordinator.snapshot === "function"
            ? coordinator.snapshot(frm)
            : null;
    }

    function isCoordinatorStartingCost(frm) {
        const snap = coordinatorSnapshot(frm);
        return Boolean(snap && snap.activeKind === "cost" && snap.phase === "starting");
    }

    function revealCostSettings(frm) {
        const layout = window.AlmdinaCostPageLayoutUX;
        if (layout && typeof layout.revealSettings === "function") {
            layout.revealSettings(frm);
            return true;
        }
        if (layout && typeof layout.enhance === "function") {
            layout.enhance(frm);
            return true;
        }
        return false;
    }

    function sync(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        // The coordinator emits "starting" before beginEdit. A read-mode
        // reconcile here would refresh/unmount relocated native rate fields
        // while the Cost HTML shell still hosts them.
        if (!isEditing(frm) && isCoordinatorStartingCost(frm)) return;
        if (isEditing(frm) && !canEditCostWorkspace(frm)) {
            const coordinator = editSessionCoordinator();
            if (coordinator && typeof coordinator.activeKind === "function" && coordinator.activeKind(frm) === "cost") {
                coordinator.cancel(frm, "cost");
                return;
            }
            const store = storeFor(frm);
            if (store) store.cancelEdit();
            unmountDraftControls(frm);
            // Permission/state loss must not leave an unsaved local price marker
            // that can later leak into another edit session. No authoritative GET
            // is needed: the stored snapshot already owns the read projection.
            discardPendingPriceEdits(frm, { refresh: false }).catch((error) => {
                console.debug("Could not discard pending Cost price edits", error);
            });
            projectCurrent(frm);
            applyFieldAccess(frm);
            signalEditChanged(frm);
            return;
        }
        if (isEditing(frm)) {
            applyFieldAccess(frm);
            if (canEditCostSettings(frm)) {
                mountDraftControls(frm);
            } else {
                unmountDraftControls(frm);
            }
            return;
        }
        unmountDraftControls(frm);
        projectCurrent(frm);
        applyFieldAccess(frm);
    }

    function schedule(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        const context = documentContext();
        if (context && typeof context.scheduleFrame === "function") {
            context.scheduleFrame(frm, "cost-settings-edit-session", () => sync(frm));
            return;
        }
        if (window.requestAnimationFrame) {
            window.requestAnimationFrame(() => {
                if (window.cur_frm === frm) sync(frm);
            });
            return;
        }
        if (window.cur_frm === frm) sync(frm);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
        almdina_edit_session_changed(frm) { schedule(frm); },
    });

    ["almdina:permissions-updated", "almdina:cost-workspace-updated"].forEach((eventName) => {
        window.addEventListener(eventName, () => {
            const frm = window.cur_frm;
            if (frm && frm.doctype === "Door Cutting Order") schedule(frm);
        });
    });

    function editSessionCoordinator() {
        return window.AlmdinaDcoEditSessionCoordinator || null;
    }

    function coordinated(command, frm, fallback) {
        const coordinator = editSessionCoordinator();
        if (!coordinator || typeof coordinator[command] !== "function") return fallback(frm);
        return coordinator[command](frm, "cost");
    }

    const coordinator = editSessionCoordinator();
    if (coordinator && typeof coordinator.register === "function") {
        coordinator.register("cost", {
            canStart: canEditCostWorkspace,
            start: startEditing,
            save: saveEditing,
            cancel: cancelEditing,
            isDirty(frm) {
                const state = workspaceSnapshot(frm);
                return Boolean(state && state.dirty);
            },
        });
    }

    window.AlmdinaCostEditSessionUX = Object.freeze({
        COST_SETTING_FIELDS,
        canEditCostSettings,
        canEditPiecePrices,
        canEditCostWorkspace,
        isEditing,
        costSettingsMayWrite,
        startEditing: frm => coordinated("start", frm, startEditing),
        cancelEditing: frm => coordinated("cancel", frm, cancelEditing),
        saveEditing: frm => coordinated("save", frm, saveEditing),
        applyFieldAccess,
        captureCostSettings,
        normalizeCostSettings,
        validateRequiredCostSettings,
        sync,
        schedule,
    });
})();
