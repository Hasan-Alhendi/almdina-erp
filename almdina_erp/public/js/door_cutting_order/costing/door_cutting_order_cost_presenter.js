(() => {
    "use strict";

    if (window.AlmdinaOrderCostUX) return;

    const STYLE_ID = "dco-capability-cost-presenter-css-v6";

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
        if (value === "Extra") return "إضافية";
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
            clippedEdgePrice: number(source.clipped_corner_edge_price_usd),
            clippedEdgeStatus: source.clipped_corner_edge_price_status || "Unpriced",
            clippedEdgeNote: source.clipped_corner_edge_price_note || "",
            clippedPosition: source.clipped_corner_position || "",
            clippedWidth: number(source.clipped_corner_width_cm),
            clippedLength: number(source.clipped_corner_length_cm),
            extraAddons: [
                {
                    selected: Boolean(number(source.extra_double)),
                    label: "Double",
                    rate: number(source.extra_double_unit_price_usd),
                    amount: number(source.extra_double_total_usd),
                },
                {
                    selected: Boolean(number(source.extra_liner)),
                    label: "Liner",
                    rate: number(source.extra_liner_unit_price_usd),
                    amount: number(source.extra_liner_total_usd),
                },
                {
                    selected: Boolean(number(source.extra_recessed_handle_cutout)),
                    label: "تفريغ مسكة مخفية",
                    rate: number(source.extra_recessed_handle_cutout_unit_price_usd),
                    amount: number(source.extra_recessed_handle_cutout_total_usd),
                },
            ],
        }));
    }

    function specialPriceReady(row) {
        return row.priceStatus === "Approved" && row.approvedUnit > 0;
    }

    function cutCornerPriceReady(row) {
        return row.clippedEdgeStatus === "Priced" && row.clippedEdgePrice > 0;
    }

    function invoiceLines(frm) {
        const result = [];
        const allRows = rows(frm);
        const customDoorRows = allRows.filter(row =>
            row.pieceType === "Special" || row.pieceType === "Clipped Corner"
        );
        const regularRows = customDoorRows.length
            ? allRows.filter(row => row.pieceType !== "Special" && row.pieceType !== "Clipped Corner")
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

        if (!edgeGroups.size && !customDoorRows.length && number(frm.doc.edge_cost_usd) > 0) {
            result.push({
                type: "edge",
                description: "القشاط",
                quantity: number(frm.doc.total_edge_meters),
                unit: "متر",
                rate: 0,
                amount: number(frm.doc.edge_cost_usd),
            });
        }

        allRows.forEach(row => {
            if (row.pieceType === "Special") {
                const ready = specialPriceReady(row);
                result.push({
                    type: "special",
                    description: `درفة خاصة رقم ${row.index}`,
                    quantity: row.qty,
                    unit: "درفة",
                    rate: ready ? row.approvedUnit : null,
                    amount: ready ? row.approvedUnit * row.qty : 0,
                    pending: !ready,
                    note: ready ? row.priceNote : "بانتظار إدخال السعر الخاص الشامل",
                });
                return;
            }
            if (row.pieceType === "Clipped Corner") {
                const ready = cutCornerPriceReady(row);
                result.push({
                    type: "cut_corner",
                    description: `درفة زاوية مقصوصة ${row.index}`,
                    quantity: row.qty,
                    unit: "درفة",
                    rate: ready ? row.clippedEdgePrice : null,
                    amount: ready ? row.clippedEdgePrice * row.qty : 0,
                    pending: !ready,
                    note: ready ? row.clippedEdgeNote : "بانتظار إدخال سعر معالجة قشاط الزاوية المقصوصة",
                });
                return;
            }
            if (row.pieceType === "Extra") {
                row.extraAddons
                    .filter(addon => addon.selected || addon.amount > 0)
                    .forEach(addon => result.push({
                        type: "extra_addon",
                        description: `إضافة ${addon.label} — درفة رقم ${row.index}`,
                        quantity: row.qty,
                        unit: "درفة",
                        rate: addon.rate,
                        amount: addon.amount || addon.rate * row.qty,
                        note: row.notes,
                    }));
            }
        });

        return result;
    }

    function pendingCustomEdgePriceLabels(frm) {
        return rows(frm).flatMap(row => {
            if (row.pieceType === "Special" && !specialPriceReady(row)) {
                return [`درفة خاصة رقم ${row.index}`];
            }
            if (row.pieceType === "Clipped Corner" && !cutCornerPriceReady(row)) {
                return [`درفة زاوية مقصوصة ${row.index}`];
            }
            return [];
        });
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
            .dco-cost-actions-bar{display:flex;justify-content:flex-start;margin:0 0 12px;min-height:32px}
            .dco-cost-actions{display:flex;gap:8px;flex-wrap:wrap}
            .dco-cost-actions .btn{border-radius:9px;font-weight:800}
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
            .dco-invoice-pending-row td{background:rgba(190,125,25,.055)}
            .dco-invoice-pending-badge{display:inline-flex;margin-inline-start:7px;padding:2px 7px;border-radius:999px;background:#fff3d8;color:#875812;font-size:9px;font-weight:900}
            .dco-invoice-pending-value{font-weight:900;color:#9a6a1d}
            .dco-special-price-list{display:grid;gap:9px;padding:12px}
            .dco-special-price-card{display:grid;grid-template-columns:minmax(150px,.9fr) minmax(160px,1fr) minmax(140px,.85fr) auto;align-items:center;gap:10px;padding:12px;border:1px solid var(--border-color,#e0e5e9);border-radius:13px;background:var(--card-bg,#fff)}
            .dco-special-price-id{font-size:14px;font-weight:900;letter-spacing:.02em}
            .dco-special-price-id small{display:block;margin-top:3px;font-size:10px;font-weight:700;color:var(--text-muted,#687481);letter-spacing:0}
            .dco-special-price-cell{padding:8px 9px;border-radius:10px;background:var(--subtle-fg,#f7f9fa)}
            .dco-special-price-cell span{display:block;font-size:9px;color:var(--text-muted,#687481);margin-bottom:3px}
            .dco-special-price-cell b{display:block;direction:ltr;text-align:right}
            .dco-special-price-cell.is-unpriced b{color:var(--text-muted,#8a939c);font-weight:800}
            .dco-inline-price-input{
                width:100%;max-width:140px;box-sizing:border-box;padding:6px 8px;border:1px solid var(--border-color,#d0d7de);
                border-radius:8px;background:#fff;font-size:13px;font-weight:800;direction:ltr;text-align:right;
            }
            .dco-inline-price-input:disabled,.dco-inline-price-input[readonly]{
                background:transparent;border-color:transparent;color:inherit;padding-inline:0;cursor:default;
            }
            .dco-inline-price-input:not(:disabled):not([readonly]):focus{
                outline:2px solid var(--primary,#2490ef);outline-offset:1px;
            }
            .dco-special-price-actions{display:flex;flex-direction:column;gap:6px;min-width:118px}
            .dco-special-price-note{grid-column:1/-1;font-size:10px;color:var(--text-muted,#687481)}
            .dco-invoice-total-card{margin:0;padding:18px 20px;border:1px solid rgba(31,130,82,.35);border-radius:0;border-top:0;background:linear-gradient(135deg,rgba(31,130,82,.12),rgba(31,130,82,.045));display:flex;align-items:center;justify-content:space-between;gap:16px}
            .dco-invoice-total-card.is-pending{border-color:rgba(190,125,25,.4);background:linear-gradient(135deg,rgba(190,125,25,.11),rgba(190,125,25,.035))}
            .dco-invoice-total-card span{display:block;font-size:13px;font-weight:800;color:#1f8252}
            .dco-invoice-total-card.is-pending span{color:#875812}
            .dco-invoice-total-card small{display:block;margin-top:4px;font-size:10px;color:var(--text-muted,#687481);font-weight:700}
            .dco-invoice-total-card b{display:block;font-size:28px;font-weight:900;direction:ltr;text-align:left;color:#14653d;letter-spacing:.01em}
            .dco-invoice-total-card.is-pending b{color:#875812}
            .dco-cost-empty{padding:24px;text-align:center;color:var(--text-muted,#687481)}
            .dco-cost-plan-stale-notice{margin:0;padding:10px 14px;border-bottom:1px solid rgba(190,125,25,.28);background:rgba(190,125,25,.08);color:#875812;font-size:11px;font-weight:800;line-height:1.55}
            @media(max-width:900px){.dco-special-price-card{grid-template-columns:1fr 1fr}.dco-special-price-actions,.dco-special-price-card>.dco-special-price-id,.dco-special-price-note{grid-column:1/-1}}
            @media(max-width:560px){.dco-cost-actions .btn{width:100%}.dco-special-price-card{grid-template-columns:1fr}.dco-invoice-total-card{flex-direction:column;align-items:flex-start}.dco-invoice-total-card b{font-size:24px}}
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

    function planNeedsRecalculation(frm) {
        return Number(frm.doc.plan_needs_recalculation || 0) === 1;
    }

    function stalePlanNoticeHtml(frm) {
        if (!planNeedsRecalculation(frm)) return "";
        return `<div class="dco-cost-plan-stale-notice" role="status">
            ${__("عدد الألواح وأجور القص مبنية على آخر خطة محسوبة. احسب خطة القص لتحديث الفاتورة بالقيم النهائية.")}
        </div>`;
    }

    function invoiceRowsHtml(frm) {
        const lines = effectiveInvoiceLines(frm);
        if (!lines.length) {
            return '<div class="dco-cost-empty">احفظ الطلب واحسب خطة القص لتظهر تفاصيل السعر.</div>';
        }
        return `${stalePlanNoticeHtml(frm)}<div class="dco-cost-table-wrap"><table class="dco-cost-table"><thead><tr>
            <th>#</th><th class="text-start">البيان</th><th>الكمية</th><th>الوحدة</th><th>سعر الوحدة ($)</th><th>الإجمالي ($)</th>
        </tr></thead><tbody>${lines.map((line, index) => `<tr class="${line.pending ? "dco-invoice-pending-row" : ""}">
            <td>${index + 1}</td><td class="text-start"><b>${esc(line.description)}</b>${line.pending ? `<span class="dco-invoice-pending-badge">${__("غير مسعّر")}</span>` : ""}${line.note ? `<small style="display:block">${esc(line.note)}</small>` : ""}</td>
            <td>${quantity(line.quantity)}</td><td>${esc(line.unit)}</td>
            <td class="${line.pending ? "dco-invoice-pending-value" : ""}">${line.pending ? "—" : money(line.rate)}</td>
            <td class="${line.pending ? "dco-invoice-pending-value" : ""}">${line.pending ? "—" : `<b>${money(line.amount)}</b>`}</td>
        </tr>`).join("")}</tbody></table></div>`;
    }

    function invoiceTotalCardHtml(frm) {
        const total = quoteTotal(frm);
        const pending = pendingCustomEdgePriceLabels(frm);
        const finalLabel = __("الإجمالي النهائي للفاتورة");
        if (!pending.length) {
            return `<div class="dco-invoice-total-card">
                <span>${finalLabel}</span>
                <b>$ ${money(total)}</b>
            </div>`;
        }
        return `<div class="dco-invoice-total-card is-pending">
            <span>${__("الإجمالي الحالي قبل الأسعار غير المسعرة")}<small>${__("لا يعتبر إجماليًا نهائيًا حتى تسعير: {0}").replace("{0}", pending.join("، "))}</small></span>
            <b>$ ${money(total)}</b>
        </div>`;
    }

    function specialDoorLabel(row) {
        return `درفة خاصة رقم ${row.index}`;
    }

    function cutCornerDoorLabel(row) {
        return `درفة زاوية مقصوصة ${row.index}`;
    }

    function specialPriceInputValue(row) {
        if (specialPriceReady(row)) return number(row.approvedUnit);
        return number(row.estimatedUnit);
    }

    function cutCornerPriceInputValue(row) {
        return number(row.clippedEdgePrice);
    }

    function specialPricingHtml(frm) {
        const specialRows = rows(frm).filter(row => row.pieceType === "Special");
        if (!specialRows.length) return "";
        return `<div class="dco-cost-section"><div class="dco-cost-section-title">
            <h4>تسعير الدرفات الخاصة</h4><span>أدخل السعر الخاص الشامل لكل درفة أثناء وضع التعديل</span>
        </div><div class="dco-special-price-list">${specialRows.map(row => {
            const doorLabel = specialDoorLabel(row);
            const priced = specialPriceReady(row);
            const documented = row.drawingStatus === "Documented"
                || Boolean(String(row.source.special_shape_geometry_json || "").trim())
                || Boolean(String(row.source.special_shape_drawing_json || "").trim());
            const priceValue = specialPriceInputValue(row);
            return `<div class="dco-special-price-card" data-special-row="${esc(row.name)}" data-custom-id="${esc(doorLabel)}">
                <div class="dco-special-price-id">${esc(doorLabel)}<small>${quantity(row.length)} × ${quantity(row.width)} سم — عدد ${row.qty}</small></div>
                <div class="dco-special-price-cell"><span>${__("الطول × العرض")}</span><b>${quantity(row.length)} × ${quantity(row.width)} سم</b></div>
                <div class="dco-special-price-cell ${priced ? "" : "is-unpriced"}">
                    <span>${__("السعر الخاص الشامل ($)")}</span>
                    <input type="number" class="dco-inline-price-input" data-price-kind="special" data-piece-name="${esc(row.name)}" min="0" step="0.01" value="${priceValue || ""}" disabled readonly inputmode="decimal">
                    ${priced ? "" : `<small style="display:block;margin-top:4px;color:var(--text-muted,#8a939c)">${__("غير مسعّر")}</small>`}
                </div>
                <div class="dco-special-price-actions"><button type="button" class="btn btn-default btn-xs dco-view-special-sketch" ${documented ? "" : "disabled"}>${__("عرض التوثيق")}</button></div>
                ${row.priceNote ? `<div class="dco-special-price-note">${esc(row.priceNote)}</div>` : ""}
            </div>`;
        }).join("")}</div></div>`;
    }

    function cutCornerPricingHtml(frm) {
        const cutRows = rows(frm).filter(row => row.pieceType === "Clipped Corner");
        if (!cutRows.length) return "";
        return `<div class="dco-cost-section"><div class="dco-cost-section-title">
            <h4>تسعير قشاط درف الزاوية المقصوصة</h4><span>عدّل سعر القشاط مباشرة في الحقل أثناء وضع التعديل</span>
        </div><div class="dco-special-price-list">${cutRows.map(row => {
            const doorLabel = cutCornerDoorLabel(row);
            const priced = cutCornerPriceReady(row);
            const hasDrawing = Boolean(row.clippedPosition)
                && number(row.clippedWidth) > 0
                && number(row.clippedLength) > 0;
            const priceValue = cutCornerPriceInputValue(row);
            return `<div class="dco-special-price-card" data-cut-corner-row="${esc(row.name)}" data-custom-id="${esc(doorLabel)}">
                <div class="dco-special-price-id">${esc(doorLabel)}<small>${quantity(row.length)} × ${quantity(row.width)} سم — عدد ${row.qty}</small></div>
                <div class="dco-special-price-cell"><span>${__("الطول × العرض")}</span><b>${quantity(row.length)} × ${quantity(row.width)} سم</b></div>
                <div class="dco-special-price-cell ${priced ? "" : "is-unpriced"}">
                    <span>${__("سعر القشاط ($)")}</span>
                    <input type="number" class="dco-inline-price-input" data-price-kind="clipped" data-piece-name="${esc(row.name)}" min="0" step="0.01" value="${priceValue || ""}" disabled readonly inputmode="decimal">
                    ${priced ? "" : `<small style="display:block;margin-top:4px;color:var(--text-muted,#8a939c)">${__("غير مسعّر")}</small>`}
                </div>
                <div class="dco-special-price-actions"><button type="button" class="btn btn-default btn-xs dco-view-cut-corner-sketch" ${hasDrawing ? "" : "disabled"}>${__("عرض الرسم")}</button></div>
                ${row.clippedEdgeNote ? `<div class="dco-special-price-note">${esc(row.clippedEdgeNote)}</div>` : ""}
            </div>`;
        }).join("")}</div></div>`;
    }

    function bindViewDrawing(frm, wrapper) {
        wrapper.find(".dco-view-special-sketch").on("click", function onViewDrawing() {
            const card = this.closest("[data-special-row]");
            const source = (frm.doc.pieces || []).find(row => row.name === (card && card.dataset.specialRow));
            if (!source || !window.AlmdinaSpecialShapeEditor || typeof window.AlmdinaSpecialShapeEditor.view !== "function") {
                frappe.msgprint(__("تعذر تحميل توثيق الدرفة الخاصة."));
                return;
            }
            window.AlmdinaSpecialShapeEditor.view(frm, source);
        });
        wrapper.find(".dco-view-cut-corner-sketch").on("click", function onViewCutCorner() {
            const card = this.closest("[data-cut-corner-row]");
            const source = (frm.doc.pieces || []).find(row => row.name === (card && card.dataset.cutCornerRow));
            if (!source || !window.AlmdinaClippedCornerEditor || typeof window.AlmdinaClippedCornerEditor.view !== "function") {
                frappe.msgprint(__("تعذر تحميل رسم الزاوية المقصوصة."));
                return;
            }
            window.AlmdinaClippedCornerEditor.view(frm, source);
        });
    }

    function render(frm) {
        const field = frm.fields_dict.order_cost_invoice_html;
        if (!field || !field.$wrapper) return false;

        const canView = can(frm, "view_costs");
        const canPrint = can(frm, "print_customer_invoice");
        if (!canView && !canPrint) {
            field.$wrapper.empty();
            return false;
        }

        installStyles();
        const actionShell = '<div class="dco-cost-actions-bar"><div class="dco-cost-actions"></div></div>';
        if (!canView) {
            field.$wrapper.html(`<div class="dco-cost-shell">${actionShell}</div>`);
            return true;
        }

        field.$wrapper.html(`<div class="dco-cost-shell">
            ${actionShell}
            <div class="dco-cost-section"><div class="dco-cost-section-title"><h4>جدول قياسات الطلب</h4><span>القياسات والكميات والملاحظات</span></div>${measurementRowsHtml(frm)}</div>
            ${specialPricingHtml(frm)}
            ${cutCornerPricingHtml(frm)}
            <div class="dco-cost-section dco-cost-invoice-section"><div class="dco-cost-section-title"><h4>تفاصيل عرض السعر</h4><span>الألواح والقص والقشاط والدرف الخاصة وإضافات Extra</span></div>${invoiceRowsHtml(frm)}${invoiceTotalCardHtml(frm)}</div>
        </div>`);
        bindViewDrawing(frm, field.$wrapper);
        return true;
    }

    function refreshInvoiceSection(frm) {
        const field = frm.fields_dict.order_cost_invoice_html;
        if (!field || !field.$wrapper) return false;
        const section = field.$wrapper.find(".dco-cost-invoice-section");
        if (!section.length) return render(frm);
        section.html(
            `<div class="dco-cost-section-title"><h4>تفاصيل عرض السعر</h4><span>الألواح والقص والقشاط والدرف الخاصة وإضافات Extra</span></div>${invoiceRowsHtml(frm)}${invoiceTotalCardHtml(frm)}`
        );
        return true;
    }

    window.AlmdinaOrderCostUX = Object.freeze({
        render,
        refreshInvoiceSection,
        invoiceLines,
        invoiceTotal,
        quoteTotal,
        pendingCustomEdgePriceLabels,
    });
})();
