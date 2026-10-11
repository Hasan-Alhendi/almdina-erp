"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../../public/js");

function read(relativePath) {
    return fs.readFileSync(path.join(root, relativePath), "utf8");
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

const french = {
    "Special door": "Porte spéciale",
    "Add-ons": "Options",
    "Liner": "Doublure",
    "Back groove": "Rainure",
    "Door piece drawing {0}": "Dessin {0}",
    "Not specified": "Non précisé",
    "Side": "Côté",
    "All around": "Tout autour",
    "No customization": "Aucune personnalisation",
    "Draft": "Brouillon",
    "Customer": "Client",
    "Phone": "Téléphone",
    "Board": "Panneau",
    "Edge color": "Couleur de chant",
    "Cutting machine": "Machine de coupe",
    "Door count": "Nombre de portes",
    "Order notes:": "Notes de commande :",
    "Measurements table": "Tableau des mesures",
    "Order measurements table": "Tableau des mesures de commande",
    "Custom": "Sur mesure",
    "Custom edge banding": "Chant personnalisé",
    "Type": "Type",
    "Width": "Largeur",
    "Length": "Longueur",
    "Qty": "Qté",
    "Notes": "Notes",
    "Quotation details": "Détails du devis",
    "Description": "Description",
    "Quantity": "Quantité",
    "Unit": "Unité",
    "Unit price $": "Prix unitaire $",
    "Total $": "Total $",
    "Final total": "Total final",
    "No price lines are available for this order.": "Aucune ligne de prix.",
    "Order number:": "Numéro :",
    "Printed on:": "Imprimé le :",
    "Customer invoice": "Facture client",
    "Measurements": "Mesures",
    "Exceptional customization": "Personnalisation exceptionnelle",
    "Double edge banding": "Double chant",
    "Full door double": "Double porte complète",
    "Recessed handle cutout": "Poignée encastrée",
    "Regular door": "Porte standard",
    "This documents the customer request and is not a manufacturing file.": "Ceci documente la demande.",
};

const arabic = {
    "Customer": "الزبون",
    "Add-ons": "إضافات",
    "Liner": "لاينر",
    "Back groove": "فرزة ظهر",
    "Side": "ضلع",
    "Custom": "مخصص",
    "Measurements table": "جدول القياسات",
    "Order measurements table": "جدول قياسات الطلب",
};

let active = french;
let pageDir = "ltr";

function translate(message, replacements) {
    const text = Object.prototype.hasOwnProperty.call(active, message) ? active[message] : message;
    if (!replacements) return text;
    return String(text).replace("{0}", String(replacements[0]));
}

const fakeWindow = {
    frappe: {
        boot: { lang: "fr" },
        utils: { escape_html: escapeHtml },
        datetime: { now_datetime: () => "2026-10-11 12:00:00" },
        ui: { form: { on() {} } },
        msgprint() {},
    },
};
fakeWindow.window = fakeWindow;

const context = vm.createContext({
    window: fakeWindow,
    document: {
        documentElement: {
            lang: "fr",
            getAttribute(name) {
                return name === "dir" ? pageDir : "fr";
            },
        },
        getElementById() { return null; },
        addEventListener() {},
    },
    frappe: fakeWindow.frappe,
    __: translate,
    console,
    Object,
    Map,
    Set,
    Array,
    Number,
    String,
    Boolean,
    Promise,
    Error,
});

vm.runInContext(read("almdina_locale.js"), context, { filename: "almdina_locale.js" });
vm.runInContext(read("door_cutting_order/printing/door_cutting_order_document_print_theme.js"), context, { filename: "theme.js" });
vm.runInContext(read("door_cutting_order/printing/door_cutting_order_document_print_presenter.js"), context, { filename: "presenter.js" });

fakeWindow.AlmdinaShapePrint = {
    hasVisual: () => true,
    css: "",
    notesCell(row, notes, options) {
        return `<figure data-caption="${escapeHtml(options.caption)}" data-label="${escapeHtml(options.label)}">${escapeHtml(notes)}</figure>`;
    },
};
fakeWindow.AlmdinaMultiEdgeBanding = {
    details() {
        return [
            { custom: true, edge_type: "PVC 1mm", side_label: "" },
            { custom: true, edge_type: "PVC 1mm", side_label: "" },
        ];
    },
};

const form = {
    doc: {
        name: "26-00089",
        customer: "أحمد",
        order_date: "2026-09-23",
        board_description: "لوح أبيض",
        edge_color: "أسود",
        order_cutting_machine: "CNC",
        order_notes: "تسليم بعد الظهر",
        pieces: [{
            piece_type: "Special",
            width_cm: 80,
            length_cm: 210,
            qty: 2,
            notes: "مقبض",
            extra_liner: 1,
            extra_back_groove: 1,
        }],
    },
};

const quote = {
    kind: "customer_invoice",
    lines: [
        {
            type: "material",
            description: "ألواح MDF",
            quantity: 2,
            unit: "لوح",
            rate_usd: 12.5,
            amount_usd: 25,
            note: "ملاحظة السعر",
        },
        {
            type: "edge",
            description: "PVC 1mm",
            quantity: 4,
            unit: "m",
            rate_usd: 1,
            amount_usd: 4,
            note: "يتضمن أطرافًا مخصصة",
        },
        {
            type: "edge",
            description: "Default edge",
            quantity: 1,
            unit: "m",
            rate_usd: 1,
            amount_usd: 1,
            note: "طول من القشاط الافتراضي",
        },
    ],
    totals: [{ value_usd: 29 }],
};

const frenchHtml = fakeWindow.AlmdinaOrderDocumentPrint.html(
    form,
    "invoice",
    { print_factory_name: "Almadina" },
    quote,
    "0944123456"
);

assert.match(frenchHtml, /lang="fr"/);
assert.match(frenchHtml, /dir="ltr"/);
assert.match(frenchHtml, /direction:ltr/);
assert.match(frenchHtml, /Client/);
assert.match(frenchHtml, /Téléphone/);
assert.match(frenchHtml, /Panneau/);
assert.match(frenchHtml, /Couleur de chant/);
assert.match(frenchHtml, /Porte spéciale/);
assert.match(frenchHtml, /<em>Sur mesure<\/em>/);
assert.match(frenchHtml, /Dessin 1/);
assert.match(frenchHtml, /Options: Doublure, Rainure/);
assert.match(frenchHtml, /Côté, Côté/);
assert.match(frenchHtml, /Tableau des mesures/);
assert.match(frenchHtml, /Notes de commande :/);
assert.match(frenchHtml, /Personnalisation exceptionnelle/);
assert.match(frenchHtml, /Détails du devis/);
assert.match(frenchHtml, /أحمد/);
assert.match(frenchHtml, /لوح أبيض/);
assert.match(frenchHtml, /أسود/);
assert.match(frenchHtml, /تسليم بعد الظهر/);
assert.match(frenchHtml, /مقبض/);
assert.match(frenchHtml, /ألواح MDF/);
assert.match(frenchHtml, /ملاحظة السعر/);
assert.match(frenchHtml, /PVC 1mm/);
assert.match(frenchHtml, /CNC/);
assert.doesNotMatch(frenchHtml, /،/);
assert.doesNotMatch(frenchHtml, /خاصة|إضافات|على الداير|لا يوجد تخصيص|جدول القياسات|الزبون|الهاتف|لون القشاط|عدد الدرف|ملاحظات الطلب|غير محدد|ضلع|مسودة|تفاصيل عرض السعر|من القشاط الافتراضي|يتضمن أطرافًا مخصصة|تخصيص استثنائي/);

active = arabic;
pageDir = "rtl";
fakeWindow.frappe.boot.lang = "ar";
const arabicHtml = fakeWindow.AlmdinaOrderDocumentPrint.html(
    form,
    "measurements",
    { print_factory_name: "Almadina" },
    null,
    "0944123456"
);

assert.match(arabicHtml, /lang="ar"/);
assert.match(arabicHtml, /dir="rtl"/);
assert.match(arabicHtml, /direction:rtl/);
assert.match(arabicHtml, /<b>الزبون<\/b>/);
assert.match(arabicHtml, /<em>مخصص<\/em>/);
assert.match(arabicHtml, /إضافات: لاينر، فرزة ظهر/);
assert.match(arabicHtml, /جدول القياسات/);
assert.match(arabicHtml, /مقبض/);
assert.match(arabicHtml, /PVC 1mm/);
assert.doesNotMatch(arabicHtml, /<em>Custom<\/em>/);

console.log("Browser print locale simulation passed");
