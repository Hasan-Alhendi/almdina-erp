(() => {
    "use strict";

    if (window.AlmdinaExtraDoorAddonsUX) return;

    const TYPE = "Extra";
    const PIECE_TYPES = Object.freeze([
        Object.freeze({ value: "Regular", labelAr: "عادية", labelEn: "Regular" }),
        Object.freeze({ value: "Clipped Corner", labelAr: "زاوية مقصوصة", labelEn: "Clipped corner" }),
        Object.freeze({ value: "Special", labelAr: "خاصة", labelEn: "Special" }),
        Object.freeze({ value: TYPE, labelAr: "إضافية", labelEn: "Extra", hasSubmenu: true }),
    ]);
    const FIELDS = Object.freeze([
        Object.freeze({ fieldname: "extra_liner", labelAr: "لاينر", labelEn: "Liner" }),
        Object.freeze({ fieldname: "extra_double", labelAr: "دبل", labelEn: "Double" }),
        Object.freeze({
            fieldname: "extra_recessed_handle_cutout",
            labelAr: "مسكة غطس",
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

    function renderSelectedAddons(row) {
        if (!row || (row.piece_type || "Regular") !== TYPE) return "";
        const selected = selectedFields(row);
        if (!selected.length) {
            return `<span class="dco-extra-required">${isArabic() ? "اختر إضافة واحدة على الأقل" : "Choose at least one add-on"}</span>`;
        }
        return `
            <span class="dco-extra-chip-list">
                ${selected.map(item => `<span>${esc(isArabic() ? item.labelAr : item.labelEn)}</span>`).join("")}
            </span>
        `;
    }

    function renderTypePicker(row, options = {}) {
        const pieceType = (row && row.piece_type) || "Regular";
        const selectedCount = pieceType === TYPE ? selectedFields(row).length : 0;
        const disabled = options.editable ? "" : "disabled";
        const typeLabel = pieceTypeLabel(pieceType);
        const accessibleLabel = isArabic()
            ? `نوع الدرفة: ${typeLabel}`
            : `Piece type: ${typeLabel}`;
        return `
            <div class="dco-piece-type-picker" data-piece-type="${esc(pieceType)}">
                <button type="button" class="dco-piece-type-trigger" aria-haspopup="menu" aria-expanded="false" aria-label="${esc(accessibleLabel)}" ${disabled}>
                    <span class="dco-piece-type-label">${esc(typeLabel)}</span>
                    ${selectedCount ? `<b class="dco-piece-type-count" aria-label="${selectedCount}">${selectedCount}</b>` : ""}
                    <span class="dco-piece-type-chevron" aria-hidden="true">⌄</span>
                </button>
                ${renderSelectedAddons(row)}
            </div>
        `;
    }

    function renderMenu(row) {
        const currentType = (row && row.piece_type) || "Regular";
        const selected = new Set(selectedFields(row).map(item => item.fieldname));
        const submenuArrow = isArabic() ? "‹" : "›";
        return `
            <div class="dco-piece-type-menu" role="menu" aria-label="${isArabic() ? "نوع الدرفة" : "Piece type"}">
                <div class="dco-piece-type-menu-title">${isArabic() ? "نوع الدرفة" : "Piece type"}</div>
                ${PIECE_TYPES.map(item => {
                    const label = isArabic() ? item.labelAr : item.labelEn;
                    const selectedType = item.value === currentType;
                    return `
                        <button type="button" class="dco-piece-type-option ${item.hasSubmenu ? "has-submenu" : ""}" data-piece-type-option="${esc(item.value)}" role="menuitemradio" aria-checked="${selectedType ? "true" : "false"}" ${item.hasSubmenu ? 'aria-haspopup="menu" aria-expanded="false"' : ""}>
                            <span class="dco-piece-type-check" aria-hidden="true">${selectedType ? "✓" : ""}</span>
                            <span>${esc(label)}</span>
                            ${item.hasSubmenu ? `<span class="dco-piece-type-submenu-arrow" aria-hidden="true">${submenuArrow}</span>` : ""}
                        </button>
                    `;
                }).join("")}
            </div>
            <div class="dco-extra-submenu" role="menu" aria-label="${isArabic() ? "إضافات الدرفة" : "Door add-ons"}" aria-hidden="true">
                <div class="dco-extra-submenu-head">
                    <b>${isArabic() ? "إضافات الدرفة" : "Door add-ons"}</b>
                    <span>${isArabic() ? "يمكن اختيار أكثر من خيار" : "Choose one or more"}</span>
                </div>
                <div class="dco-extra-options">
                    ${FIELDS.map(item => {
                        const label = isArabic() ? item.labelAr : item.labelEn;
                        return `
                            <label>
                                <input type="checkbox" data-extra-field="${item.fieldname}" ${selected.has(item.fieldname) ? "checked" : ""}>
                                <span><b>${esc(label)}</b><small>${isArabic() ? "السعر لكل درفة × العدد" : "Price per door × quantity"}</small></span>
                            </label>
                        `;
                    }).join("")}
                </div>
                <div class="dco-extra-error" role="alert" aria-live="polite"></div>
                <div class="dco-extra-submenu-actions">
                    <button type="button" class="btn btn-default btn-sm dco-extra-cancel">${isArabic() ? "إلغاء" : "Cancel"}</button>
                    <button type="button" class="btn btn-primary btn-sm dco-extra-apply">${isArabic() ? "تطبيق" : "Apply"}</button>
                </div>
            </div>
        `;
    }

    function notesCueHtml(row) {
        if (!row || (row.piece_type || "Regular") !== TYPE || String(row.notes || "").trim()) return "";
        return `<span class="dco-extra-notes-cue" role="status">${isArabic() ? "اكتب تفاصيل التنفيذ قبل الحفظ" : "Add implementation details before saving"}</span>`;
    }

    function rowByName(frm, name) {
        return (frm && frm.doc && frm.doc.pieces || []).find(row => row && row.name === name) || null;
    }

    function triggerFields(frm, row, changed) {
        changed.forEach(fieldname => {
            Promise.resolve(
                frm.script_manager.trigger(fieldname, row.doctype, row.name)
            ).catch(error => console.error("Extra add-on field trigger failed", error));
        });
    }

    function syncRowPresentation(frm, tableRow, row, options = {}) {
        if (!tableRow || !row) return false;
        tableRow.classList.toggle("dco-extra-row", (row.piece_type || "Regular") === TYPE);
        const typeCell = tableRow.querySelector(".dco-col-type");
        if (typeCell) {
            typeCell.innerHTML = renderTypePicker(row, {
                editable: options.editable !== false,
                virtual: Boolean(options.virtual),
            });
        }
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
            const field = frm.fields_dict && frm.fields_dict.pieces_fast_entry;
            const root = field && field.$wrapper && field.$wrapper.get(0);
            if (!root) return;
            const escapedName = cssEscape(row.name);
            const selector = `tr[data-row-name="${escapedName}"] input[data-field="notes"]`;
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

    function focusTypeTrigger(frm, row) {
        const context = window.AlmdinaDocumentContext;
        const run = () => {
            const field = frm.fields_dict && frm.fields_dict.pieces_fast_entry;
            const root = field && field.$wrapper && field.$wrapper.get(0);
            if (!root) return;
            const escapedName = cssEscape(row.name);
            const trigger = root.querySelector(
                `tr[data-row-name="${escapedName}"] .dco-piece-type-trigger`
            );
            if (!trigger) return;
            trigger.focus({ preventScroll: true });
            trigger.scrollIntoView({ block: "nearest", inline: "nearest" });
        };
        if (context && typeof context.scheduleFrame === "function") {
            context.scheduleFrame(frm, `extra-trigger-focus:${row.name}`, run);
        } else {
            window.requestAnimationFrame(run);
        }
    }

    function closeSurface(frm, options = {}) {
        const active = frm && frm.__almdinaExtraAddonsSurface;
        if (!active) return false;
        frm.__almdinaExtraAddonsSurface = null;
        if (active.trigger && active.trigger.isConnected) {
            active.trigger.setAttribute("aria-expanded", "false");
        }
        active.surface.remove();
        document.removeEventListener("pointerdown", active.onOutside, true);
        document.removeEventListener("keydown", active.onDocumentKeydown, true);
        window.removeEventListener("resize", active.onResize);
        if (options.restoreFocus && active.trigger && active.trigger.isConnected) {
            active.trigger.focus({ preventScroll: true });
        }
        return true;
    }

    function placeSurface(active) {
        const { surface, trigger } = active;
        if (window.innerWidth <= 720) {
            surface.classList.remove("opens-left", "opens-right", "is-stacked");
            surface.style.removeProperty("--dco-piece-type-top");
            surface.style.removeProperty("--dco-piece-type-left");
            return;
        }

        const rect = trigger.getBoundingClientRect();
        const submenuOpen = surface.classList.contains("is-extra-open");
        const mainWidth = 224;
        const submenuWidth = 292;
        const gap = 8;
        const width = submenuOpen ? mainWidth + submenuWidth + gap : mainWidth;
        const margin = 12;
        const canFitSideBySide = submenuOpen && width <= window.innerWidth - (margin * 2);
        const spaceBefore = rect.right - margin;
        const spaceAfter = window.innerWidth - rect.left - margin;
        const opensLeft = canFitSideBySide && spaceBefore >= spaceAfter;
        const opensRight = canFitSideBySide && !opensLeft;
        surface.classList.toggle("opens-left", opensLeft);
        surface.classList.toggle("opens-right", opensRight);
        surface.classList.toggle("is-stacked", submenuOpen && !opensLeft && !opensRight);

        const actualWidth = surface.classList.contains("is-stacked")
            ? Math.min(Math.max(mainWidth, submenuWidth), window.innerWidth - (margin * 2))
            : width;
        let left;
        if (opensLeft) left = rect.right - actualWidth;
        else if (opensRight) left = rect.left;
        else left = Math.min(Math.max(margin, rect.right - actualWidth), window.innerWidth - actualWidth - margin);

        const height = Math.min(surface.scrollHeight || 420, window.innerHeight - (margin * 2));
        const below = rect.bottom + 7;
        const top = below + height <= window.innerHeight - margin
            ? below
            : Math.max(margin, rect.top - height - 7);
        surface.style.setProperty("--dco-piece-type-top", `${Math.round(top)}px`);
        surface.style.setProperty("--dco-piece-type-left", `${Math.round(left)}px`);
    }

    function setExtraSubmenu(active, open, options = {}) {
        const extraOption = active.surface.querySelector('[data-piece-type-option="Extra"]');
        const submenu = active.surface.querySelector(".dco-extra-submenu");
        active.surface.classList.toggle("is-extra-open", Boolean(open));
        if (extraOption) extraOption.setAttribute("aria-expanded", open ? "true" : "false");
        if (submenu) submenu.setAttribute("aria-hidden", open ? "false" : "true");
        placeSurface(active);
        if (open && options.focusFirst && submenu) {
            const first = submenu.querySelector("input[data-extra-field]");
            if (first) first.focus({ preventScroll: true });
        }
    }

    function commitPieceType(frm, tableRow, pieceType) {
        const performance = window.AlmdinaTablePerformanceUX;
        if (!performance || typeof performance.setPieceType !== "function") {
            throw new Error("AlmdinaTablePerformanceUX.setPieceType is required");
        }
        return performance.setPieceType(frm, tableRow, pieceType);
    }

    function refreshPieceTypeVisual(frm, tableRow, row) {
        const performance = window.AlmdinaTablePerformanceUX;
        if (performance && typeof performance.refreshPieceTypeVisual === "function") {
            performance.refreshPieceTypeVisual(frm, tableRow, row);
            return;
        }
        syncRowPresentation(frm, tableRow, row, { editable: true });
    }

    function applySelection(frm, row, chosen) {
        const changed = [];
        FIELDS.forEach(item => {
            const value = chosen.has(item.fieldname) ? 1 : 0;
            if (Number(row[item.fieldname] || 0) === value) return;
            row[item.fieldname] = value;
            changed.push(item.fieldname);
        });
        if (changed.length) {
            frm.dirty();
            triggerFields(frm, row, changed);
        }
        return changed;
    }

    function openSurface(frm, row, trigger, tableRow) {
        closeSurface(frm);
        const surface = document.createElement("div");
        surface.className = "dco-piece-type-flyout";
        surface.setAttribute("aria-label", isArabic() ? "اختيار نوع الدرفة وإضافاتها" : "Choose piece type and add-ons");
        surface.innerHTML = renderMenu(row);
        document.body.appendChild(surface);
        trigger.setAttribute("aria-expanded", "true");

        const onOutside = event => {
            if (surface.contains(event.target) || trigger.contains(event.target)) return;
            closeSurface(frm);
        };
        const onDocumentKeydown = event => {
            if (event.key !== "Escape") return;
            event.preventDefault();
            closeSurface(frm, { restoreFocus: true });
        };
        const active = {
            surface,
            trigger,
            tableRow,
            onOutside,
            onDocumentKeydown,
            onResize: null,
        };
        active.onResize = () => placeSurface(active);
        frm.__almdinaExtraAddonsSurface = active;
        document.addEventListener("pointerdown", onOutside, true);
        document.addEventListener("keydown", onDocumentKeydown, true);
        window.addEventListener("resize", active.onResize);

        surface.addEventListener("pointerover", event => {
            const option = event.target.closest("[data-piece-type-option]");
            if (!option || !surface.contains(option)) return;
            setExtraSubmenu(active, option.dataset.pieceTypeOption === TYPE);
        });
        surface.addEventListener("focusin", event => {
            const option = event.target.closest("[data-piece-type-option]");
            if (!option || !surface.contains(option)) return;
            setExtraSubmenu(active, option.dataset.pieceTypeOption === TYPE);
        });
        surface.addEventListener("change", event => {
            if (!event.target.matches("input[data-extra-field]")) return;
            const error = surface.querySelector(".dco-extra-error");
            if (error) error.textContent = "";
        });
        surface.addEventListener("keydown", event => {
            const option = event.target.closest("[data-piece-type-option]");
            if (!option) return;
            const options = [...surface.querySelectorAll("[data-piece-type-option]")];
            const index = options.indexOf(option);
            if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                event.preventDefault();
                const step = event.key === "ArrowDown" ? 1 : -1;
                options[(index + step + options.length) % options.length].focus({ preventScroll: true });
                return;
            }
            if (option.dataset.pieceTypeOption === TYPE && (event.key === "ArrowLeft" || event.key === "ArrowRight")) {
                event.preventDefault();
                setExtraSubmenu(active, true, { focusFirst: true });
            }
        });
        surface.addEventListener("click", event => {
            const typeOption = event.target.closest("[data-piece-type-option]");
            if (typeOption && surface.contains(typeOption)) {
                event.preventDefault();
                const nextType = typeOption.dataset.pieceTypeOption || "Regular";
                if (nextType === TYPE) {
                    setExtraSubmenu(active, true);
                    return;
                }
                closeSurface(frm);
                commitPieceType(frm, tableRow, nextType);
                return;
            }
            if (event.target.closest(".dco-extra-cancel")) {
                closeSurface(frm, { restoreFocus: true });
                return;
            }
            if (!event.target.closest(".dco-extra-apply")) return;
            const chosen = new Set(
                [...surface.querySelectorAll("input[data-extra-field]:checked")]
                    .map(input => input.dataset.extraField)
            );
            if (!chosen.size) {
                const error = surface.querySelector(".dco-extra-error");
                if (error) {
                    error.textContent = isArabic()
                        ? "اختر إضافة واحدة على الأقل."
                        : "Choose at least one add-on.";
                }
                const first = surface.querySelector("input[data-extra-field]");
                if (first) first.focus({ preventScroll: true });
                return;
            }

            closeSurface(frm);
            const currentRow = commitPieceType(frm, tableRow, TYPE);
            if (!currentRow) return;
            applySelection(frm, currentRow, chosen);
            refreshPieceTypeVisual(frm, tableRow, currentRow);
            if (!String(currentRow.notes || "").trim()) {
                frappe.show_alert({
                    message: isArabic()
                        ? "تم اختيار الإضافات — أكمل ملاحظات التنفيذ."
                        : "Add-ons selected — complete the implementation notes.",
                    indicator: "blue",
                });
                focusNotes(frm, currentRow);
            }
        });

        const currentType = (row && row.piece_type) || "Regular";
        if (currentType === TYPE) setExtraSubmenu(active, true);
        else placeSurface(active);
        const currentOption = surface.querySelector(`[data-piece-type-option="${cssEscape(currentType)}"]`)
            || surface.querySelector("[data-piece-type-option]");
        if (currentOption) currentOption.focus({ preventScroll: true });
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
        if (root.__almdinaExtraAddonsBound) return true;
        root.__almdinaExtraAddonsBound = true;
        root.addEventListener("click", event => {
            const trigger = event.target.closest(".dco-piece-type-trigger");
            if (!trigger || !root.contains(trigger) || trigger.disabled) return;
            event.preventDefault();
            event.stopPropagation();
            const currentFrm = root.__almdinaExtraAddonsForm;
            const tableRow = trigger.closest("tr[data-row-name]");
            const row = rowByName(currentFrm, tableRow && tableRow.dataset.rowName);
            openSurface(currentFrm, row, trigger, tableRow);
        });
        root.addEventListener("keydown", event => {
            const trigger = event.target.closest(".dco-piece-type-trigger");
            if (!trigger || !root.contains(trigger) || trigger.disabled || event.key !== "ArrowDown") return;
            event.preventDefault();
            const currentFrm = root.__almdinaExtraAddonsForm;
            const tableRow = trigger.closest("tr[data-row-name]");
            const row = rowByName(currentFrm, tableRow && tableRow.dataset.rowName);
            openSurface(currentFrm, row, trigger, tableRow);
        });
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
        if (missingAddon) focusTypeTrigger(frm, invalid);
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
        pieceTypeLabel,
        renderTypePicker,
        renderMenu,
        notesCueHtml,
        syncRowPresentation,
        reconcilePieceType,
        bindTable,
        validateRows,
        closeSurface,
    });
})();
