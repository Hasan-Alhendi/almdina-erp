(() => {
    "use strict";

    if (window.AlmdinaExtraDoorAddonsUX) return;

    const PIECE_TYPES = Object.freeze([
        Object.freeze({ value: "Regular", labelAr: "عادية", labelEn: "Regular" }),
        Object.freeze({ value: "Special", labelAr: "خاصة", labelEn: "Special" }),
        Object.freeze({ value: "Clipped Corner", labelAr: "الزاوية الكسر", labelEn: "Clipped corner" }),
        Object.freeze({ value: "L-Shaped Corner", labelAr: "زاوية L", labelEn: "L-shaped corner" }),
    ]);
    const FIELDS = Object.freeze([
        Object.freeze({ fieldname: "extra_double", labelAr: "دبل قشاط", labelEn: "Double", shortAr: "دبل", shortEn: "D" }),
        Object.freeze({ fieldname: "extra_full_door_double", labelAr: "دبل كامل", labelEn: "Full door double", shortAr: "كامل", shortEn: "FD" }),
        Object.freeze({ fieldname: "extra_liner", labelAr: "لاينر", labelEn: "Liner", shortAr: "لاينر", shortEn: "L" }),
        Object.freeze({ fieldname: "extra_back_groove", labelAr: "فرزة ظهر", labelEn: "Back groove", shortAr: "ظهر", shortEn: "BG" }),
        Object.freeze({ fieldname: "extra_recessed_handle_cutout", labelAr: "مسكة غطس", labelEn: "Recessed handle", shortAr: "غطس", shortEn: "RH" }),
    ]);
    const FIELD_NAMES = new Set(FIELDS.map(item => item.fieldname));
    const PIECE_TYPE_VALUES = new Set(PIECE_TYPES.map(item => item.value));
    const DOUBLE_FIELD = "extra_double";
    const FULL_DOUBLE_FIELD = "extra_full_door_double";

    function isArabic() {
        const lang = String(
            (window.frappe && frappe.boot && frappe.boot.lang)
            || document.documentElement.lang
            || ""
        ).toLowerCase();
        return lang === "ar" || lang.startsWith("ar-");
    }

    function esc(value) {
        if (window.frappe && frappe.utils && frappe.utils.escape_html) {
            return frappe.utils.escape_html(String(value ?? ""));
        }
        return String(value ?? "");
    }

    function typeDefinition(value) {
        return PIECE_TYPES.find(item => item.value === value) || PIECE_TYPES[0];
    }

    function selectedFields(row) {
        return FIELDS.filter(item => Boolean(Number(row && row[item.fieldname])));
    }

    function physicalCutQuantity(row) {
        const qty = Math.max(0, Math.floor(Number(row && row.qty) || 0));
        return Number(row && row.extra_full_door_double) ? qty * 2 : qty;
    }

    function renderTypePicker(row, options = {}) {
        const pieceType = typeDefinition(row && row.piece_type).value;
        const disabled = options.editable === false ? "disabled" : "";
        const choices = PIECE_TYPES.map(item => {
            const label = isArabic() ? item.labelAr : item.labelEn;
            return `<option value="${esc(item.value)}" ${pieceType === item.value ? "selected" : ""}>${esc(label)}</option>`;
        }).join("");
        return `<div class="dco-piece-type-native" data-piece-type="${esc(pieceType)}">
            <select class="dco-fast-select dco-piece-type-select" data-field="piece_type" aria-label="${isArabic() ? "نوع الدرفة" : "Piece type"}" ${disabled}>${choices}</select>
        </div>`;
    }

    function renderAddonCell(row, fieldname, options = {}) {
        const definition = FIELDS.find(item => item.fieldname === fieldname);
        if (!definition) return "";
        const selected = Boolean(Number(row && row[fieldname]));
        const disabled = options.editable === false ? "disabled" : "";
        const label = isArabic() ? definition.labelAr : definition.labelEn;
        const shortLabel = isArabic() ? definition.shortAr : definition.shortEn;
        return `<button type="button" class="dco-check-toggle dco-addon-toggle ${selected ? "is-checked" : ""}" data-check-field="${fieldname}" aria-pressed="${selected ? "true" : "false"}" aria-label="${esc(label)}" title="${esc(label)}" ${disabled}>
            <span class="dco-check-mark" aria-hidden="true">${selected ? "✓" : ""}</span><span class="dco-addon-short">${esc(shortLabel)}</span>
        </button>`;
    }

    function enforceMutualExclusivity(row, fieldname, enabled) {
        if (!row || !FIELD_NAMES.has(fieldname)) return [];
        const changed = [];
        const next = enabled ? 1 : 0;
        if (Number(row[fieldname] || 0) !== next) {
            row[fieldname] = next;
            changed.push(fieldname);
        }
        if (!next) return changed;
        const peer = fieldname === DOUBLE_FIELD
            ? FULL_DOUBLE_FIELD
            : (fieldname === FULL_DOUBLE_FIELD ? DOUBLE_FIELD : "");
        if (peer && Number(row[peer] || 0)) {
            row[peer] = 0;
            changed.push(peer);
        }
        return changed;
    }

    function syncAddonButtons(tableRow, row, editable = true) {
        if (!tableRow || !tableRow.querySelectorAll) return false;
        tableRow.querySelectorAll(".dco-addon-toggle[data-check-field]").forEach((button) => {
            const selected = Boolean(Number(row && row[button.dataset.checkField]));
            button.classList.toggle("is-checked", selected);
            button.setAttribute("aria-pressed", selected ? "true" : "false");
            button.disabled = !editable;
            const mark = button.querySelector(".dco-check-mark");
            if (mark) mark.textContent = selected ? "✓" : "";
        });
        return true;
    }

    function syncRowPresentation(_frm, tableRow, row, options = {}) {
        if (!tableRow || !row) return false;
        const select = tableRow.querySelector && tableRow.querySelector(
            "select.dco-piece-type-select[data-field='piece_type']"
        );
        if (select) {
            select.value = typeDefinition(row.piece_type).value;
            select.disabled = options.editable === false;
        }
        syncAddonButtons(tableRow, row, options.editable !== false);
        return true;
    }

    function reconcilePieceType(frm, row) {
        if (!row || PIECE_TYPE_VALUES.has(row.piece_type || "Regular")) return false;
        row.piece_type = "Regular";
        if (frm && typeof frm.dirty === "function") frm.dirty();
        return true;
    }

    function bindTable() {
        return true;
    }

    window.AlmdinaExtraDoorAddonsUX = Object.freeze({
        PIECE_TYPES,
        FIELDS,
        FIELD_NAMES,
        selectedFields,
        physicalCutQuantity,
        renderTypePicker,
        renderAddonCell,
        enforceMutualExclusivity,
        syncAddonButtons,
        syncRowPresentation,
        reconcilePieceType,
        bindTable,
    });
})();
