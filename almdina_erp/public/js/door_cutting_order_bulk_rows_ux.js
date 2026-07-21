(() => {
    "use strict";

    const EDITABLE_STATUSES = new Set(["Draft", "Pending Review", "Rejected"]);

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
        return frm.doc.docstatus === 0 && EDITABLE_STATUSES.has(frm.doc.status || "Draft");
    }

    function selectedRows(frm) {
        if (!(frm._dco_selected_piece_rows instanceof Set)) {
            frm._dco_selected_piece_rows = new Set();
        }
        return frm._dco_selected_piece_rows;
    }

    function liveRowNames(frm) {
        return new Set((frm.doc.pieces || []).map(row => row.name));
    }

    function installStyles() {
        if (document.getElementById("dco-bulk-rows-ux-css")) return;
        $("head").append(`
            <style id="dco-bulk-rows-ux-css">
                .dco-fast-table { min-width:1180px !important; }
                .dco-fast-table .dco-select-col {
                    width:48px !important;
                    min-width:48px !important;
                    max-width:48px !important;
                    text-align:center !important;
                    padding:4px !important;
                }
                .dco-row-selector,
                .dco-select-all {
                    width:20px;
                    height:20px;
                    margin:0;
                    cursor:pointer;
                    accent-color:var(--primary,#2490ef);
                    vertical-align:middle;
                }
                .dco-row-selector:focus-visible,
                .dco-select-all:focus-visible {
                    outline:2px solid var(--primary,#2490ef);
                    outline-offset:2px;
                    border-radius:4px;
                }
                .dco-fast-table tbody tr.dco-row-selected {
                    background:rgba(36,144,239,.09) !important;
                    box-shadow:inset -3px 0 0 var(--primary,#2490ef);
                }
                .dco-fast-table tbody tr.dco-row-selected:hover {
                    background:rgba(36,144,239,.12) !important;
                }
                .dco-bulk-footer {
                    display:flex;
                    align-items:center;
                    justify-content:space-between;
                    gap:12px;
                    flex-wrap:wrap;
                    padding:10px 12px;
                    border-top:1px solid var(--border-color,#dfe3e8);
                    background:var(--card-bg,var(--fg-color,#fff));
                    position:sticky;
                    bottom:0;
                    z-index:8;
                    box-shadow:0 -6px 18px rgba(0,0,0,.035);
                }
                .dco-selection-actions {
                    display:flex;
                    align-items:center;
                    gap:8px;
                    flex-wrap:wrap;
                }
                .dco-selection-actions[hidden] { display:none !important; }
                .dco-selection-count {
                    display:inline-flex;
                    align-items:center;
                    min-height:32px;
                    padding:5px 10px;
                    border-radius:999px;
                    background:rgba(36,144,239,.1);
                    color:var(--primary,#2490ef);
                    font-weight:800;
                    font-size:12px;
                }
                .dco-delete-selected.btn {
                    font-weight:800;
                    border-radius:8px;
                }
                .dco-clear-selection.btn,
                .dco-add-row.btn {
                    border-radius:8px;
                    font-weight:700;
                }
                .dco-add-row {
                    margin-inline-start:auto;
                    min-width:150px;
                }
                .dco-add-row .dco-plus {
                    font-size:18px;
                    line-height:1;
                    margin-inline-end:5px;
                    vertical-align:-1px;
                }
                @media (max-width:700px) {
                    .dco-bulk-footer { align-items:stretch; }
                    .dco-selection-actions { width:100%; }
                    .dco-add-row { width:100%; margin-inline-start:0; }
                }
            </style>
        `);
    }

    function makeSelectorCell(frm, tr) {
        let cell = tr.querySelector(":scope > .dco-select-col");
        if (!cell) {
            cell = document.createElement("td");
            cell.className = "dco-select-col";
            tr.prepend(cell);
        }

        if (tr.classList.contains("dco-virtual-row")) {
            cell.innerHTML = "";
            tr.classList.remove("dco-row-selected");
            return;
        }

        const name = tr.dataset.rowName || "";
        const exists = (frm.doc.pieces || []).some(row => row.name === name);
        if (!exists) {
            cell.innerHTML = "";
            return;
        }

        let checkbox = cell.querySelector(".dco-row-selector");
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
        tr.classList.toggle("dco-row-selected", checkbox.checked);
    }

    function ensureHeader(root) {
        const headRow = root.querySelector(".dco-fast-table thead tr");
        if (!headRow) return;
        let cell = headRow.querySelector(":scope > .dco-select-col");
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

    function ensureRows(frm, root) {
        root.querySelectorAll(".dco-fast-table tbody tr[data-row-name]").forEach(tr => makeSelectorCell(frm, tr));
    }

    function ensureFooter(frm, root) {
        const shell = root.querySelector(".dco-fast-entry-shell") || root;
        let footer = shell.querySelector(":scope > .dco-bulk-footer");
        if (!footer) {
            footer = document.createElement("div");
            footer.className = "dco-bulk-footer";
            footer.innerHTML = `
                <div class="dco-selection-actions" hidden>
                    <span class="dco-selection-count"></span>
                    <button type="button" class="btn btn-danger btn-sm dco-delete-selected">
                        ${isArabic() ? "حذف الأسطر المحددة" : "Delete selected rows"}
                    </button>
                    <button type="button" class="btn btn-default btn-sm dco-clear-selection">
                        ${isArabic() ? "إلغاء التحديد" : "Clear selection"}
                    </button>
                </div>
                <button type="button" class="btn btn-primary btn-sm dco-add-row">
                    <span class="dco-plus">+</span>${isArabic() ? "إضافة سطر جديد" : "Add new row"}
                </button>
            `;
            shell.appendChild(footer);
        }
        footer.querySelector(".dco-add-row").disabled = !isEditable(frm);
    }

    function pruneSelection(frm) {
        const selected = selectedRows(frm);
        const live = liveRowNames(frm);
        [...selected].forEach(name => {
            if (!live.has(name)) selected.delete(name);
        });
    }

    function updateSelectionUI(frm, root) {
        pruneSelection(frm);
        const selected = selectedRows(frm);
        const actualRows = [...root.querySelectorAll(".dco-fast-table tbody tr[data-row-name]:not(.dco-virtual-row)")]
            .filter(tr => (frm.doc.pieces || []).some(row => row.name === tr.dataset.rowName));

        actualRows.forEach(tr => {
            const checkbox = tr.querySelector(".dco-row-selector");
            const checked = selected.has(tr.dataset.rowName || "");
            if (checkbox) checkbox.checked = checked;
            tr.classList.toggle("dco-row-selected", checked);
        });

        const all = root.querySelector(".dco-select-all");
        if (all) {
            all.checked = actualRows.length > 0 && selected.size === actualRows.length;
            all.indeterminate = selected.size > 0 && selected.size < actualRows.length;
            all.disabled = actualRows.length === 0 || !isEditable(frm);
        }

        const actions = root.querySelector(".dco-selection-actions");
        const count = root.querySelector(".dco-selection-count");
        if (actions) actions.hidden = selected.size === 0;
        if (count) {
            count.textContent = isArabic()
                ? `تم تحديد ${selected.size} ${selected.size === 1 ? "سطر" : "أسطر"}`
                : `${selected.size} row${selected.size === 1 ? "" : "s"} selected`;
        }
    }

    function reindex(frm, root) {
        (frm.doc.pieces || []).forEach((row, index) => {
            row.idx = index + 1;
            row.piece_no = index + 1;
        });
        let visibleIndex = 0;
        root.querySelectorAll(".dco-fast-table tbody tr[data-row-name]").forEach(tr => {
            if (tr.classList.contains("dco-virtual-row")) {
                const number = tr.querySelector(".dco-row-number");
                if (number) number.textContent = (frm.doc.pieces || []).length + 1;
                return;
            }
            const row = (frm.doc.pieces || []).find(item => item.name === tr.dataset.rowName);
            if (!row) return;
            visibleIndex += 1;
            const number = tr.querySelector(".dco-row-number");
            if (number) number.textContent = visibleIndex;
        });
    }

    function focusBlankRow(root) {
        const virtual = root.querySelector(".dco-fast-table tbody tr.dco-virtual-row");
        const width = virtual && virtual.querySelector("input[data-field='width_cm']");
        if (!width) return false;
        virtual.scrollIntoView({ block: "nearest", inline: "nearest" });
        width.focus({ preventScroll: true });
        width.select();
        return true;
    }

    function clearSelection(frm, root) {
        selectedRows(frm).clear();
        updateSelectionUI(frm, root);
    }

    function deleteSelected(frm, root) {
        const selected = selectedRows(frm);
        const names = [...selected].filter(name => (frm.doc.pieces || []).some(row => row.name === name));
        if (!names.length) return;

        const message = isArabic()
            ? (names.length === 1
                ? "سيتم حذف السطر المحدد من جدول القياسات. هل أنت متأكد من المتابعة؟"
                : `سيتم حذف ${names.length} أسطر محددة من جدول القياسات. هل أنت متأكد من المتابعة؟`)
            : (names.length === 1
                ? "The selected row will be deleted. Continue?"
                : `${names.length} selected rows will be deleted. Continue?`);

        frappe.confirm(message, () => {
            const toDelete = new Set(names);
            const rows = frm.doc.pieces || [];

            for (let index = rows.length - 1; index >= 0; index -= 1) {
                const row = rows[index];
                if (!toDelete.has(row.name)) continue;
                rows.splice(index, 1);
                try {
                    frappe.model.clear_doc(row.doctype, row.name);
                } catch (error) {
                    // The child may already have been detached locally.
                }
            }

            root.querySelectorAll(".dco-fast-table tbody tr[data-row-name]:not(.dco-virtual-row)").forEach(tr => {
                if (toDelete.has(tr.dataset.rowName || "")) tr.remove();
            });

            selected.clear();
            reindex(frm, root);
            frm.dirty();
            frm.refresh_field("pieces");
            ensureRows(frm, root);
            updateSelectionUI(frm, root);

            Promise.resolve(frm.script_manager.trigger("pieces_remove"))
                .catch(error => console.error(error));

            frappe.show_alert({
                message: isArabic()
                    ? (names.length === 1 ? "تم حذف السطر المحدد" : `تم حذف ${names.length} أسطر محددة`)
                    : (names.length === 1 ? "Selected row deleted" : `${names.length} selected rows deleted`),
                indicator: "green",
            }, 3);
        });
    }

    function bind(frm, root) {
        if (root._dcoBulkRowsBound) return;
        root._dcoBulkRowsBound = true;

        root.addEventListener("change", event => {
            const rowSelector = event.target.closest(".dco-row-selector");
            if (rowSelector && root.contains(rowSelector)) {
                const name = rowSelector.dataset.rowName || "";
                if (!name) return;
                if (rowSelector.checked) selectedRows(frm).add(name);
                else selectedRows(frm).delete(name);
                updateSelectionUI(frm, root);
                return;
            }

            const selectAll = event.target.closest(".dco-select-all");
            if (selectAll && root.contains(selectAll)) {
                const selected = selectedRows(frm);
                selected.clear();
                if (selectAll.checked) {
                    (frm.doc.pieces || []).forEach(row => selected.add(row.name));
                }
                updateSelectionUI(frm, root);
            }
        });

        root.addEventListener("click", event => {
            const deleteButton = event.target.closest(".dco-delete-selected");
            if (deleteButton && root.contains(deleteButton)) {
                event.preventDefault();
                deleteSelected(frm, root);
                return;
            }

            const clearButton = event.target.closest(".dco-clear-selection");
            if (clearButton && root.contains(clearButton)) {
                event.preventDefault();
                clearSelection(frm, root);
                return;
            }

            const addButton = event.target.closest(".dco-add-row");
            if (addButton && root.contains(addButton)) {
                event.preventDefault();
                if (!isEditable(frm)) return;
                focusBlankRow(root);
            }
        });
    }

    function observeDynamicRows(frm, root) {
        const tbody = root.querySelector(".dco-fast-table tbody");
        if (!tbody || tbody._dcoBulkObserver) return;

        let scheduled = false;
        const observer = new MutationObserver(() => {
            if (scheduled) return;
            scheduled = true;
            requestAnimationFrame(() => {
                scheduled = false;
                ensureRows(frm, root);
                updateSelectionUI(frm, root);
            });
        });

        observer.observe(tbody, {
            childList: true,
            subtree: false,
            attributes: true,
            attributeFilter: ["class", "data-row-name"],
        });
        tbody._dcoBulkObserver = observer;
    }

    function enhance(frm) {
        installStyles();
        const field = frm.fields_dict.pieces_fast_entry;
        if (!field || !field.$wrapper) return;
        const root = field.$wrapper.get(0);
        if (!root || !root.querySelector(".dco-fast-table")) return;

        ensureHeader(root);
        ensureRows(frm, root);
        ensureFooter(frm, root);
        bind(frm, root);
        observeDynamicRows(frm, root);
        updateSelectionUI(frm, root);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) {
            requestAnimationFrame(() => enhance(frm));
        },
        refresh(frm) {
            requestAnimationFrame(() => enhance(frm));
        },
    });
})();
