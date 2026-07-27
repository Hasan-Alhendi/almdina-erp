(() => {
    "use strict";

    const PATCH_DELAYS = [0, 60, 220, 500];

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function getCostRoot(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.order_cost_invoice_html;
        return field && field.$wrapper ? field.$wrapper.get(0) : null;
    }

    function orderEdgeColor(frm) {
        return String(frm.doc.edge_color || "").trim() || "غير محدد";
    }

    function removeLegacyColorDuplicates(root) {
        if (!root) return;
        root.querySelectorAll(
            ".dco-edge-color-col,.dco-edge-color-inline,.dco-edge-color-meta"
        ).forEach(node => node.remove());
    }

    function updateColorKpi(frm, root) {
        if (!root) return;
        const color = orderEdgeColor(frm);
        [...root.querySelectorAll(".dco-cost-kpi")].forEach(card => {
            const label = card.querySelector(".label");
            if (!label || label.textContent.trim() !== "لون القشاط") return;
            const value = card.querySelector(".value");
            if (value) value.textContent = color;
        });
    }

    function patchFastEntryContext(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.pieces_fast_entry;
        const root = field && field.$wrapper ? field.$wrapper.get(0) : null;
        const toolbar = root && root.querySelector(".dco-fast-entry-toolbar");
        if (!toolbar) return;
        const color = orderEdgeColor(frm);
        let badge = toolbar.querySelector(".dco-order-edge-color-badge");
        if (!badge) {
            badge = document.createElement("span");
            badge.className = "dco-order-edge-color-badge";
            badge.style.cssText = "display:inline-flex;align-items:center;gap:5px;margin-inline-start:auto;padding:5px 9px;border:1px solid rgba(36,144,239,.22);border-radius:999px;background:rgba(36,144,239,.06);font-size:10px;font-weight:800;white-space:nowrap";
            toolbar.appendChild(badge);
        }
        badge.innerHTML = `<span style="width:7px;height:7px;border-radius:50%;background:var(--primary,#2490ef)"></span><span>لون القشاط: ${esc(color)}</span>`;
        badge.title = "لون القشاط العام للطلب";
    }

    function patchCostView(frm) {
        const root = getCostRoot(frm);
        removeLegacyColorDuplicates(root);
        updateColorKpi(frm, root);
        patchFastEntryContext(frm);
    }

    function observeCostView(frm, root) {
        if (!root || root._dcoEdgeColorObserver) return;
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
        root._dcoEdgeColorObserver = observer;
    }

    function enhance(frm) {
        const root = getCostRoot(frm);
        patchCostView(frm);
        observeCostView(frm, root);
    }

    function schedule(frm) {
        PATCH_DELAYS.forEach(delay => setTimeout(() => enhance(frm), delay));
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
        edge_color(frm) {
            if (window.AlmdinaOrderCostUX && window.AlmdinaOrderCostUX.render) {
                window.AlmdinaOrderCostUX.render(frm);
            }
            schedule(frm);
        },
        default_edge_type(frm) { schedule(frm); },
        pieces_add(frm) { schedule(frm); },
        pieces_remove(frm) { schedule(frm); },
    });
})();
