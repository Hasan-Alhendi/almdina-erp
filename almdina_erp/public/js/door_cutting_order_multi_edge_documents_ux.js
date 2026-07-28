(() => {
    "use strict";

    const STYLE_ID = "dco-side-edge-documents-css";
    let activeFrm = null;

    function api() {
        return window.AlmdinaMultiEdgeBanding || null;
    }

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function num(value) {
        const result = Number(value || 0);
        return Number.isFinite(result) ? result : 0;
    }

    function money(value) {
        return num(value).toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    function quantity(value) {
        return num(value).toLocaleString("en-US", { maximumFractionDigits: 3 });
    }

    function rows(frm) {
        const module = api();
        return (frm.doc.pieces || []).map((row, index) => ({
            source: row,
            index: index + 1,
            piece_type: row.piece_type || "Regular",
            width_cm: num(row.width_cm),
            length_cm: num(row.length_cm),
            qty: Math.max(1, Math.trunc(num(row.qty) || 1)),
            notes: row.notes || "",
            details: module ? module.details(frm, row) : [],
        }));
    }

    function pieceTypeLabel(value) {
        if (value === "Special") return "خاصة";
        if (value === "Clipped Corner") return "زاوية مقصوصة";
        return "عادية";
    }

    function modeLabel(detail) {
        return detail.custom ? "مخصص" : "افتراضي";
    }

    function edgeDetailsHtml(details, { prices = false } = {}) {
        if (!details.length) return '<span class="dco-edge-none">بدون قشاط</span>';
        return `<div class="dco-edge-detail-list">${details.map(detail => `
            <div class="dco-edge-detail-badge ${detail.custom ? "is-custom" : ""}">
                <b>${esc(detail.side_label)} <em>${esc(modeLabel(detail))}</em></b>
                <span>${esc(detail.edge_type || "غير محدد")}${prices ? ` · ${quantity(detail.meters)} م · $ ${money(detail.rate)}/م` : ""}</span>
            </div>`).join("")}</div>`;
    }

    function edgeInvoiceLines(frm) {
        const data = rows(frm);
        const hasSpecial = data.some(row => row.piece_type === "Special");
        const sourceRows = hasSpecial
            ? data.filter(row => row.piece_type !== "Special")
            : data;
        const groups = new Map();

        sourceRows.forEach(row => {
            row.details.forEach(detail => {
                if (!detail.meters) return;
                const key = `${detail.edge_type}::${detail.rate}::${detail.thickness_mm}`;
                if (!groups.has(key)) {
                    groups.set(key, {
                        type: "edge",
                        description: `قشاط — ${detail.edge_type || "غير محدد"}`,
                        quantity: 0,
                        unit: "متر",
                        rate: detail.rate,
                        amount: 0,
                        thickness: detail.thickness_mm,
                        sides: new Set(),
                        hasCustom: false,
                    });
                }
                const group = groups.get(key);
                group.quantity += num(detail.meters);
                group.amount += num(detail.amount);
                group.sides.add(detail.side_label);
                group.hasCustom = group.hasCustom || Boolean(detail.custom);
            });
        });

        return [...groups.values()].map(group => ({
            type: group.type,
            description: group.description,
            quantity: Math.round(group.quantity * 1000) / 1000,
            unit: group.unit,
            rate: group.rate,
            amount: Math.round(group.amount * 1000) / 1000,
            note: `السماكة ${quantity(group.thickness)} مم — ${group.hasCustom ? "يتضمن أطرافًا مخصصة" : "من القشاط الافتراضي"} — ${[...group.sides].join("، ")}`,
        }));
    }

    function invoiceLines(frm) {
        const originalApi = window.AlmdinaOrderCostUX;
        const original = originalApi && originalApi.invoiceLines
            ? originalApi.invoiceLines(frm)
            : [];
        const nonEdge = original.filter(line => line.type !== "edge");
        const detailedEdges = edgeInvoiceLines(frm);
        const firstSpecial = nonEdge.findIndex(line => line.type === "special");
        if (firstSpecial < 0) return [...nonEdge, ...detailedEdges];
        return [
            ...nonEdge.slice(0, firstSpecial),
            ...detailedEdges,
            ...nonEdge.slice(firstSpecial),
        ];
    }

    function invoiceTotal(frm) {
        return invoiceLines(frm).reduce((sum, line) => sum + num(line.amount), 0);
    }

    function invoiceRowsHtml(frm) {
        const lines = invoiceLines(frm);
        if (!lines.length) return '<tr><td colspan="6">احفظ الطلب واحسب خطة القص لتظهر تفاصيل الفاتورة.</td></tr>';
        return lines.map((line, index) => `
            <tr>
                <td>${index + 1}</td>
                <td class="text-start"><b>${esc(line.description)}</b>${line.note ? `<span class="dco-invoice-line-note">${esc(line.note)}</span>` : ""}</td>
                <td>${quantity(line.quantity)}</td>
                <td>${esc(line.unit)}</td>
                <td>${line.rate || line.rate === 0 ? money(line.rate) : "—"}</td>
                <td><b>${money(line.amount)}</b></td>
            </tr>`).join("");
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-edge-none{color:var(--text-muted,#6c7680);font-size:10px}
            .dco-edge-detail-list{display:grid;gap:4px;min-width:170px}
            .dco-edge-detail-badge{display:grid;gap:2px;padding:5px 7px;border:1px solid var(--border-color,#e1e5e9);border-radius:8px;background:var(--subtle-fg,#f8f9fa);text-align:right;line-height:1.25}
            .dco-edge-detail-badge.is-custom{border-color:#ddb94a;background:#fff9e8}
            .dco-edge-detail-badge b{display:flex;align-items:center;justify-content:space-between;gap:6px;font-size:10px}
            .dco-edge-detail-badge b em{font-style:normal;font-size:8px;color:var(--text-muted,#66717e);font-weight:800}
            .dco-edge-detail-badge.is-custom b em{color:#8b6400}
            .dco-edge-detail-badge span{font-size:9px;color:var(--text-muted,#66717e);word-break:break-word}
            .dco-cost-table .dco-edge-detail-cell{min-width:210px;white-space:normal}
            .dco-edge-pricing-note{display:inline-flex;align-items:center;gap:5px;padding:4px 8px;border-radius:999px;background:rgba(31,130,82,.08);color:#17643f;font-weight:800}
        `;
        document.head.appendChild(style);
    }

    function findSection(wrapper, title) {
        return [...wrapper.querySelectorAll(".dco-cost-section")].find(section => {
            const heading = section.querySelector(".dco-cost-section-title h4");
            return heading && heading.textContent.trim() === title;
        }) || null;
    }

    function patchMeasurements(frm, wrapper) {
        const section = findSection(wrapper, "جدول قياسات الطلب");
        const table = section && section.querySelector("table.dco-cost-table");
        if (!table) return;
        const headerCells = table.querySelectorAll("thead th");
        if (headerCells[5]) headerCells[5].textContent = "قشاط الأطراف";
        const data = rows(frm);
        table.querySelectorAll("tbody tr").forEach((tr, index) => {
            const cells = tr.querySelectorAll(":scope > td");
            if (!cells[5] || !data[index]) return;
            cells[5].classList.add("dco-edge-detail-cell");
            cells[5].innerHTML = edgeDetailsHtml(data[index].details);
        });
        const subtitle = section.querySelector(".dco-cost-section-title span");
        if (subtitle) subtitle.textContent = "كل ضلع يعرض نوعه الفعلي، مع تمييز التخصيص عن الافتراضي";
    }

    function patchInvoice(frm, wrapper) {
        const section = findSection(wrapper, "تفاصيل الفاتورة");
        const tbody = section && section.querySelector("table.dco-cost-table tbody");
        if (!tbody) return;
        const signature = JSON.stringify(invoiceLines(frm));
        if (tbody.dataset.sideEdgeInvoiceSignature !== signature) {
            tbody.dataset.sideEdgeInvoiceSignature = signature;
            tbody.innerHTML = invoiceRowsHtml(frm);
        }
        const subtitle = section.querySelector(".dco-cost-section-title span");
        if (subtitle) {
            subtitle.innerHTML = '<span class="dco-edge-pricing-note">سطر مستقل لكل نوع قشاط وسعره، حتى لو خُصص لضلع واحد</span>';
        }
        const total = invoiceTotal(frm);
        const amount = section.querySelector(".dco-grand-total .amount");
        if (amount) amount.textContent = `$ ${money(total)}`;
    }

    function patchCostScreen(frm) {
        installStyles();
        const field = frm.fields_dict.order_cost_invoice_html;
        const wrapper = field && field.$wrapper && field.$wrapper.get(0);
        if (!wrapper) return;
        patchMeasurements(frm, wrapper);
        patchInvoice(frm, wrapper);
        if (!wrapper._dcoSideEdgeDocumentsObserver) {
            let queued = false;
            const observer = new MutationObserver(() => {
                if (queued) return;
                queued = true;
                requestAnimationFrame(() => {
                    queued = false;
                    patchMeasurements(frm, wrapper);
                    patchInvoice(frm, wrapper);
                });
            });
            observer.observe(wrapper, { childList: true, subtree: true });
            wrapper._dcoSideEdgeDocumentsObserver = observer;
        }
    }

    function dimensionMark(value, count) {
        const safeCount = Math.max(0, Math.min(2, Number(count || 0)));
        const lines = Array.from({ length: safeCount }, () => '<span class="edge-line"></span>').join("");
        return `<span class="dimension"><b>${quantity(value)}</b><span class="edge-lines edge-lines-${safeCount}">${lines}</span></span>`;
    }

    function printRowsHtml(frm) {
        return rows(frm).map(row => {
            const longCount = Number(Boolean(row.source.edge_long_right)) + Number(Boolean(row.source.edge_long_left));
            const widthCount = Number(Boolean(row.source.edge_width_top)) + Number(Boolean(row.source.edge_width_bottom));
            return `<tr>
                <td>${row.index}</td>
                <td>${esc(pieceTypeLabel(row.piece_type))}</td>
                <td>${dimensionMark(row.width_cm, widthCount)}</td>
                <td>${dimensionMark(row.length_cm, longCount)}</td>
                <td>${row.qty}</td>
                <td class="right">${edgeDetailsHtml(row.details)}</td>
                <td class="right">${esc(row.notes || "—")}</td>
            </tr>`;
        }).join("");
    }

    function sharedPrintCss() {
        return `@page{size:A4 portrait;margin:11mm}*{box-sizing:border-box}body{font-family:Tahoma,Arial,sans-serif;color:#111;margin:0;font-size:10px;direction:rtl;-webkit-print-color-adjust:exact;print-color-adjust:exact}.header{display:flex;justify-content:space-between;border-bottom:2px solid #111;padding-bottom:8px;margin-bottom:9px}.header h1{font-size:21px;margin:0 0 4px}.muted{color:#666;font-size:8.5px}.info{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin:8px 0}.info>div{border:1px solid #aaa;border-radius:5px;padding:6px}.info b{display:block;font-size:8px;color:#555;margin-bottom:2px}.title{font-size:13px;font-weight:900;margin:11px 0 4px}.table{width:100%;border-collapse:collapse}.table th,.table td{border:1px solid #999;padding:4px;text-align:center;vertical-align:middle}.table th{background:#eee}.right{text-align:right!important;white-space:normal}.measurements{font-size:8.5px}.invoice{font-size:9.5px}.dco-edge-detail-list{display:grid;gap:2px}.dco-edge-detail-badge{display:grid;gap:1px;padding:2px 4px;border:1px solid #bbb;border-radius:3px;text-align:right}.dco-edge-detail-badge.is-custom{border-color:#b88b00;background:#fff8df}.dco-edge-detail-badge b{display:flex;justify-content:space-between;font-size:7.8px}.dco-edge-detail-badge b em{font-style:normal;font-size:6.5px}.dco-edge-detail-badge span{font-size:7px;color:#444}.dco-edge-none{color:#666}.dimension{display:inline-flex;min-width:36px;flex-direction:column;align-items:center;gap:1px}.edge-lines{display:flex;flex-direction:column;gap:1px;min-height:4px}.edge-line{display:block;width:26px;height:1px;background:#111}.edge-lines-0{visibility:hidden}.line-note{display:block;color:#555;font-size:7.5px;margin-top:2px}.total{margin-top:8px;margin-right:auto;width:43%;border:2px solid #111;padding:8px;display:flex;justify-content:space-between;font-size:14px;font-weight:900}.footer{margin-top:10px;border-top:1px solid #aaa;padding-top:5px;display:flex;justify-content:space-between;color:#666;font-size:8px}`;
    }

    function printInvoiceHtml(frm) {
        const lines = invoiceLines(frm);
        const total = invoiceTotal(frm);
        const generated = frappe.datetime ? frappe.datetime.now_datetime() : new Date().toISOString();
        return `<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8"><title>فاتورة الطلب ${esc(frm.doc.name || "")}</title><style>${sharedPrintCss()}</style></head><body>
            <div class="header"><div><h1>عرض سعر الطلب</h1><div class="muted">القشاط الافتراضي مع توضيح أي تخصيص استثنائي لكل ضلع</div></div><div style="text-align:left"><b>${esc(frm.doc.name || "مسودة")}</b><div class="muted">${esc(frm.doc.order_date || "")}</div></div></div>
            <div class="info"><div><b>الزبون</b>${esc(frm.doc.customer || "—")}</div><div><b>صنف اللوح</b>${esc(frm.doc.board_description || frm.doc.board_item || "—")}</div><div><b>عدد الألواح</b>${quantity(frm.doc.required_boards)}</div><div><b>سعر اللوح</b>$ ${money(frm.doc.board_rate_usd)}</div><div><b>أجور القص / لوح</b>$ ${money(frm.doc.cutting_cost_per_board_usd)}</div><div><b>إجمالي القشاط</b>$ ${money(frm.doc.edge_cost_usd)}</div></div>
            <div class="title">جدول القياسات والقشاط</div>
            <table class="table measurements"><thead><tr><th>#</th><th>النوع</th><th>العرض</th><th>الطول</th><th>العدد</th><th>قشاط الأطراف</th><th>ملاحظات</th></tr></thead><tbody>${printRowsHtml(frm)}</tbody></table>
            <div class="title">تفاصيل الفاتورة</div>
            <table class="table invoice"><thead><tr><th>#</th><th class="right">البيان</th><th>الكمية</th><th>الوحدة</th><th>سعر الوحدة $</th><th>الإجمالي $</th></tr></thead><tbody>${lines.map((line,index)=>`<tr><td>${index+1}</td><td class="right"><b>${esc(line.description)}</b>${line.note ? `<span class="line-note">${esc(line.note)}</span>` : ""}</td><td>${quantity(line.quantity)}</td><td>${esc(line.unit)}</td><td>${line.rate || line.rate === 0 ? money(line.rate) : "—"}</td><td><b>${money(line.amount)}</b></td></tr>`).join("")}</tbody></table>
            <div class="total"><span>الإجمالي النهائي</span><span>$ ${money(total)}</span></div>
            ${frm.doc.order_notes ? `<div style="margin-top:8px;border:1px solid #aaa;padding:6px"><b>ملاحظات:</b> ${esc(frm.doc.order_notes)}</div>` : ""}
            <div class="footer"><span>رقم الطلب: ${esc(frm.doc.name || "مسودة")}</span><span>تاريخ الطباعة: ${esc(generated)}</span></div>
        </body></html>`;
    }

    function printMeasurementsHtml(frm) {
        const generated = frappe.datetime ? frappe.datetime.now_datetime() : new Date().toISOString();
        return `<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8"><title>قياسات الطلب ${esc(frm.doc.name || "")}</title><style>${sharedPrintCss()}</style></head><body>
            <div class="header"><div><h1>جدول قياسات الطلب</h1><div class="muted">نوع القشاط الفعلي لكل ضلع مع تمييز المخصص عن الافتراضي</div></div><div style="text-align:left"><b>${esc(frm.doc.name || "مسودة")}</b><div class="muted">${esc(frm.doc.order_date || "")}</div></div></div>
            <table class="table"><thead><tr><th>#</th><th>النوع</th><th>العرض</th><th>الطول</th><th>العدد</th><th>قشاط الأطراف</th><th>ملاحظات</th></tr></thead><tbody>${printRowsHtml(frm)}</tbody></table>
            ${frm.doc.order_notes ? `<div style="margin-top:8px;border:1px solid #aaa;padding:6px"><b>ملاحظات الطلب:</b> ${esc(frm.doc.order_notes)}</div>` : ""}
            <div class="footer"><span>رقم الطلب: ${esc(frm.doc.name || "مسودة")}</span><span>تاريخ الطباعة: ${esc(generated)}</span></div>
        </body></html>`;
    }

    function printHtml(html, frameId) {
        document.getElementById(frameId)?.remove();
        const frame = document.createElement("iframe");
        frame.id = frameId;
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
                console.error("Per-side edge print failed", error);
                cleanup();
                frappe.msgprint("تعذر تشغيل الطباعة. أعد تحميل الصفحة ثم حاول مرة أخرى.");
            }
        };
        frame.srcdoc = html;
        document.body.appendChild(frame);
        setTimeout(cleanup, 120000);
    }

    function bindPrintInterception() {
        if (document._dcoSideEdgePrintBound) return;
        document._dcoSideEdgePrintBound = true;
        document.addEventListener("click", event => {
            if (!activeFrm || !api()) return;
            const invoice = event.target.closest(".dco-print-customer-invoice");
            if (invoice) {
                event.preventDefault();
                event.stopImmediatePropagation();
                printHtml(printInvoiceHtml(activeFrm), "dco-side-edge-invoice-frame");
                return;
            }
            const measurements = event.target.closest(".dco-print-measurements");
            if (measurements) {
                event.preventDefault();
                event.stopImmediatePropagation();
                printHtml(printMeasurementsHtml(activeFrm), "dco-side-edge-measurements-frame");
            }
        }, true);
    }

    function schedule(frm) {
        activeFrm = frm;
        bindPrintInterception();
        requestAnimationFrame(() => patchCostScreen(frm));
        setTimeout(() => patchCostScreen(frm), 180);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
        edge_cost_usd(frm) { schedule(frm); },
        total_cost_usd(frm) { schedule(frm); },
        customer_quote_total_usd(frm) { schedule(frm); },
        pieces_add(frm) { schedule(frm); },
        pieces_remove(frm) { schedule(frm); },
    });

    frappe.ui.form.on("Door Cutting Order Detail", {
        edge_long_right_type_override(frm) { schedule(frm); },
        edge_long_left_type_override(frm) { schedule(frm); },
        edge_width_top_type_override(frm) { schedule(frm); },
        edge_width_bottom_type_override(frm) { schedule(frm); },
        edge_long_cost_usd(frm) { schedule(frm); },
        edge_width_cost_usd(frm) { schedule(frm); },
        edge_cost_usd(frm) { schedule(frm); },
        width_cm(frm) { schedule(frm); },
        length_cm(frm) { schedule(frm); },
        qty(frm) { schedule(frm); },
    });

    window.AlmdinaMultiEdgeDocuments = {
        edgeInvoiceLines,
        invoiceLines,
        invoiceTotal,
        patch: patchCostScreen,
        printInvoice(frm) { printHtml(printInvoiceHtml(frm), "dco-side-edge-invoice-frame"); },
        printMeasurements(frm) { printHtml(printMeasurementsHtml(frm), "dco-side-edge-measurements-frame"); },
    };
})();
