(() => {
    "use strict";

    const STYLE_ID = "dco-compact-measurements-css";

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-fast-table th.dco-col-calc,
            .dco-fast-table td.dco-col-calc {
                display: none !important;
            }

            .dco-fast-table {
                min-width: 1180px !important;
            }

            .dco-fast-table .dco-col-edge-type {
                width: 175px !important;
            }

            .dco-fast-table .dco-col-notes {
                width: 250px !important;
            }
        `;
        document.head.appendChild(style);
    }

    function compactTable(frm) {
        installStyles();
        const field = frm && frm.fields_dict && frm.fields_dict.pieces_fast_entry;
        if (!field || !field.$wrapper) return;
        const root = field.$wrapper.get(0);
        if (!root) return;

        root.querySelectorAll("th.dco-col-calc, td.dco-col-calc").forEach(cell => {
            cell.setAttribute("aria-hidden", "true");
            cell.tabIndex = -1;
        });
    }

    function schedule(frm) {
        compactTable(frm);
        requestAnimationFrame(() => compactTable(frm));
        setTimeout(() => compactTable(frm), 180);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) {
            schedule(frm);
        },
        refresh(frm) {
            schedule(frm);
        },
        pieces_add(frm) {
            schedule(frm);
        },
        pieces_remove(frm) {
            schedule(frm);
        },
    });
})();
