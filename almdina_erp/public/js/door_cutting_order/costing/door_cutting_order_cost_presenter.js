(() => {
    "use strict";

    if (window.AlmdinaOrderCostUX) return;

    const STYLE_ID = "dco-capability-cost-presenter-css-v8";
    const LEGACY_STYLE_IDS = Object.freeze([
        "dco-capability-cost-presenter-css-v7",
        "dco-capability-cost-presenter-css-v6",
        "dco-capability-cost-presenter-css-v5",
    ]);

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

    function translate(message, replacements) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") {
            return locale.translate(message, replacements);
        }
        if (typeof __ === "function") {
            return replacements === undefined ? __(message) : __(message, replacements);
        }
        let text = String(message == null ? "" : message);
        if (Array.isArray(replacements)) {
            replacements.forEach((value, index) => {
                text = text.split(`{${index}}`).join(String(value));
            });
        }
        return text;
    }

    function uiDirection() {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.direction === "function") {
            const value = locale.direction();
            if (value === "ltr" || value === "rtl") return value;
        }
        const root = typeof document !== "undefined" ? document.documentElement : null;
        const dir = root && root.getAttribute("dir");
        return dir === "ltr" ? "ltr" : "rtl";
    }

    function htmlText(message, replacements) {
        return esc(translate(message, replacements));
    }

    function pieceTypeLabel(value) {
        if (value === "Special") return translate("Special");
        if (value === "Clipped Corner") return translate("Clipped corner");
        if (value === "L-Shaped Corner") return translate("L-shaped corner");
        if (value === "Glass") return translate("Glass");
        if (value === "Regular" || value == null || value === "") return translate("Regular");
        return String(value);
    }

    function isCornerCutType(value) {
        const geometry = window.AlmdinaClippedCornerGeometry;
        return Boolean(geometry && geometry.isCornerCut({ piece_type: value }));
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
            edgeBreak: Boolean(number(source.edge_break)),
            edgeBreakOnly: Boolean(number(source.edge_break_only)),
            edgeBreakLength: number(source.edge_break_length_cm),
            edgeBreakMeters: number(source.edge_break_meters),
            edgeBreakRate: number(source.edge_break_rate_usd),
            edgeBreakAmount: number(source.edge_break_cost_usd),
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
            extraAddons: [
                {
                    selected: Boolean(number(source.extra_double)),
                    label: "Double Edge",
                    rate: number(source.extra_double_unit_price_usd),
                    amount: number(source.extra_double_total_usd),
                },
                {
                    selected: Boolean(number(source.extra_full_door_double)),
                    label: "Full door double",
                    rate: number(source.extra_full_door_double_unit_price_usd),
                    amount: number(source.extra_full_door_double_total_usd),
                },
                {
                    selected: Boolean(number(source.extra_liner)),
                    label: "Liner",
                    rate: number(source.extra_liner_unit_price_usd),
                    amount: number(source.extra_liner_total_usd),
                },
                {
                    selected: Boolean(number(source.extra_back_groove)),
                    label: "Back groove",
                    rate: number(source.extra_back_groove_unit_price_usd),
                    amount: number(source.extra_back_groove_total_usd),
                },
                {
                    selected: Boolean(number(source.extra_recessed_handle_cutout)),
                    label: "Recessed handle",
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
        return row.clippedEdgeStatus === "Priced";
    }

    function invoiceLines(frm) {
        const result = [];
        const allRows = rows(frm);
        const specialDoorRows = allRows.filter(row => row.pieceType === "Special");
        const edgeRows = specialDoorRows.length
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
                description: frm.doc.board_description
                    ? translate("MDF boards — {0}", [frm.doc.board_description])
                    : translate("MDF boards"),
                quantity: boardCount || (boardRate ? boardAmount / boardRate : 0),
                unit: translate("Board"),
                rate: boardRate,
                amount: boardAmount,
            });
        }

        if (boardCount || cuttingAmount) {
            result.push({
                type: "cutting",
                description: translate("Board cutting and preparation"),
                quantity: boardCount || (cuttingRate ? cuttingAmount / cuttingRate : 0),
                unit: translate("Board"),
                rate: cuttingRate,
                amount: cuttingAmount,
            });
        }

        const edgeGroups = new Map();
        const addEdgeGroup = (row, meters, rate, amount) => {
            if (meters <= 0) return;
            const edgeName = String(row.edgeType || "");
            const key = `${edgeName}::${rate}`;
            const group = edgeGroups.get(key) || {
                type: "edge",
                // Quotation row shows the edge-type name only (no "Edge banding —" prefix).
                description: edgeName || translate("Edge banding — unspecified"),
                quantity: 0,
                unit: translate("Meter"),
                rate,
                amount: 0,
            };
            group.quantity += meters;
            group.amount += amount;
            edgeGroups.set(key, group);
        };
        edgeRows.forEach(row => {
            if (row.edgeBreakOnly) {
                addEdgeGroup(
                    row,
                    Math.max(0, row.edgeMeters - row.edgeBreakMeters),
                    row.edgeRate,
                    Math.max(0, row.edgeAmount - row.edgeBreakAmount)
                );
                addEdgeGroup(
                    row,
                    row.edgeBreakMeters,
                    row.edgeBreakRate,
                    row.edgeBreakAmount
                );
                return;
            }
            addEdgeGroup(
                row,
                row.edgeMeters,
                row.edgeRate,
                row.edgeAmount || row.edgeMeters * row.edgeRate
            );
        });
        result.push(...edgeGroups.values());

        if (!edgeGroups.size && !specialDoorRows.length && number(frm.doc.edge_cost_usd) > 0) {
            result.push({
                type: "edge",
                description: translate("Edge banding"),
                quantity: number(frm.doc.total_edge_meters),
                unit: translate("Meter"),
                rate: 0,
                amount: number(frm.doc.edge_cost_usd),
            });
        }

        allRows.forEach(row => {
            if (row.pieceType === "Special") {
                const ready = specialPriceReady(row);
                result.push({
                    type: "special",
                    description: translate("Special door number {0}", [row.index]),
                    quantity: row.qty,
                    unit: translate("Door"),
                    rate: ready ? row.approvedUnit : null,
                    amount: ready ? row.approvedUnit * row.qty : 0,
                    pending: !ready,
                    note: ready ? row.priceNote : translate("Waiting for the inclusive special price"),
                });
            } else if (isCornerCutType(row.pieceType) && row.edgeBreak && row.edgeBreakLength > 0) {
                const ready = cutCornerPriceReady(row);
                result.push({
                    type: "cut_corner",
                    description: cutCornerDoorLabel(row),
                    quantity: row.qty,
                    unit: translate("Door"),
                    rate: ready ? row.clippedEdgePrice : null,
                    amount: ready ? row.clippedEdgePrice * row.qty : 0,
                    pending: !ready,
                    note: ready ? row.clippedEdgeNote : translate(
                        row.pieceType === "L-Shaped Corner"
                            ? "Waiting for the L-shaped corner edge price"
                            : "Waiting for the clipped-corner edge price"
                    ),
                });
            }
            row.extraAddons
                .filter(addon => addon.selected || addon.amount > 0)
                .forEach(addon => result.push({
                    type: "extra_addon",
                    description: `Add-on ${addon.label} — door number ${row.index}`,
                    quantity: row.qty,
                    unit: translate("Door"),
                    rate: addon.rate,
                    amount: addon.amount || addon.rate * row.qty,
                    note: row.notes,
                }));
        });

        return result;
    }

    function pendingCustomEdgePriceLabels(frm) {
        return rows(frm).flatMap(row => {
            if (row.pieceType === "Special" && !specialPriceReady(row)) {
                return [translate("Special door number {0}", [row.index])];
            }
            if (isCornerCutType(row.pieceType) && row.edgeBreak && !cutCornerPriceReady(row)) {
                return [cutCornerDoorLabel(row)];
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

    function dimensionMark(value, count) {
        // Same count contract as measurements print (one mark per edged side on that axis).
        // Screen layout mirrors the printed look: 2 sides => line above + below; 1 side => below.
        const safeCount = Math.max(0, Math.min(2, Number(count || 0)));
        const line = '<span class="dco-cost-dimension-edge-line" aria-hidden="true"></span>';
        const spacer = '<span class="dco-cost-dimension-edge-line is-spacer" aria-hidden="true"></span>';
        const top = safeCount === 2 ? line : spacer;
        const bottom = safeCount >= 1 ? line : spacer;
        return (
            `<span class="dco-cost-dimension" data-edge-marks="${safeCount}">`
            + `<span class="dco-cost-dimension-rail">${top}</span>`
            + `<b>${quantity(value)}</b>`
            + `<span class="dco-cost-dimension-rail">${bottom}</span>`
            + `</span>`
        );
    }

    function installStyles() {
        LEGACY_STYLE_IDS.forEach((id) => {
            const legacy = document.getElementById(id);
            if (legacy) legacy.remove();
        });
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-cost-shell{max-width:1440px;margin:0 auto;padding:4px 0 18px}
            .dco-cost-actions-bar{display:flex;justify-content:flex-start;margin:0 0 12px;min-height:32px}
            .dco-cost-actions{display:flex;gap:8px;flex-wrap:wrap}
            .dco-cost-actions .btn{border-radius:9px;font-weight:800}
            .dco-cost-section{margin-top:12px;border:1px solid var(--border-color,#dfe4e8);border-radius:15px;background:var(--card-bg,#fff);overflow:hidden}
            .dco-cost-section-title{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:13px 16px;border-bottom:1px solid var(--border-color,#dfe4e8);background:var(--subtle-fg,#f8f9fa)}
            .dco-cost-section-title h4{margin:0;font-size:14px;font-weight:900}
            .dco-cost-section-title span{font-size:10px;color:var(--text-muted,#687481)}
            .dco-offcut-price-body{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:14px 16px}
            .dco-offcut-price-body>span{font-size:12px;font-weight:800;color:var(--text-muted,#687481)}
            .dco-offcut-price-control{min-width:150px;display:flex;justify-content:flex-end}
            .dco-offcut-price-input{max-width:150px;direction:ltr;text-align:end;font-weight:900}
            .dco-offcut-price-input:disabled,.dco-offcut-price-input[readonly]{background:transparent;border-color:transparent;box-shadow:none;color:inherit;opacity:1;cursor:default;padding-inline:0}
            .dco-cost-table-wrap{overflow:auto}
            .dco-cost-table{width:100%;min-width:760px;border-collapse:collapse;font-size:12px}
            .dco-cost-table th,.dco-cost-table td{padding:9px 10px;border-bottom:1px solid var(--border-color,#e7ebef);text-align:center;vertical-align:middle}
            .dco-cost-table th{background:var(--subtle-fg,#f7f9fb);font-weight:900;white-space:nowrap}
            .dco-cost-table tr:last-child td{border-bottom:0}
            .dco-cost-table .text-start{text-align:start}
            .dco-cost-dimension{display:inline-flex;min-width:2.75rem;flex-direction:column;align-items:center;gap:2px;line-height:1}
            .dco-cost-dimension b{font-size:12px;font-weight:900}
            .dco-cost-dimension-rail{display:flex;min-height:4px;align-items:center;justify-content:center}
            .dco-cost-dimension-edge-line{display:block;width:1.65rem;height:1.5px;border-radius:999px;background:var(--alm-primary,#172033)}
            .dco-cost-dimension-edge-line.is-spacer{visibility:hidden}
            .dco-invoice-pending-row td{background:rgba(190,125,25,.055)}
            .dco-invoice-pending-badge{display:inline-flex;margin-inline-start:7px;padding:2px 7px;border-radius:999px;background:#fff3d8;color:#875812;font-size:9px;font-weight:900}
            .dco-invoice-pending-value{font-weight:900;color:#9a6a1d}
            .dco-special-price-list{display:grid;gap:9px;padding:12px}
            .dco-special-price-card{display:grid;grid-template-columns:minmax(150px,.9fr) minmax(160px,1fr) minmax(140px,.85fr) auto;align-items:center;gap:10px;padding:12px;border:1px solid var(--border-color,#e0e5e9);border-radius:13px;background:var(--card-bg,#fff)}
            .dco-special-price-id{font-size:14px;font-weight:900;letter-spacing:.02em}
            .dco-special-price-id small{display:block;margin-top:3px;font-size:10px;font-weight:700;color:var(--text-muted,#687481);letter-spacing:0}
            .dco-special-price-cell{padding:8px 9px;border-radius:10px;background:var(--subtle-fg,#f7f9fa)}
            .dco-special-price-cell span{display:block;font-size:9px;color:var(--text-muted,#687481);margin-bottom:3px}
            .dco-special-price-cell b{display:block;direction:ltr;text-align:end}
            .dco-special-price-cell.is-unpriced b{color:var(--text-muted,#8a939c);font-weight:800}
            .dco-inline-price-input{
                width:100%;max-width:140px;box-sizing:border-box;padding:6px 8px;border:1px solid var(--border-color,#d0d7de);
                border-radius:8px;background:#fff;font-size:13px;font-weight:800;direction:ltr;text-align:end;
            }
            .dco-inline-price-input:disabled,.dco-inline-price-input[readonly]{
                background:transparent;border-color:transparent;color:inherit;padding-inline:0;cursor:default;
            }
            .dco-inline-price-input:not(:disabled):not([readonly]):focus{
                outline:2px solid var(--alm-primary,#172033);outline-offset:1px;
            }
            .dco-special-price-actions{display:flex;flex-direction:column;gap:6px;min-width:118px}
            .dco-special-price-note{grid-column:1/-1;font-size:10px;color:var(--text-muted,#687481)}
            .dco-cost-section{border-color:var(--alm-card-border,#e4e8ee);border-radius:var(--alm-radius-card,16px);box-shadow:var(--alm-shadow-card,0 8px 24px rgba(15,23,42,.045))}
            .dco-cost-section-title{background:var(--alm-card,#fff)}
            .dco-cost-invoice-section .dco-cost-section-title{align-items:flex-start}
            .dco-cost-actions .btn,.dco-cost-actions .alm-btn-primary{border-radius:999px;background:var(--alm-primary,#172033);color:var(--alm-on-primary,#fff);border-color:var(--alm-primary,#172033)}
            .dco-invoice-total-card{margin:12px;padding:16px 18px;border:1px solid var(--alm-card-border,#e4e8ee);border-radius:14px;background:var(--alm-card,#fff);display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
            .dco-invoice-total-card.is-pending{border-color:color-mix(in srgb, var(--alm-warning,#b45309) 35%, #fff);background:var(--alm-warning-bg,#fff7e8)}
            .dco-invoice-total-label{display:flex;flex-direction:column;gap:4px;flex:1 1 160px;min-width:0}
            .dco-invoice-total-end{display:flex;align-items:center;justify-content:flex-end;flex-wrap:wrap;gap:8px;margin-inline-start:auto;flex:0 1 auto;min-width:0}
            .dco-invoice-total-card .dco-invoice-total-label>span{display:block;font-size:13px;font-weight:800;color:var(--text-color,#1f272e)}
            .dco-invoice-total-card.is-pending .dco-invoice-total-label>span{color:var(--alm-warning,#b45309)}
            .dco-invoice-total-card .dco-invoice-total-label small{display:block;margin-top:0;font-size:10px;color:var(--text-muted,#687481);font-weight:700}
            .dco-invoice-total-amount{display:inline-flex;align-items:center;justify-content:center;min-height:52px;padding:8px 16px;border:1px solid color-mix(in srgb, var(--alm-warning,#b45309) 45%, #fff);border-radius:12px;background:#fff;font-size:28px;font-weight:900;direction:ltr;text-align:left;color:var(--alm-warning,#b45309);letter-spacing:.01em;flex:0 0 auto}
            .dco-invoice-total-card.is-pending .dco-invoice-total-amount{color:var(--alm-warning,#b45309)}
            .dco-price-approval-slot{display:flex;align-items:center;flex:0 1 auto;min-width:0}
            .dco-cost-empty{padding:24px;text-align:center;color:var(--text-muted,#687481)}
            .dco-cost-plan-stale-notice{margin:0;padding:10px 14px;border-bottom:1px solid rgba(190,125,25,.28);background:rgba(190,125,25,.08);color:#875812;font-size:11px;font-weight:800;line-height:1.55}
            @media(max-width:900px){.dco-special-price-card{grid-template-columns:1fr 1fr}.dco-special-price-actions,.dco-special-price-card>.dco-special-price-id,.dco-special-price-note{grid-column:1/-1}}
            @media(max-width:560px){.dco-cost-actions .btn{width:100%}.dco-special-price-card{grid-template-columns:1fr}.dco-invoice-total-card{align-items:stretch}.dco-invoice-total-label{flex:1 1 100%}.dco-invoice-total-end{flex:1 1 100%;margin-inline-start:0;justify-content:flex-start}.dco-invoice-total-amount{font-size:24px;margin-inline-start:auto}.dco-offcut-price-body{align-items:flex-start;flex-direction:column}.dco-offcut-price-control{width:100%;justify-content:flex-start}}
        `;
        document.head.appendChild(style);
    }

    function measurementRowsHtml(frm) {
        const data = rows(frm);
        if (!data.length) {
            return `<div class="dco-cost-empty">${htmlText("This order has no measurements yet.")}</div>`;
        }
        return `<div class="dco-cost-table-wrap"><table class="dco-cost-table"><thead><tr>
            <th>#</th><th>${htmlText("Type")}</th><th>${htmlText("Width (cm)")}</th><th>${htmlText("Length (cm)")}</th><th>${htmlText("Quantity")}</th><th class="text-start">${htmlText("Notes")}</th><th>${htmlText("Edge type")}</th>
        </tr></thead><tbody>${data.map(row => {
            const widthCount = Number(Boolean(row.source.edge_width_top))
                + Number(Boolean(row.source.edge_width_bottom));
            const longCount = Number(Boolean(row.source.edge_long_right))
                + Number(Boolean(row.source.edge_long_left));
            return `<tr>
            <td><b>${row.index}</b></td><td data-piece-type="${esc(row.pieceType)}">${esc(pieceTypeLabel(row.pieceType))}</td>
            <td>${dimensionMark(row.width, widthCount)}</td><td>${dimensionMark(row.length, longCount)}</td><td>${row.qty}</td>
            <td class="text-start">${esc(row.notes || "—")}</td><td>${esc(row.edgeType || "—")}</td>
        </tr>`;
        }).join("")}</tbody></table></div>`;
    }

    function planNeedsRecalculation(frm) {
        return Number(frm.doc.plan_needs_recalculation || 0) === 1;
    }

    function stalePlanNoticeHtml(frm) {
        if (!planNeedsRecalculation(frm)) return "";
        return `<div class="dco-cost-plan-stale-notice" role="status">
            ${htmlText("Board count and cutting charges use the last calculated plan. Calculate the cutting plan to update the invoice with the final values.")}
        </div>`;
    }

    function offcutPriceHtml(frm) {
        const state = window.AlmdinaCostWorkspaceState;
        const snapshot = state && typeof state.snapshot === "function" ? state.snapshot(frm) : null;
        const hasOffcut = Boolean(snapshot && snapshot.data && snapshot.data.offcut
            && Array.isArray(snapshot.data.offcut.assignments)
            && snapshot.data.offcut.assignments.length);
        if (number(frm.doc.offcut_price_applicable) <= 0 && !hasOffcut) return "";
        const value = number(frm.doc.offcut_price_usd);
        return `<div class="dco-cost-section dco-offcut-price-section" data-offcut-price-section>
            <div class="dco-cost-section-title">
                <h4>${htmlText("Offcut price")}</h4><span>${htmlText("One total price for the group")}</span>
            </div>
            <div class="dco-offcut-price-body">
                <span>${htmlText("Offcut price ($)")}</span>
                <div class="dco-offcut-price-control" data-offcut-price-control>
                    <input class="form-control dco-offcut-price-input" data-offcut-price-input type="number" min="0" step="0.01" value="${esc(value)}" disabled readonly inputmode="decimal" aria-label="${htmlText("Offcut price ($)")}">
                </div>
            </div>
        </div>`;
    }

    function invoiceRowsHtml(frm) {
        const lines = effectiveInvoiceLines(frm);
        if (!lines.length) {
            return `<div class="dco-cost-empty">${htmlText("Save the order and calculate the cutting plan to show the price details.")}</div>`;
        }
        return `${stalePlanNoticeHtml(frm)}<div class="dco-cost-table-wrap"><table class="dco-cost-table"><thead><tr>
            <th>#</th><th class="text-start">${htmlText("Description")}</th><th>${htmlText("Quantity")}</th><th>${htmlText("Unit")}</th><th>${htmlText("Unit price ($)")}</th><th>${htmlText("Total ($)")}</th>
        </tr></thead><tbody>${lines.map((line, index) => `<tr class="${line.pending ? "dco-invoice-pending-row" : ""}">
            <td>${index + 1}</td><td class="text-start"><b>${esc(line.description)}</b>${line.pending ? `<span class="dco-invoice-pending-badge">${htmlText("Unpriced")}</span>` : ""}${line.note ? `<small style="display:block">${esc(line.note)}</small>` : ""}</td>
            <td>${quantity(line.quantity)}</td><td>${esc(line.unit)}</td>
            <td class="${line.pending ? "dco-invoice-pending-value" : ""}">${line.pending ? "—" : money(line.rate)}</td>
            <td class="${line.pending ? "dco-invoice-pending-value" : ""}">${line.pending ? "—" : `<b>${money(line.amount)}</b>`}</td>
        </tr>`).join("")}</tbody></table></div>`;
    }

    function invoiceTotalCardHtml(frm) {
        const total = quoteTotal(frm);
        const pending = pendingCustomEdgePriceLabels(frm);
        const approvalSlot = '<div class="dco-price-approval-slot" data-price-approval-panel></div>';
        const amount = `<b class="dco-invoice-total-amount">$ ${money(total)}</b>`;
        if (!pending.length) {
            return `<div class="dco-invoice-total-card">
                <div class="dco-invoice-total-label">
                    <span>${htmlText("Final invoice total")}</span>
                </div>
                <div class="dco-invoice-total-end">
                    ${approvalSlot}
                    ${amount}
                </div>
            </div>`;
        }
        return `<div class="dco-invoice-total-card is-pending">
            <div class="dco-invoice-total-label">
                <span>${htmlText("Current total before unpriced items")}</span>
                <small>${htmlText("This is not a final total until these items are priced: {0}", [pending.join(", ")])}</small>
            </div>
            <div class="dco-invoice-total-end">
                ${approvalSlot}
                ${amount}
            </div>
        </div>`;
    }

    function specialDoorLabel(row) {
        return translate("Special door number {0}", [row.index]);
    }

    function cutCornerDoorLabel(row) {
        return row.pieceType === "L-Shaped Corner"
            ? translate("L-shaped corner door {0}", [row.index])
            : translate("Clipped-corner door {0}", [row.index]);
    }

    function specialPriceInputValue(row) {
        if (specialPriceReady(row)) return number(row.approvedUnit);
        return number(row.estimatedUnit);
    }

    function specialPricingHtml(frm) {
        const specialRows = rows(frm).filter(row => row.pieceType === "Special");
        if (!specialRows.length) return "";
        return `<div class="dco-cost-section"><div class="dco-cost-section-title">
            <h4>${htmlText("Special door pricing")}</h4><span>${htmlText("Enter the inclusive special price for each door while editing")}</span>
        </div><div class="dco-special-price-list">${specialRows.map(row => {
            const doorLabel = specialDoorLabel(row);
            const priced = specialPriceReady(row);
            const documented = row.drawingStatus === "Documented"
                || Boolean(String(row.source.special_shape_geometry_json || "").trim())
                || Boolean(String(row.source.special_shape_drawing_json || "").trim());
            const priceValue = specialPriceInputValue(row);
            return `<div class="dco-special-price-card" data-special-row="${esc(row.name)}" data-custom-id="${esc(doorLabel)}">
                <div class="dco-special-price-id">${esc(doorLabel)}<small>${htmlText("{0} × {1} cm — quantity {2}", [quantity(row.length), quantity(row.width), row.qty])}</small></div>
                <div class="dco-special-price-cell"><span>${htmlText("Length × width")}</span><b>${htmlText("{0} × {1} cm", [quantity(row.length), quantity(row.width)])}</b></div>
                <div class="dco-special-price-cell ${priced ? "" : "is-unpriced"}">
                    <span>${htmlText("Inclusive special price ($)")}</span>
                    <input type="number" class="dco-inline-price-input" data-price-kind="special" data-piece-name="${esc(row.name)}" min="0" step="0.01" value="${esc(priceValue)}" disabled readonly inputmode="decimal">
                    ${priced ? "" : `<small style="display:block;margin-top:4px;color:var(--text-muted,#8a939c)">${htmlText("Unpriced")}</small>`}
                </div>
                <div class="dco-special-price-actions"><button type="button" class="btn btn-default btn-xs dco-view-special-sketch" ${documented ? "" : "disabled"}>${htmlText("View documentation")}</button></div>
                ${row.priceNote ? `<div class="dco-special-price-note">${esc(row.priceNote)}</div>` : ""}
            </div>`;
        }).join("")}</div></div>`;
    }

    function bindViewDrawing(frm, wrapper) {
        wrapper.find(".dco-view-special-sketch").on("click", function onViewDrawing() {
            const card = this.closest("[data-special-row]");
            const source = (frm.doc.pieces || []).find(row => row.name === (card && card.dataset.specialRow));
            if (!source || !window.AlmdinaSpecialShapeEditor || typeof window.AlmdinaSpecialShapeEditor.view !== "function") {
                frappe.msgprint(translate("Could not load the special door documentation."));
                return;
            }
            window.AlmdinaSpecialShapeEditor.view(frm, source);
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
            field.$wrapper.html(`<div class="dco-cost-shell" dir="${esc(uiDirection())}">${actionShell}</div>`);
            return true;
        }

        field.$wrapper.html(`<div class="dco-cost-shell" dir="${esc(uiDirection())}">
            ${actionShell}
            ${offcutPriceHtml(frm)}
            <div class="dco-cost-section"><div class="dco-cost-section-title"><h4>${htmlText("Order measurement table")}</h4><span>${htmlText("Measurements, quantities, and notes")}</span></div>${measurementRowsHtml(frm)}</div>
            ${specialPricingHtml(frm)}
            <div class="dco-cost-section dco-cost-invoice-section"><div class="dco-cost-section-title"><h4>${htmlText("Quotation details")}</h4><span>${htmlText("Boards, cutting, edge banding, special doors, and door add-ons")}</span></div>${invoiceRowsHtml(frm)}${invoiceTotalCardHtml(frm)}</div>
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
            `<div class="dco-cost-section-title"><h4>${htmlText("Quotation details")}</h4><span>${htmlText("Boards, cutting, edge banding, special doors, and door add-ons")}</span></div>${invoiceRowsHtml(frm)}${invoiceTotalCardHtml(frm)}`
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
