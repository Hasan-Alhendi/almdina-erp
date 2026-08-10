(() => {
    "use strict";

    // Canonical cutting-plan renderer shared by the order and shop-floor views.
    function num(value) {
        if (value === null || value === undefined) return 0;
        return parseFloat(String(value).replace(/,/g, "")) || 0;
    }

    function round(value, decimals = 3) {
        const factor = Math.pow(10, decimals);
        return Math.round(num(value) * factor) / factor;
    }

    function escape_html(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function parse_plan(frm) {
        const raw = frm.doc.cutting_plan_json;
        if (!raw) return null;

        if (typeof raw === "object") return raw;

        try {
            return JSON.parse(raw);
        } catch (error) {
            console.error("Invalid cutting_plan_json", error);
            return null;
        }
    }

    // =====================================================
    // Cutting plan rendering
    // =====================================================

    function render_piece_edge_lines(piece) {
        let left = 0;
        let right = 0;
        let top = 0;
        let bottom = 0;

        if (!piece.rotated) {
            left = piece.edge_long_left ? 1 : 0;
            right = piece.edge_long_right ? 1 : 0;
            top = piece.edge_width_top ? 1 : 0;
            bottom = piece.edge_width_bottom ? 1 : 0;
        } else {
            // 90 degrees clockwise, preserving the physical edge meaning.
            top = piece.edge_long_left ? 1 : 0;
            bottom = piece.edge_long_right ? 1 : 0;
            right = piece.edge_width_top ? 1 : 0;
            left = piece.edge_width_bottom ? 1 : 0;
        }

        const color = "#d00000";
        const thickness = "3px";
        const inset = "3px";
        const EDGE_LINE_PERCENT = 66.666;
        const EDGE_LINE_START = (100 - EDGE_LINE_PERCENT) / 2;
        let html = "";

        if (left) {
            html += `<span class="dco-edge-line" style="position:absolute;left:${inset};top:${EDGE_LINE_START}%;height:${EDGE_LINE_PERCENT}%;border-left:${thickness} solid ${color};z-index:3;"></span>`;
        }
        if (right) {
            html += `<span class="dco-edge-line" style="position:absolute;right:${inset};top:${EDGE_LINE_START}%;height:${EDGE_LINE_PERCENT}%;border-right:${thickness} solid ${color};z-index:3;"></span>`;
        }
        if (top) {
            html += `<span class="dco-edge-line" style="position:absolute;top:${inset};left:${EDGE_LINE_START}%;width:${EDGE_LINE_PERCENT}%;border-top:${thickness} solid ${color};z-index:3;"></span>`;
        }
        if (bottom) {
            html += `<span class="dco-edge-line" style="position:absolute;bottom:${inset};left:${EDGE_LINE_START}%;width:${EDGE_LINE_PERCENT}%;border-bottom:${thickness} solid ${color};z-index:3;"></span>`;
        }

        return html;
    }

    function render_piece_label(piece) {
        const shape_output = window.AlmdinaShapeOutputContract;
        const exact_special = piece.piece_type === "Special"
            && shape_output
            && shape_output.hasExactCutPath(piece);
        const special = piece.piece_type === "Special"
            ? `<span style="display:inline-block;margin-bottom:2px;padding:2px 6px;border-radius:999px;background:#7a4c13;color:#fff;font-size:9px;font-weight:900">${exact_special ? "◆ درفة خاصة · مسار هندسي" : "✦ درفة خاصة · خام CNC"}</span><br>`
            : "";
        const clipped = piece.piece_type === "Clipped Corner"
            ? `<span style="display:inline-block;margin-bottom:2px;padding:2px 6px;border-radius:999px;background:#8a5700;color:#fff;font-size:9px;font-weight:900">⌑ زاوية مقصوصة</span><br>`
            : "";
        return `
            <div class="dco-piece-label" style="position:relative;z-index:4;direction:ltr;text-align:center;">
                ${special}${clipped}
                <span>${round(piece.original_w, 1)}*${round(piece.original_h, 1)}</span>
            </div>
        `;
    }

    function render_special_raw_coverage(frm, plan) {
        const requested_from_rows = (frm.doc.pieces || []).reduce((total, row) => {
            if ((row.piece_type || "Regular") !== "Special") return total;
            return total + Math.max(0, Math.floor(num(row.qty)));
        }, 0);
        const placed_from_plan = (plan.sheets || []).reduce((total, sheet) => {
            return total + (sheet.pieces || []).filter(piece => piece.piece_type === "Special").length;
        }, 0);
        const snapshot = plan.special_shape_raw_summary || {};
        const requested = Number.isFinite(Number(snapshot.requested))
            ? Number(snapshot.requested)
            : requested_from_rows;
        const placed = Number.isFinite(Number(snapshot.placed))
            ? Number(snapshot.placed)
            : placed_from_plan;
        if (!requested) return "";

        const complete = Boolean(snapshot.complete ?? (placed === requested));
        const tone = complete
            ? "border-color:#c9a66b;background:linear-gradient(135deg,#fff8e8,#fffdf8);color:#684117"
            : "border-color:#dc7b72;background:#fff4f2;color:#9b2f26";
        const message = complete
            ? `تم إدخال جميع الدرف الخاصة في خطة القص كمستطيل خام: <b>${placed} من ${requested}</b>`
            : `تنبيه: دخل خطة القص <b>${placed} من ${requested}</b> فقط من الدرف الخاصة. راجع المقاسات والقطع غير الموزعة.`;

        return `
            <div class="dco-special-raw-coverage" style="direction:rtl;border:1px solid;border-radius:10px;padding:9px 12px;margin:8px 0 12px;font-size:12px;font-weight:700;${tone}">
                <span style="font-size:16px;margin-left:6px">✦</span>${message}
            </div>
        `;
    }

    function render_piece_groups_summary(frm) {
        const rows = (frm.doc.pieces || []).filter(row => {
            return num(row.width_cm) || num(row.length_cm) || num(row.qty);
        });

        if (!rows.length) return "";

        let html = `
            <div class="dco-piece-groups" style="border:1px solid #ddd;border-radius:8px;padding:8px;margin:8px 0 12px 0;font-size:12px;line-height:1.8;background:#fafafa;">
                <b>قائمة الدرف:</b><br>
        `;

        rows.forEach((row, index) => {
            const typeLabel = row.piece_type === "Special"
                ? " · ✦ خاصة (خام CNC)"
                : (row.piece_type === "Clipped Corner" ? " · ⌑ زاوية مقصوصة" : "");
            html += `
                <span style="display:inline-block;margin-left:16px;white-space:nowrap;">
                    ${index + 1}- ${round(row.width_cm, 1)}*${round(row.length_cm, 1)} عدد ${Math.max(0, Math.floor(num(row.qty)))}${typeLabel}
                </span>
            `;
        });

        html += "</div>";
        return html;
    }

    function format_order_date(frm) {
        const raw = frm && frm.doc && frm.doc.order_date;
        if (!raw) return "—";
        if (window.frappe && frappe.datetime && typeof frappe.datetime.str_to_user === "function") {
            return frappe.datetime.str_to_user(raw);
        }
        return String(raw);
    }

    function render_plan_header_cards(frm) {
        const cards = [
            { label: "رقم الطلب", value: frm.doc.name || "—" },
            { label: "اسم الزبون", value: frm.doc.customer || "—" },
            { label: "تاريخ الطلب", value: format_order_date(frm) },
            { label: "نوع اللوح", value: frm.doc.board_description || "—" },
            { label: "لون القشاط", value: frm.doc.edge_color || "—" },
        ];

        return `
            <div class="dco-plan-header-cards" style="display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin:8px 0 12px 0;">
                ${cards.map(card => `
                    <div class="dco-plan-header-card" style="border:1px solid #ddd;border-radius:8px;padding:8px;background:#f8fafc;min-width:0;">
                        <b style="display:block;font-size:10px;color:#555;margin-bottom:4px;">${escape_html(card.label)}</b>
                        <span style="display:block;font-size:12px;font-weight:700;line-height:1.35;word-break:break-word;">${escape_html(card.value)}</span>
                    </div>
                `).join("")}
            </div>
        `;
    }

    function build_cutting_plan_html(frm, plan) {
        if (!plan || !plan.sheets || !plan.sheets.length) return "";

        const board_w_cm = num(plan.usable_board_width_cm);
        const board_h_cm = num(plan.usable_board_length_cm);
        const full_board_w_cm = num(plan.full_board_width_cm);
        const full_board_h_cm = num(plan.full_board_length_cm);
        const kerf_cm = num(plan.kerf_cm);
        const trim_cm = num(plan.trim_cm);
        const board_area_m2 = (board_w_cm * board_h_cm) / 10000;
        const used_area_m2 = round(plan.used_area_m2, 3);
        const total_board_area_m2 = round(plan.total_board_area_m2, 3);
        const waste_area_m2 = round(plan.waste_area_m2, 3);
        const waste_percent = total_board_area_m2 ? round((waste_area_m2 / total_board_area_m2) * 100, 2) : 0;

        const board_width_px = 560;
        const board_height_px = Math.max(260, Math.round(board_width_px * (board_h_cm / board_w_cm)));

        let html = `
            <div class="dco-cutting-plan" style="font-family:Arial,Tahoma,sans-serif;direction:rtl;color:#111;background:#fff;">
                <h2 style="margin:0 0 8px 0;font-size:18px;">خطة القص</h2>
                ${render_plan_header_cards(frm)}

                <div class="dco-summary-grid" style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:8px 0 12px 0;">
                    <div class="dco-summary-card" style="border:1px solid #ddd;border-radius:8px;padding:8px;background:#f8fafc;"><b>عدد الألواح</b><span>${plan.sheets.length}</span></div>
                    <div class="dco-summary-card" style="border:1px solid #ddd;border-radius:8px;padding:8px;background:#f8fafc;"><b>مساحة القطع</b><span>${used_area_m2} م²</span></div>
                    <div class="dco-summary-card" style="border:1px solid #ddd;border-radius:8px;padding:8px;background:#f8fafc;"><b>مساحة الهدر</b><span>${waste_area_m2} م²</span></div>
                    <div class="dco-summary-card" style="border:1px solid #ddd;border-radius:8px;padding:8px;background:#f8fafc;"><b>نسبة الهدر</b><span>${waste_percent}%</span></div>
                </div>

                ${render_piece_groups_summary(frm)}
                ${render_special_raw_coverage(frm, plan)}

                <div style="font-size:12px;margin-bottom:8px;"><b>طريقة الترتيب:</b> ${escape_html(plan.method_label || frm.doc.packing_method || "")}</div>
        `;

        plan.sheets.forEach(sheet => {
            const sheet_used_area_m2 = round((sheet.pieces || []).reduce((sum, p) => sum + num(p.area_m2), 0), 3);
            const sheet_waste_area_m2 = round(Math.max(0, board_area_m2 - sheet_used_area_m2), 3);
            const sheet_waste_percent = board_area_m2 ? round((sheet_waste_area_m2 / board_area_m2) * 100, 2) : 0;

            html += `
                <div class="dco-sheet-card" style="border:1px solid #bbb;border-radius:10px;padding:10px;margin:14px 0;background:#fff;page-break-inside:avoid;break-inside:avoid;">
                    <div class="dco-sheet-title" style="display:flex;justify-content:space-between;gap:10px;margin-bottom:8px;font-size:13px;font-weight:bold;">
                        <div>اللوح ${sheet.sheet_no}</div>
                        <div>عدد القطع: ${(sheet.pieces || []).length} &nbsp; | &nbsp; الهدر: ${sheet_waste_area_m2} م² (${sheet_waste_percent}%)</div>
                    </div>
                    <div class="dco-sheet-board" style="position:relative;direction:ltr;width:${board_width_px}px;height:${board_height_px}px;max-width:100%;border:2px solid #111;background:linear-gradient(90deg,rgba(0,0,0,0.05) 1px,transparent 1px),linear-gradient(rgba(0,0,0,0.05) 1px,transparent 1px),#fff;background-size:32px 32px;overflow:hidden;margin:0 auto 8px auto;">
            `;

            (sheet.pieces || []).forEach(piece => {
                const left = (num(piece.x) / board_w_cm) * 100;
                const top = (num(piece.y) / board_h_cm) * 100;
                const width = (num(piece.w) / board_w_cm) * 100;
                const height = (num(piece.h) / board_h_cm) * 100;
                const special_piece_style = piece.piece_type === "Special"
                    ? "border:2px solid #7a4c13;background:linear-gradient(135deg,#fff2cf,#ffe2a3);box-shadow:inset 0 0 0 2px rgba(255,255,255,.45);"
                    : "border:1px solid #111;background:#e4f5ff;";
                const clipped = piece.piece_type === "Clipped Corner";
                const clippedGeometry = window.AlmdinaClippedCornerGeometry;
                const shapeOutput = window.AlmdinaShapeOutputContract;
                const exactSpecial = piece.piece_type === "Special"
                    && shapeOutput
                    && shapeOutput.hasExactCutPath(piece);
                const shapePoints = clipped && clippedGeometry
                    ? clippedGeometry.pointsAttribute(piece, 100, 100)
                    : (exactSpecial
                        ? shapeOutput.pointsAttribute(piece, 100, 100)
                        : "0,0 100,0 100,100 0,100");
                const shaped = clipped || exactSpecial;
                const shapeOutline = shaped
                    ? `<svg class="dco-shaped-piece-outline" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" style="position:absolute;inset:0;width:100%;height:100%;z-index:1;overflow:visible"><polygon points="${shapePoints}" fill="${exactSpecial ? "#ffe5ad" : "#fff0c7"}" stroke="${exactSpecial ? "#7a4c13" : "#8a5700"}" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round"/></svg>`
                    : "";
                const pieceStyle = shaped
                    ? "border:0;background:transparent;box-shadow:none;"
                    : special_piece_style;
                const shapeClip = shapePoints.split(" ").map(pair => {
                    const [x, y] = pair.split(",");
                    return `${x}% ${y}%`;
                }).join(",");
                const edgeLines = shaped
                    ? `<span style="position:absolute;display:block;inset:0;z-index:3;clip-path:polygon(${shapeClip})">${render_piece_edge_lines(piece)}</span>`
                    : render_piece_edge_lines(piece);

                html += `
                    <div class="dco-piece ${piece.piece_type === "Special" ? "dco-special-raw-piece" : ""} ${exactSpecial ? "dco-special-exact-piece" : ""} ${clipped ? "dco-clipped-corner-piece" : ""}" data-piece-type="${escape_html(piece.piece_type || "Regular")}" style="position:absolute;left:${left}%;top:${top}%;width:${width}%;height:${height}%;${pieceStyle}color:#111;overflow:hidden;padding:2px;font-size:10px;line-height:1.2;text-align:center;box-sizing:border-box;display:flex;align-items:center;justify-content:center;">
                        ${shapeOutline}
                        ${edgeLines}
                        ${render_piece_label(piece)}
                    </div>
                `;
            });

            html += "</div></div>";
        });

        if (plan.unplaced && plan.unplaced.length) {
            html += `<div style="border:1px solid #d9534f;background:#fff5f5;color:#a94442;padding:8px;border-radius:8px;margin-top:12px;"><b>تنبيه:</b> توجد ${plan.unplaced.length} قطعة لم تدخل ضمن الألواح. راجع المقاسات أو مقاس اللوح أو سماحية التدوير.</div>`;
        }

        html += "</div>";
        return html;
    }

    // =====================================================
    // Print cutting plan — dynamic A4 landscape, max 10 boards per page
    // =====================================================

    const MAX_SHEETS_PER_PAGE = 10;

    function planRootFromVisibleDom(frm) {
        const field = frm.fields_dict && frm.fields_dict.cutting_plan_html;
        const root = field && field.$wrapper && field.$wrapper.get(0);
        if (!root) return null;
        const planRoot = root.querySelector(".dco-cutting-plan");
        return planRoot ? planRoot.cloneNode(true) : null;
    }

    function planRootFromPlan(frm, plan) {
        if (!plan || !plan.sheets || !plan.sheets.length) return null;
        const holder = document.createElement("div");
        holder.innerHTML = build_cutting_plan_html(frm, plan);
        return holder.querySelector(".dco-cutting-plan");
    }

    function printGridColumns(count) {
        if (count <= 1) return 1;
        if (count <= 2) return 2;
        if (count <= 4) return 2;
        if (count <= 6) return 3;
        if (count <= 8) return 4;
        return 5;
    }

    function requestedPieceCount(frm) {
        return (frm.doc.pieces || []).reduce(
            (total, row) => total + Math.max(0, Math.floor(num(row.qty))),
            0
        );
    }

    function printBoardSize(frm, plan) {
        const width = num(plan && plan.full_board_width_cm) || num(frm.doc.board_width_cm);
        const length = num(plan && plan.full_board_length_cm) || num(frm.doc.board_length_cm);
        if (!width || !length) return "—";
        return `${round(width, 1)} × ${round(length, 1)} سم`;
    }

    function printContactsHtml(value) {
        const contacts = String(value || "")
            .split(/\r?\n/)
            .map(line => line.trim())
            .filter(Boolean);
        if (!contacts.length) return "";
        return `<div class="dco-print-factory-contacts">${contacts.map(contact => `<span>${escape_html(contact)}</span>`).join("")}</div>`;
    }

    function printFactoryIdentityHtml(identity) {
        const resolved = identity || {};
        return `<div class="dco-print-factory-identity">
            <div class="dco-print-factory-name">${escape_html(resolved.print_factory_name || "")}</div>
            <div class="dco-print-factory-description">${escape_html(resolved.print_factory_description || "")}</div>
            <div class="dco-print-factory-address">${escape_html(resolved.print_factory_address || "")}</div>
            ${printContactsHtml(resolved.print_factory_contacts)}
        </div>`;
    }

    function printOrderMetaHtml(frm, plan, totalSheets) {
        const items = [
            ["رقم الطلب", frm.doc.name || "—"],
            ["اسم الزبون", frm.doc.customer || "—"],
            ["لون اللوح", frm.doc.board_description || "—"],
            ["عدد الألواح", totalSheets],
            ["عدد القطع", requestedPieceCount(frm)],
            ["قياس اللوح", printBoardSize(frm, plan)],
        ];
        return `<div class="dco-print-order-meta">${items.map(([label, value]) => `
            <div><b>${escape_html(label)}</b><span>${escape_html(value)}</span></div>
        `).join("")}</div>`;
    }

    function boardAspectFromCards(cards, frm, plan) {
        const firstBoard = cards[0] && cards[0].querySelector(".dco-sheet-board");
        const renderedW = parseFloat(firstBoard && firstBoard.style.width);
        const renderedH = parseFloat(firstBoard && firstBoard.style.height);
        if (renderedW > 0 && renderedH > 0) return renderedH / renderedW;

        const width = num(plan && plan.usable_board_width_cm)
            || num(plan && plan.full_board_width_cm)
            || num(frm.doc.board_width_cm);
        const length = num(plan && plan.usable_board_length_cm)
            || num(plan && plan.full_board_length_cm)
            || num(frm.doc.board_length_cm);
        return width > 0 && length > 0 ? length / width : 2;
    }

    function sizeBoardsForPage(cards, frm, plan) {
        const count = cards.length;
        const cols = printGridColumns(count);
        const rows = Math.ceil(count / cols);
        const aspect = Math.max(0.15, boardAspectFromCards(cards, frm, plan));
        const pageGridWidthMm = 281;
        const pageGridHeightMm = 145;
        const columnGapMm = 2.4;
        const rowGapMm = 2.4;
        const titleHeightMm = 5.5;
        const cardHorizontalSpaceMm = 1.4;

        const widthLimit = (
            pageGridWidthMm
            - (cols - 1) * columnGapMm
            - cols * cardHorizontalSpaceMm
        ) / cols;
        const heightPerRow = (
            pageGridHeightMm
            - (rows - 1) * rowGapMm
        ) / Math.max(rows, 1);
        const heightLimit = Math.max(12, heightPerRow - titleHeightMm);
        const boardWmm = Math.max(8, Math.min(widthLimit, heightLimit / aspect));
        const boardHmm = boardWmm * aspect;

        cards.forEach((card, index) => {
            const board = card.querySelector(".dco-sheet-board");
            const title = card.querySelector(".dco-sheet-title");
            if (title) title.innerHTML = `<div class="dco-print-sheet-number">لوح ${index + 1}</div>`;
            if (board) {
                board.style.width = `${boardWmm}mm`;
                board.style.height = `${boardHmm}mm`;
                board.style.maxWidth = "100%";
                board.style.margin = "0 auto";
            }
            card.style.margin = "0";
            card.style.padding = ".6mm";
        });
        return { cols, rows };
    }

    function pageChunks(cards) {
        const chunks = [];
        for (let index = 0; index < cards.length; index += MAX_SHEETS_PER_PAGE) {
            chunks.push(cards.slice(index, index + MAX_SHEETS_PER_PAGE));
        }
        return chunks;
    }

    function buildPrintPages(frm, planRoot, plan, identity) {
        const sourceCards = [...planRoot.querySelectorAll(".dco-sheet-card")]
            .map(card => card.cloneNode(true));
        const totalSheets = sourceCards.length;
        const chunks = pageChunks(sourceCards);
        let globalBoardIndex = 0;

        return chunks.map((cards, pageIndex) => {
            const layout = sizeBoardsForPage(cards, frm, plan);
            const gridCards = cards.map(card => {
                const title = card.querySelector(".dco-sheet-title");
                globalBoardIndex += 1;
                if (title) title.innerHTML = `<div class="dco-print-sheet-number">لوح ${globalBoardIndex}</div>`;
                return card.outerHTML;
            }).join("");
            return `<section class="dco-print-page" data-page="${pageIndex + 1}">
                <header class="dco-print-header">
                    ${printFactoryIdentityHtml(identity)}
                    <div class="dco-print-document-title">
                        <h1>خطة القص</h1>
                        <span>صفحة ${pageIndex + 1} من ${chunks.length}</span>
                    </div>
                </header>
                ${printOrderMetaHtml(frm, plan, totalSheets)}
                <div class="dco-print-sheets-grid" style="--print-cols:${layout.cols};--print-rows:${layout.rows}">${gridCards}</div>
            </section>`;
        }).join("");
    }

    function buildPrintDocument(title, frm, planRoot, plan, identity) {
        const pages = buildPrintPages(frm, planRoot, plan, identity);
        return `<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<title>${escape_html(title)}</title>
<style>
@page { size: A4 landscape; margin: 6mm; }
* { box-sizing: border-box !important; }
html, body {
    margin: 0;
    padding: 0;
    background: #fff !important;
    color: #111 !important;
    font-family: Tahoma, Arial, sans-serif;
    direction: rtl;
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
}
.dco-print-page {
    width: 100%;
    min-height: 198mm;
    display: flex;
    flex-direction: column;
    break-after: page;
    page-break-after: always;
}
.dco-print-page:last-child {
    break-after: auto;
    page-break-after: auto;
}
.dco-print-header {
    display: grid;
    grid-template-columns: minmax(0, 1.7fr) minmax(45mm, .55fr);
    gap: 6mm;
    align-items: start;
    padding-bottom: 1.6mm;
    border-bottom: 1.2pt solid #111;
}
.dco-print-factory-identity { min-width: 0; text-align: right; line-height: 1.25; }
.dco-print-factory-name { font-size: 13pt; line-height: 1.05; font-weight: 950; }
.dco-print-factory-description { margin-top: .7mm; font-size: 6.8pt; font-weight: 800; }
.dco-print-factory-address { margin-top: .5mm; font-size: 6.4pt; font-weight: 650; }
.dco-print-factory-contacts { display: flex; flex-wrap: wrap; gap: .4mm 2.4mm; margin-top: .45mm; font-size: 6.2pt; font-weight: 700; }
.dco-print-factory-contacts span { white-space: nowrap; }
.dco-print-document-title { text-align: left; }
.dco-print-document-title h1 { margin: 0; font-size: 15pt; font-weight: 950; line-height: 1.1; }
.dco-print-document-title span { display: block; margin-top: 1mm; font-size: 6.5pt; color: #555; }
.dco-print-order-meta {
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 1.2mm;
    margin: 1.6mm 0 2mm;
}
.dco-print-order-meta > div {
    min-width: 0;
    padding: 1mm 1.2mm;
    border: .6pt solid #aab0b6;
    border-radius: 1.2mm;
    background: #fff;
    line-height: 1.15;
}
.dco-print-order-meta b { display: block; margin-bottom: .45mm; font-size: 5.7pt; color: #4d555c; }
.dco-print-order-meta span { display: block; font-size: 7.1pt; font-weight: 850; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dco-print-sheets-grid {
    flex: 1 1 auto;
    min-height: 0;
    display: grid;
    grid-template-columns: repeat(var(--print-cols, 1), minmax(0, 1fr));
    grid-template-rows: repeat(var(--print-rows, 1), minmax(0, 1fr));
    gap: 2.4mm;
    align-items: start;
    justify-items: center;
}
.dco-sheet-card {
    width: 100%;
    max-width: 100%;
    margin: 0 !important;
    padding: .6mm !important;
    border: 0 !important;
    border-radius: 0 !important;
    background: #fff !important;
    box-shadow: none !important;
    break-inside: avoid !important;
    page-break-inside: avoid !important;
}
.dco-sheet-title {
    display: block !important;
    margin: 0 0 .8mm !important;
    text-align: center !important;
    font-size: 9pt !important;
    font-weight: 950 !important;
    line-height: 1 !important;
}
.dco-print-sheet-number { text-align: center; }
.dco-sheet-board {
    position: relative !important;
    direction: ltr !important;
    display: block !important;
    border: 1.1pt solid #111 !important;
    background: #fff !important;
    overflow: hidden !important;
    box-shadow: none !important;
}
.dco-piece {
    overflow: hidden !important;
    background: #fff !important;
    border-color: #111 !important;
    color: #111 !important;
    box-shadow: none !important;
    padding: 0 !important;
}
.dco-special-exact-piece,
.dco-clipped-corner-piece { background: transparent !important; border: 0 !important; }
.dco-shaped-piece-outline polygon { fill: #fff !important; stroke: #111 !important; }
.dco-piece-label {
    direction: ltr !important;
    text-align: center !important;
    font-size: 6pt !important;
    line-height: 1 !important;
    color: #111 !important;
    white-space: nowrap !important;
}
.dco-piece-label span { background: transparent !important; color: #111 !important; border: 0 !important; padding: 0 !important; }
.dco-edge-line { border-color: #111 !important; }
@media print {
    a { color: inherit !important; text-decoration: none !important; }
}
</style>
</head>
<body>${pages}<script>window.onload=function(){setTimeout(function(){window.focus();window.print();},350);};<\/script></body>
</html>`;
    }

    async function print_cutting_plan(frm, planOverride = null) {
        const plan = planOverride || parse_plan(frm) || {};
        let planRoot = null;
        if (planOverride) {
            planRoot = planRootFromPlan(frm, planOverride);
        }
        if (!planRoot) {
            planRoot = planRootFromVisibleDom(frm);
        }
        if (!planRoot) {
            planRoot = planRootFromPlan(frm, plan);
        }
        if (!planRoot || !planRoot.querySelector(".dco-sheet-card")) {
            frappe.msgprint("لا يوجد مخطط قص للطباعة. اضغط أولًا على إعادة حساب خطة القص.");
            return false;
        }

        const title = "خطة قص - " + (frm.doc.name || "");
        const print_window = window.open("", "_blank");
        if (!print_window) {
            frappe.msgprint("المتصفح منع فتح نافذة الطباعة. اسمح بالنوافذ المنبثقة ثم جرّب مرة أخرى.");
            return false;
        }

        print_window.document.open();
        print_window.document.write('<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>جاري تجهيز خطة القص…</title></head><body style="font-family:Tahoma,Arial,sans-serif;direction:rtl;padding:24px">جاري تجهيز خطة القص للطباعة…</body></html>');
        print_window.document.close();

        try {
            const identityApi = window.AlmdinaFactoryPrintIdentity;
            const identity = identityApi && typeof identityApi.get === "function"
                ? await identityApi.get()
                : (identityApi && typeof identityApi.fallback === "function" ? identityApi.fallback() : {});
            print_window.document.open();
            print_window.document.write(buildPrintDocument(title, frm, planRoot, plan, identity));
            print_window.document.close();
            return true;
        } catch (error) {
            console.error("Cutting plan print preparation failed", error);
            try { print_window.close(); } catch (closeError) { /* ignored */ }
            frappe.msgprint("تعذر تجهيز خطة القص للطباعة. أعد تحميل الصفحة ثم حاول مرة أخرى.");
            return false;
        }
    }

    window.AlmdinaCuttingPlanRender = {
        build: build_cutting_plan_html,
        parse: parse_plan,
        print: print_cutting_plan,
    };
})();
