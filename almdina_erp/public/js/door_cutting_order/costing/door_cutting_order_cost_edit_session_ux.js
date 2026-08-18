(() => {
    "use strict";

    if (window.AlmdinaCostEditSessionUX) return;

    const COST_SETTING_FIELDS = Object.freeze([
        "board_rate_usd",
        "cutting_cost_per_board_usd",
    ]);
    const EDITABLE_ORDER_STATUSES = new Set(["Draft", "Pending Review", "Rejected"]);
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

    function can(frm, capability) {
        const permissions = window.AlmdinaPermissions;
        if (!permissions) return false;
        if (frm && typeof permissions.canDocument === "function") {
            return Boolean(permissions.canDocument(frm, capability));
        }
        return typeof permissions.can === "function" && Boolean(permissions.can(capability));
    }

    function canEditCostSettings(frm) {
        if (!frm || !frm.doc || frm.doctype !== "Door Cutting Order") return false;
        if (frm.is_new && frm.is_new()) return false;
        if (Number(frm.doc.docstatus || 0) !== 0) return false;
        if (String(frm.doc.revision_state || "Current") === "Superseded") return false;
        if (!EDITABLE_ORDER_STATUSES.has(String(frm.doc.status || "Draft"))) return false;
        return Boolean(can(frm, "view_costs") && can(frm, "edit_cost_settings"));
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

    function mountDraftControls(frm) {
        const store = storeFor(frm);
        const fieldEditor = editor();
        const state = store && store.snapshot();
        if (!store || !fieldEditor || !state || !state.editing) return false;
        fieldEditor.mount(frm, COST_SETTING_FIELDS, state.draft || {}, (patch) => {
            store.patchDraft(patch);
        });
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

    async function startEditing(frm) {
        if (!canEditCostSettings(frm)) {
            frappe.msgprint(__("لا تملك صلاحية تعديل التكلفة في حالة الطلب الحالية."));
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
            frappe.msgprint(__("تعذر تحميل إعدادات التكلفة الحالية."));
            return false;
        }
        store.beginEdit(seed);
        applyFieldAccess(frm);
        mountDraftControls(frm);
        signalEditChanged(frm);
        const fieldEditor = editor();
        if (fieldEditor && typeof fieldEditor.focus === "function") {
            fieldEditor.focus(frm, "board_rate_usd");
        }
        return true;
    }

    async function cancelEditing(frm) {
        if (!isEditing(frm)) return false;
        const store = storeFor(frm);
        if (store) store.cancelEdit();
        unmountDraftControls(frm);
        projectCurrent(frm);
        applyFieldAccess(frm);
        signalEditChanged(frm);
        return true;
    }

    async function saveEditing(frm) {
        if (!isEditing(frm)) return false;
        if (!canEditCostSettings(frm)) {
            await cancelEditing(frm);
            frappe.msgprint(__("لم تعد حالة الطلب تسمح لك بتعديل التكلفة."));
            return false;
        }

        const store = storeFor(frm);
        const state = store && store.snapshot();
        const api = window.AlmdinaCostWorkspaceAPI;
        if (!store || !state || !api || typeof api.saveSettings !== "function") return false;

        if (state.dirty) {
            await api.saveSettings(frm.doc.name, state.draft || {});
        }

        unmountDraftControls(frm);
        const owner = stateOwner();
        if (owner && typeof owner.load === "function") {
            await owner.load(frm, { force: true });
        } else {
            store.cancelEdit();
        }
        projectCurrent(frm);
        applyFieldAccess(frm);
        signalEditChanged(frm);
        frappe.show_alert({
            message: __("تم حفظ تعديلات التكلفة وإعادة القسم إلى وضع القراءة."),
            indicator: "green",
        }, 5);
        return true;
    }

    function sync(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        if (isEditing(frm) && !canEditCostSettings(frm)) {
            const store = storeFor(frm);
            if (store) store.cancelEdit();
            unmountDraftControls(frm);
            applyFieldAccess(frm);
            signalEditChanged(frm);
            return;
        }
        if (isEditing(frm)) {
            applyFieldAccess(frm);
            mountDraftControls(frm);
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
        isEditing,
        costSettingsMayWrite,
        startEditing,
        cancelEditing,
        saveEditing,
        applyFieldAccess,
        schedule,
    });
})();
