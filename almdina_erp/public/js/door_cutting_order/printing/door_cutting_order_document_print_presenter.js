(() => {
    "use strict";

    const FRAME_ID = "dco-unified-document-print-frame";
    // Invariant: customer invoice = the exact measurement document + authorized quote details at the end.
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
        if (value === "Extra") return "إضافية";
        return "عادية";
    }

    function rowHasDrawing(row) {
        const renderer = shapePrintApi();
        return Boolean(renderer && renderer.hasVisual(row));
    }

    function extraAddonLabels(row) {
        if (!row || (row.piece_type || "Regular") !== "Extra") return [];
        return [
            ["extra_double", "دبل قشاط"],
            ["extra_full_door_double", "دبل كامل الدرفة"],
            ["extra_liner", "Liner"],
            ["extra_back_groove", "فرزة ظهر"],
            ["extra_recessed_handle_cutout", "حفر مسكة غطس"],
        ].filter(([fieldname]) => Number(row[fieldname] || 0)).map(([, label]) => label);
    }

    function notesCellHtml(row) {
        const renderer = shapePrintApi();
        const addons = extraAddonLabels(row);
        const summary = addons.length ? `إضافات: ${addons.join("، ")}` : "";
        const notes = summary && row.notes ? `${summary} — ${row.notes}` : (summary || row.notes);
        return renderer
            ? renderer.notesCell(row, notes, {
                label: `رسمة الدرفة رقم ${row.index}`,
                caption: `رسمة الدرفة ${row.index}`,
            })
            : esc(notes || "—");
    }

    function shapePrintCss() {
        const renderer = shapePrintApi();
        return renderer ? renderer.css : "";
    }

    function authoritativeDocumentation(payload) {
        const result = new Map();
        const measurements = Array.isArray(payload && payload.measurements)
            ? payload.measurements
            : [];
        measurements.forEach(row => {
            const pieceName = String(row && row.piece_name || "").trim();
            if (!pieceName) return;
            result.set(pieceName, String(row.special_shape_drawing_json || ""));
        });
        return result;
    }

    function rows(frm, payload = null) {
        const module = edgeBandingApi();
        const documentation = authoritativeDocumentation(payload);
        return (frm.doc.pieces || []).map((source, index) => {
            const pieceName = String(source && source.name || "").trim();
            const hasAuthoritativeDocumentation = pieceName && documentation.has(pieceName);
            const printable = hasAuthoritativeDocumentation
                ? {
                    ...source,
                    special_shape_drawing_json: documentation.get(pieceName),
                    drawing_json: documentation.get(pieceName),
                }
                : source;
            return {
                ...printable,
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
            };
        });
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

    function measurementRowsHtmlWithPayload(frm, payload) {
        return rows(frm, payload).map(row => {
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

    function measurementRowsHtml(frm) {
        return measurementRowsHtmlWithPayload(frm, null);
    }

    function sharedHeader(frm, printIdentity) {
        const theme = printThemeApi();
        if (!theme || typeof theme.headerHtml !== "function") {
            throw new Error("Unified factory print header is unavailable");
        }
        const reference = frm.doc.name || "مسودة";
        const date = String(frm.doc.order_date || "").trim();
        return theme.headerHtml(printIdentity, {
            title: "جدول قياسات الطلب",
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

    function measurementTableWithPayload(frm, payload) {
        return `<table class="table measurements">
            <thead><tr><th>#</th><th>النوع</th><th>العرض</th><th>الطول</th><th>العدد</th><th>القشاط المخصص</th><th>ملاحظات</th></tr></thead>
            <tbody>${measurementRowsHtmlWithPayload(frm, payload)}</tbody>
        </table>`;
    }

    function measurementTable(frm) {
        return measurementTableWithPayload(frm, null);
    }

    function orderNotesHtml(frm) {
        return frm.doc.order_notes
            ? `<div class="order-note"><b>ملاحظات الطلب:</b> ${esc(frm.doc.order_notes)}</div>`
            : "";
    }

    function measurementDocumentBodyWithPayload(frm, payload) {
        return `
            ${sharedInfo(frm)}
            <div class="title">جدول القياسات</div>
            ${measurementTableWithPayload(frm, payload)}
            ${orderNotesHtml(frm)}`;
    }

    function measurementDocumentBody(frm) {
        return measurementDocumentBodyWithPayload(frm, null);
    }

    function quoteLineNote(line) {
        const note = String(line.note || "").trim();
        if (!note) return "";
        if (line.type !== "edge") return note;
        if (note.includes("من القشاط الافتراضي")) return "";
        return note.replace("يتضمن أطرافًا مخصصة", "تخصيص استثنائي");
    }

    function quoteRowsHtml(payload) {
        const lines = Array.isArray(payload && payload.lines) ? payload.lines : [];
        if (!lines.length) {
            return '<tr><td colspan="6">لا توجد بنود سعر متاحة لهذا الطلب.</td></tr>';
        }
        return lines.map((line, index) => {
            const note = quoteLineNote(line);
            const rate = line.rate_usd;
            return `<tr>
                <td>${index + 1}</td>
                <td class="right invoice-description"><b>${esc(line.description)}</b>${note ? `<span class="line-note">${esc(note)}</span>` : ""}</td>
                <td>${quantity(line.quantity)}</td>
                <td>${esc(line.unit)}</td>
                <td>${rate || rate === 0 ? money(rate) : "—"}</td>
                <td><b>${money(line.amount_usd)}</b></td>
            </tr>`;
        }).join("");
    }

    function quoteTotal(payload) {
        const totals = Array.isArray(payload && payload.totals) ? payload.totals : [];
        const explicit = totals.find(item => item && item.value_usd !== undefined && item.value_usd !== null);
        if (explicit) return number(explicit.value_usd);
        const lines = Array.isArray(payload && payload.lines) ? payload.lines : [];
        return lines.reduce((sum, line) => sum + number(line.amount_usd), 0);
    }

    function quoteDetailsHtml(payload) {
        return `<section class="quote-details">
            <div class="title quote-title">تفاصيل عرض السعر</div>
            <table class="table invoice"><thead><tr><th>#</th><th class="right">البيان</th><th>الكمية</th><th>الوحدة</th><th>سعر الوحدة $</th><th>الإجمالي $</th></tr></thead><tbody>${quoteRowsHtml(payload)}</tbody></table>
            <div class="total"><span>الإجمالي النهائي</span><span>$ ${money(quoteTotal(payload))}</span></div>
        </section>`;
    }

    function printCss() {
        const theme = printThemeApi();
        return theme && typeof theme.css === "function"
            ? theme.css("measurements", shapePrintCss())
            : shapePrintCss();
    }

    function documentHtml(frm, mode = "measurements", printIdentity = null, quotePayload = null) {
        const api = printIdentityApi();
        const identity = printIdentity || (api && typeof api.fallback === "function" ? api.fallback() : {});
        const invoice = mode === "invoice";
        const generated = frappe.datetime ? frappe.datetime.now_datetime() : new Date().toISOString();
        return `<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8"><title>${invoice ? "فاتورة الزبون" : "قياسات"} الطلب ${esc(frm.doc.name || "")}</title><style>${printCss()}</style></head><body>
            ${sharedHeader(frm, identity)}
            ${invoice ? measurementDocumentBodyWithPayload(frm, quotePayload) : measurementDocumentBody(frm)}
            ${invoice ? quoteDetailsHtml(quotePayload || {}) : ""}
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

    async function printMeasurements(frm) {
        const documentIdentity = captureIdentity(frm);
        if (!isCurrent(frm, documentIdentity)) return false;
        const [, printIdentity] = await Promise.all([
            ensureProfiles(frm),
            resolvePrintIdentity(),
        ]);
        if (!isCurrent(frm, documentIdentity)) return false;
        printHtml(documentHtml(frm, "measurements", printIdentity));
        return true;
    }

    async function printAuthorizedInvoice(frm, payload) {
        const documentIdentity = captureIdentity(frm);
        if (!isCurrent(frm, documentIdentity)) return false;
        if (!payload || payload.kind !== "customer_invoice" || payload.order_name !== frm.doc.name) {
            throw new Error("Authorized customer invoice payload does not match the active order");
        }
        const [, printIdentity] = await Promise.all([
            ensureProfiles(frm),
            resolvePrintIdentity(),
        ]);
        if (!isCurrent(frm, documentIdentity)) return false;
        printHtml(documentHtml(frm, "invoice", printIdentity, payload));
        return true;
    }

    function requestAuthorizedInvoice(frm) {
        const financial = window.AlmdinaFinancialDocuments;
        if (financial && typeof financial.printCustomerInvoice === "function") {
            return financial.printCustomerInvoice(frm);
        }
        frappe.msgprint("تعذر تجهيز فاتورة الزبون. أعد تحميل الصفحة ثم حاول مرة أخرى.");
        return Promise.resolve(false);
    }

    function printInvoice(frm) {
        return requestAuthorizedInvoice(frm);
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
            const action = invoiceButton ? printInvoice(frm) : printMeasurements(frm);
            Promise.resolve(action).catch(error => {
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
        printInvoice,
        printAuthorizedInvoice,
        printMeasurements,
        html: documentHtml,
    });
})();
