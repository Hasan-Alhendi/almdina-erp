/* Liner settings dialog. Reuses the clipped-corner dialog shell and styles. */
(() => {
    "use strict";

    if (window.AlmdinaLinerEditor) return;

    const geometry = () => window.AlmdinaLinerGeometry;
    const MESSAGES = {
        missing_dimensions: "أدخل عرض الدرفة وطولها قبل ضبط اللاينر.",
        missing_corner: "اضبط زاوية الدرفة أولًا، ثم حدّد اللاينر.",
        invalid_corner: "موضع الزاوية غير صالح للاينر.",
        side_unavailable: "الجهة المختارة غير متاحة لهذا النوع من الدرفات.",
        offset_invalid: "المسافة يجب أن تكون صفرًا أو أكبر.",
        width_invalid: "عرض اللاينر يجب أن يكون أكبر من صفر.",
        strip_outside: "اللاينر يخرج خارج الدرفة. قلّل المسافة أو العرض.",
    };

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

    function draftFromRow(row) {
        const api = geometry();
        const piece = api.pieceFromRow(row);
        const sides = api.availableSides(piece.pieceType);
        const stored = sides.includes(row.liner_reference_side) ? row.liner_reference_side : (sides[0] || "");
        return {
            piece,
            side: stored,
            offsetCm: row.liner_reference_side ? num(row.liner_offset_cm) : 2,
            widthCm: row.liner_reference_side ? num(row.liner_width_cm) : 1.5,
            enabled: Boolean(Number(row.extra_liner)),
        };
    }

    function validationMessage(draft) {
        const code = geometry().validationCode(draft.piece, draft.side, draft.offsetCm, draft.widthCm);
        return code ? (MESSAGES[code] || code) : "";
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

    function previewSvg(draft) {
        const api = geometry();
        const piece = draft.piece;
        const corner = window.AlmdinaClippedCornerGeometry;
        const frame = corner && typeof corner.previewFrame === "function"
            ? corner.previewFrame(piece.widthCm, piece.lengthCm)
            : { x: 30, y: 30, width: 300, height: 180, scale: 1 };
        const outline = api.piecePolygonMm(piece).map(point => mapPoint(point, frame, piece));
        const paths = api.edgePaths(piece);
        const message = validationMessage(draft);
        let strip = "";
        let measures = "";
        if (!message && draft.side && paths[draft.side]) {
            const polygon = api.stripPolygonMm(piece, draft.side, draft.offsetCm, draft.widthCm)
                .map(point => mapPoint(point, frame, piece));
            strip = `<polygon class="dco-liner-strip" data-liner-strip="1" points="${pointsAttr(polygon)}" fill="rgba(29,111,191,.22)" stroke="#1d6fbf" stroke-width="1.4"/>`;
            const reference = paths[draft.side].map(point => mapPoint(point, frame, piece));
            const near = polygon.slice(0, reference.length);
            const far = polygon.slice(reference.length).slice().reverse();
            const anchor = Math.floor(reference.length / 2);
            const from = reference[Math.min(anchor, reference.length - 1)];
            const mid = near[Math.min(anchor, near.length - 1)];
            const to = far[Math.min(anchor, far.length - 1)];
            if (from && mid && to) {
                measures = `
                    <line class="dco-liner-measure" data-liner-offset-line="1" x1="${rounded(from[0])}" y1="${rounded(from[1])}" x2="${rounded(mid[0])}" y2="${rounded(mid[1])}" stroke="#9a6207" stroke-width="1.2"/>
                    <line class="dco-liner-measure" data-liner-width-line="1" x1="${rounded(mid[0])}" y1="${rounded(mid[1])}" x2="${rounded(to[0])}" y2="${rounded(to[1])}" stroke="#1d6fbf" stroke-width="1.2"/>
                    <text data-liner-offset-label="1" x="${rounded((from[0] + mid[0]) / 2)}" y="${rounded((from[1] + mid[1]) / 2) - 4}" font-size="11" fill="#9a6207">${rounded(draft.offsetCm)}</text>
                    <text data-liner-width-label="1" x="${rounded((mid[0] + to[0]) / 2)}" y="${rounded((mid[1] + to[1]) / 2) - 4}" font-size="11" fill="#1d6fbf">${rounded(draft.widthCm)}</text>`;
            }
        }
        const hits = api.availableSides(piece.pieceType).map(side => {
            const path = paths[side];
            if (!path) return "";
            const active = side === draft.side ? "is-selected" : "";
            return `<polyline class="dco-liner-side ${active}" data-liner-side="${side}" points="${pointsAttr(path.map(point => mapPoint(point, frame, piece)))}" fill="none" stroke="${side === draft.side ? "#9a6207" : "transparent"}" stroke-width="${side === draft.side ? 4 : 12}" stroke-linecap="round"/>`;
        }).join("");
        return `<svg viewBox="0 0 420 280" role="img" aria-label="${esc(__("Liner preview"))}">
            <polygon points="${pointsAttr(outline)}" fill="#fff7e8" stroke="#8a5700" stroke-width="2"/>
            ${hits}
            ${strip}
            ${measures}
            <text x="210" y="268" text-anchor="middle" font-size="12" fill="#536577">${rounded(piece.widthCm)} × ${rounded(piece.lengthCm)} ${esc(__("cm"))}</text>
        </svg>`;
    }

    function editorHtml(row, draft) {
        const api = geometry();
        const sides = api.availableSides(draft.piece.pieceType).map(side => `
            <button type="button" class="dco-corner-position ${side === draft.side ? "is-active" : ""}" data-liner-side="${side}" aria-pressed="${side === draft.side ? "true" : "false"}">
                ${esc(api.sideLabel(side, draft.piece.pieceType))}
            </button>`).join("");
        const remove = draft.enabled
            ? `<button type="button" class="btn btn-default btn-sm" data-liner-remove>${esc(__("Remove liner"))}</button>`
            : "";
        return `<div class="dco-corner-editor" data-liner-editor>
            <section class="dco-corner-preview-panel">
                <div class="dco-corner-preview-head">
                    <span class="dco-corner-badge">${esc(__("Liner"))}</span>
                </div>
                <div class="dco-corner-preview" data-liner-preview>${previewSvg(draft)}</div>
            </section>
            <section class="dco-corner-controls">
                <div class="dco-corner-section-label">${esc(__("Reference side"))}</div>
                <div class="dco-corner-position-grid" data-liner-sides>${sides}</div>
                <div class="dco-corner-section-label">${esc(__("Distance and width"))}</div>
                <div class="dco-corner-input-grid">
                    <div class="dco-corner-input-wrap">
                        <label>${esc(__("Distance from side"))}</label>
                        <div class="dco-corner-input-shell"><input type="number" min="0" step="0.1" data-liner-offset value="${rounded(draft.offsetCm)}"><span>${esc(__("cm"))}</span></div>
                    </div>
                    <div class="dco-corner-input-wrap">
                        <label>${esc(__("Liner width"))}</label>
                        <div class="dco-corner-input-shell"><input type="number" min="0.1" step="0.1" data-liner-width value="${rounded(draft.widthCm)}"><span>${esc(__("cm"))}</span></div>
                    </div>
                </div>
                <div class="dco-corner-help" data-liner-help></div>
                ${remove}
            </section>
        </div>`;
    }

    function readDraft(root, piece, enabled) {
        const offset = root.querySelector("[data-liner-offset]");
        const width = root.querySelector("[data-liner-width]");
        const active = root.querySelector("[data-liner-sides] .is-active");
        return {
            piece,
            side: active ? active.getAttribute("data-liner-side") : "",
            offsetCm: offset ? Number(offset.value) : NaN,
            widthCm: width ? Number(width.value) : NaN,
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
        const message = validationMessage(draft);
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

    async function commit(frm, row, values) {
        const editor = window.AlmdinaClippedCornerEditor;
        if (!editor || typeof editor.commitChildValues !== "function") {
            await frappe.model.set_value(row.doctype, row.name, values);
        } else {
            await editor.commitChildValues(frm, row, values);
        }
        frm.dirty();
        refreshTable(frm);
    }

    let activeDialog = null;

    function open(frm, row) {
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
        const piece = api.pieceFromRow(row);
        piece.widthCm = size.width;
        piece.lengthCm = size.length;
        let draft = draftFromRow(row);
        draft.piece = piece;
        const dialog = new frappe.ui.Dialog({
            title: __("Liner — Door piece {0}", [row.piece_no || row.idx || ""]),
            fields: [{ fieldname: "liner_editor", fieldtype: "HTML" }],
            primary_action_label: __("Apply liner"),
            primary_action() {
                const root = dialog.$wrapper.find("[data-liner-editor]").get(0);
                if (!root) return;
                draft = readDraft(root, piece, true);
                const message = paint(root, draft, dialog);
                if (message) {
                    frappe.msgprint({ title: __("Check liner"), message, indicator: "orange" });
                    return Promise.resolve(false);
                }
                return commit(frm, row, {
                    extra_liner: 1,
                    liner_reference_side: draft.side,
                    liner_offset_cm: draft.offsetCm,
                    liner_width_cm: draft.widthCm,
                }).then(() => dialog.hide());
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
                draft = readDraft(root, piece, draft.enabled);
                draft.side = side.getAttribute("data-liner-side");
                paint(root, draft, dialog);
                return;
            }
            if (event.target.closest("[data-liner-remove]")) {
                commit(frm, row, {
                    extra_liner: 0,
                    liner_reference_side: "",
                    liner_offset_cm: 0,
                    liner_width_cm: 0,
                }).then(() => dialog.hide());
            }
        });
        root.addEventListener("input", () => {
            draft = readDraft(root, piece, draft.enabled);
            paint(root, draft, dialog);
        });
        return true;
    }

    window.AlmdinaLinerEditor = Object.freeze({
        open,
        previewSvg,
        validationMessage,
        draftFromRow,
    });
})();
