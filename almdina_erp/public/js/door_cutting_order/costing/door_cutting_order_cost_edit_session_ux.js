(() => {
    "use strict";

    if (window.AlmdinaCostEditSessionUX) return;

    const COST_SETTING_FIELDS = Object.freeze([
        "board_rate_usd",
        "cutting_cost_per_board_usd",
    ]);
    const OFFCUT_PRICE_FIELD = "offcut_price_usd";
    const REQUIRED_COST_LABELS = Object.freeze({
        board_rate_usd: "سعر اللوح",
        cutting_cost_per_board_usd: "أجور القص / لوح",
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

    function canEditCostSettings(frm) {
        if (!baseDocumentEditable(frm)) return false;
        return Boolean(can(frm, "view_costs") && can(frm, "edit_cost_settings"));
    }

    function canEditPiecePrices(frm) {
        if (!baseDocumentEditable(frm)) return false;
        // Canonical price commands call assert_order_editable(), which is Draft-only.
        if (String(frm.doc.status || "Draft") !== "Draft") return false;
        return Boolean(
            can(frm, "view_costs")
            && (can(frm, "approve_special_price") || can(frm, "edit_special_price"))
        );
    }

    function canEditCostWorkspace(frm) {
        // One visual edit session hosts independent financial authorities. Owning
        // price approval must never imply edit_cost_settings, and vice versa.
        return canEditCostSettings(frm) || canEditPiecePrices(frm);
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
        if (draft && draft.offcut_price_applicable) {
            const input = offcutPriceInput(frm);
            values[OFFCUT_PRICE_FIELD] = input
                ? input.val()
                : draft[OFFCUT_PRICE_FIELD];
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

        const labels = missing.map((fieldname) => __(REQUIRED_COST_LABELS[fieldname] || fieldname));
        frappe.msgprint({
            title: __("حقول مطلوبة"),
            message: __("يجب إدخال القيم التالية من صفحة التكلفة قبل الحفظ: {0}")
                .replace("{0}", labels.join("، ")),
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
        if (!canEditCostWorkspace(frm)) {
            frappe.msgprint(__("لا تملك صلاحية تعديل التكلفة أو تسعير الدرف الخاصة لهذا المستند."));
            return false;
        }
        if (frm.is_dirty && frm.is_dirty()) {
            frappe.msgprint(__("احفظ أو ألغِ تعديلات الطلب الحالية قبل فتح تعديل التكلفة."));
            return false;
        }

        const token = captureDocument(frm);
        try {
            await ensureLoaded(frm);
        } catch (error) {
            if (!documentStillCurrent(frm, token)) return false;
            console.error("Cost workspace load failed while starting edit", error);
            frappe.msgprint({
                title: __("تعذر تحميل التكلفة"),
                message: __("تعذر تحميل بيانات التكلفة الحالية. أعد تحميل الطلب ثم حاول مرة أخرى."),
                indicator: "red",
            });
            return false;
        }
        if (!documentStillCurrent(frm, token)) return false;
        if (!sessionIsCurrent(frm, sessionContext)) return false;

        const store = storeFor(frm);
        const seed = currentSettings(frm);
        if (!store || !seed) {
            frappe.msgprint(__("تعذر تحميل بيانات التكلفة الحالية."));
            return false;
        }

        const started = store.beginEdit(seed);
        const startedState = store.snapshot();
        if (!started || !startedState || startedState.editing !== true) {
            frappe.msgprint({
                title: __("تعذر بدء التعديل"),
                message: __("لم تصبح بيانات التكلفة جاهزة لوضع التعديل. أعد المحاولة بعد اكتمال التحميل."),
                indicator: "orange",
            });
            return false;
        }

        // Reconcile the Cost-owned controls synchronously from the canonical store
        // before broadcasting the edit-state change to page/visual owners.
        sync(frm);
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
                frappe.msgprint(__("لم تعد صلاحياتك أو حالة هذا المستند تسمح بتعديل هذا القسم."));
            }
            return false;
        }

        const token = captureDocument(frm);
        const orderName = String(frm.doc.name || "");
        const store = storeFor(frm);
        const state = store && store.snapshot();
        const owner = stateOwner();
        if (!store || !state) return false;

        if (canEditCostSettings(frm)) {
            const api = window.AlmdinaCostWorkspaceAPI;
            if (!api || typeof api.saveSettings !== "function") return false;

            // Capture the visible controls exactly once. Validation, dirty detection,
            // and transport all consume this same payload so the UI can never show
            // one value while the workspace saves a stale draft.
            const captured = captureCostSettings(frm, state.draft || {});
            const payload = normalizeCostSettings(captured);
            store.replaceDraft(payload);
            const pending = store.snapshot();

            if (pending.dirty && !validateRequiredCostSettings(frm, captured)) {
                return false;
            }

            if (pending.dirty) {
                const saved = await api.saveSettings(orderName, payload);
                if (!documentStillCurrent(frm, token)) return false;
                if (!sessionIsCurrent(frm, sessionContext)) return false;
                if (!validSavedSnapshot(saved)) {
                    frappe.msgprint({
                        title: __("تعذر حفظ التكلفة"),
                        message: __("لم يعُد الخادم ببيانات التكلفة المحفوظة. لم يتم إغلاق وضع التعديل."),
                        indicator: "red",
                    });
                    return false;
                }
                if (owner && typeof owner.commit === "function") {
                    owner.commit(frm, saved);
                } else {
                    store.commit(saved);
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

        // Special/clipped prices belong to their capability-protected commands,
        // but the Cost tab Save action owns this user intent. Flush them here,
        // after the settings draft closes, and reload one authoritative snapshot.
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
            message: __("تم حفظ تعديلات التكلفة وإعادة القسم إلى وضع القراءة."),
            indicator: "green",
        }, 5);
        return true;
    }

    function sync(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;
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
