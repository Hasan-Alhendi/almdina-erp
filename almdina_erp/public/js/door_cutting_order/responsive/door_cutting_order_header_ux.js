(() => {
    "use strict";

    const TAB_LABELS = {
        order_tab: "الطلب",
        results_tab: "خطة القص",
        cost_tab: "تكلفة الطلب",
    };
    const HIDE_EVENT = "hide.almdinaDcoHeaderUx";

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

    function isArabic() {
        const lang = String(
            (frappe.boot && frappe.boot.lang) ||
            (frappe.boot && frappe.boot.user && frappe.boot.user.language) ||
            (document.documentElement && document.documentElement.lang) ||
            ""
        ).toLowerCase();
        return lang === "ar" || lang.startsWith("ar-");
    }


    function domNode(value) {
        if (!value) return null;
        return value.nodeType ? value : (value[0] && value[0].nodeType ? value[0] : null);
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
        const head = frm && frm._dco_presentation_head;
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
            const height = Math.max(44, tabs.getBoundingClientRect().height || tabs.offsetHeight || 44);
            placeholder.style.height = `${height}px`;
            tabs.classList.add("dco-tabs-is-fixed");
            tabs.style.top = `${top}px`;
            tabs.style.left = `${Math.round(anchorRect.left)}px`;
            tabs.style.width = `${Math.round(anchorRect.width)}px`;
        } else {
            placeholder.style.height = "0px";
            tabs.classList.remove("dco-tabs-is-fixed");
            tabs.style.removeProperty("top");
            tabs.style.removeProperty("left");
            tabs.style.removeProperty("width");
        }
    }

    function clearFixedTabListeners(frm, schedule, root, observer, cleanup) {
        document.removeEventListener("scroll", schedule, true);
        window.removeEventListener("resize", schedule);
        if (observer) observer.disconnect();
        const $root = root && window.jQuery && window.jQuery(root);
        if ($root) $root.off(HIDE_EVENT, cleanup);
        if (frm._dco_fixed_tabs_schedule === schedule) {
            frm._dco_fixed_tabs_listener_installed = false;
            frm._dco_fixed_tabs_schedule = null;
            frm._dco_fixed_tabs_listener_root = null;
            frm._dco_fixed_tabs_resize_head = null;
            frm._dco_fixed_tabs_resize_parent = null;
            frm._dco_fixed_tabs_listener_cleanup = null;
        }
    }

    function ensureFixedTabListeners(frm, nodes) {
        const pageRoot = nodes.pageWrapper || nodes.pageContainer;
        const resizeParent = nodes.placeholder.parentElement;
        if (
            frm._dco_fixed_tabs_listener_installed
            && frm._dco_fixed_tabs_listener_root === pageRoot
            && frm._dco_fixed_tabs_resize_head === nodes.head
            && frm._dco_fixed_tabs_resize_parent === resizeParent
            && pageRoot.isConnected
        ) return;
        if (typeof frm._dco_fixed_tabs_listener_cleanup === "function") {
            frm._dco_fixed_tabs_listener_cleanup();
        }
        const schedule = () => {
            scheduleFrame(frm, "header-fixed-tabs-scroll", () => updateFixedTabs(frm));
        };
        const observer = window.ResizeObserver ? new window.ResizeObserver(schedule) : null;
        if (observer) {
            observer.observe(nodes.head);
            if (resizeParent && resizeParent !== nodes.head) observer.observe(resizeParent);
        }
        const cleanup = () => clearFixedTabListeners(frm, schedule, pageRoot, observer, cleanup);
        const $root = pageRoot && window.jQuery && window.jQuery(pageRoot);
        if ($root) $root.on(HIDE_EVENT, cleanup);
        // Frappe may scroll a nested Desk container instead of window. Capture scrolls
        // from every ancestor so the tabs stay fixed regardless of which container scrolls.
        document.addEventListener("scroll", schedule, true);
        window.addEventListener("resize", schedule, { passive: true });
        frm._dco_fixed_tabs_schedule = schedule;
        frm._dco_fixed_tabs_listener_root = pageRoot;
        frm._dco_fixed_tabs_resize_head = nodes.head;
        frm._dco_fixed_tabs_resize_parent = resizeParent;
        frm._dco_fixed_tabs_listener_cleanup = cleanup;
        frm._dco_fixed_tabs_listener_installed = true;
        const context = documentContext();
        if (context && typeof context.registerCleanup === "function") {
            context.registerCleanup(frm, "header-fixed-tabs-listeners", cleanup);
        }
    }

    window.AlmdinaDcoHeaderUx = Object.freeze({
        recoverPresentation(frm, nodes) {
            if (!frm || !nodes || !nodes.tabs || !nodes.placeholder) return false;
            forceRenderedTabLabels(frm, nodes.tabs);
            ensureFixedTabListeners(frm, nodes);
            updateFixedTabs(frm);
            return Boolean(
                frm._dco_fixed_tabs === nodes.tabs
                && frm._dco_tabs_placeholder === nodes.placeholder
                && frm._dco_fixed_tabs.isConnected
            );
        },
        isReady(frm, nodes) {
            return Boolean(
                frm
                && nodes
                && frm._dco_fixed_tabs === nodes.tabs
                && frm._dco_tabs_placeholder === nodes.placeholder
                && nodes.tabs.isConnected
                && nodes.placeholder.isConnected
                && frm._dco_fixed_tabs_listener_root === (nodes.pageWrapper || nodes.pageContainer)
                && frm._dco_fixed_tabs_resize_head === nodes.head
                && frm._dco_fixed_tabs_resize_parent === nodes.placeholder.parentElement
                && frm._dco_fixed_tabs_listener_installed
            );
        },
        suspendPresentation(frm) {
            if (!frm || typeof frm._dco_fixed_tabs_listener_cleanup !== "function") return false;
            frm._dco_fixed_tabs_listener_cleanup();
            return true;
        },
    });
})();
