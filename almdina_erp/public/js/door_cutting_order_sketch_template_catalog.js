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
        const first = points[0];
        const last = points[points.length - 1];
        if (first[0] === last[0] && first[1] === last[1]) return points;
        return [...points, [first[0], first[1]]];
    }

    function rectangle() {
        return close([[250, 150], [750, 150], [750, 500], [250, 500]]);
    }

    function slopeLeft() {
        return close([[340, 150], [750, 150], [750, 500], [250, 500], [250, 250]]);
    }

    function slopeRight() {
        return close([[250, 150], [660, 150], [750, 250], [750, 500], [250, 500]]);
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

    function lBottomLeft() {
        return close([[250, 150], [750, 150], [750, 500], [500, 500], [500, 330], [250, 330]]);
    }

    function lBottomRight() {
        return close([[250, 150], [750, 150], [750, 330], [500, 330], [500, 500], [250, 500]]);
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
        { key: "rectangle", icon: "▭", label: "مستطيل", hint: "شكل أساسي", group: "basic", common: true },
        { key: "l-bottom-left", icon: "⌞", label: "L يسار", hint: "نقرة سفلية يسار", group: "notch", common: true },
        { key: "l-bottom-right", icon: "⌟", label: "L يمين", hint: "نقرة سفلية يمين", group: "notch", common: true },
        { key: "u-bottom", icon: "∪", label: "فتحة U", hint: "فتحة من الأسفل", group: "notch", common: true },
        { key: "single-slope-left", icon: "◩", label: "ميل يسار", hint: "طرف علوي مائل", group: "angled", common: true },
        { key: "single-slope-right", icon: "◪", label: "ميل يمين", hint: "طرف علوي مائل", group: "angled", common: true },
        { key: "clipped-top-left", icon: "⌜", label: "قص يسار", hint: "زاوية علوية مقصوصة", group: "angled", common: false },
        { key: "clipped-top-right", icon: "⌝", label: "قص يمين", hint: "زاوية علوية مقصوصة", group: "angled", common: false },
        { key: "double-clipped", icon: "⬡", label: "قصتان علويتان", hint: "زاويتان متماثلتان", group: "angled", common: true },
        { key: "trapezoid", icon: "▱", label: "شبه منحرف", hint: "ميل من الجهتين", group: "angled", common: false },
        { key: "step-left", icon: "▟", label: "درجة يسار", hint: "بروز/تراجع جانبي", group: "step", common: true },
        { key: "step-right", icon: "▙", label: "درجة يمين", hint: "بروز/تراجع جانبي", group: "step", common: true },
        { key: "arch", icon: "⌒", label: "قوس علوي", hint: "قوس ناعم", group: "curve", common: true },
        { key: "crown", icon: "♜", label: "تاج علوي", hint: "رأس زخرفي مبسط", group: "curve", common: false },
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
        find,
        common,
        all,
    });
})();