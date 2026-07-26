(() => {
    "use strict";

    function getNode(value) {
        return value && (value.nodeType ? value : value[0]);
    }

    function realRowNames(root) {
        return [...root.querySelectorAll(".dco-fast-table tbody tr[data-row-name]:not(.dco-virtual-row)")]
            .map(row => row.dataset.rowName || "");
    }

    function modelRowNames(frm) {
        return (frm.doc.pieces || []).map(row => row.name || "");
    }

    function sameRows(frm, root) {
        const domNames = realRowNames(root);
        const docNames = modelRowNames(frm);
        return domNames.length === docNames.length
            && domNames.every((name, index) => name === docNames[index]);
    }

    function number(value) {
        const parsed = Number(value || 0);
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function area(row) {
        return number(row.width_cm) * number(row.length_cm) * Math.max(0, number(row.qty)) / 10000;
    }

    function edgeMeters(row) {
        const longSides = Number(Boolean(row.edge_long_right)) + Number(Boolean(row.edge_long_left));
        const widthSides = Number(Boolean(row.edge_width_top)) + Number(Boolean(row.edge_width_bottom));
        return (
            (number(row.length_cm) * longSides + number(row.width_cm) * widthSides)
            * Math.max(0, number(row.qty))
            / 100
        );
    }

    function syncToggle(button, checked) {
        if (!button) return;
        button.classList.toggle("is-checked", checked);
        button.setAttribute("aria-pressed", checked ? "true" : "false");
        const mark = button.querySelector(".dco-check-mark");
        if (mark) mark.textContent = checked ? "✓" : "";
    }

    function syncExistingTable(frm, root) {
        const active = document.activeElement;
        (frm.doc.pieces || []).forEach((row, index) => {
            const tr = root.querySelector(`tr[data-row-name="${CSS.escape(row.name || "")}"]`);
            if (!tr) return;

            const numberCell = tr.querySelector(".dco-row-number");
            if (numberCell) numberCell.textContent = index + 1;

            tr.querySelectorAll("input[data-field],select[data-field]").forEach(control => {
                if (control === active) return;
                const fieldname = control.dataset.field;
                if (!fieldname) return;
                const value = fieldname === "qty" ? (row[fieldname] || 1) : (row[fieldname] ?? "");
                if (String(control.value) !== String(value)) control.value = value;
            });

            tr.querySelectorAll("button.dco-check-toggle[data-check-field]").forEach(button => {
                syncToggle(button, Boolean(row[button.dataset.checkField]));
            });

            const areaCell = tr.querySelector("[data-calc='area_m2']");
            const edgeCell = tr.querySelector("[data-calc='edge_meters']");
            if (areaCell) areaCell.textContent = area(row).toFixed(3);
            if (edgeCell) edgeCell.textContent = edgeMeters(row).toFixed(3);

            tr.classList.toggle("dco-special-row", row.piece_type === "Special");
            tr.classList.toggle("dco-clipped-corner-row", row.piece_type === "Clipped Corner");

            const sketch = tr.querySelector(".dco-special-sketch-button");
            if (sketch) {
                const documented = Boolean(String(row.special_shape_drawing_json || "").trim());
                sketch.classList.toggle("is-documented", documented);
            }
        });
    }

    function installMeasurementGuard(frm) {
        const field = frm.fields_dict.pieces_fast_entry;
        if (!field || !field.$wrapper || field.$wrapper._dcoFastHtmlGuard) return;

        const wrapper = field.$wrapper;
        const originalHtml = wrapper.html;
        wrapper.html = function guardedHtml(value) {
            if (
                arguments.length === 1
                && typeof value === "string"
                && value.includes("dco-fast-entry-shell")
            ) {
                const root = getNode(this);
                const existing = root && root.querySelector(".dco-fast-entry-shell");
                if (existing && sameRows(frm, root)) {
                    syncExistingTable(frm, root);
                    return this;
                }
            }
            return originalHtml.apply(this, arguments);
        };
        wrapper._dcoFastHtmlGuard = true;
    }

    function costTabIsActive(frm) {
        const field = frm.fields_dict.order_cost_invoice_html;
        const node = field && field.wrapper;
        if (!node) return false;
        const pane = node.closest ? node.closest(".tab-pane") : null;
        return !pane || pane.classList.contains("active") || pane.classList.contains("show");
    }

    function installCostGuard(frm) {
        const field = frm.fields_dict.order_cost_invoice_html;
        if (!field || !field.$wrapper || field.$wrapper._dcoCostHtmlGuard) return;

        const wrapper = field.$wrapper;
        const originalHtml = wrapper.html;
        wrapper.html = function guardedCostHtml(value) {
            if (
                arguments.length === 1
                && typeof value === "string"
                && value.includes("dco-cost-shell")
                && getNode(this)?.querySelector(".dco-cost-shell")
                && !costTabIsActive(frm)
            ) {
                frm._dco_cost_render_deferred = true;
                return this;
            }
            frm._dco_cost_render_deferred = false;
            return originalHtml.apply(this, arguments);
        };
        wrapper._dcoCostHtmlGuard = true;
    }

    function bindDeferredTabs(frm) {
        const root = getNode(frm.wrapper);
        if (!root || root._dcoDeferredRenderTabsBound) return;
        root._dcoDeferredRenderTabsBound = true;
        root.addEventListener("click", event => {
            const tab = event.target.closest("[data-fieldname='cost_tab']");
            if (!tab || !frm._dco_cost_render_deferred) return;
            requestAnimationFrame(() => {
                if (window.AlmdinaOrderCostUX && window.AlmdinaOrderCostUX.render) {
                    window.AlmdinaOrderCostUX.render(frm);
                }
            });
        });
    }

    function install(frm) {
        installMeasurementGuard(frm);
        installCostGuard(frm);
        bindDeferredTabs(frm);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { install(frm); },
        refresh(frm) { install(frm); },
    });
})();
