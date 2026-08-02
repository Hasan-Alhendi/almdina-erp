(() => {
    "use strict";

    if (window.AlmdinaOrderTabPermissionsUX) return;

    const TAB_RULES = Object.freeze({
        results_tab: "view_cutting_plan",
        cost_tab: "view_costs",
    });

    function can(capability) {
        return Boolean(
            window.AlmdinaPermissions
            && window.AlmdinaPermissions.can(capability)
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
        return String(
            frm
            && frm.layout
            && frm.layout.current_tab
            && frm.layout.current_tab.df
            && frm.layout.current_tab.df.fieldname
            || ""
        );
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

    function apply(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;

        const saved = !frm.is_new();
        const visibility = {
            results_tab: saved && can(TAB_RULES.results_tab),
            cost_tab: saved && can(TAB_RULES.cost_tab),
        };

        Object.entries(visibility).forEach(([fieldname, visible]) => {
            frm.set_df_property(fieldname, "hidden", visible ? 0 : 1);
            setRenderedVisibility(frm, fieldname, visible);
        });

        const active = currentTabFieldname(frm);
        if (active && visibility[active] === false) {
            activateOrderTab(frm);
        }

        window.requestAnimationFrame(() => {
            Object.entries(visibility).forEach(([fieldname, visible]) => {
                setRenderedVisibility(frm, fieldname, visible);
            });
        });
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) {
            apply(frm);
        },
        refresh(frm) {
            apply(frm);
            window.setTimeout(() => apply(frm), 180);
            window.setTimeout(() => apply(frm), 700);
        },
    });

    window.addEventListener("almdina:permissions-updated", () => {
        const frm = window.cur_frm;
        if (frm && frm.doctype === "Door Cutting Order") apply(frm);
    });

    window.AlmdinaOrderTabPermissionsUX = Object.freeze({
        apply,
        renderedTabNodes,
    });
})();
