(() => {
    "use strict";

    function num(value) {
        const result = Number(value);
        return Number.isFinite(result) ? result : 0;
    }

    function pair(code, value) {
        return `${code}\r\n${value}\r\n`;
    }

    function dxfNumber(value) {
        return String(Math.round(num(value) * 1000) / 1000);
    }

    function layer(name, color) {
        return pair(0, "LAYER") + pair(2, name) + pair(70, 0) + pair(62, color) + pair(6, "CONTINUOUS");
    }

    function rect(layerName, x, y, width, height) {
        const points = [[x, y], [x + width, y], [x + width, y + height], [x, y + height]];
        let out = pair(0, "POLYLINE") + pair(8, layerName) + pair(66, 1) + pair(10, 0) + pair(20, 0) + pair(30, 0) + pair(70, 1);
        points.forEach(point => {
            out += pair(0, "VERTEX") + pair(8, layerName) + pair(10, dxfNumber(point[0])) + pair(20, dxfNumber(point[1])) + pair(30, 0);
        });
        return out + pair(0, "SEQEND") + pair(8, layerName);
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

            entities += rect("SHEET_OUTLINE", offsetX, offsetY, fullWidth, fullHeight);
            (sheet.pieces || []).forEach(piece => {
                const pieceWidth = num(piece.w) * 10;
                const pieceHeight = num(piece.h) * 10;
                const x = offsetX + trimMm + num(piece.x) * 10;
                const y = offsetY + fullHeight - trimMm - num(piece.y) * 10 - pieceHeight;
                entities += rect("CUT_PATH", x, y, pieceWidth, pieceHeight);
            });
        });

        let dxf = pair(0, "SECTION") + pair(2, "HEADER");
        dxf += pair(9, "$ACADVER") + pair(1, "AC1009");
        dxf += pair(9, "$INSUNITS") + pair(70, 4);
        dxf += pair(9, "$EXTMIN") + pair(10, 0) + pair(20, 0) + pair(30, 0);
        dxf += pair(9, "$EXTMAX") + pair(10, dxfNumber(extmaxX)) + pair(20, dxfNumber(extmaxY)) + pair(30, 0);
        dxf += pair(0, "ENDSEC");
        dxf += pair(0, "SECTION") + pair(2, "TABLES");
        dxf += pair(0, "TABLE") + pair(2, "LTYPE") + pair(70, 1);
        dxf += pair(0, "LTYPE") + pair(2, "CONTINUOUS") + pair(70, 0) + pair(3, "Solid line") + pair(72, 65) + pair(73, 0) + pair(40, 0);
        dxf += pair(0, "ENDTAB");
        dxf += pair(0, "TABLE") + pair(2, "LAYER") + pair(70, 3) + layer("0", 7) + layer("SHEET_OUTLINE", 8) + layer("CUT_PATH", 1) + pair(0, "ENDTAB");
        dxf += pair(0, "ENDSEC");
        dxf += pair(0, "SECTION") + pair(2, "BLOCKS") + pair(0, "ENDSEC");
        dxf += pair(0, "SECTION") + pair(2, "ENTITIES") + entities + pair(0, "ENDSEC") + pair(0, "EOF");
        return dxf;
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
            freeze_message: __("Validating DXF geometry on server..."),
        }).then(r => {
            const data = r.message || {};
            const plan = data.plan || {};
            const manifest = data.manifest || {};
            if (!(plan.sheets || []).length) {
                frappe.throw(__("Validated cutting plan contains no sheets to export."));
            }

            const base = `cutting_plan_${safeName(frm.doc.name || "draft")}`;
            download(`${base}.dxf`, buildDxf(plan), "application/octet-stream");
            download(`${base}_manifest.json`, JSON.stringify(manifest, null, 2), "application/json;charset=utf-8");
            frappe.show_alert({
                message: __("Validated DXF and manifest exported successfully."),
                indicator: "green",
            });
        });
    }

    function installButton(frm) {
        if (frm.doctype !== "Door Cutting Order") return;
        ["تصدير DXF", "Export DXF"].forEach(label => frm.remove_custom_button(label));
        frm.add_custom_button(__("Export DXF"), () => validatedExport(frm));
    }

    frappe.ui.form.on("Door Cutting Order", {
        refresh(frm) {
            setTimeout(() => installButton(frm), 900);
            if (frappe.after_ajax) frappe.after_ajax(() => installButton(frm));
        },
    });
})();
