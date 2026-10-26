(() => {
    "use strict";

    // Presentation preview of domain validate_glass_opening.
    // opening_mm = outer_cm * MM_PER_CM - 2 * margin_mm.
    // The order save remains the server authority for this contract.
    const GLASS_TYPE = "Glass";
    const MM_PER_CM = 10;
    const OUTER_MARGIN_NOTE = "Glass margin is measured from the entered outer size. The cut size can differ after edge banding.";

    function isGlass(row) {
        return String((row && row.piece_type) || "") === GLASS_TYPE;
    }

    function roundMm(value) {
        const number = Number(value);
        if (!Number.isFinite(number)) return null;
        return Math.round(number * 1000) / 1000;
    }

    function formatNumber(value) {
        const rounded = roundMm(value);
        return rounded == null ? "—" : String(rounded);
    }

    function openingMm(widthCm, lengthCm, marginMm) {
        const width = Number(widthCm);
        const length = Number(lengthCm);
        const margin = Number(marginMm);
        if (![width, length, margin].every(Number.isFinite)) return null;
        return {
            marginMm: roundMm(margin),
            openingWidthMm: roundMm(width * MM_PER_CM - (2 * margin)),
            openingLengthMm: roundMm(length * MM_PER_CM - (2 * margin)),
        };
    }

    function isPositiveOpening(opening) {
        return Boolean(
            opening
            && opening.marginMm > 0
            && opening.openingWidthMm > 0
            && opening.openingLengthMm > 0
        );
    }

    function marginMmFromCm(value) {
        const centimeters = Number(value);
        if (!Number.isFinite(centimeters)) return null;
        return roundMm(centimeters * MM_PER_CM);
    }

    function marginCmTextFromMm(value) {
        const millimeters = Number(value);
        if (!Number.isFinite(millimeters) || millimeters === 0) return "";
        const thousandths = Math.round(millimeters * 1000);
        return String(thousandths / 10000);
    }

    function approvedMarginText(row) {
        return marginCmTextFromMm(row && row.glass_margin_mm);
    }

    function previewState(widthCm, lengthCm, draftCmText) {
        const text = String(draftCmText ?? "").trim();
        if (!text) return { status: "empty", opening: null };
        const marginMm = marginMmFromCm(text);
        const opening = marginMm == null ? null : openingMm(widthCm, lengthCm, marginMm);
        if (!isPositiveOpening(opening)) return { status: "invalid", opening };
        return { status: "valid", opening };
    }

    function applyDraft(row, draftText) {
        const state = previewState(row && row.width_cm, row && row.length_cm, draftText);
        if (state.status !== "valid" || !state.opening) {
            return { ok: false, error: "invalid_glass_margin", save: false };
        }
        return {
            ok: true,
            save: false,
            glass_margin_mm: state.opening.marginMm,
            values: { glass_margin_mm: state.opening.marginMm },
        };
    }

    function beginSession(row) {
        const session = {
            draft: approvedMarginText(row),
            setDraft(value) {
                this.draft = value;
            },
            preview() {
                return previewState(row.width_cm, row.length_cm, this.draft);
            },
            cancel() {
                this.draft = approvedMarginText(row);
                return {
                    dirty: false,
                    save: false,
                    glass_margin_mm: row.glass_margin_mm,
                    draft: this.draft,
                };
            },
            apply() {
                return applyDraft(row, this.draft);
            },
        };
        return session;
    }

    function shapeButtonState(row, options = {}) {
        if (!isGlass(row)) return null;
        const state = previewState(row.width_cm, row.length_cm, approvedMarginText(row));
        const valid = state.status === "valid";
        const summary = valid
            ? `${marginCmTextFromMm(state.opening.marginMm)} ${__("cm")}`
            : "";
        return {
            enabled: !options.virtual,
            incomplete: !valid,
            icon: "▢",
            label: valid ? summary : __("Set"),
            title: valid
                ? `${__("Glass Door")} — ${formatNumber(state.opening.openingWidthMm)} × ${formatNumber(state.opening.openingLengthMm)} ${__("mm")}`
                : (approvedMarginText(row) ? __("Invalid Glass Margin") : __("Glass Margin")),
        };
    }

    function paintShapeButton(button, state) {
        button.disabled = !state.enabled;
        button.classList.add("is-glass");
        button.classList.toggle("is-incomplete", state.incomplete);
        button.classList.remove("is-documented", "is-exact-geometry", "is-clipped-corner");
        const icon = button.querySelector("span:first-child");
        const label = button.querySelector("span:last-child");
        if (icon) icon.textContent = state.icon;
        if (label) label.textContent = state.label;
        button.title = state.title;
    }

    function syncShapeButton(tr, row, options) {
        const button = tr && tr.querySelector && tr.querySelector("button.dco-special-sketch-button");
        if (!button) return false;
        if (!isGlass(row)) {
            button.classList.remove("is-glass", "is-incomplete");
            return false;
        }
        const editable = options && Object.prototype.hasOwnProperty.call(options, "editable")
            ? Boolean(options.editable)
            : (!button.disabled && !tr.classList.contains("dco-virtual-row"));
        const virtual = options && Object.prototype.hasOwnProperty.call(options, "virtual")
            ? Boolean(options.virtual)
            : false;
        paintShapeButton(button, shapeButtonState(row, { editable, virtual }));
        return true;
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function readout(state, key) {
        if (!state || !state.opening || !(state.opening[key] > 0)) return "—";
        return formatNumber(state.opening[key]);
    }

    function previewSvg(widthCm, lengthCm, state) {
        const width = Number(widthCm);
        const length = Number(lengthCm);
        const safeWidth = Number.isFinite(width) && width > 0 ? width : 1;
        const safeLength = Number.isFinite(length) && length > 0 ? length : 1;
        const viewWidth = 220;
        const viewHeight = 280;
        const padTop = 18;
        const padBottom = 20;
        const padSide = 8;
        const scale = Math.min(
            (viewWidth - (padSide * 2)) / safeWidth,
            (viewHeight - padTop - padBottom) / safeLength
        );
        const frameWidth = safeWidth * scale;
        const frameHeight = safeLength * scale;
        const x = (viewWidth - frameWidth) / 2;
        const y = padTop + ((viewHeight - padTop - padBottom - frameHeight) / 2);
        const round = (value) => Math.round(value * 100) / 100;
        let opening = "";
        if (state && state.status === "valid" && state.opening) {
            const inset = (state.opening.marginMm / MM_PER_CM) * scale;
            const innerWidth = frameWidth - (inset * 2);
            const innerHeight = frameHeight - (inset * 2);
            if (innerWidth > 0 && innerHeight > 0) {
                opening = `<rect class="dco-glass-opening" x="${round(x + inset)}" y="${round(y + inset)}" width="${round(innerWidth)}" height="${round(innerHeight)}"></rect>
                    <text x="${round(x + (frameWidth / 2))}" y="${round(y + (frameHeight / 2))}" text-anchor="middle">${escapeHtml(formatNumber(state.opening.openingWidthMm))} × ${escapeHtml(formatNumber(state.opening.openingLengthMm))}</text>`;
            }
        }
        return `<svg viewBox="0 0 ${viewWidth} ${viewHeight}" role="img" aria-label="${escapeHtml(__("Glass Opening Dimensions"))}">
            <rect class="dco-glass-frame" x="${round(x)}" y="${round(y)}" width="${round(frameWidth)}" height="${round(frameHeight)}"></rect>
            ${opening}
            <text x="${round(x + (frameWidth / 2))}" y="${round(y - 6)}" text-anchor="middle">${escapeHtml(formatNumber(safeWidth))} ${escapeHtml(__("cm"))}</text>
            <text x="${round(x + (frameWidth / 2))}" y="${round(y + frameHeight + 14)}" text-anchor="middle">${escapeHtml(formatNumber(safeLength))} ${escapeHtml(__("cm"))}</text>
        </svg>`;
    }

    function renderEditor(root, row, draftText, options = {}) {
        const state = previewState(row.width_cm, row.length_cm, draftText);
        const preview = root.querySelector("[data-glass-preview]");
        if (preview) preview.innerHTML = previewSvg(row.width_cm, row.length_cm, state);
        const openingWidth = root.querySelector("[data-opening-width]");
        const openingLength = root.querySelector("[data-opening-length]");
        if (openingWidth) openingWidth.textContent = readout(state, "openingWidthMm");
        if (openingLength) openingLength.textContent = readout(state, "openingLengthMm");
        const help = root.querySelector("[data-glass-help]");
        if (help) {
            help.classList.toggle("is-error", state.status === "invalid");
            help.textContent = state.status === "invalid"
                ? __("Invalid Glass Margin")
                : __(OUTER_MARGIN_NOTE);
        }
        const input = root.querySelector("[data-glass-margin]");
        if (input && options.setInput) input.value = draftText;
        return state;
    }

    function editorHtml() {
        return `<div class="dco-glass-editor">
            <section class="dco-glass-preview-panel">
                <div class="dco-glass-preview-head">
                    <strong>${__("Glass Door")}</strong>
                    <span>${__("Glass Opening Dimensions")}</span>
                </div>
                <div class="dco-glass-preview" data-glass-preview></div>
            </section>
            <section class="dco-glass-controls">
                <label class="dco-glass-field">
                    <span>${__("Glass Margin")}</span>
                    <span class="dco-glass-input-shell">
                        <input type="number" inputmode="decimal" step="any" data-glass-margin aria-label="${escapeHtml(__("Glass Margin"))}">
                        <span>${__("cm")}</span>
                    </span>
                </label>
                <div class="dco-glass-readout">
                    <span>${__("Opening Width")}<b data-opening-width>—</b></span>
                    <span>${__("Opening Length")}<b data-opening-length>—</b></span>
                </div>
                <p class="dco-glass-help" data-glass-help></p>
            </section>
        </div>`;
    }

    function commitMargin(frm, row, marginMm) {
        const editor = window.AlmdinaClippedCornerEditor;
        const write = async () => {
            if (editor && typeof editor.commitChildValues === "function") {
                return editor.commitChildValues(frm, row, { glass_margin_mm: marginMm });
            }
            await frappe.model.set_value(row.doctype, row.name, { glass_margin_mm: marginMm });
            return row;
        };
        if (editor && typeof editor.queueChildApply === "function") {
            return editor.queueChildApply(frm, write);
        }
        return write().then((value) => ({ ok: true, value })).catch((error) => ({ ok: false, error }));
    }

    let activeDialog = null;

    function open(frm, row, options = {}) {
        if (!frm || !isGlass(row)) return;
        const readOnly = Boolean(options.readOnly);
        const currentRow = () => {
            const editor = window.AlmdinaClippedCornerEditor;
            if (editor && typeof editor.resolveChildRow === "function") {
                return editor.resolveChildRow(frm, row) || row;
            }
            return (frm.doc.pieces || []).find((candidate) => candidate && candidate.name === row.name) || row;
        };
        if (activeDialog) {
            try { activeDialog.hide(); } catch (error) { /* replace the previous glass dialog */ }
            activeDialog = null;
        }
        const dialog = new frappe.ui.Dialog({
            title: __("Glass Door"),
            fields: [{ fieldname: "glass_editor", fieldtype: "HTML" }],
            primary_action_label: readOnly ? __("Close") : __("Apply Shape"),
            primary_action() {
                if (readOnly) {
                    dialog.hide();
                    return Promise.resolve();
                }
                const root = dialog.$wrapper.find(".dco-glass-editor").get(0);
                const input = root && root.querySelector("[data-glass-margin]");
                const latestRow = currentRow();
                const draft = input ? input.value : "";
                if (!latestRow || !isGlass(latestRow)) {
                    frappe.msgprint({
                        title: __("Invalid Glass Margin"),
                        message: __("Invalid Glass Margin"),
                        indicator: "orange",
                    });
                    return Promise.resolve(false);
                }
                const decision = applyDraft(latestRow, draft);
                if (!decision.ok) {
                    if (root) renderEditor(root, latestRow, draft);
                    frappe.msgprint({
                        title: __("Invalid Glass Margin"),
                        message: __("Invalid Glass Margin"),
                        indicator: "orange",
                    });
                    return Promise.resolve(false);
                }
                if (typeof dialog.disable_primary_action === "function") dialog.disable_primary_action();
                return Promise.resolve(commitMargin(frm, latestRow, decision.glass_margin_mm)).then((result) => {
                    if (typeof dialog.enable_primary_action === "function") dialog.enable_primary_action();
                    if (!result || result.ok === false) {
                        frappe.msgprint({
                            title: __("Invalid Glass Margin"),
                            message: __("Invalid Glass Margin"),
                            indicator: "red",
                        });
                        return false;
                    }
                    frm.dirty();
                    dialog.hide();
                    if (window.AlmdinaDoorCuttingFastEntry && typeof window.AlmdinaDoorCuttingFastEntry.render === "function") {
                        window.AlmdinaDoorCuttingFastEntry.render(frm);
                    }
                    if (typeof frappe.show_alert === "function") {
                        frappe.show_alert({ message: __("Glass shape applied"), indicator: "green" });
                    }
                    return result.value || latestRow;
                });
            },
        });
        dialog.$wrapper.addClass("dco-glass-modal");
        activeDialog = dialog;
        dialog.$wrapper.on("hidden.bs.modal.dco-glass-shape", () => {
            if (activeDialog === dialog) activeDialog = null;
        });
        dialog.show();
        const field = dialog.fields_dict.glass_editor;
        const draft = approvedMarginText(currentRow() || row);
        field.$wrapper.html(editorHtml());
        const root = field.$wrapper.find(".dco-glass-editor").get(0);
        renderEditor(root, currentRow() || row, draft, { setInput: true });
        const input = root.querySelector("[data-glass-margin]");
        if (readOnly) {
            input.disabled = true;
            return;
        }
        input.addEventListener("input", () => {
            renderEditor(root, currentRow() || row, input.value);
        });
    }

    function view(frm, row) {
        return open(frm, row, { readOnly: true });
    }

    window.AlmdinaGlassShape = Object.freeze({
        GLASS_TYPE,
        MM_PER_CM,
        isGlass,
        openingMm,
        previewState,
        applyDraft,
        marginMmFromCm,
        marginCmTextFromMm,
        approvedMarginText,
        beginSession,
        shapeButtonState,
        previewSvg,
        renderEditor,
        syncShapeButton,
        open,
        view,
    });
})();
