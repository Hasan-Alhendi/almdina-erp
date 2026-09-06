(() => {
    "use strict";

    const DOCTYPE = "Door Cutting Order";
    const UPDATED_EVENT = "almdina:notes-context-updated";

    function panel() {
        return window.AlmdinaNotesPanel || null;
    }

    function isSavedOrder(frm) {
        return Boolean(
            frm
            && frm.doc
            && frm.doc.doctype === DOCTYPE
            && frm.doc.name
            && !(typeof frm.is_new === "function" && frm.is_new())
            && !String(frm.doc.name).startsWith("new-")
        );
    }

    function buttonLabel(frm) {
        const count = Number(frm && frm._almdinaNotesCount || 0);
        const important = String(frm && frm.doc && frm.doc.important_note_preview || "").trim();
        const countText = count > 0 ? ` ${count}` : "";
        const importantText = important ? " ★" : "";
        return `الملاحظات${countText}${importantText}`;
    }

    function buttonNode(button) {
        if (!button) return null;
        if (button.nodeType) return button;
        if (button[0] && button[0].nodeType) return button[0];
        return null;
    }

    function updateButtonPresentation(frm) {
        const button = buttonNode(frm && frm._almdinaNotesButton);
        if (!button || !button.isConnected) return false;
        button.textContent = buttonLabel(frm);
        button.classList.toggle(
            "dco-notes-button-has-important",
            Boolean(String(frm.doc && frm.doc.important_note_preview || "").trim())
        );
        const preview = String(frm.doc && frm.doc.important_note_preview || "").trim();
        button.title = preview ? `الملاحظة المهمة: ${preview}` : "فتح الملاحظات";
        button.setAttribute("aria-label", button.title);
        return true;
    }

    function openNotes(frm) {
        const owner = panel();
        if (!owner || typeof owner.openForOrder !== "function") {
            frappe.msgprint({
                title: "الملاحظات",
                message: "تعذر تحميل واجهة الملاحظات. حدّث الصفحة وحاول مرة أخرى.",
                indicator: "orange",
            });
            return;
        }
        owner.openForOrder(frm.doc.name);
    }

    function ensureNotesButton(frm) {
        if (!isSavedOrder(frm)) return;
        if (updateButtonPresentation(frm)) return;

        const button = frm.add_custom_button(buttonLabel(frm), () => openNotes(frm));
        frm._almdinaNotesButton = button;
        updateButtonPresentation(frm);
    }

    function applyContextUpdate(event) {
        const detail = event && event.detail || {};
        const frm = window.cur_frm;
        if (!isSavedOrder(frm)) return;
        if (String(detail.order_name || "") !== String(frm.doc.name || "")) return;

        const counts = detail.counts || {};
        frm._almdinaNotesCount = Number(counts.order || 0);
        // Projection values are presentation state here. Assign directly instead
        // of frm.set_value so a collaboration action can never dirty/save the DCO.
        frm.doc.important_note_preview = String(detail.important_note_preview || "");
        frm.doc.important_note_comment = String(detail.important_note_comment || "");
        ensureNotesButton(frm);
    }

    document.addEventListener(UPDATED_EVENT, applyContextUpdate);

    frappe.ui.form.on(DOCTYPE, {
        refresh(frm) {
            ensureNotesButton(frm);
        },
    });

    window.AlmdinaDoorCuttingOrderNotesUX = Object.freeze({
        buttonLabel,
        ensureNotesButton,
        openNotes,
    });
})();
