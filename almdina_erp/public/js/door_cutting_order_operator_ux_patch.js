(() => {
    "use strict";

    const CHECK_FIELDS = new Set([
        "allow_rotation",
        "edge_long_right",
        "edge_long_left",
        "edge_width_top",
        "edge_width_bottom",
    ]);

    function rowByName(frm, name) {
        return (frm.doc.pieces || []).find(row => row.name === name) || null;
    }

    function num(value) {
        if (value === null || value === undefined || value === "") return 0;
        return Number(String(value).replace(",", ".")) || 0;
    }

    function updateCalculatedCells(tr, row) {
        if (!tr || !row) return;
        const qty = Math.max(0, num(row.qty));
        const area = (num(row.width_cm) * num(row.length_cm) * qty) / 10000;
        const longSides = Number(Boolean(row.edge_long_right)) + Number(Boolean(row.edge_long_left));
        const widthSides = Number(Boolean(row.edge_width_top)) + Number(Boolean(row.edge_width_bottom));
        const edgeMeters = ((longSides * num(row.length_cm)) + (widthSides * num(row.width_cm))) * qty / 100;
        const areaCell = tr.querySelector("[data-calc='area_m2']");
        const edgeCell = tr.querySelector("[data-calc='edge_meters']");
        if (areaCell) areaCell.textContent = area.toFixed(3);
        if (edgeCell) edgeCell.textContent = edgeMeters.toFixed(3);
    }

    function triggerFieldLater(frm, row, fieldname) {
        window.setTimeout(() => {
            Promise.resolve(frm.script_manager.trigger(fieldname, row.doctype, row.name)).catch(error => console.error(error));
        }, 0);
    }

    function toggleButtonImmediately(frm, button) {
        const tr = button.closest("tr[data-row-name]");
        const fieldname = button.dataset.checkField;
        if (!tr || !CHECK_FIELDS.has(fieldname)) return;

        const row = rowByName(frm, tr.dataset.rowName || "");
        if (!row) return;

        const next = row[fieldname] ? 0 : 1;
        row[fieldname] = next;
        frm.dirty();

        // Update the visible control synchronously before any recalculation starts.
        button.classList.toggle("is-checked", Boolean(next));
        button.setAttribute("aria-pressed", next ? "true" : "false");
        const mark = button.querySelector(".dco-check-mark");
        if (mark) mark.textContent = next ? "✓" : "";
        updateCalculatedCells(tr, row);

        triggerFieldLater(frm, row, fieldname);
    }

    function syncQty(frm, input) {
        const tr = input.closest("tr[data-row-name]");
        if (!tr) return null;
        const row = rowByName(frm, tr.dataset.rowName || "");
        if (!row) return null;
        row.qty = Math.max(1, Math.trunc(num(input.value) || 1));
        input.value = row.qty;
        frm.dirty();
        updateCalculatedCells(tr, row);
        return row;
    }

    function focusNextWidth(currentTr) {
        if (!currentTr) return;
        const next = currentTr.nextElementSibling;
        if (!next) return;
        const width = next.querySelector("input[data-field='width_cm']");
        if (!width) return;
        width.focus({ preventScroll: true });
        width.select();
        next.scrollIntoView({ block: "nearest", inline: "nearest" });
    }

    function measurementWrapper(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.pieces_fast_entry;
        return field && field.$wrapper ? field.$wrapper.get(0) : null;
    }

    function measurementRoot(frm) {
        const wrapper = measurementWrapper(frm);
        return wrapper && wrapper.querySelector(".dco-fast-entry-shell");
    }

    function disconnectCompetingEdgeObservers(root) {
        if (!root) return;
        [
            "_dcoSideEdgeObserver",
            "_dcoCompactEdgeProfileControlsObserver",
        ].forEach(key => {
            const observer = root[key];
            if (observer && typeof observer.disconnect === "function") observer.disconnect();
            root[key] = null;
        });
    }

    function structuralMeasurementMutation(mutation) {
        const nodes = [
            ...(mutation.addedNodes || []),
            ...(mutation.removedNodes || []),
        ];
        return nodes.some(node => {
            if (!node || node.nodeType !== 1) return false;
            if (node.matches(".dco-fast-entry-shell,tbody,tr[data-row-name]")) return true;
            if (node.matches("td") && node.querySelector("input[data-field],select[data-field]")) return true;
            return Boolean(node.querySelector(
                ".dco-fast-entry-shell,tbody tr[data-row-name],input[data-field='width_cm'],select[data-field='piece_type']"
            ));
        });
    }

    function refreshEdgeDecorations(frm) {
        const root = measurementRoot(frm);
        if (!root) return;
        disconnectCompetingEdgeObservers(root);

        const multiEdge = window.AlmdinaMultiEdgeBanding;
        if (multiEdge && typeof multiEdge.schedule === "function") multiEdge.schedule(frm);
        const controls = window.AlmdinaEdgeProfileControls;
        if (controls && typeof controls.schedule === "function") controls.schedule(frm);

        // Both legacy edge modules install their own broad MutationObservers.
        // They decorate the same nodes and can trigger each other forever. Their
        // explicit field-event schedules remain active, while this structural
        // observer owns DOM replacement detection.
        requestAnimationFrame(() => disconnectCompetingEdgeObservers(measurementRoot(frm)));
        setTimeout(() => disconnectCompetingEdgeObservers(measurementRoot(frm)), 180);
    }

    function stabilizeEdgeRendering(frm) {
        const wrapper = measurementWrapper(frm);
        if (!wrapper) return;

        if (frm.__dcoEdgeStructureObservedWrapper !== wrapper) {
            if (frm.__dcoEdgeStructureObserver) frm.__dcoEdgeStructureObserver.disconnect();
            let queued = false;
            const observer = new MutationObserver(mutations => {
                if (!mutations.some(structuralMeasurementMutation) || queued) return;
                queued = true;
                requestAnimationFrame(() => {
                    queued = false;
                    refreshEdgeDecorations(frm);
                });
            });
            observer.observe(wrapper, { childList: true, subtree: true });
            frm.__dcoEdgeStructureObserver = observer;
            frm.__dcoEdgeStructureObservedWrapper = wrapper;
        }

        refreshEdgeDecorations(frm);
    }

    function install(frm) {
        const field = frm.fields_dict.pieces_fast_entry;
        if (!field || !field.$wrapper) return;
        const root = field.$wrapper.get(0);
        if (!root || root._dcoFastPatchInstalled) {
            stabilizeEdgeRendering(frm);
            return;
        }
        root._dcoFastPatchInstalled = true;

        // Capture the click before the original delegated handler. This avoids any
        // stale/competing handler and guarantees a true one-click toggle.
        root.addEventListener("click", event => {
            const button = event.target.closest(".dco-check-toggle[data-check-field]");
            if (!button || !root.contains(button) || button.disabled) return;
            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation();
            toggleButtonImmediately(frm, button);
        }, true);

        root.addEventListener("keydown", event => {
            const input = event.target.closest("input[data-field='qty']");
            if (!input || !root.contains(input) || event.key !== "Enter") return;

            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation();

            const tr = input.closest("tr[data-row-name]");
            const row = syncQty(frm, input);
            if (row) triggerFieldLater(frm, row, "qty");
            focusNextWidth(tr);
        }, true);

        requestAnimationFrame(() => stabilizeEdgeRendering(frm));
        setTimeout(() => stabilizeEdgeRendering(frm), 220);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) {
            install(frm);
            setTimeout(() => stabilizeEdgeRendering(frm), 0);
        },
        refresh(frm) {
            install(frm);
            requestAnimationFrame(() => install(frm));
            setTimeout(() => stabilizeEdgeRendering(frm), 220);
        },
        almdina_edit_session_changed(frm) {
            requestAnimationFrame(() => stabilizeEdgeRendering(frm));
            setTimeout(() => stabilizeEdgeRendering(frm), 180);
        },
    });
})();
