(() => {
    "use strict";

    if (window.AlmdinaOrderTabPermissionsUX) return;

    const TAB_RULES = Object.freeze({
        results_tab: "view_cutting_plan",
        cost_tab: "view_costs",
    });

    function scheduleFrame(frm, key, callback) {
        const context = window.AlmdinaDocumentContext;
        if (context && typeof context.scheduleFrame === "function") {
            return context.scheduleFrame(frm, key, callback);
        }
        return window.requestAnimationFrame(() => {
            if (window.cur_frm === frm) callback(frm);
        });
    }

    function scheduleDelay(frm, key, callback, delay) {
        const context = window.AlmdinaDocumentContext;
        if (context && typeof context.schedule === "function") {
            return context.schedule(frm, key, callback, delay);
        }
        return window.setTimeout(() => {
            if (window.cur_frm === frm) callback(frm);
        }, delay);
    }

    function can(frm, capability) {
        const permissions = window.AlmdinaPermissions;
        return Boolean(
            permissions
            && (
                typeof permissions.canDocument === "function"
                    ? permissions.canDocument(frm, capability)
                    : permissions.can(capability)
            )
        );
    }

    function formRoot(frm) {
        const wrapper = frm && frm.wrapper;
        return wrapper && (wrapper.nodeType ? wrapper : wrapper[0]);
    }

    function renderedTabNodes(frm, fieldname) {
        const root = formRoot(frm);
        if (!root) return [];
        return [...root.querySelectorAll(`[data-fieldname="${fieldname}"]`)]
            .map(node => node.closest("li,.nav-item") || node)
            .filter((node, index, values) => values.indexOf(node) === index);
    }

    function setRenderedVisibility(frm, fieldname, visible) {
        renderedTabNodes(frm, fieldname).forEach(node => {
            node.hidden = !visible;
            node.style.display = visible ? "" : "none";
            node.setAttribute("aria-hidden", visible ? "false" : "true");
        });
    }

    function currentTabFieldname(frm) {
        // Keep permission reconciliation aligned with the workspace lifecycle.
        // In Frappe v16 layout.current_tab can lag behind the visibly selected
        // tab, while get_active_tab() exposes the canonical host state.
        const activeTab = frm && typeof frm.get_active_tab === "function"
            ? frm.get_active_tab()
            : null;
        const activeFieldname = String(
            activeTab
            && activeTab.df
            && activeTab.df.fieldname
            || ""
        ).trim();
        if (activeFieldname) return activeFieldname;

        return String(
            frm
            && frm.layout
            && frm.layout.current_tab
            && frm.layout.current_tab.df
            && frm.layout.current_tab.df.fieldname
            || ""
        ).trim();
    }

    function activateOrderTab(frm) {
        if (typeof frm.set_active_tab === "function") {
            frm.set_active_tab("order_tab");
            return;
        }
        const root = formRoot(frm);
        const order = root && root.querySelector(
            '[data-fieldname="order_tab"] .nav-link,'
            + '[data-fieldname="order_tab"].nav-link,'
            + '[data-fieldname="order_tab"]'
        );
        if (order && typeof order.click === "function") order.click();
    }

    function visibilityState(frm) {
        return {
            results_tab: can(frm, TAB_RULES.results_tab),
            cost_tab: can(frm, TAB_RULES.cost_tab) || can(frm, "print_customer_invoice"),
        };
    }

    function applyRenderedVisibility(frm, visibility) {
        Object.entries(visibility).forEach(([fieldname, visible]) => {
            setRenderedVisibility(frm, fieldname, visible);
        });
    }

    function apply(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;

        const visibility = visibilityState(frm);

        // IMPORTANT: Do not call frm.set_df_property(..., "hidden", ...) for a
        // Tab Break here. Frappe refreshes the form layout when a Tab Break's
        // hidden state changes, which rebuilds HTML fields and can erase the
        // already-rendered cutting-plan commands and Board Layout. Business
        // authorization is enforced by the server; this module only controls
        // the rendered navigation surface.
        applyRenderedVisibility(frm, visibility);

        const active = currentTabFieldname(frm);
        if (active && visibility[active] === false) {
            activateOrderTab(frm);
        }

        scheduleFrame(frm, "tab-permissions-frame", () => {
            applyRenderedVisibility(frm, visibility);
        });
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) {
            apply(frm);
        },
        refresh(frm) {
            apply(frm);
            // Frappe may repaint the tab navigation after refresh. Reapply only
            // DOM visibility; never rebuild the form layout.
            scheduleDelay(frm, "tab-permissions-180", () => apply(frm), 180);
            scheduleDelay(frm, "tab-permissions-700", () => apply(frm), 700);
        },
    });

    window.addEventListener("almdina:permissions-updated", () => {
        const frm = window.cur_frm;
        if (frm && frm.doctype === "Door Cutting Order") apply(frm);
    });

    window.AlmdinaOrderTabPermissionsUX = Object.freeze({
        apply,
        renderedTabNodes,
        visibilityState,
    });

    window.setTimeout(() => {
        const frm = window.cur_frm;
        if (frm && frm.doctype === "Door Cutting Order") apply(frm);
    }, 0);
})();
