"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/almdina_locale.js"),
    "utf8"
);

function loadLocale({ lang, dir, bootLang, translator }) {
    const html = { lang: lang || "", dir: dir || "" };
    const fakeWindow = {
        frappe: { boot: { lang: bootLang || "" } },
        __: translator || ((message, replacements) => {
            if (!replacements) return message;
            return message.replace("{0}", String(replacements[0]));
        }),
    };
    fakeWindow.window = fakeWindow;
    const context = vm.createContext({
        window: fakeWindow,
        document: { documentElement: {
            lang: html.lang,
            getAttribute(name) {
                return name === "dir" ? html.dir : html.lang;
            },
        } },
        Object,
        Set,
        String,
    });
    vm.runInContext(source, context, { filename: "almdina_locale.js" });
    return fakeWindow.AlmdinaLocale;
}

const arabic = loadLocale({ lang: "ar", dir: "rtl", bootLang: "ar" });
assert.equal(arabic.currentLanguage(), "ar");
assert.equal(arabic.direction(), "rtl");
assert.equal(arabic.isRTL(), true);
assert.deepEqual(JSON.parse(JSON.stringify(arabic.context())), {
    language: "ar",
    direction: "rtl",
    isRTL: true,
});

const french = loadLocale({ lang: "fr", dir: "ltr", bootLang: "fr" });
assert.equal(french.currentLanguage(), "fr");
assert.equal(french.direction(), "ltr");
assert.equal(french.isRTL(), false);
assert.equal(french.direction("fr"), "ltr");
assert.equal(french.isRTL("ar"), true);
assert.deepEqual(JSON.parse(JSON.stringify(french.context())), {
    language: "fr",
    direction: "ltr",
    isRTL: false,
});

const browserIgnored = loadLocale({ lang: "en-US", dir: "rtl", bootLang: "ar" });
assert.equal(browserIgnored.currentLanguage(), "ar");
assert.equal(browserIgnored.direction(), "rtl");

const derived = loadLocale({ lang: "", dir: "", bootLang: "fr" });
assert.equal(derived.currentLanguage(), "fr");
assert.equal(derived.direction(), "ltr");
assert.equal(derived.isRTL(), false);

let seen = null;
const delegated = loadLocale({
    lang: "ar",
    dir: "rtl",
    bootLang: "ar",
    translator(message, replacements) {
        seen = { message, replacements };
        return "مترجم";
    },
});
assert.equal(delegated.translate("Piece {0}", ["12"]), "مترجم");
assert.deepEqual(JSON.parse(JSON.stringify(seen)), { message: "Piece {0}", replacements: ["12"] });

console.log("Almdina locale context simulation passed");
