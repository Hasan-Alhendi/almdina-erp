(() => {
    "use strict";

    const STYLE_ID = "dco-side-edge-documents-css";

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
            details: module && typeof module.details === "function"
                ? module.details(frm, row)
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

    function customEdgeSummaryHtml(details) {
        const groups = customEdgeGroups(details);
        if (!groups.length) {
            return '<span class="dco-edge-default-note" title="لا يوجد تخصيص">—</span>';
        }
        const sideCount = groups.reduce((sum, group) => sum + group.sides.length, 0);
        return `<div class="dco-custom-edge-list">${groups.map(group => {
            const sides = sideCount === 4 && group.sides.length === 4
                ? "على الداير"
                : group.sides.join("، ");
            return `<span class="dco-custom-edge-chip">
                <span class="dco-custom-edge-sides">${esc(sides)}</span>
                <b>${esc(group.type)}</b>
                <em>مخصص</em>
            </span>`;
        }).join("")}</div>`;
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
        const original = originalApi && typeof originalApi.invoiceLines === "function"
            ? originalApi.invoiceLines(frm)
            : [];
        const nonEdge = original.filter(line => line.type !== "edge");
        const detailedEdges = edgeInvoiceLines(frm);
        const firstCustom = nonEdge.findIndex(line =>
            line.type === "special" || line.type === "cut_corner"
        );
        if (firstCustom < 0) return [...nonEdge, ...detailedEdges];
        return [
            ...nonEdge.slice(0, firstCustom),
            ...detailedEdges,
            ...nonEdge.slice(firstCustom),
        ];
    }

    function invoiceTotal(frm) {
        return invoiceLines(frm).reduce((sum, line) => sum + num(line.amount), 0);
    }

    function invoiceRowsHtml(frm) {
        const lines = invoiceLines(frm);
        if (!lines.length) {
            return '<tr><td colspan="6" class="dco-cost-empty-row">احفظ الطلب واحسب خطة القص لتظهر تفاصيل الفاتورة.</td></tr>';
        }
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
            .dco-cost-shell{max-width:1440px!important}
            .dco-cost-section{border-color:var(--border-color,#dfe4e8)!important;box-shadow:0 8px 24px rgba(23,32,51,.045)}
            .dco-cost-section-title{padding:15px 18px!important;background:linear-gradient(180deg,var(--subtle-fg,#fafbfc),var(--card-bg,#fff))!important}
            .dco-cost-section-title h4{font-size:15px!important;letter-spacing:-.1px}
            .dco-cost-section-title>span{max-width:66%;font-size:11px!important;line-height:1.55;text-align:left}
            .dco-cost-table-wrap{padding:12px;overflow:auto;background:var(--card-bg,#fff)}
            .dco-cost-table{min-width:820px!important;border-collapse:separate!important;border-spacing:0!important;border:1px solid var(--border-color,#dfe4e8);border-radius:13px;overflow:hidden;font-size:12.5px!important;background:var(--card-bg,#fff)}
            .dco-cost-table thead th{position:sticky;top:0;z-index:2;padding:11px 10px!important;background:var(--subtle-fg,#f5f7f9)!important;color:var(--text-color,#29333d);font-size:11px;letter-spacing:.05px;border-bottom:1px solid var(--border-color,#d8dee4)!important}
            .dco-cost-table tbody td{padding:11px 10px!important;border-bottom:1px solid var(--border-color,#e7ebef)!important;line-height:1.45}
            .dco-cost-table tbody tr:nth-child(even){background:rgba(107,119,132,.025)}
            .dco-cost-table tbody tr{transition:background-color .14s ease,box-shadow .14s ease}
            .dco-cost-table tbody tr:hover{background:rgba(36,115,77,.045);box-shadow:inset 3px 0 0 rgba(36,115,77,.45)}
            .dco-cost-table tbody tr:last-child td{border-bottom:0!important}
            .dco-cost-table td,.dco-cost-table th{font-variant-numeric:tabular-nums}
            .dco-cost-table .dco-row-index{display:inline-grid;place-items:center;min-width:27px;height:27px;padding:0 7px;border-radius:8px;background:var(--subtle-fg,#eef2f5);font-weight:900;color:var(--text-color,#26313b)}
            .dco-cost-table .dco-piece-type{display:inline-flex;align-items:center;justify-content:center;min-width:58px;padding:4px 9px;border-radius:999px;background:var(--subtle-fg,#eef2f5);font-size:10px;font-weight:900;color:var(--text-muted,#5e6a75)}
            .dco-cost-table .dco-piece-type.is-special{background:#fff3d8;color:#875812}
            .dco-cost-table .dco-dimension-value{font-size:13px;font-weight:900}
            .dco-cost-table .dco-dimension-edge-line{width:31px;height:1.4px}
            .dco-cost-table .dco-edge-detail-cell{width:30%;min-width:250px;white-space:normal}
            .dco-edge-default-note{color:var(--text-muted,#7a858f);font-size:16px;line-height:1}
            .dco-custom-edge-list{display:grid;gap:6px}
            .dco-custom-edge-chip{display:grid;grid-template-columns:minmax(90px,.85fr) minmax(120px,1.25fr) auto;align-items:center;gap:8px;padding:7px 9px;border:1px solid #dfbd55;border-radius:10px;background:linear-gradient(135deg,#fffdf4,#fff7da);text-align:right;box-shadow:0 2px 7px rgba(139,100,0,.055)}
            .dco-custom-edge-sides{font-size:10px;font-weight:800;color:#5e6266;line-height:1.35}
            .dco-custom-edge-chip b{font-size:11px;font-weight:900;line-height:1.35;overflow-wrap:anywhere}
            .dco-custom-edge-chip em{padding:3px 7px;border:1px solid currentColor;border-radius:999px;color:#805b00;font-size:8px;font-style:normal;font-weight:900;white-space:nowrap}
            .dco-cost-table .dco-notes-col{width:27%!important;min-width:220px!important;line-height:1.6!important;color:var(--text-color,#313b45)}
            .dco-cost-table .dco-notes-col.is-empty{color:var(--text-muted,#8b949d);text-align:center!important}
            .dco-cost-table--invoice td:nth-last-child(-n+2){direction:ltr;font-weight:800}
            .dco-cost-empty-row{padding:26px!important;color:var(--text-muted,#6b7680);text-align:center!important}
            .dco-edge-pricing-note{display:inline-flex;align-items:center;gap:5px;padding:5px 9px;border-radius:999px;background:rgba(31,130,82,.09);color:#17643f;font-weight:850}
            @media(max-width:900px){
                .dco-cost-section-title{align-items:flex-start!important;flex-direction:column}
                .dco-cost-section-title>span{max-width:100%;text-align:right}
            }
            @media(max-width:760px){
                .dco-cost-table-wrap{padding:8px;overflow:visible}
                .dco-cost-table.dco-cost-table--enhanced{min-width:0!important;border:0;background:transparent;overflow:visible}
                .dco-cost-table--enhanced thead{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
                .dco-cost-table--enhanced tbody{display:grid;gap:10px}
                .dco-cost-table--enhanced tbody tr{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0;border:1px solid var(--border-color,#dfe4e8);border-radius:13px;background:var(--card-bg,#fff)!important;overflow:hidden;box-shadow:0 5px 16px rgba(23,32,51,.05)}
                .dco-cost-table--enhanced tbody td{display:flex;align-items:center;justify-content:space-between;gap:12px;min-width:0!important;width:auto!important;padding:10px 11px!important;border-bottom:1px solid var(--border-color,#edf0f2)!important;text-align:left!important}
                .dco-cost-table--enhanced tbody td::before{content:attr(data-label);color:var(--text-muted,#66727d);font-size:9px;font-weight:850;text-align:right}
                .dco-cost-table--enhanced tbody td.dco-cell-notes,.dco-cost-table--enhanced tbody td.dco-edge-detail-cell,.dco-cost-table--invoice tbody td:nth-child(2){grid-column:1/-1}
                .dco-cost-table--enhanced tbody td.dco-cell-notes,.dco-cost-table--enhanced tbody td.dco-edge-detail-cell{align-items:flex-start;flex-direction:column;text-align:right!important}
                .dco-cost-table--enhanced tbody td:last-child{border-bottom:0!important}
                .dco-custom-edge-list{width:100%}
                .dco-custom-edge-chip{grid-template-columns:1fr;gap:3px;width:100%}
                .dco-custom-edge-chip em{justify-self:start}
            }
        `;
        document.head.appendChild(style);
    }

    function findSection(wrapper, title) {
        return [...wrapper.querySelectorAll(".dco-cost-section")].find(section => {
            const heading = section.querySelector(".dco-cost-section-title h4");
            return heading && heading.textContent.trim() === title;
        }) || null;
    }

    function decorateTable(table, kind) {
        if (!table) return;
        table.classList.add("dco-cost-table--enhanced", `dco-cost-table--${kind}`);
        const headers = [...table.querySelectorAll("thead th")].map(th => th.textContent.trim());
        table.querySelectorAll("tbody tr").forEach(row => {
            [...row.children].forEach((cell, index) => {
                cell.dataset.label = headers[index] || "";
            });
            const cells = row.querySelectorAll(":scope > td");
            if (cells[0] && !cells[0].querySelector(".dco-row-index")) {
                cells[0].innerHTML = `<span class="dco-row-index">${esc(cells[0].textContent.trim())}</span>`;
            }
            if (kind === "measurements") {
                if (cells[1] && !cells[1].querySelector(".dco-piece-type")) {
                    const label = cells[1].textContent.trim();
                    cells[1].innerHTML = `<span class="dco-piece-type ${label.includes("خاصة") ? "is-special" : ""}">${esc(label)}</span>`;
                }
                if (cells[6]) {
                    cells[6].classList.add("dco-cell-notes");
                    if (cells[6].textContent.trim() === "—") cells[6].classList.add("is-empty");
                }
            }
        });
    }

    function patchMeasurements(frm, wrapper) {
        const section = findSection(wrapper, "جدول قياسات الطلب");
        const table = section && section.querySelector("table.dco-cost-table");
        if (!table) return;
        const headerCells = table.querySelectorAll("thead th");
        if (headerCells[5]) headerCells[5].textContent = "القشاط المخصص";
        const data = rows(frm);
        table.querySelectorAll("tbody tr").forEach((row, index) => {
            const cells = row.querySelectorAll(":scope > td");
            if (!cells[5] || !data[index]) return;
            cells[5].classList.add("dco-edge-detail-cell");
            const signature = JSON.stringify(customEdgeGroups(data[index].details));
            if (cells[5].dataset.customEdgeSignature !== signature) {
                cells[5].dataset.customEdgeSignature = signature;
                cells[5].innerHTML = customEdgeSummaryHtml(data[index].details);
            }
        });
        const subtitle = section.querySelector(".dco-cost-section-title span");
        if (subtitle) {
            subtitle.textContent = "التخصيص الاستثنائي فقط؛ قشاط الأطراف الافتراضي محدد في بيانات الطلب";
        }
        decorateTable(table, "measurements");
    }

    function patchInvoice(frm, wrapper) {
        const section = findSection(wrapper, "تفاصيل الفاتورة");
        const table = section && section.querySelector("table.dco-cost-table");
        const tbody = table && table.querySelector("tbody");
        if (!tbody) return;
        const signature = JSON.stringify(invoiceLines(frm));
        if (tbody.dataset.sideEdgeInvoiceSignature !== signature) {
            tbody.dataset.sideEdgeInvoiceSignature = signature;
            tbody.innerHTML = invoiceRowsHtml(frm);
        }
        const subtitle = section.querySelector(".dco-cost-section-title span");
        if (subtitle) {
            subtitle.innerHTML = '<span class="dco-edge-pricing-note">سطر مستقل لكل نوع قشاط وسعره</span>';
        }
        const amount = section.querySelector(".dco-grand-total .amount");
        if (amount) amount.textContent = `$ ${money(invoiceTotal(frm))}`;
        decorateTable(table, "invoice");
    }

    function patchCostScreen(frm) {
        installStyles();
        const field = frm.fields_dict.order_cost_invoice_html;
        const wrapper = field && field.$wrapper && field.$wrapper.get(0);
        if (!wrapper) return;
        patchMeasurements(frm, wrapper);
        patchInvoice(frm, wrapper);
        if (wrapper._dcoSideEdgeDocumentsObserver) return;
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

    function schedule(frm) {
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

    window.AlmdinaMultiEdgeDocuments = Object.freeze({
        edgeInvoiceLines,
        invoiceLines,
        invoiceTotal,
        patch: patchCostScreen,
    });
})();
