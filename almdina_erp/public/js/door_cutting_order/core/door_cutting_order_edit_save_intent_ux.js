(() => {
    "use strict";

    if (window.AlmdinaOrderEditSaveIntentUX) return;

    function prepareExplicitSave(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return false;
        if (!frm.__almdina_lock_after_save) return false;

        // A plan recalculation checkpoint is allowed to preserve the Order edit
        // session across its internal save. An explicit user Save is different:
        // the same successful native save must finish the edit session. Clear a
        // leftover/in-flight checkpoint marker before Frappe evaluates after_save
        // so preserve intent can never override the explicit lock intent.
        frm.__almdina_preserve_edit_session_after_save = false;
        return true;
    }

    frappe.ui.form.on("Door Cutting Order", {
        before_save(frm) {
            prepareExplicitSave(frm);
        },
    });

    window.AlmdinaOrderEditSaveIntentUX = Object.freeze({
        prepareExplicitSave,
    });
})();
