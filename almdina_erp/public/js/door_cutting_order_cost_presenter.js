(() => {
    "use strict";

    if (window.AlmdinaOrderCostUX) return;

    const STYLE_ID = "dco-capability-cost-presenter-css";

    function can(frm, capability) {
        const permissions = window.AlmdinaPermissions;
        return Boolean(
            permissions &&
            (
                typeof permissions.canDocument === "function"
                    ? permissions.canDocument(frm, capability)
                    : permissions.can(capability)
            )
        );
    }

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function number(value) {
        const parsed = Number(value || 0);
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function money(value) {
        return number(value).toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    function quantity(value) {
        return number(value).toLocaleString("en-US", {
            maximumFractionDigits: 3,
        });
    }

    function pieceTypeLabel(value) {
        if (value === "Special") return "خاصة";
        if (value === "Clipped Corner") return "زاوية مقصوصة";
        return "عادية";
    }

    function rows(frm) {
        return (frm.doc.pieces || []).map((source, index) => ({
            source,
            name: source.name,
            index: index + 1,
            pieceType: source.piece_type || "Regular",
            width: number(source.width_cm),
            length: number(source.length_cm),
            qty: Math.max(1, Math.trunc(number(source.qty) || 1)),
            edgeType: source.edge_type || frm.doc.default_edge_type || "",
            edgeMeters: number(source.edge_meters),
            edgeRate: number(source.edge_rate_usd),
            edgeAmount: number(source.edge_cost_usd),
            notes: source.notes || "",
            estimatedUnit: number(source.special_shape_estimated_unit_price_usd),
            approvedUnit: number(source.special_shape_custom_unit_price_usd),
            finalUnit: number(source.special_shape_final_unit_price_usd),
            priceStatus: source.special_shape_price_status || "Not Applicable",
            priceNote: source.special_shape_price_note || "",
            drawingStatus: source.special_shape_status || "Not Required",
        }));
    }

    function invoiceLines(frm) {
        const result = [];
        const allRows = rows(frm);
        const specialRows = allRows.filter(row => row.pieceType === "Special");
        const regularRows = specialRows.length
            ? allRows.filter(row => row.pieceType !== "Special")
            : allRows;
        const boardCount = Math.max(0, Math.trunc(number(frm.doc.required_boards)));
        const boardRate = number(frm.doc.board_rate_usd);
        const cuttingRate = number(frm.doc.cutting_cost_per_board_usd);
        const boardAmount = boardCount
            ? boardCount * boardRate
            : number(frm.doc.mdf_cost_usd);
        const cuttingAmount = boardCount
            ? boardCount * cuttingRate
            : number(frm.doc.cutting_cost_usd);

        if (boardCount || boardAmount) {
            result.push({
                type: "material",
                description: `ألواح MDF${frm.doc.board_description ? ` — ${frm.doc.board_description}` : ""}`,
                quantity: boardCount || (boardRate ? boardAmount / boardRate : 0),
                unit: "لوح",
                rate: boardRate,
                amount: boardAmount,
            });
        }

        if (boardCount || cuttingAmount) {
            result.push({
                type: "cutting",
                description: "أجور قص وتجهيز الألواح",
                quantity: boardCount || (cuttingRate ? cuttingAmount / cuttingRate : 0),
                unit: "لوح",
                rate: cuttingRate,
                amount: cuttingAmount,
            });
        }

        const edgeGroups = new Map();
        regularRows.forEach(row => {
            if (row.edgeMeters <= 0) return;
            const key = `${row.edgeType || "قشاط"}::${row.edgeRate}`;
            const group = edgeGroups.get(key) || {
                type: "edge",
                description: `قشاط — ${row.edgeType || "غير محدد"}`,
                quantity: 0,
                unit: "متر",
                rate: row.edgeRate,
                amount: 0,
            };
            group.quantity += row.edgeMeters;
            group.amount += row.edgeAmount || row.edgeMeters * row.edgeRate;
            edgeGroups.set(key, group);
        });
        result.push(...edgeGroups.values());

        if (!edgeGroups.size && !specialRows.length && number(frm.doc.edge_cost_usd) > 0) {
            result.push({
                type: "edge",
                description: "القشاط",
                quantity: number(frm.doc.total_edge_meters),
                unit: "متر",
                rate: 0,
                amount: number(frm.doc.edge_cost_usd),
            });
        }

        specialRows.forEach(row => {
            result.push({
                type: "special",
                description: `درفة خاصة رقم ${row.index} — ${row.priceStatus === "Approved" ? "سعر معتمد شامل" : "سعر تقديري شامل"}`,
                quantity: row.qty,
                unit: "درفة",
                rate: row.finalUnit,
                amount: row.finalUnit * row.qty,
                note: row.priceNote,
            });
        });

        return result;
    }

    function effectiveInvoiceLines(frm) {
        const multiEdge = window.AlmdinaMultiEdgeDocuments;
        if (multiEdge && typeof multiEdge.invoiceLines === "function") {
            return multiEdge.invoiceLines(frm);
        }
        return invoiceLines(frm);
    }

    function invoiceTotal(frm) {
        return effectiveInvoiceLines(frm).reduce(
            (sum, line) => sum + number(line.amount),
            0
        );
    }

    function quoteTotal(frm) {
        const lines = effectiveInvoiceLines(frm);
        if (lines.length) {
            return lines.reduce((sum, line) => sum + number(line.amount), 0);
        }
        return frm.doc.customer_quote_total_usd === undefined
            || frm.doc.customer_quote_total_usd === null
            ? number(frm.doc.total_cost_usd)
            : number(frm.doc.customer_quote_total_usd);
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-cost-shell{direction:rtl;max-width:1440px;margin:0 auto;padding:4px 0 18px}
            .dco-cost-hero{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding:18px 20px;border:1px solid var(--border-color,#dfe4e8);border-radius:16px;background:linear-gradient(135deg,var(--card-bg,#fff),var(--subtle-fg,#f7f9fb));box-shadow:0 8px 24px rgba(23,32,51,.045)}
            .dco-cost-hero h3{margin:0 0 5px;font-size:20px;font-weight:900}
            .dco-cost-hero p{margin:0;color:var(--text-muted,#67727e);font-size:12px;line-height:1.7}
            .dco-cost-actions{display:flex;gap:8px;flex-wrap:wrap}
            .dco-cost-actions .btn{border-radius:9px;font-weight:800}
            .dco-cost-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:12px 0}
            .dco-cost-kpi{padding:13px 14px;border:1px solid var(--border-color,#dfe4e8);border-radius:13px;background:var(--card-bg,#fff)}
            .dco-cost-kpi span{display:block;color:var(--text-muted,#687481);font-size:10px;margin-bottom:4px}
            .dco-cost-kpi b{display:block;font-size:18px;font-weight:900;direction:ltr;text-align:right}
            .dco-cost-kpi.total{border-color:rgba(31,130,82,.3);background:rgba(31,130,82,.055)}
            .dco-cost-section{margin-top:12px;border:1px solid var(--border-color,#dfe4e8);border-radius:15px;background:var(--card-bg,#fff);overflow:hidden}
            .dco-cost-section-title{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:13px 16px;border-bottom:1px solid var(--border-color,#dfe4e8);background:var(--subtle-fg,#f8f9fa)}
            .dco-cost-section-title h4{margin:0;font-size:14px;font-weight:900}
            .dco-cost-section-title span{font-size:10px;color:var(--text-muted,#687481)}
            .dco-cost-table-wrap{overflow:auto}
            .dco-cost-table{width:100%;min-width:760px;border-collapse:collapse;font-size:12px}
            .dco-cost-table th,.dco-cost-table td{padding:9px 10px;border-bottom:1px solid var(--border-color,#e7ebef);text-align:center;vertical-align:middle}
            .dco-cost-table th{background:var(--subtle-fg,#f7f9fb);font-weight:900;white-space:nowrap}
            .dco-cost-table tr:last-child td{border-bottom:0}
            .dco-cost-table .text-start{text-align:right}
            .dco-special-price-list{display:grid;gap:9px;padding:12px}
            .dco-special-price-card{display:grid;grid-template-columns:minmax(190px,1.2fr) repeat(3,minmax(110px,.7fr)) auto;align-items:center;gap:9px;padding:12px;border:1px solid var(--border-color,#e0e5e9);border-radius:13px;background:var(--card-bg,#fff)}
            .dco-special-price-cell{padding:8px 9px;border-radius:10px;background:var(--subtle-fg,#f7f9fa)}
            .dco-special-price-cell span{display:block;font-size:9px;color:var(--text-muted,#687481);margin-bottom:3px}
            .dco-special-price-cell b{display:block;direction:ltr;text-align:right}
            .dco-special-price-actions{display:flex;flex-direction:column;gap:6px}
            .dco-special-price-note{grid-column:1/-1;font-size:10px;color:var(--text-muted,#687481)}
            .dco-cost-empty{padding:24px;text-align:center;color:var(--text-muted,#687481)}
            @media(max-width:900px){.dco-cost-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.dco-cost-hero{flex-direction:column}.dco-special-price-card{grid-template-columns:1fr 1fr}.dco-special-price-actions,.dco-special-price-card>strong,.dco-special-price-note{grid-column:1/-1}}
            @media(max-width:560px){.dco-cost-kpis{grid-template-columns:1fr}.dco-cost-actions .btn{width:100%}}
        `;
        document.head.appendChild(style);
    }

    function measurementRowsHtml(frm) {
        const data = rows(frm);
        if (!data.length) {
            return '<div class="dco-cost-empty">لا توجد قياسات في الطلب بعد.</div>';
        }
        return `<div class="dco-cost-table-wrap"><table class="dco-cost-table"><thead><tr>
            <th>#</th><th>النوع</th><th>العرض (سم)</th><th>الطول (سم)</th><th>العدد</th><th>نوع القشاط</th><th class="text-start">ملاحظات</th>
        </tr></thead><tbody>${data.map(row => `<tr>
            <td><b>${row.index}</b></td><td>${esc(pieceTypeLabel(row.pieceType))}</td>
            <td>${quantity(row.width)}</td><td>${quantity(row.length)}</td><td>${row.qty}</td>
            <td>${esc(row.edgeType || "—")}</td><td class="text-start">${esc(row.notes || "—")}</td>
        </tr>`).join("")}</tbody></table></div>`;
    }

    function invoiceRowsHtml(frm) {
        const lines = effectiveInvoiceLines(frm);
        if (!lines.length) {
            return '<div class="dco-cost-empty">احفظ الطلب واحسب خطة القص لتظهر تفاصيل السعر.</div>';
        }
        return `<div class="dco-cost-table-wrap"><table class="dco-cost-table"><thead><tr>
            <th>#</th><th class="text-start">البيان</th><th>الكمية</th><th>الوحدة</th><th>سعر الوحدة ($)</th><th>الإجمالي ($)</th>
        </tr></thead><tbody>${lines.map((line, index) => `<tr>
            <td>${index + 1}</td><td class="text-start"><b>${esc(line.description)}</b>${line.note ? `<small style="display:block">${esc(line.note)}</small>` : ""}</td>
            <td>${quantity(line.quantity)}</td><td>${esc(line.unit)}</td><td>${money(line.rate)}</td><td><b>${money(line.amount)}</b></td>
        </tr>`).join("")}</tbody></table></div>`;
    }

    function specialPricingHtml(frm) {
        const specialRows = rows(frm).filter(row => row.pieceType === "Special");
        if (!specialRows.length) return "";
        return `<div class="dco-cost-section"><div class="dco-cost-section-title">
            <h4>تسعير الدرف الخاصة</h4><span>السعر النهائي المستخدم لكل درفة خاصة</span>
        </div><div class="dco-special-price-list">${specialRows.map(row => {
            const approved = row.priceStatus === "Approved";
            const documented = row.drawingStatus === "Documented";
            return `<div class="dco-special-price-card" data-special-row="${esc(row.name)}">
                <strong>درفة خاصة رقم ${row.index}<small style="display:block;color:var(--text-muted,#687481)">${quantity(row.width)} × ${quantity(row.length)} سم — عدد ${row.qty}</small></strong>
                <div class="dco-special-price-cell"><span>التقديري / الوحدة</span><b>$ ${money(row.estimatedUnit)}</b></div>
                <div class="dco-special-price-cell"><span>المعتمد / الوحدة</span><b>${approved ? `$ ${money(row.approvedUnit)}` : "—"}</b></div>
                <div class="dco-special-price-cell"><span>الإجمالي المستخدم</span><b>$ ${money(row.finalUnit * row.qty)}</b></div>
                <div class="dco-special-price-actions"><button type="button" class="btn btn-default btn-xs dco-view-special-sketch" ${documented ? "" : "disabled"}>عرض الرسم</button></div>
                ${row.priceNote ? `<div class="dco-special-price-note">${esc(row.priceNote)}</div>` : ""}
            </div>`;
        }).join("")}</div></div>`;
    }

    function bindViewDrawing(frm, wrapper) {
        wrapper.find(".dco-view-special-sketch").on("click", function onViewDrawing() {
            const card = this.closest("[data-special-row]");
            const source = (frm.doc.pieces || []).find(
                row => row.name === (card && card.dataset.specialRow)
            );
            if (!source || !window.AlmdinaSpecialShapeEditor || !window.AlmdinaSpecialShapeEditor.view) {
                frappe.msgprint(__("تعذر تحميل رسم الدرفة الخاصة."));
                return;
            }
            window.AlmdinaSpecialShapeEditor.view(frm, source);
        });
    }

    function render(frm) {
        const field = frm.fields_dict.order_cost_invoice_html;
        if (!field || !field.$wrapper) return false;
        if (!can(frm, "view_costs")) {
            field.$wrapper.empty();
            return false;
        }

        installStyles();
        const boardAmount = number(frm.doc.mdf_cost_usd);
        const cuttingAmount = number(frm.doc.cutting_cost_usd);
        const edgeAmount = number(frm.doc.edge_cost_usd);
        const total = quoteTotal(frm);
        field.$wrapper.html(`<div class="dco-cost-shell">
            <div class="dco-cost-hero"><div><h3>تكلفة الطلب</h3><p>تفاصيل سعر البيع والقياسات والخدمات المحسوبة لهذا الطلب.</p></div>
                <div class="dco-cost-actions"><button type="button" class="btn btn-default btn-sm dco-print-customer-invoice">طباعة فاتورة الزبون</button></div>
            </div>
            <div class="dco-cost-kpis">
                <div class="dco-cost-kpi"><span>الألواح</span><b>$ ${money(boardAmount)}</b></div>
                <div class="dco-cost-kpi"><span>أجور القص</span><b>$ ${money(cuttingAmount)}</b></div>
                <div class="dco-cost-kpi"><span>القشاط</span><b>$ ${money(edgeAmount)}</b></div>
                <div class="dco-cost-kpi total"><span>الإجمالي النهائي</span><b>$ ${money(total)}</b></div>
            </div>
            <div class="dco-cost-section"><div class="dco-cost-section-title"><h4>جدول قياسات الطلب</h4><span>القياسات والكميات والملاحظات</span></div>${measurementRowsHtml(frm)}</div>
            ${specialPricingHtml(frm)}
            <div class="dco-cost-section"><div class="dco-cost-section-title"><h4>تفاصيل عرض السعر</h4><span>الألواح والقص والقشاط والدرف الخاصة</span></div>${invoiceRowsHtml(frm)}</div>
        </div>`);
        bindViewDrawing(frm, field.$wrapper);
        return true;
    }

    window.AlmdinaOrderCostUX = Object.freeze({
        render,
        invoiceLines,
        invoiceTotal,
        quoteTotal,
    });
})();
