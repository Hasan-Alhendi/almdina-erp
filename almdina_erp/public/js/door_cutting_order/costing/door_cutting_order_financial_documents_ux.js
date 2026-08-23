(() => {
    "use strict";

    const PRINT_FRAME_ID = "dco-secure-financial-print-frame";
    const CUSTOMER_CLASS = "dco-secure-print-customer-invoice";
    const INTERNAL_CLASS = "dco-secure-print-internal-cost-report";
    const LEGACY_CUSTOMER_CLASS = "dco-print-customer-invoice";
    let activeFrm = null;

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

    function qty(value) {
        return number(value).toLocaleString("en-US", { maximumFractionDigits: 3 });
    }

    function money(value) {
        return number(value).toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    function documentContext() {
        return window.AlmdinaDocumentContext;
    }

    function printThemeApi() {
        return window.AlmdinaOrderDocumentPrintTheme || null;
    }

    function printIdentityApi() {
        return window.AlmdinaFactoryPrintIdentity || null;
    }

    function customerPrintApi() {
        return window.AlmdinaOrderDocumentPrint || null;
    }

    async function resolvePrintIdentity() {
        const api = printIdentityApi();
        if (api && typeof api.get === "function") {
            return Promise.resolve(api.get());
        }
        return api && typeof api.fallback === "function" ? api.fallback() : {};
    }

    function formRoot(frm) {
        return $(frm.wrapper || frm.page?.wrapper || document.body);
    }

    function costActions(frm) {
        const field = frm.fields_dict.order_cost_invoice_html;
        if (!field || !field.$wrapper) return $();
        return field.$wrapper.find(".dco-cost-actions");
    }

    function documentMethod(kind) {
        return kind === "internal_cost_report"
            ? "almdina_erp.almdina_erp.services.cost_document_service.get_internal_cost_report_document"
            : "almdina_erp.almdina_erp.services.cost_document_service.get_customer_invoice_document";
    }

    function requiredCapability(kind) {
        return kind === "internal_cost_report"
            ? "print_internal_cost_report"
            : "print_customer_invoice";
    }

    function formatSummaryValue(item) {
        if (item.format === "money") return `$ ${money(item.value)}`;
        if (item.format === "percent") return `${qty(item.value)}%`;
        return esc(item.value ?? "—");
    }

    function metaHtml(payload) {
        return `<div class="financial-meta">${(payload.meta || []).map(item => `
            <div class="financial-meta-item">
                <span>${esc(item.label)}</span>
                <b>${esc(item.value)}</b>
            </div>`).join("")}</div>`;
    }

    function summaryHtml(payload) {
        return `<div class="financial-summary internal">${(payload.summary || []).map(item => `
            <div class="financial-summary-card">
                <span>${esc(item.label)}</span>
                <b>${formatSummaryValue(item)}</b>
            </div>`).join("")}</div>`;
    }

    function costBreakdownHtml(rows) {
        if (!rows || !rows.length) return "";
        const total = rows.reduce((sum, row) => sum + number(row.amount_usd), 0);
        return `
            <section>
                <h2>تفصيل التكلفة التشغيلية</h2>
                <table class="compact"><thead><tr><th class="right">البند</th><th>القيمة $</th></tr></thead><tbody>
                    ${rows.map(row => `<tr><td class="right">${esc(row.label)}</td><td>${money(row.amount_usd)}</td></tr>`).join("")}
                    <tr class="strong"><td class="right">مجموع البنود التفصيلية</td><td>${money(total)}</td></tr>
                </tbody></table>
            </section>`;
    }

    function operationsHtml(rows) {
        if (!rows || !rows.length) return "";
        return `
            <section>
                <h2>مؤشرات التشغيل والهدر</h2>
                <div class="operations-grid">${rows.map(row => `
                    <div><span>${esc(row.label)}</span><b>${esc(row.value)}</b></div>
                `).join("")}</div>
            </section>`;
    }

    function specialPricesHtml(rows) {
        if (!rows || !rows.length) return "";
        return `
            <section>
                <h2>مراجعة أسعار الدرف الخاصة</h2>
                <table><thead><tr>
                    <th>#</th><th>العدد</th><th>التقديري / وحدة $</th><th>المعتمد / وحدة $</th>
                    <th>النهائي / وحدة $</th><th>الفرق الإجمالي $</th><th>الحالة</th>
                    <th>اعتمده</th><th>تاريخ الاعتماد</th><th class="right">ملاحظة</th>
                </tr></thead><tbody>
                    ${rows.map(row => `<tr>
                        <td>${esc(row.piece_no)}</td><td>${qty(row.quantity)}</td>
                        <td>${money(row.estimated_unit_usd)}</td><td>${money(row.approved_unit_usd)}</td>
                        <td>${money(row.final_unit_usd)}</td><td>${money(row.variance_total_usd)}</td>
                        <td>${esc(row.status)}</td><td>${esc(row.approved_by)}</td>
                        <td>${esc(row.approved_on)}</td><td class="right">${esc(row.note)}</td>
                    </tr>`).join("")}
                </tbody></table>
            </section>`;
    }

    function totalsHtml(rows) {
        if (!rows || !rows.length) return "";
        return `<div class="financial-totals">${rows.map(row => `
            <div><span>${esc(row.label)}</span><b>$ ${money(row.value_usd)}</b></div>
        `).join("")}</div>`;
    }

    function printHeaderHtml(payload, printIdentity) {
        const theme = printThemeApi();
        if (!theme || typeof theme.headerHtml !== "function") {
            throw new Error("Unified factory print header is unavailable");
        }
        const metaParts = [payload.order_name, payload.subtitle]
            .map(value => String(value || "").trim())
            .filter(Boolean);
        return theme.headerHtml(printIdentity, {
            title: payload.title,
            meta: metaParts.join(" · "),
            badge: payload.classification || "داخلي",
            badgeClass: "internal",
        });
    }

    function printCss() {
        const theme = printThemeApi();
        if (!theme || typeof theme.headerCss !== "function") {
            throw new Error("Unified factory print header styles are unavailable");
        }
        return `
            @page{size:A4 landscape;margin:11mm}
            *{box-sizing:border-box}
            body{font-family:Tahoma,Arial,sans-serif;color:#172033;margin:0;direction:rtl;font-size:10px;-webkit-print-color-adjust:exact;print-color-adjust:exact}
            ${theme.headerCss()}
            .financial-meta,.financial-summary{display:grid;gap:7px;margin-top:10px}
            .financial-meta{grid-template-columns:repeat(3,minmax(0,1fr))}
            .financial-summary.internal{grid-template-columns:repeat(5,minmax(0,1fr))}
            .financial-meta-item,.financial-summary-card,.operations-grid>div{border:1px solid #cfd6de;border-radius:7px;padding:7px 8px;background:#fff}
            .financial-meta-item span,.financial-summary-card span,.operations-grid span{display:block;color:#697582;font-size:8px;margin-bottom:3px}
            .financial-meta-item b,.financial-summary-card b,.operations-grid b{font-size:11px;word-break:break-word}
            .financial-summary-card{background:#f7fafc}
            section{margin-top:12px;break-inside:avoid} h2{font-size:13px;margin:0 0 6px;padding:6px 8px;background:#eef2f6;border-right:3px solid #273b50}
            table{width:100%;border-collapse:collapse;font-size:9px} th,td{border:1px solid #aeb8c2;padding:4.5px;text-align:center;vertical-align:middle}
            th{background:#edf1f5;font-weight:900} td.right,th.right{text-align:right} td small{display:block;color:#66717d;font-size:7.5px;margin-top:2px;line-height:1.5}
            tr.strong td{font-weight:900;background:#f5f7f9} table.compact{max-width:620px}
            .operations-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}
            .financial-totals{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px;margin-top:12px}
            .financial-totals>div{padding:10px;border:1px solid #273b50;border-radius:8px;background:#f4f7fa}
            .financial-totals span{display:block;font-size:8px;color:#66717d;margin-bottom:4px}.financial-totals b{font-size:14px;direction:ltr;display:block;text-align:right}
            .notes{margin-top:10px;border:1px solid #cfd6de;border-radius:7px;padding:8px;min-height:34px;line-height:1.7}
            footer{display:flex;justify-content:space-between;gap:12px;margin-top:12px;padding-top:6px;border-top:1px solid #b9c1ca;color:#687481;font-size:8px}
            @media print{section{break-inside:auto}thead{display:table-header-group}tr{break-inside:avoid}}
        `;
    }

    function documentHtml(payload, printIdentity = null) {
        if (!payload || payload.kind !== "internal_cost_report") {
            throw new Error("Customer invoice layout belongs to AlmdinaOrderDocumentPrint");
        }
        const identityApi = printIdentityApi();
        const identity = printIdentity || (
            identityApi && typeof identityApi.fallback === "function"
                ? identityApi.fallback()
                : {}
        );
        return `<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8"><title>${esc(payload.title)} — ${esc(payload.order_name)}</title><style>${printCss()}</style></head><body>
            ${printHeaderHtml(payload, identity)}
            ${metaHtml(payload)}${summaryHtml(payload)}
            ${costBreakdownHtml(payload.cost_breakdown)}
            ${operationsHtml(payload.operations)}
            ${specialPricesHtml(payload.special_prices)}
            ${totalsHtml(payload.totals)}
            ${payload.notes ? `<div class="notes"><b>ملاحظات الطلب:</b> ${esc(payload.notes)}</div>` : ""}
            <footer><span>أنشئ بواسطة: ${esc(payload.generated_by || "—")}</span><span>تاريخ الإنشاء: ${esc(payload.generated_on || "—")}</span><span>المراجعة: ${esc(payload.source_revision || "1")}</span></footer>
        </body></html>`;
    }

    function printHtml(html) {
        document.getElementById(PRINT_FRAME_ID)?.remove();
        const frame = document.createElement("iframe");
        frame.id = PRINT_FRAME_ID;
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
                const printWindow = frame.contentWindow;
                if (!printWindow) throw new Error("Print frame is unavailable");
                printWindow.addEventListener("afterprint", cleanup, { once: true });
                setTimeout(() => {
                    printWindow.focus();
                    printWindow.print();
                }, 100);
            } catch (error) {
                console.error("Secure financial print failed", error);
                cleanup();
                frappe.msgprint(__("تعذر تشغيل الطباعة. أعد تحميل الصفحة ثم حاول مرة أخرى."));
            }
        };
        frame.srcdoc = html;
        document.body.appendChild(frame);
        setTimeout(cleanup, 120000);
    }

    function handledRejection(message) {
        const error = new Error(message);
        error.__almdinaHandled = true;
        return Promise.reject(error);
    }

    function validateCustomerPrices(frm) {
        const costApi = window.AlmdinaOrderCostUX;
        const pending = costApi && typeof costApi.pendingCustomEdgePriceLabels === "function"
            ? costApi.pendingCustomEdgePriceLabels(frm)
            : [];
        if (!pending.length) return true;
        frappe.msgprint(__(
            "لا يمكن طباعة فاتورة غير مكتملة. أدخل أسعار قشاط الدرفات الخاصة ودرفات الزاوية المقصوصة أولًا. المتبقي: {0}."
        ).replace("{0}", pending.join("، ")));
        return false;
    }

    function renderAuthorizedDocument(frm, kind, payload) {
        if (kind === "customer_invoice") {
            const presenter = customerPrintApi();
            if (!presenter || typeof presenter.printAuthorizedInvoice !== "function") {
                throw new Error("Unified customer invoice presenter is unavailable");
            }
            return Promise.resolve(presenter.printAuthorizedInvoice(frm, payload)).then(() => payload);
        }
        return resolvePrintIdentity().then(printIdentity => {
            printHtml(documentHtml(payload, printIdentity));
            return payload;
        });
    }

    function printFinancialDocument(frm, kind) {
        const context = documentContext();
        const identity = context && context.capture(frm);
        if (!context || !context.isCurrent(frm, identity)) {
            return Promise.resolve(null);
        }
        const capability = requiredCapability(kind);
        const canPrint = kind === "customer_invoice"
            ? can(frm, capability)
            : can(frm, "view_costs") && can(frm, capability);
        if (!canPrint) {
            frappe.msgprint(__("ليس لديك صلاحية طباعة هذا المستند."));
            return handledRejection("Missing print capability");
        }
        if (frm.is_new()) {
            frappe.msgprint(__("احفظ الطلب قبل طباعة المستند."));
            return handledRejection("Unsaved order");
        }
        if (kind === "customer_invoice" && !validateCustomerPrices(frm)) {
            return handledRejection("Missing custom edge prices");
        }

        return frappe.call({
            method: documentMethod(kind),
            args: { order_name: frm.doc.name },
            freeze: true,
            freeze_message: kind === "internal_cost_report"
                ? __("جاري تجهيز تقرير التكلفة الداخلي...")
                : __("جاري تجهيز فاتورة الزبون..."),
        }).then(response => {
            if (!context.isCurrent(frm, identity)) return null;
            const payload = response.message || {};
            if (payload.kind !== kind || payload.order_name !== frm.doc.name) {
                throw new Error("Financial document response does not match the active order");
            }
            return renderAuthorizedDocument(frm, kind, payload);
        }).catch(error => {
            console.error("Financial document preparation failed", error);
            throw error;
        });
    }

    function createButton(label, className, primary = false) {
        return $(`<button type="button" class="btn ${primary ? "btn-primary" : "btn-default"} btn-sm ${className}">${esc(label)}</button>`);
    }

    function ensureActionButton(actions, options) {
        const selector = `.${options.className}`;
        const matches = actions.find(selector);
        let action = matches.first();
        matches.slice(1).remove();

        if (!options.visible) {
            action.remove();
            return;
        }
        if (!action.length) {
            action = createButton(options.label, options.className, options.primary);
            actions.append(action);
        }
        action
            .off("click.almdinaFinancialDocuments")
            .on("click.almdinaFinancialDocuments", options.handler);
    }

    function installButtons(frm) {
        const root = formRoot(frm);
        root.find(`.${LEGACY_CUSTOMER_CLASS}`).remove();

        const actions = costActions(frm);
        if (!actions.length) return;

        ensureActionButton(actions, {
            className: CUSTOMER_CLASS,
            label: __("طباعة فاتورة الزبون"),
            primary: true,
            visible: !frm.is_new() && can(frm, "print_customer_invoice"),
            handler: () => {
                printFinancialDocument(frm, "customer_invoice").catch(error => {
                    if (!error || !error.__almdinaHandled) {
                        console.error("Customer invoice action failed", error);
                    }
                });
            },
        });
        ensureActionButton(actions, {
            className: INTERNAL_CLASS,
            label: __("طباعة تقرير التكلفة الداخلي"),
            primary: false,
            visible: can(frm, "view_costs") && !frm.is_new() && can(frm, "print_internal_cost_report"),
            handler: () => {
                printFinancialDocument(frm, "internal_cost_report").catch(error => {
                    if (!error || !error.__almdinaHandled) {
                        console.error("Internal cost report action failed", error);
                    }
                });
            },
        });
    }

    function observeFinancialActions(frm) {
        if (frm.__almdina_financial_observer) {
            frm.__almdina_financial_observer.disconnect();
        }
        const root = formRoot(frm);
        if (!root[0]) return;
        const identity = documentContext().capture(frm);
        let scheduled = false;
        const schedule = () => {
            if (scheduled) return;
            scheduled = true;
            requestAnimationFrame(() => {
                scheduled = false;
                if (documentContext().isCurrent(frm, identity)) installButtons(frm);
            });
        };
        const observer = new MutationObserver(schedule);
        observer.observe(root[0], { childList: true, subtree: true });
        frm.__almdina_financial_observer = observer;
        schedule();
    }

    function resolvedForm(targetFrm) {
        return targetFrm || activeFrm;
    }

    function secureLegacyGlobals(frm) {
        const previous = window.AlmdinaOrderDocumentPrint;
        if (previous && typeof previous === "object" && !previous.__secureFinancialDocuments) {
            window.AlmdinaOrderDocumentPrint = Object.freeze({
                ...previous,
                __secureFinancialDocuments: true,
                printInvoice(targetFrm) {
                    return printFinancialDocument(resolvedForm(targetFrm) || frm, "customer_invoice");
                },
                printInternalCostReport(targetFrm) {
                    return printFinancialDocument(resolvedForm(targetFrm) || frm, "internal_cost_report");
                },
                html(targetFrm, mode) {
                    if (mode === "invoice") {
                        throw new Error("Customer invoice HTML is server-authorized and cannot be built without its quote payload.");
                    }
                    return previous.html(targetFrm, mode);
                },
            });
        }
    }

    function apply(frm) {
        activeFrm = frm;
        secureLegacyGlobals(frm);
        observeFinancialActions(frm);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) {
            setTimeout(() => apply(frm), 0);
        },
        refresh(frm) {
            setTimeout(() => apply(frm), 0);
        },
    });

    window.AlmdinaFinancialDocuments = Object.freeze({
        apply,
        documentHtml,
        printCustomerInvoice(frm) {
            return printFinancialDocument(resolvedForm(frm), "customer_invoice");
        },
        printInternalCostReport(frm) {
            return printFinancialDocument(resolvedForm(frm), "internal_cost_report");
        },
    });
})();
