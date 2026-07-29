(() => {
    "use strict";

    const FRAME_ID = "dco-unified-document-print-frame";
    let activeFrm = null;

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function number(value) {
        const parsed = Number(value || 0);
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function quantity(value) {
        return number(value).toLocaleString("en-US", { maximumFractionDigits: 3 });
    }

    function money(value) {
        return number(value).toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    function edgeBandingApi() {
        return window.AlmdinaMultiEdgeBanding || null;
    }

    function shapePrintApi() {
        return window.AlmdinaShapePrint || null;
    }

    async function ensureProfiles(frm) {
        const module = edgeBandingApi();
        if (module && typeof module.ensureProfiles === "function") {
            await Promise.resolve(module.ensureProfiles(frm));
        }
    }

    function pieceTypeLabel(value) {
        if (value === "Special") return "خاصة";
        if (value === "Clipped Corner") return "زاوية مقصوصة";
        return "عادية";
    }

    function rowHasDrawing(row) {
        const renderer = shapePrintApi();
        return Boolean(renderer && renderer.hasVisual(row));
    }

    function notesCellHtml(row) {
        const renderer = shapePrintApi();
        return renderer
            ? renderer.notesCell(row, row.notes, { label: `رسمة الدرفة رقم ${row.index}` })
            : esc(row.notes || "—");
    }

    function shapePrintCss() {
        const renderer = shapePrintApi();
        return renderer ? renderer.css : "";
    }

    function rows(frm) {
        const module = edgeBandingApi();
        return (frm.doc.pieces || []).map((source, index) => ({
            ...source,
            index: index + 1,
            source,
            pieceType: source.piece_type || "Regular",
            width: number(source.width_cm),
            length: number(source.length_cm),
            qty: Math.max(1, Math.trunc(number(source.qty) || 1)),
            notes: source.notes || "",
            details: module && typeof module.details === "function"
                ? module.details(frm, source)
                : [],
        }));
    }

    function customEdgeGroups(details) {
        const groups = new Map();
        (details || [])
            .filter(detail => Boolean(detail.custom))
            .forEach(detail => {
                const type = String(detail.edge_type || "غير محدد").trim() || "غير محدد";
                if (!groups.has(type)) groups.set(type, { type, sides: [] });
                groups.get(type).sides.push(detail.side_label || "ضلع");
            });
        return [...groups.values()];
    }

    function sideSummary(group, customSideCount) {
        if (customSideCount === 4 && group.sides.length === 4) return "على الداير";
        return group.sides.join("، ");
    }

    function customEdgeDetailsHtml(details) {
        const groups = customEdgeGroups(details);
        if (!groups.length) return '<span class="custom-edge-empty" aria-label="لا يوجد تخصيص"></span>';
        const customSideCount = groups.reduce((sum, group) => sum + group.sides.length, 0);
        return `<div class="custom-edge-summary">${groups.map(group => `
            <div class="custom-edge-line">
                <span>${esc(sideSummary(group, customSideCount))}</span>
                <b>${esc(group.type)}</b>
                <em>مخصص</em>
            </div>`).join("")}</div>`;
    }

    function dimensionMark(value, count) {
        const safeCount = Math.max(0, Math.min(2, Number(count || 0)));
        const lines = Array.from(
            { length: safeCount },
            () => '<span class="dimension-edge-line"></span>'
        ).join("");
        return `<span class="dimension"><b>${quantity(value)}</b><span class="dimension-lines dimension-lines-${safeCount}">${lines}</span></span>`;
    }

    function measurementRowsHtml(frm) {
        return rows(frm).map(row => {
            const longCount = Number(Boolean(row.source.edge_long_right))
                + Number(Boolean(row.source.edge_long_left));
            const widthCount = Number(Boolean(row.source.edge_width_top))
                + Number(Boolean(row.source.edge_width_bottom));
            return `<tr class="${rowHasDrawing(row) ? "row-with-drawing" : ""}">
                <td>${row.index}</td>
                <td>${esc(pieceTypeLabel(row.pieceType))}</td>
                <td>${dimensionMark(row.width, widthCount)}</td>
                <td>${dimensionMark(row.length, longCount)}</td>
                <td>${row.qty}</td>
                <td class="right custom-edge-cell">${customEdgeDetailsHtml(row.details)}</td>
                <td class="right notes-cell ${rowHasDrawing(row) ? "notes-with-drawing" : ""}">${notesCellHtml(row)}</td>
            </tr>`;
        }).join("");
    }

    function invoiceLines(frm) {
        const documents = window.AlmdinaMultiEdgeDocuments;
        if (documents && typeof documents.invoiceLines === "function") {
            return documents.invoiceLines(frm);
        }
        const costing = window.AlmdinaOrderCostUX;
        return costing && typeof costing.invoiceLines === "function"
            ? costing.invoiceLines(frm)
            : [];
    }

    function invoiceTotal(frm, lines) {
        const documents = window.AlmdinaMultiEdgeDocuments;
        if (documents && typeof documents.invoiceTotal === "function") {
            return documents.invoiceTotal(frm);
        }
        return lines.reduce((sum, line) => sum + number(line.amount), 0);
    }

    function customerLineNote(line) {
        const note = String(line.note || "").trim();
        if (!note) return "";
        if (line.type !== "edge") return note;
        if (note.includes("من القشاط الافتراضي")) return "";
        return note.replace("يتضمن أطرافًا مخصصة", "تخصيص استثنائي");
    }

    function invoiceRowsHtml(lines) {
        if (!lines.length) {
            return '<tr><td colspan="6">احفظ الطلب واحسب خطة القص لتظهر تفاصيل الفاتورة.</td></tr>';
        }
        return lines.map((line, index) => {
            const note = customerLineNote(line);
            return `<tr>
                <td>${index + 1}</td>
                <td class="right invoice-description"><b>${esc(line.description)}</b>${note ? `<span class="line-note">${esc(note)}</span>` : ""}</td>
                <td>${quantity(line.quantity)}</td>
                <td>${esc(line.unit)}</td>
                <td>${line.rate || line.rate === 0 ? money(line.rate) : "—"}</td>
                <td><b>${money(line.amount)}</b></td>
            </tr>`;
        }).join("");
    }

    function sharedHeader(frm, mode) {
        const title = mode === "invoice" ? "عرض سعر الطلب" : "جدول قياسات الطلب";
        return `<div class="header">
            <div><h1>${title}</h1><div class="muted">يظهر في عمود القشاط التخصيص الاستثنائي فقط</div></div>
            <div class="header-order"><b>${esc(frm.doc.name || "مسودة")}</b><div class="muted">${esc(frm.doc.order_date || "")}</div></div>
        </div>`;
    }

    function sharedInfo(frm) {
        const doorCount = (frm.doc.pieces || []).reduce(
            (sum, row) => sum + Math.max(1, Math.trunc(number(row.qty) || 1)),
            0
        );
        return `<div class="info shared-info">
            <div><b>رقم الطلب</b>${esc(frm.doc.name || "مسودة")}</div>
            <div><b>الزبون</b>${esc(frm.doc.customer || "—")}</div>
            <div><b>صنف اللوح</b>${esc(frm.doc.board_description || frm.doc.board_item || "—")}</div>
            <div><b>نوع القشاط</b>${esc(frm.doc.default_edge_type || "—")}</div>
            <div><b>لون القشاط</b>${esc(frm.doc.edge_color || "غير محدد")}</div>
            <div><b>عدد الدرف</b>${quantity(doorCount)}</div>
        </div>`;
    }

    function invoiceSummary(frm) {
        return `<div class="info financial-info">
            <div><b>عدد الألواح</b>${quantity(frm.doc.required_boards)}</div>
            <div><b>سعر اللوح</b>$ ${money(frm.doc.board_rate_usd)}</div>
            <div><b>أجور القص / لوح</b>$ ${money(frm.doc.cutting_cost_per_board_usd)}</div>
            <div><b>إجمالي القشاط</b>$ ${money(frm.doc.edge_cost_usd)}</div>
        </div>`;
    }

    function measurementTable(frm) {
        return `<table class="table measurements">
            <thead><tr><th>#</th><th>النوع</th><th>العرض</th><th>الطول</th><th>العدد</th><th>القشاط المخصص</th><th>ملاحظات</th></tr></thead>
            <tbody>${measurementRowsHtml(frm)}</tbody>
        </table>`;
    }

    function printCss(mode) {
        const measurementOnly = mode === "measurements";
        return `
            @page{size:A4 portrait;margin:${measurementOnly ? "5mm" : "6mm"}}
            *{box-sizing:border-box}
            html,body{margin:0;padding:0;font-family:Tahoma,Arial,sans-serif;color:#111;direction:rtl;background:#fff}
            body{font-size:${measurementOnly ? "7.4px" : "8px"};-webkit-print-color-adjust:exact;print-color-adjust:exact}
            .header{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:1.5px solid #111;padding-bottom:3px;margin-bottom:3px}
            .header h1{font-size:${measurementOnly ? "15px" : "17px"};line-height:1.05;margin:0 0 1px}.header-order{text-align:left}
            .muted{color:#666;font-size:${measurementOnly ? "6.2px" : "6.8px"};line-height:1.15}
            .info{display:grid;gap:2px;margin:3px 0}.shared-info{grid-template-columns:repeat(6,minmax(0,1fr))}.financial-info{grid-template-columns:repeat(4,minmax(0,1fr))}
            .info>div{border:1px solid #aaa;border-radius:3px;padding:${measurementOnly ? "2px 3px" : "3px 4px"};min-width:0;line-height:1.15;word-break:break-word;min-height:${measurementOnly ? "22px" : "26px"}}
            .info b{display:block;font-size:${measurementOnly ? "5.8px" : "6.5px"};color:#555;margin-bottom:1px}
            .title{font-size:${measurementOnly ? "9px" : "10px"};font-weight:900;margin:${measurementOnly ? "3px" : "5px"} 0 2px}
            .table{width:100%;border-collapse:collapse;table-layout:fixed}.table thead{display:table-header-group}
            .table th,.table td{border:1px solid #999;padding:${measurementOnly ? "1px 2px" : "2px 3px"};text-align:center;vertical-align:middle;line-height:${measurementOnly ? "1.05" : "1.15"}}
            .table th{background:#eee;font-weight:900}.table tr{break-inside:avoid;page-break-inside:avoid}.right{text-align:right!important;white-space:normal}
            .measurements{font-size:${measurementOnly ? "6.5px" : "7.1px"}}
            .measurements th:nth-child(1),.measurements td:nth-child(1){width:3.5%}.measurements th:nth-child(2),.measurements td:nth-child(2){width:7.5%}
            .measurements th:nth-child(3),.measurements td:nth-child(3){width:8.5%}.measurements th:nth-child(4),.measurements td:nth-child(4){width:8.5%}
            .measurements th:nth-child(5),.measurements td:nth-child(5){width:5.5%}.measurements th:nth-child(6),.measurements td:nth-child(6){width:31%}
            .measurements th:nth-child(7),.measurements td:nth-child(7){width:35.5%}
            .custom-edge-cell:empty{padding:0}.custom-edge-empty{display:block;min-height:${measurementOnly ? "4px" : "6px"}}
            .custom-edge-summary{display:grid;gap:1px}.custom-edge-line{display:flex;align-items:center;gap:3px;border:1px solid #b88b00;border-radius:3px;background:#fff8df;padding:${measurementOnly ? "0 2px" : "1px 3px"};white-space:normal}
            .custom-edge-line span{font-size:${measurementOnly ? "5.6px" : "6.3px"};font-weight:800;color:#333}.custom-edge-line b{font-size:${measurementOnly ? "6px" : "6.9px"};word-break:break-word}
            .custom-edge-line em{margin-inline-start:auto;font-style:normal;font-size:${measurementOnly ? "5px" : "5.8px"};font-weight:900;color:#805b00;border:1px solid currentColor;border-radius:999px;padding:0 3px;white-space:nowrap}
            .notes-cell{font-size:${measurementOnly ? "6.1px" : "6.9px"};line-height:1.15}.dimension{display:inline-flex;min-width:28px;flex-direction:column;align-items:center;gap:0;line-height:1}
            .dimension b{font-size:${measurementOnly ? "6.6px" : "7.3px"}}.dimension-lines{display:flex;flex-direction:column;gap:1px;min-height:3px}
            .dimension-edge-line{display:block;width:20px;height:1px;background:#111}.dimension-lines-0{visibility:hidden}.row-with-drawing td{padding-top:2px;padding-bottom:2px}.notes-with-drawing{min-width:0}
            .invoice{font-size:7.4px;break-inside:avoid;page-break-inside:avoid}.invoice th,.invoice td{padding:2px 3px}
            .invoice th:nth-child(1),.invoice td:nth-child(1){width:4%}.invoice th:nth-child(2),.invoice td:nth-child(2){width:48%}.invoice th:nth-child(3),.invoice td:nth-child(3){width:11%}
            .invoice th:nth-child(4),.invoice td:nth-child(4){width:10%}.invoice th:nth-child(5),.invoice td:nth-child(5){width:13.5%}.invoice th:nth-child(6),.invoice td:nth-child(6){width:13.5%}
            .invoice-description{line-height:1.2}.line-note{display:block;color:#555;font-size:6.2px;margin-top:1px;line-height:1.15}
            .total{margin-top:4px;margin-right:auto;width:38%;border:1.5px solid #111;padding:4px 6px;display:flex;justify-content:space-between;font-size:10.5px;font-weight:900}
            .order-note{margin-top:4px;border:1px solid #aaa;padding:3px 4px;font-size:6.8px;line-height:1.2}
            .footer{margin-top:3px;border-top:1px solid #aaa;padding-top:2px;display:flex;justify-content:space-between;color:#666;font-size:${measurementOnly ? "5.8px" : "6.3px"}}
            ${shapePrintCss()}
        `;
    }

    function documentHtml(frm, mode) {
        const lines = mode === "invoice" ? invoiceLines(frm) : [];
        const total = mode === "invoice" ? invoiceTotal(frm, lines) : 0;
        const generated = frappe.datetime ? frappe.datetime.now_datetime() : new Date().toISOString();
        return `<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8"><title>${mode === "invoice" ? "فاتورة" : "قياسات"} الطلب ${esc(frm.doc.name || "")}</title><style>${printCss(mode)}</style></head><body>
            ${sharedHeader(frm, mode)}${sharedInfo(frm)}${mode === "invoice" ? invoiceSummary(frm) : ""}
            <div class="title">جدول القياسات</div>${measurementTable(frm)}
            ${mode === "invoice" ? `<div class="title">تفاصيل الفاتورة</div><table class="table invoice"><thead><tr><th>#</th><th class="right">البيان</th><th>الكمية</th><th>الوحدة</th><th>سعر الوحدة $</th><th>الإجمالي $</th></tr></thead><tbody>${invoiceRowsHtml(lines)}</tbody></table><div class="total"><span>الإجمالي النهائي</span><span>$ ${money(total)}</span></div>` : ""}
            ${frm.doc.order_notes ? `<div class="order-note"><b>ملاحظات الطلب:</b> ${esc(frm.doc.order_notes)}</div>` : ""}
            <div class="footer"><span>رقم الطلب: ${esc(frm.doc.name || "مسودة")}</span><span>تاريخ الطباعة: ${esc(generated)}</span></div>
        </body></html>`;
    }

    function printHtml(html) {
        document.getElementById(FRAME_ID)?.remove();
        const frame = document.createElement("iframe");
        frame.id = FRAME_ID;
        frame.setAttribute("aria-hidden", "true");
        frame.style.cssText = "position:fixed;right:0;bottom:0;width:1px;height:1px;border:0;opacity:0;pointer-events:none;z-index:-1";
        let cleaned = false;
        const cleanup = () => {
            if (cleaned) return;
            cleaned = true;
            frame.remove();
        };
        frame.onload = () => {
            try {
                const win = frame.contentWindow;
                if (!win) throw new Error("Print window unavailable");
                win.addEventListener("afterprint", cleanup, { once: true });
                setTimeout(() => { win.focus(); win.print(); }, 100);
            } catch (error) {
                console.error("Unified order print failed", error);
                cleanup();
                frappe.msgprint("تعذر تشغيل الطباعة. أعد تحميل الصفحة ثم حاول مرة أخرى.");
            }
        };
        frame.srcdoc = html;
        document.body.appendChild(frame);
        setTimeout(cleanup, 120000);
    }

    async function printDocument(frm, mode) {
        await ensureProfiles(frm);
        printHtml(documentHtml(frm, mode));
    }

    function bindPrintInterception() {
        if (document._dcoUnifiedDocumentPrintBound) return;
        document._dcoUnifiedDocumentPrintBound = true;
        document.addEventListener("click", event => {
            if (!activeFrm) return;
            const invoiceButton = event.target.closest(".dco-print-customer-invoice");
            const measurementButton = event.target.closest(".dco-print-measurements,.dco-entry-window-print");
            if (!invoiceButton && !measurementButton) return;
            event.preventDefault();
            event.stopImmediatePropagation();
            printDocument(activeFrm, invoiceButton ? "invoice" : "measurements").catch(error => {
                console.error("Order document preparation failed", error);
                frappe.msgprint("تعذر تجهيز المستند للطباعة. أعد تحميل الصفحة ثم حاول مرة أخرى.");
            });
        }, true);
    }

    function schedule(frm) {
        activeFrm = frm;
        bindPrintInterception();
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
    });

    window.AlmdinaOrderDocumentPrint = {
        printInvoice(frm) { return printDocument(frm, "invoice"); },
        printMeasurements(frm) { return printDocument(frm, "measurements"); },
        html: documentHtml,
    };
})();
