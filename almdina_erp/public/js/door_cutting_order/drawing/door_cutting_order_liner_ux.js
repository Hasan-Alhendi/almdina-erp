/* Liner settings dialog. Reuses the clipped-corner dialog shell and styles. */
(() => {
    "use strict";

    if (window.AlmdinaLinerEditor) return;

    const geometry = () => window.AlmdinaLinerGeometry;
    const LINER_ADDON = Object.freeze({
        kind: "liner",
        layer: "Liner",
        enabled: "extra_liner",
        side: "liner_reference_side",
        offset: "liner_offset_cm",
        width: "liner_width_cm",
        start: "liner_start_cm",
        length: "liner_length_cm",
        title: "Liner",
        nounAr: "اللاينر",
    });

    function addonFor(kind) {
        const engine = window.AlmdinaMachiningOverlay;
        const resolved = engine && typeof engine.addon === "function" ? engine.addon(kind || "liner") : null;
        return resolved || LINER_ADDON;
    }

    function noun(kind) {
        return addonFor(kind).nounAr || "اللاينر";
    }

    function localize(text, kind) {
        const resolved = __(text);
        if (!kind || kind === "liner") return resolved;
        return String(resolved).replaceAll("اللاينر", noun(kind)).replaceAll("Liner", noun(kind));
    }
    const MESSAGES = {
        missing_dimensions: "أدخل عرض الدرفة وطولها قبل ضبط اللاينر.",
        missing_corner: "اضبط زاوية الدرفة أولًا، ثم حدّد اللاينر.",
        invalid_corner: "موضع الزاوية غير صالح للاينر.",
        side_unavailable: "الجهة المختارة غير متاحة لهذا النوع من الدرفات.",
        choose_side: "Choose a reference side.",
        offset_invalid: "المسافة يجب أن تكون صفرًا أو أكبر.",
        width_invalid: "عرض اللاينر يجب أن يكون أكبر من صفر.",
        strip_outside: "اللاينر يخرج خارج الدرفة. قلّل المسافة أو العرض.",
        liner_start_invalid: "Liner start must be zero or greater.",
        liner_length_invalid: "Liner length must be greater than zero.",
        liner_span_exceeds_edge: "Liner start plus length exceeds the reference side.",
        liner_flat_end_unmachinable: "A flat end cannot be machined with this bit and length.",
        liner_span_on_corner: "The liner limit sits on a bend that has no single direction.",
    };

    const DIRECTION = {
        edge_long_right: "Top to bottom",
        edge_long_left: "Top to bottom",
        edge_width_top: "Left to right",
        edge_width_bottom: "Left to right",
    };

    function edgeCm(piece, side) {
        const path = (geometry().edgePaths(piece) || {})[side] || [];
        let length = 0;
        for (let index = 1; index < path.length; index += 1) {
            length += Math.hypot(path[index][0] - path[index - 1][0], path[index][1] - path[index - 1][1]);
        }
        return length / 10;
    }

    function num(value) {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function rounded(value) {
        return Math.round(num(value) * 10) / 10;
    }

    function esc(value) {
        return frappe.utils.escape_html(value == null ? "" : String(value));
    }

    function dimensions(row) {
        return {
            width: num(row && row.cut_width_cm) || num(row && row.width_cm),
            length: num(row && row.cut_length_cm) || num(row && row.length_cm),
        };
    }

    function draftFromRow(row, kind, options) {
        const api = geometry();
        const addon = addonFor(kind);
        const piece = api.pieceFromRow(row);
        const sides = api.availableSides(piece.pieceType);
        const rawSide = row && row[addon.side] ? String(row[addon.side]) : "";
        const validStored = Boolean(rawSide) && sides.includes(rawSide);
        let side = "";
        if (validStored) side = rawSide;
        else if (!rawSide && !(options && options.blankWhenMissing)) side = sides[0] || "";
        const edge = edgeCm(piece, side);
        const storedLength = num(row && row[addon.length]);
        return {
            piece,
            row,
            kind: addon.kind,
            side,
            offsetCm: rawSide ? num(row[addon.offset]) : 2,
            widthCm: rawSide ? num(row[addon.width]) : 1.5,
            startCm: rawSide ? num(row && row[addon.start]) : 0,
            lengthCm: rawSide && storedLength > 0 ? storedLength : edge,
            edgeCm: edge,
            enabled: Boolean(Number(row && row[addon.enabled])),
        };
    }

    function validationMessage(draft) {
        if (!draft || !draft.side) return localize(MESSAGES.choose_side, draft && draft.kind);
        const code = geometry().validationCode(draft.piece, draft.side, draft.offsetCm, draft.widthCm);
        if (code) return localize(MESSAGES[code] || code, draft && draft.kind);
        try {
            geometry().centerlineMm(
                draft.piece,
                draft.side,
                draft.offsetCm,
                draft.widthCm,
                draft.startCm,
                draft.lengthCm
            );
        } catch (error) {
            return localize(MESSAGES[error.code] || error.code || "Liner settings are invalid.", draft && draft.kind);
        }
        return "";
    }

    function mapPoint(point, frame, piece) {
        return [
            frame.x + ((point[0] / (piece.widthCm * 10)) * frame.width),
            frame.y + ((point[1] / (piece.lengthCm * 10)) * frame.height),
        ];
    }

    function pointsAttr(points) {
        return points.map(point => `${rounded(point[0])},${rounded(point[1])}`).join(" ");
    }

    function machiningTone(kind) {
        if (kind === "back_groove") return { fill: "rgba(15,122,74,.2)", stroke: "#0f7a4a" };
        if (kind === "recessed_handle_cutout") return { fill: "rgba(194,106,18,.2)", stroke: "#c26a12" };
        return { fill: "rgba(29,111,191,.22)", stroke: "#1d6fbf" };
    }

    function machiningLayer(draft, frame, piece, role) {
        const api = geometry();
        const paths = api.edgePaths(piece);
        if (!draft || !draft.side || !paths[draft.side] || validationMessage(draft)) return "";
        const tone = role === "legacy"
            ? { fill: "rgba(29,111,191,.22)", stroke: "#1d6fbf" }
            : machiningTone(draft.kind);
        const width = role === "active" ? 2.2 : (role === "quiet" ? 1.2 : 1.4);
        let center = "";
        try {
            const line = api.centerlineMm(
                piece,
                draft.side,
                draft.offsetCm,
                draft.widthCm,
                draft.startCm,
                draft.lengthCm
            ).map(point => mapPoint(point, frame, piece));
            center = `<polyline data-liner-center="1" data-machining-kind="${esc(draft.kind)}" points="${pointsAttr(line)}" fill="none" stroke="${tone.stroke}" stroke-width="${role === "quiet" ? 1.2 : 1.8}" stroke-dasharray="5 3" stroke-linecap="butt"/>`;
        } catch (error) {
            center = "";
        }
        const polygon = api.stripPolygonMm(piece, draft.side, draft.offsetCm, draft.widthCm)
            .map(point => mapPoint(point, frame, piece));
        const strip = `<polygon class="dco-liner-strip" data-liner-strip="1" data-machining-kind="${esc(draft.kind)}" data-machining-role="${esc(role)}" points="${pointsAttr(polygon)}" fill="${tone.fill}" stroke="${tone.stroke}" stroke-width="${width}"/>`;
        if (role === "quiet") return `${strip}${center}`;
        const reference = paths[draft.side].map(point => mapPoint(point, frame, piece));
        const near = polygon.slice(0, reference.length);
        const far = polygon.slice(reference.length).slice().reverse();
        const anchor = Math.floor(reference.length / 2);
        const from = reference[Math.min(anchor, reference.length - 1)];
        const mid = near[Math.min(anchor, near.length - 1)];
        const to = far[Math.min(anchor, far.length - 1)];
        let measures = "";
        if (from && mid && to) {
            measures = `
                <line class="dco-liner-measure" data-liner-offset-line="1" x1="${rounded(from[0])}" y1="${rounded(from[1])}" x2="${rounded(mid[0])}" y2="${rounded(mid[1])}" stroke="#9a6207" stroke-width="1.2"/>
                <line class="dco-liner-measure" data-liner-width-line="1" x1="${rounded(mid[0])}" y1="${rounded(mid[1])}" x2="${rounded(to[0])}" y2="${rounded(to[1])}" stroke="${tone.stroke}" stroke-width="1.2"/>
                <text data-liner-offset-label="1" x="${rounded((from[0] + mid[0]) / 2)}" y="${rounded((from[1] + mid[1]) / 2) - 4}" font-size="11" fill="#9a6207">${rounded(draft.offsetCm)}</text>
                <text data-liner-width-label="1" x="${rounded((mid[0] + to[0]) / 2)}" y="${rounded((mid[1] + to[1]) / 2) - 4}" font-size="11" fill="${tone.stroke}">${rounded(draft.widthCm)}</text>`;
        }
        return `${strip}${center}${measures}`;
    }

    function previewScene(draft) {
        const api = geometry();
        const piece = draft.piece;
        const corner = window.AlmdinaClippedCornerGeometry;
        const frame = corner && typeof corner.previewFrame === "function"
            ? corner.previewFrame(piece.widthCm, piece.lengthCm)
            : { x: 30, y: 30, width: 300, height: 180, scale: 1 };
        const outline = api.piecePolygonMm(piece).map(point => mapPoint(point, frame, piece));
        const source = draft.row || {};
        const cornerPiece = corner && typeof corner.isCornerCut === "function" && corner.isCornerCut(source);
        const bands = cornerPiece && typeof corner.edgeBandSvgMarkup === "function"
            ? corner.edgeBandSvgMarkup(source, frame.width, frame.height, {
                offsetX: frame.x,
                offsetY: frame.y,
                inheritStroke: false,
                color: "#b42318",
                strokeWidth: 3,
            })
            : [
                [Number(source.edge_width_top), [[frame.x, frame.y], [frame.x + frame.width, frame.y]]],
                [Number(source.edge_width_bottom), [[frame.x, frame.y + frame.height], [frame.x + frame.width, frame.y + frame.height]]],
                [Number(source.edge_long_left), [[frame.x, frame.y], [frame.x, frame.y + frame.height]]],
                [Number(source.edge_long_right), [[frame.x + frame.width, frame.y], [frame.x + frame.width, frame.y + frame.height]]],
            ].filter(entry => entry[0]).map((entry, index) => (
                `<polyline data-liner-edge="1" data-liner-edge-index="${index}" points="${pointsAttr(entry[1])}" fill="none" stroke="#b42318" stroke-width="3" stroke-linecap="round"/>`
            )).join("");
        return { api, piece, frame, outline, bands };
    }

    function previewSvg(draft, options) {
        const scene = previewScene(draft);
        const multi = Boolean(options && options.multi);
        const quiet = multi
            ? (options.companions || []).filter(item => (
                item && item.enabled && item.kind !== draft.kind
            )).map(item => machiningLayer(item, scene.frame, scene.piece, "quiet")).join("")
            : "";
        const active = multi
            ? (draft.enabled ? machiningLayer(draft, scene.frame, scene.piece, "active") : "")
            : machiningLayer(draft, scene.frame, scene.piece, "legacy");
        const hits = multi ? "" : scene.api.availableSides(scene.piece.pieceType).map(side => {
            const path = scene.api.edgePaths(scene.piece)[side];
            if (!path) return "";
            const selected = side === draft.side;
            return `<polyline class="dco-liner-side ${selected ? "is-selected" : ""}" data-liner-side="${side}" points="${pointsAttr(path.map(point => mapPoint(point, scene.frame, scene.piece)))}" fill="none" stroke="${selected ? "#9a6207" : "transparent"}" stroke-width="${selected ? 4 : 12}" stroke-linecap="round"/>`;
        }).join("");
        const label = multi ? __("Piece preview") : __("Liner preview");
        return `<svg viewBox="0 0 420 280" dir="ltr" role="img" aria-label="${esc(label)}">
            <polygon points="${pointsAttr(scene.outline)}" fill="#fff7e8" stroke="#8a5700" stroke-width="2"/>
            ${scene.bands}
            ${hits}
            ${quiet}
            ${active}
            <text x="210" y="268" text-anchor="middle" font-size="12" fill="#536577">${rounded(scene.piece.widthCm)} × ${rounded(scene.piece.lengthCm)} ${esc(__("cm"))}</text>
        </svg>`;
    }

    function controlsHtml(draft) {
        const api = geometry();
        const sides = api.availableSides(draft.piece.pieceType).map(side => `
            <button type="button" class="dco-corner-position ${side === draft.side ? "is-active" : ""}" data-liner-side="${side}" aria-pressed="${side === draft.side ? "true" : "false"}">
                ${esc(api.sideLabel(side, draft.piece.pieceType))}
            </button>`).join("");
        const addon = addonFor(draft.kind);
        const widthLabel = addon.kind === "liner" ? __("Liner Width") : __("Machining Width");
        const startLabel = addon.kind === "liner" ? __("Liner Start Position") : __("Machining Start");
        const lengthLabel = addon.kind === "liner" ? __("Liner Length") : __("Machining Length");
        return `<div data-liner-fields data-machining-kind="${esc(addon.kind)}">
                <div class="dco-corner-section-label">${esc(__("Reference Side"))}</div>
                <div class="dco-corner-position-grid" data-liner-sides>${sides}</div>
                <div class="dco-corner-section-label">${esc(__("Distance and width"))}</div>
                <div class="dco-corner-input-grid">
                    <div class="dco-corner-input-wrap">
                        <label>${esc(__("Edge Offset"))}</label>
                        <div class="dco-corner-input-shell"><input type="number" min="0" step="0.1" data-liner-offset value="${rounded(draft.offsetCm)}"><span>${esc(__("cm"))}</span></div>
                    </div>
                    <div class="dco-corner-input-wrap">
                        <label>${esc(widthLabel)}</label>
                        <div class="dco-corner-input-shell"><input type="number" min="0.1" step="0.1" data-liner-width value="${rounded(draft.widthCm)}"><span>${esc(__("cm"))}</span></div>
                    </div>
                    <div class="dco-corner-input-wrap">
                        <label>${esc(startLabel)}</label>
                        <div class="dco-corner-input-shell"><input type="number" min="0" step="0.1" data-liner-start value="${rounded(draft.startCm)}"><span>${esc(__("cm"))}</span></div>
                    </div>
                    <div class="dco-corner-input-wrap">
                        <label>${esc(lengthLabel)}</label>
                        <div class="dco-corner-input-shell"><input type="number" min="0.1" step="0.1" data-liner-length value="${rounded(draft.lengthCm)}"><span>${esc(__("cm"))}</span></div>
                    </div>
                </div>
                <div class="dco-corner-help" data-liner-available>${esc(__("Available Length"))}: ${rounded(draft.edgeCm)} ${esc(__("cm"))}</div>
                <div class="dco-corner-help" data-liner-direction>${esc(__("Measurement Direction"))}: ${esc(__(DIRECTION[draft.side] || "Along the selected edge"))}</div>
                <div class="dco-corner-help" data-liner-help></div>
            </div>`;
    }

    function editorHtml(row, draft) {
        const addon = addonFor(draft.kind);
        const removeLabel = addon.kind === "liner" ? __("Remove liner") : __("Remove add-on");
        const remove = draft.enabled
            ? `<button type="button" class="btn btn-default btn-sm" data-liner-remove>${esc(removeLabel)}</button>`
            : "";
        return `<div class="dco-corner-editor" data-liner-editor data-machining-kind="${esc(addon.kind)}">
            <section class="dco-corner-preview-panel">
                <div class="dco-corner-preview-head">
                    <span class="dco-corner-badge">${esc(__(addon.title))}</span>
                </div>
                <div class="dco-corner-preview" data-liner-preview>${previewSvg(draft)}</div>
            </section>
            <section class="dco-corner-controls">
                ${controlsHtml(draft)}
                <button type="button" class="btn btn-default btn-sm" data-liner-cancel>${esc(__("Cancel"))}</button>
                ${remove}
            </section>
        </div>`;
    }

    function selectSide(draft, piece, nextSide) {
        const previousEdge = draft.edgeCm;
        const previousLength = draft.lengthCm;
        const previousStart = draft.startCm;
        const nextEdge = edgeCm(piece, nextSide);
        const wasFull = previousStart <= 0.05 && Math.abs(previousLength - previousEdge) < 0.05;
        draft.side = nextSide;
        draft.edgeCm = nextEdge;
        if (wasFull || draft.startCm + draft.lengthCm > nextEdge + 0.05) {
            if (wasFull || draft.startCm >= nextEdge) draft.startCm = 0;
            draft.lengthCm = Math.max(0.1, nextEdge - draft.startCm);
        }
        return draft;
    }

    function readDraft(root, piece, enabled, row, kind) {
        const offset = root.querySelector("[data-liner-offset]");
        const width = root.querySelector("[data-liner-width]");
        const start = root.querySelector("[data-liner-start]");
        const length = root.querySelector("[data-liner-length]");
        const active = root.querySelector("[data-liner-sides] .is-active");
        const side = active ? active.getAttribute("data-liner-side") : "";
        return {
            piece,
            row: row || null,
            kind: kind || "liner",
            side,
            offsetCm: offset ? Number(offset.value) : NaN,
            widthCm: width ? Number(width.value) : NaN,
            startCm: start ? Number(start.value) : 0,
            lengthCm: length ? Number(length.value) : NaN,
            edgeCm: edgeCm(piece, side),
            enabled,
        };
    }

    function paint(root, draft, dialog) {
        const preview = root.querySelector("[data-liner-preview]");
        if (preview) preview.innerHTML = previewSvg(draft);
        root.querySelectorAll("[data-liner-sides] [data-liner-side]").forEach(button => {
            const selected = button.getAttribute("data-liner-side") === draft.side;
            button.classList.toggle("is-active", selected);
            button.setAttribute("aria-pressed", selected ? "true" : "false");
        });
        const help = root.querySelector("[data-liner-help]");
        const available = root.querySelector("[data-liner-available]");
        const direction = root.querySelector("[data-liner-direction]");
        const message = validationMessage(draft);
        if (available) available.textContent = `${__("Available Length")}: ${rounded(draft.edgeCm)} ${__("cm")}`;
        if (direction) {
            direction.textContent = `${__("Measurement Direction")}: ${__(DIRECTION[draft.side] || "Along the selected edge")}`;
        }
        if (help) help.textContent = message;
        if (dialog && dialog.get_primary_btn) {
            dialog.get_primary_btn().prop("disabled", Boolean(message));
        }
        return message;
    }

    function refreshTable(frm) {
        if (window.AlmdinaDoorCuttingFastEntry && window.AlmdinaDoorCuttingFastEntry.render) {
            window.AlmdinaDoorCuttingFastEntry.render(frm);
        }
    }

    function hostPiece(frm, row) {
        const api = geometry();
        const piece = api.pieceFromRow(row);
        const size = dimensions(row);
        piece.widthCm = size.width || piece.widthCm;
        piece.lengthCm = size.length || piece.lengthCm;
        if (typeof api.contourNotchFromOrder === "function") {
            const notch = api.contourNotchFromOrder(frm, row);
            piece.cutWidthCm = notch.cutWidthCm;
            piece.cutLengthCm = notch.cutLengthCm;
        }
        return piece;
    }

    function failureText(error, kind) {
        if (!error) {
            return addonFor(kind).kind === "liner"
                ? __("Could not save the liner.")
                : __("Could not save the add-on.");
        }
        return String(error.message || error);
    }

    function valuesFor(kind, draft, enabled) {
        const addon = addonFor(kind || (draft && draft.kind));
        const values = {};
        values[addon.enabled] = enabled ? 1 : 0;
        values[addon.side] = enabled ? draft.side : "";
        values[addon.offset] = enabled ? draft.offsetCm : 0;
        values[addon.width] = enabled ? draft.widthCm : 0;
        values[addon.start] = enabled ? draft.startCm : 0;
        values[addon.length] = enabled ? draft.lengthCm : 0;
        return values;
    }

    const applyGate = { running: false };

    async function writeLiner(frm, sourceRow, values, kind) {
        const editor = window.AlmdinaClippedCornerEditor;
        const row = editor && typeof editor.resolveChildRow === "function"
            ? editor.resolveChildRow(frm, sourceRow)
            : sourceRow;
        if (!row) {
            frappe.msgprint({
                title: __(addonFor(kind).title),
                message: __("This door piece is no longer in the order."),
                indicator: "orange",
            });
            return false;
        }
        const api = geometry();
        if (!api.availableSides(row.piece_type || "Regular").length) {
            frappe.msgprint({
                title: __(addonFor(kind).title),
                message: addonFor(kind).kind === "liner"
                    ? __("This piece type no longer supports a liner.")
                    : __("This piece type does not support this add-on."),
                indicator: "orange",
            });
            return false;
        }
        const addon = addonFor(kind);
        if (Number(values[addon.enabled])) {
            const piece = hostPiece(frm, row);
            const code = api.validationCode(
                piece,
                values[addon.side],
                values[addon.offset],
                values[addon.width]
            );
            if (code) {
                frappe.msgprint({
                    title: addon.kind === "liner" ? __("Check liner") : __("Check add-on"),
                    message: localize(MESSAGES[code] || code, addon.kind),
                    indicator: "orange",
                });
                return false;
            }
        }
        if (!editor || typeof editor.commitChildValues !== "function") {
            await frappe.model.set_value(row.doctype, row.name, values);
        } else {
            await editor.commitChildValues(frm, row, values);
        }
        frm.dirty();
        refreshTable(frm);
        return true;
    }

    async function applyLiner(frm, sourceRow, values, kind) {
        if (applyGate.running) return false;
        applyGate.running = true;
        const editor = window.AlmdinaClippedCornerEditor;
        const queued = editor && typeof editor.queueChildApply === "function"
            ? editor.queueChildApply(frm, () => writeLiner(frm, sourceRow, values, kind))
            : writeLiner(frm, sourceRow, values, kind);
        try {
            const result = await queued;
            if (result && typeof result.ok === "boolean") {
                if (!result.ok) {
                    frappe.msgprint({
                    title: __(addonFor(kind).title),
                    message: failureText(result.error, kind),
                        indicator: "red",
                    });
                    return false;
                }
                return result.value !== false;
            }
            return result !== false;
        } catch (error) {
            frappe.msgprint({
            title: __(addonFor(kind).title),
            message: failureText(error, kind),
                indicator: "red",
            });
            return false;
        } finally {
            applyGate.running = false;
        }
    }

    let activeDialog = null;

    function open(frm, row, kind) {
        const api = geometry();
        if (!frm || !row || !api) return false;
        if ((row.piece_type || "Regular") === "Special") return false;
        if (!api.availableSides(row.piece_type || "Regular").length) return false;
        const size = dimensions(row);
        if (!size.width || !size.length) {
            frappe.msgprint({
                title: __("Enter dimensions first"),
                message: __("Enter the piece width and length before editing the liner."),
                indicator: "orange",
            });
            return false;
        }
        const cornerEditor = window.AlmdinaClippedCornerEditor;
        if (cornerEditor && typeof cornerEditor.ensureStyles === "function") cornerEditor.ensureStyles();
        if (activeDialog) {
            try { activeDialog.hide(); } catch (error) { /* previous dialog */ }
            activeDialog = null;
        }
        const addon = addonFor(kind);
        const piece = hostPiece(frm, row);
        let draft = draftFromRow(row, addon.kind);
        draft.piece = piece;
        const title = addon.kind === "liner"
            ? __("Liner — Door piece {0}", [row.piece_no || row.idx || ""])
            : __("{0} — Door piece {1}", [__(addon.title), row.piece_no || row.idx || ""]);
        const dialog = new frappe.ui.Dialog({
            title,
            fields: [{ fieldname: "liner_editor", fieldtype: "HTML" }],
            primary_action_label: __("Save"),
            primary_action() {
                const root = dialog.$wrapper.find("[data-liner-editor]").get(0);
                if (!root) return;
                draft = readDraft(root, piece, true, row, addon.kind);
                const message = paint(root, draft, dialog);
                if (message) {
                    frappe.msgprint({
                        title: addon.kind === "liner" ? __("Check liner") : __("Check add-on"),
                        message,
                        indicator: "orange",
                    });
                    return Promise.resolve(false);
                }
                const button = dialog.get_primary_btn && dialog.get_primary_btn();
                if (button) button.prop("disabled", true);
                return applyLiner(frm, row, valuesFor(addon.kind, draft, true), addon.kind).then(saved => {
                    if (saved) dialog.hide();
                    else if (button) button.prop("disabled", Boolean(paint(root, draft, dialog)));
                });
            },
        });
        activeDialog = dialog;
        dialog.$wrapper.addClass("dco-clipped-corner-modal");
        dialog.show();
        const field = dialog.get_field("liner_editor");
        field.$wrapper.html(editorHtml(row, draft));
        const root = field.$wrapper.find("[data-liner-editor]").get(0);
        paint(root, draft, dialog);
        root.addEventListener("click", (event) => {
            const side = event.target.closest("[data-liner-side]");
            if (side && root.contains(side)) {
                draft = readDraft(root, piece, draft.enabled, row, addon.kind);
                draft = selectSide(draft, piece, side.getAttribute("data-liner-side"));
                const startInput = root.querySelector("[data-liner-start]");
                const lengthInput = root.querySelector("[data-liner-length]");
                if (startInput) startInput.value = rounded(draft.startCm);
                if (lengthInput) lengthInput.value = rounded(draft.lengthCm);
                paint(root, draft, dialog);
                return;
            }
            if (event.target.closest("[data-liner-cancel]")) {
                dialog.hide();
                return;
            }
            if (event.target.closest("[data-liner-remove]")) {
                const remove = event.target.closest("[data-liner-remove]");
                remove.disabled = true;
                applyLiner(frm, row, valuesFor(addon.kind, draft, false), addon.kind).then(saved => {
                    if (saved) dialog.hide();
                    else remove.disabled = false;
                });
            }
        });
        root.addEventListener("input", () => {
            draft = readDraft(root, piece, draft.enabled, row, addon.kind);
            paint(root, draft, dialog);
        });
        return true;
    }

    window.AlmdinaLinerEditor = Object.freeze({
        open,
        applyLiner,
        previewSvg,
        validationMessage,
        draftFromRow,
        valuesFor,
        controlsHtml,
        readDraft,
        selectSide,
        hostPiece,
        paint,
    });
})();
