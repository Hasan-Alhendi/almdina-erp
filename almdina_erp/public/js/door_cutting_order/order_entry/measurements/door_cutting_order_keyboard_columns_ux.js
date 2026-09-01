(() => {
    "use strict";

    const EDITABLE_ORDER_STATUSES = new Set(["Draft", "Pending Review", "Rejected"]);
    const CHECK_COLUMNS = [
        { field: "allow_rotation", labelAr: "تدوير", labelEn: "Rotate" },
        { field: "edge_width_top", labelAr: "عرض أعلى", labelEn: "Top" },
        { field: "edge_width_bottom", labelAr: "عرض أسفل", labelEn: "Bottom" },
        { field: "edge_long_right", labelAr: "طول يمين", labelEn: "Long R" },
        { field: "edge_long_left", labelAr: "طول يسار", labelEn: "Long L" },
    ];
    const EDGE_COLUMNS = CHECK_COLUMNS.slice(1);
    const ARROW_KEYS = new Set(["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"]);
    const NAV_SELECTOR = [
        "input.dco-fast-input[data-field]",
        "select.dco-fast-select[data-field]",
        "button.dco-check-toggle[data-check-field]",
    ].join(",");

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
        return frm.doc.docstatus === 0 && EDITABLE_ORDER_STATUSES.has(frm.doc.status || "Draft");
    }

    function installStyles() {
        if (document.getElementById("dco-keyboard-columns-css")) return;
        $("head").append(`
            <style id="dco-keyboard-columns-css">
                .dco-fast-table th.dco-col-rotate,
                .dco-fast-table th.dco-col-edges { padding:5px 4px !important; }
                .dco-column-header-select {
                    display:flex; flex-direction:column; align-items:center; justify-content:center;
                    gap:4px; min-height:48px; font-size:11px; line-height:1.15;
                }
                .dco-edge-header-grid {
                    display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:4px;
                    align-items:stretch; width:100%; min-height:48px;
                }
                .dco-edge-header-item {
                    display:flex; flex-direction:column; align-items:center; justify-content:center;
                    gap:4px; min-width:0; font-size:10px; line-height:1.1; white-space:normal;
                }
                .dco-column-select-all {
                    display:inline-flex; align-items:center; justify-content:center; gap:4px;
                    cursor:pointer; user-select:none; font-size:10px; font-weight:700;
                    color:var(--text-muted,#6c7680); margin:0;
                }
                .dco-column-select-all input {
                    width:16px; height:16px; margin:0; cursor:pointer;
                    accent-color:var(--primary,#2490ef);
                }
                .dco-column-select-all input:disabled { cursor:not-allowed; opacity:.5; }
                .dco-fast-table input.dco-fast-input[data-field]:focus-visible,
                .dco-fast-table select.dco-fast-select[data-field]:focus-visible,
                .dco-fast-table button.dco-check-toggle[data-check-field]:focus-visible {
                    outline:2px solid var(--primary,#2490ef) !important;
                    outline-offset:1px;
                    box-shadow:0 0 0 3px rgba(36,144,239,.13) !important;
                }
                .dco-arrow-nav-hint {
                    display:inline-flex; align-items:center; gap:5px; font-weight:700;
                    color:var(--text-muted,#6c7680);
                }
                .dco-arrow-nav-hint kbd { direction:ltr; }
            </style>
        `);
    }

    function rowByName(frm, name) {
        return (frm.doc.pieces || []).find(row => row.name === name) || null;
    }

    function num(value) {
        if (value === null || value === undefined || value === "") return 0;
        return Number(String(value).replace(",", ".")) || 0;
    }

    function updateCalculatedCells(tr, row) {
        if (!tr || !row) return;
        const quantity = Math.max(0, num(row.qty));
        const area = (num(row.width_cm) * num(row.length_cm) * quantity) / 10000;
        const longSides = Number(Boolean(row.edge_long_right)) + Number(Boolean(row.edge_long_left));
        const widthSides = Number(Boolean(row.edge_width_top)) + Number(Boolean(row.edge_width_bottom));
        const edgeMeters = ((longSides * num(row.length_cm)) + (widthSides * num(row.width_cm))) * quantity / 100;
        const areaCell = tr.querySelector("[data-calc='area_m2']");
        const edgeCell = tr.querySelector("[data-calc='edge_meters']");
        if (areaCell) areaCell.textContent = area.toFixed(3);
        if (edgeCell) edgeCell.textContent = edgeMeters.toFixed(3);
    }

    function controlKey(control) {
        if (!control) return "";
        if (control.matches("[data-check-field]")) return `check:${control.dataset.checkField}`;
        if (control.matches("[data-field]")) return `field:${control.dataset.field}`;
        return "";
    }

    function controlForKey(tr, key) {
        if (!tr || !key) return null;
        if (key.startsWith("check:")) {
            const field = CSS.escape(key.slice(6));
            return tr.querySelector(`button.dco-check-toggle[data-check-field="${field}"]:not(:disabled)`);
        }
        if (key.startsWith("field:")) {
            const field = CSS.escape(key.slice(6));
            return tr.querySelector(`[data-field="${field}"]:not(:disabled)`);
        }
        return null;
    }

    function visibleControls(tr) {
        return [...tr.querySelectorAll(NAV_SELECTOR)]
            .filter(control => !control.disabled && control.getClientRects().length)
            .sort((a, b) => {
                const ar = a.getBoundingClientRect();
                const br = b.getBoundingClientRect();
                return (ar.left + ar.width / 2) - (br.left + br.width / 2);
            });
    }

    function focusControl(control) {
        if (!control) return false;
        control.focus({ preventScroll: true });
        if (control.matches("input.dco-fast-input") && typeof control.select === "function") {
            control.select();
        }
        control.scrollIntoView({ block: "nearest", inline: "nearest" });
        return document.activeElement === control;
    }

    function adjacentRow(tr, direction) {
        let row = direction < 0 ? tr.previousElementSibling : tr.nextElementSibling;
        while (row && !row.matches("tr[data-row-name]")) {
            row = direction < 0 ? row.previousElementSibling : row.nextElementSibling;
        }
        return row;
    }

    function moveByArrow(event, control) {
        const tr = control.closest("tr[data-row-name]");
        if (!tr) return false;

        if (event.key === "ArrowUp" || event.key === "ArrowDown") {
            const destinationRow = adjacentRow(tr, event.key === "ArrowUp" ? -1 : 1);
            const destination = controlForKey(destinationRow, controlKey(control));
            return focusControl(destination);
        }

        const controls = visibleControls(tr);
        const index = controls.indexOf(control);
        if (index < 0) return false;
        const destinationIndex = event.key === "ArrowLeft" ? index - 1 : index + 1;
        return focusControl(controls[destinationIndex]);
    }

    function actualRows(root) {
        return [...root.querySelectorAll(".dco-fast-table tbody tr[data-row-name]:not(.dco-virtual-row)")];
    }

    function setVisibleToggle(button, checked) {
        if (!button) return;
        button.classList.toggle("is-checked", checked);
        button.setAttribute("aria-pressed", checked ? "true" : "false");
        const mark = button.querySelector(".dco-check-mark");
        if (mark) mark.textContent = checked ? "✓" : "";
    }

    function checkboxForField(root, fieldname) {
        return root.querySelector(`.dco-column-select-all-input[data-column-field="${CSS.escape(fieldname)}"]`);
    }

    function refreshHeaderState(frm, root, fieldname) {
        const checkbox = checkboxForField(root, fieldname);
        if (!checkbox) return;
        const rows = actualRows(root);
        const values = rows.map(tr => {
            const row = rowByName(frm, tr.dataset.rowName || "");
            return Boolean(row && row[fieldname]);
        });
        const checkedCount = values.filter(Boolean).length;
        checkbox.disabled = rows.length === 0 || !isEditable(frm);
        checkbox.checked = values.length > 0 && checkedCount === values.length;
        checkbox.indeterminate = checkedCount > 0 && checkedCount < values.length;
        checkbox.title = checkbox.checked
            ? (isArabic() ? "إلغاء تحديد الكل" : "Clear all")
            : (isArabic() ? "تحديد الكل" : "Select all");
    }

    function refreshAllHeaderStates(frm, root) {
        CHECK_COLUMNS.forEach(column => refreshHeaderState(frm, root, column.field));
    }

    function headerCheckbox(fieldname) {
        return `
            <label class="dco-column-select-all" title="${isArabic() ? "تحديد الكل" : "Select all"}">
                <input type="checkbox" class="dco-column-select-all-input" data-column-field="${fieldname}">
                <span>${isArabic() ? "الكل" : "All"}</span>
            </label>`;
    }

    function decorateHeaders(frm, root) {
        const table = root.querySelector(".dco-fast-table");
        if (!table) return;

        const rotate = table.querySelector("thead th.dco-col-rotate");
        if (rotate && rotate.dataset.columnUxReady !== "1") {
            rotate.dataset.columnUxReady = "1";
            rotate.innerHTML = `
                <div class="dco-column-header-select">
                    <span>${isArabic() ? "تدوير" : "Rotate"}</span>
                    ${headerCheckbox("allow_rotation")}
                </div>`;
        }

        const edges = table.querySelector("thead th.dco-col-edges");
        if (edges && edges.dataset.columnUxReady !== "1") {
            edges.dataset.columnUxReady = "1";
            edges.innerHTML = `
                <div class="dco-edge-header-grid">
                    ${EDGE_COLUMNS.map(column => `
                        <div class="dco-edge-header-item">
                            <span>${isArabic() ? column.labelAr : column.labelEn}</span>
                            ${headerCheckbox(column.field)}
                        </div>`).join("")}
                </div>`;
        }

        const help = root.querySelector(".dco-fast-help");
        if (help && !help.querySelector(".dco-arrow-nav-hint")) {
            help.insertAdjacentHTML("beforeend", `
                <span class="dco-arrow-nav-hint">
                    <kbd>← ↑ ↓ →</kbd>
                    <span>${isArabic() ? "للتنقل بين الخلايا" : "move between cells"}</span>
                </span>`);
        }
        refreshAllHeaderStates(frm, root);
    }

    function applyColumnToAll(frm, root, fieldname, targetValue) {
        if (!isEditable(frm)) return;
        const changedRows = [];
        actualRows(root).forEach(tr => {
            const row = rowByName(frm, tr.dataset.rowName || "");
            if (!row || Boolean(row[fieldname]) === targetValue) return;
            row[fieldname] = targetValue ? 1 : 0;
            changedRows.push(row);
            setVisibleToggle(tr.querySelector(`button.dco-check-toggle[data-check-field="${CSS.escape(fieldname)}"]`), targetValue);
            updateCalculatedCells(tr, row);
        });

        if (!changedRows.length) {
            refreshHeaderState(frm, root, fieldname);
            return;
        }

        frm.dirty();
        refreshHeaderState(frm, root, fieldname);

        // Keep the visual operation instantaneous, then run existing child-field
        // recalculation handlers asynchronously without changing the established focus flow.
        window.setTimeout(() => {
            Promise.allSettled(changedRows.map(row =>
                Promise.resolve(frm.script_manager.trigger(fieldname, row.doctype, row.name))
            )).finally(() => refreshAllHeaderStates(frm, root));
        }, 0);
    }

    function observeRows(frm, root) {
        const tbody = root.querySelector(".dco-fast-table tbody");
        if (!tbody || root._dcoKeyboardObservedBody === tbody) return;
        if (root._dcoKeyboardColumnsObserver) root._dcoKeyboardColumnsObserver.disconnect();

        const observer = new MutationObserver(() => {
            requestAnimationFrame(() => {
                decorateHeaders(frm, root);
                refreshAllHeaderStates(frm, root);
            });
        });
        observer.observe(tbody, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ["class", "data-row-name"],
        });
        root._dcoKeyboardColumnsObserver = observer;
        root._dcoKeyboardObservedBody = tbody;
    }

    function bind(frm, root) {
        if (root._dcoKeyboardColumnsBound) return;
        root._dcoKeyboardColumnsBound = true;

        root.addEventListener("keydown", event => {
            if (!ARROW_KEYS.has(event.key) || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
            const control = event.target.closest(NAV_SELECTOR);
            if (!control || !root.contains(control) || !control.closest("tbody")) return;

            // Prevent native number-input increment/decrement. Tab and Enter are
            // intentionally untouched and continue to use the existing workflow.
            event.preventDefault();
            event.stopPropagation();
            moveByArrow(event, control);
        }, true);

        root.addEventListener("change", event => {
            const checkbox = event.target.closest(".dco-column-select-all-input[data-column-field]");
            if (!checkbox || !root.contains(checkbox)) return;
            event.preventDefault();
            event.stopPropagation();
            if (!isEditable(frm)) {
                refreshAllHeaderStates(frm, root);
                return;
            }
            const fieldname = checkbox.dataset.columnField;
            const rows = actualRows(root);
            const allChecked = rows.length > 0 && rows.every(tr => {
                const row = rowByName(frm, tr.dataset.rowName || "");
                return Boolean(row && row[fieldname]);
            });
            applyColumnToAll(frm, root, fieldname, !allChecked);
        }, true);
    }

    function install(frm) {
        installStyles();
        const field = frm.fields_dict.pieces_fast_entry;
        if (!field || !field.$wrapper) return;
        const root = field.$wrapper.get(0);
        if (!root) return;
        bind(frm, root);
        decorateHeaders(frm, root);
        observeRows(frm, root);
    }

    function scheduleInstall(frm, delays = []) {
        const lifecycle = window.AlmdinaMeasurementLifecycle;
        if (!lifecycle) {
            install(frm);
            requestAnimationFrame(() => install(frm));
            delays.forEach(delay => setTimeout(() => install(frm), delay));
            return;
        }
        lifecycle.schedule(
            frm,
            "keyboard-columns",
            () => install(frm),
            { delays }
        );
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) {
            scheduleInstall(frm);
        },
        refresh(frm) {
            scheduleInstall(frm, [250]);
        },
    });

    const measurementLifecycle = window.AlmdinaMeasurementLifecycle;
    if (measurementLifecycle && typeof measurementLifecycle.registerFeature === "function") {
        measurementLifecycle.registerFeature("keyboard-columns", install);
    }
})();
