(() => {
    "use strict";

    function rowByName(frm, name) {
        return (frm.doc.pieces || []).find(row => row.name === name) || null;
    }

    function normalizeQty(value) {
        const numeric = Number(String(value ?? "").replace(",", ".")) || 0;
        return Math.max(1, Math.trunc(numeric || 1));
    }

    function triggerQty(frm, row) {
        window.setTimeout(() => {
            Promise.resolve(
                frm.script_manager.trigger("qty", row.doctype, row.name)
            ).catch(error => console.error(error));
        }, 0);
    }

    function focusNextWidth(currentTr) {
        if (!currentTr) return false;
        const next = currentTr.nextElementSibling;
        const width = next && next.querySelector("input[data-field='width_cm']");
        if (!width) return false;
        width.focus({ preventScroll: true });
        if (typeof width.select === "function") width.select();
        next.scrollIntoView({ block: "nearest", inline: "nearest" });
        return document.activeElement === width;
    }

    function syncQtyThroughOperator(frm, input) {
        const tr = input && input.closest("tr[data-row-name]");
        if (!tr) return null;

        input.value = String(normalizeQty(input.value));
        // The operator owns row materialization/model syncing. Reuse that one
        // input contract instead of duplicating its private virtual-row logic.
        input.dispatchEvent(new Event("input", { bubbles: true }));

        const row = rowByName(frm, tr.dataset.rowName || "");
        if (!row) return null;
        row.qty = normalizeQty(input.value);
        input.value = String(row.qty);
        frm.dirty();
        return row;
    }

    function install(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.pieces_fast_entry;
        const root = field && field.$wrapper ? field.$wrapper.get(0) : null;
        if (!root) return false;

        root._dcoFastEntryKeyboardForm = frm;
        if (root._dcoFastEntryKeyboardBound) return true;
        root._dcoFastEntryKeyboardBound = true;

        root.addEventListener("keydown", event => {
            const currentFrm = root._dcoFastEntryKeyboardForm;
            const input = event.target.closest("input[data-field='qty']");
            if (!currentFrm || !input || !root.contains(input) || event.key !== "Enter") return;

            event.preventDefault();
            event.stopPropagation();

            const tr = input.closest("tr[data-row-name]");
            const row = syncQtyThroughOperator(currentFrm, input);
            if (row) triggerQty(currentFrm, row);
            focusNextWidth(tr);
        }, true);
        return true;
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { install(frm); },
        refresh(frm) { install(frm); },
        almdina_edit_session_changed(frm) { install(frm); },
    });

    window.AlmdinaFastEntryKeyboardUX = Object.freeze({
        install,
        normalizeQty,
        focusNextWidth,
    });
})();
