(() => {
    "use strict";

    function isArabic() {
        const lang = String(
            (frappe.boot && frappe.boot.lang) ||
            (frappe.boot && frappe.boot.user && frappe.boot.user.language) ||
            document.documentElement.lang ||
            ""
        ).toLowerCase();
        return lang === "ar" || lang.startsWith("ar-");
    }

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function n(value) {
        const result = Number(value);
        return Number.isFinite(result) ? result : 0;
    }

    function money(value) {
        return n(value).toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    function qty(value) {
        return n(value).toLocaleString("en-US", { maximumFractionDigits: 3 });
    }

    function pieces(frm) {
        return (frm.doc.pieces || []).map((row, index) => ({
            index: index + 1,
            width_cm: n(row.width_cm),
            length_cm: n(row.length_cm),
            qty: Math.max(1, Math.trunc(n(row.qty) || 1)),
            edge_meters: n(row.edge_meters),
            edge_rate_usd: n(row.edge_rate_usd),
            edge_cost_usd: n(row.edge_cost_usd),
            edge_type: row.edge_type || frm.doc.default_edge_type || "",
            width_edge_count: Number(Boolean(row.edge_width_top)) + Number(Boolean(row.edge_width_bottom)),
            length_edge_count: Number(Boolean(row.edge_long_right)) + Number(Boolean(row.edge_long_left)),
            notes: row.notes || "",
        }));
    }

    function dimensionMark(value, edgeCount, printMode = false) {
        const count = Math.max(0, Math.min(2, Number(edgeCount || 0)));
        const lines = Array.from({ length: count }, () => '<span class="dco-dimension-edge-line"></span>').join("");
        return `
            <div class="dco-dimension-mark${printMode ? " dco-dimension-mark--print" : ""}">
                <span class="dco-dimension-value">${qty(value)}</span>
                <span class="dco-dimension-lines dco-dimension-lines-${count}">${lines}</span>
            </div>`;
    }

    function edgeGroups(frm) {
        const groups = new Map();
        pieces(frm).forEach(row => {
            if (row.edge_meters <= 0) return;
            const key = `${row.edge_type || "بدون نوع"}::${row.edge_rate_usd}`;
            if (!groups.has(key)) {
                groups.set(key, {
                    edge_type: row.edge_type || "قشاط",
                    meters: 0,
                    rate: row.edge_rate_usd,
                    amount: 0,
                });
            }
            const group = groups.get(key);
            group.meters += row.edge_meters;
            group.amount += row.edge_cost_usd || row.edge_meters * row.edge_rate_usd;
        });
        return [...groups.values()];
    }

    function invoiceLines(frm) {
        const boardCount = n(frm.doc.required_boards);
        const lines = [];

        if (boardCount > 0 || n(frm.doc.mdf_cost_usd) > 0) {
            lines.push({
                type: "material",
                description: `ألواح MDF${frm.doc.board_item ? ` — ${frm.doc.board_item}` : ""}`,
                quantity: boardCount,
                unit: "لوح",
                rate: n(frm.doc.board_rate_usd),
                amount: n(frm.doc.mdf_cost_usd),
            });
        }

        if (boardCount > 0 || n(frm.doc.cutting_cost_usd) > 0) {
            lines.push({
                type: "cutting",
                description: "أجور قص وتجهيز الألواح",
                quantity: boardCount,
                unit: "لوح",
                rate: n(frm.doc.cutting_cost_per_board_usd),
                amount: n(frm.doc.cutting_cost_usd),
            });
        }

        edgeGroups(frm).forEach(group => {
            lines.push({
                type: "edge",
                description: `قشاط — ${group.edge_type}`,
                quantity: group.meters,
                unit: "متر",
                rate: group.rate,
                amount: group.amount,
            });
        });

        if (!lines.some(line => line.type === "edge") && n(frm.doc.edge_cost_usd) > 0) {
            lines.push({
                type: "edge",
                description: "تكلفة القشاط",
                quantity: n(frm.doc.total_edge_meters),
                unit: "متر",
                rate: 0,
                amount: n(frm.doc.edge_cost_usd),
            });
        }

        return lines;
    }

    function installStyles() {
        if (document.getElementById("dco-cost-invoice-css")) return;
        $("head").append(`
            <style id="dco-cost-invoice-css">
                .dco-cost-shell{direction:rtl;font-family:inherit;max-width:1280px;margin:0 auto;padding:4px 0 18px}
                .dco-cost-hero{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;padding:20px 22px;border:1px solid var(--border-color,#dfe3e8);border-radius:16px;background:linear-gradient(135deg,var(--card-bg,#fff),var(--subtle-fg,#f7f9fb));box-shadow:0 8px 24px rgba(0,0,0,.045)}
                .dco-cost-hero h3{margin:0 0 6px;font-size:20px;font-weight:900}
                .dco-cost-hero p{margin:0;color:var(--text-muted,#6c7680);font-size:12px;line-height:1.7}
                .dco-cost-actions{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-start}
                .dco-cost-actions .btn{border-radius:9px;font-weight:800;min-height:36px}
                .dco-cost-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:12px 0}
                .dco-cost-kpi{padding:14px 15px;border:1px solid var(--border-color,#dfe3e8);border-radius:13px;background:var(--card-bg,#fff)}
                .dco-cost-kpi .label{display:block;font-size:11px;color:var(--text-muted,#6c7680);margin-bottom:5px}
                .dco-cost-kpi .value{display:block;font-size:18px;font-weight:900;line-height:1.25}
                .dco-cost-kpi.total{border-color:rgba(29,128,79,.28);background:rgba(29,128,79,.055)}
                .dco-cost-section{margin-top:12px;border:1px solid var(--border-color,#dfe3e8);border-radius:15px;background:var(--card-bg,#fff);overflow:hidden}
                .dco-cost-section-title{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:13px 16px;border-bottom:1px solid var(--border-color,#dfe3e8);background:var(--subtle-fg,#f8f9fa)}
                .dco-cost-section-title h4{margin:0;font-size:14px;font-weight:900}
                .dco-cost-section-title span{font-size:11px;color:var(--text-muted,#6c7680)}
                .dco-cost-table-wrap{overflow:auto}
                .dco-cost-table{width:100%;border-collapse:collapse;min-width:760px;font-size:12px}
                .dco-cost-table th{background:var(--subtle-fg,#f7f9fb);font-weight:900;white-space:nowrap}
                .dco-cost-table th,.dco-cost-table td{padding:9px 10px;border-bottom:1px solid var(--border-color,#e7eaee);text-align:center;vertical-align:middle}
                .dco-cost-table tbody tr:last-child td{border-bottom:0}
                .dco-cost-table .text-start{text-align:right}
                .dco-dimension-mark{display:inline-flex;min-width:54px;flex-direction:column;align-items:center;justify-content:center;gap:2px;line-height:1.05}
                .dco-dimension-value{font-weight:700;font-variant-numeric:tabular-nums}
                .dco-dimension-lines{display:flex;flex-direction:column;align-items:center;gap:2px;min-height:6px;margin-top:1px}
                .dco-dimension-edge-line{display:block;width:34px;height:1.5px;border-radius:999px;background:currentColor}
                .dco-dimension-lines-0{visibility:hidden}
                .dco-invoice-summary{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:14px;padding:14px}
                .dco-invoice-meta{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;align-content:start}
                .dco-invoice-meta-item{padding:10px 12px;border:1px solid var(--border-color,#e3e6ea);border-radius:10px;background:var(--subtle-fg,#fafbfc)}
                .dco-invoice-meta-item .label{font-size:10px;color:var(--text-muted,#6c7680);display:block;margin-bottom:3px}
                .dco-invoice-meta-item .value{font-size:12px;font-weight:800;word-break:break-word}
                .dco-grand-total{display:flex;flex-direction:column;justify-content:center;padding:18px;border-radius:14px;background:linear-gradient(135deg,#174d33,#24734d);color:#fff;min-height:122px}
                .dco-grand-total .label{font-size:12px;opacity:.85;margin-bottom:5px}
                .dco-grand-total .amount{font-size:30px;font-weight:950;letter-spacing:.2px;direction:ltr;text-align:right}
                .dco-grand-total .hint{font-size:10px;opacity:.72;margin-top:5px}
                .dco-cost-empty{padding:28px;text-align:center;color:var(--text-muted,#6c7680)}
                @media(max-width:900px){.dco-cost-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.dco-invoice-summary{grid-template-columns:1fr}.dco-cost-hero{flex-direction:column}.dco-cost-actions{width:100%}}
                @media(max-width:560px){.dco-cost-kpis,.dco-invoice-meta{grid-template-columns:1fr}.dco-cost-actions .btn{width:100%}}
            </style>
        `);
    }

    function measurementRowsHtml(frm) {
        const rows = pieces(frm);
        if (!rows.length) {
            return `<div class="dco-cost-empty">لا توجد قياسات في الطلب بعد.</div>`;
        }
        return `
            <div class="dco-cost-table-wrap">
                <table class="dco-cost-table">
                    <thead><tr>
                        <th>#</th>
                        <th>العرض (سم)</th>
                        <th>الطول (سم)</th>
                        <th>العدد</th>
                        <th>طول القشاط (م)</th>
                        <th>نوع القشاط</th>
                        <th>ملاحظات</th>
                    </tr></thead>
                    <tbody>${rows.map(row => `
                        <tr>
                            <td><b>${row.index}</b></td>
                            <td>${dimensionMark(row.width_cm, row.width_edge_count)}</td>
                            <td>${dimensionMark(row.length_cm, row.length_edge_count)}</td>
                            <td>${row.qty}</td>
                            <td><b>${qty(row.edge_meters)}</b></td>
                            <td>${esc(row.edge_type || "—")}</td>
                            <td class="text-start">${esc(row.notes || "—")}</td>
                        </tr>`).join("")}</tbody>
                </table>
            </div>`;
    }

    function invoiceRowsHtml(frm) {
        const lines = invoiceLines(frm);
        if (!lines.length) return `<div class="dco-cost-empty">احفظ الطلب واحسب خطة القص لتظهر تفاصيل الفاتورة.</div>`;
        return `
            <div class="dco-cost-table-wrap">
                <table class="dco-cost-table">
                    <thead><tr>
                        <th>#</th><th class="text-start">البيان</th><th>الكمية</th><th>الوحدة</th><th>سعر الوحدة ($)</th><th>الإجمالي ($)</th>
                    </tr></thead>
                    <tbody>${lines.map((line, index) => `
                        <tr>
                            <td>${index + 1}</td>
                            <td class="text-start"><b>${esc(line.description)}</b></td>
                            <td>${qty(line.quantity)}</td>
                            <td>${esc(line.unit)}</td>
                            <td>${line.rate ? money(line.rate) : "—"}</td>
                            <td><b>${money(line.amount)}</b></td>
                        </tr>`).join("")}</tbody>
                </table>
            </div>`;
    }

    function buildScreenHtml(frm) {
        const total = n(frm.doc.total_cost_usd);
        return `
            <div class="dco-cost-shell">
                <div class="dco-cost-hero">
                    <div>
                        <h3>تكلفة الطلب والفاتورة</h3>
                        <p>جدول القياسات مع طول القشاط، ثم تفاصيل تكلفة الألواح والقص والقشاط والإجمالي النهائي القابل للطباعة للزبون.</p>
                    </div>
                    <div class="dco-cost-actions">
                        <button type="button" class="btn btn-primary btn-sm dco-print-customer-invoice">طباعة فاتورة الزبون</button>
                    </div>
                </div>

                <div class="dco-cost-kpis">
                    <div class="dco-cost-kpi"><span class="label">عدد الألواح</span><span class="value">${qty(frm.doc.required_boards)} لوح</span></div>
                    <div class="dco-cost-kpi"><span class="label">إجمالي القشاط</span><span class="value">${qty(frm.doc.total_edge_meters)} م</span></div>
                    <div class="dco-cost-kpi"><span class="label">تكلفة القشاط</span><span class="value">$ ${money(frm.doc.edge_cost_usd)}</span></div>
                    <div class="dco-cost-kpi total"><span class="label">إجمالي تكلفة الطلب</span><span class="value">$ ${money(total)}</span></div>
                </div>

                <div class="dco-cost-section">
                    <div class="dco-cost-section-title">
                        <h4>جدول قياسات الطلب</h4>
                        <span>خط واحد أسفل البعد = جهة قشاط واحدة، خطان = جهتان · طول القشاط محسوب مع الكمية</span>
                    </div>
                    ${measurementRowsHtml(frm)}
                </div>

                <div class="dco-cost-section">
                    <div class="dco-cost-section-title"><h4>تفاصيل الفاتورة</h4><span>التكلفة حسب خطة القص الحالية</span></div>
                    ${invoiceRowsHtml(frm)}
                    <div class="dco-invoice-summary">
                        <div class="dco-invoice-meta">
                            <div class="dco-invoice-meta-item"><span class="label">رقم الطلب</span><span class="value">${esc(frm.doc.name || "مسودة")}</span></div>
                            <div class="dco-invoice-meta-item"><span class="label">الزبون</span><span class="value">${esc(frm.doc.customer || "—")}</span></div>
                            <div class="dco-invoice-meta-item"><span class="label">تاريخ الطلب</span><span class="value">${esc(frm.doc.order_date || "—")}</span></div>
                            <div class="dco-invoice-meta-item"><span class="label">صنف اللوح</span><span class="value">${esc(frm.doc.board_item || "—")}</span></div>
                        </div>
                        <div class="dco-grand-total">
                            <span class="label">الإجمالي النهائي</span>
                            <span class="amount">$ ${money(total)}</span>
                            <span class="hint">ألواح + قص + قشاط</span>
                        </div>
                    </div>
                </div>
            </div>`;
    }

    function buildPrintHtml(frm) {
        const rows = pieces(frm);
        const lines = invoiceLines(frm);
        const total = n(frm.doc.total_cost_usd);
        const generated = frappe.datetime ? frappe.datetime.now_datetime() : new Date().toISOString();
        return `<!doctype html>
<html dir="rtl" lang="ar"><head><meta charset="utf-8"><title>فاتورة الطلب ${esc(frm.doc.name || "")}</title>
<style>
@page{size:A4 portrait;margin:12mm}*{box-sizing:border-box}body{font-family:Tahoma,Arial,sans-serif;color:#111;margin:0;font-size:11px;direction:rtl;-webkit-print-color-adjust:exact;print-color-adjust:exact}.header{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:2px solid #111;padding-bottom:10px;margin-bottom:12px}.title h1{font-size:22px;margin:0 0 5px}.muted{color:#666;font-size:10px}.info{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;margin:10px 0}.info>div{border:1px solid #bbb;border-radius:6px;padding:7px}.info b{display:block;font-size:9px;color:#555;margin-bottom:3px}.section-title{font-size:14px;font-weight:800;margin:14px 0 6px}.table{width:100%;border-collapse:collapse}.table th,.table td{border:1px solid #999;padding:5px;text-align:center;vertical-align:middle}.table th{background:#eee;font-weight:800}.table .right{text-align:right}.measurements{font-size:9px}.invoice{font-size:10px}.dco-dimension-mark{display:inline-flex;min-width:38px;flex-direction:column;align-items:center;justify-content:center;gap:1px;line-height:1}.dco-dimension-value{font-weight:700}.dco-dimension-lines{display:flex;flex-direction:column;align-items:center;gap:1.5px;min-height:5px;margin-top:1px}.dco-dimension-edge-line{display:block;width:28px;height:1px;background:#111}.dco-dimension-lines-0{visibility:hidden}.total-box{margin-top:10px;margin-right:auto;width:45%;border:2px solid #111;padding:10px;display:flex;justify-content:space-between;align-items:center}.total-box span:first-child{font-size:14px;font-weight:800}.total-box .amount{font-size:22px;font-weight:900;direction:ltr}.notes{margin-top:12px;padding:8px;border:1px solid #bbb;min-height:36px}.footer{margin-top:14px;border-top:1px solid #bbb;padding-top:6px;font-size:9px;color:#666;display:flex;justify-content:space-between}
</style></head><body>
<div class="header"><div class="title"><h1>فاتورة تكلفة الطلب</h1><div class="muted">تفاصيل القياسات والمواد وخدمات القص والقشاط</div></div><div style="text-align:left"><b>${esc(frm.doc.name || "مسودة")}</b><div class="muted">${esc(frm.doc.order_date || "")}</div></div></div>
<div class="info"><div><b>الزبون</b>${esc(frm.doc.customer || "—")}</div><div><b>صنف اللوح</b>${esc(frm.doc.board_item || "—")}</div><div><b>عدد الألواح</b>${qty(frm.doc.required_boards)}</div><div><b>إجمالي القشاط</b>${qty(frm.doc.total_edge_meters)} متر</div></div>
<div class="section-title">جدول القياسات <span class="muted">— الخطوط أسفل العرض والطول تمثل عدد جهات القشاط</span></div>
<table class="table measurements"><thead><tr><th>#</th><th>العرض سم</th><th>الطول سم</th><th>العدد</th><th>طول القشاط م</th><th>نوع القشاط</th><th>ملاحظات</th></tr></thead><tbody>
${rows.map(row => `<tr><td>${row.index}</td><td>${dimensionMark(row.width_cm,row.width_edge_count,true)}</td><td>${dimensionMark(row.length_cm,row.length_edge_count,true)}</td><td>${row.qty}</td><td><b>${qty(row.edge_meters)}</b></td><td>${esc(row.edge_type || "—")}</td><td class="right">${esc(row.notes || "—")}</td></tr>`).join("")}
</tbody></table>
<div class="section-title">تفاصيل الفاتورة</div>
<table class="table invoice"><thead><tr><th>#</th><th class="right">البيان</th><th>الكمية</th><th>الوحدة</th><th>سعر الوحدة $</th><th>الإجمالي $</th></tr></thead><tbody>
${lines.map((line,index)=>`<tr><td>${index+1}</td><td class="right"><b>${esc(line.description)}</b></td><td>${qty(line.quantity)}</td><td>${esc(line.unit)}</td><td>${line.rate?money(line.rate):"—"}</td><td><b>${money(line.amount)}</b></td></tr>`).join("")}
</tbody></table>
<div class="total-box"><span>الإجمالي النهائي</span><span class="amount">$ ${money(total)}</span></div>
${frm.doc.order_notes ? `<div class="notes"><b>ملاحظات:</b> ${esc(frm.doc.order_notes)}</div>` : ""}
<div class="footer"><span>رقم الطلب: ${esc(frm.doc.name || "مسودة")}</span><span>تاريخ الطباعة: ${esc(generated)}</span></div>
</body></html>`;
    }

    function printInvoice(frm) {
        // Print inside an isolated same-page iframe instead of opening a popup.
        // This avoids browser popup blockers while keeping only the invoice in the print job.
        const previous = document.getElementById("dco-customer-invoice-print-frame");
        if (previous) previous.remove();

        const frame = document.createElement("iframe");
        frame.id = "dco-customer-invoice-print-frame";
        frame.setAttribute("aria-hidden", "true");
        frame.style.position = "fixed";
        frame.style.right = "0";
        frame.style.bottom = "0";
        frame.style.width = "1px";
        frame.style.height = "1px";
        frame.style.border = "0";
        frame.style.opacity = "0";
        frame.style.pointerEvents = "none";
        frame.style.zIndex = "-1";

        let printed = false;
        let cleaned = false;
        const cleanup = () => {
            if (cleaned) return;
            cleaned = true;
            if (frame.parentNode) frame.parentNode.removeChild(frame);
        };

        frame.onload = () => {
            if (printed) return;
            printed = true;
            try {
                const printWindow = frame.contentWindow;
                if (!printWindow) throw new Error("Print iframe window is unavailable.");
                printWindow.addEventListener("afterprint", cleanup, { once: true });
                setTimeout(() => {
                    printWindow.focus();
                    printWindow.print();
                }, 120);
            } catch (error) {
                console.error("Customer invoice print failed", error);
                cleanup();
                frappe.msgprint("تعذر تشغيل الطباعة من المتصفح. أعد تحميل الصفحة ثم حاول مرة أخرى.");
            }
        };

        frame.srcdoc = buildPrintHtml(frm);
        document.body.appendChild(frame);

        // Safety cleanup for browsers that do not fire afterprint.
        setTimeout(cleanup, 120000);
    }

    function render(frm) {
        installStyles();
        if (isArabic()) frm.set_df_property("cost_tab", "label", "تكلفة الطلب");
        const field = frm.fields_dict.order_cost_invoice_html;
        if (!field || !field.$wrapper) return;
        field.$wrapper.html(buildScreenHtml(frm));
        field.$wrapper.find(".dco-print-customer-invoice").on("click", () => printInvoice(frm));
    }

    function scheduleRender(frm) {
        requestAnimationFrame(() => render(frm));
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { scheduleRender(frm); },
        refresh(frm) { scheduleRender(frm); },
        customer(frm) { scheduleRender(frm); },
        order_date(frm) { scheduleRender(frm); },
        board_item(frm) { scheduleRender(frm); },
        default_edge_type(frm) { scheduleRender(frm); },
        pieces_add(frm) { scheduleRender(frm); },
        pieces_remove(frm) { scheduleRender(frm); },
    });
})();
