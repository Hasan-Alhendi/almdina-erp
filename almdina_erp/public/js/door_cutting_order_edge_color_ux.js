(() => {
    "use strict";

    const PATCH_DELAYS = [0, 60, 220, 500];

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function money(value) {
        const number = Number(value);
        return (Number.isFinite(number) ? number : 0).toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    function quoteTotal(frm) {
        const value = frm.doc.customer_quote_total_usd;
        return value === undefined || value === null
            ? Number(frm.doc.total_cost_usd || 0)
            : Number(value || 0);
    }

    function quoteStatusLabel(status) {
        return {
            Automatic: "تلقائي",
            Estimated: "تقديري",
            "Partially Approved": "معتمد جزئيًا",
            Approved: "معتمد",
        }[status] || status || "تلقائي";
    }

    function getCostRoot(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.order_cost_invoice_html;
        return field && field.$wrapper ? field.$wrapper.get(0) : null;
    }

    function orderEdgeColor(frm) {
        return String(frm.doc.edge_color || "").trim() || "غير محدد";
    }

    function sectionByTitle(root, title) {
        if (!root) return null;
        return [...root.querySelectorAll(".dco-cost-section")].find(section => {
            const heading = section.querySelector(".dco-cost-section-title h4");
            return heading && heading.textContent.trim() === title;
        }) || null;
    }

    function removeLegacyColorDuplicates(root) {
        if (!root) return;
        root.querySelectorAll(
            ".dco-edge-color-col,.dco-edge-color-inline,.dco-edge-color-meta"
        ).forEach(node => node.remove());
    }

    function updateColorKpi(frm, root) {
        if (!root) return;
        const color = orderEdgeColor(frm);
        [...root.querySelectorAll(".dco-cost-kpi")].forEach(card => {
            const label = card.querySelector(".label");
            if (!label || label.textContent.trim() !== "لون القشاط") return;
            const value = card.querySelector(".value");
            if (value) value.textContent = color;
        });
    }

    function patchFastEntryContext(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.pieces_fast_entry;
        const root = field && field.$wrapper ? field.$wrapper.get(0) : null;
        const toolbar = root && root.querySelector(".dco-fast-entry-toolbar");
        if (!toolbar) return;
        const color = orderEdgeColor(frm);
        let badge = toolbar.querySelector(".dco-order-edge-color-badge");
        if (!badge) {
            badge = document.createElement("span");
            badge.className = "dco-order-edge-color-badge";
            badge.style.cssText = "display:inline-flex;align-items:center;gap:5px;margin-inline-start:auto;padding:5px 9px;border:1px solid rgba(36,144,239,.22);border-radius:999px;background:rgba(36,144,239,.06);font-size:10px;font-weight:800;white-space:nowrap";
            toolbar.appendChild(badge);
        }
        badge.innerHTML = `<span style="width:7px;height:7px;border-radius:50%;background:var(--primary,#2490ef)"></span><span>لون القشاط: ${esc(color)}</span>`;
        badge.title = "لون القشاط العام للطلب";
    }

    function patchCostView(frm) {
        const root = getCostRoot(frm);
        removeLegacyColorDuplicates(root);
        updateColorKpi(frm, root);
        patchFastEntryContext(frm);
    }

    function cleanClone(table) {
        if (!table) return null;
        const clone = table.cloneNode(true);
        clone.querySelectorAll(
            ".dco-edge-color-col,.dco-edge-color-inline,.dco-edge-color-meta"
        ).forEach(node => node.remove());
        return clone;
    }

    function printHtml(frm) {
        const root = getCostRoot(frm);
        patchCostView(frm);
        const measurement = sectionByTitle(root, "جدول قياسات الطلب");
        const invoice = sectionByTitle(root, "تفاصيل الفاتورة");
        const measurementTable = cleanClone(measurement && measurement.querySelector("table"));
        const invoiceTable = cleanClone(invoice && invoice.querySelector("table"));
        const generated = frappe.datetime ? frappe.datetime.now_datetime() : new Date().toISOString();

        return `<!doctype html>
<html dir="rtl" lang="ar"><head><meta charset="utf-8"><title>فاتورة الطلب ${esc(frm.doc.name || "")}</title>
<style>
@page{size:A4 portrait;margin:11mm}*{box-sizing:border-box}body{font-family:Tahoma,Arial,sans-serif;color:#111;margin:0;font-size:10.5px;direction:rtl;-webkit-print-color-adjust:exact;print-color-adjust:exact}.header{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:2px solid #111;padding-bottom:9px;margin-bottom:10px}.header h1{font-size:21px;margin:0 0 4px}.muted{color:#666;font-size:9px}.info{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:5px;margin:9px 0}.info>div{border:1px solid #aaa;border-radius:5px;padding:6px;min-width:0;word-break:break-word}.info b{display:block;font-size:8px;color:#555;margin-bottom:2px}.section-title{font-size:13px;font-weight:900;margin:12px 0 5px}.dco-cost-table{width:100%;border-collapse:collapse;font-size:8.8px;min-width:0!important}.dco-cost-table th,.dco-cost-table td{border:1px solid #999;padding:4px;text-align:center;vertical-align:middle}.dco-cost-table th{background:#eee;font-weight:900}.dco-cost-table .text-start,.dco-cost-table .dco-notes-col{text-align:right}.dco-cost-table .dco-notes-col{width:28%;white-space:normal;line-height:1.45}.dco-special-price-status{font-weight:800}.dco-dimension-mark{display:inline-flex;min-width:34px;flex-direction:column;align-items:center;justify-content:center;gap:1px;line-height:1}.dco-dimension-value{font-weight:700}.dco-dimension-lines{display:flex;flex-direction:column;align-items:center;gap:1px;min-height:4px}.dco-dimension-edge-line{display:block;width:25px;height:1px;background:#111}.dco-dimension-lines-0{visibility:hidden}.total{margin-top:9px;margin-right:auto;width:45%;border:2px solid #111;padding:9px;display:flex;justify-content:space-between;align-items:center}.total b{font-size:13px}.total span{font-size:20px;font-weight:900;direction:ltr}.notes{margin-top:10px;padding:7px;border:1px solid #aaa;min-height:32px}.footer{margin-top:12px;border-top:1px solid #aaa;padding-top:5px;font-size:8px;color:#666;display:flex;justify-content:space-between}
</style></head><body>
<div class="header"><div><h1>عرض سعر الطلب</h1><div class="muted">تفاصيل القياسات والمواد والقص والقشاط</div></div><div style="text-align:left"><b>${esc(frm.doc.name || "مسودة")}</b><div class="muted">${esc(frm.doc.order_date || "")}</div><div class="muted">حالة السعر: ${esc(quoteStatusLabel(frm.doc.customer_quote_status))}</div></div></div>
<div class="info"><div><b>الزبون</b>${esc(frm.doc.customer || "—")}</div><div><b>صنف اللوح</b>${esc(frm.doc.board_item || "—")}</div><div><b>عدد الألواح</b>${esc(frm.doc.required_boards || 0)}</div><div><b>نوع القشاط</b>${esc(frm.doc.default_edge_type || "—")}</div></div>
<div class="section-title">جدول القياسات</div>${measurementTable ? measurementTable.outerHTML : '<div>لا توجد قياسات.</div>'}
<div class="section-title">تفاصيل الفاتورة</div>${invoiceTable ? invoiceTable.outerHTML : '<div>لا توجد تفاصيل فاتورة.</div>'}
<div class="total"><b>الإجمالي النهائي</b><span>$ ${money(quoteTotal(frm))}</span></div>
${frm.doc.order_notes ? `<div class="notes"><b>ملاحظات الطلب:</b> ${esc(frm.doc.order_notes)}</div>` : ""}
<div class="footer"><span>رقم الطلب: ${esc(frm.doc.name || "مسودة")}</span><span>تاريخ الطباعة: ${esc(generated)}</span></div>
</body></html>`;
    }

    function printCustomerInvoice(frm) {
        const previous = document.getElementById("dco-edge-color-customer-print-frame");
        if (previous) previous.remove();
        const frame = document.createElement("iframe");
        frame.id = "dco-edge-color-customer-print-frame";
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
                const printWindow = frame.contentWindow;
                if (!printWindow) throw new Error("Print frame unavailable");
                printWindow.addEventListener("afterprint", cleanup, { once: true });
                setTimeout(() => { printWindow.focus(); printWindow.print(); }, 120);
            } catch (error) {
                console.error("Customer invoice print failed", error);
                cleanup();
                frappe.msgprint("تعذر تشغيل الطباعة. أعد تحميل الصفحة ثم حاول مرة أخرى.");
            }
        };
        frame.srcdoc = printHtml(frm);
        document.body.appendChild(frame);
        setTimeout(cleanup, 120000);
    }

    function bindPrintOverride(frm, root) {
        if (!root || root._dcoEdgeColorPrintBound) return;
        root._dcoEdgeColorPrintBound = true;
        root.addEventListener("click", event => {
            const button = event.target.closest(".dco-print-customer-invoice");
            if (!button || !root.contains(button)) return;
            event.preventDefault();
            event.stopImmediatePropagation();
            event.stopPropagation();
            printCustomerInvoice(frm);
        }, true);
    }

    function observeCostView(frm, root) {
        if (!root || root._dcoEdgeColorObserver) return;
        let scheduled = false;
        const observer = new MutationObserver(() => {
            if (scheduled) return;
            scheduled = true;
            requestAnimationFrame(() => {
                scheduled = false;
                patchCostView(frm);
            });
        });
        observer.observe(root, { childList: true, subtree: true });
        root._dcoEdgeColorObserver = observer;
    }

    function enhance(frm) {
        const root = getCostRoot(frm);
        patchCostView(frm);
        bindPrintOverride(frm, root);
        observeCostView(frm, root);
    }

    function schedule(frm) {
        PATCH_DELAYS.forEach(delay => setTimeout(() => enhance(frm), delay));
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
        edge_color(frm) {
            if (window.AlmdinaOrderCostUX && window.AlmdinaOrderCostUX.render) {
                window.AlmdinaOrderCostUX.render(frm);
            }
            schedule(frm);
        },
        default_edge_type(frm) { schedule(frm); },
        pieces_add(frm) { schedule(frm); },
        pieces_remove(frm) { schedule(frm); },
    });
})();
