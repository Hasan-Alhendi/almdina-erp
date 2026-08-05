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
    // Print cutting plan — screen header + all sheets on one A4
    // =====================================================

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

    function layoutPlanForSingleA4(planRoot) {
        const sheets = [...planRoot.querySelectorAll(".dco-sheet-card")];
        const count = sheets.length;
        if (!count) return planRoot;

        const sheetsWrap = document.createElement("div");
        sheetsWrap.className = "dco-print-sheets-grid";

        sheets.forEach(card => {
            if (card.parentNode) card.parentNode.removeChild(card);
            sheetsWrap.appendChild(card);
        });
        planRoot.appendChild(sheetsWrap);

        const cols = count === 1 ? 1 : count <= 4 ? 2 : count <= 9 ? 3 : 4;
        sheetsWrap.style.setProperty("--print-cols", String(cols));

        const firstBoard = sheets[0].querySelector(".dco-sheet-board");
        const origW = parseFloat(firstBoard && firstBoard.style.width) || 560;
        const origH = parseFloat(firstBoard && firstBoard.style.height) || 260;
        const aspect = origH / Math.max(origW, 1);

        const gridMaxW = 194;
        const gridMaxH = 138;
        const gap = 3;
        const rows = Math.ceil(count / cols);

        let boardWmm = (gridMaxW - (cols - 1) * gap) / cols - 6;
        let boardHmm = boardWmm * aspect;
        const rowHmm = boardHmm + 14;
        let totalHmm = rows * rowHmm + (rows - 1) * gap;

        if (totalHmm > gridMaxH) {
            const shrink = gridMaxH / totalHmm;
            boardWmm *= shrink;
            boardHmm *= shrink;
        }

        sheets.forEach(card => {
            const board = card.querySelector(".dco-sheet-board");
            if (!board) return;
            board.style.width = `${boardWmm}mm`;
            board.style.height = `${boardHmm}mm`;
            board.style.maxWidth = "100%";
            board.style.margin = "0 auto";
            card.style.margin = "0";
            card.style.padding = "2mm";
        });

        return planRoot;
    }

    function buildPrintDocument(title, planRoot) {
        layoutPlanForSingleA4(planRoot);
        planRoot.classList.add("dco-print-plan-single");

        return `<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<title>${escape_html(title)}</title>
<style>
@page { size: A4 portrait; margin: 8mm; }
* { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; box-sizing: border-box !important; }
html, body {
    margin: 0;
    padding: 0;
    background: #fff !important;
    color: #111 !important;
    font-family: Arial, Tahoma, sans-serif;
    direction: rtl;
}
.dco-print-plan-single {
    width: 100%;
    margin: 0;
    padding: 0;
    background: #fff;
    page-break-inside: avoid !important;
    break-inside: avoid !important;
}
.dco-print-plan-single h2 {
    margin: 0 0 4px 0 !important;
    font-size: 16px !important;
}
.dco-print-plan-single .dco-plan-header-cards {
    grid-template-columns: repeat(5, minmax(0, 1fr)) !important;
    gap: 2mm !important;
    margin: 2mm 0 3mm 0 !important;
}
.dco-print-plan-single .dco-plan-header-card {
    padding: 2mm 2.5mm !important;
    border-radius: 6px !important;
}
.dco-print-plan-single .dco-plan-header-card b {
    font-size: 7.5px !important;
    margin-bottom: 1mm !important;
}
.dco-print-plan-single .dco-plan-header-card span {
    font-size: 9px !important;
    line-height: 1.25 !important;
}
.dco-print-plan-single .dco-summary-grid {
    gap: 4px !important;
    margin: 4px 0 6px 0 !important;
}
.dco-print-plan-single .dco-summary-card {
    padding: 4px 6px !important;
    font-size: 10px !important;
}
.dco-print-plan-single .dco-piece-groups,
.dco-print-plan-single .dco-special-raw-coverage {
    margin: 4px 0 6px 0 !important;
    padding: 4px 6px !important;
    font-size: 10px !important;
    line-height: 1.5 !important;
}
.dco-print-sheets-grid {
    display: grid;
    grid-template-columns: repeat(var(--print-cols, 1), 1fr);
    gap: 3mm;
    align-items: start;
    margin-top: 4px;
}
.dco-sheet-card {
    width: 100%;
    max-width: 100%;
    margin: 0 !important;
    border: 1px solid #bbb !important;
    border-radius: 8px !important;
    background: #fff !important;
    page-break-inside: avoid !important;
    break-inside: avoid !important;
}
.dco-sheet-title {
    display: flex !important;
    justify-content: space-between !important;
    gap: 6px !important;
    margin-bottom: 4px !important;
    font-size: 10px !important;
    font-weight: bold !important;
}
.dco-sheet-board {
    position: relative !important;
    direction: ltr !important;
    display: block !important;
    border: 2px solid #111 !important;
    background:
        linear-gradient(90deg, rgba(0,0,0,.05) 1px, transparent 1px),
        linear-gradient(rgba(0,0,0,.05) 1px, transparent 1px),
        #fff !important;
    background-size: 32px 32px !important;
    overflow: hidden !important;
}
.dco-piece { overflow: hidden !important; }
.dco-piece-label { direction: ltr !important; text-align: center !important; font-size: 8px !important; line-height: 1.1 !important; }
.dco-edge-line { border-color: #d00000 !important; }
</style>
</head>
<body>${planRoot.outerHTML}<script>window.onload=function(){setTimeout(function(){window.focus();window.print();},400);};<\/script></body>
</html>`;
    }

    function print_cutting_plan(frm, planOverride = null) {
        let planRoot = null;
        if (planOverride) {
            planRoot = planRootFromPlan(frm, planOverride);
        }
        if (!planRoot) {
            planRoot = planRootFromVisibleDom(frm);
        }
        if (!planRoot) {
            planRoot = planRootFromPlan(frm, parse_plan(frm));
        }
        if (!planRoot || !planRoot.querySelector(".dco-sheet-card")) {
            frappe.msgprint("لا يوجد مخطط قص للطباعة. اضغط أولًا على إعادة حساب خطة القص.");
            return;
        }

        const title = "خطة قص - " + (frm.doc.name || "");
        const print_window = window.open("", "_blank");
        if (!print_window) {
            frappe.msgprint("المتصفح منع فتح نافذة الطباعة. اسمح بالنوافذ المنبثقة ثم جرّب مرة أخرى.");
            return;
        }

        print_window.document.open();
        print_window.document.write(buildPrintDocument(title, planRoot));
        print_window.document.close();
    }

    window.AlmdinaCuttingPlanRender = {
        build: build_cutting_plan_html,
        parse: parse_plan,
        print: print_cutting_plan,
    };
})();
