(() => {
    "use strict";

    const STYLE_ID = "dco-responsive-header-css";

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
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

            .dco-sticky-tabs {
                position: sticky !important;
                top: 0 !important;
                z-index: 1050 !important;
                background: var(--card-bg, #fff) !important;
                border-bottom: 1px solid var(--border-color, #dfe3e8) !important;
                box-shadow: 0 5px 14px rgba(15, 23, 42, .08) !important;
                margin-bottom: 10px !important;
            }

            .dco-sticky-tabs .nav-tabs,
            .dco-sticky-tabs .form-tabs-list {
                background: var(--card-bg, #fff) !important;
            }

            .dco-sticky-tabs .nav-link,
            .dco-sticky-tabs .form-tab {
                font-weight: 800 !important;
                min-height: 44px !important;
                display: inline-flex !important;
                align-items: center !important;
                justify-content: center !important;
                white-space: nowrap !important;
            }

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

    function domNode(value) {
        if (!value) return null;
        return value.nodeType ? value : (value[0] && value[0].nodeType ? value[0] : null);
    }

    function markCurrentHeader(frm) {
        installStyles();

        document.querySelectorAll(".page-head.dco-responsive-head").forEach(node => {
            node.classList.remove("dco-responsive-head");
        });

        const wrapper = domNode(frm && frm.wrapper);
        if (!wrapper) return;

        const pageContainer = wrapper.closest(".page-container") || wrapper.closest(".desk-page") || wrapper.parentElement;
        let head = pageContainer ? pageContainer.querySelector(".page-head") : null;
        if (!head) head = document.querySelector(".page-head");
        if (head) head.classList.add("dco-responsive-head");
    }

    function markStickyTabs(frm) {
        if (!frm) return;
        frm.set_df_property("order_tab", "label", "الطلب");
        frm.set_df_property("results_tab", "label", "خطة القص");
        frm.set_df_property("cost_tab", "label", "تكلفة الطلب");

        const wrapper = domNode(frm.wrapper);
        if (!wrapper) return;
        wrapper.querySelectorAll(".dco-sticky-tabs").forEach(node => node.classList.remove("dco-sticky-tabs"));

        const candidates = [
            ...wrapper.querySelectorAll(".form-tabs"),
            ...wrapper.querySelectorAll(".form-tabs-list"),
        ];
        if (!candidates.length) return;

        const tabs = candidates.find(node => node.classList.contains("form-tabs")) || candidates[0];
        tabs.classList.add("dco-sticky-tabs");
    }

    function refreshHeaderUX(frm) {
        markCurrentHeader(frm);
        markStickyTabs(frm);
        requestAnimationFrame(() => {
            markCurrentHeader(frm);
            markStickyTabs(frm);
        });
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) {
            refreshHeaderUX(frm);
        },
        refresh(frm) {
            refreshHeaderUX(frm);
            setTimeout(() => markStickyTabs(frm), 180);
        },
    });
})();
