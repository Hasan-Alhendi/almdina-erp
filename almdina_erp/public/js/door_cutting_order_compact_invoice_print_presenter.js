(() => {
    "use strict";

    const FRAME_ID = "dco-compact-invoice-print-frame";
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

    function rows(frm) {
        const module = edgeBandingApi();
        return (frm.doc.pieces || []).map((row, index) => ({
            source: row,
            index: index + 1,
            pieceType: row.piece_type || "Regular",
            width: number(row.width_cm),
            length: number(row.length_cm),
            qty: Math.max(1, Math.trunc(number(row.qty) || 1)),
            notes: row.notes || "",
            details: module && typeof module.details === "function"
                ? module.details(frm, row)
                : [],
        }));
    }

    function groupedEdgeDetails(details) {
        const groups = new Map();
        (details || []).forEach(detail => {
            const type = String(detail.edge_type || "غير محدد").trim() || "غير محدد";
            const custom = Boolean(detail.custom);
            const key = `${type}::${custom ? "custom" : "default"}`;
            if (!groups.has(key)) {
                groups.set(key, { type, custom, sides: [] });
            }
            groups.get(key).sides.push(detail.side_label || "ضلع");
        });
        return [...groups.values()];
    }

    function sideSummary(group, totalSides) {
        if (totalSides === 4 && group.sides.length === 4) return "على الداير";
        return group.sides.join("، ");
    }

    function compactEdgeDetailsHtml(details) {
        if (!details || !details.length) {
            return '<span class="edge-none">بدون قشاط</span>';
        }
        const groups = groupedEdgeDetails(details);
        return `<div class="edge-summary">${groups.map(group => `
            <div class="edge-summary-line ${group.custom ? "is-custom" : ""}">
                <span class="edge-sides">${esc(sideSummary(group, details.length))}</span>
                <b>${esc(group.type)}</b>
                ${group.custom ? "<em>مخصص</em>" : ""}
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
            return `<tr>
                <td>${row.index}</td>
                <td>${esc(pieceTypeLabel(row.pieceType))}</td>
                <td>${dimensionMark(row.width, widthCount)}</td>
                <td>${dimensionMark(row.length, longCount)}</td>
                <td>${row.qty}</td>
                <td class="right edge-cell">${compactEdgeDetailsHtml(row.details)}</td>
                <td class="right notes-cell">${esc(row.notes || "—")}</td>
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

    function invoiceRowsHtml(lines) {
        if (!lines.length) {
            return '<tr><td colspan="6">احفظ الطلب واحسب خطة القص لتظهر تفاصيل الفاتورة.</td></tr>';
        }
        return lines.map((line, index) => `<tr>
            <td>${index + 1}</td>
            <td class="right invoice-description"><b>${esc(line.description)}</b>${line.note ? `<span class="line-note">${esc(line.note)}</span>` : ""}</td>
            <td>${quantity(line.quantity)}</td>
            <td>${esc(line.unit)}</td>
            <td>${line.rate || line.rate === 0 ? money(line.rate) : "—"}</td>
            <td><b>${money(line.amount)}</b></td>
        </tr>`).join("");
    }

    function printCss() {
        return `
            @page{size:A4 portrait;margin:8mm}
            *{box-sizing:border-box}
            html,body{margin:0;padding:0;font-family:Tahoma,Arial,sans-serif;color:#111;direction:rtl;background:#fff}
            body{font-size:9px;-webkit-print-color-adjust:exact;print-color-adjust:exact}
            .header{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:1.5px solid #111;padding-bottom:6px;margin-bottom:6px}
            .header h1{font-size:19px;line-height:1.1;margin:0 0 2px}
            .muted{color:#666;font-size:7.5px;line-height:1.25}
            .info{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:4px;margin:6px 0}
            .info>div{border:1px solid #aaa;border-radius:3px;padding:4px 5px;min-width:0;line-height:1.2;word-break:break-word}
            .info b{display:block;font-size:7px;color:#555;margin-bottom:1px}
            .title{font-size:11.5px;font-weight:900;margin:7px 0 3px}
            .table{width:100%;border-collapse:collapse;table-layout:fixed}
            .table th,.table td{border:1px solid #999;padding:3px 4px;text-align:center;vertical-align:middle;line-height:1.15}
            .table th{background:#eee;font-weight:900}
            .table tr{break-inside:avoid;page-break-inside:avoid}
            .right{text-align:right!important;white-space:normal}
            .measurements{font-size:8.1px}
            .measurements th:nth-child(1),.measurements td:nth-child(1){width:3.5%}
            .measurements th:nth-child(2),.measurements td:nth-child(2){width:7.5%}
            .measurements th:nth-child(3),.measurements td:nth-child(3){width:8.5%}
            .measurements th:nth-child(4),.measurements td:nth-child(4){width:8.5%}
            .measurements th:nth-child(5),.measurements td:nth-child(5){width:5.5%}
            .measurements th:nth-child(6),.measurements td:nth-child(6){width:34%}
            .measurements th:nth-child(7),.measurements td:nth-child(7){width:32.5%}
            .edge-summary{display:grid;gap:1px}
            .edge-summary-line{display:flex;align-items:center;gap:3px;min-height:14px;padding:0 2px;white-space:normal}
            .edge-summary-line.is-custom{border:1px solid #b88b00;border-radius:3px;background:#fff8df;padding:1px 3px}
            .edge-sides{font-size:7px;font-weight:800;color:#333}
            .edge-summary-line b{font-size:7.8px;word-break:break-word}
            .edge-summary-line em{margin-inline-start:auto;font-style:normal;font-size:6.5px;font-weight:900;color:#805b00;border:1px solid currentColor;border-radius:999px;padding:0 3px;white-space:nowrap}
            .edge-none{color:#666;font-size:7.2px}
            .notes-cell{font-size:7.8px;line-height:1.25}
            .dimension{display:inline-flex;min-width:30px;flex-direction:column;align-items:center;gap:1px;line-height:1}
            .dimension b{font-size:8.2px}
            .dimension-lines{display:flex;flex-direction:column;gap:1px;min-height:3px}
            .dimension-edge-line{display:block;width:22px;height:1px;background:#111}
            .dimension-lines-0{visibility:hidden}
            .invoice{font-size:8.4px;break-inside:avoid;page-break-inside:avoid}
            .invoice th,.invoice td{padding:3px 4px}
            .invoice th:nth-child(1),.invoice td:nth-child(1){width:4%}
            .invoice th:nth-child(2),.invoice td:nth-child(2){width:48%}
            .invoice th:nth-child(3),.invoice td:nth-child(3){width:11%}
            .invoice th:nth-child(4),.invoice td:nth-child(4){width:10%}
            .invoice th:nth-child(5),.invoice td:nth-child(5){width:13.5%}
            .invoice th:nth-child(6),.invoice td:nth-child(6){width:13.5%}
            .invoice-description{line-height:1.2}
            .line-note{display:block;color:#555;font-size:7px;margin-top:1px;line-height:1.15}
            .total{margin-top:4px;margin-right:auto;width:38%;border:1.5px solid #111;padding:4px 6px;display:flex;justify-content:space-between;font-size:12px;font-weight:900}
            .order-note{margin-top:4px;border:1px solid #aaa;padding:4px 5px;font-size:7.5px;line-height:1.2}
            .footer{margin-top:4px;border-top:1px solid #aaa;padding-top:3px;display:flex;justify-content:space-between;color:#666;font-size:7px}
        `;
    }

    function printInvoiceHtml(frm) {
        const lines = invoiceLines(frm);
        const total = invoiceTotal(frm, lines);
        const generated = frappe.datetime
            ? frappe.datetime.now_datetime()
            : new Date().toISOString();
        return `<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8"><title>فاتورة الطلب ${esc(frm.doc.name || "")}</title><style>${printCss()}</style></head><body>
            <div class="header"><div><h1>عرض سعر الطلب</h1><div class="muted">القشاط الافتراضي يظهر باختصار، وتظهر الاستثناءات المخصصة فقط بالتفصيل</div></div><div style="text-align:left"><b>${esc(frm.doc.name || "مسودة")}</b><div class="muted">${esc(frm.doc.order_date || "")}</div></div></div>
            <div class="info"><div><b>الزبون</b>${esc(frm.doc.customer || "—")}</div><div><b>صنف اللوح</b>${esc(frm.doc.board_description || frm.doc.board_item || "—")}</div><div><b>عدد الألواح</b>${quantity(frm.doc.required_boards)}</div><div><b>سعر اللوح</b>$ ${money(frm.doc.board_rate_usd)}</div><div><b>أجور القص / لوح</b>$ ${money(frm.doc.cutting_cost_per_board_usd)}</div><div><b>إجمالي القشاط</b>$ ${money(frm.doc.edge_cost_usd)}</div></div>
            <div class="title">جدول القياسات والقشاط</div>
            <table class="table measurements"><thead><tr><th>#</th><th>النوع</th><th>العرض</th><th>الطول</th><th>العدد</th><th>قشاط الأطراف</th><th>ملاحظات</th></tr></thead><tbody>${measurementRowsHtml(frm)}</tbody></table>
            <div class="title">تفاصيل الفاتورة</div>
            <table class="table invoice"><thead><tr><th>#</th><th class="right">البيان</th><th>الكمية</th><th>الوحدة</th><th>سعر الوحدة $</th><th>الإجمالي $</th></tr></thead><tbody>${invoiceRowsHtml(lines)}</tbody></table>
            <div class="total"><span>الإجمالي النهائي</span><span>$ ${money(total)}</span></div>
            ${frm.doc.order_notes ? `<div class="order-note"><b>ملاحظات:</b> ${esc(frm.doc.order_notes)}</div>` : ""}
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
                setTimeout(() => {
                    win.focus();
                    win.print();
                }, 100);
            } catch (error) {
                console.error("Compact invoice print failed", error);
                cleanup();
                frappe.msgprint("تعذر تشغيل طباعة عرض السعر. أعد تحميل الصفحة ثم حاول مرة أخرى.");
            }
        };
        frame.srcdoc = html;
        document.body.appendChild(frame);
        setTimeout(cleanup, 120000);
    }

    async function printInvoice(frm) {
        await ensureProfiles(frm);
        printHtml(printInvoiceHtml(frm));
    }

    function bindPrintInterception() {
        if (document._dcoCompactInvoicePrintBound) return;
        document._dcoCompactInvoicePrintBound = true;
        document.addEventListener("click", event => {
            const button = event.target.closest(".dco-print-customer-invoice");
            if (!button || !activeFrm) return;
            event.preventDefault();
            event.stopImmediatePropagation();
            printInvoice(activeFrm).catch(error => {
                console.error("Compact invoice preparation failed", error);
                frappe.msgprint("تعذر تجهيز عرض السعر للطباعة. أعد تحميل الصفحة ثم حاول مرة أخرى.");
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

    window.AlmdinaCompactInvoicePrint = {
        print: printInvoice,
        html: printInvoiceHtml,
    };
})();
