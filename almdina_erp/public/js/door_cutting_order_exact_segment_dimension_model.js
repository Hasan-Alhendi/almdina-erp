(() => {
    "use strict";

    const lineModel = window.AlmdinaExactLineModel;
    const lineEdit = window.AlmdinaExactLineEditModel;
    const arcModel = window.AlmdinaExactArcModel;
    if (!lineModel || !lineEdit || !arcModel) {
        console.error("Exact line, line-edit and arc models must load before segment dimensions");
        return;
    }

    const EPSILON = 0.001;

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function num(value) {
        const result = Number(String(value ?? "").trim().replace(",", "."));
        return Number.isFinite(result) ? result : 0;
    }

    function samePoint(first, second, tolerance = EPSILON) {
        return Boolean(
            Array.isArray(first)
            && Array.isArray(second)
            && Math.abs(num(first[0]) - num(second[0])) <= tolerance
            && Math.abs(num(first[1]) - num(second[1])) <= tolerance
        );
    }

    function kind(element) {
        if (lineModel.exactMeta(element)) return "line";
        if (arcModel.arcMeta(element)) return "arc";
        return "";
    }

    function endpoints(element) {
        const line = lineModel.exactMeta(element);
        if (line) return {
            start: [num(line.start_cm[0]), num(line.start_cm[1])],
            end: [num(line.end_cm[0]), num(line.end_cm[1])],
        };
        const arc = arcModel.arcMeta(element);
        if (arc) return {
            start: [num(arc.start_cm[0]), num(arc.start_cm[1])],
            end: [num(arc.end_cm[0]), num(arc.end_cm[1])],
        };
        return null;
    }

    function metrics(element) {
        const line = lineModel.exactMeta(element);
        if (line) {
            return {
                kind: "line",
                lengthCm: num(line.length_cm),
                angleDeg: num(line.angle_deg),
                start: line.start_cm.slice(),
                end: line.end_cm.slice(),
            };
        }
        const arc = arcModel.arcMeta(element);
        if (arc) {
            return {
                kind: "arc",
                chordCm: num(arc.chord_cm),
                riseCm: num(arc.rise_cm),
                radiusCm: num(arc.radius_cm),
                arcLengthCm: num(arc.length_cm),
                side: Number(arc.side) < 0 ? -1 : 1,
                start: arc.start_cm.slice(),
                end: arc.end_cm.slice(),
            };
        }
        return null;
    }

    function descriptors(elements) {
        let exactIndex = 0;
        return (Array.isArray(elements) ? elements : []).flatMap(element => {
            const info = metrics(element);
            if (!info) return [];
            exactIndex += 1;
            return [{
                id: String(element.id || ""),
                number: exactIndex,
                label: info.kind === "arc" ? `قوس ${exactIndex}` : `ضلع ${exactIndex}`,
                ...info,
            }];
        });
    }

    function resizeLine(element, transform, options = {}) {
        const meta = lineModel.exactMeta(element);
        if (!meta) return { valid: false, reason: "not-exact-line", element: null };
        return lineEdit.resize(
            element,
            transform,
            options.lengthCm == null ? meta.length_cm : options.lengthCm,
            options.angleDeg == null ? meta.angle_deg : options.angleDeg,
            options.anchor === "end" ? "end" : "start"
        );
    }

    function arcEndForChord(meta, chordCm, anchor) {
        const target = num(chordCm);
        if (!meta || target <= EPSILON) return null;
        const frame = arcModel.chord(meta.start_cm, meta.end_cm);
        if (!frame) return null;
        if (anchor === "end") {
            return {
                start: [
                    frame.end[0] - frame.tangent[0] * target,
                    frame.end[1] - frame.tangent[1] * target,
                ],
                end: frame.end.slice(),
            };
        }
        return {
            start: frame.start.slice(),
            end: [
                frame.start[0] + frame.tangent[0] * target,
                frame.start[1] + frame.tangent[1] * target,
            ],
        };
    }

    function resizeArc(element, transform, options = {}) {
        const meta = arcModel.arcMeta(element);
        if (!meta) return { valid: false, reason: "not-exact-arc", element: null };
        const chordCm = options.chordCm == null ? meta.chord_cm : num(options.chordCm);
        const endpoints = arcEndForChord(meta, chordCm, options.anchor === "end" ? "end" : "start");
        if (!endpoints) return { valid: false, reason: "invalid-chord", element: null };
        const result = arcModel.buildElement({
            transform,
            startCm: endpoints.start,
            endCm: endpoints.end,
            riseCm: options.riseCm == null ? meta.rise_cm : num(options.riseCm),
            side: options.side == null ? meta.side : options.side,
            color: element.color,
            id: element.id,
        });
        if (!result.valid) return result;
        result.element = { ...clone(element), ...result.element, exact_arc: result.element.exact_arc };
        delete result.element.exact_line;
        return result;
    }

    function rebuildWithEndpoint(element, transform, role, point) {
        const current = endpoints(element);
        const next = [num(point && point[0]), num(point && point[1])];
        if (!current) return { valid: true, changed: false, element: clone(element) };
        const start = role === "start" ? next : current.start;
        const end = role === "end" ? next : current.end;
        if (kind(element) === "line") {
            const result = lineEdit.buildFromEndpoints(element, transform, start, end);
            return result.valid
                ? { valid: true, changed: true, element: result.element }
                : { valid: false, changed: false, reason: result.reason, element: null };
        }
        const meta = arcModel.arcMeta(element);
        const result = arcModel.buildElement({
            transform,
            startCm: start,
            endCm: end,
            riseCm: meta.rise_cm,
            side: meta.side,
            color: element.color,
            id: element.id,
        });
        if (!result.valid) return { valid: false, changed: false, reason: result.reason, element: null };
        result.element = { ...clone(element), ...result.element, exact_arc: result.element.exact_arc };
        delete result.element.exact_line;
        return { valid: true, changed: true, element: result.element };
    }

    function moveSharedEndpoint(element, transform, fromPoint, toPoint) {
        const current = endpoints(element);
        if (!current) return { valid: true, changed: false, element: clone(element) };
        const startMatches = samePoint(current.start, fromPoint);
        const endMatches = samePoint(current.end, fromPoint);
        if (!startMatches && !endMatches) return { valid: true, changed: false, element: clone(element) };
        if (startMatches && endMatches) return { valid: false, changed: false, reason: "degenerate-segment", element: null };
        return rebuildWithEndpoint(element, transform, startMatches ? "start" : "end", toPoint);
    }

    function applyEdit(elements, selectedId, nextSelected, transform, options = {}) {
        const source = Array.isArray(elements) ? elements : [];
        const index = source.findIndex(element => String(element && element.id) === String(selectedId || ""));
        const before = index >= 0 ? source[index] : null;
        const beforeEndpoints = endpoints(before);
        const afterEndpoints = endpoints(nextSelected);
        if (index < 0 || !beforeEndpoints || !afterEndpoints) {
            return { valid: false, reason: "missing-selected-segment", elements: clone(source), changedIds: [] };
        }
        const next = clone(source);
        next[index] = clone(nextSelected);
        const changedIds = [String(selectedId)];
        if (options.preserveConnections === false) {
            return { valid: true, reason: "", elements: next, changedIds };
        }
        const moves = [];
        if (!samePoint(beforeEndpoints.start, afterEndpoints.start)) moves.push([beforeEndpoints.start, afterEndpoints.start]);
        if (!samePoint(beforeEndpoints.end, afterEndpoints.end)) moves.push([beforeEndpoints.end, afterEndpoints.end]);
        for (const [fromPoint, toPoint] of moves) {
            for (let cursor = 0; cursor < next.length; cursor += 1) {
                if (cursor === index) continue;
                const moved = moveSharedEndpoint(next[cursor], transform, fromPoint, toPoint);
                if (!moved.valid) {
                    return { valid: false, reason: "connected-segment-invalid", elements: clone(source), changedIds: [] };
                }
                if (moved.changed) {
                    next[cursor] = moved.element;
                    const id = String(moved.element.id || "");
                    if (id && !changedIds.includes(id)) changedIds.push(id);
                }
            }
        }
        return { valid: true, reason: "", elements: next, changedIds };
    }

    window.AlmdinaExactSegmentDimensionModel = Object.freeze({
        EPSILON,
        kind,
        endpoints,
        metrics,
        descriptors,
        resizeLine,
        resizeArc,
        rebuildWithEndpoint,
        moveSharedEndpoint,
        applyEdit,
    });
})();
