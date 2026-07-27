(() => {
    "use strict";

    const PRINT_TRIGGER_SELECTOR = [
        ".dco-print-customer-invoice",
        ".dco-print-measurements",
        ".dco-open-measurements-window",
        ".dco-entry-window-print",
    ].join(",");

    function boardLabel(frm) {
        return String(frm.doc.board_description || "").trim() || "—";
    }

    function patchCostView(frm) {
        const field = frm.fields_dict && frm.fields_dict.order_cost_invoice_html;
        const root = field && field.$wrapper ? field.$wrapper.get(0) : null;
        if (!root) return;
        const label = boardLabel(frm);

        root.querySelectorAll(".dco-invoice-meta-item").forEach(item => {
            const name = item.querySelector(".label");
            if (!name || name.textContent.trim() !== "صنف اللوح") return;
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

    function withBoardDescriptionForPrint(frm, callback) {
        const description = boardLabel(frm);
        const previous = frm.doc.board_item;
        frm.doc.board_item = description === "—" ? "" : description;
        try {
            callback();
        } finally {
            window.setTimeout(() => {
                frm.doc.board_item = previous;
            }, 0);
        }
    }

    function installPrintBridge(frm) {
        if (frm._dcoBoardTextPrintBridge) return;
        frm._dcoBoardTextPrintBridge = true;
        document.addEventListener("click", event => {
            const trigger = event.target.closest(PRINT_TRIGGER_SELECTOR);
            if (!trigger) return;
            const wrapper = frm.wrapper && (frm.wrapper.nodeType ? frm.wrapper : frm.wrapper[0]);
            const editor = frm._dcoMeasurementEntryWindow && frm._dcoMeasurementEntryWindow.overlay;
            if (wrapper && !wrapper.contains(trigger) && !(editor && editor.contains(trigger))) return;

            const description = boardLabel(frm);
            if (!description || description === "—") return;
            const previous = frm.doc.board_item;
            frm.doc.board_item = description;
            window.setTimeout(() => {
                frm.doc.board_item = previous;
            }, 0);
        }, true);
    }

    function refresh(frm) {
        patchCostView(frm);
        installCostObserver(frm);
        installPrintBridge(frm);
        requestAnimationFrame(() => patchCostView(frm));
        window.setTimeout(() => patchCostView(frm), 250);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { refresh(frm); },
        refresh(frm) { refresh(frm); },
        board_description(frm) { refresh(frm); },
        board_length_cm(frm) { refresh(frm); },
        board_width_cm(frm) { refresh(frm); },
    });

    window.AlmdinaBoardTextUX = {
        refresh,
        label: boardLabel,
        withBoardDescriptionForPrint,
    };
})();
