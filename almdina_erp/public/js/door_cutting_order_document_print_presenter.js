(() => {
    "use strict";

    const FRAME_ID = "dco-unified-document-print-frame";
    let activeFrm = null;
    let activeIdentity = "";

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

    function money(value) {
        return number(value).toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function captureIdentity(frm) {
        const context = documentContext();
        if (context && typeof context.capture === "function") {
            return context.capture(frm);
        }
        const doc = frm && frm.doc;
        return doc ? `${doc.doctype || frm.doctype || ""}::${doc.name || "__new__"}` : "";
    }

    function isCurrent(frm, identity) {
        const context = documentContext();
        if (context && typeof context.isCurrent === "function") {
            return context.isCurrent(frm, identity);
        }
        return Boolean(frm && identity && frm === activeFrm && identity === activeIdentity);
    }

    function edgeBandingApi() {
        return window.AlmdinaMultiEdgeBanding || null;
    }

    function shapePrintApi() {
        return window.AlmdinaShapePrint || null;
    }

    function printThemeApi() {
        return window.AlmdinaOrderDocumentPrintTheme || null;
    }

    function printIdentityApi() {
        return window.AlmdinaFactoryPrintIdentity || null;
    }

    async function resolvePrintIdentity() {
        const api = printIdentityApi();
        if (api && typeof api.get === "function") {
            return Promise.resolve(api.get());
        }
        return api && typeof api.fallback === "function" ? api.fallback() : {};
    }

    async function ensureProfiles(frm) {
        const module = edgeBandingApi();
        if (module && typeof module.ensureProfiles === "function") {
            await Promise.resolve(module.ensureProfiles(frm));
        }
    }

    function pieceTypeLabel(value) {
        if (value === "Special") return "خاصة";
        if (value === "Clipped Corner") return "زاوية مقصوصة";
        return "عادية";
    }

    function rowHasDrawing(row) {
        const renderer = shapePrintApi();
        return Boolean(renderer && renderer.hasVisual(row));
    }

    function notesCellHtml(row) {
        const renderer = shapePrintApi();
        return renderer
            ? renderer.notesCell(row, row.notes, {
                label: `رسمة الدرفة رقم ${row.index}`,
                caption: `رسمة الدرفة ${row.index}`,
            })
            : esc(row.notes || "—");
    }

    function shapePrintCss() {
        const renderer = shapePrintApi();
        return renderer ? renderer.css : "";
    }

    function rows(frm) {
        const module = edgeBandingApi();
        return (frm.doc.pieces || []).map((source, index) => ({
            ...source,
            index: index + 1,
            source,
            pieceType: source.piece_type || "Regular",
            width: number(source.width_cm),
            length: number(source.length_cm),
            qty: Math.max(1, Math.trunc(number(source.qty) || 1)),
            notes: source.notes || "",
            details: module && typeof module.details === "function"
                ? module.details(frm, source)
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

    function sideSummary(group, customSideCount) {
        if (customSideCount === 4 && group.sides.length === 4) return "على الداير";
        return group.sides.join("، ");
    }

    function customEdgeDetailsHtml(details) {
        const groups = customEdgeGroups(details);
        if (!groups.length) return '<span class="custom-edge-empty" aria-label="لا يوجد تخصيص"></span>';
        const customSideCount = groups.reduce((sum, group) => sum + group.sides.length, 0);
        return `<div class="custom-edge-summary">${groups.map(group => `
            <div class="custom-edge-line">
                <span>${esc(sideSummary(group, customSideCount))}</span>
                <b>${esc(group.type)}</b>
                <em>مخصص</em>
            </div>`).join("")}</div>`;
    }

    function dimensionMark(value, count) {
        const safeCount = Math.max(0, Math.min(2, Number(count || 0)));
        const lines = Array.from(
            { length: safeCount },
            () => '<span class="dimension-edge-line"></span>'
        ).join("");
        return `<span class="dimension"><b>${quantity(value)}</b><span class="dimension-lines dimension-lines-${safeCount}">${lines}</span></span>`;
    }

    function measurementRowsHtml(frm) {
        return rows(frm).map(row => {
            const longCount = Number(Boolean(row.source.edge_long_right))
                + Number(Boolean(row.source.edge_long_left));
            const widthCount = Number(Boolean(row.source.edge_width_top))
                + Number(Boolean(row.source.edge_width_bottom));
            const drawing = rowHasDrawing(row);
            return `<tr class="${drawing ? "row-with-drawing" : ""}">
                <td><b>${row.index}</b></td>
                <td>${esc(pieceTypeLabel(row.pieceType))}</td>
                <td>${dimensionMark(row.width, widthCount)}</td>
                <td>${dimensionMark(row.length, longCount)}</td>
                <td>${row.qty}</td>
                <td class="right custom-edge-cell">${customEdgeDetailsHtml(row.details)}</td>
                <td class="right notes-cell ${drawing ? "notes-with-drawing" : ""}">${notesCellHtml(row)}</td>
            </tr>`;
        }).join("");
    }

    function invoiceLines(frm) {
        const documents = window.AlmdinaMultiEdgeDocuments;
        if (documents && typeof documents.invoiceLines === "function") {
            return documents.invoiceLines(frm);
        }
        const costing = window.AlmdinaOrderCostUX;
        return costing && typeof costing.invoiceLines === "function"
            ? costing.invoiceLines(frm)
            : [];
    }

    function invoiceTotal(frm, lines) {
        const documents = window.AlmdinaMultiEdgeDocuments;
        if (documents && typeof documents.invoiceTotal === "function") {
            return documents.invoiceTotal(frm);
        }
        return lines.reduce((sum, line) => sum + number(line.amount), 0);
    }

    function customerLineNote(line) {
        const note = String(line.note || "").trim();
        if (!note) return "";
        if (line.type !== "edge") return note;
        if (note.includes("من القشاط الافتراضي")) return "";
        return note.replace("يتضمن أطرافًا مخصصة", "تخصيص استثنائي");
    }

    function invoiceRowsHtml(lines) {
        if (!lines.length) {
            return '<tr><td colspan="6">احفظ الطلب واحسب خطة القص لتظهر تفاصيل الفاتورة.</td></tr>';
        }
        return lines.map((line, index) => {
            const note = customerLineNote(line);
            return `<tr>
                <td>${index + 1}</td>
                <td class="right invoice-description"><b>${esc(line.description)}</b>${note ? `<span class="line-note">${esc(note)}</span>` : ""}</td>
                <td>${quantity(line.quantity)}</td>
                <td>${esc(line.unit)}</td>
                <td>${line.rate || line.rate === 0 ? money(line.rate) : "—"}</td>
                <td><b>${money(line.amount)}</b></td>
            </tr>`;
        }).join("");
    }

    function sharedHeader(frm, mode, printIdentity) {
        const theme = printThemeApi();
        if (!theme || typeof theme.headerHtml !== "function") {
            throw new Error("Unified factory print header is unavailable");
        }
        const title = mode === "invoice" ? "عرض سعر الطلب" : "جدول قياسات الطلب";
        const reference = frm.doc.name || "مسودة";
        const date = String(frm.doc.order_date || "").trim();
        return theme.headerHtml(printIdentity, {
            title,
            meta: date ? `${reference} · ${date}` : reference,
        });
    }

    function sharedInfo(frm) {
        const doorCount = (frm.doc.pieces || []).reduce(
            (sum, row) => sum + Math.max(1, Math.trunc(number(row.qty) || 1)),
            0
        );
        return `<div class="info shared-info">
            <div><b>رقم الطلب</b>${esc(frm.doc.name || "مسودة")}</div>
            <div><b>الزبون</b>${esc(frm.doc.customer || "—")}</div>
            <div><b>اللوح</b>${esc(frm.doc.board_description || "—")}</div>
            <div><b>نوع القشاط</b>${esc(frm.doc.default_edge_type || "—")}</div>
            <div><b>لون القشاط</b>${esc(frm.doc.edge_color || "غير محدد")}</div>
            <div><b>عدد الدرف</b>${quantity(doorCount)}</div>
        </div>`;
    }

    function invoiceSummary(frm) {
        return `<div class="info financial-info">
            <div><b>عدد الألواح</b>${quantity(frm.doc.required_boards)}</div>
            <div><b>سعر اللوح</b>$ ${money(frm.doc.board_rate_usd)}</div>
            <div><b>أجور القص / لوح</b>$ ${money(frm.doc.cutting_cost_per_board_usd)}</div>
            <div><b>إجمالي القشاط</b>$ ${money(frm.doc.edge_cost_usd)}</div>
        </div>`;
    }

    function measurementTable(frm) {
        return `<table class="table measurements">
            <thead><tr><th>#</th><th>النوع</th><th>العرض</th><th>الطول</th><th>العدد</th><th>القشاط المخصص</th><th>ملاحظات</th></tr></thead>
            <tbody>${measurementRowsHtml(frm)}</tbody>
        </table>`;
    }

    function printCss(mode) {
        const theme = printThemeApi();
        return theme && typeof theme.css === "function"
            ? theme.css(mode, shapePrintCss())
            : shapePrintCss();
    }

    function documentHtml(frm, mode, printIdentity = null) {
        const api = printIdentityApi();
        const identity = printIdentity || (api && typeof api.fallback === "function" ? api.fallback() : {});
        const lines = mode === "invoice" ? invoiceLines(frm) : [];
        const total = mode === "invoice" ? invoiceTotal(frm, lines) : 0;
        const generated = frappe.datetime ? frappe.datetime.now_datetime() : new Date().toISOString();
        return `<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8"><title>${mode === "invoice" ? "فاتورة" : "قياسات"} الطلب ${esc(frm.doc.name || "")}</title><style>${printCss(mode)}</style></head><body>
            ${sharedHeader(frm, mode, identity)}
            ${sharedInfo(frm)}
            ${mode === "invoice" ? invoiceSummary(frm) : ""}
            <div class="title">جدول القياسات</div>
            ${measurementTable(frm)}
            ${mode === "invoice" ? `
                <div class="title">تفاصيل الفاتورة</div>
                <table class="table invoice"><thead><tr><th>#</th><th class="right">البيان</th><th>الكمية</th><th>الوحدة</th><th>سعر الوحدة $</th><th>الإجمالي $</th></tr></thead><tbody>${invoiceRowsHtml(lines)}</tbody></table>
                <div class="total"><span>الإجمالي النهائي</span><span>$ ${money(total)}</span></div>` : ""}
            ${frm.doc.order_notes ? `<div class="order-note"><b>ملاحظات الطلب:</b> ${esc(frm.doc.order_notes)}</div>` : ""}
            <div class="footer"><span>رقم الطلب: ${esc(frm.doc.name || "مسودة")}</span><span>تاريخ الطباعة: ${esc(generated)}</span></div>
        </body></html>`;
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
                if (!win) throw new Error("Print window unavailable");
                win.addEventListener("afterprint", cleanup, { once: true });
                setTimeout(() => { win.focus(); win.print(); }, 100);
            } catch (error) {
                console.error("Unified order print failed", error);
                cleanup();
                frappe.msgprint("تعذر تشغيل الطباعة. أعد تحميل الصفحة ثم حاول مرة أخرى.");
            }
        };
        frame.srcdoc = html;
        document.body.appendChild(frame);
        setTimeout(cleanup, 120000);
    }

    async function printDocument(frm, mode) {
        const documentIdentity = captureIdentity(frm);
        if (!isCurrent(frm, documentIdentity)) return false;
        const [, printIdentity] = await Promise.all([
            ensureProfiles(frm),
            resolvePrintIdentity(),
        ]);
        if (!isCurrent(frm, documentIdentity)) return false;
        printHtml(documentHtml(frm, mode, printIdentity));
        return true;
    }

    function bindPrintInterception() {
        if (document._dcoUnifiedDocumentPrintBound) return;
        document._dcoUnifiedDocumentPrintBound = true;
        document.addEventListener("click", event => {
            const frm = activeFrm;
            const identity = activeIdentity;
            if (!frm || !isCurrent(frm, identity)) return;
            const invoiceButton = event.target.closest(".dco-print-customer-invoice");
            const measurementButton = event.target.closest(".dco-print-measurements,.dco-entry-window-print");
            if (!invoiceButton && !measurementButton) return;
            event.preventDefault();
            event.stopImmediatePropagation();
            printDocument(frm, invoiceButton ? "invoice" : "measurements").catch(error => {
                console.error("Order document preparation failed", error);
                frappe.msgprint("تعذر تجهيز المستند للطباعة. أعد تحميل الصفحة ثم حاول مرة أخرى.");
            });
        }, true);
    }

    function schedule(frm) {
        activeFrm = frm;
        activeIdentity = captureIdentity(frm);
        bindPrintInterception();
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
    });

    window.AlmdinaOrderDocumentPrint = Object.freeze({
        printInvoice(frm) { return printDocument(frm, "invoice"); },
        printMeasurements(frm) { return printDocument(frm, "measurements"); },
        html: documentHtml,
    });
})();
