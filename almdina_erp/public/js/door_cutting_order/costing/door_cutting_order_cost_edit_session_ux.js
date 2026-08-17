(() => {
    "use strict";

    if (window.AlmdinaCostEditSessionUX) return;

    const COST_SETTING_FIELDS = Object.freeze([
        "board_rate_usd",
        "cutting_cost_per_board_usd",
    ]);
    const EDITABLE_ORDER_STATUSES = new Set(["Draft", "Pending Review", "Rejected"]);
    const EDITING_KEY = "__almdina_cost_settings_editing";
    const IDENTITY_KEY = "__almdina_cost_settings_edit_identity";
    const BASELINE_KEY = "__almdina_cost_settings_edit_baseline";
    const STATUS_KEY = "__almdinaFocusedCostStatus";
    const STATUS_OWNER_KEY = "__almdinaFocusedCostStatusOwnerInstalled";
    const SAVE_METHOD =
        "almdina_erp.almdina_erp.services.cost_permission_service.update_order_cost_settings";

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function formIdentity(frm) {
        const context = documentContext();
        if (context && typeof context.formIdentity === "function") {
            return context.formIdentity(frm);
        }
        if (!frm || !frm.doc) return "";
        return `${frm.doctype || frm.doc.doctype || ""}::${frm.doc.name || "__new__"}`;
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
        return Boolean(
            can(frm, "view_costs")
            && can(frm, "edit_cost_settings")
        );
    }

    function isEditing(frm) {
        if (!frm || !frm.doc || frm[EDITING_KEY] !== true) return false;
        return frm[IDENTITY_KEY] === formIdentity(frm);
    }

    function costSettingsMayWrite(frm) {
        return Boolean(isEditing(frm) && canEditCostSettings(frm));
    }

    function setEditing(frm, enabled) {
        if (!frm) return;
        frm[EDITING_KEY] = Boolean(enabled);
        frm[IDENTITY_KEY] = enabled ? formIdentity(frm) : null;
        if (!enabled) frm[BASELINE_KEY] = null;
    }

    function captureBaseline(frm) {
        frm[BASELINE_KEY] = {
            board_rate_usd: Number(frm.doc.board_rate_usd || 0),
            cutting_cost_per_board_usd: Number(frm.doc.cutting_cost_per_board_usd || 0),
        };
    }

    function installNativeStatusOwner(field) {
        if (!field || !field.df || field.df[STATUS_OWNER_KEY]) return;
        const df = field.df;
        const previousGetStatus = typeof df.get_status === "function"
            ? df.get_status
            : null;

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
        const mayWrite = costSettingsMayWrite(frm);
        COST_SETTING_FIELDS.forEach((fieldname) => {
            const field = frm.fields_dict[fieldname];
            if (!field || !field.df) return;
            installNativeStatusOwner(field);
            field.df[STATUS_KEY] = mayWrite ? "Write" : "Read";
            if (typeof field.refresh === "function") field.refresh();
        });
        return true;
    }

    function refreshCostUx(frm) {
        const cost = window.AlmdinaCostPermissionsUX;
        if (cost && typeof cost.apply === "function") cost.apply(frm);
        applyFieldAccess(frm);
    }

    function startEditing(frm) {
        if (!canEditCostSettings(frm)) {
            frappe.msgprint(__("لا تملك صلاحية تعديل التكلفة في حالة الطلب الحالية."));
            return false;
        }
        if (frm.is_dirty && frm.is_dirty()) {
            frappe.msgprint(__("احفظ أو ألغِ التعديلات الحالية قبل فتح تعديل التكلفة."));
            return false;
        }
        captureBaseline(frm);
        setEditing(frm, true);
        refreshCostUx(frm);
        const first = frm.fields_dict && frm.fields_dict.board_rate_usd;
        if (first && first.$input && first.$input.length) first.$input.trigger("focus");
        return true;
    }

    async function cancelEditing(frm) {
        if (!isEditing(frm)) return false;
        setEditing(frm, false);
        applyFieldAccess(frm);
        await frm.reload_doc();
        return true;
    }

    function settingsChanged(frm) {
        const baseline = frm && frm[BASELINE_KEY];
        if (!baseline) return true;
        return (
            Math.abs(Number(frm.doc.board_rate_usd || 0) - baseline.board_rate_usd) > 0.000001
            || Math.abs(
                Number(frm.doc.cutting_cost_per_board_usd || 0)
                - baseline.cutting_cost_per_board_usd
            ) > 0.000001
        );
    }

    async function saveEditing(frm) {
        if (!isEditing(frm)) return false;
        if (!canEditCostSettings(frm)) {
            setEditing(frm, false);
            applyFieldAccess(frm);
            frappe.msgprint(__("لم تعد حالة الطلب تسمح لك بتعديل التكلفة."));
            return false;
        }

        if (settingsChanged(frm)) {
            await frappe.call({
                method: SAVE_METHOD,
                args: {
                    order_name: frm.doc.name,
                    board_rate_usd: frm.doc.board_rate_usd,
                    cutting_cost_per_board_usd: frm.doc.cutting_cost_per_board_usd,
                },
                freeze: true,
                freeze_message: __("جاري حفظ إعدادات التكلفة..."),
            });
        }

        setEditing(frm, false);
        await frm.reload_doc();
        frappe.show_alert({
            message: __("تم حفظ تعديلات التكلفة وإعادة الصفحة إلى وضع القراءة."),
            indicator: "green",
        }, 5);
        return true;
    }

    function schedule(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        const context = documentContext();
        if (context && typeof context.scheduleFrame === "function") {
            context.scheduleFrame(frm, "cost-settings-edit-session", () => {
                if (isEditing(frm) && !canEditCostSettings(frm)) setEditing(frm, false);
                refreshCostUx(frm);
            });
            return;
        }
        window.requestAnimationFrame(() => {
            if (window.cur_frm !== frm) return;
            if (isEditing(frm) && !canEditCostSettings(frm)) setEditing(frm, false);
            refreshCostUx(frm);
        });
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
        almdina_edit_session_changed(frm) { schedule(frm); },
    });

    window.addEventListener("almdina:permissions-updated", () => {
        const frm = window.cur_frm;
        if (frm && frm.doctype === "Door Cutting Order") schedule(frm);
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
