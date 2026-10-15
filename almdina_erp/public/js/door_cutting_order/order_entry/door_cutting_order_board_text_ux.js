(() => {
    "use strict";

    const INPUT_FIELDS = ["board_description", "board_length_cm", "board_width_cm"];

    function context() {
        return window.AlmdinaDocumentContext || null;
    }

    function owns(frm, token) {
        const owner = context();
        return owner && owner.isSameDocument(frm, token)
            && (!window.cur_frm || window.cur_frm === frm);
    }

    function bindInput(frm, fieldname) {
        const field = frm.fields_dict && frm.fields_dict[fieldname];
        const input = field && field.$input;
        if (!input || !input.length || typeof input.on !== "function") return;
        const element = typeof input.get === "function" ? input.get(0) : input[0];
        if (field.__almdinaOwnedInputElement === element) return;
        field.__almdinaOwnedInputElement = element;
        field.__almdinaOwnedInputEdit = null;
        input.on("input.almdinaBoardOwnership change.almdinaBoardOwnership", () => {
            const owner = context();
            const token = owner?.capture(frm);
            if (!token || !owns(frm, token)) return;
            field.__almdinaOwnedInputEdit = { token, element, value: input.val() };
        });
    }

    function bindInputs(frm) {
        INPUT_FIELDS.forEach(fieldname => bindInput(frm, fieldname));
    }

    function controlValue(frm, fieldname) {
        const field = frm.fields_dict && frm.fields_dict[fieldname];
        if (!field) return frm.doc[fieldname];
        const input = field.$input;
        const edit = field.__almdinaOwnedInputEdit;
        const element = input && (typeof input.get === "function" ? input.get(0) : input[0]);
        if (input?.length && edit && edit.element === element && owns(frm, edit.token)
            && edit.value === field.$input.val()) return edit.value;
        // The Frappe model owns values not entered during this document visit.
        // get_value() and $input.val() can both expose an old control's value.
        return frm.doc[fieldname];
    }

    function boardDescriptionValue(frm) {
        return String(controlValue(frm, "board_description") || "").trim();
    }

    function boardLabel(frm) {
        return boardDescriptionValue(frm) || "—";
    }

    function isBoardReady(frm) {
        return !!boardDescriptionValue(frm);
    }

    function hasMeasurablePieces(frm) {
        return (frm.doc.pieces || []).some(row => (
            Number(row.width_cm || 0) > 0
            && Number(row.length_cm || 0) > 0
            && Number(row.qty || 0) > 0
        ));
    }

    function canCalculatePlan(frm) {
        return isBoardReady(frm)
            && Number(controlValue(frm, "board_length_cm") || 0) > 0
            && Number(controlValue(frm, "board_width_cm") || 0) > 0
            && hasMeasurablePieces(frm);
    }

    async function syncInputs(frm) {
        const owner = context();
        const token = owner?.capture(frm);
        if (!token || !owns(frm, token)) return false;
        bindInputs(frm);
        const description = boardDescriptionValue(frm);
        const length = Number(controlValue(frm, "board_length_cm") || 0);
        const width = Number(controlValue(frm, "board_width_cm") || 0);
        const updates = {};

        if (description !== String(frm.doc.board_description || "").trim()) {
            updates.board_description = description;
        }
        if (Number.isFinite(length) && length !== Number(frm.doc.board_length_cm || 0)) {
            updates.board_length_cm = length;
        }
        if (Number.isFinite(width) && width !== Number(frm.doc.board_width_cm || 0)) {
            updates.board_width_cm = width;
        }

        if (Object.keys(updates).length) {
            if (!owns(frm, token)) return false;
            // Frappe v16 frm.set_value({...}) runs one field at a time and
            // reads me.doc.name again for each task. A route change during an
            // awaited field trigger could otherwise apply later A values to B.
            // model.set_value(doc, updates) selects the captured document once
            // and applies the whole batch before its asynchronous triggers.
            const targetDoc = frm.doc;
            await (typeof frappe.model?.set_value === "function"
                ? frappe.model.set_value(targetDoc, updates)
                : frm.set_value(updates));
        }

        if (!owns(frm, token)) return false;

        frm.doc.full_board_length_mm = Number(frm.doc.board_length_cm || 0) * 10;
        frm.doc.full_board_width_mm = Number(frm.doc.board_width_cm || 0) * 10;
        return {
            board_description: String(frm.doc.board_description || "").trim(),
            board_length_cm: Number(frm.doc.board_length_cm || 0),
            board_width_cm: Number(frm.doc.board_width_cm || 0),
        };
    }

    function patchCostView(frm) {
        const field = frm.fields_dict && frm.fields_dict.order_cost_invoice_html;
        const root = field && field.$wrapper ? field.$wrapper.get(0) : null;
        if (!root) return;
        const label = boardLabel(frm);

        root.querySelectorAll(".dco-invoice-meta-item").forEach(item => {
            const name = item.querySelector(".label");
            if (!name || name.textContent.trim() !== "اللوح") return;
            const value = item.querySelector(".value");
            if (value) value.textContent = label;
        });

        root.querySelectorAll(".dco-cost-table tbody td.text-start b").forEach(node => {
            if (!String(node.textContent || "").trim().startsWith("ألواح MDF")) return;
            node.textContent = `ألواح MDF — ${label}`;
        });
    }

    function installCostObserver(frm) {
        const field = frm.fields_dict && frm.fields_dict.order_cost_invoice_html;
        const root = field && field.$wrapper ? field.$wrapper.get(0) : null;
        if (!root || root._dcoBoardTextObserver) return;
        let scheduled = false;
        const observer = new MutationObserver(() => {
            if (scheduled) return;
            scheduled = true;
            requestAnimationFrame(() => {
                scheduled = false;
                patchCostView(frm);
            });
        });
        observer.observe(root, { childList: true, subtree: true });
        root._dcoBoardTextObserver = observer;
    }

    function refresh(frm) {
        bindInputs(frm);
        patchCostView(frm);
        installCostObserver(frm);
        requestAnimationFrame(() => patchCostView(frm));
        window.setTimeout(() => patchCostView(frm), 250);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { refresh(frm); },
        refresh(frm) { refresh(frm); },
        before_save(frm) { return syncInputs(frm); },
        board_description(frm) { refresh(frm); },
        board_length_cm(frm) { refresh(frm); },
        board_width_cm(frm) { refresh(frm); },
    });

    window.AlmdinaBoardTextUX = {
        refresh,
        label: boardLabel,
        isBoardReady,
        hasMeasurablePieces,
        canCalculatePlan,
        syncInputs,
    };
})();
