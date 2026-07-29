(() => {
    "use strict";

    const EDITABLE_STATUSES = new Set(["Draft", "Pending Review", "Rejected"]);
    const CHILD_DOCTYPE = "Door Cutting Order Detail";
    let virtualSequence = 0;

    function isArabic() {
        const lang = String(
            (frappe.boot && frappe.boot.lang) ||
            (frappe.boot && frappe.boot.user && frappe.boot.user.language) ||
            document.documentElement.lang ||
            ""
        ).toLowerCase();
        return lang === "ar" || lang.startsWith("ar-");
    }

    function isEditable(frm) {
        if (window.frappe && frappe.almdina && frappe.almdina.orderCanEdit) {
            return frappe.almdina.orderCanEdit(frm);
        }
        return frm.doc.docstatus === 0 && EDITABLE_STATUSES.has(frm.doc.status || "Draft");
    }

    function getRoot(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.pieces_fast_entry;
        return field && field.$wrapper ? field.$wrapper.get(0) : null;
    }

    function rowByName(frm, name) {
        return (frm.doc.pieces || []).find(row => row.name === name) || null;
    }

    function selectedRows(frm) {
        if (!(frm._dco_selected_piece_rows instanceof Set)) {
            frm._dco_selected_piece_rows = new Set();
        }
        return frm._dco_selected_piece_rows;
    }

    function reindex(frm) {
        (frm.doc.pieces || []).forEach((row, index) => {
            row.idx = index + 1;
            row.piece_no = index + 1;
        });
    }

    function ensureHeaderSelector(root) {
        const headRow = root.querySelector(".dco-fast-table thead tr");
        if (!headRow) return;
        let cell = headRow.querySelector(":scope > th.dco-select-col");
        if (!cell) {
            cell = document.createElement("th");
            cell.className = "dco-select-col";
            headRow.prepend(cell);
        }
        if (!cell.querySelector(".dco-select-all")) {
            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.className = "dco-select-all";
            checkbox.setAttribute("aria-label", isArabic() ? "تحديد كل الأسطر" : "Select all rows");
            checkbox.title = isArabic() ? "تحديد كل الأسطر" : "Select all rows";
            cell.appendChild(checkbox);
        }
    }

    function ensureRowSelector(frm, tr) {
        if (!tr) return;
        let cell = tr.querySelector(":scope > td.dco-select-col");
        if (!cell) {
            cell = document.createElement("td");
            cell.className = "dco-select-col";
            tr.prepend(cell);
        }

        if (tr.classList.contains("dco-virtual-row")) {
            cell.replaceChildren();
            tr.classList.remove("dco-row-selected");
            return;
        }

        const name = tr.dataset.rowName || "";
        const row = rowByName(frm, name);
        if (!row) {
            cell.replaceChildren();
            return;
        }

        let checkbox = cell.querySelector("input.dco-row-selector");
        if (!checkbox) {
            checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.className = "dco-row-selector";
            checkbox.setAttribute("aria-label", isArabic() ? "تحديد السطر" : "Select row");
            checkbox.title = isArabic() ? "تحديد هذا السطر" : "Select this row";
            cell.appendChild(checkbox);
        }
        checkbox.dataset.rowName = name;
        checkbox.checked = selectedRows(frm).has(name);
        checkbox.disabled = !isEditable(frm);
        tr.classList.toggle("dco-row-selected", checkbox.checked);
    }

    function ensureAllSelectors(frm, root) {
        ensureHeaderSelector(root);
        root.querySelectorAll(".dco-fast-table tbody tr[data-row-name]").forEach(tr => ensureRowSelector(frm, tr));
        refreshSelectionHeader(frm, root);
    }

    function refreshSelectionHeader(frm, root) {
        const checkbox = root.querySelector(".dco-select-all");
        if (!checkbox) return;
        const rows = [...root.querySelectorAll(".dco-fast-table tbody tr[data-row-name]:not(.dco-virtual-row)")]
            .filter(tr => Boolean(rowByName(frm, tr.dataset.rowName || "")));
        const selected = selectedRows(frm);
        const selectedCount = rows.filter(tr => selected.has(tr.dataset.rowName || "")).length;
        checkbox.checked = rows.length > 0 && selectedCount === rows.length;
        checkbox.indeterminate = selectedCount > 0 && selectedCount < rows.length;
        checkbox.disabled = rows.length === 0 || !isEditable(frm);
    }

    function refreshColumnHeaderStates(frm, root) {
        root.querySelectorAll(".dco-column-select-all-input[data-column-field]").forEach(checkbox => {
            const fieldname = checkbox.dataset.columnField;
            const rows = [...root.querySelectorAll(".dco-fast-table tbody tr[data-row-name]:not(.dco-virtual-row)")]
                .map(tr => rowByName(frm, tr.dataset.rowName || ""))
                .filter(Boolean);
            const checked = rows.filter(row => Boolean(row[fieldname])).length;
            checkbox.checked = rows.length > 0 && checked === rows.length;
            checkbox.indeterminate = checked > 0 && checked < rows.length;
            checkbox.disabled = rows.length === 0 || !isEditable(frm);
        });
    }

    function copyVirtualControlsToRow(tr, row) {
        tr.querySelectorAll("[data-field]").forEach(control => {
            const fieldname = control.dataset.field;
            if (!fieldname) return;
            let value = control.value;
            if (["width_cm", "length_cm", "qty"].includes(fieldname)) {
                value = Number(String(value || "").replace(",", ".")) || 0;
                if (fieldname === "qty") value = Math.max(1, Math.trunc(value || 1));
            }
            row[fieldname] = value;
        });
        tr.querySelectorAll("button.dco-check-toggle[data-check-field]").forEach(button => {
            row[button.dataset.checkField] = button.classList.contains("is-checked") ? 1 : 0;
        });
        if (!row.qty) row.qty = 1;
    }

    function resetVirtualClone(frm, clone) {
        clone.dataset.rowName = `__virtual__perf_${Date.now()}_${++virtualSequence}`;
        clone.classList.add("dco-virtual-row");
        clone.classList.remove("dco-special-row", "dco-clipped-corner-row", "dco-row-selected");

        const selectorCell = clone.querySelector(":scope > td.dco-select-col");
        if (selectorCell) selectorCell.replaceChildren();

        const number = clone.querySelector(".dco-row-number");
        if (number) number.textContent = (frm.doc.pieces || []).length + 1;

        clone.querySelectorAll("[data-field]").forEach(control => {
            const fieldname = control.dataset.field;
            if (fieldname === "piece_type") control.value = "Regular";
            else if (fieldname === "qty") control.value = "1";
            else control.value = "";
        });

        clone.querySelectorAll("button.dco-check-toggle[data-check-field]").forEach(button => {
            button.classList.remove("is-checked");
            button.setAttribute("aria-pressed", "false");
            const mark = button.querySelector(".dco-check-mark");
            if (mark) mark.textContent = "";
        });

        const sketch = clone.querySelector("button.dco-special-sketch-button");
        if (sketch) {
            sketch.disabled = true;
            sketch.classList.remove("is-documented", "is-clipped-corner");
            const icon = sketch.querySelector("span:first-child");
            const label = sketch.querySelector("span:last-child");
            if (icon) icon.textContent = "✎";
            if (label) label.textContent = isArabic() ? "ارسم" : "Sketch";
        }

        clone.querySelectorAll("[data-calc]").forEach(cell => { cell.textContent = "0.000"; });
        const deleteCell = clone.querySelector(".dco-col-delete");
        if (deleteCell) deleteCell.replaceChildren();
        const notesButton = clone.querySelector("button.dco-notes-expand");
        if (notesButton) {
            notesButton.disabled = true;
            notesButton.classList.remove("has-note", "has-long-note");
        }
    }

    function materializeVirtualRow(frm, tr) {
        const row = frappe.model.add_child(frm.doc, CHILD_DOCTYPE, "pieces");
        copyVirtualControlsToRow(tr, row);
        reindex(frm);

        tr.dataset.rowName = row.name;
        tr.classList.remove("dco-virtual-row");
        const number = tr.querySelector(".dco-row-number");
        if (number) number.textContent = row.idx;
        ensureRowSelector(frm, tr);

        const tbody = tr.parentElement;
        if (tbody) {
            const clone = tr.cloneNode(true);
            resetVirtualClone(frm, clone);
            tbody.querySelectorAll("tr.dco-virtual-row").forEach(existing => existing.remove());
            tbody.appendChild(clone);
        }

        frm.dirty();
        queueMicrotask(() => {
            Promise.resolve(frm.script_manager.trigger("pieces_add", row.doctype, row.name)).catch(error => console.error(error));
        });
        return row;
    }

    function updatePieceTypeVisual(frm, tr, row) {
        const special = row.piece_type === "Special";
        const clipped = row.piece_type === "Clipped Corner";
        const drawing = Boolean(String(row.special_shape_drawing_json || "").trim());
        const exact = Boolean(
            special
            && window.AlmdinaSpecialShapeGeometry
            && window.AlmdinaSpecialShapeGeometry.isExact(row)
        );
        tr.classList.toggle("dco-special-row", special);
        tr.classList.toggle("dco-clipped-corner-row", clipped);

        const edgeButtons = tr.querySelector(".dco-edge-buttons");
        if (edgeButtons) {
            edgeButtons.title = special
                ? (isArabic()
                    ? "قشاط مبدئي لتقدير السعر؛ يمكن اعتماده أو تعديله بعد تصميم CNC"
                    : "Preliminary banding for the estimate; finalize after CNC design")
                : "";
        }

        const sketch = tr.querySelector("button.dco-special-sketch-button");
        if (sketch) {
            const cornerSummary = clipped && window.AlmdinaClippedCornerGeometry
                ? window.AlmdinaClippedCornerGeometry.summary(row)
                : "";
            sketch.disabled = !((special || clipped) && isEditable(frm));
            sketch.classList.toggle("is-documented", special && (drawing || exact));
            sketch.classList.toggle("is-exact-geometry", exact);
            sketch.classList.toggle("is-clipped-corner", clipped);
            const icon = sketch.querySelector("span:first-child");
            const label = sketch.querySelector("span:last-child");
            if (icon) icon.textContent = clipped ? "⌑" : ((drawing || exact) ? "✓" : "✎");
            if (label) {
                label.textContent = clipped
                    ? (isArabic() ? "ضبط" : "Set")
                    : ((drawing || exact)
                        ? (isArabic() ? "موثقة" : "Documented")
                        : (isArabic() ? "ارسم" : "Sketch"));
            }
            sketch.title = clipped
                ? `${isArabic() ? "ضبط الزاوية المقصوصة" : "Configure clipped corner"}${cornerSummary ? ` — ${cornerSummary}` : ""}`
                : (isArabic() ? "افتح ورقة الرسم والملاحظات" : "Open sketch and notes");
        }

        ensureRowSelector(frm, tr);
    }

    function schedulePieceTypeTrigger(frm, row) {
        frm._dco_piece_type_trigger_timers = frm._dco_piece_type_trigger_timers || {};
        const key = row.name;
        if (frm._dco_piece_type_trigger_timers[key]) {
            clearTimeout(frm._dco_piece_type_trigger_timers[key]);
        }
        frm._dco_piece_type_trigger_timers[key] = setTimeout(() => {
            delete frm._dco_piece_type_trigger_timers[key];
            Promise.resolve(frm.script_manager.trigger("piece_type", row.doctype, row.name)).catch(error => console.error(error));
        }, 0);
    }

    function handlePieceTypeChange(frm, root, control, event) {
        const tr = control.closest("tr[data-row-name]");
        if (!tr) return;

        // Stop the legacy handler before it replaces the entire table. Updating one
        // row in place keeps selection, focus and both scroll positions untouched.
        event.stopImmediatePropagation();
        event.stopPropagation();

        let row = rowByName(frm, tr.dataset.rowName || "");
        if (!row && tr.classList.contains("dco-virtual-row")) {
            row = materializeVirtualRow(frm, tr);
        }
        if (!row) return;

        row.piece_type = control.value || "Regular";
        if (row.piece_type === "Clipped Corner" && window.AlmdinaClippedCornerEditor) {
            window.AlmdinaClippedCornerEditor.prepare(row);
        }
        frm.dirty();
        updatePieceTypeVisual(frm, tr, row);
        ensureAllSelectors(frm, root);
        refreshColumnHeaderStates(frm, root);
        control.focus({ preventScroll: true });
        schedulePieceTypeTrigger(frm, row);
    }

    function installLeanObserver(frm, root) {
        const tbody = root.querySelector(".dco-fast-table tbody");
        if (!tbody) return;

        // The original keyboard observer watched every class mutation in every
        // button, forcing full-table scans on each click. Replace it with one
        // child-list observer that runs only when rows are added or removed.
        if (root._dcoKeyboardColumnsObserver) {
            root._dcoKeyboardColumnsObserver.disconnect();
        }
        if (root._dcoTablePerformanceObserver) {
            root._dcoTablePerformanceObserver.disconnect();
        }

        let scheduled = false;
        const observer = new MutationObserver(() => {
            if (scheduled) return;
            scheduled = true;
            requestAnimationFrame(() => {
                scheduled = false;
                ensureAllSelectors(frm, root);
                refreshColumnHeaderStates(frm, root);
            });
        });
        observer.observe(tbody, { childList: true, subtree: false });
        root._dcoTablePerformanceObserver = observer;
        root._dcoKeyboardColumnsObserver = observer;
        root._dcoKeyboardObservedBody = tbody;
    }

    function bind(frm, root) {
        if (root._dcoTablePerformanceBound) return;
        root._dcoTablePerformanceBound = true;

        root.addEventListener("change", event => {
            const control = event.target.closest("select.dco-fast-select[data-field='piece_type']");
            if (control && root.contains(control)) {
                handlePieceTypeChange(frm, root, control, event);
                return;
            }
            if (event.target.closest(".dco-column-select-all-input,.dco-row-selector,.dco-select-all")) {
                requestAnimationFrame(() => {
                    ensureAllSelectors(frm, root);
                    refreshColumnHeaderStates(frm, root);
                });
            }
        }, true);

        root.addEventListener("click", event => {
            if (!event.target.closest("button.dco-check-toggle[data-check-field]")) return;
            requestAnimationFrame(() => refreshColumnHeaderStates(frm, root));
        });
    }

    function enhance(frm) {
        const root = getRoot(frm);
        if (!root || !root.querySelector(".dco-fast-table")) return;
        ensureAllSelectors(frm, root);
        refreshColumnHeaderStates(frm, root);
        bind(frm, root);
        installLeanObserver(frm, root);
    }

    function schedule(frm) {
        enhance(frm);
        requestAnimationFrame(() => enhance(frm));
        setTimeout(() => enhance(frm), 220);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
        pieces_add(frm) { requestAnimationFrame(() => enhance(frm)); },
        pieces_remove(frm) { requestAnimationFrame(() => enhance(frm)); },
    });
})();
