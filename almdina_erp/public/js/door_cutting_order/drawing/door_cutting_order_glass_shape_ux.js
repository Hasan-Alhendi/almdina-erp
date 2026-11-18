(() => {
    "use strict";

    // Presentation preview of domain validate_glass_opening.
    // opening_mm = outer_cm * MM_PER_CM - 2 * margin_mm.
    // The order save remains the server authority for this contract.
    const GLASS_TYPE = "Glass";
    const MM_PER_CM = 10;
    const MODE_ALL = "All Directions";
    const MODE_SIDES = "Individual Sides";
    const DEFAULT_GLASS_MARGIN_MM = 60;
    const OUTER_MARGIN_NOTE = "Glass margin is measured from the entered outer size. The cut size can differ after edge banding.";

    function isGlass(row) {
        return String((row && row.piece_type) || "") === GLASS_TYPE;
    }

    function applyNewGlassMargin(row) {
        if (!isGlass(row)) return row;
        row.glass_margin_mode = MODE_ALL;
        row.glass_margin_mm = DEFAULT_GLASS_MARGIN_MM;
        row.glass_margin_top_mm = 0;
        row.glass_margin_bottom_mm = 0;
        row.glass_margin_right_mm = 0;
        row.glass_margin_left_mm = 0;
        return row;
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
        return openingFromSides(widthCm, lengthCm, {
            top: marginMm,
            bottom: marginMm,
            right: marginMm,
            left: marginMm,
        }, MODE_ALL);
    }

    function openingFromSides(widthCm, lengthCm, sidesMm, mode) {
        const width = Number(widthCm);
        const length = Number(lengthCm);
        const top = Number(sidesMm && sidesMm.top);
        const bottom = Number(sidesMm && sidesMm.bottom);
        const right = Number(sidesMm && sidesMm.right);
        const left = Number(sidesMm && sidesMm.left);
        if (![width, length, top, bottom, right, left].every(Number.isFinite)) return null;
        const shared = top === bottom && bottom === right && right === left ? top : null;
        return {
            mode: mode || MODE_ALL,
            marginMm: shared == null ? null : roundMm(shared),
            topMm: roundMm(top),
            bottomMm: roundMm(bottom),
            rightMm: roundMm(right),
            leftMm: roundMm(left),
            originXmm: roundMm(left),
            originYmm: roundMm(top),
            openingWidthMm: roundMm(width * MM_PER_CM - left - right),
            openingLengthMm: roundMm(length * MM_PER_CM - top - bottom),
        };
    }

    function isPositiveOpening(opening) {
        return Boolean(
            opening
            && opening.topMm > 0
            && opening.bottomMm > 0
            && opening.rightMm > 0
            && opening.leftMm > 0
            && opening.openingWidthMm > 0
            && opening.openingLengthMm > 0
        );
    }

    function readMode(row) {
        return String((row && row.glass_margin_mode) || "") === MODE_SIDES ? MODE_SIDES : MODE_ALL;
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
            values: {
                glass_margin_mode: MODE_ALL,
                glass_margin_mm: state.opening.marginMm,
                glass_margin_top_mm: 0,
                glass_margin_bottom_mm: 0,
                glass_margin_right_mm: 0,
                glass_margin_left_mm: 0,
            },
        };
    }

    function storedSideCm(row) {
        if (readMode(row) !== MODE_SIDES) {
            const shared = approvedMarginText(row);
            return { top: shared, bottom: shared, right: shared, left: shared };
        }
        return {
            top: marginCmTextFromMm(row && row.glass_margin_top_mm),
            bottom: marginCmTextFromMm(row && row.glass_margin_bottom_mm),
            right: marginCmTextFromMm(row && row.glass_margin_right_mm),
            left: marginCmTextFromMm(row && row.glass_margin_left_mm),
        };
    }

    function previewSides(widthCm, lengthCm, sidesCm, mode) {
        const sidesMm = {};
        for (const key of ["top", "bottom", "right", "left"]) {
            const text = String((sidesCm && sidesCm[key]) ?? "").trim();
            if (!text) return { status: "empty", opening: null };
            const millimeters = marginMmFromCm(text);
            if (millimeters == null) return { status: "invalid", opening: null };
            sidesMm[key] = millimeters;
        }
        const opening = openingFromSides(widthCm, lengthCm, sidesMm, mode || MODE_SIDES);
        if (!isPositiveOpening(opening)) return { status: "invalid", opening };
        return { status: "valid", opening };
    }

    function approvedState(row) {
        if (readMode(row) === MODE_SIDES) {
            return previewSides(row && row.width_cm, row && row.length_cm, storedSideCm(row), MODE_SIDES);
        }
        return previewState(row && row.width_cm, row && row.length_cm, approvedMarginText(row));
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
        const state = approvedState(row);
        const valid = state.status === "valid";
        const summary = valid
            ? (readMode(row) === MODE_SIDES
                ? `${marginCmTextFromMm(state.opening.topMm)}/${marginCmTextFromMm(state.opening.bottomMm)}/${marginCmTextFromMm(state.opening.rightMm)}/${marginCmTextFromMm(state.opening.leftMm)} ${__("cm")}`
                : `${marginCmTextFromMm(state.opening.marginMm)} ${__("cm")}`)
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
            const left = ((state.opening.leftMm ?? state.opening.marginMm) / MM_PER_CM) * scale;
            const top = ((state.opening.topMm ?? state.opening.marginMm) / MM_PER_CM) * scale;
            const innerWidth = (state.opening.openingWidthMm / MM_PER_CM) * scale;
            const innerHeight = (state.opening.openingLengthMm / MM_PER_CM) * scale;
            if (innerWidth > 0 && innerHeight > 0) {
                opening = `<rect class="dco-glass-opening" x="${round(x + left)}" y="${round(y + top)}" width="${round(innerWidth)}" height="${round(innerHeight)}"></rect>
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

    function sideField(name, label) {
        return `<label class="dco-glass-field">
            <span>${escapeHtml(label)}</span>
            <span class="dco-glass-input-shell">
                <input type="number" inputmode="decimal" step="any" data-glass-side="${name}" aria-label="${escapeHtml(label)}">
                <span>${__("cm")}</span>
            </span>
        </label>`;
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
                <div class="dco-glass-mode" role="radiogroup" aria-label="${escapeHtml(__("Glass Margin Mode"))}">
                    <label><input type="radio" name="dco-glass-margin-mode" value="${MODE_ALL}" data-glass-mode="${MODE_ALL}">${escapeHtml(__("All Directions"))}</label>
                    <label><input type="radio" name="dco-glass-margin-mode" value="${MODE_SIDES}" data-glass-mode="${MODE_SIDES}">${escapeHtml(__("Individual Sides"))}</label>
                </div>
                <label class="dco-glass-field" data-glass-uniform>
                    <span>${__("Glass Margin")}</span>
                    <span class="dco-glass-input-shell">
                        <input type="number" inputmode="decimal" step="any" data-glass-margin aria-label="${escapeHtml(__("Glass Margin"))}">
                        <span>${__("cm")}</span>
                    </span>
                </label>
                <div class="dco-glass-sides" data-glass-sides hidden>
                    ${sideField("top", __("Top Margin"))}
                    ${sideField("bottom", __("Bottom Margin"))}
                    ${sideField("right", __("Right Margin"))}
                    ${sideField("left", __("Left Margin"))}
                </div>
                <div class="dco-glass-readout">
                    <span>${__("Opening Width")}<b data-opening-width>—</b></span>
                    <span>${__("Opening Length")}<b data-opening-length>—</b></span>
                </div>
                <p class="dco-glass-help" data-glass-help></p>
            </section>
        </div>`;
    }

    function commitValues(frm, row, values) {
        const editor = window.AlmdinaClippedCornerEditor;
        const write = async () => {
            if (editor && typeof editor.commitChildValues === "function") {
                return editor.commitChildValues(frm, row, values);
            }
            await frappe.model.set_value(row.doctype, row.name, values);
            return row;
        };
        if (editor && typeof editor.queueChildApply === "function") {
            return editor.queueChildApply(frm, write);
        }
        return write().then((value) => ({ ok: true, value })).catch((error) => ({ ok: false, error }));
    }

    function commitMargin(frm, row, marginMm) {
        return commitValues(frm, row, {
            glass_margin_mode: MODE_ALL,
            glass_margin_mm: marginMm,
            glass_margin_top_mm: 0,
            glass_margin_bottom_mm: 0,
            glass_margin_right_mm: 0,
            glass_margin_left_mm: 0,
        });
    }

    function readForm(root) {
        const selected = root && root.querySelector("[data-glass-mode]:checked");
        const mode = selected ? selected.value : MODE_ALL;
        const valueOf = (selector) => {
            const node = root && root.querySelector(selector);
            return node ? node.value : "";
        };
        return {
            mode,
            margin: valueOf("[data-glass-margin]"),
            top: valueOf('[data-glass-side="top"]'),
            bottom: valueOf('[data-glass-side="bottom"]'),
            right: valueOf('[data-glass-side="right"]'),
            left: valueOf('[data-glass-side="left"]'),
        };
    }

    function formState(row, form) {
        if (!form || form.mode !== MODE_SIDES) {
            return previewState(row && row.width_cm, row && row.length_cm, form ? form.margin : "");
        }
        return previewSides(row && row.width_cm, row && row.length_cm, form, MODE_SIDES);
    }

    function applyForm(row, form) {
        if (!form || form.mode !== MODE_SIDES) return applyDraft(row, form ? form.margin : "");
        const state = formState(row, form);
        if (state.status !== "valid" || !state.opening) {
            return { ok: false, error: "invalid_glass_margin", save: false };
        }
        const opening = state.opening;
        return {
            ok: true,
            save: false,
            glass_margin_mm: opening.marginMm || 0,
            values: {
                glass_margin_mode: MODE_SIDES,
                glass_margin_mm: opening.marginMm || 0,
                glass_margin_top_mm: opening.topMm,
                glass_margin_bottom_mm: opening.bottomMm,
                glass_margin_right_mm: opening.rightMm,
                glass_margin_left_mm: opening.leftMm,
            },
        };
    }

    function showMode(root, mode) {
        const sides = root.querySelector("[data-glass-sides]");
        const uniform = root.querySelector("[data-glass-uniform]");
        if (sides) sides.hidden = mode !== MODE_SIDES;
        if (uniform) uniform.hidden = mode === MODE_SIDES;
        root.querySelectorAll("[data-glass-mode]").forEach((node) => {
            node.checked = node.value === mode;
        });
    }

    function paintForm(root, row) {
        const form = readForm(root);
        const state = formState(row, form);
        const preview = root.querySelector("[data-glass-preview]");
        if (preview) preview.innerHTML = previewSvg(row && row.width_cm, row && row.length_cm, state);
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
        showMode(root, form.mode);
        return state;
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
                const latestRow = currentRow();
                const form = root ? readForm(root) : { mode: MODE_ALL, margin: "" };
                if (!latestRow || !isGlass(latestRow)) {
                    frappe.msgprint({
                        title: __("Invalid Glass Margin"),
                        message: __("Invalid Glass Margin"),
                        indicator: "orange",
                    });
                    return Promise.resolve(false);
                }
                const decision = applyForm(latestRow, form);
                if (!decision.ok) {
                    if (root) paintForm(root, latestRow);
                    frappe.msgprint({
                        title: __("Invalid Glass Margin"),
                        message: __("Invalid Glass Margin"),
                        indicator: "orange",
                    });
                    return Promise.resolve(false);
                }
                if (typeof dialog.disable_primary_action === "function") dialog.disable_primary_action();
                return Promise.resolve(commitValues(frm, latestRow, decision.values)).then((result) => {
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
        const latest = currentRow() || row;
        const initialMode = readMode(latest);
        const initialSides = storedSideCm(latest);
        field.$wrapper.html(editorHtml());
        const root = field.$wrapper.find(".dco-glass-editor").get(0);
        const marginInput = root.querySelector("[data-glass-margin]");
        if (marginInput) marginInput.value = approvedMarginText(latest);
        ["top", "bottom", "right", "left"].forEach((name) => {
            const sideInput = root.querySelector(`[data-glass-side="${name}"]`);
            if (sideInput) sideInput.value = initialSides[name];
        });
        showMode(root, initialMode);
        paintForm(root, latest);
        if (readOnly) {
            root.querySelectorAll("input").forEach((input) => {
                input.disabled = true;
            });
            return;
        }
        root.addEventListener("input", () => {
            paintForm(root, currentRow() || row);
        });
        root.addEventListener("change", (event) => {
            const mode = event.target && event.target.getAttribute && event.target.getAttribute("data-glass-mode");
            if (!mode) return;
            if (mode === MODE_SIDES) {
                const shared = (root.querySelector("[data-glass-margin]") || {}).value || "";
                ["top", "bottom", "right", "left"].forEach((name) => {
                    const sideInput = root.querySelector(`[data-glass-side="${name}"]`);
                    if (sideInput) sideInput.value = shared;
                });
            }
            showMode(root, mode);
            paintForm(root, currentRow() || row);
        });
    }

    function view(frm, row) {
        return open(frm, row, { readOnly: true });
    }

    window.AlmdinaGlassShape = Object.freeze({
        GLASS_TYPE,
        MM_PER_CM,
        DEFAULT_GLASS_MARGIN_MM,
        isGlass,
        applyNewGlassMargin,
        openingMm,
        openingFromSides,
        previewState,
        applyDraft,
        applyForm,
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
