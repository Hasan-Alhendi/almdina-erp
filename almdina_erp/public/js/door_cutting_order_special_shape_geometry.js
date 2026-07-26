(() => {
    "use strict";

    const TYPE = "Special";
    const VERSION = 1;
    const MAX_VERTICES = 64;
    const EPSILON = 0.001;
    const PARSE_CACHE_LIMIT = 250;
    const parseCache = new Map();
    const exactCache = new Map();

    function num(value) {
        const result = Number(String(value ?? "").replace(",", "."));
        return Number.isFinite(result) ? result : 0;
    }

    function rounded(value, precision = 3) {
        const factor = 10 ** precision;
        return Math.round(num(value) * factor) / factor;
    }

    function clamp(value, minimum, maximum) {
        return Math.min(maximum, Math.max(minimum, num(value)));
    }

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function samePoint(first, second, tolerance = EPSILON) {
        return Boolean(
            first
            && second
            && Math.abs(num(first[0]) - num(second[0])) <= tolerance
            && Math.abs(num(first[1]) - num(second[1])) <= tolerance
        );
    }

    function normalizePoints(points) {
        const result = (Array.isArray(points) ? points : [])
            .filter(point => Array.isArray(point) && point.length === 2)
            .map(point => [rounded(point[0]), rounded(point[1])])
            .filter(point => Number.isFinite(point[0]) && Number.isFinite(point[1]));
        if (result.length > 1 && samePoint(result[0], result[result.length - 1])) {
            result.pop();
        }
        return result;
    }

    function parse(raw) {
        if (!raw) return null;
        try {
            if (typeof raw === "string" && parseCache.has(raw)) {
                return parseCache.get(raw);
            }
            const payload = typeof raw === "string" ? JSON.parse(raw) : raw;
            if (
                !payload
                || Number(payload.version) !== VERSION
                || payload.kind !== "polygon"
                || payload.units !== "cm"
            ) {
                return null;
            }
            const parsed = {
                version: VERSION,
                kind: "polygon",
                units: "cm",
                template: String(payload.template || "custom"),
                blank_width_cm: rounded(payload.blank_width_cm),
                blank_length_cm: rounded(payload.blank_length_cm),
                points: normalizePoints(payload.points),
                exact: payload.exact !== false,
            };
            if (typeof raw === "string") {
                parsed.points.forEach(Object.freeze);
                Object.freeze(parsed.points);
                Object.freeze(parsed);
                parseCache.set(raw, parsed);
                if (parseCache.size > PARSE_CACHE_LIMIT) {
                    parseCache.delete(parseCache.keys().next().value);
                }
            }
            return parsed;
        } catch (error) {
            return null;
        }
    }

    function fromPiece(piece) {
        return parse(piece && piece.special_shape_geometry_json);
    }

    function signedArea(points) {
        const source = normalizePoints(points);
        if (source.length < 3) return 0;
        return source.reduce((sum, point, index) => {
            const next = source[(index + 1) % source.length];
            return sum + point[0] * next[1] - next[0] * point[1];
        }, 0) / 2;
    }

    function area(points) {
        return Math.abs(signedArea(points));
    }

    function orientation(first, second, third) {
        const value = (
            (num(second[1]) - num(first[1])) * (num(third[0]) - num(second[0]))
            - (num(second[0]) - num(first[0])) * (num(third[1]) - num(second[1]))
        );
        if (Math.abs(value) <= EPSILON) return 0;
        return value > 0 ? 1 : 2;
    }

    function pointOnSegment(first, point, second) {
        return (
            num(point[0]) <= Math.max(num(first[0]), num(second[0])) + EPSILON
            && num(point[0]) >= Math.min(num(first[0]), num(second[0])) - EPSILON
            && num(point[1]) <= Math.max(num(first[1]), num(second[1])) + EPSILON
            && num(point[1]) >= Math.min(num(first[1]), num(second[1])) - EPSILON
        );
    }

    function segmentsIntersect(firstStart, firstEnd, secondStart, secondEnd) {
        const o1 = orientation(firstStart, firstEnd, secondStart);
        const o2 = orientation(firstStart, firstEnd, secondEnd);
        const o3 = orientation(secondStart, secondEnd, firstStart);
        const o4 = orientation(secondStart, secondEnd, firstEnd);
        if (o1 !== o2 && o3 !== o4) return true;
        if (o1 === 0 && pointOnSegment(firstStart, secondStart, firstEnd)) return true;
        if (o2 === 0 && pointOnSegment(firstStart, secondEnd, firstEnd)) return true;
        if (o3 === 0 && pointOnSegment(secondStart, firstStart, secondEnd)) return true;
        return o4 === 0 && pointOnSegment(secondStart, firstEnd, secondEnd);
    }

    function hasSelfIntersection(points) {
        const source = normalizePoints(points);
        const count = source.length;
        if (count < 4) return false;
        for (let first = 0; first < count; first += 1) {
            const firstNext = (first + 1) % count;
            for (let second = first + 1; second < count; second += 1) {
                const secondNext = (second + 1) % count;
                if (
                    first === second
                    || firstNext === second
                    || secondNext === first
                    || (first === 0 && secondNext === 0)
                ) {
                    continue;
                }
                if (segmentsIntersect(
                    source[first],
                    source[firstNext],
                    source[second],
                    source[secondNext]
                )) {
                    return true;
                }
            }
        }
        return false;
    }

    function validate(geometry, expectedWidth = 0, expectedLength = 0) {
        const parsed = parse(geometry);
        const errors = [];
        if (!parsed) {
            return { valid: false, errors: ["بيانات الشكل الهندسي غير صالحة."], geometry: null };
        }

        const width = parsed.blank_width_cm;
        const length = parsed.blank_length_cm;
        const points = parsed.points;
        if (width <= 0 || length <= 0) {
            errors.push("أدخل عرض الدرفة وطولها قبل بناء الشكل.");
        }
        if (
            expectedWidth > 0
            && Math.abs(width - num(expectedWidth)) > EPSILON
        ) {
            errors.push("عرض الرسم لا يطابق عرض الدرفة الحالي.");
        }
        if (
            expectedLength > 0
            && Math.abs(length - num(expectedLength)) > EPSILON
        ) {
            errors.push("طول الرسم لا يطابق طول الدرفة الحالي.");
        }
        if (points.length < 3) errors.push("الشكل يحتاج ثلاث زوايا على الأقل.");
        if (points.length > MAX_VERTICES) errors.push(`الحد الأقصى هو ${MAX_VERTICES} زاوية.`);

        points.forEach((point, index) => {
            if (
                point[0] < -EPSILON
                || point[1] < -EPSILON
                || point[0] > width + EPSILON
                || point[1] > length + EPSILON
            ) {
                errors.push(`الزاوية ${index + 1} خارج مقاس الخام.`);
            }
            const next = points[(index + 1) % points.length];
            if (next && samePoint(point, next)) {
                errors.push(`الزاويتان ${index + 1} و${(index + 1) % points.length + 1} متطابقتان.`);
            }
        });

        if (points.length >= 3) {
            const xs = points.map(point => point[0]);
            const ys = points.map(point => point[1]);
            if (
                Math.abs(Math.min(...xs)) > EPSILON
                || Math.abs(Math.max(...xs) - width) > EPSILON
                || Math.abs(Math.min(...ys)) > EPSILON
                || Math.abs(Math.max(...ys) - length) > EPSILON
            ) {
                errors.push("يجب أن يلامس الشكل حدود العرض والطول الخارجية للخام.");
            }
            if (area(points) <= EPSILON) errors.push("مساحة الشكل يجب أن تكون أكبر من صفر.");
            if (hasSelfIntersection(points)) errors.push("أضلاع الشكل تتقاطع. حرّك الزوايا حتى يصبح المسار مغلقًا وواضحًا.");
        }

        return { valid: errors.length === 0, errors, geometry: parsed };
    }

    function defaultInset(total, ratio = 0.2) {
        total = Math.max(0, num(total));
        return rounded(Math.min(Math.max(total * ratio, 1), total * 0.42));
    }

    function templatePoints(template, width, length) {
        width = Math.max(0, num(width));
        length = Math.max(0, num(length));
        if (!width || !length) return [];
        const insetX = defaultInset(width);
        const insetY = defaultInset(length);

        if (template === "single-slope") {
            return [[insetX, 0], [width, 0], [width, length], [0, length]];
        }
        if (template === "double-clipped") {
            return [
                [insetX, 0],
                [width - insetX, 0],
                [width, insetY],
                [width, length],
                [0, length],
                [0, insetY],
            ];
        }
        if (template === "trapezoid") {
            return [[insetX, 0], [width - insetX, 0], [width, length], [0, length]];
        }
        if (template === "l-notch") {
            return [
                [0, 0],
                [width, 0],
                [width, length],
                [insetX, length],
                [insetX, length - insetY],
                [0, length - insetY],
            ];
        }
        if (template === "arch") {
            const rise = Math.min(length * 0.3, width * 0.42);
            const points = [[0, length]];
            for (let index = 0; index <= 16; index += 1) {
                const angle = Math.PI - Math.PI * index / 16;
                points.push([
                    rounded(width / 2 + Math.cos(angle) * width / 2),
                    rounded(rise - Math.sin(angle) * rise),
                ]);
            }
            points.push([width, length]);
            return normalizePoints(points);
        }
        return [[0, 0], [width, 0], [width, length], [0, length]];
    }

    function create(template, width, length, points = null) {
        return {
            version: VERSION,
            kind: "polygon",
            units: "cm",
            template: String(template || "custom"),
            blank_width_cm: rounded(width),
            blank_length_cm: rounded(length),
            points: normalizePoints(points || templatePoints(template, width, length)),
            exact: true,
        };
    }

    function serialize(geometry) {
        const parsed = parse(geometry);
        return parsed ? JSON.stringify(parsed) : "";
    }

    function originalDimensions(piece, geometry = fromPiece(piece)) {
        return {
            width: num(
                piece && (piece.original_w || piece.original_width_cm || piece.width_cm)
                || geometry && geometry.blank_width_cm
            ),
            length: num(
                piece && (piece.original_h || piece.original_length_cm || piece.length_cm)
                || geometry && geometry.blank_length_cm
            ),
        };
    }

    function effectivePoints(piece) {
        const geometry = fromPiece(piece);
        if (!geometry) return [];
        const dimensions = originalDimensions(piece, geometry);
        if (!piece || !piece.rotated) return clone(geometry.points);
        return geometry.points.map(point => [
            rounded(dimensions.length - point[1]),
            rounded(point[0]),
        ]);
    }

    function points(piece, viewportWidth = 100, viewportHeight = 100) {
        const geometry = fromPiece(piece);
        if (!geometry) return [];
        const rotated = Boolean(piece && piece.rotated);
        const dimensions = originalDimensions(piece, geometry);
        const effectiveWidth = rotated ? dimensions.length : dimensions.width;
        const effectiveLength = rotated ? dimensions.width : dimensions.length;
        if (!effectiveWidth || !effectiveLength) return [];
        return effectivePoints(piece).map(point => [
            rounded(point[0] / effectiveWidth * num(viewportWidth)),
            rounded(point[1] / effectiveLength * num(viewportHeight)),
        ]);
    }

    function pointsAttribute(piece, width = 100, height = 100) {
        return points(piece, width, height)
            .map(point => `${rounded(point[0])},${rounded(point[1])}`)
            .join(" ");
    }

    function dxfPoints(piece, x, y, width, height) {
        return points(piece, width, height).map(point => [
            rounded(num(x) + point[0]),
            rounded(num(y) + num(height) - point[1]),
        ]);
    }

    function isExact(piece) {
        if (!piece || piece.piece_type !== TYPE) return false;
        const raw = piece.special_shape_geometry_json;
        const parsed = fromPiece(piece);
        if (!parsed || parsed.exact === false) return false;
        const dimensions = originalDimensions(piece, parsed);
        const cacheKey = typeof raw === "string"
            ? `${raw}\u0000${dimensions.width}\u0000${dimensions.length}`
            : "";
        if (cacheKey && exactCache.has(cacheKey)) return exactCache.get(cacheKey);
        const result = validate(parsed, dimensions.width, dimensions.length).valid;
        if (cacheKey) {
            exactCache.set(cacheKey, result);
            if (exactCache.size > PARSE_CACHE_LIMIT) {
                exactCache.delete(exactCache.keys().next().value);
            }
        }
        return result;
    }

    function edgeLength(first, second) {
        return rounded(Math.hypot(num(second[0]) - num(first[0]), num(second[1]) - num(first[1])));
    }

    function summary(piece) {
        const geometry = fromPiece(piece);
        if (!geometry) return "";
        return `${geometry.points.length} زوايا · ${rounded(area(geometry.points) / 10000, 3)} م²`;
    }

    window.AlmdinaSpecialShapeGeometry = Object.freeze({
        TYPE,
        VERSION,
        MAX_VERTICES,
        parse,
        fromPiece,
        create,
        serialize,
        validate,
        normalizePoints,
        signedArea,
        area,
        hasSelfIntersection,
        templatePoints,
        effectivePoints,
        points,
        pointsAttribute,
        dxfPoints,
        isExact,
        edgeLength,
        summary,
        clamp,
        rounded,
    });
})();
