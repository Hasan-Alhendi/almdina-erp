(() => {
    "use strict";

    const engine = window.AlmdinaSketchEngine;
    if (!engine) {
        console.error("AlmdinaSketchEngine must load before smart sketch templates");
        return;
    }

    const CANVAS = engine.DEFAULT_CANVAS;

    function close(points) {
        if (!points.length) return [];
        const source = points.map(point => [Number(point[0]), Number(point[1])]);
        const first = source[0];
        const last = source[source.length - 1];
        if (first[0] === last[0] && first[1] === last[1]) return source;
        return [...source, [first[0], first[1]]];
    }

    function rectangle() {
        return close([[250, 150], [750, 150], [750, 500], [250, 500]]);
    }

    // A full sloped side, not a small clipped corner. This distinction is important
    // because the operator chooses templates by their outside silhouette.
    function slopeLeft() {
        return close([[340, 150], [750, 150], [750, 500], [250, 500]]);
    }

    function slopeRight() {
        return close([[250, 150], [660, 150], [750, 500], [250, 500]]);
    }

    function clippedTopLeft() {
        return close([[340, 150], [750, 150], [750, 500], [250, 500], [250, 240]]);
    }

    function clippedTopRight() {
        return close([[250, 150], [660, 150], [750, 240], [750, 500], [250, 500]]);
    }

    function doubleClipped() {
        return close([[340, 150], [660, 150], [750, 240], [750, 500], [250, 500], [250, 240]]);
    }

    function trapezoid() {
        return close([[340, 150], [660, 150], [750, 500], [250, 500]]);
    }

    // L-left means the lower leg is on the left. L-right is its mirror.
    function lBottomLeft() {
        return close([[250, 150], [750, 150], [750, 330], [500, 330], [500, 500], [250, 500]]);
    }

    function lBottomRight() {
        return close([[250, 150], [750, 150], [750, 500], [500, 500], [500, 330], [250, 330]]);
    }

    function uBottom() {
        return close([
            [250, 150], [750, 150], [750, 500], [610, 500],
            [610, 375], [390, 375], [390, 500], [250, 500],
        ]);
    }

    function stepLeft() {
        return close([
            [250, 150], [750, 150], [750, 500], [250, 500],
            [250, 390], [390, 390], [390, 270], [250, 270],
        ]);
    }

    function stepRight() {
        return close([
            [250, 150], [750, 150], [750, 270], [610, 270],
            [610, 390], [750, 390], [750, 500], [250, 500],
        ]);
    }

    function crown() {
        return close([
            [250, 500], [250, 260], [365, 260], [430, 185],
            [500, 150], [570, 185], [635, 260], [750, 260], [750, 500],
        ]);
    }

    function arch() {
        const points = [[280, 500], [280, 300]];
        for (let index = 0; index <= 24; index += 1) {
            const angle = Math.PI - Math.PI * index / 24;
            points.push([
                500 + Math.cos(angle) * 220,
                300 - Math.sin(angle) * 220,
            ]);
        }
        points.push([720, 500]);
        return close(points);
    }

    const BUILDERS = Object.freeze({
        rectangle,
        "single-slope-left": slopeLeft,
        "single-slope-right": slopeRight,
        "clipped-top-left": clippedTopLeft,
        "clipped-top-right": clippedTopRight,
        "double-clipped": doubleClipped,
        trapezoid,
        "l-bottom-left": lBottomLeft,
        "l-bottom-right": lBottomRight,
        "u-bottom": uBottom,
        "step-left": stepLeft,
        "step-right": stepRight,
        crown,
        arch,
    });

    const ALIASES = Object.freeze({
        "single-slope": "single-slope-left",
        "clipped-corner": "clipped-top-left",
        angled: "clipped-top-left",
        lshape: "l-bottom-left",
    });

    const TEMPLATES = Object.freeze([
        { key: "rectangle", label: "مستطيل", hint: "حدود مستطيلة كاملة", group: "basic", common: true },
        { key: "l-bottom-left", label: "L يسار", hint: "الرجل السفلية جهة اليسار", group: "notch", common: true },
        { key: "l-bottom-right", label: "L يمين", hint: "الرجل السفلية جهة اليمين", group: "notch", common: true },
        { key: "u-bottom", label: "فتحة U", hint: "فتحة مستطيلة من الأسفل", group: "notch", common: true },
        { key: "single-slope-left", label: "ميل يسار", hint: "الضلع الخارجي الأيسر مائل بالكامل", group: "angled", common: true },
        { key: "single-slope-right", label: "ميل يمين", hint: "الضلع الخارجي الأيمن مائل بالكامل", group: "angled", common: true },
        { key: "clipped-top-left", label: "قص علوي يسار", hint: "قص صغير في الزاوية العلوية اليسرى", group: "angled", common: false },
        { key: "clipped-top-right", label: "قص علوي يمين", hint: "قص صغير في الزاوية العلوية اليمنى", group: "angled", common: false },
        { key: "double-clipped", label: "قصتان علويتان", hint: "قص متماثل في الزاويتين العلويتين", group: "angled", common: true },
        { key: "trapezoid", label: "شبه منحرف", hint: "الجانبان مائلان والقمة أضيق", group: "angled", common: false },
        { key: "step-left", label: "درجة يسار", hint: "درجة داخلية في الضلع الأيسر", group: "step", common: true },
        { key: "step-right", label: "درجة يمين", hint: "درجة داخلية في الضلع الأيمن", group: "step", common: true },
        { key: "arch", label: "قوس علوي", hint: "قوس نصف دائري ناعم من الأعلى", group: "curve", common: true },
        { key: "crown", label: "تاج علوي", hint: "قمة مركزية متعددة الأضلاع", group: "curve", common: false },
    ]);

    function resolveKey(key) {
        const value = String(key || "");
        return ALIASES[value] || value;
    }

    function points(key) {
        const resolved = resolveKey(key);
        const builder = BUILDERS[resolved];
        return builder ? builder().map(point => [Number(point[0]), Number(point[1])]) : [];
    }

    function pathData(key) {
        const source = points(key);
        if (!source.length) return "";
        return source.map((point, index) =>
            `${index ? "L" : "M"} ${Number(point[0]).toFixed(1)} ${Number(point[1]).toFixed(1)}`
        ).join(" ");
    }

    function find(key) {
        const resolved = resolveKey(key);
        return TEMPLATES.find(item => item.key === resolved) || null;
    }

    function common() {
        return TEMPLATES.filter(item => item.common);
    }

    function all() {
        return TEMPLATES.slice();
    }

    const previousTemplatePoints = engine.templatePoints;
    window.AlmdinaSketchEngine = Object.freeze({
        ...engine,
        templatePoints(key) {
            const result = points(key);
            return result.length ? result : previousTemplatePoints(key);
        },
    });

    window.AlmdinaSketchTemplateCatalog = Object.freeze({
        CANVAS,
        TEMPLATES,
        ALIASES,
        resolveKey,
        points,
        pathData,
        find,
        common,
        all,
    });
})();