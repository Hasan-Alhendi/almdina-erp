(() => {
    "use strict";

    function isArabic() {
        const lang = String(
            (frappe.boot && frappe.boot.lang) ||
            (frappe.boot && frappe.boot.user && frappe.boot.user.language) ||
            document.documentElement.lang ||
            ""
        ).toLowerCase();
        return lang === "ar" || lang.startsWith("ar-");
    }

    if (!isArabic()) return;

    // These values are generated/stored as stable English machine keys or were
    // frozen into old approved snapshots before the Arabic operator layer was
    // completed. Translate display text only; never mutate document values.
    const replacements = [
        ["Auto اختار: ", "تلقائي - تم اختيار: "],
        ["Remnant First + ", "استخدام البقايا أولًا + "],
        ["No full board required", "لا حاجة إلى لوح جديد"],
        ["MaxRects - Best Short Side", "ترتيب المستطيلات - أفضل ضلع قصير"],
        ["MaxRects - Best Area", "ترتيب المستطيلات - أفضل استغلال للمساحة"],
        ["MaxRects - Bottom Left", "ترتيب المستطيلات - من أسفل اليسار"],
        ["MaxRects - Contact Point", "ترتيب المستطيلات - أكبر تلامس"],
        ["MaxRects - الأعرض أولاً", "ترتيب المستطيلات - الأعرض أولًا"],
        ["MaxRects - الأطول أولاً", "ترتيب المستطيلات - الأطول أولًا"],
        ["Shelf Packing - صفوف أفقية", "ترتيب صفوف أفقية"],
        ["Shelf Packing - أعمدة عمودية", "ترتيب أعمدة عمودية"],
        ["Shelf Packing - First Fit", "ترتيب صفوف - أول مكان مناسب"],
        ["Shelf Packing - Next Fit", "ترتيب صفوف - المكان التالي المناسب"],
        ["Guillotine - Short Axis Split", "قص متتابع - التقسيم على المحور القصير"],
        ["Guillotine - Long Axis Split", "قص متتابع - التقسيم على المحور الطويل"],
        ["Guillotine - Best Area Fit", "قص متتابع - أفضل استغلال للمساحة"],
        ["Guillotine - Best Short Side Fit", "قص متتابع - أفضل ضلع قصير"],
        ["Guillotine - Best Long Side Fit", "قص متتابع - أفضل ضلع طويل"],
        ["Skyline - Bottom Left", "ترتيب خط الأفق - من أسفل اليسار"],
        ["Skyline - Best Fit", "ترتيب خط الأفق - أفضل موضع"],
    ].sort((a, b) => b[0].length - a[0].length);

    function translateText(text) {
        let value = text;
        for (const [source, arabic] of replacements) {
            if (value.includes(source)) value = value.split(source).join(arabic);
        }
        return value;
    }

    function shouldSkip(node) {
        const parent = node.parentElement;
        if (!parent) return true;
        return ["SCRIPT", "STYLE", "CODE", "PRE", "TEXTAREA", "OPTION"].includes(parent.tagName);
    }

    function process(root) {
        if (!root) return;
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
        const nodes = [];
        while (walker.nextNode()) nodes.push(walker.currentNode);
        for (const node of nodes) {
            if (shouldSkip(node) || !node.nodeValue || !node.nodeValue.trim()) continue;
            const translated = translateText(node.nodeValue);
            if (translated !== node.nodeValue) node.nodeValue = translated;
        }
    }

    function run() {
        process(document.body);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", run, { once: true });
    } else {
        run();
    }

    const observer = new MutationObserver(mutations => {
        for (const mutation of mutations) {
            mutation.addedNodes.forEach(node => {
                if (node.nodeType === Node.TEXT_NODE) {
                    if (!shouldSkip(node) && node.nodeValue) {
                        const translated = translateText(node.nodeValue);
                        if (translated !== node.nodeValue) node.nodeValue = translated;
                    }
                } else if (node.nodeType === Node.ELEMENT_NODE) {
                    process(node);
                }
            });
        }
    });

    observer.observe(document.documentElement, { childList: true, subtree: true });
})();
