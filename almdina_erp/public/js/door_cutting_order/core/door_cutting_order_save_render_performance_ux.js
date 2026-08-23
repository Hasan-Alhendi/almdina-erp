(() => {
    "use strict";

    function getNode(value) {
        return value && (value.nodeType ? value : value[0]);
    }

    function documentName(frm) {
        return String(frm && frm.doc && frm.doc.name || "").trim();
    }

    function realRowNames(root) {
        return [...root.querySelectorAll(".dco-fast-table tbody tr[data-row-name]:not(.dco-virtual-row)")]
            .map(row => row.dataset.rowName || "");
    }

    function modelRowNames(frm) {
        return (frm.doc.pieces || []).map(row => row.name || "");
    }

    function htmlRowNames(value) {
        if (typeof value !== "string" || !value.includes("dco-fast-entry-shell")) return [];
        const template = document.createElement("template");
        template.innerHTML = value;
        return [...template.content.querySelectorAll(".dco-fast-table tbody tr[data-row-name]:not(.dco-virtual-row)")]
            .map(row => row.dataset.rowName || "");
    }

    function rowsEqual(left, right) {
        return left.length === right.length
            && left.every((name, index) => name === right[index]);
    }

    function sameRows(frm, root) {
        return rowsEqual(realRowNames(root), modelRowNames(frm));
    }

    function htmlBelongsToForm(frm, value) {
        return rowsEqual(htmlRowNames(value), modelRowNames(frm));
    }

    function costHtmlOrderName(value) {
        if (typeof value !== "string" || !value.includes("dco-cost-shell")) return "";
        const template = document.createElement("template");
        template.innerHTML = value;
        const shell = template.content.querySelector(".dco-cost-shell");
        const tagged = shell && shell.dataset ? String(shell.dataset.orderName || "").trim() : "";
        if (tagged) return tagged;

        const items = template.content.querySelectorAll(".dco-invoice-meta-item");
        for (const item of items) {
            const label = item.querySelector(".label");
            if (String(label && label.textContent || "").trim() !== "رقم الطلب") continue;
            return String(item.querySelector(".value")?.textContent || "").trim();
        }
        return "";
    }

    function existingCostOrderName(root) {
        const shell = root && root.querySelector(".dco-cost-shell");
        if (!shell) return "";
        const tagged = String(shell.dataset.orderName || "").trim();
        if (tagged) return tagged;
        const items = shell.querySelectorAll(".dco-invoice-meta-item");
        for (const item of items) {
            const label = item.querySelector(".label");
            if (String(label && label.textContent || "").trim() !== "رقم الطلب") continue;
            return String(item.querySelector(".value")?.textContent || "").trim();
        }
        return "";
    }

    function tagCostShell(root, name) {
        const shell = root && root.querySelector(".dco-cost-shell");
        if (shell && name) shell.dataset.orderName = name;
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

    function htmlLooksEditable(value) {
        if (typeof value !== "string" || !value.includes("dco-fast-entry-shell")) return false;
        // Locked shells always include this note; editable shells include a virtual row.
        if (value.includes("dco-fast-readonly-note")) return false;
        return value.includes("dco-virtual-row");
    }

    function currentShellEditable(root) {
        if (!root) return false;
        if (root.querySelector(".dco-fast-readonly-note")) return false;
        const input = root.querySelector(
            "tr:not(.dco-virtual-row) input.dco-fast-input[data-field='width_cm']"
        );
        if (input) return !input.disabled;
        return Boolean(root.querySelector("tr.dco-virtual-row"));
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
        if (!field || !field.$wrapper) return;

        const wrapper = field.$wrapper;
        wrapper._dcoFastHtmlGuardForm = frm;
        if (wrapper._dcoFastHtmlGuard) return;

        const originalHtml = wrapper.html;
        wrapper.html = function guardedHtml(value) {
            const currentFrm = wrapper._dcoFastHtmlGuardForm || frm;
            if (wrapper._dcoForceHtmlReplace) {
                wrapper._dcoForceHtmlReplace = false;
                return originalHtml.apply(this, arguments);
            }
            if (
                arguments.length === 1
                && typeof value === "string"
                && value.includes("dco-fast-entry-shell")
            ) {
                // An asynchronous renderer from a previously opened order must
                // never be allowed to write into the shared HTML field wrapper.
                if (!htmlBelongsToForm(currentFrm, value)) return this;

                const root = getNode(this);
                const existing = root && root.querySelector(".dco-fast-entry-shell");
                if (existing && sameRows(currentFrm, root)) {
                    // Same piece rows, but lock/unlock flipped (edit session):
                    // must replace HTML so disabled attributes update.
                    if (htmlLooksEditable(value) !== currentShellEditable(root)) {
                        return originalHtml.apply(this, arguments);
                    }
                    syncExistingTable(currentFrm, root);
                    return this;
                }
            }
            return originalHtml.apply(this, arguments);
        };
        wrapper._dcoFastHtmlGuard = true;
    }

    function costTabIsActive(frm) {
        const field = frm.fields_dict.order_cost_invoice_html;
        const node = getNode(field && (field.wrapper || field.$wrapper));
        if (!node) return false;
        const pane = node.closest(".tab-pane");
        return !pane || pane.classList.contains("active") || pane.classList.contains("show");
    }

    function installCostGuard(frm) {
        const field = frm.fields_dict.order_cost_invoice_html;
        if (!field || !field.$wrapper) return;

        const wrapper = field.$wrapper;
        wrapper._dcoCostHtmlGuardForm = frm;
        if (wrapper._dcoCostHtmlGuard) return;

        const originalHtml = wrapper.html;
        wrapper.html = function guardedCostHtml(value) {
            const currentFrm = wrapper._dcoCostHtmlGuardForm || frm;
            const currentName = documentName(currentFrm);
            if (
                arguments.length === 1
                && typeof value === "string"
                && value.includes("dco-cost-shell")
            ) {
                const incomingName = costHtmlOrderName(value);
                if (incomingName && currentName && incomingName !== currentName) {
                    return this;
                }

                const root = getNode(this);
                const existingName = existingCostOrderName(root);
                const sameDocument = !existingName || !currentName || existingName === currentName;
                if (
                    sameDocument
                    && root?.querySelector(".dco-cost-shell")
                    && !costTabIsActive(currentFrm)
                ) {
                    currentFrm._dco_cost_render_deferred = true;
                    return this;
                }
            }

            currentFrm._dco_cost_render_deferred = false;
            const result = originalHtml.apply(this, arguments);
            tagCostShell(getNode(this), currentName || costHtmlOrderName(value));
            return result;
        };
        wrapper._dcoCostHtmlGuard = true;
    }

    function bindDeferredTabs(frm) {
        const root = getNode(frm.wrapper);
        if (!root) return;
        root._dcoDeferredRenderForm = frm;
        if (root._dcoDeferredRenderTabsBound) return;
        root._dcoDeferredRenderTabsBound = true;
        root.addEventListener("click", event => {
            const currentFrm = root._dcoDeferredRenderForm || frm;
            const tab = event.target.closest("[data-fieldname='cost_tab']");
            if (!tab || !currentFrm._dco_cost_render_deferred) return;
            requestAnimationFrame(() => {
                if (window.AlmdinaOrderCostUX && window.AlmdinaOrderCostUX.render) {
                    window.AlmdinaOrderCostUX.render(currentFrm);
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
