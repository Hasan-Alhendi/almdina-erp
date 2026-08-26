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

    const replacements = [
        ["Door Cutting Plan Production A4", "خطة القص للتنفيذ"],
        ["Door Cutting Plan Official", "خطة القص الرسمية المعتمدة"],
        ["Door Cutting Measurements", "جدول قياسات الدرف"],
        ["Production Incidents and Replacements", "أخطاء الإنتاج والقطع التعويضية"],
        ["Production Stage Performance", "أداء مراحل الإنتاج"],
        ["Factory Operations Summary", "ملخص حركة المعمل"],
        ["Factory Order Analysis", "تحليل طلبات القص"],
        ["Piece Size Usage Analysis", "تحليل المقاسات الأكثر استخدامًا"],
        ["Board Usage Analysis", "تحليل استهلاك الألواح"],
        ["Factory Operations", "التشغيل اليومي للمعمل"],
        ["Door Cutting Orders", "طلبات قص الدرف"],
        ["Production Incidents", "أخطاء ومشاكل الإنتاج"],
        ["Replacement Pieces", "القطع التعويضية"],
        ["Factory Settings", "إعدادات المعمل"],
        ["Factory Management", "إدارة المعمل"],
        ["Order Cost Settings", "إعدادات تكلفة الطلب"],
        ["Cutting Plan Controls", "التحكم بخطة القص"],
        ["Optimization Time Limit (Sec)", "مهلة البحث عن أفضل خطة (ثانية)"],
        ["Default Optimization Time Limit (Sec)", "مهلة البحث الافتراضية (ثانية)"],
        ["Optimal Search Exact Piece Limit", "أقصى عدد قطع للبحث الأمثل الدقيق"],
        ["Default Cutting Machine Type", "نوع ماكينة القص الافتراضية"],
        ["Cutting Machine Type", "نوع ماكينة القص"],
        ["Industrial Plan Quality", "جودة خطة القص التشغيلية"],
        ["Estimated Cut Count", "عدد خطوط القص التقديري"],
        ["Estimated Cut Length M", "طول القص التقديري (متر)"],
        ["Largest Empty Rectangle M2", "أكبر مستطيل فارغ م²"],
        ["Rotation Count", "عدد مرات تدوير القطع"],
        ["Optimization Attempts", "عدد محاولات التحسين"],
        ["Optimization Mode", "مستوى تحسين خطة القص"],
        ["Ordering Strategy", "طريقة ترتيب القطع قبل التوزيع"],
        ["Solver Status", "حالة البحث الأمثل"],
        ["Search Elapsed Sec", "مدة البحث (ثانية)"],
        ["GUILLOTINE_DEEP_SEARCH", "بحث معمق مناسب لمنشار الألواح"],
        ["HEURISTIC_FALLBACK", "أفضل حل تجريبي ضمن المهلة"],
        ["FEASIBLE", "حل صالح وجيد ضمن المهلة"],
        ["OPTIMAL", "مثبت كأفضل حل ضمن النموذج"],
        ["Optimal Search", "بحث أمثل"],
        ["Deep Search", "بحث معمق"],
        ["Auto Pro", "تلقائي متقدم"],
        ["CNC Router", "راوتر CNC"],
        ["Panel Saw", "منشار ألواح"],
        ["Almdina ERP", "إدارة المعمل"],
        ["Auto Pro اختار: ", "التلقائي المتقدم اختار: "],
        ["بحث معمق اختار: ", "البحث المعمق اختار: "],
        ["Auto اختار: ", "تلقائي - تم اختيار: "],
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
        "Auto": "تلقائي سريع",
        "Auto Pro": "تلقائي متقدم - الأفضل للاستخدام اليومي",
        "Deep Search": "بحث معمق",
        "Optimal Search": "بحث أمثل",
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

    const machineOptions = {
        "Auto": "تلقائي - بدون قيد ماكينة",
        "CNC Router": "راوتر CNC",
        "Panel Saw": "منشار ألواح",
    };

    const fieldOptionTranslations = {
        packing_mode: packingOptions,
        default_packing_mode: packingOptions,
        cutting_machine_type: machineOptions,
        default_cutting_machine_type: machineOptions,
    };

    const pendingRoots = new Set();
    let scheduledFrame = null;

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

    function translateTextNode(node) {
        if (!node || shouldSkip(node) || !node.nodeValue || !node.nodeValue.trim()) return;
        const translated = translateText(node.nodeValue);
        if (translated !== node.nodeValue) node.nodeValue = translated;
    }

    function translateOption(option, directTranslations = null) {
        const storedValue = option.value;
        const sourceText = option.textContent.trim();
        if (!sourceText) return;
        const sourceValue = storedValue || sourceText;
        const translated = (directTranslations && directTranslations[sourceValue]) || __(sourceText);
        if (!translated || translated === sourceText) return;
        option.textContent = translated;
        option.value = storedValue || sourceValue;
    }

    function queryWithin(root, selector) {
        if (!root || root.nodeType !== Node.ELEMENT_NODE) return [];
        const results = [];
        if (typeof root.matches === "function" && root.matches(selector)) results.push(root);
        if (typeof root.querySelectorAll === "function") results.push(...root.querySelectorAll(selector));
        return results;
    }

    function localizeSelectOptions(root) {
        queryWithin(root, "option").forEach(option => translateOption(option));
        for (const [fieldname, translations] of Object.entries(fieldOptionTranslations)) {
            queryWithin(root, `[data-fieldname="${fieldname}"]`).forEach(control => {
                control.querySelectorAll("option").forEach(option => translateOption(option, translations));
            });
        }
    }

    function processElement(root) {
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
        while (walker.nextNode()) translateTextNode(walker.currentNode);
        localizeSelectOptions(root);
    }

    function processNode(node) {
        if (!node) return;
        if (node.nodeType === Node.TEXT_NODE) {
            translateTextNode(node);
            return;
        }
        if (node.nodeType === Node.ELEMENT_NODE) processElement(node);
    }

    function compactPendingRoots() {
        const roots = Array.from(pendingRoots);
        return roots.filter((candidate, index) => {
            if (!candidate || candidate.nodeType !== Node.ELEMENT_NODE) return true;
            return !roots.some((other, otherIndex) => (
                otherIndex !== index
                && other
                && other.nodeType === Node.ELEMENT_NODE
                && typeof other.contains === "function"
                && other.contains(candidate)
            ));
        });
    }

    function flushPendingRoots() {
        scheduledFrame = null;
        const roots = compactPendingRoots();
        pendingRoots.clear();
        roots.forEach(processNode);
    }

    function scheduleFlush() {
        if (scheduledFrame !== null) return;
        const schedule = window.requestAnimationFrame || (callback => window.setTimeout(callback, 16));
        scheduledFrame = schedule(flushPendingRoots);
    }

    function queueNode(node) {
        if (!node || (node.nodeType !== Node.TEXT_NODE && node.nodeType !== Node.ELEMENT_NODE)) return;
        pendingRoots.add(node);
        scheduleFlush();
    }

    function run() {
        if (!document.body) return;
        processElement(document.body);

        const observer = new MutationObserver(mutations => {
            for (const mutation of mutations) mutation.addedNodes.forEach(queueNode);
        });
        observer.observe(document.body, { childList: true, subtree: true });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", run, { once: true });
    } else {
        run();
    }
})();
