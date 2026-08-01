"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order_financial_documents_ux.js"
    ),
    "utf8"
);

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function payload(kind, orderName) {
    return {
        kind,
        order_name: orderName,
        title: kind === "internal_cost_report" ? "تقرير التكلفة الداخلي" : "عرض سعر الطلب",
        subtitle: "اختبار",
        classification: kind === "internal_cost_report" ? "داخلي — لا يسلّم للزبون" : undefined,
        meta: [{ label: "رقم الطلب", value: orderName }],
        summary: [{ label: "الإجمالي", value: 10, format: "money" }],
        measurements: [],
        lines: [],
        cost_breakdown: [],
        operations: [],
        special_prices: [],
        totals: [{ label: "الإجمالي", value_usd: 10 }],
        generated_by: "tester@example.com",
        generated_on: "2026-08-01 15:00:00",
        source_revision: 1,
    };
}

function load() {
    const calls = [];
    const prints = [];
    const capabilities = new Set([
        "view_costs",
        "print_customer_invoice",
        "print_internal_cost_report",
    ]);
    const handlers = {};

    const fakeDocument = {
        body: {
            appendChild(frame) {
                setImmediate(() => frame.onload && frame.onload());
            },
        },
        getElementById() {
            return null;
        },
        createElement(tag) {
            assert.equal(tag, "iframe");
            return {
                id: "",
                style: {},
                srcdoc: "",
                setAttribute() {},
                remove() {},
                contentWindow: {
                    addEventListener() {},
                    focus() {},
                    print() {
                        prints.push("printed");
                    },
                },
            };
        },
    };

    const fakeWindow = {
        AlmdinaPermissions: {
            can(capability) {
                return capabilities.has(capability);
            },
        },
        AlmdinaDocumentContext: {
            capture(frm) {
                return frm.doc.name;
            },
            isCurrent(frm, identity) {
                return frm.doc.name === identity;
            },
        },
    };

    const fakeFrappe = {
        utils: { escape_html: escapeHtml },
        ui: {
            form: {
                on(doctype, config) {
                    assert.equal(doctype, "Door Cutting Order");
                    Object.assign(handlers, config);
                },
            },
        },
        call(options) {
            calls.push(options);
            const kind = options.method.includes("internal_cost_report")
                ? "internal_cost_report"
                : "customer_invoice";
            return Promise.resolve({
                message: payload(kind, options.args.order_name),
            });
        },
        msgprint() {},
    };

    const context = vm.createContext({
        window: fakeWindow,
        document: fakeDocument,
        frappe: fakeFrappe,
        __: value => value,
        console,
        Promise,
        Error,
        Object,
        String,
        Number,
        Boolean,
        Set,
        Map,
        Array,
        Math,
        JSON,
        setImmediate,
        setTimeout(fn, delay) {
            if (delay < 1000) setImmediate(fn);
            return 1;
        },
        requestAnimationFrame(fn) {
            setImmediate(fn);
        },
        MutationObserver: class {
            observe() {}
            disconnect() {}
        },
        $() {
            throw new Error("jQuery should not be needed for direct secure printing");
        },
    });

    vm.runInContext(source, context, {
        filename: "door_cutting_order_financial_documents_ux.js",
    });

    return { fakeWindow, calls, prints, capabilities, handlers };
}

async function main() {
    const runtime = load();
    const frm = {
        doc: { name: "DCO-TEST-0001" },
        is_new() {
            return false;
        },
    };

    await runtime.fakeWindow.AlmdinaFinancialDocuments.printCustomerInvoice(frm);
    assert.equal(runtime.calls.length, 1);
    assert.match(runtime.calls[0].method, /get_customer_invoice_document$/);
    assert.equal(runtime.calls[0].args.order_name, frm.doc.name);

    await runtime.fakeWindow.AlmdinaFinancialDocuments.printInternalCostReport(frm);
    assert.equal(runtime.calls.length, 2);
    assert.match(runtime.calls[1].method, /get_internal_cost_report_document$/);
    assert.equal(runtime.calls[1].args.order_name, frm.doc.name);

    await new Promise(resolve => setImmediate(resolve));
    assert.equal(runtime.prints.length, 2);

    const customerHtml = runtime.fakeWindow.AlmdinaFinancialDocuments.documentHtml(
        payload("customer_invoice", frm.doc.name)
    );
    const internalHtml = runtime.fakeWindow.AlmdinaFinancialDocuments.documentHtml(
        payload("internal_cost_report", frm.doc.name)
    );
    assert.doesNotMatch(customerHtml, /لا يسلّم للزبون/);
    assert.match(internalHtml, /لا يسلّم للزبون/);

    runtime.capabilities.delete("print_internal_cost_report");
    await assert.rejects(
        runtime.fakeWindow.AlmdinaFinancialDocuments.printInternalCostReport(frm),
        /Missing capability: print_internal_cost_report/
    );
    assert.equal(runtime.calls.length, 2);

    console.log("Secure financial document simulation passed");
}

main().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
