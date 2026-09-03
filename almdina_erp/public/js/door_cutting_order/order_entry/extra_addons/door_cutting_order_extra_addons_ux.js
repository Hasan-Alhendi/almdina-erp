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
    const HOVER_OPEN_MS = 40;
    const ROW_HOVER_OPEN_MS = 90;
    const HOVER_CLOSE_MS = 240;

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

    function prefersReducedMotion() {
        return Boolean(
            window.matchMedia
            && window.matchMedia("(prefers-reduced-motion: reduce)").matches
        );
    }

    function isMousePointer(event) {
        if (event.pointerType === "touch" || event.pointerType === "pen") return false;
        if (event.sourceCapabilities && event.sourceCapabilities.firesTouchEvents) return false;
        return !event.pointerType || event.pointerType === "mouse";
    }

    function hoverDelay(ms) {
        return prefersReducedMotion() ? 0 : ms;
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

    function renderTypeMenu(row) {
        const current = (row && row.piece_type) || "Regular";
        return PIECE_TYPES.map(item => {
            const label = isArabic() ? item.labelAr : item.labelEn;
            const isExtra = item.value === TYPE;
            const selected = current === item.value;
            const submenu = isExtra ? " dco-piece-type-has-submenu" : "";
            const selectedClass = selected ? " is-selected" : "";
            const arrow = isExtra
                ? `<span class="dco-piece-type-submenu-arrow" aria-hidden="true">${isArabic() ? "‹" : "›"}</span>`
                : "";
            const popup = isExtra ? ' aria-haspopup="menu" aria-expanded="false"' : "";
            return `<button type="button" role="menuitemradio" class="dco-piece-type-option${submenu}${selectedClass}" data-piece-type-option="${esc(item.value)}" aria-checked="${selected ? "true" : "false"}"${popup}><span class="dco-piece-type-check" aria-hidden="true">${selected ? "✓" : ""}</span><span class="dco-piece-type-option-label">${esc(label)}</span>${arrow}</button>`;
        }).join("");
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

    function typeSelect(tableRow) {
        return tableRow && tableRow.querySelector("select.dco-piece-type-select[data-field='piece_type']");
    }

    function extraOption(active) {
        return active && active.typeMenu
            ? active.typeMenu.querySelector("[data-piece-type-option='Extra']")
            : null;
    }

    function isRowEditable(tableRow) {
        const select = typeSelect(tableRow);
        return Boolean(select && !select.disabled);
    }

    function nodeFrom(target) {
        if (!target) return null;
        if (target.nodeType === 1) return target;
        return target.parentElement || null;
    }

    function isInsideMenuTree(active, target) {
        const node = nodeFrom(target);
        if (!active || !node || typeof node.closest !== "function") return false;
        if (active.surface && active.surface.contains(node)) return true;
        if (active.typeMenu && active.typeMenu.contains(node)) return true;
        if (!active.tableRow || !active.tableRow.isConnected) return false;
        const typeCell = active.tableRow.querySelector(".dco-col-type");
        return Boolean(typeCell && typeCell.contains(node));
    }

    function clearTimer(active, key) {
        if (!active || !active[key]) return;
        window.clearTimeout(active[key]);
        active[key] = null;
    }

    function clearHoverTimers(active) {
        clearTimer(active, "openTimer");
        clearTimer(active, "closeTimer");
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
        if (active && active.tableRow === tableRow && active.surface) {
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

    function unbindSession(active) {
        if (!active) return;
        document.removeEventListener("pointerdown", active.onOutside, true);
        document.removeEventListener("pointerover", active.onPointerOver, true);
        document.removeEventListener("pointerout", active.onPointerOut, true);
        document.removeEventListener("keydown", active.onDocumentKeydown, true);
        document.removeEventListener("scroll", active.onScroll, true);
        window.removeEventListener("resize", active.onResize);
    }

    function syncExpandedButtons(active) {
        if (!active || !active.tableRow) return;
        const expanded = Boolean(active.surface);
        const button = active.tableRow.querySelector(".dco-extra-open-button");
        if (button) button.setAttribute("aria-expanded", expanded ? "true" : "false");
        const option = extraOption(active);
        if (option) {
            option.classList.toggle("is-open", expanded);
            option.setAttribute("aria-expanded", expanded ? "true" : "false");
        }
    }

    function closeAddonFlyout(active) {
        if (!active || !active.surface) return false;
        active.surface.remove();
        active.surface = null;
        syncExpandedButtons(active);
        return true;
    }

    function closeTypeMenu(active) {
        if (!active || !active.typeMenu) return false;
        active.typeMenu.remove();
        active.typeMenu = null;
        return true;
    }

    function closeSurface(frm, options = {}) {
        const active = frm && frm.__almdinaExtraAddonsSurface;
        if (!active) return false;
        clearHoverTimers(active);
        const currentButton = active.tableRow && active.tableRow.querySelector(".dco-extra-open-button");
        closeAddonFlyout(active);
        closeTypeMenu(active);
        unbindSession(active);
        frm.__almdinaExtraAddonsSurface = null;
        if (options.restoreFocus && currentButton && currentButton.isConnected) {
            currentButton.focus({ preventScroll: true });
        }
        return true;
    }

    function resolveAnchor(active) {
        const option = extraOption(active);
        if (option) return option;
        if (!active.tableRow || !active.tableRow.isConnected) return null;
        return active.tableRow.querySelector(".dco-extra-open-button")
            || typeSelect(active.tableRow);
    }

    function applyFixedBox(node, top, left, width) {
        if (!node) return;
        node.style.setProperty("position", "fixed", "important");
        node.style.setProperty("inset", "auto", "important");
        node.style.setProperty("top", `${Math.round(top)}px`, "important");
        node.style.setProperty("left", `${Math.round(left)}px`, "important");
        node.style.setProperty("right", "auto", "important");
        node.style.setProperty("bottom", "auto", "important");
        node.style.setProperty("margin", "0", "important");
        node.style.setProperty("transform", "none", "important");
        if (width == null) {
            node.style.setProperty("width", "max-content", "important");
            node.style.setProperty("min-width", "136px", "important");
            return;
        }
        node.style.setProperty("width", `${Math.round(width)}px`, "important");
    }

    function placeTypeMenu(active) {
        const select = typeSelect(active.tableRow);
        const menu = active.typeMenu;
        if (!select || !menu) {
            if (!select) closeSurface(active.frm);
            return;
        }
        const rect = select.getBoundingClientRect();
        const margin = 8;
        applyFixedBox(menu, rect.top, rect.left, null);
        const width = Math.max(menu.offsetWidth || 136, 136);
        const height = Math.min(menu.scrollHeight || 180, window.innerHeight - (margin * 2));
        const selected = menu.querySelector(".dco-piece-type-option.is-selected");
        const selectedOffset = selected ? selected.offsetTop : 0;
        let top = rect.top - selectedOffset;
        if (top < margin) top = margin;
        if (top + height > window.innerHeight - margin) {
            top = Math.max(margin, window.innerHeight - height - margin);
        }
        let left = isArabic() ? rect.right - width : rect.left;
        left = Math.min(Math.max(margin, left), window.innerWidth - width - margin);
        applyFixedBox(menu, top, left, width);
    }

    function placeSurface(active) {
        if (!active.surface) return;
        const anchor = resolveAnchor(active);
        if (!anchor) {
            closeSurface(active.frm);
            return;
        }
        active.anchor = anchor;
        const rect = anchor.getBoundingClientRect();
        const surface = active.surface;
        const margin = 10;
        const gap = extraOption(active) ? 2 : 7;
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
        applyFixedBox(surface, top, left, width);
    }

    function placeMenus(active) {
        if (!active) return;
        if (active.typeMenu) placeTypeMenu(active);
        if (active.surface) placeSurface(active);
    }

    function refreshPieceTypeVisual(frm, tableRow, row) {
        const performance = window.AlmdinaTablePerformanceUX;
        if (performance && typeof performance.refreshPieceTypeVisual === "function") {
            performance.refreshPieceTypeVisual(frm, tableRow, row);
            return;
        }
        syncRowPresentation(frm, tableRow, row, { editable: true });
    }

    function applyPieceType(frm, tableRow, pieceType) {
        const performance = window.AlmdinaTablePerformanceUX;
        if (performance && typeof performance.setPieceType === "function") {
            return performance.setPieceType(frm, tableRow, pieceType);
        }
        const select = typeSelect(tableRow);
        if (!select) return rowByName(frm, tableRow && tableRow.dataset.rowName);
        if (select.value !== pieceType) {
            select.value = pieceType;
            select.dispatchEvent(new Event("change", { bubbles: true }));
        }
        return rowByName(frm, tableRow.dataset.rowName);
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

    function virtualPlaceholder(tableRow) {
        if (!tableRow || !tableRow.classList.contains("dco-virtual-row")) return null;
        const select = typeSelect(tableRow);
        return {
            name: tableRow.dataset.rowName,
            piece_type: (select && select.value) || "Regular",
        };
    }

    function currentRow(active) {
        return rowByName(active.frm, active.rowName)
            || rowByName(active.frm, active.tableRow && active.tableRow.dataset.rowName)
            || virtualPlaceholder(active.tableRow);
    }

    function updateAddonError(active, row) {
        if (!active.surface) return;
        const error = active.surface.querySelector(".dco-extra-error");
        if (!error) return;
        error.textContent = selectedFields(row).length
            ? ""
            : (isArabic() ? "اختر إضافة واحدة على الأقل." : "Choose at least one add-on.");
    }

    function bindAddonSurface(active) {
        const surface = active.surface;
        if (!surface || surface.__almdinaExtraBound) return;
        surface.__almdinaExtraBound = true;
        surface.addEventListener("change", event => {
            const input = event.target.closest("input[data-extra-field]");
            if (!input || !surface.contains(input)) return;
            let row = currentRow(active);
            if (!row) {
                closeSurface(active.frm);
                return;
            }
            if ((row.piece_type || "Regular") !== TYPE) {
                row = applyPieceType(active.frm, active.tableRow, TYPE) || row;
            }
            if (!row || (row.piece_type || "Regular") !== TYPE) {
                closeSurface(active.frm);
                return;
            }
            active.rowName = row.name;
            setAddon(active.frm, active.tableRow, row, input.dataset.extraField, input.checked);
            updateAddonError(active, row);
            placeMenus(active);
        });
        surface.addEventListener("pointerover", () => clearTimer(active, "closeTimer"));
    }

    function openAddonFlyout(frm, row, tableRow, options = {}) {
        if (!frm || !row || !tableRow) return false;
        const active = frm.__almdinaExtraAddonsSurface;
        if (!active || active.tableRow !== tableRow) return false;

        if (active.surface) {
            syncExpandedButtons(active);
            placeMenus(active);
            return true;
        }

        const surface = document.createElement("div");
        surface.className = "dco-extra-submenu-flyout";
        surface.setAttribute("role", "menu");
        surface.setAttribute("aria-label", isArabic() ? "إضافات Extra" : "Extra add-ons");
        surface.setAttribute("dir", isArabic() ? "rtl" : "ltr");
        surface.innerHTML = renderSubmenu(row);
        document.body.appendChild(surface);
        active.surface = surface;
        bindAddonSurface(active);
        syncExpandedButtons(active);
        placeMenus(active);
        if (options.focusFirst) {
            const first = surface.querySelector("input[data-extra-field]");
            if (first) first.focus({ preventScroll: true });
        }
        return true;
    }

    function bindTypeMenu(active) {
        const menu = active.typeMenu;
        if (!menu || menu.__almdinaTypeMenuBound) return;
        menu.__almdinaTypeMenuBound = true;
        menu.addEventListener("click", event => {
            const option = event.target.closest("[data-piece-type-option]");
            if (!option || !menu.contains(option)) return;
            event.preventDefault();
            const pieceType = option.dataset.pieceTypeOption;
            const row = applyPieceType(active.frm, active.tableRow, pieceType);
            if (!row) {
                closeSurface(active.frm);
                return;
            }
            active.rowName = row.name;
            if (pieceType === TYPE) {
                openAddonFlyout(active.frm, row, active.tableRow);
                return;
            }
            closeSurface(active.frm);
        });
        menu.addEventListener("pointerover", event => {
            if (!isMousePointer(event)) return;
            const option = event.target.closest("[data-piece-type-option]");
            if (!option || !menu.contains(option)) return;
            clearTimer(active, "closeTimer");
            if (option.dataset.pieceTypeOption === TYPE) {
                option.classList.add("is-open");
                option.setAttribute("aria-expanded", "true");
                scheduleAddonOpen(active, HOVER_OPEN_MS);
                return;
            }
            clearTimer(active, "openTimer");
            closeAddonFlyout(active);
        });
    }

    function openTypeMenu(frm, row, tableRow) {
        const active = frm.__almdinaExtraAddonsSurface;
        if (!active || active.tableRow !== tableRow || active.typeMenu) return false;
        const menu = document.createElement("div");
        menu.className = "dco-piece-type-menu-flyout";
        menu.setAttribute("role", "menu");
        menu.setAttribute("aria-label", isArabic() ? "نوع الدرفة" : "Piece type");
        menu.setAttribute("dir", isArabic() ? "rtl" : "ltr");
        menu.innerHTML = renderTypeMenu(row);
        document.body.appendChild(menu);
        active.typeMenu = menu;
        active.pinned = true;
        bindTypeMenu(active);
        placeMenus(active);
        window.requestAnimationFrame(() => {
            if (active.typeMenu === menu) placeMenus(active);
        });
        return true;
    }

    function scheduleLeaveClose(active) {
        clearTimer(active, "closeTimer");
        active.closeTimer = window.setTimeout(() => {
            active.closeTimer = null;
            if (active.pinned && active.typeMenu) {
                closeAddonFlyout(active);
                return;
            }
            if (active.pinned) return;
            closeSurface(active.frm);
        }, hoverDelay(HOVER_CLOSE_MS));
    }

    function scheduleAddonOpen(active, delayMs) {
        clearTimer(active, "openTimer");
        const run = () => {
            active.openTimer = null;
            if (!active.pointerInside && !active.surface) return;
            const row = currentRow(active);
            if (!row || !active.tableRow || !active.tableRow.isConnected) return;
            openAddonFlyout(active.frm, row, active.tableRow);
        };
        const wait = hoverDelay(delayMs);
        if (!wait) {
            run();
            return;
        }
        active.openTimer = window.setTimeout(run, wait);
    }

    function ensureSession(frm, tableRow, row, options = {}) {
        let active = frm.__almdinaExtraAddonsSurface;
        if (active && active.tableRow !== tableRow) {
            closeSurface(frm);
            active = null;
        }
        if (active) {
            active.rowName = row.name;
            if (options.pinned) active.pinned = true;
            return active;
        }

        active = {
            frm,
            rowName: row.name,
            tableRow,
            surface: null,
            typeMenu: null,
            anchor: null,
            pinned: Boolean(options.pinned),
            pointerInside: true,
            openTimer: null,
            closeTimer: null,
            onOutside: null,
            onPointerOver: null,
            onPointerOut: null,
            onDocumentKeydown: null,
            onResize: null,
            onScroll: null,
        };
        active.onOutside = event => {
            if (isInsideMenuTree(active, event.target)) return;
            closeSurface(frm);
        };
        active.onPointerOver = event => {
            if (!isMousePointer(event) || !isInsideMenuTree(active, event.target)) return;
            active.pointerInside = true;
            clearTimer(active, "closeTimer");
        };
        active.onPointerOut = event => {
            if (!isMousePointer(event) || isInsideMenuTree(active, event.relatedTarget)) return;
            active.pointerInside = false;
            scheduleLeaveClose(active);
        };
        active.onDocumentKeydown = event => {
            if (event.key !== "Escape") return;
            event.preventDefault();
            closeSurface(frm, { restoreFocus: true });
        };
        active.onResize = () => placeMenus(active);
        active.onScroll = () => placeMenus(active);
        document.addEventListener("pointerdown", active.onOutside, true);
        document.addEventListener("pointerover", active.onPointerOver, true);
        document.addEventListener("pointerout", active.onPointerOut, true);
        document.addEventListener("keydown", active.onDocumentKeydown, true);
        document.addEventListener("scroll", active.onScroll, true);
        window.addEventListener("resize", active.onResize);
        frm.__almdinaExtraAddonsSurface = active;
        return active;
    }

    function openSurface(frm, row, tableRow, options = {}) {
        if (!frm || !row || !tableRow || (row.piece_type || "Regular") !== TYPE) return false;
        const active = ensureSession(frm, tableRow, row, { pinned: options.pinned !== false });
        return openAddonFlyout(frm, row, tableRow, options);
    }

    function toggleTypeMenu(frm, tableRow) {
        const row = rowByName(frm, tableRow.dataset.rowName) || virtualPlaceholder(tableRow);
        if (!row || !isRowEditable(tableRow)) return false;
        const active = frm.__almdinaExtraAddonsSurface;
        if (active && active.tableRow === tableRow && active.typeMenu) {
            closeSurface(frm);
            return false;
        }
        const session = ensureSession(frm, tableRow, row, { pinned: true });
        return openTypeMenu(frm, row, tableRow) || Boolean(session.typeMenu);
    }

    function previewExtraRow(frm, tableRow) {
        const row = rowByName(frm, tableRow.dataset.rowName);
        if (!row || (row.piece_type || "Regular") !== TYPE || !isRowEditable(tableRow)) return false;
        const active = ensureSession(frm, tableRow, row, { pinned: false });
        if (active.typeMenu) return false;
        scheduleAddonOpen(active, ROW_HOVER_OPEN_MS);
        return true;
    }

    function scheduleOpenForSelection(frm, tableRow) {
        const context = window.AlmdinaDocumentContext;
        const run = () => {
            if (!tableRow || !tableRow.isConnected) return;
            const row = rowByName(frm, tableRow.dataset.rowName || "");
            if (!row || (row.piece_type || "Regular") !== TYPE) return;
            const active = frm.__almdinaExtraAddonsSurface;
            if (active && active.tableRow === tableRow && active.typeMenu) {
                openAddonFlyout(frm, row, tableRow);
                return;
            }
            openSurface(frm, row, tableRow, { focusFirst: true, pinned: true });
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
            root.addEventListener("pointerdown", event => {
                if (!isMousePointer(event) || event.button) return;
                const select = event.target.closest("select.dco-piece-type-select[data-field='piece_type']");
                if (!select || select.disabled || !root.contains(select)) return;
                event.preventDefault();
                select.focus({ preventScroll: true });
                const currentFrm = root.__almdinaExtraAddonsForm;
                const tableRow = select.closest("tr[data-row-name]");
                if (!tableRow) return;
                toggleTypeMenu(currentFrm, tableRow);
            }, true);
            root.addEventListener("mousedown", event => {
                if (event.button) return;
                const select = event.target.closest("select.dco-piece-type-select[data-field='piece_type']");
                if (!select || select.disabled || !root.contains(select)) return;
                const currentFrm = root.__almdinaExtraAddonsForm;
                const active = currentFrm && currentFrm.__almdinaExtraAddonsSurface;
                if (active && active.typeMenu) event.preventDefault();
            }, true);
            root.addEventListener("click", event => {
                const button = event.target.closest(".dco-extra-open-button");
                if (!button || !root.contains(button) || button.disabled) return;
                event.preventDefault();
                event.stopPropagation();
                const currentFrm = root.__almdinaExtraAddonsForm;
                const tableRow = button.closest("tr[data-row-name]");
                const row = rowByName(currentFrm, tableRow && tableRow.dataset.rowName);
                if (!row || (row.piece_type || "Regular") !== TYPE) return;
                openSurface(currentFrm, row, tableRow, { focusFirst: true, pinned: true });
            });
            root.addEventListener("pointerover", event => {
                if (!isMousePointer(event)) return;
                const typeCell = event.target.closest(".dco-col-type");
                if (!typeCell || !root.contains(typeCell)) return;
                const tableRow = typeCell.closest("tr[data-row-name]");
                if (!tableRow) return;
                const currentFrm = root.__almdinaExtraAddonsForm;
                const active = currentFrm && currentFrm.__almdinaExtraAddonsSurface;
                if (active && active.tableRow === tableRow) {
                    clearTimer(active, "closeTimer");
                    return;
                }
                previewExtraRow(currentFrm, tableRow);
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
        renderTypeMenu,
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
