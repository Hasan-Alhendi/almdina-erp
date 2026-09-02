(() => {
    "use strict";

    if (window.AlmdinaExtraDoorAddonsUX) return;

    const TYPE = "Extra";
    const PIECE_TYPES = Object.freeze([
        Object.freeze({ value: "Regular", labelAr: "عادية", labelEn: "Regular" }),
        Object.freeze({ value: "Special", labelAr: "خاصة", labelEn: "Special" }),
        Object.freeze({ value: "Clipped Corner", labelAr: "زاوية", labelEn: "Clipped corner" }),
        Object.freeze({ value: "L-Shaped Corner", labelAr: "زاوية L", labelEn: "L-shaped corner" }),
        Object.freeze({ value: TYPE, labelAr: "Extra", labelEn: "Extra" }),
    ]);
    const FIELDS = Object.freeze([
        Object.freeze({
            fieldname: "extra_double",
            labelAr: "دبل قشاط",
            labelEn: "Double Edge Banding",
        }),
        Object.freeze({
            fieldname: "extra_full_door_double",
            labelAr: "دبل كامل الدرفة",
            labelEn: "Full Door Double",
        }),
        Object.freeze({ fieldname: "extra_liner", labelAr: "لاينر", labelEn: "Liner" }),
        Object.freeze({
            fieldname: "extra_back_groove",
            labelAr: "فرزة ظهر",
            labelEn: "Back Groove",
        }),
        Object.freeze({
            fieldname: "extra_recessed_handle_cutout",
            labelAr: "حفر مسكة غطس",
            labelEn: "Recessed handle cutout",
        }),
    ]);
    const CLEANUP_KEY = "extra-door-addons-surface";

    function isArabic() {
        const language = String(
            (frappe.boot && frappe.boot.lang)
            || document.documentElement.lang
            || ""
        ).toLowerCase();
        return language === "ar" || language.startsWith("ar-");
    }

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function cssEscape(value) {
        if (window.CSS && typeof window.CSS.escape === "function") {
            return window.CSS.escape(value);
        }
        return String(value || "").replace(/["\\]/g, "\\$&");
    }

    function pieceTypeDefinition(value) {
        return PIECE_TYPES.find(item => item.value === value) || PIECE_TYPES[0];
    }

    function pieceTypeLabel(value) {
        const item = pieceTypeDefinition(value);
        return isArabic() ? item.labelAr : item.labelEn;
    }

    function selectedFields(row) {
        return FIELDS.filter(item => Boolean(Number(row && row[item.fieldname] || 0)));
    }

    function physicalCutQuantity(row) {
        const qty = Math.max(0, Math.floor(Number(row && row.qty || 0)));
        if (!qty) return 0;
        return Number(row && row.extra_full_door_double) ? qty * 2 : qty;
    }

    function renderSelectedAddons(row) {
        if (!row || (row.piece_type || "Regular") !== TYPE) return "";
        const selected = selectedFields(row);
        if (!selected.length) {
            return `<span class="dco-extra-required">${isArabic() ? "اختر إضافة واحدة على الأقل" : "Choose at least one add-on"}</span>`;
        }
        const labels = selected.map(item => isArabic() ? item.labelAr : item.labelEn);
        return `<span class="dco-extra-selection-summary">${esc(labels.join("، "))}</span>`;
    }

    function renderExtraOpenButton(row, editable = true) {
        if (!row || (row.piece_type || "Regular") !== TYPE) return "";
        const selectedCount = selectedFields(row).length;
        const disabled = editable ? "" : "disabled";
        return `<button type="button" class="dco-extra-open-button" aria-haspopup="menu" aria-expanded="false" aria-label="${isArabic() ? "تعديل إضافات Extra" : "Edit Extra add-ons"}" title="${isArabic() ? "تعديل إضافات Extra" : "Edit Extra add-ons"}" ${disabled}>
                    ${selectedCount ? `<b class="dco-extra-open-count">${selectedCount}</b>` : ""}
                    <span aria-hidden="true">${isArabic() ? "‹" : "›"}</span>
                </button>`;
    }

    function renderTypePicker(row, options = {}) {
        const pieceType = (row && row.piece_type) || "Regular";
        const editable = options.editable === true;
        const disabled = editable ? "" : "disabled";
        const typeOptions = PIECE_TYPES.map(item => {
            const label = isArabic() ? item.labelAr : item.labelEn;
            return `<option value="${esc(item.value)}" ${pieceType === item.value ? "selected" : ""}>${esc(label)}</option>`;
        }).join("");
        return `
            <div class="dco-piece-type-native" data-piece-type="${esc(pieceType)}">
                <select class="dco-fast-select dco-piece-type-select" data-field="piece_type" aria-label="${isArabic() ? "نوع الدرفة" : "Piece type"}" ${disabled}>
                    ${typeOptions}
                </select>
                ${renderExtraOpenButton(row, editable)}
                ${renderSelectedAddons(row)}
            </div>
        `;
    }

    function renderSubmenu(row) {
        const selected = new Set(selectedFields(row).map(item => item.fieldname));
        return `
            <div class="dco-extra-submenu-head">
                <b>${isArabic() ? "إضافات Extra" : "Extra add-ons"}</b>
                <span>${isArabic() ? "يمكن اختيار أكثر من خيار" : "Choose one or more"}</span>
            </div>
            <div class="dco-extra-options" role="group">
                ${FIELDS.map(item => {
                    const label = isArabic() ? item.labelAr : item.labelEn;
                    return `
                        <label>
                            <input type="checkbox" data-extra-field="${item.fieldname}" ${selected.has(item.fieldname) ? "checked" : ""}>
                            <span>${esc(label)}</span>
                        </label>
                    `;
                }).join("")}
            </div>
            <div class="dco-extra-error" role="status" aria-live="polite"></div>
        `;
    }

    function notesCueHtml(row) {
        if (!row || (row.piece_type || "Regular") !== TYPE || String(row.notes || "").trim()) return "";
        return `<span class="dco-extra-notes-cue" role="status">${isArabic() ? "اكتب تفاصيل التنفيذ قبل الحفظ" : "Add implementation details before saving"}</span>`;
    }

    function rowByName(frm, name) {
        return (frm && frm.doc && frm.doc.pieces || []).find(row => row && row.name === name) || null;
    }

    function rootFor(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.pieces_fast_entry;
        return field && field.$wrapper ? field.$wrapper.get(0) : null;
    }

    function triggerFields(frm, row, changed) {
        changed.forEach(fieldname => {
            Promise.resolve(
                frm.script_manager.trigger(fieldname, row.doctype, row.name)
            ).catch(error => console.error("Extra add-on field trigger failed", error));
        });
    }

    function ensureNativeTypeShell(typeCell) {
        if (!typeCell) return null;
        let shell = typeCell.querySelector(".dco-piece-type-native");
        let select = shell && shell.querySelector("select.dco-piece-type-select[data-field='piece_type']");
        if (shell && select) return { shell, select };

        select = typeCell.querySelector("select.dco-fast-select[data-field='piece_type']");
        if (!select) return null;
        select.classList.add("dco-piece-type-select");

        shell = document.createElement("div");
        shell.className = "dco-piece-type-native";
        select.replaceWith(shell);
        shell.appendChild(select);
        return { shell, select };
    }

    function syncTypeCell(frm, tableRow, typeCell, row, options = {}) {
        const native = ensureNativeTypeShell(typeCell);
        if (!native) {
            typeCell.innerHTML = renderTypePicker(row, {
                editable: options.editable !== false,
                virtual: Boolean(options.virtual),
            });
            return;
        }

        const pieceType = (row && row.piece_type) || "Regular";
        const editable = options.editable !== false;
        native.shell.dataset.pieceType = pieceType;
        native.select.value = pieceType;
        native.select.disabled = !editable;
        native.shell.querySelectorAll(
            ".dco-extra-open-button,.dco-extra-selection-summary,.dco-extra-required"
        ).forEach(node => node.remove());

        if (pieceType !== TYPE) return;
        native.select.insertAdjacentHTML("afterend", renderExtraOpenButton(row, editable));
        native.shell.insertAdjacentHTML("beforeend", renderSelectedAddons(row));

        const active = frm && frm.__almdinaExtraAddonsSurface;
        if (active && active.tableRow === tableRow) {
            const button = native.shell.querySelector(".dco-extra-open-button");
            if (button) button.setAttribute("aria-expanded", "true");
        }
    }

    function syncRowPresentation(frm, tableRow, row, options = {}) {
        if (!tableRow || !row) return false;
        tableRow.classList.toggle("dco-extra-row", (row.piece_type || "Regular") === TYPE);
        const typeCell = tableRow.querySelector(".dco-col-type");
        if (typeCell) syncTypeCell(frm, tableRow, typeCell, row, options);
        const notesCell = tableRow.querySelector(".dco-col-notes");
        if (notesCell) {
            notesCell.querySelectorAll(".dco-extra-notes-cue").forEach(cue => cue.remove());
            const cueHtml = notesCueHtml(row);
            if (cueHtml) notesCell.insertAdjacentHTML("beforeend", cueHtml);
        }
        return true;
    }

    function focusNotes(frm, row) {
        const context = window.AlmdinaDocumentContext;
        const run = () => {
            const root = rootFor(frm);
            if (!root) return;
            const selector = `tr[data-row-name="${cssEscape(row.name)}"] input[data-field="notes"]`;
            const input = root.querySelector(selector);
            if (!input) return;
            input.focus({ preventScroll: true });
            input.scrollIntoView({ block: "nearest", inline: "nearest" });
        };
        if (context && typeof context.scheduleFrame === "function") {
            context.scheduleFrame(frm, `extra-notes-focus:${row.name}`, run);
        } else {
            window.requestAnimationFrame(run);
        }
    }

    function focusTypeSelect(frm, row) {
        const context = window.AlmdinaDocumentContext;
        const run = () => {
            const root = rootFor(frm);
            if (!root) return;
            const select = root.querySelector(
                `tr[data-row-name="${cssEscape(row.name)}"] select.dco-piece-type-select`
            );
            if (!select) return;
            select.focus({ preventScroll: true });
            select.scrollIntoView({ block: "nearest", inline: "nearest" });
        };
        if (context && typeof context.scheduleFrame === "function") {
            context.scheduleFrame(frm, `extra-type-focus:${row.name}`, run);
        } else {
            window.requestAnimationFrame(run);
        }
    }

    function closeSurface(frm, options = {}) {
        const active = frm && frm.__almdinaExtraAddonsSurface;
        if (!active) return false;
        frm.__almdinaExtraAddonsSurface = null;
        const currentButton = active.tableRow && active.tableRow.querySelector(".dco-extra-open-button");
        if (currentButton) currentButton.setAttribute("aria-expanded", "false");
        active.surface.remove();
        document.removeEventListener("pointerdown", active.onOutside, true);
        document.removeEventListener("keydown", active.onDocumentKeydown, true);
        document.removeEventListener("scroll", active.onScroll, true);
        window.removeEventListener("resize", active.onResize);
        if (options.restoreFocus && currentButton && currentButton.isConnected) {
            currentButton.focus({ preventScroll: true });
        }
        return true;
    }

    function resolveAnchor(active) {
        if (!active.tableRow || !active.tableRow.isConnected) return null;
        return active.tableRow.querySelector(".dco-extra-open-button")
            || active.tableRow.querySelector("select.dco-piece-type-select");
    }

    function placeSurface(active) {
        const anchor = resolveAnchor(active);
        if (!anchor) {
            closeSurface(active.frm);
            return;
        }
        active.anchor = anchor;
        const rect = anchor.getBoundingClientRect();
        const surface = active.surface;
        const margin = 10;
        const gap = 7;
        const width = Math.min(236, window.innerWidth - (margin * 2));
        const height = Math.min(surface.scrollHeight || 210, window.innerHeight - (margin * 2));
        const leftSide = rect.left - width - gap;
        const rightSide = rect.right + gap;
        let left;
        if (isArabic() && leftSide >= margin) left = leftSide;
        else if (!isArabic() && rightSide + width <= window.innerWidth - margin) left = rightSide;
        else if (rightSide + width <= window.innerWidth - margin) left = rightSide;
        else if (leftSide >= margin) left = leftSide;
        else left = Math.min(Math.max(margin, rect.left), window.innerWidth - width - margin);

        let top = Math.max(margin, rect.top);
        if (top + height > window.innerHeight - margin) {
            top = Math.max(margin, window.innerHeight - height - margin);
        }
        surface.style.setProperty("--dco-extra-top", `${Math.round(top)}px`);
        surface.style.setProperty("--dco-extra-left", `${Math.round(left)}px`);
        surface.style.setProperty("--dco-extra-width", `${Math.round(width)}px`);
    }

    function refreshPieceTypeVisual(frm, tableRow, row) {
        const performance = window.AlmdinaTablePerformanceUX;
        if (performance && typeof performance.refreshPieceTypeVisual === "function") {
            performance.refreshPieceTypeVisual(frm, tableRow, row);
            return;
        }
        syncRowPresentation(frm, tableRow, row, { editable: true });
    }

    function setAddon(frm, tableRow, row, fieldname, enabled) {
        if (!FIELDS.some(item => item.fieldname === fieldname)) return false;
        const value = enabled ? 1 : 0;
        if (Number(row[fieldname] || 0) === value) return false;
        row[fieldname] = value;
        frm.dirty();
        triggerFields(frm, row, [fieldname]);
        refreshPieceTypeVisual(frm, tableRow, row);
        return true;
    }

    function openSurface(frm, row, tableRow, options = {}) {
        if (!frm || !row || !tableRow || (row.piece_type || "Regular") !== TYPE) return false;
        closeSurface(frm);

        const surface = document.createElement("div");
        surface.className = "dco-extra-submenu-flyout";
        surface.setAttribute("role", "menu");
        surface.setAttribute("aria-label", isArabic() ? "إضافات Extra" : "Extra add-ons");
        surface.innerHTML = renderSubmenu(row);
        document.body.appendChild(surface);

        const active = {
            frm,
            rowName: row.name,
            tableRow,
            surface,
            anchor: null,
            onOutside: null,
            onDocumentKeydown: null,
            onResize: null,
            onScroll: null,
        };
        active.onOutside = event => {
            const anchor = resolveAnchor(active);
            if (surface.contains(event.target) || (anchor && anchor.contains(event.target))) return;
            closeSurface(frm);
        };
        active.onDocumentKeydown = event => {
            if (event.key !== "Escape") return;
            event.preventDefault();
            closeSurface(frm, { restoreFocus: true });
        };
        active.onResize = () => placeSurface(active);
        active.onScroll = () => placeSurface(active);
        frm.__almdinaExtraAddonsSurface = active;

        const button = tableRow.querySelector(".dco-extra-open-button");
        if (button) button.setAttribute("aria-expanded", "true");
        document.addEventListener("pointerdown", active.onOutside, true);
        document.addEventListener("keydown", active.onDocumentKeydown, true);
        document.addEventListener("scroll", active.onScroll, true);
        window.addEventListener("resize", active.onResize);

        surface.addEventListener("change", event => {
            const input = event.target.closest("input[data-extra-field]");
            if (!input || !surface.contains(input)) return;
            const currentRow = rowByName(frm, active.rowName);
            if (!currentRow || (currentRow.piece_type || "Regular") !== TYPE) {
                closeSurface(frm);
                return;
            }
            setAddon(frm, tableRow, currentRow, input.dataset.extraField, input.checked);
            const error = surface.querySelector(".dco-extra-error");
            if (error) {
                error.textContent = selectedFields(currentRow).length
                    ? ""
                    : (isArabic() ? "اختر إضافة واحدة على الأقل." : "Choose at least one add-on.");
            }
            placeSurface(active);
        });

        placeSurface(active);
        if (options.focusFirst) {
            const first = surface.querySelector("input[data-extra-field]");
            if (first) first.focus({ preventScroll: true });
        }
        return true;
    }

    function scheduleOpenForSelection(frm, tableRow) {
        const context = window.AlmdinaDocumentContext;
        const run = () => {
            if (!tableRow || !tableRow.isConnected) return;
            const row = rowByName(frm, tableRow.dataset.rowName || "");
            if (!row || (row.piece_type || "Regular") !== TYPE) return;
            openSurface(frm, row, tableRow, { focusFirst: true });
        };
        if (context && typeof context.scheduleFrame === "function") {
            const rowName = tableRow && tableRow.dataset ? tableRow.dataset.rowName : "row";
            context.scheduleFrame(frm, `extra-open:${rowName}`, run);
        } else {
            window.requestAnimationFrame(run);
        }
    }

    function reconcilePieceType(frm, row) {
        if (!row || (row.piece_type || "Regular") === TYPE) return false;
        const changed = [];
        FIELDS.forEach(item => {
            if (!Number(row[item.fieldname] || 0)) return;
            row[item.fieldname] = 0;
            changed.push(item.fieldname);
        });
        if (!changed.length) return false;
        frm.dirty();
        triggerFields(frm, row, changed);
        frappe.show_alert({
            message: isArabic()
                ? "تم مسح إضافات Extra بعد تغيير نوع الدرفة."
                : "Extra add-ons were cleared after changing the door type.",
            indicator: "orange",
        });
        return true;
    }

    function bindTable(frm, root) {
        if (!frm || !root) return false;
        root.__almdinaExtraAddonsForm = frm;

        const formWrapper = frm.wrapper || root.parentElement || root;
        formWrapper.__almdinaExtraAddonsForm = frm;
        if (!formWrapper.__almdinaExtraAddonsSelectCaptureBound) {
            formWrapper.__almdinaExtraAddonsSelectCaptureBound = true;
            formWrapper.addEventListener("change", event => {
                const select = event.target.closest("select.dco-piece-type-select[data-field='piece_type']");
                if (!select) return;
                const currentFrm = formWrapper.__almdinaExtraAddonsForm;
                const currentRoot = rootFor(currentFrm);
                if (!currentRoot || !currentRoot.contains(select)) return;
                const tableRow = select.closest("tr[data-row-name]");
                if (!tableRow) return;
                if (select.value === TYPE) {
                    scheduleOpenForSelection(currentFrm, tableRow);
                    return;
                }
                const active = currentFrm.__almdinaExtraAddonsSurface;
                if (active && active.tableRow === tableRow) closeSurface(currentFrm);
            }, true);
        }

        if (!root.__almdinaExtraAddonsBound) {
            root.__almdinaExtraAddonsBound = true;
            root.addEventListener("click", event => {
                const button = event.target.closest(".dco-extra-open-button");
                if (!button || !root.contains(button) || button.disabled) return;
                event.preventDefault();
                event.stopPropagation();
                const currentFrm = root.__almdinaExtraAddonsForm;
                const tableRow = button.closest("tr[data-row-name]");
                const row = rowByName(currentFrm, tableRow && tableRow.dataset.rowName);
                if (!row || (row.piece_type || "Regular") !== TYPE) return;
                openSurface(currentFrm, row, tableRow, { focusFirst: true });
            });
        }

        const context = window.AlmdinaDocumentContext;
        if (context && typeof context.registerCleanup === "function") {
            context.registerCleanup(frm, CLEANUP_KEY, () => closeSurface(frm));
        }
        return true;
    }

    function validateRows(frm) {
        const invalid = (frm.doc.pieces || []).find(row => {
            if ((row.piece_type || "Regular") !== TYPE) return false;
            return !selectedFields(row).length || !String(row.notes || "").trim();
        });
        if (!invalid) return true;
        const missingAddon = !selectedFields(invalid).length;
        const performance = window.AlmdinaTablePerformanceUX;
        if (performance && typeof performance.refreshAll === "function") performance.refreshAll(frm);
        if (missingAddon) focusTypeSelect(frm, invalid);
        else focusNotes(frm, invalid);
        frappe.throw(
            isArabic()
                ? "كل درفة Extra تحتاج إضافة واحدة على الأقل وملاحظات تنفيذ."
                : "Every Extra door requires at least one add-on and implementation notes."
        );
        return false;
    }

    frappe.ui.form.on("Door Cutting Order", {
        validate(frm) { validateRows(frm); },
    });

    window.AlmdinaExtraDoorAddonsUX = Object.freeze({
        TYPE,
        PIECE_TYPES,
        FIELDS,
        selectedFields,
        physicalCutQuantity,
        pieceTypeLabel,
        renderTypePicker,
        renderSubmenu,
        notesCueHtml,
        syncRowPresentation,
        reconcilePieceType,
        bindTable,
        validateRows,
        closeSurface,
        openSurface,
    });
})();
