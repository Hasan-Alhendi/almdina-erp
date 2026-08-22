(() => {
    "use strict";

    if (window.AlmdinaOrderEditSaveIntentUX) return;

    const CHECKPOINT_KEY = "__almdina_order_checkpoint_save_in_progress";
    const INSTALL_KEY = "__almdina_order_save_intent_guard_installed";

    function prepareExplicitSave(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return false;
        if (!frm.__almdina_lock_after_save) return false;
        if (frm[CHECKPOINT_KEY]) return false;

        // A plan recalculation checkpoint is allowed to preserve the Order edit
        // session across its internal save. An explicit user Save is different:
        // the same successful native save must finish the edit session. Clear a
        // leftover preserve marker only when this save really belongs to the
        // explicit-save path; a stale lock from an earlier failed save must never
        // reclassify a later checkpoint as an explicit save.
        frm.__almdina_preserve_edit_session_after_save = false;
        return true;
    }

    function installCheckpointIntentGuard() {
        const policy = window.frappe && frappe.almdina;
        if (!policy || typeof policy.persistOrderEditCheckpoint !== "function") return false;
        if (policy[INSTALL_KEY]) return true;

        const original = policy.persistOrderEditCheckpoint;
        policy.persistOrderEditCheckpoint = async function guardedOrderEditCheckpoint(frm, ...args) {
            if (!frm || frm.doctype !== "Door Cutting Order") {
                return original.call(this, frm, ...args);
            }
            frm[CHECKPOINT_KEY] = true;
            try {
                return await original.call(this, frm, ...args);
            } finally {
                frm[CHECKPOINT_KEY] = false;
            }
        };
        policy[INSTALL_KEY] = true;
        return true;
    }

    frappe.ui.form.on("Door Cutting Order", {
        before_save(frm) {
            prepareExplicitSave(frm);
        },
    });

    installCheckpointIntentGuard();

    window.AlmdinaOrderEditSaveIntentUX = Object.freeze({
        CHECKPOINT_KEY,
        prepareExplicitSave,
        installCheckpointIntentGuard,
    });
})();
