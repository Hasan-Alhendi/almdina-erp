(() => {
    "use strict";

    const STYLE_ID = "dco-responsive-header-css";
    const TAB_LABELS = {
        order_tab: "الطلب",
        results_tab: "خطة القص",
        cost_tab: "تكلفة الطلب",
    };

    function isArabic() {
        const lang = String(
            (frappe.boot && frappe.boot.lang) ||
            (frappe.boot && frappe.boot.user && frappe.boot.user.language) ||
            document.documentElement.lang ||
            ""
        ).toLowerCase();
        return lang === "ar" || lang.startsWith("ar-");
    }

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

            .dco-tabs-fixed-placeholder {
                display: block;
                width: 100%;
                height: 0;
                margin: 0;
                padding: 0;
                border: 0;
            }

            .dco-sticky-tabs {
                background: var(--card-bg, #fff) !important;
                border-bottom: 1px solid var(--border-color, #dfe3e8) !important;
                box-shadow: 0 5px 14px rgba(15, 23, 42, .08) !important;
                margin-bottom: 10px !important;
            }

            .dco-sticky-tabs.dco-tabs-is-fixed {
                position: fixed !important;
                z-index: 1055 !important;
                margin: 0 !important;
                background: var(--card-bg, #fff) !important;
            }

            .dco-sticky-tabs .nav-tabs,
            .dco-sticky-tabs .form-tabs-list {
                background: var(--card-bg, #fff) !important;
                margin-bottom: 0 !important;
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

    function forceRenderedTabLabels(frm, tabs) {
        if (!isArabic() || !tabs) return;

        Object.entries(TAB_LABELS).forEach(([fieldname, label]) => {
            frm.set_df_property(fieldname, "label", label);

            const direct = tabs.querySelector(`[data-fieldname="${fieldname}"]`);
            if (direct) {
                const labelNode = direct.querySelector(".nav-link, .form-tab, .tab-label, span") || direct;
                labelNode.textContent = label;
            }
        });

        // Frappe may render the tab text without a data-fieldname on the visible node.
        // Replace exact legacy labels as a final rendering fallback without touching other UI text.
        tabs.querySelectorAll(".nav-link, .form-tab, a, button").forEach(node => {
            const text = String(node.textContent || "").trim();
            if (text === "Order") node.textContent = "الطلب";
            if (text === "Cutting Plan") node.textContent = "خطة القص";
            if (text === "Order Cost") node.textContent = "تكلفة الطلب";
        });
    }

    function currentFixedTop(frm) {
        const wrapper = domNode(frm && frm.wrapper);
        const pageContainer = wrapper && (wrapper.closest(".page-container") || wrapper.closest(".desk-page"));
        const head = pageContainer ? pageContainer.querySelector(".page-head") : document.querySelector(".page-head");
        if (!head) return 0;

        const style = window.getComputedStyle(head);
        const rect = head.getBoundingClientRect();
        const anchored = style.position === "fixed" || style.position === "sticky";
        if (anchored && rect.bottom > 0 && rect.top <= 1) {
            return Math.max(0, Math.round(rect.bottom));
        }
        return 0;
    }

    function updateFixedTabs(frm) {
        const tabs = frm && frm._dco_fixed_tabs;
        const placeholder = frm && frm._dco_tabs_placeholder;
        if (!tabs || !placeholder || !tabs.isConnected || !placeholder.isConnected) return;

        forceRenderedTabLabels(frm, tabs);

        const top = currentFixedTop(frm);
        const anchorRect = placeholder.getBoundingClientRect();
        const shouldFix = anchorRect.top <= top;

        if (shouldFix) {
            const widthRect = placeholder.parentElement ? placeholder.parentElement.getBoundingClientRect() : anchorRect;
            const height = Math.max(44, tabs.getBoundingClientRect().height || tabs.offsetHeight || 44);
            placeholder.style.height = `${height}px`;
            tabs.classList.add("dco-tabs-is-fixed");
            tabs.style.top = `${top}px`;
            tabs.style.left = `${Math.round(widthRect.left)}px`;
            tabs.style.width = `${Math.round(widthRect.width)}px`;
        } else {
            placeholder.style.height = "0px";
            tabs.classList.remove("dco-tabs-is-fixed");
            tabs.style.removeProperty("top");
            tabs.style.removeProperty("left");
            tabs.style.removeProperty("width");
        }
    }

    function ensureFixedTabListeners(frm) {
        if (frm._dco_fixed_tabs_listener_installed) return;
        frm._dco_fixed_tabs_listener_installed = true;

        let scheduled = false;
        const schedule = () => {
            if (scheduled) return;
            scheduled = true;
            requestAnimationFrame(() => {
                scheduled = false;
                updateFixedTabs(frm);
            });
        };

        // Frappe may scroll a nested Desk container instead of window. Capture scrolls
        // from every ancestor so the tabs stay fixed regardless of which container scrolls.
        document.addEventListener("scroll", schedule, true);
        window.addEventListener("resize", schedule, { passive: true });
        frm._dco_fixed_tabs_schedule = schedule;
    }

    function markStickyTabs(frm) {
        if (!frm) return;
        const wrapper = domNode(frm.wrapper);
        if (!wrapper) return;

        const candidates = [
            ...wrapper.querySelectorAll(".form-tabs"),
            ...wrapper.querySelectorAll(".form-tabs-list"),
        ];
        if (!candidates.length) return;

        const tabs = candidates.find(node => node.classList.contains("form-tabs")) || candidates[0];
        tabs.classList.add("dco-sticky-tabs");
        forceRenderedTabLabels(frm, tabs);

        let placeholder = tabs.previousElementSibling;
        if (!placeholder || !placeholder.classList.contains("dco-tabs-fixed-placeholder")) {
            placeholder = document.createElement("div");
            placeholder.className = "dco-tabs-fixed-placeholder";
            tabs.parentNode.insertBefore(placeholder, tabs);
        }

        frm._dco_fixed_tabs = tabs;
        frm._dco_tabs_placeholder = placeholder;
        ensureFixedTabListeners(frm);
        updateFixedTabs(frm);
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
            setTimeout(() => markStickyTabs(frm), 700);
        },
    });
})();
