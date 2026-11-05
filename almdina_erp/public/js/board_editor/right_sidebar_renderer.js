(() => {
    "use strict";

    function esc(value) {
        return frappe.utils.escape_html(String(value == null ? "" : value));
    }

    function alignIcon(mode) {
        // Local SVG marks modelled on common editor alignment glyphs (Figma-like).
        const strokes = {
            align_left: `
                <line x1="5" y1="4" x2="5" y2="20" />
                <rect x="8" y="6" width="10" height="4" rx="0.5" />
                <rect x="8" y="14" width="7" height="4" rx="0.5" />`,
            align_center_x: `
                <line x1="12" y1="4" x2="12" y2="20" />
                <rect x="7" y="6" width="10" height="4" rx="0.5" />
                <rect x="8.5" y="14" width="7" height="4" rx="0.5" />`,
            align_right: `
                <line x1="19" y1="4" x2="19" y2="20" />
                <rect x="6" y="6" width="10" height="4" rx="0.5" />
                <rect x="9" y="14" width="7" height="4" rx="0.5" />`,
            align_top: `
                <line x1="4" y1="5" x2="20" y2="5" />
                <rect x="6" y="8" width="4" height="10" rx="0.5" />
                <rect x="14" y="8" width="4" height="7" rx="0.5" />`,
            align_center_y: `
                <line x1="4" y1="12" x2="20" y2="12" />
                <rect x="6" y="7" width="4" height="10" rx="0.5" />
                <rect x="14" y="8.5" width="4" height="7" rx="0.5" />`,
            align_bottom: `
                <line x1="4" y1="19" x2="20" y2="19" />
                <rect x="6" y="6" width="4" height="10" rx="0.5" />
                <rect x="14" y="9" width="4" height="7" rx="0.5" />`,
        };
        const body = strokes[mode] || "";
        return `<svg class="icon icon-sm abe-tool-icon abe-align-icon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;
    }

    const ALIGN_TOOLS = Object.freeze([
        { mode: "align_left", label: "Align left", title: "Align left edges of the selection" },
        { mode: "align_center_x", label: "Align horizontal centers", title: "Align horizontal centers of the selection" },
        { mode: "align_right", label: "Align right", title: "Align right edges of the selection" },
        { mode: "align_top", label: "Align top", title: "Align top edges of the selection" },
        { mode: "align_center_y", label: "Align vertical centers", title: "Align vertical centers of the selection" },
        { mode: "align_bottom", label: "Align bottom", title: "Align bottom edges of the selection" },
    ]);

    function positionAxisField(axis, label, valueText, editable, options) {
        const opts = options || {};
        const disabled = editable ? "" : " disabled";
        const mixed = Boolean(opts.mixed);
        const stepMinus = mixed
            ? __("Nudge selected pieces −1 mm on {0}", [label])
            : __("Decrease {0} by 1 mm", [label]);
        const stepPlus = mixed
            ? __("Nudge selected pieces +1 mm on {0}", [label])
            : __("Increase {0} by 1 mm", [label]);
        const inputTitle = mixed
            ? __("Enter a relative millimetre offset for the selection (for example +5 or -2.5). Bare numbers mean a positive offset.")
            : label;
        const attrs = mixed ? ` data-abe-pos-mixed="1" placeholder="${esc(__("Mixed"))}"` : "";
        return `<div class="abe-pos-field abe-inspector-pos-field" data-abe-pos-axis="${esc(axis)}">
            <span class="abe-pos-axis-label" dir="ltr">${esc(label)}</span>
            <button type="button" class="alm-btn-secondary abe-tool-btn abe-pos-step" data-abe-pos-step="-1"${disabled} title="${esc(stepMinus)}" aria-label="${esc(stepMinus)}">−</button>
            <input type="text" inputmode="decimal" class="abe-pos-input" data-abe-pos-input="1" value="${esc(valueText)}"${disabled}${attrs} aria-label="${esc(label)}" title="${esc(inputTitle)}" dir="ltr" />
            <button type="button" class="alm-btn-secondary abe-tool-btn abe-pos-step" data-abe-pos-step="1"${disabled} title="${esc(stepPlus)}" aria-label="${esc(stepPlus)}">+</button>
        </div>`;
    }

    function alignmentSectionHtml(storeView) {
        // Always render all six tools; enablement comes only from AlignmentGeometry.
        const AG = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.AlignmentGeometry;
        const eligibility = AG && typeof AG.alignmentEligibility === "function"
            ? AG.alignmentEligibility(storeView.session, storeView.selectedPieceKeys || [])
            : { enabled: false };
        const enabled = Boolean(eligibility.enabled);
        const disabledTitle = eligibility.reason
            ? __(eligibility.reason)
            : __("Select two or more pieces to align them.");
        const buttons = ALIGN_TOOLS.map((tool) => {
            const title = enabled ? __(tool.title) : disabledTitle;
            const label = __(tool.label);
            return `<button type="button" class="alm-btn-secondary abe-tool-btn abe-align-btn" data-abe-align="${esc(tool.mode)}"${enabled ? "" : " disabled"} title="${esc(title)}" aria-label="${esc(label)}" aria-disabled="${enabled ? "false" : "true"}">${alignIcon(tool.mode)}</button>`;
        }).join("");
        return `<section class="abe-inspector-block abe-inspector-align-block" data-abe-align-section="1">
            <div class="abe-inspector-block-title">${esc(__("Alignment"))}</div>
            <div class="abe-inspector-align" role="group" aria-label="${esc(__("Alignment"))}">
                <div class="abe-align-grid">${buttons}</div>
            </div>
        </section>`;
    }

    function propertiesSectionHtml(storeView) {
        const PG = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.PositionGeometry;
        const session = storeView.session;
        const keys = Array.isArray(storeView.selectedPieceKeys)
            ? storeView.selectedPieceKeys.filter(Boolean)
            : [];
        if (!keys.length) {
            return `<section class="abe-inspector-block abe-inspector-props-block">
                <div class="abe-inspector-empty" role="status">${esc(__("Select a piece to edit its properties."))}</div>
            </section>`;
        }

        const positionModel = PG && typeof PG.selectionPositionModel === "function"
            ? PG.selectionPositionModel(session, keys)
            : null;
        const mixedLabel = (PG && PG.MIXED_LABEL) || "Mixed";

        if (keys.length > 1) {
            const editable = Boolean(positionModel && positionModel.editable);
            const note = positionModel && positionModel.reason
                ? `<div class="abe-inspector-note" role="status">${esc(__(positionModel.reason))}</div>`
                : "";
            return `<section class="abe-inspector-block abe-inspector-props-block">
                <div class="abe-inspector-position" data-abe-position-bar="1" data-abe-pos-mixed="1" role="group" aria-label="${esc(__("Precision piece position"))}">
                    <div class="abe-inspector-block-title">${esc(__("Position"))}</div>
                    <div class="abe-inspector-multi" role="status">
                        <span>${esc(__("{0} pieces selected", [String(keys.length)]))}</span>
                    </div>
                    ${positionAxisField("x", __("X (mm)"), mixedLabel, editable, { mixed: true })}
                    ${positionAxisField("y", __("Y (mm)"), mixedLabel, editable, { mixed: true })}
                    ${note}
                </div>
            </section>`;
        }

        const pieceKey = keys[0];
        const piece = session && session.pieces && session.pieces[pieceKey];
        if (!piece) {
            return `<section class="abe-inspector-block abe-inspector-props-block">
                <div class="abe-inspector-empty" role="status">${esc(__("Select a piece to edit its properties."))}</div>
            </section>`;
        }
        const format = PG && typeof PG.formatMm === "function" ? PG.formatMm : (value) => String(value);
        const dimsHelper = PG && typeof PG.pieceDimensionsMm === "function"
            ? PG.pieceDimensionsMm(piece)
            : { widthMm: 0, lengthMm: 0 };
        const label = piece.label || piece.piece_instance_id || String(piece.piece_id || "");
        const dims = `${format(dimsHelper.lengthMm)} × ${format(dimsHelper.widthMm)} mm`;
        let positionHtml = "";
        if (positionModel && !positionModel.mixed) {
            positionHtml = `<div class="abe-inspector-position" data-abe-position-bar="1" data-abe-pos-piece="${esc(positionModel.pieceKey)}" role="group" aria-label="${esc(__("Precision piece position"))}">
                <div class="abe-inspector-block-title">${esc(__("Position"))}</div>
                ${positionAxisField("x", __("X (mm)"), format(positionModel.x), Boolean(positionModel.editable))}
                ${positionAxisField("y", __("Y (mm)"), format(positionModel.y), Boolean(positionModel.editable))}
            </div>`;
        } else {
            positionHtml = `<div class="abe-inspector-note" role="status">${esc(__("Board X/Y is available for pieces placed on a board."))}</div>`;
        }
        const locked = piece.editable === false
            ? `<span class="abe-host-hint">${esc(__("Not editable"))}</span>`
            : "";
        return `<section class="abe-inspector-block abe-inspector-props-block">
            ${positionHtml}
            <div class="abe-inspector-piece">
                <div class="abe-inspector-block-title">${esc(__("Piece properties"))}</div>
                <div class="abe-inspector-meta">
                    <div class="abe-inspector-label" dir="ltr" title="${esc(label)}">${esc(label)}</div>
                    <div class="abe-inspector-dims" dir="ltr">${esc(dims)}</div>
                    ${locked}
                </div>
            </div>
        </section>`;
    }

    function bindPositionControls(host, handlers, model) {
        const bar = host && host.querySelector("[data-abe-position-bar]");
        if (!bar || !model) return;
        const PG = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.PositionGeometry;
        const format = PG && typeof PG.formatMm === "function" ? PG.formatMm : (value) => String(value);
        const parseAbsolute = PG && typeof PG.parseMm === "function" ? PG.parseMm : (text) => Number(text);
        const parseRelative = PG && typeof PG.parseRelativeOffset === "function"
            ? PG.parseRelativeOffset
            : parseAbsolute;
        const mixedLabel = (PG && PG.MIXED_LABEL) || "Mixed";
        const mixed = Boolean(model.mixed);
        const pieceKey = model.pieceKey;

        function displayFor(nextModel, axis) {
            if (!nextModel) return mixed ? mixedLabel : "0";
            if (nextModel.mixed) return mixedLabel;
            if (axis === "x" && nextModel.displayX != null) return nextModel.displayX;
            if (axis === "y" && nextModel.displayY != null) return nextModel.displayY;
            return format(nextModel[axis]);
        }

        function syncInputsFromModel(nextModel) {
            if (!nextModel) return;
            bar.querySelectorAll("[data-abe-pos-axis]").forEach((field) => {
                const axis = field.getAttribute("data-abe-pos-axis");
                const input = field.querySelector("[data-abe-pos-input]");
                if (!input || !axis) return;
                input.value = displayFor(nextModel, axis);
                input.dataset.abePosCommitted = input.value;
            });
        }

        syncInputsFromModel(model);

        bar.querySelectorAll("[data-abe-pos-input]").forEach((input) => {
            const field = input.closest("[data-abe-pos-axis]");
            const axis = field && field.getAttribute("data-abe-pos-axis");
            if (!axis) return;
            input.dataset.abePosCommitted = input.value;

            const commit = () => {
                if (!(handlers && handlers.applyPositionAxis)) return;
                const raw = input.value;
                if (mixed) {
                    const parsed = parseRelative(raw);
                    if (parsed == null) {
                        if (handlers.onPositionRejected) {
                            handlers.onPositionRejected(__("Enter a valid millimetre offset."));
                        }
                        input.value = input.dataset.abePosCommitted || mixedLabel;
                        return;
                    }
                    const result = handlers.applyPositionAxis(pieceKey, axis, parsed, { mixed: true });
                    if (!result || result.ok === false) {
                        input.value = input.dataset.abePosCommitted || mixedLabel;
                        return;
                    }
                    syncInputsFromModel(result.model || { mixed: true });
                    return;
                }
                const parsed = parseAbsolute(raw);
                if (parsed == null) {
                    if (handlers.onPositionRejected) {
                        handlers.onPositionRejected(__("Enter a valid millimetre value."));
                    }
                    input.value = input.dataset.abePosCommitted || format(model[axis]);
                    return;
                }
                const result = handlers.applyPositionAxis(pieceKey, axis, parsed);
                if (!result || result.ok === false) {
                    input.value = input.dataset.abePosCommitted || format(model[axis]);
                    return;
                }
                if (result.model) syncInputsFromModel(result.model);
                else input.dataset.abePosCommitted = format(parsed);
            };

            input.addEventListener("focus", () => {
                if (!mixed || input.disabled) return;
                // Keep focus; clear Mixed so the relative offset can be typed.
                if (String(input.value).toLowerCase() === mixedLabel.toLowerCase()) {
                    input.value = "";
                }
                input.select();
            });
            input.addEventListener("keydown", (event) => {
                if (event.key === " " || event.code === "Space" || event.key === "Delete") {
                    event.stopPropagation();
                }
                if (event.key === "Escape") {
                    event.preventDefault();
                    event.stopPropagation();
                    input.value = input.dataset.abePosCommitted || displayFor(model, axis);
                    input.blur();
                    return;
                }
                if (event.key === "Enter") {
                    event.preventDefault();
                    commit();
                    input.blur();
                }
            });
            input.addEventListener("wheel", (event) => {
                event.stopPropagation();
            });
            input.addEventListener("change", commit);
            input.addEventListener("blur", () => {
                if (mixed && !String(input.value).trim()) {
                    input.value = input.dataset.abePosCommitted || mixedLabel;
                    return;
                }
                if (String(input.value) !== String(input.dataset.abePosCommitted || "")) {
                    commit();
                }
            });
        });

        bar.querySelectorAll("[data-abe-pos-step]").forEach((button) => {
            const field = button.closest("[data-abe-pos-axis]");
            const axis = field && field.getAttribute("data-abe-pos-axis");
            const input = field && field.querySelector("[data-abe-pos-input]");
            const step = Number(button.getAttribute("data-abe-pos-step")) || 0;
            if (!axis || !input || !step) return;
            button.addEventListener("mousedown", (event) => {
                event.preventDefault();
            });
            button.addEventListener("click", () => {
                if (!(handlers && handlers.applyPositionAxis)) return;
                if (mixed) {
                    const result = handlers.applyPositionAxis(pieceKey, axis, step, { mixed: true, step: true });
                    const liveModel = handlers.readPositionModel && handlers.readPositionModel(pieceKey);
                    if (!result || result.ok === false) {
                        syncInputsFromModel(liveModel || model);
                        return;
                    }
                    syncInputsFromModel(result.model || liveModel || { mixed: true });
                    return;
                }
                const parsed = parseAbsolute(input.value);
                const liveModel = handlers.readPositionModel && handlers.readPositionModel(pieceKey);
                const base = parsed == null
                    ? Number((liveModel && liveModel[axis]) || model[axis]) || 0
                    : parsed;
                const result = handlers.applyPositionAxis(pieceKey, axis, base + step);
                if (!result || result.ok === false) {
                    syncInputsFromModel(liveModel || model);
                    return;
                }
                if (result.model) syncInputsFromModel(result.model);
            });
        });
    }

    function bindAlignmentControls(host, handlers) {
        if (!host) return;
        host.querySelectorAll("[data-abe-align]").forEach((button) => {
            button.addEventListener("click", () => {
                const mode = button.getAttribute("data-abe-align");
                if (!mode || button.disabled) return;
                if (handlers && handlers.applyAlignment) handlers.applyAlignment(mode);
            });
        });
    }

    function render(host, storeView, handlers) {
        if (!host) return;
        const PG = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.PositionGeometry;
        const keys = Array.isArray(storeView.selectedPieceKeys)
            ? storeView.selectedPieceKeys.filter(Boolean)
            : [];
        const positionModel = PG && typeof PG.selectionPositionModel === "function"
            ? PG.selectionPositionModel(storeView.session, keys)
            : null;

        // Alignment stays pinned at the top of the stack; properties follow tightly.
        host.innerHTML = `<div class="abe-right-sidebar" data-abe-right-sidebar="1">
            <div class="abe-section-scroll abe-inspector-scroll">
                ${alignmentSectionHtml(storeView)}
                ${propertiesSectionHtml(storeView)}
            </div>
        </div>`;

        bindPositionControls(host, handlers || {}, positionModel);
        bindAlignmentControls(host, handlers || {});
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.RightSidebarRenderer = Object.freeze({
        ALIGN_TOOLS,
        render,
    });
})();
