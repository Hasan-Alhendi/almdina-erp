(() => {
    "use strict";

    if (window.AlmdinaCostEditSessionUX) return;

    const COST_SETTING_FIELDS = Object.freeze([
        "board_rate_usd",
        "cutting_cost_per_board_usd",
    ]);
    const REQUIRED_COST_LABELS = Object.freeze({
        board_rate_usd: "سعر اللوح",
        cutting_cost_per_board_usd: "أجور القص / لوح",
    });
    const COST_SETTINGS_EDITABLE_ORDER_STATUSES = new Set(["Draft", "Pending Review", "Rejected"]);
    const STATUS_KEY = "__almdinaFocusedCostStatus";
    const STATUS_OWNER_KEY = "__almdinaFocusedCostStatusOwnerInstalled";

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
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
        if (!COST_SETTINGS_EDITABLE_ORDER_STATUSES.has(String(frm.doc.status || "Draft"))) return false;
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
        return true;
    }

    function unmountDraftControls(frm) {
        const fieldEditor = editor();
        if (fieldEditor && typeof fieldEditor.unmount === "function") {
            fieldEditor.unmount(frm, COST_SETTING_FIELDS);
        }
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
        return Object.fromEntries(
            COST_SETTING_FIELDS.map((fieldname) => [
                fieldname,
                draftControlValue(frm, fieldname, draft),
            ])
        );
    }

    function normalizeCostSettings(values) {
        return Object.fromEntries(
            COST_SETTING_FIELDS.map((fieldname) => {
                const raw = values ? values[fieldname] : null;
                if (raw === null || raw === undefined || String(raw).trim() === "") {
                    return [fieldname, raw];
                }
                return [fieldname, Number(raw)];
            })
        );
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

    async function startEditing(frm) {
        if (!canEditCostWorkspace(frm)) {
            frappe.msgprint(__("لا تملك صلاحية تعديل التكلفة أو تسعير الدرف الخاصة في حالة الطلب الحالية."));
            return false;
        }
        if (frm.is_dirty && frm.is_dirty()) {
            frappe.msgprint(__("احفظ أو ألغِ تعديلات الطلب الحالية قبل فتح تعديل التكلفة."));
            return false;
        }

        await ensureLoaded(frm);
        const store = storeFor(frm);
        const seed = currentSettings(frm);
        if (!store || !seed) {
            frappe.msgprint(__("تعذر تحميل بيانات التكلفة الحالية."));
            return false;
        }
        store.beginEdit(seed);
        applyFieldAccess(frm);
        if (canEditCostSettings(frm)) {
            mountDraftControls(frm);
        } else {
            unmountDraftControls(frm);
        }
        signalEditChanged(frm);
        if (canEditCostSettings(frm)) {
            const fieldEditor = editor();
            if (fieldEditor && typeof fieldEditor.focus === "function") {
                fieldEditor.focus(frm, "board_rate_usd");
            }
        }
        return true;
    }

    async function cancelEditing(frm) {
        if (!isEditing(frm)) return false;
        const store = storeFor(frm);
        if (store) store.cancelEdit();
        unmountDraftControls(frm);

        const discardedPrice = await discardPendingPriceEdits(frm);
        if (!discardedPrice) {
            projectCurrent(frm);
        }
        applyFieldAccess(frm);
        signalEditChanged(frm);
        return true;
    }

    async function saveEditing(frm) {
        if (!isEditing(frm)) return false;
        if (!canEditCostWorkspace(frm)) {
            await cancelEditing(frm);
            frappe.msgprint(__("لم تعد حالة الطلب أو صلاحياتك تسمح بتعديل هذا القسم."));
            return false;
        }

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
                const saved = await api.saveSettings(frm.doc.name, payload);
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

        unmountDraftControls(frm);
        projectCurrent(frm);
        applyFieldAccess(frm);

        // Special/clipped prices belong to their capability-protected commands,
        // but the Cost tab Save action owns this user intent. Flush them here,
        // after the settings draft closes, and reload one authoritative snapshot.
        const hadPendingPrices = pendingPricePieces(frm).length > 0;
        if (hadPendingPrices) {
            await flushPendingPriceEdits(frm, { refresh: false });
            if (owner && typeof owner.load === "function") {
                await owner.load(frm, { force: true });
            } else {
                projectCurrent(frm);
            }
        }

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
            const store = storeFor(frm);
            if (store) store.cancelEdit();
            unmountDraftControls(frm);
            // Permission/state loss must not leave an unsaved local price marker
            // that can later leak into another edit session.
            discardPendingPriceEdits(frm).catch((error) => {
                console.debug("Could not discard pending Cost price edits", error);
            });
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
        window.requestAnimationFrame(() => {
            if (window.cur_frm === frm) sync(frm);
        });
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

    window.AlmdinaCostEditSessionUX = Object.freeze({
        COST_SETTING_FIELDS,
        canEditCostSettings,
        canEditPiecePrices,
        canEditCostWorkspace,
        isEditing,
        costSettingsMayWrite,
        startEditing,
        cancelEditing,
        saveEditing,
        applyFieldAccess,
        captureCostSettings,
        normalizeCostSettings,
        validateRequiredCostSettings,
        schedule,
    });
})();
