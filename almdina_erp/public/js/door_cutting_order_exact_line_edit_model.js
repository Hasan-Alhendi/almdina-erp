(() => {
    "use strict";

    const lineModel = window.AlmdinaExactLineModel;
    if (!lineModel) {
        console.error("AlmdinaExactLineModel must load before exact-line edit model");
        return;
    }

    const EPSILON = 0.001;

    function num(value) {
        const result = Number(String(value ?? "").trim().replace(",", "."));
        return Number.isFinite(result) ? result : 0;
    }

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function samePoint(first, second, tolerance = EPSILON) {
        return Boolean(
            Array.isArray(first)
            && Array.isArray(second)
            && Math.abs(num(first[0]) - num(second[0])) <= tolerance
            && Math.abs(num(first[1]) - num(second[1])) <= tolerance
        );
    }

    function endpoints(element) {
        const meta = lineModel.exactMeta(element);
        if (!meta) return null;
        return {
            start: [num(meta.start_cm[0]), num(meta.start_cm[1])],
            end: [num(meta.end_cm[0]), num(meta.end_cm[1])],
        };
    }

    function buildFromEndpoints(element, transform, startCm, endCm) {
        if (!element || !transform) return { valid: false, reason: "missing-input", element: null };
        const rawStart = [num(startCm && startCm[0]), num(startCm && startCm[1])];
        const rawEnd = [num(endCm && endCm[0]), num(endCm && endCm[1])];
        if (!lineModel.insidePiece(transform, rawStart, 0.01) || !lineModel.insidePiece(transform, rawEnd, 0.01)) {
            return { valid: false, reason: "outside-piece", element: null };
        }
        const start = lineModel.clampPointToPiece(transform, rawStart);
        const end = lineModel.clampPointToPiece(transform, rawEnd);
        const length = Math.hypot(end[0] - start[0], end[1] - start[1]);
        if (length < lineModel.MIN_LENGTH_CM) {
            return { valid: false, reason: "length-too-small", element: null };
        }
        const result = lineModel.buildElement({
            transform,
            startCm: start,
            lengthCm: length,
            angleDeg: lineModel.angleBetween(start, end),
            color: element.color || "#172033",
            id: element.id,
        });
        if (!result.valid) return result;
        result.element = {
            ...clone(element),
            ...result.element,
            exact_line: result.element.exact_line,
        };
        return result;
    }

    function resize(element, transform, lengthCm, angleDeg, anchor = "start") {
        const current = endpoints(element);
        const length = num(lengthCm);
        const angle = lineModel.normalizeAngle(angleDeg);
        if (!current || !transform) return { valid: false, reason: "missing-input", element: null };
        if (length < lineModel.MIN_LENGTH_CM) {
            return { valid: false, reason: "length-too-small", element: null };
        }
        if (anchor === "end") {
            const start = lineModel.pointAt(current.end, length, angle + 180);
            return buildFromEndpoints(element, transform, start, current.end);
        }
        const end = lineModel.pointAt(current.start, length, angle);
        return buildFromEndpoints(element, transform, current.start, end);
    }

    function axisAngle(element, axis) {
        const current = endpoints(element);
        if (!current) return 0;
        if (axis === "vertical") return current.end[1] < current.start[1] ? -90 : 90;
        return current.end[0] < current.start[0] ? 180 : 0;
    }

    function replaceEndpoint(element, transform, role, point) {
        const current = endpoints(element);
        if (!current) return { valid: false, reason: "not-exact-line", element: null };
        return role === "start"
            ? buildFromEndpoints(element, transform, point, current.end)
            : buildFromEndpoints(element, transform, current.start, point);
    }

    function connectedCount(elements, selectedId, point) {
        let count = 0;
        (Array.isArray(elements) ? elements : []).forEach(element => {
            if (String(element && element.id) === String(selectedId || "")) return;
            const current = endpoints(element);
            if (!current) return;
            if (samePoint(current.start, point) || samePoint(current.end, point)) count += 1;
        });
        return count;
    }

    function moveSharedEndpoint(element, transform, fromPoint, toPoint) {
        const current = endpoints(element);
        if (!current) return { valid: true, changed: false, element: clone(element) };
        const startMatches = samePoint(current.start, fromPoint);
        const endMatches = samePoint(current.end, fromPoint);
        if (!startMatches && !endMatches) {
            return { valid: true, changed: false, element: clone(element) };
        }
        const nextStart = startMatches ? toPoint : current.start;
        const nextEnd = endMatches ? toPoint : current.end;
        const result = buildFromEndpoints(element, transform, nextStart, nextEnd);
        return result.valid
            ? { valid: true, changed: true, element: result.element }
            : { valid: false, changed: false, reason: result.reason, element: null };
    }

    function applyEdit(elements, selectedId, nextSelected, transform, options = {}) {
        const source = Array.isArray(elements) ? elements : [];
        const index = source.findIndex(element => String(element && element.id) === String(selectedId || ""));
        const before = index >= 0 ? source[index] : null;
        const beforeEndpoints = endpoints(before);
        const afterEndpoints = endpoints(nextSelected);
        if (index < 0 || !beforeEndpoints || !afterEndpoints) {
            return { valid: false, reason: "missing-selected-line", elements: clone(source), changedIds: [] };
        }

        const preserveConnections = options.preserveConnections !== false;
        const next = clone(source);
        next[index] = clone(nextSelected);
        const changedIds = [String(selectedId)];
        if (!preserveConnections) {
            return { valid: true, reason: "", elements: next, changedIds };
        }

        const endpointMoves = [];
        if (!samePoint(beforeEndpoints.start, afterEndpoints.start)) {
            endpointMoves.push([beforeEndpoints.start, afterEndpoints.start]);
        }
        if (!samePoint(beforeEndpoints.end, afterEndpoints.end)) {
            endpointMoves.push([beforeEndpoints.end, afterEndpoints.end]);
        }

        for (const [fromPoint, toPoint] of endpointMoves) {
            for (let elementIndex = 0; elementIndex < next.length; elementIndex += 1) {
                if (elementIndex === index) continue;
                const moved = moveSharedEndpoint(next[elementIndex], transform, fromPoint, toPoint);
                if (!moved.valid) {
                    return {
                        valid: false,
                        reason: "connected-line-invalid",
                        elements: clone(source),
                        changedIds: [],
                    };
                }
                if (moved.changed) {
                    next[elementIndex] = moved.element;
                    const id = String(moved.element.id || "");
                    if (id && !changedIds.includes(id)) changedIds.push(id);
                }
            }
        }

        return { valid: true, reason: "", elements: next, changedIds };
    }

    window.AlmdinaExactLineEditModel = Object.freeze({
        EPSILON,
        samePoint,
        endpoints,
        buildFromEndpoints,
        resize,
        axisAngle,
        replaceEndpoint,
        connectedCount,
        moveSharedEndpoint,
        applyEdit,
    });
})();