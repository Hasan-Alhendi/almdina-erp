(() => {
    "use strict";

    if (window.AlmdinaExtraDoorAddonsUX) return;

    const PIECE_TYPES = Object.freeze([
        Object.freeze({ value: "Regular", label: "Regular" }),
        Object.freeze({ value: "Special", label: "Special" }),
        Object.freeze({ value: "Clipped Corner", label: "Clipped corner" }),
        Object.freeze({ value: "L-Shaped Corner", label: "L-shaped corner" }),
        Object.freeze({ value: "Glass", label: "Glass" }),
    ]);
    const FIELDS = Object.freeze([
        Object.freeze({ fieldname: "extra_double", label: "Double Edge", button: "Double Edge" }),
        Object.freeze({ fieldname: "extra_full_door_double", label: "Full Door Double", button: "Full Double" }),
        Object.freeze({ fieldname: "extra_liner", label: "Liner", button: "Liner" }),
        Object.freeze({ fieldname: "extra_back_groove", label: "Back Groove", button: "Back Groove" }),
        Object.freeze({ fieldname: "extra_recessed_handle_cutout", label: "Recessed Handle Cutout", button: "Recessed Handle" }),
    ]);
    const FIELD_NAMES = new Set(FIELDS.map(item => item.fieldname));
    const PIECE_TYPE_VALUES = new Set(PIECE_TYPES.map(item => item.value));
    const DOUBLE_FIELD = "extra_double";
    const FULL_DOUBLE_FIELD = "extra_full_door_double";

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
            const label = __(item.label);
            return `<option value="${esc(item.value)}" ${pieceType === item.value ? "selected" : ""}>${esc(label)}</option>`;
        }).join("");
        return `<div class="dco-piece-type-native" data-piece-type="${esc(pieceType)}">
            <select class="dco-fast-select dco-piece-type-select" data-field="piece_type" aria-label="${__("Piece type")}" ${disabled}>${choices}</select>
        </div>`;
    }

    function translate(message) {
        return typeof __ === "function" ? __(message) : message;
    }

    function addonButtonLabel(definition) {
        return String(translate(definition && definition.button) || "");
    }

    function addonSummary(row) {
        const names = selectedFields(row).map(addonButtonLabel).filter(Boolean);
        const hidden = names.length > 2 ? names.length - 2 : 0;
        const empty = translate("Add-ons");
        const label = names.length === 0
            ? empty
            : (hidden ? `${names[0]} · ${names[1]}` : names.join(" · "));
        return {
            names,
            label,
            hidden,
            tooltip: names.length ? names.join(" · ") : empty,
        };
    }

    function renderAddonSummary(row, options = {}) {
        const summary = addonSummary(row);
        const disabled = options.virtual ? "disabled" : "";
        const active = summary.names.length ? "is-active" : "";
        const badge = summary.hidden
            ? `<span class="dco-addons-more" aria-hidden="true">+${summary.hidden}</span>`
            : "";
        const icon = summary.names.length
            ? ""
            : `<svg class="dco-addons-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M2.5 4.5h11M2.5 8h11M2.5 11.5h11" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>`;
        return `<button type="button" class="dco-addons-open ${active}" data-open-addons="1" title="${esc(summary.tooltip)}" aria-label="${esc(summary.tooltip)}" ${disabled}>${icon}<span class="dco-addons-open-label">${esc(summary.label)}</span>${badge}</button>`;
    }

    function renderAddonCell(row, fieldname, options = {}) {
        const definition = FIELDS.find(item => item.fieldname === fieldname);
        if (!definition) return "";
        const selected = Boolean(Number(row && row[fieldname]));
        const disabled = options.editable === false ? "disabled" : "";
        const label = __(definition.label);
        const engine = window.AlmdinaMachiningOverlay;
        const machiningSummary = engine && selected && typeof engine.summary === "function"
            ? engine.summary(row, fieldname)
            : "";
        const liner = !machiningSummary && fieldname === "extra_liner" && window.AlmdinaLinerGeometry;
        const linerSummary = machiningSummary || (liner && selected ? window.AlmdinaLinerGeometry.summary(row) : "");
        const title = linerSummary ? `${label} — ${linerSummary}` : label;
        const buttonLabel = __(definition.button);
        const buttonLines = buttonLabel.split(/\s+/).map(word => (
            `<span class="dco-addon-label-line">${esc(word)}</span>`
        )).join("\n");
        return `<button type="button" class="dco-check-toggle dco-addon-toggle ${selected ? "is-checked" : ""}" data-check-field="${fieldname}" aria-pressed="${selected ? "true" : "false"}" aria-label="${esc(label)}" title="${esc(title)}" ${disabled}>
            ${buttonLines}
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
        });
        const summary = tableRow.querySelector("[data-open-addons]");
        if (summary) {
            const cell = summary.closest("td") || summary.parentElement;
            if (cell) cell.innerHTML = renderAddonSummary(row, { editable });
        }
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
        addonSummary,
        renderAddonSummary,
        renderAddonCell,
        enforceMutualExclusivity,
        syncAddonButtons,
        syncRowPresentation,
        reconcilePieceType,
        bindTable,
    });
})();
