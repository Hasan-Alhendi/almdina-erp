(() => {
    "use strict";

    const STYLE_ID = "dco-responsive-header-css";

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            /* Door Cutting Order has many daily actions. Give the title its own row
               and let actions wrap naturally instead of forcing the operator to zoom. */
            .page-head.dco-responsive-head {
                height: auto !important;
                min-height: 54px !important;
                overflow: visible !important;
            }

            .page-head.dco-responsive-head .page-head-content {
                height: auto !important;
                min-height: 54px !important;
                padding-top: 8px !important;
                padding-bottom: 8px !important;
                display: flex !important;
                flex-wrap: wrap !important;
                align-items: center !important;
                column-gap: 10px !important;
                row-gap: 8px !important;
            }

            .page-head.dco-responsive-head .page-title,
            .page-head.dco-responsive-head .title-area {
                flex: 1 1 100% !important;
                width: 100% !important;
                min-width: 0 !important;
                max-width: 100% !important;
            }

            .page-head.dco-responsive-head .page-actions {
                flex: 1 1 100% !important;
                width: 100% !important;
                min-width: 0 !important;
                margin: 0 !important;
                display: flex !important;
                align-items: center !important;
                justify-content: flex-start !important;
                flex-wrap: wrap !important;
                gap: 6px !important;
                overflow: visible !important;
            }

            .page-head.dco-responsive-head .page-actions .custom-actions,
            .page-head.dco-responsive-head .page-actions .standard-actions,
            .page-head.dco-responsive-head .page-actions .menu-btn-group {
                display: flex !important;
                align-items: center !important;
                flex-wrap: wrap !important;
                gap: 6px !important;
                margin: 0 !important;
            }

            .page-head.dco-responsive-head .page-actions .btn,
            .page-head.dco-responsive-head .page-actions .dropdown,
            .page-head.dco-responsive-head .page-actions .btn-group {
                flex: 0 0 auto !important;
                margin: 0 !important;
            }

            .page-head.dco-responsive-head .page-actions .btn {
                white-space: nowrap !important;
                max-width: none !important;
            }

            /* On narrower workstations keep every action reachable without shrinking text. */
            @media (max-width: 1200px) {
                .page-head.dco-responsive-head .page-actions {
                    max-height: 116px;
                    overflow-y: auto !important;
                    align-content: flex-start !important;
                    padding-bottom: 2px !important;
                }
            }
        `;
        document.head.appendChild(style);
    }

    function markCurrentHeader(frm) {
        installStyles();

        // Remove the marker from any previously opened form, then mark only the
        // page-head that belongs to the current Door Cutting Order form.
        document.querySelectorAll(".page-head.dco-responsive-head").forEach(node => {
            node.classList.remove("dco-responsive-head");
        });

        const wrapper = frm && frm.wrapper;
        if (!wrapper) return;

        const pageContainer = wrapper.closest(".page-container") || wrapper.closest(".desk-page") || wrapper.parentElement;
        let head = pageContainer ? pageContainer.querySelector(".page-head") : null;
        if (!head) head = document.querySelector(".page-head");
        if (head) head.classList.add("dco-responsive-head");
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) {
            markCurrentHeader(frm);
        },
        refresh(frm) {
            markCurrentHeader(frm);
            requestAnimationFrame(() => markCurrentHeader(frm));
        },
    });
})();
