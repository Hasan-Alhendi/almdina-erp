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
        ["Door Cutting Plan Production A4", "خطة القص للتنفيذ"],
        ["Door Cutting Plan Official", "خطة القص الرسمية المعتمدة"],
        ["Door Cutting Measurements", "جدول قياسات الدرف"],
        ["Production Incidents and Replacements", "أخطاء الإنتاج والقطع التعويضية"],
        ["Production Stage Performance", "أداء مراحل الإنتاج"],
        ["Factory Performance Benchmark", "اختبار سرعة محرك خطة القص"],
        ["Factory System Preflight", "فحص جاهزية إعدادات المعمل"],
        ["Factory Operations Summary", "ملخص حركة المعمل"],
        ["Factory Approval Queue", "طلبات بانتظار الاعتماد"],
        ["Factory Order Analysis", "تحليل طلبات القص"],
        ["Order Stock Availability", "توفر مواد الطلبات"],
        ["Piece Size Usage Analysis", "تحليل المقاسات الأكثر استخدامًا"],
        ["Board Usage Analysis", "تحليل استهلاك الألواح"],
        ["Factory Operations", "التشغيل اليومي للمعمل"],
        ["Door Cutting Orders", "طلبات قص الدرف"],
        ["Material Reservations", "المواد المحجوزة للطلبات"],
        ["Production Incidents", "أخطاء ومشاكل الإنتاج"],
        ["Replacement Pieces", "القطع التعويضية"],
        ["Board Remnants", "بقايا الألواح"],
        ["Factory Settings", "إعدادات المعمل"],
        ["Remnant Inventory", "مخزون بقايا الألواح"],
        ["Factory Management", "إدارة المعمل"],
        ["Stock & Control", "المواد والمخزون والمتابعة"],
        ["Almdina ERP", "إدارة المعمل"],
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

    const packingOptions = {
        "Auto": "تلقائي - اختيار أفضل طريقة",
        "MaxRects Best Short Side": "ترتيب المستطيلات - أفضل ضلع قصير",
        "MaxRects Best Area": "ترتيب المستطيلات - أفضل استغلال للمساحة",
        "MaxRects Bottom Left": "ترتيب المستطيلات - من أسفل اليسار",
        "MaxRects Contact Point": "ترتيب المستطيلات - أكبر تلامس",
        "MaxRects Width": "ترتيب المستطيلات - الأعرض أولًا",
        "MaxRects Length": "ترتيب المستطيلات - الأطول أولًا",
        "Shelf Horizontal": "ترتيب صفوف أفقية",
        "Shelf Vertical": "ترتيب أعمدة عمودية",
        "Shelf First Fit": "ترتيب صفوف - أول مكان مناسب",
        "Shelf Next Fit": "ترتيب صفوف - المكان التالي المناسب",
        "Guillotine Short Axis": "قص متتابع - المحور القصير",
        "Guillotine Long Axis": "قص متتابع - المحور الطويل",
        "Guillotine Best Area Fit": "قص متتابع - أفضل استغلال للمساحة",
        "Guillotine Best Short Side Fit": "قص متتابع - أفضل ضلع قصير",
        "Guillotine Best Long Side Fit": "قص متتابع - أفضل ضلع طويل",
        "Skyline Bottom Left": "ترتيب خط الأفق - من أسفل اليسار",
        "Skyline Best Fit": "ترتيب خط الأفق - أفضل موضع",
    };

    const fieldOptionTranslations = {
        packing_mode: packingOptions,
        default_packing_mode: packingOptions,
        stock_consumption_point: {
            "Cutting Start": "عند بدء القص",
            "Cutting Finish": "عند انتهاء القص",
        },
        remnant_cost_policy: {
            "Zero": "بدون تكلفة",
            "Average Valuation": "حسب متوسط تكلفة المخزون",
            "Configured Rate": "حسب سعر محدد",
        },
    };

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

    function localizeSelectOptions(root) {
        const scope = root && root.querySelectorAll ? root : document;
        for (const [fieldname, translations] of Object.entries(fieldOptionTranslations)) {
            const controls = [];
            if (scope.matches && scope.matches(`[data-fieldname="${fieldname}"]`)) controls.push(scope);
            controls.push(...scope.querySelectorAll(`[data-fieldname="${fieldname}"]`));
            for (const control of controls) {
                control.querySelectorAll("option").forEach(option => {
                    const storedValue = option.value;
                    const source = storedValue || option.textContent.trim();
                    const translated = translations[source];
                    if (!translated) return;
                    option.textContent = translated;
                    // Preserve the stable machine value even when the browser had
                    // inferred it from the original option text.
                    option.value = storedValue || source;
                });
            }
        }
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
        localizeSelectOptions(root);
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
