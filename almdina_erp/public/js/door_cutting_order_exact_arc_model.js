(() => {
    "use strict";

    const lineModel = window.AlmdinaExactLineModel;
    if (!lineModel) {
        console.error("AlmdinaExactLineModel must load before exact-arc model");
        return;
    }

    const VERSION = 1;
    const UNITS = "cm";
    const MIN_RISE_CM = 0.2;
    const MAX_RISE_RATIO = 0.49;
    const DEFAULT_RISE_RATIO = 0.18;
    const SAMPLE_COUNT = 28;
    const EPSILON = 0.001;

    function num(value) {
        const result = Number(String(value ?? "").trim().replace(",", "."));
        return Number.isFinite(result) ? result : 0;
    }

    function rounded(value, precision = 4) {
        return lineModel.rounded(value, precision);
    }

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function normalizeSide(value) {
        return Number(value) < 0 ? -1 : 1;
    }

    function arcMeta(element) {
        const meta = element && element.exact_arc;
        if (
            !meta
            || Number(meta.version) !== VERSION
            || meta.units !== UNITS
            || !Array.isArray(meta.start_cm)
            || !Array.isArray(meta.end_cm)
            || num(meta.radius_cm) <= 0
            || num(meta.rise_cm) <= 0
        ) return null;
        return meta;
    }

    function chord(start, end) {
        const x1 = num(start && start[0]);
        const y1 = num(start && start[1]);
        const x2 = num(end && end[0]);
        const y2 = num(end && end[1]);
        const dx = x2 - x1;
        const dy = y2 - y1;
        const length = Math.hypot(dx, dy);
        if (length <= EPSILON) return null;
        const tangent = [dx / length, dy / length];
        const normal = [-tangent[1], tangent[0]];
        return {
            start: [rounded(x1), rounded(y1)],
            end: [rounded(x2), rounded(y2)],
            midpoint: [rounded((x1 + x2) / 2), rounded((y1 + y2) / 2)],
            tangent,
            normal,
            length: rounded(length),
        };
    }

    function limits(start, end) {
        const frame = chord(start, end);
        if (!frame) return { minimum: MIN_RISE_CM, maximum: 0, defaultRise: 0 };
        const maximum = rounded(frame.length * MAX_RISE_RATIO, 3);
        return {
            minimum: MIN_RISE_CM,
            maximum,
            defaultRise: rounded(Math.max(MIN_RISE_CM, Math.min(maximum, frame.length * DEFAULT_RISE_RATIO)), 3),
        };
    }

    function geometryFromChord(start, end, riseCm, side = 1) {
        const frame = chord(start, end);
        if (!frame) return { valid: false, reason: "zero-chord" };
        const rise = Math.abs(num(riseCm));
        const allowed = limits(start, end);
        if (rise < MIN_RISE_CM) return { valid: false, reason: "rise-too-small", limits: allowed };
        if (rise > allowed.maximum + EPSILON) return { valid: false, reason: "rise-too-large", limits: allowed };

        const direction = normalizeSide(side);
        const radius = (frame.length * frame.length) / (8 * rise) + rise / 2;
        const centerOffset = radius - rise;
        const center = [
            rounded(frame.midpoint[0] - frame.normal[0] * direction * centerOffset),
            rounded(frame.midpoint[1] - frame.normal[1] * direction * centerOffset),
        ];
        const apex = [
            rounded(frame.midpoint[0] + frame.normal[0] * direction * rise),
            rounded(frame.midpoint[1] + frame.normal[1] * direction * rise),
        ];
        const sweepRad = 2 * Math.asin(Math.min(1, frame.length / (2 * radius)));
        const arcLength = radius * sweepRad;
        return {
            valid: true,
            reason: "",
            frame,
            rise: rounded(rise, 3),
            side: direction,
            radius: rounded(radius, 4),
            center,
            apex,
            sweepRad,
            sweepDeg: rounded(sweepRad * 180 / Math.PI, 4),
            arcLength: rounded(arcLength, 4),
            limits: allowed,
        };
    }

    function sampleCmFromGeometry(result, count = SAMPLE_COUNT) {
        if (!result || !result.valid) return [];
        const frame = result.frame;
        const samples = Math.max(8, Math.min(64, Math.round(num(count) || SAMPLE_COUNT)));
        const half = frame.length / 2;
        const centerY = result.rise - result.radius;
        const points = [];
        for (let index = 0; index <= samples; index += 1) {
            const x = -half + frame.length * index / samples;
            const inside = Math.max(0, result.radius * result.radius - x * x);
            const localY = Math.sqrt(inside) + centerY;
            points.push([
                rounded(frame.midpoint[0] + frame.tangent[0] * x + frame.normal[0] * result.side * localY),
                rounded(frame.midpoint[1] + frame.tangent[1] * x + frame.normal[1] * result.side * localY),
            ]);
        }
        points[0] = frame.start.slice();
        points[points.length - 1] = frame.end.slice();
        return points;
    }

    function sampleCm(metaOrElement, count = SAMPLE_COUNT) {
        const meta = metaOrElement && metaOrElement.exact_arc
            ? arcMeta(metaOrElement)
            : metaOrElement;
        if (!meta) return [];
        const result = geometryFromChord(meta.start_cm, meta.end_cm, meta.rise_cm, meta.side);
        return sampleCmFromGeometry(result, count);
    }

    function samplesInside(transform, points) {
        return Boolean(transform && points.length && points.every(point => lineModel.insidePiece(transform, point, 0.01)));
    }

    function buildElement(options = {}) {
        const transform = options.transform;
        if (!transform) return { valid: false, reason: "missing-transform", element: null };
        const start = [num(options.startCm && options.startCm[0]), num(options.startCm && options.startCm[1])];
        const end = [num(options.endCm && options.endCm[0]), num(options.endCm && options.endCm[1])];
        if (!lineModel.insidePiece(transform, start, 0.01) || !lineModel.insidePiece(transform, end, 0.01)) {
            return { valid: false, reason: "outside-piece", element: null };
        }
        const result = geometryFromChord(start, end, options.riseCm, options.side);
        if (!result.valid) return { ...result, element: null };
        const samplesCm = sampleCmFromGeometry(result, options.sampleCount || SAMPLE_COUNT);
        if (!samplesInside(transform, samplesCm)) {
            return { valid: false, reason: "arc-outside-piece", limits: result.limits, element: null };
        }
        const samplesCanvas = samplesCm.map(point => lineModel.cmToCanvas(transform, point));
        return {
            valid: true,
            reason: "",
            geometry: result,
            element: {
                id: String(options.id || `exact-arc-${Date.now()}`),
                type: "pen",
                points: samplesCanvas,
                color: String(options.color || "#172033"),
                exact_arc: {
                    version: VERSION,
                    units: UNITS,
                    start_cm: result.frame.start.slice(),
                    end_cm: result.frame.end.slice(),
                    chord_cm: rounded(result.frame.length, 3),
                    rise_cm: result.rise,
                    side: result.side,
                    radius_cm: rounded(result.radius, 3),
                    center_cm: result.center.slice(),
                    apex_cm: result.apex.slice(),
                    sweep_deg: rounded(result.sweepDeg, 3),
                    length_cm: rounded(result.arcLength, 3),
                    sample_count: samplesCanvas.length,
                    blank_width_cm: rounded(transform.widthCm, 3),
                    blank_length_cm: rounded(transform.lengthCm, 3),
                },
            },
        };
    }

    function fromLine(element, transform, riseCm = null, side = 1) {
        const meta = lineModel.exactMeta(element);
        if (!meta) return { valid: false, reason: "not-exact-line", element: null };
        const allowed = limits(meta.start_cm, meta.end_cm);
        return buildElement({
            transform,
            startCm: meta.start_cm,
            endCm: meta.end_cm,
            riseCm: riseCm == null ? allowed.defaultRise : riseCm,
            side,
            color: element.color,
            id: element.id,
        });
    }

    function rebuild(element, transform, options = {}) {
        const meta = arcMeta(element);
        if (!meta) return { valid: false, reason: "not-exact-arc", element: null };
        const result = buildElement({
            transform,
            startCm: meta.start_cm,
            endCm: meta.end_cm,
            riseCm: options.riseCm == null ? meta.rise_cm : options.riseCm,
            side: options.side == null ? meta.side : options.side,
            color: element.color,
            id: element.id,
        });
        if (!result.valid) return result;
        result.element = {
            ...clone(element),
            ...result.element,
            exact_arc: result.element.exact_arc,
        };
        delete result.element.exact_line;
        return result;
    }

    function flip(element, transform) {
        const meta = arcMeta(element);
        return meta ? rebuild(element, transform, { side: -normalizeSide(meta.side) }) : { valid: false, reason: "not-exact-arc", element: null };
    }

    function toLine(element, transform) {
        const meta = arcMeta(element);
        if (!meta || !transform) return { valid: false, reason: "not-exact-arc", element: null };
        const chordLength = Math.hypot(
            num(meta.end_cm[0]) - num(meta.start_cm[0]),
            num(meta.end_cm[1]) - num(meta.start_cm[1])
        );
        const result = lineModel.buildElement({
            transform,
            startCm: meta.start_cm,
            lengthCm: chordLength,
            angleDeg: lineModel.angleBetween(meta.start_cm, meta.end_cm),
            color: element.color,
            id: element.id,
        });
        if (!result.valid) return result;
        result.element = { ...clone(element), ...result.element, exact_line: result.element.exact_line };
        delete result.element.exact_arc;
        delete result.element.points;
        return result;
    }

    function svgArcPath(element, transform) {
        const meta = arcMeta(element);
        if (!meta || !transform) return "";
        const start = lineModel.cmToCanvas(transform, meta.start_cm);
        const end = lineModel.cmToCanvas(transform, meta.end_cm);
        const radius = num(meta.radius_cm) * transform.scale;
        const sweepFlag = normalizeSide(meta.side) > 0 ? 0 : 1;
        return `M ${rounded(start[0], 3)} ${rounded(start[1], 3)} A ${rounded(radius, 3)} ${rounded(radius, 3)} 0 0 ${sweepFlag} ${rounded(end[0], 3)} ${rounded(end[1], 3)}`;
    }

    window.AlmdinaExactArcModel = Object.freeze({
        VERSION,
        UNITS,
        MIN_RISE_CM,
        MAX_RISE_RATIO,
        DEFAULT_RISE_RATIO,
        SAMPLE_COUNT,
        arcMeta,
        chord,
        limits,
        geometryFromChord,
        sampleCm,
        buildElement,
        fromLine,
        rebuild,
        flip,
        toLine,
        svgArcPath,
        normalizeSide,
    });
})();
