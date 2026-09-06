(() => {
    "use strict";

    const DOCTYPE = "Door Cutting Order";
    const UPDATED_EVENT = "almdina:notes-context-updated";
    const CONTEXT_METHOD = "almdina_erp.almdina_erp.services.notes_service.get_order_notes_context";

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

    function orderIdentity(frm) {
        return isSavedOrder(frm) ? String(frm.doc.name || "").trim() : "";
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

    function resetIdentityState(frm, identity) {
        if (!frm) return;
        frm._almdinaNotesOrderIdentity = String(identity || "");
        frm._almdinaNotesCount = 0;
        frm._almdinaNotesSummaryGeneration = Number(frm._almdinaNotesSummaryGeneration || 0) + 1;
        frm._almdinaNotesSummaryPromise = null;
    }

    function isCurrentSummaryRequest(frm, identity, generation) {
        return Boolean(
            isSavedOrder(frm)
            && orderIdentity(frm) === String(identity || "")
            && String(frm._almdinaNotesOrderIdentity || "") === String(identity || "")
            && Number(frm._almdinaNotesSummaryGeneration || 0) === Number(generation || 0)
        );
    }

    function applyContextSnapshot(frm, context, identity, generation) {
        if (!context || !isCurrentSummaryRequest(frm, identity, generation)) return false;
        if (String(context.order || "") !== String(identity || "")) return false;

        const counts = context.counts || {};
        frm._almdinaNotesCount = Number(counts.order || 0);
        // Collaboration projections are presentation state only. Keep them out of
        // the official DCO form/save lifecycle exactly like drawer mutations do.
        frm.doc.important_note_preview = String(context.important_note_preview || "");
        frm.doc.important_note_comment = String(context.important_note_comment || "");
        ensureNotesButton(frm);
        return true;
    }

    function refreshNotesSummary(frm) {
        if (!isSavedOrder(frm) || !window.frappe || typeof frappe.call !== "function") {
            return Promise.resolve(null);
        }

        const identity = orderIdentity(frm);
        if (String(frm._almdinaNotesOrderIdentity || "") !== identity) {
            // Never paint the previous order's count while the new order summary
            // is loading. The button becomes neutral until this identity confirms.
            resetIdentityState(frm, identity);
            ensureNotesButton(frm);
        }

        const generation = Number(frm._almdinaNotesSummaryGeneration || 0) + 1;
        frm._almdinaNotesSummaryGeneration = generation;

        const request = frappe.call({
            method: CONTEXT_METHOD,
            args: { order_name: identity },
            freeze: false,
        }).then(response => {
            const context = response && response.message;
            applyContextSnapshot(frm, context, identity, generation);
            return context || null;
        }).catch(error => {
            // Fail quiet on a toolbar enhancement. Most importantly, never restore
            // stale data from another order or disturb the DCO page lifecycle.
            if (isCurrentSummaryRequest(frm, identity, generation)) {
                frm._almdinaNotesCount = 0;
                ensureNotesButton(frm);
            }
            return null;
        }).finally(() => {
            if (isCurrentSummaryRequest(frm, identity, generation)) {
                frm._almdinaNotesSummaryPromise = null;
            }
        });

        frm._almdinaNotesSummaryPromise = request;
        return request;
    }

    function applyContextUpdate(event) {
        const detail = event && event.detail || {};
        const frm = window.cur_frm;
        if (!isSavedOrder(frm)) return;
        if (String(detail.order_name || "") !== String(frm.doc.name || "")) return;

        // A drawer-confirmed context is newer than any toolbar read that may still
        // be in flight. Invalidate that read before applying the mutation result.
        frm._almdinaNotesOrderIdentity = orderIdentity(frm);
        frm._almdinaNotesSummaryGeneration = Number(frm._almdinaNotesSummaryGeneration || 0) + 1;
        frm._almdinaNotesSummaryPromise = null;

        const counts = detail.counts || {};
        frm._almdinaNotesCount = Number(counts.order || 0);
        frm.doc.important_note_preview = String(detail.important_note_preview || "");
        frm.doc.important_note_comment = String(detail.important_note_comment || "");
        ensureNotesButton(frm);
    }

    document.addEventListener(UPDATED_EVENT, applyContextUpdate);

    frappe.ui.form.on(DOCTYPE, {
        refresh(frm) {
            if (!isSavedOrder(frm)) {
                resetIdentityState(frm, "");
                return;
            }
            ensureNotesButton(frm);
            refreshNotesSummary(frm);
        },
    });

    window.AlmdinaDoorCuttingOrderNotesUX = Object.freeze({
        buttonLabel,
        ensureNotesButton,
        openNotes,
        refreshNotesSummary,
    });
})();
