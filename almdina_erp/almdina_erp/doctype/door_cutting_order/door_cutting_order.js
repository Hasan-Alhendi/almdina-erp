(() => {
    "use strict";

    const PREVIEW_METHOD = "almdina_erp.almdina_erp.api.preview_door_cutting_order";

    const PACKING_OPTIONS = [
        "Auto",
        "MaxRects Best Short Side",
        "MaxRects Best Area",
        "MaxRects Bottom Left",
        "MaxRects Contact Point",
        "MaxRects Width",
        "MaxRects Length",
        "Shelf Horizontal",
        "Shelf Vertical",
        "Shelf First Fit",
        "Shelf Next Fit",
        "Guillotine Short Axis",
        "Guillotine Long Axis",
        "Guillotine Best Area Fit",
        "Guillotine Best Short Side Fit",
        "Guillotine Best Long Side Fit",
        "Skyline Bottom Left",
        "Skyline Best Fit"
    ];

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

    function set_preview_value(frm, fieldname, value) {
        frm.doc[fieldname] = value;
        frm.refresh_field(fieldname);
    }

    function apply_preview_result(frm, data) {
        if (!data) return;

        [
            "board_material",
            "board_color",
            "board_thickness_mm",
            "full_board_length_mm",
            "full_board_width_mm",
            "total_area_m2",
            "total_edge_meters",
            "required_boards",
            "waste_area_m2",
            "waste_percent",
            "mdf_cost_usd",
            "cutting_cost_usd",
            "edge_cost_usd",
            "total_cost_usd",
            "packing_method",
            "packing_score",
            "engine_version",
            "cutting_plan_json"
        ].forEach(fieldname => {
            if (Object.prototype.hasOwnProperty.call(data, fieldname)) {
                set_preview_value(frm, fieldname, data[fieldname]);
            }
        });

        (frm.doc.pieces || []).forEach((row, index) => {
            const calculated = (data.pieces || [])[index] || {};
            row.piece_no = calculated.piece_no || (index + 1);
            row.area_m2 = num(calculated.area_m2);
            row.edge_meters = num(calculated.edge_meters);
            row.edge_rate_usd = num(calculated.edge_rate_usd);
            row.edge_cost_usd = num(calculated.edge_cost_usd);
        });

        frm.refresh_field("pieces");
        render_cutting_plan(frm);
    }

    function recalculate_order(frm, options = {}) {
        const immediate = Boolean(options.immediate);
        const quiet = Boolean(options.quiet);

        frm._dco_calc_version = (frm._dco_calc_version || 0) + 1;
        const calc_version = frm._dco_calc_version;

        if (frm._dco_calc_timer) {
            clearTimeout(frm._dco_calc_timer);
            frm._dco_calc_timer = null;
        }

        const execute = () => new Promise((resolve, reject) => {
            frappe.call({
                method: PREVIEW_METHOD,
                args: {
                    doc: JSON.stringify(frm.doc)
                },
                freeze: false,
                callback(r) {
                    if (calc_version !== frm._dco_calc_version) {
                        resolve(null);
                        return;
                    }

                    apply_preview_result(frm, r.message || {});
                    resolve(r.message || {});
                },
                error(error) {
                    if (!quiet) {
                        console.error(error);
                    }
                    reject(error);
                }
            });
        });

        if (immediate) return execute();

        return new Promise((resolve, reject) => {
            frm._dco_calc_timer = setTimeout(() => {
                frm._dco_calc_timer = null;
                execute().then(resolve).catch(reject);
            }, 220);
        });
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
        return `
            <div class="dco-piece-label" style="position:relative;z-index:4;direction:ltr;text-align:center;">
                <b>${escape_html(piece.label)}</b><br>
                <span>${round(piece.original_w, 1)}*${round(piece.original_h, 1)} سم</span>
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
            html += `
                <span style="display:inline-block;margin-left:16px;white-space:nowrap;">
                    ${index + 1}- ${round(row.width_cm, 1)}*${round(row.length_cm, 1)} عدد ${Math.max(0, Math.floor(num(row.qty)))}
                </span>
            `;
        });

        html += "</div>";
        return html;
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
                <div style="line-height:1.7;margin-bottom:8px;font-size:12px;">
                    <b>الطلب:</b> ${escape_html(frm.doc.name || "")} &nbsp; | &nbsp;
                    <b>الزبون:</b> ${escape_html(frm.doc.customer || "")} &nbsp; | &nbsp;
                    <b>اللوح:</b> <span dir="ltr">${escape_html(frm.doc.board_item || "")}</span><br>
                    <b>مقاس اللوح الكامل:</b> ${round(full_board_w_cm, 1)} × ${round(full_board_h_cm, 1)} سم &nbsp; | &nbsp;
                    <b>المقاس المستخدم بعد التشذيب:</b> ${round(board_w_cm, 1)} × ${round(board_h_cm, 1)} سم &nbsp; | &nbsp;
                    <b>سماكة القص:</b> ${round(kerf_cm * 10, 1)} مم &nbsp; | &nbsp;
                    <b>هامش التشذيب:</b> ${round(trim_cm * 10, 1)} مم
                </div>

                <div class="dco-summary-grid" style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:8px 0 12px 0;">
                    <div class="dco-summary-card" style="border:1px solid #ddd;border-radius:8px;padding:8px;background:#f8fafc;"><b>عدد الألواح</b><span>${plan.sheets.length}</span></div>
                    <div class="dco-summary-card" style="border:1px solid #ddd;border-radius:8px;padding:8px;background:#f8fafc;"><b>مساحة القطع</b><span>${used_area_m2} م²</span></div>
                    <div class="dco-summary-card" style="border:1px solid #ddd;border-radius:8px;padding:8px;background:#f8fafc;"><b>مساحة الهدر</b><span>${waste_area_m2} م²</span></div>
                    <div class="dco-summary-card" style="border:1px solid #ddd;border-radius:8px;padding:8px;background:#f8fafc;"><b>نسبة الهدر</b><span>${waste_percent}%</span></div>
                </div>

                ${render_piece_groups_summary(frm)}

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

                html += `
                    <div class="dco-piece" style="position:absolute;left:${left}%;top:${top}%;width:${width}%;height:${height}%;border:1px solid #111;background:#e4f5ff;color:#111;overflow:hidden;padding:2px;font-size:10px;line-height:1.2;text-align:center;box-sizing:border-box;display:flex;align-items:center;justify-content:center;">
                        ${render_piece_edge_lines(piece)}
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

    function render_cutting_plan(frm) {
        const plan = parse_plan(frm);
        const wrapper = frm.fields_dict.cutting_plan_html && frm.fields_dict.cutting_plan_html.$wrapper;
        if (!wrapper) return;

        if (!plan || !plan.sheets || !plan.sheets.length) {
            wrapper.empty();
            return;
        }

        wrapper.html(build_cutting_plan_html(frm, plan));
    }

    // =====================================================
    // Print cutting plan
    // =====================================================

    function print_cutting_plan(frm) {
        const plan = parse_plan(frm);
        if (!plan || !plan.sheets || !plan.sheets.length) {
            frappe.msgprint("لا يوجد مخطط قص للطباعة. اضغط أولًا على إعادة حساب خطة القص.");
            return;
        }

        const plan_html = build_cutting_plan_html(frm, plan);
        const title = "خطة قص - " + (frm.doc.name || "");
        const print_window = window.open("", "_blank");

        if (!print_window) {
            frappe.msgprint("المتصفح منع فتح نافذة الطباعة. اسمح بالنوافذ المنبثقة ثم جرّب مرة أخرى.");
            return;
        }

        print_window.document.open();
        print_window.document.write(`
            <!DOCTYPE html>
            <html lang="ar" dir="rtl">
            <head>
                <meta charset="UTF-8">
                <title>${escape_html(title)}</title>
                <style>
                    @page { size:A4 portrait; margin:6mm; }
                    * { -webkit-print-color-adjust:exact !important; print-color-adjust:exact !important; box-sizing:border-box !important; }
                    html,body { margin:0;padding:0;background:#fff !important;color:#111 !important;font-family:Arial,Tahoma,sans-serif;direction:rtl; }
                    body { padding:5mm; }
                    .print-header { display:flex;justify-content:space-between;align-items:flex-start;border-bottom:2px solid #111;padding-bottom:5px;margin-bottom:6px;page-break-after:avoid; }
                    .print-title { font-size:18px;font-weight:bold;margin-bottom:4px; }
                    .print-info { font-size:10px;line-height:1.5; }
                    .print-info-ltr { direction:ltr;text-align:left; }
                    .dco-cutting-plan { color:#111 !important;background:#fff !important;padding:0 !important;margin:0 !important;font-family:Arial,Tahoma,sans-serif !important;font-size:10px !important; }
                    .dco-cutting-plan h2 { display:none !important; }
                    .dco-cutting-plan > div:first-of-type { font-size:10px !important;line-height:1.35 !important;margin-bottom:4px !important; }
                    .dco-summary-grid { display:grid !important;grid-template-columns:repeat(4,1fr) !important;gap:4px !important;margin:4px 0 6px 0 !important; }
                    .dco-summary-card { border:1px solid #aaa !important;border-radius:4px !important;padding:4px !important;background:#f8f8f8 !important;font-size:9px !important; }
                    .dco-summary-card b { display:block !important;font-size:8px !important;color:#444 !important;margin-bottom:2px !important; }
                    .dco-summary-card span { font-size:11px !important;font-weight:bold !important;color:#111 !important; }
                    .dco-sheet-card { border:1px solid #777 !important;border-radius:5px !important;padding:5px !important;margin:7px 0 0 0 !important;background:#fff !important;page-break-inside:avoid !important;break-inside:avoid !important;zoom:.68; }
                    .dco-sheet-card + .dco-sheet-card { page-break-before:always !important;break-before:page !important; }
                    .dco-sheet-title { display:flex !important;justify-content:space-between !important;align-items:center !important;font-size:11px !important;font-weight:bold !important;margin-bottom:4px !important; }
                    .dco-sheet-board { border:2px solid #111 !important;background:linear-gradient(90deg,rgba(0,0,0,.05) 1px,transparent 1px),linear-gradient(rgba(0,0,0,.05) 1px,transparent 1px),#fff !important;background-size:32px 32px !important;overflow:hidden !important;direction:ltr !important;margin:0 auto 5px auto !important; }
                    .dco-piece { border:1px solid #111 !important;background:#e4f5ff !important;color:#111 !important;font-size:8px !important;line-height:1.1 !important;padding:1px !important;display:flex !important;align-items:center !important;justify-content:center !important; }
                    .dco-piece-label { direction:ltr !important;text-align:center !important;color:#111 !important; }
                    .dco-piece b { font-size:9px !important;font-weight:bold !important; }
                    .dco-piece span,.dco-piece small { font-size:8px !important; }
                    .dco-edge-line { border-color:#d00000 !important; }
                    @media print { .no-print { display:none !important; } a[href]:after { content:"" !important; } }
                </style>
            </head>
            <body>
                <div class="print-header">
                    <div>
                        <div class="print-title">خطة قص</div>
                        <div class="print-info">رقم الطلب: ${escape_html(frm.doc.name || "")}<br>الزبون: ${escape_html(frm.doc.customer || "")}<br>نوع اللوح: <span dir="ltr">${escape_html(frm.doc.board_item || "")}</span></div>
                    </div>
                    <div class="print-info print-info-ltr">${frappe.datetime.now_datetime()}<br>ERPNext Cutting Plan</div>
                </div>
                ${plan_html}
                <script>window.onload=function(){setTimeout(function(){window.focus();window.print();},700);};<\/script>
            </body>
            </html>
        `);
        print_window.document.close();
    }

    // =====================================================
    // Measurement print
    // =====================================================

    function edge_measure_html(value, edge_count) {
        const safe_value = escape_html(round(value, 1));
        let border_style = "border-bottom:none;";
        if (edge_count === 1) border_style = "border-bottom:1.8px solid #111;";
        if (edge_count >= 2) border_style = "border-bottom:3px double #111;";

        return `<span style="display:inline-block;min-width:28px;padding:0 2px 2px 2px;${border_style}">${safe_value}</span>`;
    }

    function print_measurements_table(frm) {
        const rows = (frm.doc.pieces || []).filter(row => num(row.width_cm) || num(row.length_cm) || num(row.qty));
        if (!rows.length) {
            frappe.msgprint("لا يوجد قياسات للطباعة.");
            return;
        }

        const title = "جدول القياسات - " + (frm.doc.name || "");
        const print_window = window.open("", "_blank");
        if (!print_window) {
            frappe.msgprint("المتصفح منع فتح نافذة الطباعة. اسمح بالنوافذ المنبثقة ثم جرّب مرة أخرى.");
            return;
        }

        let table_rows_html = "";
        rows.forEach((row, index) => {
            const length_edge_count = (row.edge_long_right ? 1 : 0) + (row.edge_long_left ? 1 : 0);
            const width_edge_count = (row.edge_width_top ? 1 : 0) + (row.edge_width_bottom ? 1 : 0);
            table_rows_html += `
                <tr>
                    <td>${index + 1}</td>
                    <td>${edge_measure_html(row.width_cm, width_edge_count)}</td>
                    <td>${edge_measure_html(row.length_cm, length_edge_count)}</td>
                    <td>${Math.max(0, Math.floor(num(row.qty)))}</td>
                    <td class="notes-cell">${escape_html(row.notes || "")}</td>
                    <td>${row.allow_rotation ? "نعم" : "لا"}</td>
                </tr>
            `;
        });

        print_window.document.open();
        print_window.document.write(`
            <!DOCTYPE html>
            <html lang="ar" dir="rtl">
            <head>
                <meta charset="UTF-8">
                <title>${escape_html(title)}</title>
                <style>
                    @page { size:A4 portrait; margin:8mm; }
                    * { box-sizing:border-box;-webkit-print-color-adjust:exact !important;print-color-adjust:exact !important; }
                    html,body { margin:0;padding:0;background:#fff;color:#111;font-family:Arial,Tahoma,sans-serif;direction:rtl; }
                    .measurement-print-box { width:100mm;max-width:100mm;margin:0 auto; }
                    .print-header { display:flex;justify-content:space-between;align-items:flex-start;border-bottom:1.5px solid #111;padding-bottom:4px;margin-bottom:6px;gap:6px; }
                    .title { font-size:15px;font-weight:bold;margin-bottom:3px; }
                    .info { font-size:8.5px;line-height:1.45; }
                    .info-ltr { direction:ltr;text-align:left; }
                    table { width:100%;border-collapse:collapse;table-layout:fixed;font-size:8.5px; }
                    th,td { border:1px solid #111;padding:3px 2px;text-align:center;vertical-align:middle;overflow-wrap:anywhere; }
                    th { font-weight:bold;background:#f3f3f3; }
                    .notes-cell { text-align:right;white-space:pre-wrap; }
                    .legend { margin-top:6px;font-size:8px;line-height:1.7; }
                    .one-line { border-bottom:1.8px solid #111;padding-bottom:2px; }
                    .two-lines { border-bottom:3px double #111;padding-bottom:2px; }
                </style>
            </head>
            <body>
                <div class="measurement-print-box">
                    <div class="print-header">
                        <div>
                            <div class="title">جدول القياسات</div>
                            <div class="info">رقم الطلب: ${escape_html(frm.doc.name || "")}<br>الزبون: ${escape_html(frm.doc.customer || "")}<br>نوع اللوح: <span dir="ltr">${escape_html(frm.doc.board_item || "")}</span></div>
                        </div>
                        <div class="info info-ltr">${frappe.datetime.now_datetime()}<br>Measurements Table</div>
                    </div>
                    <table>
                        <thead><tr><th style="width:12%;">رقم</th><th style="width:16%;">العرض</th><th style="width:16%;">الطول</th><th style="width:10%;">عدد</th><th style="width:34%;">ملاحظات</th><th style="width:12%;">تدوير</th></tr></thead>
                        <tbody>${table_rows_html}</tbody>
                    </table>
                    <div class="legend"><b>دلالة خطوط القشاط:</b><br><span class="one-line">قياس</span> = قشاط على طرف واحد<br><span class="two-lines">قياس</span> = قشاط على طرفين<br>بدون خط = لا يوجد قشاط على هذا القياس</div>
                </div>
                <script>window.onload=function(){setTimeout(function(){window.focus();window.print();},500);};<\/script>
            </body>
            </html>
        `);
        print_window.document.close();
    }

    // =====================================================
    // DXF R12 export
    // =====================================================

    function dxf_num(value) {
        const n = Number(value);
        if (!isFinite(n)) return "0";
        return String(Math.round(n * 1000) / 1000);
    }

    function dxf_pair(code, value) {
        return String(code) + "\r\n" + String(value) + "\r\n";
    }

    function dxf_layer(name, color) {
        return dxf_pair(0, "LAYER") + dxf_pair(2, name) + dxf_pair(70, 0) + dxf_pair(62, color) + dxf_pair(6, "CONTINUOUS");
    }

    function dxf_ltype_continuous() {
        return dxf_pair(0, "LTYPE") + dxf_pair(2, "CONTINUOUS") + dxf_pair(70, 0) + dxf_pair(3, "Solid line") + dxf_pair(72, 65) + dxf_pair(73, 0) + dxf_pair(40, 0);
    }

    function dxf_polyline_rect(layer, x, y, w, h) {
        const points = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];
        let dxf = dxf_pair(0, "POLYLINE") + dxf_pair(8, layer || "CUT_PATH") + dxf_pair(66, 1) + dxf_pair(10, 0) + dxf_pair(20, 0) + dxf_pair(30, 0) + dxf_pair(70, 1);
        points.forEach(point => {
            dxf += dxf_pair(0, "VERTEX") + dxf_pair(8, layer || "CUT_PATH") + dxf_pair(10, dxf_num(point[0])) + dxf_pair(20, dxf_num(point[1])) + dxf_pair(30, 0);
        });
        dxf += dxf_pair(0, "SEQEND") + dxf_pair(8, layer || "CUT_PATH");
        return dxf;
    }

    function make_dxf_document(entities, extmin_x, extmin_y, extmax_x, extmax_y) {
        let dxf = "";
        dxf += dxf_pair(0, "SECTION") + dxf_pair(2, "HEADER");
        dxf += dxf_pair(9, "$ACADVER") + dxf_pair(1, "AC1009");
        dxf += dxf_pair(9, "$INSUNITS") + dxf_pair(70, 4);
        dxf += dxf_pair(9, "$EXTMIN") + dxf_pair(10, dxf_num(extmin_x)) + dxf_pair(20, dxf_num(extmin_y)) + dxf_pair(30, 0);
        dxf += dxf_pair(9, "$EXTMAX") + dxf_pair(10, dxf_num(extmax_x)) + dxf_pair(20, dxf_num(extmax_y)) + dxf_pair(30, 0);
        dxf += dxf_pair(0, "ENDSEC");
        dxf += dxf_pair(0, "SECTION") + dxf_pair(2, "TABLES");
        dxf += dxf_pair(0, "TABLE") + dxf_pair(2, "LTYPE") + dxf_pair(70, 1) + dxf_ltype_continuous() + dxf_pair(0, "ENDTAB");
        dxf += dxf_pair(0, "TABLE") + dxf_pair(2, "LAYER") + dxf_pair(70, 3) + dxf_layer("0", 7) + dxf_layer("SHEET_OUTLINE", 8) + dxf_layer("CUT_PATH", 1) + dxf_pair(0, "ENDTAB");
        dxf += dxf_pair(0, "ENDSEC");
        dxf += dxf_pair(0, "SECTION") + dxf_pair(2, "BLOCKS") + dxf_pair(0, "ENDSEC");
        dxf += dxf_pair(0, "SECTION") + dxf_pair(2, "ENTITIES") + (entities || "") + dxf_pair(0, "ENDSEC");
        dxf += dxf_pair(0, "EOF");
        return dxf;
    }

    function download_text_file(filename, content, mime_type) {
        const blob = new Blob([content], { type: mime_type || "application/octet-stream" });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = filename;
        document.body.appendChild(anchor);
        anchor.click();
        setTimeout(() => {
            document.body.removeChild(anchor);
            URL.revokeObjectURL(url);
        }, 500);
    }

    function export_cutting_plan_dxf(frm) {
        const plan = parse_plan(frm);
        if (!plan || !plan.sheets || !plan.sheets.length) {
            frappe.msgprint("لم يتم توليد خطة قص صالحة للتصدير.");
            return;
        }

        const full_board_width_mm = num(plan.full_board_width_cm) * 10;
        const full_board_length_mm = num(plan.full_board_length_cm) * 10;
        const trim_mm = num(plan.trim_cm) * 10;
        const SHEETS_PER_ROW = 2;
        const SHEET_GAP_MM = 200;
        const EXPORT_SHEET_OUTLINE = true;
        let entities = "";
        let extmin_x = 0;
        let extmin_y = 0;
        let extmax_x = 0;
        let extmax_y = 0;

        plan.sheets.forEach((sheet, index) => {
            const col = index % SHEETS_PER_ROW;
            const row_index = Math.floor(index / SHEETS_PER_ROW);
            const sheet_offset_x = col * (full_board_width_mm + SHEET_GAP_MM);
            const sheet_offset_y = row_index * (full_board_length_mm + SHEET_GAP_MM);

            extmax_x = Math.max(extmax_x, sheet_offset_x + full_board_width_mm);
            extmax_y = Math.max(extmax_y, sheet_offset_y + full_board_length_mm);

            if (EXPORT_SHEET_OUTLINE) {
                entities += dxf_polyline_rect("SHEET_OUTLINE", sheet_offset_x, sheet_offset_y, full_board_width_mm, full_board_length_mm);
            }

            (sheet.pieces || []).forEach(piece => {
                const piece_w_mm = num(piece.w) * 10;
                const piece_h_mm = num(piece.h) * 10;
                const x_mm = sheet_offset_x + trim_mm + (num(piece.x) * 10);
                const y_mm = sheet_offset_y + full_board_length_mm - trim_mm - (num(piece.y) * 10) - piece_h_mm;
                entities += dxf_polyline_rect("CUT_PATH", x_mm, y_mm, piece_w_mm, piece_h_mm);
            });
        });

        const dxf = make_dxf_document(entities, extmin_x, extmin_y, extmax_x, extmax_y);
        const filename = "cutting_plan_" + String(frm.doc.name || "door_cutting_order").replace(/[^\w\-]+/g, "_") + ".dxf";
        download_text_file(filename, dxf, "application/octet-stream");
        frappe.show_alert({ message: "تم تصدير ملف DXF بنجاح. افتح طبقة CUT_PATH للقص وطبقة SHEET_OUTLINE للمعاينة فقط.", indicator: "green" });
    }

    // =====================================================
    // Excel-like pieces grid UX
    // =====================================================

    function focus_grid_cell($row, fieldname) {
        if (!$row || !$row.length) return;
        let $cell = $row.find(`[data-fieldname="${fieldname}"]`).first();
        if (!$cell.length) $cell = $row.find('[data-fieldname="width_cm"]').first();
        if (!$cell.length) $cell = $row.find("[data-fieldname]").first();
        if (!$cell.length) return;

        $cell.click();
        setTimeout(() => {
            const $input = $row.find("input:visible, textarea:visible, select:visible").first();
            if ($input.length) {
                $input.focus();
                if ($input.is("input")) $input.select();
            }
        }, 120);
    }

    function setup_pieces_excel_ux(frm) {
        if (!frm.fields_dict.pieces || !frm.fields_dict.pieces.grid) return;
        const grid = frm.fields_dict.pieces.grid;
        const $grid_wrapper = $(grid.wrapper);

        if (!document.getElementById("dco-pieces-excel-ux-css")) {
            $("head").append(`
                <style id="dco-pieces-excel-ux-css">
                    .dco-wide-form .layout-main-section,.dco-wide-form .layout-main-section-wrapper,.dco-wide-form .form-page,.dco-wide-form .form-layout{max-width:none!important;width:100%!important}
                    .dco-pieces-wide-control{width:100%!important;max-width:none!important;flex:0 0 100%!important;grid-column:1/-1!important}
                    .dco-pieces-wide-control .grid-body{overflow-x:auto!important}
                    .dco-pieces-wide-control .grid-row,.dco-pieces-wide-control .grid-heading-row{min-width:980px!important}
                    .dco-pieces-wide-control .grid-static-col,.dco-pieces-wide-control .grid-input{font-size:13px!important}
                    .dco-pieces-wide-control .grid-row td,.dco-pieces-wide-control .grid-static-col{padding:5px 4px!important}
                    .dco-pieces-wide-control [data-fieldname="width_cm"],.dco-pieces-wide-control [data-fieldname="length_cm"]{width:92px!important;min-width:92px!important;max-width:92px!important}
                    .dco-pieces-wide-control [data-fieldname="qty"]{width:62px!important;min-width:62px!important;max-width:62px!important}
                    .dco-pieces-wide-control [data-fieldname="edge_long_right"],.dco-pieces-wide-control [data-fieldname="edge_long_left"],.dco-pieces-wide-control [data-fieldname="edge_width_top"],.dco-pieces-wide-control [data-fieldname="edge_width_bottom"],.dco-pieces-wide-control [data-fieldname="allow_rotation"]{width:66px!important;min-width:66px!important;max-width:66px!important;text-align:center!important}
                    .dco-pieces-wide-control [data-fieldname="area_m2"],.dco-pieces-wide-control [data-fieldname="edge_meters"],.dco-pieces-wide-control [data-fieldname="edge_rate_usd"],.dco-pieces-wide-control [data-fieldname="edge_cost_usd"]{width:82px!important;min-width:82px!important;max-width:82px!important}
                    .dco-pieces-wide-control [data-fieldname="edge_type"]{width:135px!important;min-width:135px!important;max-width:135px!important}
                    .dco-pieces-wide-control [data-fieldname="notes"]{width:150px!important;min-width:150px!important;max-width:150px!important}
                </style>
            `);
        }

        $(frm.wrapper).addClass("dco-wide-form");
        $grid_wrapper.closest(".frappe-control").addClass("dco-pieces-wide-control");
        $grid_wrapper.off("keydown.dco_enter_add_row");

        $grid_wrapper.on("keydown.dco_enter_add_row", "input, textarea, select", function (e) {
            if (e.key !== "Enter") return;
            if ($(e.target).is("textarea") && e.shiftKey) return;

            e.preventDefault();
            e.stopPropagation();
            $(e.target).trigger("change");

            const $current_row = $(e.target).closest(".grid-row");
            const $rows = $grid_wrapper.find(".grid-row:visible").filter(function () {
                return $(this).find("[data-fieldname]").length > 0;
            });
            const current_index = $rows.index($current_row);
            const is_last_row = current_index === $rows.length - 1;
            const current_fieldname = $(e.target).closest("[data-fieldname]").attr("data-fieldname") || "width_cm";

            if (!is_last_row && current_index >= 0) {
                focus_grid_cell($rows.eq(current_index + 1), current_fieldname);
                return;
            }

            grid.add_new_row();
            frm.refresh_field("pieces");
            setTimeout(() => {
                const $new_rows = $grid_wrapper.find(".grid-row:visible").filter(function () {
                    return $(this).find("[data-fieldname]").length > 0;
                });
                focus_grid_cell($new_rows.last(), "width_cm");
                recalculate_order(frm, { quiet: true }).catch(() => {});
            }, 250);
        });
    }

    function add_buttons(frm) {
        if (frm._dco_added_buttons) return;

        frm.add_custom_button("إعادة حساب خطة القص", () => {
            recalculate_order(frm, { immediate: true }).then(() => {
                frappe.show_alert({ message: "تمت إعادة حساب خطة القص.", indicator: "green" });
            }).catch(() => {});
        });

        frm.add_custom_button("إلغاء تخصيص قشاط الدرف", () => {
            (frm.doc.pieces || []).forEach(row => {
                frappe.model.set_value(row.doctype, row.name, "edge_type", "");
            });
            frm.refresh_field("pieces");
            recalculate_order(frm, { immediate: true }).then(() => {
                frappe.show_alert({ message: "تم إلغاء تخصيص القشاط. كل الدرف الآن تعتمد على القشاط الرئيسي.", indicator: "green" });
            }).catch(() => {});
        });

        frm.add_custom_button("طباعة خطة القص", () => print_cutting_plan(frm));
        frm.add_custom_button("طباعة جدول القياسات", () => print_measurements_table(frm));
        frm.add_custom_button("تصدير DXF", () => {
            recalculate_order(frm, { immediate: true }).then(() => export_cutting_plan_dxf(frm)).catch(() => {});
        });

        frm._dco_added_buttons = true;
    }

    function schedule_recalculate(frm) {
        recalculate_order(frm, { quiet: true }).catch(() => {});
    }

    frappe.ui.form.on("Door Cutting Order", {
        setup(frm) {
            frm.set_query("board_item", () => ({ filters: { custom_is_mdf: 1 } }));
            frm.set_df_property("packing_mode", "options", PACKING_OPTIONS.join("\n"));
        },

        refresh(frm) {
            if (frm.is_new()) {
                if (!frm.doc.order_date) frm.doc.order_date = frappe.datetime.get_today();
                if (!frm.doc.cutting_cost_per_board_usd) frm.doc.cutting_cost_per_board_usd = 1;
                if (!frm.doc.kerf_mm) frm.doc.kerf_mm = 3;
                if (!frm.doc.trim_margin_mm) frm.doc.trim_margin_mm = 5;
                if (!frm.doc.packing_mode) frm.doc.packing_mode = "Auto";
            }

            setup_pieces_excel_ux(frm);
            add_buttons(frm);
            render_cutting_plan(frm);
            schedule_recalculate(frm);
        },

        customer: schedule_recalculate,
        board_item: schedule_recalculate,
        board_rate_usd: schedule_recalculate,
        default_edge_type: schedule_recalculate,
        cutting_cost_per_board_usd: schedule_recalculate,
        kerf_mm: schedule_recalculate,
        trim_margin_mm: schedule_recalculate,
        packing_mode(frm) {
            frm.doc.packing_method = "جاري إعادة الحساب حسب: " + (frm.doc.packing_mode || "Auto");
            frm.refresh_field("packing_method");
            schedule_recalculate(frm);
        },
        pieces_add: schedule_recalculate,
        pieces_remove: schedule_recalculate
    });

    frappe.ui.form.on("Door Cutting Order Detail", {
        width_cm: schedule_recalculate,
        length_cm: schedule_recalculate,
        qty: schedule_recalculate,
        allow_rotation: schedule_recalculate,
        edge_long_right: schedule_recalculate,
        edge_long_left: schedule_recalculate,
        edge_width_top: schedule_recalculate,
        edge_width_bottom: schedule_recalculate,
        edge_type: schedule_recalculate,
        notes: schedule_recalculate
    });
})();
