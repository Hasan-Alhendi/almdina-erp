(() => {
    "use strict";

    if (window.AlmdinaExtraDoorAddonsUX) return;

    const TYPE = "Extra";
    const FIELDS = Object.freeze([
        Object.freeze({ fieldname: "extra_double", labelAr: "Double", labelEn: "Double" }),
        Object.freeze({ fieldname: "extra_liner", labelAr: "Liner", labelEn: "Liner" }),
        Object.freeze({
            fieldname: "extra_recessed_handle_cutout",
            labelAr: "تفريغ مسكة مخفية",
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

    function selectedFields(row) {
        return FIELDS.filter(item => Boolean(Number(row && row[item.fieldname] || 0)));
    }

    function renderControl(row, options = {}) {
        if (!row || (row.piece_type || "Regular") !== TYPE || options.virtual) return "";
        const selected = selectedFields(row);
        const labels = selected.map(item => isArabic() ? item.labelAr : item.labelEn);
        const title = isArabic() ? "إضافات الدرفة" : "Door add-ons";
        const count = selected.length;
        const chips = labels.length
            ? `<span class="dco-extra-chip-list">${labels.map(label => `<span>${esc(label)}</span>`).join("")}</span>`
            : `<span class="dco-extra-required">${isArabic() ? "اختر إضافة واحدة على الأقل" : "Choose at least one add-on"}</span>`;
        return `
            <button type="button" class="dco-extra-addons-trigger" aria-haspopup="dialog" aria-expanded="false" ${options.editable ? "" : "disabled"}>
                <span aria-hidden="true">＋</span>
                <span>${title}</span>
                <b>${count}</b>
            </button>
            ${chips}
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

    function rerender(frm) {
        const entry = window.AlmdinaDoorCuttingFastEntry;
        if (entry && typeof entry.render === "function") entry.render(frm);
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

    function focusAddonTrigger(frm, row) {
        const context = window.AlmdinaDocumentContext;
        const run = () => {
            const field = frm.fields_dict && frm.fields_dict.pieces_fast_entry;
            const root = field && field.$wrapper && field.$wrapper.get(0);
            if (!root) return;
            const escapedName = cssEscape(row.name);
            const trigger = root.querySelector(
                `tr[data-row-name="${escapedName}"] .dco-extra-addons-trigger`
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

    function closeSurface(frm) {
        const active = frm && frm.__almdinaExtraAddonsSurface;
        if (!active) return false;
        frm.__almdinaExtraAddonsSurface = null;
        active.trigger.setAttribute("aria-expanded", "false");
        active.surface.remove();
        document.removeEventListener("pointerdown", active.onOutside, true);
        document.removeEventListener("keydown", active.onKeydown, true);
        return true;
    }

    function placeSurface(surface, trigger) {
        const rect = trigger.getBoundingClientRect();
        const surfaceRect = surface.getBoundingClientRect();
        const width = surfaceRect.width || 390;
        const height = surfaceRect.height || 360;
        const left = Math.min(
            Math.max(12, Math.round(rect.left)),
            Math.max(12, window.innerWidth - width - 12)
        );
        const below = rect.bottom + 8;
        const top = below + Math.min(height, 360) <= window.innerHeight
            ? below
            : Math.max(12, rect.top - height - 8);
        surface.style.setProperty("--dco-extra-anchor-top", `${Math.round(top)}px`);
        surface.style.setProperty("--dco-extra-anchor-left", `${left}px`);
    }

    function openSurface(frm, row, trigger) {
        closeSurface(frm);
        const selected = new Set(selectedFields(row).map(item => item.fieldname));
        const surface = document.createElement("div");
        surface.className = "dco-extra-popover";
        surface.setAttribute("role", "dialog");
        surface.setAttribute("aria-modal", "false");
        surface.setAttribute("aria-label", isArabic() ? "اختيار إضافات الدرفة" : "Choose door add-ons");
        surface.innerHTML = `
            <div class="dco-extra-popover-head">
                <div><b>${isArabic() ? "إضافات الدرفة Extra" : "Extra door add-ons"}</b><span>${isArabic() ? "يمكن اختيار أكثر من إضافة" : "Choose one or more"}</span></div>
                <button type="button" class="dco-extra-close" aria-label="${isArabic() ? "إغلاق" : "Close"}">×</button>
            </div>
            <div class="dco-extra-options">
                ${FIELDS.map(item => {
                    const label = isArabic() ? item.labelAr : item.labelEn;
                    return `<label><input type="checkbox" data-extra-field="${item.fieldname}" ${selected.has(item.fieldname) ? "checked" : ""}><span><b>${esc(label)}</b><small>${isArabic() ? "السعر لكل درفة × العدد" : "Price per door × quantity"}</small></span></label>`;
                }).join("")}
            </div>
            <div class="dco-extra-error" role="alert" aria-live="polite"></div>
            <div class="dco-extra-popover-actions">
                <button type="button" class="btn btn-default btn-sm dco-extra-cancel">${isArabic() ? "إلغاء" : "Cancel"}</button>
                <button type="button" class="btn btn-primary btn-sm dco-extra-apply">${isArabic() ? "تطبيق" : "Apply"}</button>
            </div>
        `;
        document.body.appendChild(surface);
        placeSurface(surface, trigger);
        trigger.setAttribute("aria-expanded", "true");

        const onOutside = event => {
            if (surface.contains(event.target) || trigger.contains(event.target)) return;
            closeSurface(frm);
        };
        const onKeydown = event => {
            if (event.key !== "Escape") return;
            event.preventDefault();
            closeSurface(frm);
            trigger.focus({ preventScroll: true });
        };
        frm.__almdinaExtraAddonsSurface = { surface, trigger, onOutside, onKeydown };
        document.addEventListener("pointerdown", onOutside, true);
        document.addEventListener("keydown", onKeydown, true);

        surface.querySelector(".dco-extra-close").addEventListener("click", () => closeSurface(frm));
        surface.querySelector(".dco-extra-cancel").addEventListener("click", () => closeSurface(frm));
        surface.querySelector(".dco-extra-apply").addEventListener("click", () => {
            const chosen = new Set(
                [...surface.querySelectorAll("input[data-extra-field]:checked")]
                    .map(input => input.dataset.extraField)
            );
            if (!chosen.size) {
                surface.querySelector(".dco-extra-error").textContent = isArabic()
                    ? "اختر إضافة واحدة على الأقل."
                    : "Choose at least one add-on.";
                surface.querySelector("input[data-extra-field]").focus();
                return;
            }
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
            const needsNotes = !String(row.notes || "").trim();
            closeSurface(frm);
            rerender(frm);
            if (needsNotes) {
                frappe.show_alert({
                    message: isArabic()
                        ? "تم اختيار الإضافات — أكمل ملاحظات التنفيذ."
                        : "Add-ons selected — complete the implementation notes.",
                    indicator: "blue",
                });
                focusNotes(frm, row);
            }
        });
        const first = surface.querySelector("input[data-extra-field]");
        if (first) first.focus({ preventScroll: true });
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
            const trigger = event.target.closest(".dco-extra-addons-trigger");
            if (!trigger || !root.contains(trigger) || trigger.disabled) return;
            event.preventDefault();
            event.stopPropagation();
            const currentFrm = root.__almdinaExtraAddonsForm;
            const tableRow = trigger.closest("tr[data-row-name]");
            const row = rowByName(currentFrm, tableRow && tableRow.dataset.rowName);
            if (row) openSurface(currentFrm, row, trigger);
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
        rerender(frm);
        if (missingAddon) focusAddonTrigger(frm, invalid);
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
        FIELDS,
        selectedFields,
        renderControl,
        notesCueHtml,
        reconcilePieceType,
        bindTable,
        validateRows,
        closeSurface,
    });
})();
