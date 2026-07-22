(() => {
    "use strict";

    const DXF_VERSION = "AC1009"; // AutoCAD R11/R12 ASCII. AutoCAD 2020 opens this legacy format.
    const DXF_FORMAT_LABEL = "AutoCAD R12 ASCII";
    const DXF_UNITS = "mm";

    function isArabic() {
        const lang = String(
            (frappe.boot && frappe.boot.lang) ||
            (frappe.boot && frappe.boot.user && frappe.boot.user.language) ||
            document.documentElement.lang ||
            ""
        ).toLowerCase();
        return lang === "ar" || lang.startsWith("ar-");
    }

    function buttonLabel() {
        return isArabic() ? "تصدير DXF لأوتوكاد" : "Export DXF for AutoCAD";
    }

    function num(value) {
        const result = Number(value);
        return Number.isFinite(result) ? result : 0;
    }

    function pair(code, value) {
        return `${code}\r\n${value}\r\n`;
    }

    function dxfNumber(value) {
        const number = num(value);
        return String(Math.round(number * 1000) / 1000);
    }

    function layer(name, color) {
        return (
            pair(0, "LAYER") +
            pair(2, name) +
            pair(70, 0) +
            pair(62, color) +
            pair(6, "CONTINUOUS")
        );
    }

    function line(layerName, x1, y1, x2, y2) {
        return (
            pair(0, "LINE") +
            pair(8, layerName || "0") +
            pair(10, dxfNumber(x1)) +
            pair(20, dxfNumber(y1)) +
            pair(30, 0) +
            pair(11, dxfNumber(x2)) +
            pair(21, dxfNumber(y2)) +
            pair(31, 0)
        );
    }

    function rectangle(layerName, x, y, width, height) {
        const x2 = x + width;
        const y2 = y + height;
        return (
            line(layerName, x, y, x2, y) +
            line(layerName, x2, y, x2, y2) +
            line(layerName, x2, y2, x, y2) +
            line(layerName, x, y2, x, y)
        );
    }

    function buildDxf(plan) {
        const sheets = plan.sheets || [];
        const perRow = 2;
        const gapMm = 200;
        const maxWidth = Math.max(0, ...sheets.map(sheet => num(sheet.full_width_cm || plan.full_board_width_cm) * 10));
        const maxHeight = Math.max(0, ...sheets.map(sheet => num(sheet.full_length_cm || plan.full_board_length_cm) * 10));
        const trimMm = num(plan.trim_cm) * 10;
        let entities = "";
        let extmaxX = 0;
        let extmaxY = 0;

        sheets.forEach((sheet, index) => {
            const fullWidth = num(sheet.full_width_cm || plan.full_board_width_cm) * 10;
            const fullHeight = num(sheet.full_length_cm || plan.full_board_length_cm) * 10;
            const offsetX = (index % perRow) * (maxWidth + gapMm);
            const offsetY = Math.floor(index / perRow) * (maxHeight + gapMm);
            extmaxX = Math.max(extmaxX, offsetX + fullWidth);
            extmaxY = Math.max(extmaxY, offsetY + fullHeight);

            entities += rectangle("SHEET_OUTLINE", offsetX, offsetY, fullWidth, fullHeight);

            (sheet.pieces || []).forEach(piece => {
                const pieceWidth = num(piece.w) * 10;
                const pieceHeight = num(piece.h) * 10;
                const x = offsetX + trimMm + num(piece.x) * 10;
                const y = offsetY + fullHeight - trimMm - num(piece.y) * 10 - pieceHeight;
                entities += rectangle("CUT_PATH", x, y, pieceWidth, pieceHeight);
            });
        });

        let dxf = "";
        dxf += pair(0, "SECTION") + pair(2, "HEADER");
        dxf += pair(9, "$ACADVER") + pair(1, DXF_VERSION);
        dxf += pair(9, "$EXTMIN") + pair(10, 0) + pair(20, 0) + pair(30, 0);
        dxf += pair(9, "$EXTMAX") + pair(10, dxfNumber(extmaxX)) + pair(20, dxfNumber(extmaxY)) + pair(30, 0);
        dxf += pair(0, "ENDSEC");

        dxf += pair(0, "SECTION") + pair(2, "TABLES");
        dxf += pair(0, "TABLE") + pair(2, "LTYPE") + pair(70, 1);
        dxf += pair(0, "LTYPE") + pair(2, "CONTINUOUS") + pair(70, 0) + pair(3, "Solid line") + pair(72, 65) + pair(73, 0) + pair(40, 0);
        dxf += pair(0, "ENDTAB");
        dxf += pair(0, "TABLE") + pair(2, "LAYER") + pair(70, 3);
        dxf += layer("0", 7) + layer("SHEET_OUTLINE", 8) + layer("CUT_PATH", 1);
        dxf += pair(0, "ENDTAB") + pair(0, "ENDSEC");

        dxf += pair(0, "SECTION") + pair(2, "BLOCKS") + pair(0, "ENDSEC");
        dxf += pair(0, "SECTION") + pair(2, "ENTITIES") + entities + pair(0, "ENDSEC");
        dxf += pair(0, "EOF");
        return dxf;
    }

    function validateDxfText(content) {
        if (!content || typeof content !== "string") {
            throw new Error("DXF content is empty.");
        }
        if (content.includes("NaN") || content.includes("Infinity") || content.includes("undefined") || content.includes("null")) {
            throw new Error("DXF contains an invalid numeric/value token.");
        }
        if (!content.includes(`$ACADVER\r\n1\r\n${DXF_VERSION}\r\n`)) {
            throw new Error("DXF AutoCAD version header is missing.");
        }
        if (!content.includes("0\r\nSECTION\r\n2\r\nENTITIES\r\n")) {
            throw new Error("DXF ENTITIES section is missing.");
        }
        if (!content.includes("0\r\nLINE\r\n")) {
            throw new Error("DXF contains no LINE geometry.");
        }
        if (!content.endsWith("0\r\nEOF\r\n")) {
            throw new Error("DXF EOF marker is missing.");
        }
        const lines = content.split("\r\n");
        if (lines[lines.length - 1] === "") lines.pop();
        if (lines.length % 2 !== 0) {
            throw new Error("DXF group-code/value pairs are incomplete.");
        }
    }

    function download(filename, content, mimeType) {
        const blob = new Blob([content], { type: mimeType });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = filename;
        document.body.appendChild(anchor);
        anchor.click();
        setTimeout(() => {
            document.body.removeChild(anchor);
            URL.revokeObjectURL(url);
        }, 500);
    }

    function safeName(value) {
        return String(value || "door_cutting_order").replace(/[^\w\-]+/g, "_");
    }

    function validatedExport(frm) {
        const args = { doc: JSON.stringify(frm.doc) };
        if (!frm.is_new()) args.order_name = frm.doc.name;

        return frappe.call({
            method: "almdina_erp.almdina_erp.services.export_validation_service.get_validated_dxf_plan",
            args,
            freeze: true,
            freeze_message: isArabic() ? "جاري التحقق من هندسة ملف DXF قبل التصدير..." : "Validating DXF geometry on server...",
        }).then(r => {
            const data = r.message || {};
            const plan = data.plan || {};
            const manifest = data.manifest || {};
            if (!(plan.sheets || []).length) {
                frappe.throw(isArabic() ? "خطة القص المتحقق منها لا تحتوي على ألواح للتصدير." : "Validated cutting plan contains no sheets to export.");
            }

            const dxf = buildDxf(plan);
            try {
                validateDxfText(dxf);
            } catch (error) {
                console.error("DXF self-check failed", error);
                frappe.throw(isArabic()
                    ? "فشل ملف DXF في فحص التوافق الداخلي، لذلك تم منع تنزيل ملف تالف."
                    : "DXF export failed its compatibility self-check and was not downloaded.");
            }

            const base = `cutting_plan_${safeName(frm.doc.name || "draft")}`;
            const exportManifest = {
                ...manifest,
                dxf_export: {
                    format: DXF_FORMAT_LABEL,
                    acadver: DXF_VERSION,
                    coordinate_units: DXF_UNITS,
                    geometry_entity: "LINE",
                    cut_layer: "CUT_PATH",
                    sheet_outline_layer: "SHEET_OUTLINE",
                    compatibility_target: "AutoCAD 2020+",
                },
            };

            download(`${base}_AutoCAD2020_R12.dxf`, dxf, "application/dxf;charset=us-ascii");
            download(`${base}_manifest.json`, JSON.stringify(exportManifest, null, 2), "application/json;charset=utf-8");
            frappe.show_alert({
                message: isArabic()
                    ? "تم تصدير ملف DXF متوافق مع AutoCAD مع ملف التحقق بنجاح."
                    : "Validated AutoCAD-compatible DXF and manifest exported successfully.",
                indicator: "green",
            });
        });
    }

    function removeLegacyDxfButtons(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;

        // Old exporters used one of these labels. Keep the new AutoCAD-specific
        // action untouched so there is exactly one trustworthy export path.
        ["تصدير DXF", "Export DXF"].forEach(label => frm.remove_custom_button(label));

        const root = frm.page && frm.page.wrapper ? frm.page.wrapper : frm.wrapper;
        if (!root) return;
        $(root).find("button").filter(function () {
            const text = $(this).text().trim();
            return text === "تصدير DXF" || text === "Export DXF";
        }).remove();
    }

    function ensureLegacyObserver(frm) {
        if (frm._almdina_secure_dxf_observer) return;
        const root = frm.page && frm.page.wrapper ? frm.page.wrapper : frm.wrapper;
        const node = root && (root[0] || root);
        if (!node || typeof MutationObserver === "undefined") return;

        const observer = new MutationObserver(() => removeLegacyDxfButtons(frm));
        observer.observe(node, { childList: true, subtree: true });
        frm._almdina_secure_dxf_observer = observer;
    }

    function installButton(frm) {
        if (frm.doctype !== "Door Cutting Order") return;
        removeLegacyDxfButtons(frm);
        const label = buttonLabel();
        frm.remove_custom_button(label);
        frm.add_custom_button(label, () => validatedExport(frm));
        ensureLegacyObserver(frm);
    }

    frappe.ui.form.on("Door Cutting Order", {
        refresh(frm) {
            installButton(frm);
            [250, 900, 1600].forEach(delay => setTimeout(() => installButton(frm), delay));
            if (frappe.after_ajax) {
                frappe.after_ajax(() => setTimeout(() => installButton(frm), 0));
            }
        },
    });
})();
