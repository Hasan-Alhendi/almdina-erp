(() => {
    "use strict";

    const STYLE_ID = "dco-responsive-header-css-v6";
    const LEGACY_STYLE_IDS = [
        "dco-responsive-header-css",
        "dco-responsive-header-css-v2",
        "dco-responsive-header-css-v3",
        "dco-responsive-header-css-v4",
        "dco-responsive-header-css-v5",
    ];
    const TAB_LABELS = {
        order_tab: "الطلب",
        results_tab: "خطة القص",
        cost_tab: "تكلفة الطلب",
    };

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function scheduleFrame(frm, key, callback) {
        const context = documentContext();
        if (context && typeof context.scheduleFrame === "function") {
            return context.scheduleFrame(frm, key, callback);
        }
        return requestAnimationFrame(() => {
            if (window.cur_frm === frm) callback(frm);
        });
    }

    function scheduleDelay(frm, key, callback, delay) {
        const context = documentContext();
        if (context && typeof context.schedule === "function") {
            return context.schedule(frm, key, callback, delay);
        }
        return setTimeout(() => {
            if (window.cur_frm === frm) callback(frm);
        }, delay);
    }

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
        LEGACY_STYLE_IDS.forEach((id) => {
            const legacy = document.getElementById(id);
            if (legacy) legacy.remove();
        });
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
                border: 1px solid var(--border-color, #dfe3e8) !important;
                border-radius: 14px !important;
                box-shadow: 0 2px 10px rgba(15, 23, 42, .04) !important;
                margin: 0 0 14px !important;
                padding-block: 10px 8px !important;
                padding-inline: 16px 20px !important;
                max-width: 1440px;
                margin-inline: auto;
                width: 100%;
                box-sizing: border-box;
                overflow: hidden;
            }

            .dco-operator-form .dco-sticky-tabs .form-tabs,
            .dco-operator-form .dco-sticky-tabs .form-tabs-list {
                margin-bottom: 0 !important;
            }

            .dco-operator-form .dco-tab-edit-toolbar-slot {
                display: flex !important;
                align-items: center !important;
                padding-inline: 10px 4px !important;
                margin-inline-start: auto !important;
            }

            .dco-operator-form .dco-tab-edit-toolbar {
                padding: 4px 6px !important;
            }

            .dco-sticky-tabs.dco-tabs-is-fixed {
                position: fixed !important;
                z-index: 1055 !important;
                margin: 0 !important;
                background: var(--card-bg, #fff) !important;
                border: 1px solid var(--border-color, #dfe3e8) !important;
                border-radius: 14px !important;
                box-shadow: 0 4px 16px rgba(15, 23, 42, .08) !important;
            }

            .dco-sticky-tabs .nav-tabs,
            .dco-sticky-tabs .form-tabs-list {
                background: var(--card-bg, #fff) !important;
                margin-bottom: 0 !important;
            }

            .dco-sticky-tabs .nav-link,
            .dco-sticky-tabs .form-tab {
                font-weight: 800 !important;
                min-height: 40px !important;
                display: inline-flex !important;
                align-items: center !important;
                justify-content: center !important;
                white-space: nowrap !important;
                width: auto !important;
                max-width: none !important;
                flex: 0 0 auto !important;
                min-width: 0 !important;
                padding-inline: 14px !important;
            }

            .dco-sticky-tabs .form-tabs-list,
            .dco-sticky-tabs .nav-tabs {
                display: flex !important;
                flex-wrap: nowrap !important;
                align-items: center !important;
                gap: 4px !important;
                width: 100% !important;
                max-width: 100% !important;
                overflow-x: auto !important;
                overscroll-behavior-inline: contain;
                scrollbar-width: thin;
            }

            @media (max-width: 1200px) and (min-width: 721px) {
                .page-head.dco-responsive-head .page-actions {
                    max-height: 116px;
                    overflow-y: auto !important;
                    align-content: flex-start !important;
                    padding-bottom: 2px !important;
                }
            }

            @media (min-width: 721px) {
                .page-head.dco-responsive-head .standard-items-section {
                    display: flex !important;
                    flex-wrap: nowrap !important;
                    align-items: center !important;
                    gap: 6px !important;
                    width: auto !important;
                    flex: 0 1 auto !important;
                    min-width: 0 !important;
                }

                .page-head.dco-responsive-head .page-actions,
                .page-head.dco-responsive-head.dco-stable-actions-head .page-actions {
                    display: flex !important;
                    flex-wrap: nowrap !important;
                    align-items: center !important;
                    width: auto !important;
                    max-width: none !important;
                    flex: 0 1 auto !important;
                }

                .page-head.dco-responsive-head .page-actions .custom-actions,
                .page-head.dco-responsive-head .page-actions .custom-mobile-actions,
                .page-head.dco-responsive-head .page-actions .standard-actions,
                .page-head.dco-responsive-head .page-actions .menu-btn-group {
                    display: flex !important;
                    flex-wrap: nowrap !important;
                    align-items: center !important;
                    width: auto !important;
                    flex: 0 0 auto !important;
                }

                .page-head.dco-responsive-head .standard-actions > .search-bar {
                    flex: 0 0 auto !important;
                    width: auto !important;
                    max-width: none !important;
                    margin: 0 !important;
                }

                .page-head.dco-responsive-head .standard-actions .navbar-modal-search-mobile {
                    width: 32px !important;
                    min-width: 32px !important;
                    height: 32px !important;
                    min-height: 32px !important;
                    padding: 0 !important;
                    display: inline-flex !important;
                    align-items: center !important;
                    justify-content: center !important;
                    background: var(--control-bg, var(--alm-secondary-hover-bg, #f4f5f6)) !important;
                    border: 1px solid var(--alm-border, var(--border-color, #dfe3e8)) !important;
                    border-radius: var(--alm-radius-button, 8px) !important;
                    box-shadow: none !important;
                    cursor: pointer !important;
                }

                .page-head.dco-responsive-head .standard-actions .search-bar .search-icon svg {
                    stroke: var(--icon-stroke, var(--text-muted, #6b7280)) !important;
                }
            }

            @media (max-width: 720px) {
                .page-head.dco-responsive-head .page-head-content {
                    gap: 6px !important;
                    padding: 8px 10px !important;
                }

                .page-head.dco-responsive-head .standard-items-section {
                    flex: 1 1 100% !important;
                    width: 100% !important;
                    min-width: 0 !important;
                    max-width: 100% !important;
                    display: grid !important;
                    grid-template-columns: repeat(6, minmax(0, 1fr)) !important;
                    gap: 6px !important;
                    align-items: stretch !important;
                }

                .page-head.dco-responsive-head .page-actions,
                .page-head.dco-responsive-head.dco-stable-actions-head .page-actions {
                    display: contents !important;
                    width: 100% !important;
                    max-width: 100% !important;
                    margin: 0 !important;
                    margin-inline-start: 0 !important;
                    max-height: none !important;
                    overflow: visible !important;
                    flex-wrap: unset !important;
                }

                .page-head.dco-responsive-head .page-actions .custom-actions,
                .page-head.dco-responsive-head .page-actions .custom-mobile-actions,
                .page-head.dco-responsive-head .page-actions .standard-actions,
                .page-head.dco-responsive-head .page-actions .menu-btn-group,
                .page-head.dco-responsive-head.dco-stable-actions-head .page-actions .custom-actions,
                .page-head.dco-responsive-head.dco-stable-actions-head .page-actions .custom-mobile-actions,
                .page-head.dco-responsive-head.dco-stable-actions-head .page-actions .standard-actions {
                    display: contents !important;
                    flex-wrap: unset !important;
                }

                .page-head.dco-responsive-head .standard-items-section [data-dco-mobile-slot="primary-left"] {
                    grid-column: 1 / 4 !important;
                    grid-row: 1 !important;
                    order: 1 !important;
                }

                .page-head.dco-responsive-head .standard-items-section [data-dco-mobile-slot="primary-right"] {
                    grid-column: 4 / 7 !important;
                    grid-row: 1 !important;
                    order: 2 !important;
                }

                .page-head.dco-responsive-head .standard-items-section [data-dco-mobile-slot="utility-search"] {
                    grid-column: 1 / 3 !important;
                    grid-row: 2 !important;
                    order: 10 !important;
                }

                .page-head.dco-responsive-head .standard-items-section [data-dco-mobile-slot="utility-notes"] {
                    grid-column: 3 / 5 !important;
                    grid-row: 2 !important;
                    order: 11 !important;
                }

                .page-head.dco-responsive-head .standard-items-section [data-dco-mobile-slot="utility-menu"] {
                    grid-column: 5 / 7 !important;
                    grid-row: 2 !important;
                    order: 12 !important;
                }

                .page-head.dco-responsive-head .standard-items-section [data-dco-mobile-slot="secondary"] {
                    grid-column: var(--dco-mobile-grid-col, 1 / 4) !important;
                    grid-row: var(--dco-mobile-grid-row, 3) !important;
                    order: 100 !important;
                }

                .page-head.dco-responsive-head .search-bar {
                    width: 100% !important;
                    min-width: 0 !important;
                    margin: 0 !important;
                    padding: 0 !important;
                }

                .page-head.dco-responsive-head .search-bar[data-dco-mobile-slot="utility-search"] {
                    display: flex !important;
                    align-items: stretch !important;
                    min-height: 38px !important;
                    box-sizing: border-box !important;
                    overflow: hidden !important;
                    background: var(--control-bg, var(--alm-secondary-hover-bg, #f4f5f6)) !important;
                    border: 1px solid var(--alm-border, var(--border-color, #dfe3e8)) !important;
                    border-radius: var(--alm-radius-button, 8px) !important;
                    color: var(--alm-secondary-text, var(--text-color, #1f272e)) !important;
                    box-shadow: none !important;
                }

                .page-head.dco-responsive-head .search-bar[data-dco-mobile-slot="utility-search"] .navbar-modal-search-mobile {
                    width: 100% !important;
                    flex: 1 1 auto !important;
                    min-height: 0 !important;
                    display: flex !important;
                    align-items: center !important;
                    justify-content: center !important;
                    background: transparent !important;
                    border: 0 !important;
                    border-radius: 0 !important;
                    box-sizing: border-box !important;
                    cursor: pointer !important;
                    box-shadow: none !important;
                }

                .page-head.dco-responsive-head .search-bar[data-dco-mobile-slot="utility-search"] .search-icon,
                .page-head.dco-responsive-head .search-bar[data-dco-mobile-slot="utility-search"] .search-icon svg {
                    display: inline-flex !important;
                    align-items: center !important;
                    justify-content: center !important;
                    stroke: var(--icon-stroke, var(--text-muted, #6b7280)) !important;
                }

                .page-head.dco-responsive-head .standard-items-section > :where(.btn, .btn-group, .dropdown),
                .page-head.dco-responsive-head .page-actions .custom-actions > :where(.btn, .btn-group, .dropdown),
                .page-head.dco-responsive-head .page-actions .custom-mobile-actions > :where(.btn, .btn-group, .dropdown),
                .page-head.dco-responsive-head .page-actions .standard-actions > :where(.btn, .btn-group, .dropdown) {
                    width: 100% !important;
                    min-width: 0 !important;
                    max-width: 100% !important;
                    margin: 0 !important;
                }

                .page-head.dco-responsive-head .standard-items-section :where(.btn, button) {
                    width: 100% !important;
                    min-height: 38px !important;
                    padding: 6px 8px !important;
                    font-size: 12.5px !important;
                    line-height: 1.2 !important;
                    justify-content: center !important;
                }

                .page-head.dco-responsive-head .standard-items-section [data-dco-mobile-slot="utility-search"] :where(.btn, button),
                .page-head.dco-responsive-head .standard-items-section [data-dco-mobile-slot="utility-menu"] :where(.btn, button) {
                    padding-inline: 6px !important;
                }

                .page-head.dco-responsive-head .page-actions .menu-btn-group > .btn {
                    min-width: 0 !important;
                }

                .dco-sticky-tabs {
                    margin: 0 0 10px !important;
                    padding-block: 6px !important;
                    padding-inline: 10px !important;
                }

                .dco-operator-form .dco-tab-edit-toolbar-slot {
                    padding-inline: 6px 2px !important;
                }

                .dco-operator-form .dco-tab-edit-toolbar {
                    padding: 2px 4px !important;
                }

                .dco-sticky-tabs .nav-link,
                .dco-sticky-tabs .form-tab {
                    min-height: 34px !important;
                    min-width: 0 !important;
                    width: auto !important;
                    flex: 0 0 auto !important;
                    padding-inline: 10px !important;
                    font-size: 12.5px !important;
                    font-weight: 750 !important;
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

        const wrapper = domNode(frm && frm.wrapper);
        if (!wrapper) return;
        const pageContainer = wrapper.closest(".page-container") || wrapper.closest(".desk-page") || wrapper.parentElement;
        if (!pageContainer) return;
        pageContainer.querySelectorAll(".page-head.dco-responsive-head").forEach(node => {
            node.classList.remove("dco-responsive-head");
        });

        const head = pageContainer.querySelector(".page-head");
        if (head) head.classList.add("dco-responsive-head");
    }

    function forceRenderedTabLabels(frm, tabs) {
        if (!isArabic() || !tabs) return;

        Object.entries(TAB_LABELS).forEach(([fieldname, label]) => {
            const field = frm.fields_dict && frm.fields_dict[fieldname];
            if (field && field.df && field.df.label !== label) {
                frm.set_df_property(fieldname, "label", label);
            }

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
        const head = pageContainer ? pageContainer.querySelector(".page-head") : null;
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

        const schedule = () => {
            scheduleFrame(frm, "header-fixed-tabs-scroll", () => updateFixedTabs(frm));
        };

        // Frappe may scroll a nested Desk container instead of window. Capture scrolls
        // from every ancestor so the tabs stay fixed regardless of which container scrolls.
        document.addEventListener("scroll", schedule, true);
        window.addEventListener("resize", schedule, { passive: true });
        frm._dco_fixed_tabs_schedule = schedule;
        const context = documentContext();
        if (context && typeof context.registerCleanup === "function") {
            context.registerCleanup(frm, "header-fixed-tabs-listeners", () => {
                document.removeEventListener("scroll", schedule, true);
                window.removeEventListener("resize", schedule);
                frm._dco_fixed_tabs_listener_installed = false;
                frm._dco_fixed_tabs_schedule = null;
            });
        }
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
        scheduleFrame(frm, "header-refresh-frame", () => {
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
            scheduleDelay(frm, "header-sticky-tabs-180", () => markStickyTabs(frm), 180);
            scheduleDelay(frm, "header-sticky-tabs-700", () => markStickyTabs(frm), 700);
        },
    });
})();
