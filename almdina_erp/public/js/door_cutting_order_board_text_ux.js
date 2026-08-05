(() => {
    "use strict";

    function controlValue(frm, fieldname) {
        const field = frm.fields_dict && frm.fields_dict[fieldname];
        if (!field) return frm.doc[fieldname];
        if (field.$input && field.$input.length) return field.$input.val();
        if (typeof field.get_value === "function") return field.get_value();
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
            await frm.set_value(updates);
        }

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
