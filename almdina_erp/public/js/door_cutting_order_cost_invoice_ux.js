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

    function pieceTypeLabel(row) {
        if (row.piece_type === "Special") return "خاصة";
        if (row.piece_type === "Clipped Corner") return "زاوية مقصوصة";
        return "عادية";
    }

    function effectiveEdgeType(frm, row) {
        return row.edge_type || frm.doc.default_edge_type || "";
    }

    function loadEdgeColors(frm) {
        const types = [...new Set((frm.doc.pieces || []).map(row => effectiveEdgeType(frm, row)).filter(Boolean))];
        if (frm.doc.default_edge_type) types.push(frm.doc.default_edge_type);
        const uniqueTypes = [...new Set(types)];
        frm._dco_edge_color_map = frm._dco_edge_color_map || {};
        const missing = uniqueTypes.filter(type => !(type in frm._dco_edge_color_map));
        if (!missing.length) return Promise.resolve();

        return Promise.all(missing.map(type =>
            frappe.db.get_value("Edge Banding Type", type, "edge_color")
                .then(r => {
                    frm._dco_edge_color_map[type] = (r && r.message && r.message.edge_color) || "";
                })
                .catch(error => {
                    console.warn(`Could not load edge color for ${type}`, error);
                    frm._dco_edge_color_map[type] = "";
                })
        ));
    }

    function pieces(frm) {
        const colorMap = frm._dco_edge_color_map || {};
        return (frm.doc.pieces || []).map((row, index) => {
            const edgeType = effectiveEdgeType(frm, row);
            return {
                row_name: row.name,
                index: index + 1,
                piece_type: row.piece_type || "Regular",
                width_cm: n(row.width_cm),
                length_cm: n(row.length_cm),
                area_m2: n(row.area_m2),
                qty: Math.max(1, Math.trunc(n(row.qty) || 1)),
                edge_meters: n(row.edge_meters),
                edge_rate_usd: n(row.edge_rate_usd),
                edge_cost_usd: n(row.edge_cost_usd),
                edge_type: edgeType,
                edge_color: colorMap[edgeType] || "",
                width_edge_count: Number(Boolean(row.edge_width_top)) + Number(Boolean(row.edge_width_bottom)),
                length_edge_count: Number(Boolean(row.edge_long_right)) + Number(Boolean(row.edge_long_left)),
                notes: row.notes || "",
                drawing_json: row.special_shape_drawing_json || "",
                geometry_json: row.special_shape_geometry_json || "",
                shape_status: row.special_shape_status || "Not Required",
                estimated_unit_price: n(row.special_shape_estimated_unit_price_usd),
                custom_unit_price: n(row.special_shape_custom_unit_price_usd),
                final_unit_price: n(row.special_shape_final_unit_price_usd),
                price_status: row.special_shape_price_status || "Not Applicable",
                price_note: row.special_shape_price_note || "",
                price_approved_by: row.special_shape_price_approved_by || "",
                price_approved_on: row.special_shape_price_approved_on || "",
            };
        });
    }

    function specialRows(frm) {
        return pieces(frm).filter(row => row.piece_type === "Special");
    }

    function boardLabel(frm) {
        return String(frm.doc.board_description || frm.doc.board_item || "").trim();
    }

    function orderEdgeColor(frm) {
        const explicit = String(frm.doc.edge_color || "").trim();
        if (explicit) return explicit;
        return edgeColorLabel(frm);
    }

    function invoiceTotal(frm) {
        return invoiceLines(frm).reduce((sum, line) => sum + n(line.amount), 0);
    }

    function quoteTotal(frm) {
        const lines = invoiceLines(frm);
        if (lines.length) {
            return invoiceTotal(frm);
        }
        return frm.doc.customer_quote_total_usd === undefined || frm.doc.customer_quote_total_usd === null
            ? n(frm.doc.total_cost_usd)
            : n(frm.doc.customer_quote_total_usd);
    }

    function quoteStatusLabel(status) {
        return {
            Automatic: "تلقائي",
            Estimated: "تقديري",
            "Partially Approved": "معتمد جزئيًا",
            Approved: "معتمد",
        }[status] || status || "تلقائي";
    }

    function canApproveSpecialPrice() {
        const roles = (frappe.user_roles || []);
        return roles.includes("Accounts Management") || roles.includes("System Manager");
    }

    function edgeColorLabel(frm) {
        const colors = [...new Set(pieces(frm).map(row => row.edge_color).filter(Boolean))];
        return colors.length ? colors.join("، ") : "—";
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

    function shapePrint() {
        return window.AlmdinaShapePrint || null;
    }

    function rowHasDrawing(row) {
        const renderer = shapePrint();
        return Boolean(renderer && renderer.hasVisual(row));
    }

    function printNotesCell(row) {
        const renderer = shapePrint();
        return renderer
            ? renderer.notesCell(row, row.notes, { label: `رسمة الدرفة رقم ${row.index}` })
            : esc(row.notes || "—");
    }

    function shapePrintCss() {
        const renderer = shapePrint();
        return renderer ? renderer.css : "";
    }

    function edgeGroups(frm, sourceRows = pieces(frm)) {
        const groups = new Map();
        sourceRows.forEach(row => {
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
        const allRows = pieces(frm);
        const specials = allRows.filter(row => row.piece_type === "Special");
        const regularRows = allRows.filter(row => row.piece_type !== "Special");
        const hasSpecialPricing = specials.length > 0;
        const boardRate = n(frm.doc.board_rate_usd);
        const cuttingRate = n(frm.doc.cutting_cost_per_board_usd);
        const materialAmount = boardCount > 0 ? boardCount * boardRate : n(frm.doc.mdf_cost_usd);
        const cuttingAmount = boardCount > 0 ? boardCount * cuttingRate : n(frm.doc.cutting_cost_usd);
        const boardName = boardLabel(frm);

        if (boardCount > 0 || materialAmount > 0) {
            lines.push({
                type: "material",
                description: `ألواح MDF${boardName ? ` — ${boardName}` : ""}`,
                quantity: boardCount || (boardRate > 0 ? materialAmount / boardRate : 0),
                unit: "لوح",
                rate: boardRate,
                amount: materialAmount,
            });
        }

        if (boardCount > 0 || cuttingAmount > 0) {
            lines.push({
                type: "cutting",
                description: "أجور قص وتجهيز الألواح",
                quantity: boardCount || (cuttingRate > 0 ? cuttingAmount / cuttingRate : 0),
                unit: "لوح",
                rate: cuttingRate,
                amount: cuttingAmount,
            });
        }

        edgeGroups(frm, hasSpecialPricing ? regularRows : allRows).forEach(group => {
            lines.push({
                type: "edge",
                description: `قشاط — ${group.edge_type}`,
                quantity: group.meters,
                unit: "متر",
                rate: group.rate,
                amount: group.amount,
            });
        });

        if (
            !hasSpecialPricing
            && !lines.some(line => line.type === "edge")
            && n(frm.doc.edge_cost_usd) > 0
        ) {
            lines.push({
                type: "edge",
                description: "تكلفة القشاط",
                quantity: n(frm.doc.total_edge_meters),
                unit: "متر",
                rate: 0,
                amount: n(frm.doc.edge_cost_usd),
            });
        }

        specials.forEach(row => {
            lines.push({
                type: "special",
                description: `درفة خاصة رقم ${row.index} — ${row.price_status === "Approved" ? "سعر معتمد شامل" : "سعر تقديري شامل"}`,
                quantity: row.qty,
                unit: "درفة",
                rate: row.final_unit_price,
                amount: row.final_unit_price * row.qty,
                note: row.price_note,
            });
        });

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
                .dco-cost-kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin:12px 0}
                .dco-cost-kpi{padding:14px 15px;border:1px solid var(--border-color,#dfe3e8);border-radius:13px;background:var(--card-bg,#fff)}
                .dco-cost-kpi .label{display:block;font-size:11px;color:var(--text-muted,#6c7680);margin-bottom:5px}
                .dco-cost-kpi .value{display:block;font-size:18px;font-weight:900;line-height:1.25;word-break:break-word}
                .dco-cost-kpi.total{border-color:rgba(29,128,79,.28);background:rgba(29,128,79,.055)}
                .dco-cost-section{margin-top:12px;border:1px solid var(--border-color,#dfe3e8);border-radius:15px;background:var(--card-bg,#fff);overflow:hidden}
                .dco-cost-section-title{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:13px 16px;border-bottom:1px solid var(--border-color,#dfe3e8);background:var(--subtle-fg,#f8f9fa)}
                .dco-cost-section-title h4{margin:0;font-size:14px;font-weight:900}
                .dco-cost-section-title span{font-size:11px;color:var(--text-muted,#6c7680)}
                .dco-cost-table-wrap{overflow:auto}
                .dco-cost-table{width:100%;border-collapse:collapse;min-width:700px;font-size:12px}
                .dco-cost-table th{background:var(--subtle-fg,#f7f9fb);font-weight:900;white-space:nowrap}
                .dco-cost-table th,.dco-cost-table td{padding:9px 10px;border-bottom:1px solid var(--border-color,#e7eaee);text-align:center;vertical-align:middle}
                .dco-cost-table tbody tr:last-child td{border-bottom:0}
                .dco-cost-table .text-start{text-align:right}
                .dco-cost-table .dco-notes-col{width:34%;min-width:260px;white-space:normal;line-height:1.65}
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
                .dco-special-price-list{display:grid;gap:10px;padding:13px}
                .dco-special-price-card{display:grid;grid-template-columns:minmax(210px,1.2fr) repeat(4,minmax(112px,.65fr)) auto;align-items:center;gap:10px;padding:13px;border:1px solid var(--border-color,#e0e5e9);border-radius:13px;background:var(--card-bg,#fff)}
                .dco-special-price-identity{display:flex;align-items:center;gap:10px;min-width:0}
                .dco-special-price-icon{display:grid;place-items:center;width:42px;height:42px;border-radius:12px;background:linear-gradient(135deg,#fff4d9,#f0d6a3);color:#6d471c;font-size:20px;flex:0 0 auto}
                .dco-special-price-identity b{display:block;font-size:13px}.dco-special-price-identity small{display:block;color:var(--text-muted,#6c7680);font-size:10px;margin-top:3px}
                .dco-special-price-cell{padding:8px 9px;border-radius:10px;background:var(--subtle-fg,#f7f9fa);min-height:51px}
                .dco-special-price-cell .label{display:block;color:var(--text-muted,#6c7680);font-size:9px;margin-bottom:3px}.dco-special-price-cell .value{font-size:13px;font-weight:900;direction:ltr;text-align:right}
                .dco-special-price-status{display:inline-flex;align-items:center;gap:5px;border-radius:999px;padding:4px 8px;font-size:10px;font-weight:900;background:#fff4d8;color:#8a5a12}
                .dco-special-price-status.is-approved{background:rgba(31,130,82,.1);color:#17643f}
                .dco-special-price-actions{display:flex;flex-direction:column;gap:6px;min-width:112px}
                .dco-special-price-actions .btn{border-radius:8px;font-size:10px;font-weight:800}
                .dco-special-price-note{grid-column:1/-1;padding:7px 10px;border-radius:8px;background:var(--subtle-fg,#f7f9fa);font-size:10px;color:var(--text-muted,#63717e)}
                .dco-invoice-line-note{display:block;margin-top:4px;color:var(--text-muted,#63717e);font-size:10px;font-weight:400;line-height:1.55}
                .dco-quote-state{display:inline-flex;align-items:center;margin-right:7px;padding:3px 8px;border-radius:999px;background:rgba(255,255,255,.16);font-size:10px;font-weight:800}
                @media(max-width:900px){.dco-cost-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.dco-invoice-summary{grid-template-columns:1fr}.dco-cost-hero{flex-direction:column}.dco-cost-actions{width:100%}}
                @media(max-width:1050px){.dco-special-price-card{grid-template-columns:1fr 1fr}.dco-special-price-identity,.dco-special-price-note{grid-column:1/-1}.dco-special-price-actions{flex-direction:row}}
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
                        <th>النوع</th>
                        <th>العرض (سم)</th>
                        <th>الطول (سم)</th>
                        <th>العدد</th>
                        <th>نوع القشاط</th>
                        <th class="dco-notes-col">ملاحظات</th>
                    </tr></thead>
                    <tbody>${rows.map(row => `
                        <tr>
                            <td><b>${row.index}</b></td>
                            <td>${row.piece_type === "Special" ? '<span class="dco-special-price-status">خاصة</span>' : pieceTypeLabel(row)}</td>
                            <td>${dimensionMark(row.width_cm, row.width_edge_count)}</td>
                            <td>${dimensionMark(row.length_cm, row.length_edge_count)}</td>
                            <td>${row.qty}</td>
                            <td>${esc(row.edge_type || "—")}</td>
                            <td class="text-start dco-notes-col">${esc(row.notes || "—")}</td>
                        </tr>`).join("")}</tbody>
                </table>
            </div>`;
    }

    function specialPricingHtml(frm) {
        const rows = specialRows(frm);
        if (!rows.length) return "";
        const approver = canApproveSpecialPrice();
        const saved = !frm.is_new();
        return `
            <div class="dco-cost-section">
                <div class="dco-cost-section-title">
                    <h4>تسعير الدرف الخاصة</h4>
                    <span>التقدير يشمل خام اللوح والقص والقشاط المبدئي والرسوم الخاصة، ويمكن للمحاسب اعتماد سعر شامل</span>
                </div>
                <div class="dco-special-price-list">
                    ${rows.map(row => {
                        const approved = row.price_status === "Approved";
                        const exactGeometry = Boolean(row.geometry_json);
                        const documented = exactGeometry || Boolean(row.drawing_json);
                        return `<div class="dco-special-price-card" data-special-row="${esc(row.row_name)}">
                            <div class="dco-special-price-identity">
                                <span class="dco-special-price-icon">✦</span>
                                <span><b>درفة خاصة رقم ${row.index}</b><small>${qty(row.width_cm)} × ${qty(row.length_cm)} سم — عدد ${row.qty} · ${exactGeometry ? "مسار هندسي موثق" : (documented ? "رسم توضيحي موثق" : "بانتظار الشكل")}</small></span>
                            </div>
                            <div class="dco-special-price-cell"><span class="label">القشاط المبدئي للسطر</span><span class="value">${qty(row.edge_meters)} م · $ ${money(row.edge_cost_usd)}</span></div>
                            <div class="dco-special-price-cell"><span class="label">تقدير النظام / الوحدة</span><span class="value">$ ${money(row.estimated_unit_price)}</span></div>
                            <div class="dco-special-price-cell"><span class="label">السعر المعتمد / الوحدة</span><span class="value">${approved ? `$ ${money(row.custom_unit_price)}` : "—"}</span></div>
                            <div class="dco-special-price-cell"><span class="label">الإجمالي المستخدم</span><span class="value">$ ${money(row.final_unit_price * row.qty)}</span></div>
                            <div class="dco-special-price-actions">
                                <button type="button" class="btn btn-default btn-xs dco-view-special-sketch" ${documented ? "" : "disabled"}>عرض الرسم</button>
                                ${approver ? `<button type="button" class="btn ${approved ? "btn-default" : "btn-primary"} btn-xs dco-approve-special-price" ${saved && documented ? "" : "disabled"}>${approved ? "تعديل السعر" : "اعتماد سعر"}</button>` : ""}
                                <span class="dco-special-price-status ${approved ? "is-approved" : ""}">${approved ? "✓ سعر معتمد" : "◷ سعر تقديري"}</span>
                            </div>
                            ${approved ? `<div class="dco-special-price-note">اعتمده ${esc(row.price_approved_by || "—")} في ${esc(row.price_approved_on || "—")}${row.price_note ? ` — ${esc(row.price_note)}` : ""}</div>` : (!saved ? '<div class="dco-special-price-note">احفظ الطلب أولًا ليتمكن المحاسب من اعتماد السعر.</div>' : "")}
                        </div>`;
                    }).join("")}
                </div>
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
                            <td class="text-start"><b>${esc(line.description)}</b>${line.note ? `<span class="dco-invoice-line-note">ملاحظة السعر: ${esc(line.note)}</span>` : ""}</td>
                            <td>${qty(line.quantity)}</td>
                            <td>${esc(line.unit)}</td>
                            <td>${line.rate || line.rate === 0 ? money(line.rate) : "—"}</td>
                            <td><b>${money(line.amount)}</b></td>
                        </tr>`).join("")}</tbody>
                </table>
            </div>`;
    }

    function buildScreenHtml(frm) {
        const total = quoteTotal(frm);
        const edgeColor = orderEdgeColor(frm);
        const boardName = boardLabel(frm);
        return `
            <div class="dco-cost-shell">
                <div class="dco-cost-hero">
                    <div>
                        <h3>تكلفة الطلب وعرض السعر</h3>
                        <p>التكلفة الداخلية تبقى مستقلة، والدرف الخاصة تظهر تقديرية حتى يعتمد المحاسب سعرها الشامل.</p>
                    </div>
                    <div class="dco-cost-actions">
                        <button type="button" class="btn btn-primary btn-sm dco-print-customer-invoice">طباعة فاتورة الزبون</button>
                    </div>
                </div>

                <div class="dco-cost-kpis">
                    <div class="dco-cost-kpi"><span class="label">سعر اللوح</span><span class="value">$ ${money(frm.doc.board_rate_usd)}</span></div>
                    <div class="dco-cost-kpi"><span class="label">أجور القص / لوح</span><span class="value">$ ${money(frm.doc.cutting_cost_per_board_usd)}</span></div>
                    <div class="dco-cost-kpi"><span class="label">لون القشاط</span><span class="value">${esc(edgeColor)}</span></div>
                    <div class="dco-cost-kpi"><span class="label">تكلفة القشاط</span><span class="value">$ ${money(frm.doc.edge_cost_usd)}</span></div>
                    <div class="dco-cost-kpi total"><span class="label">إجمالي الفاتورة — ${esc(quoteStatusLabel(frm.doc.customer_quote_status))}</span><span class="value">$ ${money(total)}</span></div>
                </div>

                <div class="dco-cost-section">
                    <div class="dco-cost-section-title">
                        <h4>جدول قياسات الطلب</h4>
                        <span>خط واحد أسفل البعد = جهة قشاط واحدة، خطان = جهتان</span>
                    </div>
                    ${measurementRowsHtml(frm)}
                </div>

                ${specialPricingHtml(frm)}

                <div class="dco-cost-section">
                    <div class="dco-cost-section-title"><h4>تفاصيل الفاتورة</h4><span>التكلفة حسب خطة القص الحالية</span></div>
                    ${invoiceRowsHtml(frm)}
                    <div class="dco-invoice-summary">
                        <div class="dco-invoice-meta">
                            <div class="dco-invoice-meta-item"><span class="label">رقم الطلب</span><span class="value">${esc(frm.doc.name || "مسودة")}</span></div>
                            <div class="dco-invoice-meta-item"><span class="label">الزبون</span><span class="value">${esc(frm.doc.customer || "—")}</span></div>
                            <div class="dco-invoice-meta-item"><span class="label">تاريخ الطلب</span><span class="value">${esc(frm.doc.order_date || "—")}</span></div>
                            <div class="dco-invoice-meta-item"><span class="label">صنف اللوح</span><span class="value">${esc(boardName || "—")}</span></div>
                            <div class="dco-invoice-meta-item"><span class="label">عدد الألواح</span><span class="value">${qty(frm.doc.required_boards)}</span></div>
                        </div>
                        <div class="dco-grand-total">
                            <span class="label">الإجمالي النهائي</span>
                            <span class="amount">$ ${money(total)}</span>
                            <span class="hint">عرض الزبون <span class="dco-quote-state">${esc(quoteStatusLabel(frm.doc.customer_quote_status))}</span></span>
                        </div>
                    </div>
                </div>
            </div>`;
    }

    function buildPrintHtml(frm) {
        const rows = pieces(frm);
        const lines = invoiceLines(frm);
        const total = quoteTotal(frm);
        const edgeColor = orderEdgeColor(frm);
        const boardName = boardLabel(frm);
        const generated = frappe.datetime ? frappe.datetime.now_datetime() : new Date().toISOString();
        return `<!doctype html>
<html dir="rtl" lang="ar"><head><meta charset="utf-8"><title>فاتورة الطلب ${esc(frm.doc.name || "")}</title>
<style>
@page{size:A4 portrait;margin:12mm}*{box-sizing:border-box}body{font-family:Tahoma,Arial,sans-serif;color:#111;margin:0;font-size:11px;direction:rtl;-webkit-print-color-adjust:exact;print-color-adjust:exact}.header{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:2px solid #111;padding-bottom:10px;margin-bottom:12px}.title h1{font-size:22px;margin:0 0 5px}.muted{color:#666;font-size:10px}.info{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin:10px 0}.info>div{border:1px solid #bbb;border-radius:6px;padding:7px}.info b{display:block;font-size:9px;color:#555;margin-bottom:3px}.section-title{font-size:14px;font-weight:800;margin:14px 0 6px}.table{width:100%;border-collapse:collapse}.table th,.table td{border:1px solid #999;padding:5px;text-align:center;vertical-align:middle}.table th{background:#eee;font-weight:800}.table .right{text-align:right}.measurements{font-size:9px}.measurements .notes-col{width:36%;text-align:right;white-space:normal;line-height:1.55}.invoice{font-size:10px}.invoice .line-note{display:block;margin-top:3px;color:#555;font-size:8.5px;font-weight:400;line-height:1.45}.dco-dimension-mark{display:inline-flex;min-width:38px;flex-direction:column;align-items:center;justify-content:center;gap:1px;line-height:1}.dco-dimension-value{font-weight:700}.dco-dimension-lines{display:flex;flex-direction:column;align-items:center;gap:1.5px;min-height:5px;margin-top:1px}.dco-dimension-edge-line{display:block;width:28px;height:1px;background:#111}.dco-dimension-lines-0{visibility:hidden}.total-box{margin-top:10px;margin-right:auto;width:45%;border:2px solid #111;padding:10px;display:flex;justify-content:space-between;align-items:center}.total-box span:first-child{font-size:14px;font-weight:800}.total-box .amount{font-size:22px;font-weight:900;direction:ltr}.notes{margin-top:12px;padding:8px;border:1px solid #bbb;min-height:36px}.footer{margin-top:14px;border-top:1px solid #bbb;padding-top:6px;font-size:9px;color:#666;display:flex;justify-content:space-between}
${shapePrintCss()}
</style></head><body>
<div class="header"><div class="title"><h1>عرض سعر الطلب</h1><div class="muted">فاتورة تكلفة الطلب — تفاصيل القياسات والخدمات وتسعير الدرف الخاصة</div></div><div style="text-align:left"><b>${esc(frm.doc.name || "مسودة")}</b><div class="muted">${esc(frm.doc.order_date || "")}</div><div class="muted">حالة السعر: ${esc(quoteStatusLabel(frm.doc.customer_quote_status))}</div></div></div>
<div class="info"><div><b>الزبون</b>${esc(frm.doc.customer || "—")}</div><div><b>صنف اللوح</b>${esc(boardName || "—")}</div><div><b>عدد الألواح</b>${qty(frm.doc.required_boards)}</div><div><b>سعر اللوح</b>$ ${money(frm.doc.board_rate_usd)}</div><div><b>أجور القص / لوح</b>$ ${money(frm.doc.cutting_cost_per_board_usd)}</div><div><b>لون القشاط</b>${esc(edgeColor)}</div></div>
<div class="section-title">جدول القياسات <span class="muted">— الخطوط أسفل العرض والطول تمثل عدد الحواف المطلوب تلبيسها</span></div>
<table class="table measurements"><thead><tr><th>#</th><th>النوع</th><th>العرض سم</th><th>الطول سم</th><th>العدد</th><th>نوع القشاط</th><th class="notes-col">ملاحظات</th></tr></thead><tbody>
${rows.map(row => `<tr class="${rowHasDrawing(row) ? "dco-row-with-sketch" : ""}"><td>${row.index}</td><td>${pieceTypeLabel(row)}</td><td>${dimensionMark(row.width_cm,row.width_edge_count,true)}</td><td>${dimensionMark(row.length_cm,row.length_edge_count,true)}</td><td>${row.qty}</td><td>${esc(row.edge_type || "—")}</td><td class="notes-col ${rowHasDrawing(row) ? "dco-notes-has-sketch" : ""}">${printNotesCell(row)}</td></tr>`).join("")}
</tbody></table>
<div class="section-title">تفاصيل الفاتورة</div>
<table class="table invoice"><thead><tr><th>#</th><th class="right">البيان</th><th>الكمية</th><th>الوحدة</th><th>سعر الوحدة $</th><th>الإجمالي $</th></tr></thead><tbody>
${lines.map((line,index)=>`<tr><td>${index+1}</td><td class="right"><b>${esc(line.description)}</b>${line.note ? `<span class="line-note">ملاحظة السعر: ${esc(line.note)}</span>` : ""}</td><td>${qty(line.quantity)}</td><td>${esc(line.unit)}</td><td>${line.rate || line.rate === 0 ? money(line.rate) : "—"}</td><td><b>${money(line.amount)}</b></td></tr>`).join("")}
</tbody></table>
<div class="total-box"><span>الإجمالي النهائي</span><span class="amount">$ ${money(total)}</span></div>
${frm.doc.order_notes ? `<div class="notes"><b>ملاحظات:</b> ${esc(frm.doc.order_notes)}</div>` : ""}
<div class="footer"><span>رقم الطلب: ${esc(frm.doc.name || "مسودة")}</span><span>تاريخ الطباعة: ${esc(generated)}</span></div>
</body></html>`;
    }

    function printInvoice(frm) {
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
        setTimeout(cleanup, 120000);
    }

    function sourcePiece(frm, rowName) {
        return (frm.doc.pieces || []).find(row => row.name === rowName) || null;
    }

    function approveSpecialPrice(frm, rowName) {
        const row = sourcePiece(frm, rowName);
        if (!row) return;
        frappe.prompt(
            [
                {
                    fieldname: "unit_price_usd",
                    fieldtype: "Currency",
                    label: "السعر الشامل للدرفة الواحدة ($)",
                    reqd: 1,
                    non_negative: 1,
                    default: row.special_shape_price_status === "Approved"
                        ? n(row.special_shape_custom_unit_price_usd)
                        : n(row.special_shape_estimated_unit_price_usd),
                },
                {
                    fieldname: "note",
                    fieldtype: "Small Text",
                    label: "ملاحظة التسعير (اختياري)",
                    default: row.special_shape_price_note || "",
                    description: "إذا كتبت ملاحظة فستظهر مع الدرفة في تفاصيل الفاتورة.",
                },
            ],
            values => {
                frappe.call({
                    method: "almdina_erp.almdina_erp.services.special_shape_service.approve_special_piece_price",
                    args: {
                        order_name: frm.doc.name,
                        piece_name: row.name,
                        unit_price_usd: values.unit_price_usd,
                        note: values.note || "",
                    },
                    freeze: true,
                    freeze_message: "جاري اعتماد سعر الدرفة الخاصة...",
                    callback(response) {
                        if (!response.exc) {
                            frappe.show_alert({ message: "تم اعتماد السعر الشامل وتحديث عرض الزبون.", indicator: "green" }, 5);
                            frm.reload_doc();
                        }
                    },
                });
            },
            `تسعير الدرفة الخاصة رقم ${row.idx || row.piece_no || ""}`,
            row.special_shape_price_status === "Approved" ? "تحديث السعر" : "اعتماد السعر"
        );
    }

    function bindCostActions(frm, wrapper) {
        wrapper.find(".dco-print-customer-invoice").on("click", () => printInvoice(frm));
        wrapper.find(".dco-view-special-sketch").on("click", function () {
            const card = this.closest("[data-special-row]");
            const row = sourcePiece(frm, card && card.dataset.specialRow);
            if (!row) {
                frappe.msgprint("تعذر العثور على سطر الدرفة الخاصة. أعد تحميل الطلب ثم حاول مرة أخرى.");
                return;
            }
            if (!window.AlmdinaSpecialShapeEditor || !window.AlmdinaSpecialShapeEditor.view) {
                frappe.msgprint("تعذر تحميل عارض الرسم. حدّث الصفحة تحديثًا إجباريًا ثم حاول مرة أخرى.");
                return;
            }
            window.AlmdinaSpecialShapeEditor.view(frm, row);
        });
        wrapper.find(".dco-approve-special-price").on("click", function () {
            const card = this.closest("[data-special-row]");
            if (card) approveSpecialPrice(frm, card.dataset.specialRow);
        });
    }

    function render(frm) {
        installStyles();
        frm.set_df_property("cost_tab", "label", "تكلفة الطلب");
        const field = frm.fields_dict.order_cost_invoice_html;
        if (!field || !field.$wrapper) return;
        field.$wrapper.html(buildScreenHtml(frm));
        bindCostActions(frm, field.$wrapper);
    }

    function scheduleRender(frm) {
        loadEdgeColors(frm).finally(() => requestAnimationFrame(() => render(frm)));
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { scheduleRender(frm); },
        refresh(frm) { scheduleRender(frm); },
        customer(frm) { scheduleRender(frm); },
        order_date(frm) { scheduleRender(frm); },
        board_description(frm) { scheduleRender(frm); },
        board_item(frm) { scheduleRender(frm); },
        board_rate_usd(frm) { scheduleRender(frm); },
        cutting_cost_per_board_usd(frm) { scheduleRender(frm); },
        required_boards(frm) { scheduleRender(frm); },
        edge_color(frm) { scheduleRender(frm); },
        edge_cost_usd(frm) { scheduleRender(frm); },
        total_cost_usd(frm) { scheduleRender(frm); },
        customer_quote_total_usd(frm) { scheduleRender(frm); },
        default_edge_type(frm) { scheduleRender(frm); },
        pieces_add(frm) { scheduleRender(frm); },
        pieces_remove(frm) { scheduleRender(frm); },
    });

    frappe.ui.form.on("Door Cutting Order Detail", {
        width_cm(frm) { scheduleRender(frm); },
        length_cm(frm) { scheduleRender(frm); },
        qty(frm) { scheduleRender(frm); },
        edge_type(frm) { scheduleRender(frm); },
        edge_rate_usd(frm) { scheduleRender(frm); },
        edge_cost_usd(frm) { scheduleRender(frm); },
        area_m2(frm) { scheduleRender(frm); },
        piece_type(frm) { scheduleRender(frm); },
    });

    window.AlmdinaOrderCostUX = {
        render: scheduleRender,
        printInvoice,
        invoiceLines,
        invoiceTotal,
        quoteTotal,
    };
})();
