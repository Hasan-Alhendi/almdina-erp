(() => {
    "use strict";

    const CLIPPED_TYPE = "Clipped Corner";
    const DEFAULT_POSITION = "Top Right";
    const ROTATED_POSITION = {
        "Top Left": "Top Right",
        "Top Right": "Bottom Right",
        "Bottom Right": "Bottom Left",
        "Bottom Left": "Top Left",
    };
    const POSITIONS = [
        { value: "Top Right", ar: "أعلى اليمين", en: "Top right" },
        { value: "Top Left", ar: "أعلى اليسار", en: "Top left" },
        { value: "Bottom Right", ar: "أسفل اليمين", en: "Bottom right" },
        { value: "Bottom Left", ar: "أسفل اليسار", en: "Bottom left" },
    ];

    function isArabic() {
        const lang = String(
            (frappe.boot && frappe.boot.lang) ||
            (frappe.boot && frappe.boot.user && frappe.boot.user.language) ||
            document.documentElement.lang ||
            ""
        ).toLowerCase();
        return lang === "ar" || lang.startsWith("ar-");
    }

    function num(value) {
        const result = Number(String(value ?? "").replace(",", "."));
        return Number.isFinite(result) ? result : 0;
    }

    function rounded(value) {
        return Math.round(num(value) * 1000) / 1000;
    }

    function clamp(value, min, max) {
        return Math.min(max, Math.max(min, value));
    }

    function defaultCut(total) {
        total = num(total);
        if (total <= 0) return 0;
        return rounded(Math.min(Math.max(total * 0.2, 1), total * 0.45));
    }

    function originalDimensions(piece) {
        return {
            width: num(piece.original_w || piece.original_width_cm || piece.width_cm),
            length: num(piece.original_h || piece.original_length_cm || piece.length_cm),
        };
    }

    function baseConfig(piece) {
        const dimensions = originalDimensions(piece || {});
        return {
            position: POSITIONS.some(item => item.value === piece.clipped_corner_position)
                ? piece.clipped_corner_position
                : DEFAULT_POSITION,
            cutWidth: num(piece.clipped_corner_width_cm) || defaultCut(dimensions.width),
            cutLength: num(piece.clipped_corner_length_cm) || defaultCut(dimensions.length),
            originalWidth: dimensions.width,
            originalLength: dimensions.length,
        };
    }

    function effectiveConfig(piece) {
        const base = baseConfig(piece || {});
        const rotated = Boolean(piece && piece.rotated);
        return {
            position: rotated ? (ROTATED_POSITION[base.position] || DEFAULT_POSITION) : base.position,
            cutWidth: rotated ? base.cutLength : base.cutWidth,
            cutLength: rotated ? base.cutWidth : base.cutLength,
            width: num(piece && piece.w) || (rotated ? base.originalLength : base.originalWidth),
            length: num(piece && piece.h) || (rotated ? base.originalWidth : base.originalLength),
            rotated,
        };
    }

    function points(piece, viewportWidth = 100, viewportHeight = 100) {
        const config = effectiveConfig(piece || {});
        const width = Math.max(0, num(viewportWidth));
        const height = Math.max(0, num(viewportHeight));
        if (!width || !height || !config.width || !config.length) {
            return [[0, 0], [width, 0], [width, height], [0, height]];
        }

        const cutX = clamp(config.cutWidth / config.width * width, 0, width * 0.95);
        const cutY = clamp(config.cutLength / config.length * height, 0, height * 0.95);
        const byPosition = {
            "Top Right": [[0, 0], [width - cutX, 0], [width, cutY], [width, height], [0, height]],
            "Top Left": [[cutX, 0], [width, 0], [width, height], [0, height], [0, cutY]],
            "Bottom Right": [[0, 0], [width, 0], [width, height - cutY], [width - cutX, height], [0, height]],
            "Bottom Left": [[0, 0], [width, 0], [width, height], [cutX, height], [0, height - cutY]],
        };
        return byPosition[config.position] || byPosition[DEFAULT_POSITION];
    }

    function pointsAttribute(piece, width = 100, height = 100) {
        return points(piece, width, height)
            .map(point => `${rounded(point[0])},${rounded(point[1])}`)
            .join(" ");
    }

    function dxfPoints(piece, x, y, width, height) {
        return points(piece, width, height).map(point => [
            num(x) + point[0],
            num(y) + height - point[1],
        ]);
    }

    function positionLabel(value, arabic = isArabic()) {
        const item = POSITIONS.find(position => position.value === value) || POSITIONS[0];
        return arabic ? item.ar : item.en;
    }

    function prepareRow(row) {
        if (!row || row.piece_type !== CLIPPED_TYPE) return false;
        const config = baseConfig(row);
        let changed = false;
        if (!POSITIONS.some(item => item.value === row.clipped_corner_position)) {
            row.clipped_corner_position = config.position;
            changed = true;
        }
        if (num(row.clipped_corner_width_cm) <= 0 && config.cutWidth > 0) {
            row.clipped_corner_width_cm = config.cutWidth;
            changed = true;
        }
        if (num(row.clipped_corner_length_cm) <= 0 && config.cutLength > 0) {
            row.clipped_corner_length_cm = config.cutLength;
            changed = true;
        }
        return changed;
    }

    function summary(row, arabic = isArabic()) {
        if (!row || row.piece_type !== CLIPPED_TYPE) return "";
        const config = baseConfig(row);
        const size = config.cutWidth && config.cutLength
            ? `${rounded(config.cutWidth)}×${rounded(config.cutLength)} ${arabic ? "سم" : "cm"}`
            : (arabic ? "بعد إدخال المقاس" : "after dimensions");
        return `${positionLabel(config.position, arabic)} · ${size}`;
    }

    function installStyles() {
        if (document.getElementById("dco-clipped-corner-css")) return;
        const style = document.createElement("style");
        style.id = "dco-clipped-corner-css";
        style.textContent = `
            .dco-clipped-corner-modal .modal-dialog{max-width:min(860px,94vw)!important;width:860px!important}
            .dco-clipped-corner-modal .modal-content{border:0;border-radius:18px;overflow:hidden;box-shadow:0 24px 80px rgba(15,23,42,.24)}
            .dco-clipped-corner-modal .modal-body{padding:0!important;background:var(--subtle-fg,#f6f8fa)}
            .dco-corner-editor{direction:rtl;display:grid;grid-template-columns:minmax(0,1.18fr) minmax(290px,.82fr);min-height:430px}
            .dco-corner-preview-panel{padding:24px;background:linear-gradient(150deg,#f8fbff,#edf5fb);display:flex;flex-direction:column;gap:14px}
            .dco-corner-preview-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}
            .dco-corner-preview-head strong{display:block;font-size:16px;color:#172033}
            .dco-corner-preview-head span{font-size:11px;color:#64748b;line-height:1.6}
            .dco-corner-badge{display:inline-flex!important;align-items:center;gap:5px;padding:5px 9px;border-radius:999px;background:#fff3d6;color:#825314!important;border:1px solid #efd39b;font-weight:800;white-space:nowrap}
            .dco-corner-preview{flex:1;min-height:280px;border:1px solid #d7e2ea;border-radius:16px;background:#fff;display:flex;align-items:center;justify-content:center;padding:18px;box-shadow:0 8px 28px rgba(15,23,42,.06)}
            .dco-corner-preview svg{width:100%;height:100%;min-height:240px;overflow:visible}
            .dco-corner-controls{padding:21px 20px;background:var(--card-bg,#fff);border-right:1px solid var(--border-color,#e2e8f0);display:flex;flex-direction:column;gap:16px}
            .dco-corner-section-label{font-size:11px;font-weight:900;color:#475569;margin-bottom:7px}
            .dco-corner-position-grid{display:grid;grid-template-columns:1fr 1fr;gap:7px}
            .dco-corner-position{border:1px solid var(--border-color,#d9e0e6);border-radius:11px;background:var(--card-bg,#fff);min-height:66px;padding:7px;cursor:pointer;display:flex;align-items:center;gap:8px;text-align:right;color:inherit}
            .dco-corner-position:hover{border-color:#d09a35;background:#fffaf0}
            .dco-corner-position.is-active{border-color:#c68519;background:#fff5de;color:#754900;box-shadow:0 0 0 2px rgba(198,133,25,.12)}
            .dco-corner-position svg{width:38px;height:38px;flex:0 0 38px}
            .dco-corner-position span{font-size:11px;font-weight:800;line-height:1.4}
            .dco-corner-input-grid{display:grid;grid-template-columns:1fr 1fr;gap:9px}
            .dco-corner-input-wrap label{display:block;font-size:10px;font-weight:800;color:#64748b;margin-bottom:5px}
            .dco-corner-input-shell{display:flex;align-items:center;border:1px solid var(--border-color,#d9e0e6);border-radius:10px;overflow:hidden;background:#fff}
            .dco-corner-input-shell input{width:100%;border:0!important;box-shadow:none!important;min-height:40px;padding:7px 10px;font-size:16px;font-weight:800;text-align:center}
            .dco-corner-input-shell span{padding:0 9px;color:#64748b;font-size:10px;border-right:1px solid #e7ebef;white-space:nowrap}
            .dco-corner-equal{align-self:flex-start;border:0;background:transparent;color:var(--primary,#1674c5);font-size:11px;font-weight:800;padding:0;cursor:pointer}
            .dco-corner-help{margin-top:auto;border-radius:11px;padding:10px 11px;background:#f8fafc;border:1px solid #e2e8f0;font-size:10px;line-height:1.65;color:#52606d}
            .dco-corner-help.is-error{background:#fff3f1;border-color:#efb5ad;color:#9d2e23}
            .dco-fast-table tr.dco-clipped-corner-row td{background:rgba(224,151,24,.045)}
            .dco-fast-table tr.dco-clipped-corner-row:focus-within td{background:rgba(224,151,24,.085)!important}
            .dco-special-sketch-button.is-clipped-corner{border-style:solid!important;border-color:rgba(198,133,25,.5)!important;background:#fff7e6!important;color:#8a5700!important}
            .dco-special-sketch-button.is-clipped-corner>span:first-child{font-size:19px!important}
            @media(max-width:720px){.dco-clipped-corner-modal .modal-dialog{width:100vw!important;margin:0!important}.dco-corner-editor{display:flex;flex-direction:column}.dco-corner-preview-panel{padding:14px}.dco-corner-preview{min-height:220px}.dco-corner-preview svg{min-height:190px}.dco-corner-controls{border:0;border-top:1px solid #e2e8f0;padding:15px}}
        `;
        document.head.appendChild(style);
    }

    function cornerIcon(position) {
        const piece = {
            piece_type: CLIPPED_TYPE,
            width_cm: 100,
            length_cm: 100,
            clipped_corner_position: position,
            clipped_corner_width_cm: 34,
            clipped_corner_length_cm: 34,
        };
        return `<svg viewBox="0 0 44 44" aria-hidden="true"><polygon points="${pointsAttribute(piece, 38, 38).split(" ").map(pair => {
            const [x, y] = pair.split(",").map(Number);
            return `${x + 3},${y + 3}`;
        }).join(" ")}" fill="#fff1d1" stroke="#9a6207" stroke-width="2"/></svg>`;
    }

    function editorHtml(row) {
        const config = baseConfig(row);
        const dimensions = originalDimensions(row);
        return `
            <div class="dco-corner-editor">
                <section class="dco-corner-preview-panel">
                    <div class="dco-corner-preview-head">
                        <div>
                            <strong>${isArabic() ? "معاينة الدرفة داخل اللوح" : "Piece preview on the board"}</strong>
                            <span>${isArabic() ? "المقاس الخارجي" : "Outer size"}: ${rounded(dimensions.width)} × ${rounded(dimensions.length)} ${isArabic() ? "سم" : "cm"}</span>
                        </div>
                        <span class="dco-corner-badge">⌑ ${isArabic() ? "مسار قص حقيقي" : "Real cut path"}</span>
                    </div>
                    <div class="dco-corner-preview" data-corner-preview></div>
                </section>
                <section class="dco-corner-controls">
                    <div>
                        <div class="dco-corner-section-label">${isArabic() ? "1. اختر مكان الزاوية" : "1. Choose the corner"}</div>
                        <div class="dco-corner-position-grid">
                            ${POSITIONS.map(position => `
                                <button type="button" class="dco-corner-position ${position.value === config.position ? "is-active" : ""}" data-position="${position.value}">
                                    ${cornerIcon(position.value)}
                                    <span>${isArabic() ? position.ar : position.en}</span>
                                </button>`).join("")}
                        </div>
                    </div>
                    <div>
                        <div class="dco-corner-section-label">${isArabic() ? "2. أدخل مسافتي القص" : "2. Enter the two cut distances"}</div>
                        <div class="dco-corner-input-grid">
                            <div class="dco-corner-input-wrap">
                                <label>${isArabic() ? "على جهة العرض" : "Along width"}</label>
                                <div class="dco-corner-input-shell"><input type="number" min="0.1" step="0.1" data-corner-cut="width" value="${rounded(config.cutWidth)}"><span>${isArabic() ? "سم" : "cm"}</span></div>
                            </div>
                            <div class="dco-corner-input-wrap">
                                <label>${isArabic() ? "على جهة الطول" : "Along length"}</label>
                                <div class="dco-corner-input-shell"><input type="number" min="0.1" step="0.1" data-corner-cut="length" value="${rounded(config.cutLength)}"><span>${isArabic() ? "سم" : "cm"}</span></div>
                            </div>
                        </div>
                        <button type="button" class="dco-corner-equal">${isArabic() ? "جعل المسافتين متساويتين" : "Make both distances equal"}</button>
                    </div>
                    <div class="dco-corner-help" data-corner-help></div>
                </section>
            </div>`;
    }

    function readEditor(root, row) {
        return {
            position: root.querySelector(".dco-corner-position.is-active")?.dataset.position || DEFAULT_POSITION,
            cutWidth: num(root.querySelector("[data-corner-cut='width']")?.value),
            cutLength: num(root.querySelector("[data-corner-cut='length']")?.value),
            ...originalDimensions(row),
        };
    }

    function validationMessage(config) {
        if (!config.width || !config.length) {
            return isArabic()
                ? "أدخل عرض الدرفة وطولها أولًا، ثم افتح إعداد الزاوية."
                : "Enter the piece width and length before editing the corner.";
        }
        if (config.cutWidth <= 0 || config.cutLength <= 0) {
            return isArabic() ? "يجب أن تكون مسافتا القص أكبر من صفر." : "Both cut distances must be greater than zero.";
        }
        if (config.cutWidth >= config.width) {
            return isArabic() ? "قص جهة العرض يجب أن يكون أصغر من عرض الدرفة." : "The width cut must be smaller than the piece width.";
        }
        if (config.cutLength >= config.length) {
            return isArabic() ? "قص جهة الطول يجب أن يكون أصغر من طول الدرفة." : "The length cut must be smaller than the piece length.";
        }
        return "";
    }

    function renderPreview(root, row) {
        const config = readEditor(root, row);
        const message = validationMessage(config);
        const preview = root.querySelector("[data-corner-preview]");
        const help = root.querySelector("[data-corner-help]");
        if (help) {
            help.classList.toggle("is-error", Boolean(message));
            help.textContent = message || (isArabic()
                ? "المعاينة تمثل الشكل بعد القص. يبقى المستطيل الخارجي هو المساحة المحجوزة الآمنة أثناء توزيع القطع."
                : "The preview is the final cut shape. The outer rectangle remains the safe reserved area during nesting.");
        }
        if (!preview) return;

        const sample = {
            piece_type: CLIPPED_TYPE,
            width_cm: config.width || 100,
            length_cm: config.length || 100,
            clipped_corner_position: config.position,
            clipped_corner_width_cm: config.cutWidth,
            clipped_corner_length_cm: config.cutLength,
        };
        const polygon = points(sample, 360, 220).map(([x, y]) => `${x + 30},${y + 30}`).join(" ");
        preview.innerHTML = `
            <svg viewBox="0 0 420 280" role="img" aria-label="${isArabic() ? "معاينة الزاوية المقصوصة" : "Clipped corner preview"}">
                <defs><pattern id="dco-corner-grid" width="20" height="20" patternUnits="userSpaceOnUse"><path d="M20 0H0V20" fill="none" stroke="#dfe8ef" stroke-width="1"/></pattern></defs>
                <rect x="10" y="10" width="400" height="260" rx="12" fill="url(#dco-corner-grid)" stroke="#e2e8f0"/>
                <polygon points="${polygon}" fill="#dff1fb" stroke="#172033" stroke-width="3" stroke-linejoin="round"/>
                <text x="210" y="144" text-anchor="middle" font-size="18" font-weight="800" fill="#172033">${isArabic() ? "الدرفة" : "PIECE"}</text>
                <text x="210" y="166" text-anchor="middle" font-size="12" fill="#536577">${rounded(config.width)} × ${rounded(config.length)} ${isArabic() ? "سم" : "cm"}</text>
                <text x="210" y="258" text-anchor="middle" font-size="11" font-weight="700" fill="#9a6207">${positionLabel(config.position)} · ${rounded(config.cutWidth)} × ${rounded(config.cutLength)} ${isArabic() ? "سم" : "cm"}</text>
            </svg>`;
    }

    function refreshFastTable(frm) {
        if (window.AlmdinaDoorCuttingFastEntry && window.AlmdinaDoorCuttingFastEntry.render) {
            window.AlmdinaDoorCuttingFastEntry.render(frm);
        }
    }

    function open(frm, row) {
        if (!frm || !row || row.piece_type !== CLIPPED_TYPE) return;
        installStyles();
        prepareRow(row);

        const dialog = new frappe.ui.Dialog({
            title: isArabic()
                ? `إعداد الزاوية المقصوصة — الدرفة ${row.piece_no || row.idx || ""}`
                : `Clipped corner — piece ${row.piece_no || row.idx || ""}`,
            fields: [{ fieldname: "corner_editor", fieldtype: "HTML" }],
            primary_action_label: isArabic() ? "اعتماد الزاوية" : "Apply corner",
            primary_action() {
                const root = dialog.$wrapper.find(".dco-corner-editor").get(0);
                if (!root) return;
                const config = readEditor(root, row);
                const message = validationMessage(config);
                if (message) {
                    frappe.msgprint({ title: isArabic() ? "راجع مقاس الزاوية" : "Check corner size", message, indicator: "orange" });
                    return;
                }

                Promise.all([
                    frappe.model.set_value(row.doctype, row.name, "clipped_corner_position", config.position),
                    frappe.model.set_value(row.doctype, row.name, "clipped_corner_width_cm", rounded(config.cutWidth)),
                    frappe.model.set_value(row.doctype, row.name, "clipped_corner_length_cm", rounded(config.cutLength)),
                ]).then(() => {
                    frm.dirty();
                    dialog.hide();
                    refreshFastTable(frm);
                    frappe.show_alert({
                        message: isArabic() ? "تم اعتماد الزاوية وستظهر في خطة القص." : "Corner applied and will appear in the cutting plan.",
                        indicator: "green",
                    });
                });
            },
        });
        dialog.$wrapper.addClass("dco-clipped-corner-modal");
        dialog.show();

        const field = dialog.fields_dict.corner_editor;
        field.$wrapper.html(editorHtml(row));
        const root = field.$wrapper.find(".dco-corner-editor").get(0);
        root.querySelectorAll(".dco-corner-position").forEach(button => {
            button.addEventListener("click", () => {
                root.querySelectorAll(".dco-corner-position").forEach(item => item.classList.remove("is-active"));
                button.classList.add("is-active");
                renderPreview(root, row);
            });
        });
        root.querySelectorAll("[data-corner-cut]").forEach(input => {
            input.addEventListener("input", () => renderPreview(root, row));
            input.addEventListener("focus", () => input.select());
        });
        root.querySelector(".dco-corner-equal")?.addEventListener("click", () => {
            const widthInput = root.querySelector("[data-corner-cut='width']");
            const lengthInput = root.querySelector("[data-corner-cut='length']");
            if (widthInput && lengthInput) lengthInput.value = widthInput.value;
            renderPreview(root, row);
        });
        renderPreview(root, row);
    }

    window.AlmdinaClippedCornerGeometry = Object.freeze({
        TYPE: CLIPPED_TYPE,
        positions: POSITIONS.map(position => position.value),
        isClipped: piece => Boolean(piece && piece.piece_type === CLIPPED_TYPE),
        baseConfig,
        effectiveConfig,
        points,
        pointsAttribute,
        dxfPoints,
        positionLabel,
        summary,
    });
    window.AlmdinaClippedCornerEditor = Object.freeze({ open, prepare: prepareRow });
})();
