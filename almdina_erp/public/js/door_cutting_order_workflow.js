(() => {
    "use strict";

    function has_role(role) {
        return (frappe.user_roles || []).includes("System Manager") || (frappe.user_roles || []).includes(role);
    }

    function escape_html(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function num(value) {
        const n = Number(value);
        return Number.isFinite(n) ? n : 0;
    }

    function round(value, decimals = 3) {
        const factor = Math.pow(10, decimals);
        return Math.round(num(value) * factor) / factor;
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

    function is_source_aware_plan(plan) {
        return Boolean(
            plan &&
            Array.isArray(plan.sheets) &&
            plan.sheets.some(sheet =>
                sheet.source_type === "Remnant" ||
                num(sheet.full_width_cm) !== num(plan.full_board_width_cm) ||
                num(sheet.full_length_cm) !== num(plan.full_board_length_cm)
            )
        );
    }

    function call_action(method, args, success_message, frm) {
        return frappe.call({
            method,
            args,
            freeze: true,
            freeze_message: __("Processing..."),
        }).then(r => {
            if (success_message) {
                frappe.show_alert({ message: success_message, indicator: "green" });
            }
            if (frm) {
                return frm.reload_doc().then(() => r.message);
            }
            return r.message;
        });
    }

    function add_review_actions(frm) {
        if (frm.is_new()) return;

        if (["Draft", "Rejected"].includes(frm.doc.status) && (has_role("Order Entry") || has_role("Production Manager"))) {
            frm.add_custom_button(__("إرسال للمراجعة"), () => {
                frm.save().then(() => call_action(
                    "almdina_erp.almdina_erp.services.cutting_plan_service.submit_order_for_review",
                    { order_name: frm.doc.name },
                    __("تم إرسال الطلب للمراجعة."),
                    frm
                ));
            }, __("دورة الطلب"));
        }

        if (frm.doc.status === "Pending Review" && has_role("Production Manager")) {
            frm.add_custom_button(__("اعتماد الطلب"), () => {
                frappe.confirm(
                    __("سيتم تثبيت خطة القص الحالية كنسخة معتمدة وفحص توفر المخزون. هل تريد المتابعة؟"),
                    () => call_action(
                        "almdina_erp.almdina_erp.services.cutting_plan_service.approve_order",
                        { order_name: frm.doc.name },
                        __("تم اعتماد الطلب وتثبيت خطة القص."),
                        frm
                    )
                );
            }, __("دورة الطلب"));

            frm.add_custom_button(__("رفض وإعادة للتعديل"), () => {
                frappe.prompt(
                    [{
                        fieldname: "reason",
                        fieldtype: "Small Text",
                        label: __("سبب الرفض"),
                        reqd: 1,
                    }],
                    values => call_action(
                        "almdina_erp.almdina_erp.services.cutting_plan_service.reject_order",
                        { order_name: frm.doc.name, reason: values.reason },
                        __("تم رفض الطلب وإعادته للتعديل."),
                        frm
                    ),
                    __("رفض الطلب"),
                    __("تأكيد")
                );
            }, __("دورة الطلب"));
        }
    }

    function add_stock_action(frm) {
        if (frm.is_new() || ["Draft", "Rejected", "Pending Review"].includes(frm.doc.status)) return;
        if (!(has_role("Production Manager") || has_role("Stock Manager") || has_role("Cutting Operator"))) return;

        frm.add_custom_button(__("فحص توفر المواد"), () => {
            frappe.call({
                method: "almdina_erp.almdina_erp.services.stock_service.check_order_stock",
                args: { order_name: frm.doc.name },
                freeze: true,
            }).then(r => {
                const data = r.message || {};
                const rows = data.materials || [];
                let html = `<div><b>${__("Warehouse")}:</b> ${escape_html(data.warehouse || "")}</div>`;
                html += `<table class="table table-bordered" style="margin-top:10px"><thead><tr><th>${__("Item")}</th><th>${__("Required")}</th><th>${__("Available")}</th><th>${__("Shortage")}</th></tr></thead><tbody>`;
                rows.forEach(row => {
                    html += `<tr><td>${escape_html(row.item_code || "")}</td><td>${row.required_qty}</td><td>${row.actual_qty}</td><td>${row.shortage_qty}</td></tr>`;
                });
                html += "</tbody></table>";
                if (!rows.length) html += `<p>${__("No stock-managed materials are required from full-stock Items for this order.")}</p>`;
                frappe.msgprint({
                    title: data.is_available ? __("المخزون متوفر") : __("يوجد عجز في المخزون"),
                    indicator: data.is_available ? "green" : "red",
                    message: html,
                });
            });
        }, __("المخزون"));
    }

    function add_related_views(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("مراحل الإنتاج"), () => {
            frappe.set_route("List", "Production Stage", { door_cutting_order: frm.doc.name });
        }, __("عرض"));

        frm.add_custom_button(__("خطط القص"), () => {
            frappe.set_route("List", "Cutting Plan", { door_cutting_order: frm.doc.name });
        }, __("عرض"));

        frm.add_custom_button(__("الأخطاء والتعويضات"), () => {
            frappe.set_route("List", "Production Incident", { door_cutting_order: frm.doc.name });
        }, __("عرض"));
    }

    function render_edge_lines(piece) {
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
            top = piece.edge_long_left ? 1 : 0;
            bottom = piece.edge_long_right ? 1 : 0;
            right = piece.edge_width_top ? 1 : 0;
            left = piece.edge_width_bottom ? 1 : 0;
        }

        const percent = 66.666;
        const start = (100 - percent) / 2;
        const common = "position:absolute;z-index:3;";
        let html = "";
        if (left) html += `<span class="dco-edge-line" style="${common}left:3px;top:${start}%;height:${percent}%;border-left:3px solid #d00000"></span>`;
        if (right) html += `<span class="dco-edge-line" style="${common}right:3px;top:${start}%;height:${percent}%;border-right:3px solid #d00000"></span>`;
        if (top) html += `<span class="dco-edge-line" style="${common}top:3px;left:${start}%;width:${percent}%;border-top:3px solid #d00000"></span>`;
        if (bottom) html += `<span class="dco-edge-line" style="${common}bottom:3px;left:${start}%;width:${percent}%;border-bottom:3px solid #d00000"></span>`;
        return html;
    }

    function source_label(sheet) {
        if (sheet.source_type === "Remnant") {
            return `بقايا لوح ${escape_html(sheet.remnant || "")}`;
        }
        return "لوح كامل";
    }

    function build_source_aware_plan_html(frm, plan) {
        const total_source_area = round(plan.total_board_area_m2, 3);
        const used_area = round(plan.used_area_m2, 3);
        const waste_area = round(plan.waste_area_m2, 3);
        const waste_percent = total_source_area ? round(waste_area / total_source_area * 100, 2) : 0;
        const full_board_count = plan.required_full_boards !== undefined
            ? Number(plan.required_full_boards)
            : (plan.sheets || []).filter(s => (s.source_type || "Full Board") === "Full Board").length;
        const remnant_count = (plan.sheets || []).filter(s => s.source_type === "Remnant").length;

        let html = `
            <div class="dco-cutting-plan dco-source-aware" style="font-family:Arial,Tahoma,sans-serif;direction:rtl;color:#111;background:#fff;">
                <h2 style="margin:0 0 8px 0;font-size:18px;">خطة القص</h2>
                <div style="line-height:1.7;margin-bottom:8px;font-size:12px;">
                    <b>الطلب:</b> ${escape_html(frm.doc.name || "")} &nbsp; | &nbsp;
                    <b>الزبون:</b> ${escape_html(frm.doc.customer || "")} &nbsp; | &nbsp;
                    <b>الصنف:</b> <span dir="ltr">${escape_html(frm.doc.board_item || "")}</span><br>
                    <b>سماكة القص:</b> ${round(num(plan.kerf_cm) * 10, 1)} مم &nbsp; | &nbsp;
                    <b>هامش التشذيب:</b> ${round(num(plan.trim_cm) * 10, 1)} مم &nbsp; | &nbsp;
                    <b>الخوارزمية:</b> ${escape_html(plan.method_label || frm.doc.packing_method || "")}
                </div>
                <div class="dco-summary-grid" style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:8px 0 12px 0;">
                    <div class="dco-summary-card" style="border:1px solid #ddd;border-radius:8px;padding:8px;background:#f8fafc;"><b>ألواح جديدة</b><span>${full_board_count}</span></div>
                    <div class="dco-summary-card" style="border:1px solid #ddd;border-radius:8px;padding:8px;background:#f8fafc;"><b>بقايا مستخدمة</b><span>${remnant_count}</span></div>
                    <div class="dco-summary-card" style="border:1px solid #ddd;border-radius:8px;padding:8px;background:#f8fafc;"><b>مساحة القطع</b><span>${used_area} م²</span></div>
                    <div class="dco-summary-card" style="border:1px solid #ddd;border-radius:8px;padding:8px;background:#f8fafc;"><b>الهدر</b><span>${waste_area} م² (${waste_percent}%)</span></div>
                </div>
        `;

        (plan.sheets || []).forEach(sheet => {
            const usableW = num(sheet.usable_width_cm || sheet.w || plan.usable_board_width_cm);
            const usableH = num(sheet.usable_length_cm || sheet.h || plan.usable_board_length_cm);
            const fullW = num(sheet.full_width_cm || plan.full_board_width_cm);
            const fullH = num(sheet.full_length_cm || plan.full_board_length_cm);
            const sourceArea = num(sheet.source_area_m2) || usableW * usableH / 10000;
            const used = (sheet.pieces || []).reduce((sum, p) => sum + num(p.area_m2), 0);
            const waste = Math.max(0, sourceArea - used);
            const wastePct = sourceArea ? round(waste / sourceArea * 100, 2) : 0;
            const boardWidthPx = 560;
            const boardHeightPx = Math.max(260, Math.round(boardWidthPx * (usableH / usableW)));

            html += `
                <div class="dco-sheet-card" style="border:1px solid #bbb;border-radius:10px;padding:10px;margin:14px 0;background:#fff;page-break-inside:avoid;break-inside:avoid;">
                    <div class="dco-sheet-title" style="display:flex;justify-content:space-between;gap:10px;margin-bottom:8px;font-size:13px;font-weight:bold;">
                        <div>المصدر ${sheet.sheet_no}: ${source_label(sheet)}</div>
                        <div>المقاس الكامل: ${round(fullW, 1)}×${round(fullH, 1)} سم | المستخدم: ${round(usableW, 1)}×${round(usableH, 1)} سم | القطع: ${(sheet.pieces || []).length} | الهدر: ${round(waste, 3)} م² (${wastePct}%)</div>
                    </div>
                    <div class="dco-sheet-board" style="position:relative;direction:ltr;width:${boardWidthPx}px;height:${boardHeightPx}px;max-width:100%;border:2px solid #111;background:linear-gradient(90deg,rgba(0,0,0,.05) 1px,transparent 1px),linear-gradient(rgba(0,0,0,.05) 1px,transparent 1px),#fff;background-size:32px 32px;overflow:hidden;margin:0 auto 8px auto;">
            `;

            (sheet.pieces || []).forEach(piece => {
                const left = usableW ? num(piece.x) / usableW * 100 : 0;
                const top = usableH ? num(piece.y) / usableH * 100 : 0;
                const width = usableW ? num(piece.w) / usableW * 100 : 0;
                const height = usableH ? num(piece.h) / usableH * 100 : 0;
                html += `
                    <div class="dco-piece" style="position:absolute;left:${left}%;top:${top}%;width:${width}%;height:${height}%;border:1px solid #111;background:#e4f5ff;color:#111;overflow:hidden;padding:2px;font-size:10px;line-height:1.2;text-align:center;box-sizing:border-box;display:flex;align-items:center;justify-content:center;">
                        ${render_edge_lines(piece)}
                        <div class="dco-piece-label" style="position:relative;z-index:4;direction:ltr;text-align:center;"><b>${escape_html(piece.label)}</b><br><span>${round(piece.original_w, 1)}*${round(piece.original_h, 1)} سم</span></div>
                    </div>
                `;
            });
            html += "</div></div>";
        });

        if (plan.unplaced && plan.unplaced.length) {
            html += `<div style="border:1px solid #d9534f;background:#fff5f5;color:#a94442;padding:8px;border-radius:8px;margin-top:12px;"><b>تنبيه:</b> توجد ${plan.unplaced.length} قطعة لم تدخل ضمن المصادر.</div>`;
        }
        html += "</div>";
        return html;
    }

    function render_source_aware(frm) {
        const plan = parse_plan(frm);
        if (!is_source_aware_plan(plan)) return false;
        const wrapper = frm.fields_dict.cutting_plan_html && frm.fields_dict.cutting_plan_html.$wrapper;
        if (wrapper) wrapper.html(build_source_aware_plan_html(frm, plan));
        return true;
    }

    function print_source_aware(frm) {
        const plan = parse_plan(frm);
        if (!is_source_aware_plan(plan)) return;
        const win = window.open("", "_blank");
        if (!win) {
            frappe.msgprint("المتصفح منع فتح نافذة الطباعة. اسمح بالنوافذ المنبثقة ثم جرّب مرة أخرى.");
            return;
        }
        const html = build_source_aware_plan_html(frm, plan);
        win.document.open();
        win.document.write(`<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><title>${escape_html("خطة قص - " + (frm.doc.name || ""))}</title><style>
            @page{size:A4 portrait;margin:6mm}*{-webkit-print-color-adjust:exact!important;print-color-adjust:exact!important;box-sizing:border-box!important}html,body{margin:0;padding:0;background:#fff;color:#111;font-family:Arial,Tahoma,sans-serif;direction:rtl}body{padding:5mm}.dco-cutting-plan h2{display:none!important}.dco-summary-grid{gap:4px!important}.dco-summary-card{padding:4px!important;font-size:9px!important}.dco-summary-card b{display:block!important;font-size:8px!important}.dco-sheet-card{zoom:.68;border:1px solid #777!important;padding:5px!important;margin:7px 0 0!important;page-break-inside:avoid!important;break-inside:avoid!important}.dco-sheet-card+.dco-sheet-card{page-break-before:always!important;break-before:page!important}.dco-sheet-title{font-size:10px!important}.dco-piece{font-size:8px!important}.dco-piece-label{direction:ltr!important;text-align:center!important}.dco-edge-line{border-color:#d00000!important}
        </style></head><body><div style="border-bottom:2px solid #111;padding-bottom:5px;margin-bottom:6px"><b style="font-size:18px">خطة قص</b><br><span style="font-size:10px">رقم الطلب: ${escape_html(frm.doc.name || "")} | الزبون: ${escape_html(frm.doc.customer || "")}</span></div>${html}<script>window.onload=function(){setTimeout(function(){window.focus();window.print();},700);};<\/script></body></html>`);
        win.document.close();
    }

    function dxf_pair(code, value) {
        return `${code}\r\n${value}\r\n`;
    }

    function dxf_num(value) {
        const n = num(value);
        return String(Math.round(n * 1000) / 1000);
    }

    function dxf_layer(name, color) {
        return dxf_pair(0, "LAYER") + dxf_pair(2, name) + dxf_pair(70, 0) + dxf_pair(62, color) + dxf_pair(6, "CONTINUOUS");
    }

    function dxf_rect(layer, x, y, w, h) {
        const points = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];
        let out = dxf_pair(0, "POLYLINE") + dxf_pair(8, layer) + dxf_pair(66, 1) + dxf_pair(10, 0) + dxf_pair(20, 0) + dxf_pair(30, 0) + dxf_pair(70, 1);
        points.forEach(p => {
            out += dxf_pair(0, "VERTEX") + dxf_pair(8, layer) + dxf_pair(10, dxf_num(p[0])) + dxf_pair(20, dxf_num(p[1])) + dxf_pair(30, 0);
        });
        return out + dxf_pair(0, "SEQEND") + dxf_pair(8, layer);
    }

    function source_aware_dxf(frm) {
        const plan = parse_plan(frm);
        if (!is_source_aware_plan(plan)) return;
        const sheets = plan.sheets || [];
        const perRow = 2;
        const gap = 200;
        const maxW = Math.max(...sheets.map(s => num(s.full_width_cm || plan.full_board_width_cm) * 10));
        const maxH = Math.max(...sheets.map(s => num(s.full_length_cm || plan.full_board_length_cm) * 10));
        const trim = num(plan.trim_cm) * 10;
        let entities = "";
        let extmaxX = 0;
        let extmaxY = 0;

        sheets.forEach((sheet, index) => {
            const fullW = num(sheet.full_width_cm || plan.full_board_width_cm) * 10;
            const fullH = num(sheet.full_length_cm || plan.full_board_length_cm) * 10;
            const offsetX = (index % perRow) * (maxW + gap);
            const offsetY = Math.floor(index / perRow) * (maxH + gap);
            extmaxX = Math.max(extmaxX, offsetX + fullW);
            extmaxY = Math.max(extmaxY, offsetY + fullH);
            entities += dxf_rect("SHEET_OUTLINE", offsetX, offsetY, fullW, fullH);

            (sheet.pieces || []).forEach(piece => {
                const pieceW = num(piece.w) * 10;
                const pieceH = num(piece.h) * 10;
                const x = offsetX + trim + num(piece.x) * 10;
                const y = offsetY + fullH - trim - num(piece.y) * 10 - pieceH;
                entities += dxf_rect("CUT_PATH", x, y, pieceW, pieceH);
            });
        });

        let dxf = dxf_pair(0, "SECTION") + dxf_pair(2, "HEADER");
        dxf += dxf_pair(9, "$ACADVER") + dxf_pair(1, "AC1009") + dxf_pair(9, "$INSUNITS") + dxf_pair(70, 4);
        dxf += dxf_pair(9, "$EXTMIN") + dxf_pair(10, 0) + dxf_pair(20, 0) + dxf_pair(30, 0);
        dxf += dxf_pair(9, "$EXTMAX") + dxf_pair(10, dxf_num(extmaxX)) + dxf_pair(20, dxf_num(extmaxY)) + dxf_pair(30, 0) + dxf_pair(0, "ENDSEC");
        dxf += dxf_pair(0, "SECTION") + dxf_pair(2, "TABLES");
        dxf += dxf_pair(0, "TABLE") + dxf_pair(2, "LTYPE") + dxf_pair(70, 1) + dxf_pair(0, "LTYPE") + dxf_pair(2, "CONTINUOUS") + dxf_pair(70, 0) + dxf_pair(3, "Solid line") + dxf_pair(72, 65) + dxf_pair(73, 0) + dxf_pair(40, 0) + dxf_pair(0, "ENDTAB");
        dxf += dxf_pair(0, "TABLE") + dxf_pair(2, "LAYER") + dxf_pair(70, 3) + dxf_layer("0", 7) + dxf_layer("SHEET_OUTLINE", 8) + dxf_layer("CUT_PATH", 1) + dxf_pair(0, "ENDTAB") + dxf_pair(0, "ENDSEC");
        dxf += dxf_pair(0, "SECTION") + dxf_pair(2, "BLOCKS") + dxf_pair(0, "ENDSEC") + dxf_pair(0, "SECTION") + dxf_pair(2, "ENTITIES") + entities + dxf_pair(0, "ENDSEC") + dxf_pair(0, "EOF");

        const blob = new Blob([dxf], { type: "application/octet-stream" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `cutting_plan_${String(frm.doc.name || "door_cutting_order").replace(/[^\w\-]+/g, "_")}.dxf`;
        document.body.appendChild(a);
        a.click();
        setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 500);
        frappe.show_alert({ message: "تم تصدير DXF من المصادر الفعلية. CUT_PATH للقص وSHEET_OUTLINE للمعاينة.", indicator: "green" });
    }

    function install_source_aware_outputs(frm) {
        const plan = parse_plan(frm);
        if (!is_source_aware_plan(plan)) return;
        render_source_aware(frm);

        frm.remove_custom_button("طباعة خطة القص");
        frm.remove_custom_button("تصدير DXF");
        frm.add_custom_button("طباعة خطة القص", () => print_source_aware(frm));
        frm.add_custom_button("تصدير DXF", () => source_aware_dxf(frm));
    }

    frappe.ui.form.on("Door Cutting Order", {
        refresh(frm) {
            add_review_actions(frm);
            add_stock_action(frm);
            add_related_views(frm);
            setTimeout(() => install_source_aware_outputs(frm), 400);
            if (frappe.after_ajax) {
                frappe.after_ajax(() => install_source_aware_outputs(frm));
            }
        },
    });
})();
