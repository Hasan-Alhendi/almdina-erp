(() => {
    "use strict";

    const FRAME_ID = "dco-authoritative-measurements-print-frame";
    const SIDE_CONFIG = [
        {
            side: "long_right",
            selectedField: "edge_long_right",
            overrideField: "edge_long_right_type_override",
            label: "الطول الأيمن",
        },
        {
            side: "long_left",
            selectedField: "edge_long_left",
            overrideField: "edge_long_left_type_override",
            label: "الطول الأيسر",
        },
        {
            side: "width_top",
            selectedField: "edge_width_top",
            overrideField: "edge_width_top_type_override",
            label: "العرض العلوي",
        },
        {
            side: "width_bottom",
            selectedField: "edge_width_bottom",
            overrideField: "edge_width_bottom_type_override",
            label: "العرض السفلي",
        },
    ];
    let activeFrm = null;

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function number(value) {
        const parsed = Number(value || 0);
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function quantity(value) {
        return number(value).toLocaleString("en-US", { maximumFractionDigits: 3 });
    }

    function edgeBandingApi() {
        return window.AlmdinaMultiEdgeBanding || null;
    }

    function shapePrint() {
        return window.AlmdinaShapePrint || null;
    }

    function rowHasDrawing(row) {
        const renderer = shapePrint();
        return Boolean(renderer && renderer.hasVisual(row));
    }

    function notesCellHtml(row) {
        const renderer = shapePrint();
        return renderer
            ? renderer.notesCell(row, row.notes, { label: `رسمة الدرفة رقم ${row.index}` })
            : esc(row.notes || "—");
    }

    function shapePrintCss() {
        const renderer = shapePrint();
        return renderer ? renderer.css : "";
    }

    function pieceTypeLabel(row) {
        if (row.piece_type === "Special") return "خاصة";
        if (row.piece_type === "Clipped Corner") return "زاوية مقصوصة";
        return "عادية";
    }

    function orderEdgeColor(frm) {
        return String(frm.doc.edge_color || "").trim() || "غير محدد";
    }

    async function ensureProfiles(frm) {
        const module = edgeBandingApi();
        if (module && typeof module.ensureProfiles === "function") {
            await Promise.resolve(module.ensureProfiles(frm));
        }
    }

    function fallbackDetails(frm, row) {
        const defaultType = String(frm.doc.default_edge_type || "").trim();
        return SIDE_CONFIG.flatMap(config => {
            if (!row[config.selectedField]) return [];
            const overrideType = String(row[config.overrideField] || "").trim();
            return [{
                side: config.side,
                side_label: config.label,
                edge_type: overrideType || defaultType || "غير محدد",
                custom: Boolean(overrideType),
            }];
        });
    }

    function edgeDetails(frm, row) {
        const module = edgeBandingApi();
        if (module && typeof module.details === "function") {
            return module.details(frm, row);
        }
        return fallbackDetails(frm, row);
    }

    function groupedDetails(details) {
        const groups = new Map();
        (details || []).forEach(detail => {
            const type = String(detail.edge_type || "غير محدد").trim() || "غير محدد";
            const custom = Boolean(detail.custom);
            const key = `${type}::${custom ? "custom" : "default"}`;
            if (!groups.has(key)) {
                groups.set(key, { type, custom, sides: [] });
            }
            groups.get(key).sides.push(detail.side_label || "ضلع");
        });
        return [...groups.values()];
    }

    function edgeDetailsHtml(details) {
        if (!details || !details.length) {
            return '<span class="dco-print-edge-none">بدون قشاط</span>';
        }

        const groups = groupedDetails(details);
        if (details.length === 4 && groups.length === 1) {
            const group = groups[0];
            return `
                <div class="dco-print-edge-group ${group.custom ? "is-custom" : ""}">
                    <span class="dco-print-edge-sides">الأضلاع الأربعة</span>
                    <b>${esc(group.type)}</b>
                    <em>${group.custom ? "مخصص" : "افتراضي"}</em>
                </div>`;
        }

        return `<div class="dco-print-edge-list">${groups.map(group => `
            <div class="dco-print-edge-group ${group.custom ? "is-custom" : ""}">
                <span class="dco-print-edge-sides">${esc(group.sides.join("، "))}</span>
                <b>${esc(group.type)}</b>
                <em>${group.custom ? "مخصص" : "افتراضي"}</em>
            </div>`).join("")}</div>`;
    }

    function dimensionMark(value, edgeCount) {
        const count = Math.max(0, Math.min(2, Number(edgeCount || 0)));
        const lines = Array.from(
            { length: count },
            () => '<span class="dco-measurement-edge-line"></span>'
        ).join("");
        return `
            <span class="dco-measurement-dimension">
                <span class="dco-measurement-value">${esc(quantity(value))}</span>
                <span class="dco-measurement-lines dco-measurement-lines-${count}">${lines}</span>
            </span>`;
    }

    function rows(frm) {
        return (frm.doc.pieces || []).map((source, index) => ({
            ...source,
            index: index + 1,
            type: pieceTypeLabel(source),
            width: source.width_cm,
            length: source.length_cm,
            qty: Math.max(1, Math.trunc(number(source.qty) || 1)),
            widthEdges: Number(Boolean(source.edge_width_top)) + Number(Boolean(source.edge_width_bottom)),
            lengthEdges: Number(Boolean(source.edge_long_right)) + Number(Boolean(source.edge_long_left)),
            edgeDetails: edgeDetails(frm, source),
            notes: source.notes || "",
            drawing_json: source.special_shape_drawing_json || "",
            geometry_json: source.special_shape_geometry_json || "",
            piece_type: source.piece_type || "Regular",
        }));
    }

    function measurementsTable(frm) {
        const data = rows(frm);
        if (!data.length) {
            return '<div class="dco-measurement-empty">لا توجد قياسات في هذا الطلب.</div>';
        }
        return `
            <table class="dco-measurement-print-table">
                <thead><tr>
                    <th>#</th>
                    <th>النوع</th>
                    <th>العرض (سم)</th>
                    <th>الطول (سم)</th>
                    <th>العدد</th>
                    <th class="edge-details">قشاط الأطراف</th>
                    <th class="notes">ملاحظات</th>
                </tr></thead>
                <tbody>${data.map(row => `
                    <tr class="${rowHasDrawing(row) ? "dco-row-with-sketch" : ""}">
                        <td>${row.index}</td>
                        <td>${esc(row.type)}</td>
                        <td>${dimensionMark(row.width, row.widthEdges)}</td>
                        <td>${dimensionMark(row.length, row.lengthEdges)}</td>
                        <td>${row.qty}</td>
                        <td class="edge-details">${edgeDetailsHtml(row.edgeDetails)}</td>
                        <td class="notes ${rowHasDrawing(row) ? "dco-notes-has-sketch" : ""}">${notesCellHtml(row)}</td>
                    </tr>`).join("")}</tbody>
            </table>`;
    }

    function printDocumentHtml(frm) {
        const generated = frappe.datetime ? frappe.datetime.now_datetime() : new Date().toISOString();
        const orderName = frm.doc.name || "مسودة";
        return `<!doctype html>
<html dir="rtl" lang="ar"><head><meta charset="utf-8"><title>قياسات الطلب ${esc(orderName)}</title>
<style>
@page{size:A4 portrait;margin:11mm}*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:Tahoma,Arial,sans-serif;color:#111;direction:rtl;background:#fff}body{font-size:10.5px;-webkit-print-color-adjust:exact;print-color-adjust:exact}.sheet{max-width:100%;margin:0 auto}.header{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:2px solid #111;padding-bottom:9px;margin-bottom:10px}.header h1{font-size:21px;margin:0 0 4px}.muted{color:#666;font-size:9px}.info{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:6px;margin:9px 0 11px}.info>div{border:1px solid #aaa;border-radius:5px;padding:7px;min-width:0;word-break:break-word}.info b{display:block;font-size:8px;color:#555;margin-bottom:2px}.section-title{font-size:13px;font-weight:900;margin:12px 0 5px}.dco-measurement-print-table{width:100%;border-collapse:collapse;font-size:8.5px}.dco-measurement-print-table th,.dco-measurement-print-table td{border:1px solid #999;padding:4px;text-align:center;vertical-align:middle}.dco-measurement-print-table th{background:#eee;font-weight:900}.dco-measurement-print-table .edge-details{width:24%;text-align:right;white-space:normal}.dco-measurement-print-table .notes{width:28%;text-align:right;white-space:normal;line-height:1.5}.dco-print-edge-list{display:grid;gap:3px}.dco-print-edge-group{position:relative;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:1px 5px;padding:3px 5px;border:1px solid #aaa;border-radius:4px;background:#f8f8f8;line-height:1.25}.dco-print-edge-group.is-custom{border:1.5px solid #a67800;background:#fff8df}.dco-print-edge-group b{font-size:8px;word-break:break-word}.dco-print-edge-group em{grid-column:2;grid-row:1/3;align-self:center;font-style:normal;font-size:6.5px;font-weight:900;border:1px solid currentColor;border-radius:999px;padding:1px 4px;color:#555}.dco-print-edge-group.is-custom em{color:#805b00}.dco-print-edge-sides{font-size:7px;color:#333;font-weight:800}.dco-print-edge-none{color:#666}.dco-measurement-dimension{display:inline-flex;min-width:38px;flex-direction:column;align-items:center;justify-content:center;gap:1px;line-height:1}.dco-measurement-value{font-weight:800}.dco-measurement-lines{display:flex;flex-direction:column;align-items:center;gap:1px;min-height:5px;margin-top:1px}.dco-measurement-edge-line{display:block;width:28px;height:1px;background:#111}.dco-measurement-lines-0{visibility:hidden}.dco-measurement-empty{padding:24px;text-align:center;border:1px solid #bbb;color:#666}.footer{margin-top:12px;border-top:1px solid #aaa;padding-top:5px;font-size:8px;color:#666;display:flex;justify-content:space-between}
${shapePrintCss()}
</style></head><body>
<div class="sheet">
<div class="header"><div><h1>جدول قياسات الطلب</h1><div class="muted">نوع القشاط الفعلي لكل ضلع، مع توضيح المخصص والافتراضي</div></div><div style="text-align:left"><b>${esc(orderName)}</b><div class="muted">${esc(frm.doc.order_date || "")}</div></div></div>
<div class="info"><div><b>رقم الطلب</b>${esc(orderName)}</div><div><b>الزبون</b>${esc(frm.doc.customer || "—")}</div><div><b>صنف اللوح</b>${esc(frm.doc.board_description || frm.doc.board_item || "—")}</div><div><b>القشاط الافتراضي</b>${esc(frm.doc.default_edge_type || "—")}</div><div><b>لون القشاط</b>${esc(orderEdgeColor(frm))}</div></div>
<div class="section-title">جدول القياسات</div>${measurementsTable(frm)}
${frm.doc.order_notes ? `<div style="margin-top:10px;padding:7px;border:1px solid #aaa;min-height:32px"><b>ملاحظات الطلب:</b> ${esc(frm.doc.order_notes)}</div>` : ""}
<div class="footer"><span>رقم الطلب: ${esc(orderName)}</span><span>تاريخ الطباعة: ${esc(generated)}</span></div>
</div></body></html>`;
    }

    function printHtml(html) {
        document.getElementById(FRAME_ID)?.remove();
        const frame = document.createElement("iframe");
        frame.id = FRAME_ID;
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
                if (!win) throw new Error("Print frame unavailable");
                win.addEventListener("afterprint", cleanup, { once: true });
                setTimeout(() => { win.focus(); win.print(); }, 100);
            } catch (error) {
                console.error("Measurement print presenter failed", error);
                cleanup();
                frappe.msgprint("تعذر تشغيل طباعة القياسات. أعد تحميل الصفحة ثم حاول مرة أخرى.");
            }
        };
        frame.srcdoc = html;
        document.body.appendChild(frame);
        setTimeout(cleanup, 120000);
    }

    async function printMeasurements(frm) {
        await ensureProfiles(frm);
        printHtml(printDocumentHtml(frm));
    }

    function bindPrintOwnership() {
        if (document._dcoMeasurementPrintPresenterBound) return;
        document._dcoMeasurementPrintPresenterBound = true;
        document.addEventListener("click", event => {
            const button = event.target.closest(".dco-print-measurements,.dco-entry-window-print");
            if (!button || !activeFrm) return;
            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation();
            void printMeasurements(activeFrm);
        }, true);
    }

    bindPrintOwnership();

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { activeFrm = frm; },
        refresh(frm) { activeFrm = frm; },
    });

    window.AlmdinaMeasurementPrintPresenter = {
        details: edgeDetails,
        groups: groupedDetails,
        renderDetails: edgeDetailsHtml,
        html: printDocumentHtml,
        print: printMeasurements,
    };
})();
