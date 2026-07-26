(() => {
    "use strict";

    const STYLE_ID = "dco-measurement-actions-css";

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function number(value) {
        const parsed = Number(value || 0);
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function pieceTypeLabel(row) {
        if (row.piece_type === "Special") return "خاصة";
        if (row.piece_type === "Clipped Corner") return "زاوية مقصوصة";
        return "عادية";
    }

    function dimensionMark(value, edgeCount) {
        const count = Math.max(0, Math.min(2, Number(edgeCount || 0)));
        const lines = Array.from({ length: count }, () => '<span class="dco-measurement-edge-line"></span>').join("");
        return `
            <span class="dco-measurement-dimension">
                <span class="dco-measurement-value">${esc(number(value).toLocaleString("en-US", { maximumFractionDigits: 3 }))}</span>
                <span class="dco-measurement-lines dco-measurement-lines-${count}">${lines}</span>
            </span>`;
    }

    function rows(frm) {
        return (frm.doc.pieces || []).map((row, index) => ({
            index: index + 1,
            type: pieceTypeLabel(row),
            width: row.width_cm,
            length: row.length_cm,
            qty: Math.max(1, Math.trunc(number(row.qty) || 1)),
            widthEdges: Number(Boolean(row.edge_width_top)) + Number(Boolean(row.edge_width_bottom)),
            lengthEdges: Number(Boolean(row.edge_long_right)) + Number(Boolean(row.edge_long_left)),
            edgeType: row.edge_type || frm.doc.default_edge_type || "—",
            notes: row.notes || "—",
        }));
    }

    function measurementsTable(frm) {
        const data = rows(frm);
        if (!data.length) return '<div class="dco-measurement-empty">لا توجد قياسات في هذا الطلب.</div>';
        return `
            <table class="dco-measurement-print-table">
                <thead><tr>
                    <th>#</th>
                    <th>النوع</th>
                    <th>العرض (سم)</th>
                    <th>الطول (سم)</th>
                    <th>العدد</th>
                    <th>نوع القشاط</th>
                    <th class="notes">ملاحظات</th>
                </tr></thead>
                <tbody>${data.map(row => `
                    <tr>
                        <td>${row.index}</td>
                        <td>${esc(row.type)}</td>
                        <td>${dimensionMark(row.width, row.widthEdges)}</td>
                        <td>${dimensionMark(row.length, row.lengthEdges)}</td>
                        <td>${row.qty}</td>
                        <td>${esc(row.edgeType)}</td>
                        <td class="notes">${esc(row.notes)}</td>
                    </tr>`).join("")}</tbody>
            </table>`;
    }

    function documentHtml(frm, standalone = false) {
        const generated = frappe.datetime ? frappe.datetime.now_datetime() : new Date().toISOString();
        const orderName = frm.doc.name || "مسودة";
        return `<!doctype html>
<html dir="rtl" lang="ar"><head><meta charset="utf-8"><title>قياسات الطلب ${esc(orderName)}</title>
<style>
@page{size:A4 portrait;margin:11mm}*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:Tahoma,Arial,sans-serif;color:#111;direction:rtl;background:#fff}body{padding:${standalone ? "18px" : "0"};font-size:10.5px;-webkit-print-color-adjust:exact;print-color-adjust:exact}.screen-toolbar{display:${standalone ? "flex" : "none"};align-items:center;justify-content:space-between;gap:10px;position:sticky;top:0;z-index:20;padding:10px 12px;margin:-18px -18px 14px;background:#f6f7f8;border-bottom:1px solid #d7dbe0}.screen-toolbar .actions{display:flex;gap:8px}.screen-toolbar button{border:1px solid #c8cdd3;border-radius:8px;background:#fff;padding:8px 13px;font-family:inherit;font-weight:800;cursor:pointer}.screen-toolbar button.primary{background:#111;color:#fff;border-color:#111}.sheet{max-width:${standalone ? "1500px" : "100%"};margin:0 auto}.header{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:2px solid #111;padding-bottom:9px;margin-bottom:10px}.header h1{font-size:21px;margin:0 0 4px}.muted{color:#666;font-size:9px}.info{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;margin:9px 0 11px}.info>div{border:1px solid #aaa;border-radius:5px;padding:7px;min-width:0;word-break:break-word}.info b{display:block;font-size:8px;color:#555;margin-bottom:2px}.section-title{font-size:13px;font-weight:900;margin:12px 0 5px}.table-wrap{overflow:auto;max-height:${standalone ? "calc(100vh - 205px)" : "none"};border:1px solid #999}.dco-measurement-print-table{width:100%;border-collapse:collapse;font-size:${standalone ? "12px" : "9px"};min-width:${standalone ? "980px" : "0"}}.dco-measurement-print-table th,.dco-measurement-print-table td{border:1px solid #999;padding:${standalone ? "8px 7px" : "4px"};text-align:center;vertical-align:middle}.dco-measurement-print-table th{background:#eee;font-weight:900;position:${standalone ? "sticky" : "static"};top:0;z-index:3}.dco-measurement-print-table .notes{width:32%;text-align:right;white-space:normal;line-height:1.5}.dco-measurement-dimension{display:inline-flex;min-width:38px;flex-direction:column;align-items:center;justify-content:center;gap:1px;line-height:1}.dco-measurement-value{font-weight:800}.dco-measurement-lines{display:flex;flex-direction:column;align-items:center;gap:1px;min-height:5px;margin-top:1px}.dco-measurement-edge-line{display:block;width:28px;height:1px;background:#111}.dco-measurement-lines-0{visibility:hidden}.dco-measurement-empty{padding:24px;text-align:center;border:1px solid #bbb;color:#666}.footer{margin-top:12px;border-top:1px solid #aaa;padding-top:5px;font-size:8px;color:#666;display:flex;justify-content:space-between}@media print{body{padding:0}.screen-toolbar{display:none!important}.sheet{max-width:none}.table-wrap{overflow:visible;max-height:none;border:0}.dco-measurement-print-table{min-width:0;font-size:9px}.dco-measurement-print-table th{position:static}.dco-measurement-print-table th,.dco-measurement-print-table td{padding:4px}}
</style></head><body>
<div class="screen-toolbar"><strong>جدول قياسات الطلب ${esc(orderName)}</strong><div class="actions"><button id="dco-popup-print" class="primary">طباعة القياسات</button><button id="dco-popup-close">إغلاق النافذة</button></div></div>
<div class="sheet">
<div class="header"><div><h1>جدول قياسات الطلب</h1><div class="muted">نفس تنسيق قياسات فاتورة الطلب دون تفاصيل الأسعار والفاتورة</div></div><div style="text-align:left"><b>${esc(orderName)}</b><div class="muted">${esc(frm.doc.order_date || "")}</div></div></div>
<div class="info"><div><b>رقم الطلب</b>${esc(orderName)}</div><div><b>الزبون</b>${esc(frm.doc.customer || "—")}</div><div><b>صنف اللوح</b>${esc(frm.doc.board_item || "—")}</div><div><b>نوع القشاط</b>${esc(frm.doc.default_edge_type || "—")}</div></div>
<div class="section-title">جدول القياسات</div><div class="table-wrap">${measurementsTable(frm)}</div>
${frm.doc.order_notes ? `<div style="margin-top:10px;padding:7px;border:1px solid #aaa;min-height:32px"><b>ملاحظات الطلب:</b> ${esc(frm.doc.order_notes)}</div>` : ""}
<div class="footer"><span>رقم الطلب: ${esc(orderName)}</span><span>تاريخ الطباعة: ${esc(generated)}</span></div>
</div></body></html>`;
    }

    function printMeasurements(frm) {
        const oldFrame = document.getElementById("dco-measurements-print-frame");
        if (oldFrame) oldFrame.remove();
        const frame = document.createElement("iframe");
        frame.id = "dco-measurements-print-frame";
        frame.setAttribute("aria-hidden", "true");
        frame.style.cssText = "position:fixed;right:0;bottom:0;width:1px;height:1px;border:0;opacity:0;pointer-events:none;z-index:-1";
        let cleaned = false;
        const cleanup = () => {
            if (cleaned) return;
            cleaned = true;
            if (frame.parentNode) frame.parentNode.removeChild(frame);
        };
        frame.onload = () => {
            try {
                const win = frame.contentWindow;
                if (!win) throw new Error("Print frame unavailable");
                win.addEventListener("afterprint", cleanup, { once: true });
                setTimeout(() => { win.focus(); win.print(); }, 100);
            } catch (error) {
                console.error("Measurement print failed", error);
                cleanup();
                frappe.msgprint("تعذر تشغيل طباعة القياسات. أعد تحميل الصفحة ثم حاول مرة أخرى.");
            }
        };
        frame.srcdoc = documentHtml(frm, false);
        document.body.appendChild(frame);
        setTimeout(cleanup, 120000);
    }

    function openMeasurementsWindow(frm) {
        const popup = window.open("", `dco_measurements_${String(frm.doc.name || "draft").replace(/[^\w-]+/g, "_")}`, "popup=yes,width=1500,height=900,resizable=yes,scrollbars=yes");
        if (!popup) {
            frappe.msgprint("تعذر فتح نافذة القياسات. اسمح بالنوافذ المنبثقة لهذا الموقع ثم أعد المحاولة.");
            return;
        }
        popup.document.open();
        popup.document.write(documentHtml(frm, true));
        popup.document.close();
        const bind = () => {
            const printButton = popup.document.getElementById("dco-popup-print");
            const closeButton = popup.document.getElementById("dco-popup-close");
            if (printButton) printButton.addEventListener("click", () => { popup.focus(); popup.print(); });
            if (closeButton) closeButton.addEventListener("click", () => popup.close());
            popup.focus();
        };
        if (popup.document.readyState === "complete") bind();
        else popup.addEventListener("load", bind, { once: true });
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-measurement-table-actions{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-inline-start:auto}
            .dco-measurement-table-actions .btn{border-radius:8px!important;font-weight:800!important;white-space:nowrap}
            .dco-measurement-table-actions .dco-open-measurements-window{display:inline-flex;align-items:center;gap:5px}
            @media(max-width:760px){.dco-measurement-table-actions{width:100%;margin-inline-start:0}.dco-measurement-table-actions .btn{flex:1 1 auto}}
        `;
        document.head.appendChild(style);
    }

    function ensureActions(frm) {
        installStyles();
        const field = frm.fields_dict.pieces_fast_entry;
        const root = field && field.$wrapper ? field.$wrapper.get(0) : null;
        const toolbar = root && root.querySelector(".dco-fast-entry-toolbar");
        if (!toolbar) return;
        let actions = toolbar.querySelector(".dco-measurement-table-actions");
        if (!actions) {
            actions = document.createElement("div");
            actions.className = "dco-measurement-table-actions";
            actions.innerHTML = `
                <button type="button" class="btn btn-default btn-sm dco-print-measurements">طباعة القياسات</button>
                <button type="button" class="btn btn-default btn-sm dco-open-measurements-window"><span aria-hidden="true">↗</span><span>فتح الجدول في نافذة مستقلة</span></button>`;
            toolbar.appendChild(actions);
        }
        if (!root._dcoMeasurementActionsBound) {
            root._dcoMeasurementActionsBound = true;
            root.addEventListener("click", event => {
                const printButton = event.target.closest(".dco-print-measurements");
                if (printButton && root.contains(printButton)) {
                    event.preventDefault();
                    printMeasurements(frm);
                    return;
                }
                const openButton = event.target.closest(".dco-open-measurements-window");
                if (openButton && root.contains(openButton)) {
                    event.preventDefault();
                    openMeasurementsWindow(frm);
                }
            });
        }
        if (!root._dcoMeasurementActionsObserver) {
            let scheduled = false;
            const observer = new MutationObserver(() => {
                if (scheduled) return;
                scheduled = true;
                requestAnimationFrame(() => { scheduled = false; ensureActions(frm); });
            });
            observer.observe(root, { childList: true, subtree: true });
            root._dcoMeasurementActionsObserver = observer;
        }
    }

    function schedule(frm) {
        ensureActions(frm);
        requestAnimationFrame(() => ensureActions(frm));
        setTimeout(() => ensureActions(frm), 180);
        setTimeout(() => ensureActions(frm), 600);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
    });

    window.AlmdinaMeasurementActions = { print: printMeasurements, open: openMeasurementsWindow };
})();
