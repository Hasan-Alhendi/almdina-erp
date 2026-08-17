(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    const F = root.SmartFreehandPolicy;
    if (!G || !F || typeof F.recognize !== "function") {
        throw new Error("Door Drawing V3 freehand policy must load before smart suggestions");
    }

    const CONFIDENCE = Object.freeze({
        line: 0.55,
        circle: 0.62,
        arc: 0.65,
        rectangle: 0.9,
    });

    const LABELS = Object.freeze({
        line: "خط مستقيم",
        circle: "دائرة دقيقة",
        arc: "قوس دقيق",
        rectangle: "مستطيل دقيق",
        close: "إغلاق المسار",
    });

    function freezePoints(points) {
        return Object.freeze((points || []).map(point => G.point(point.x, point.y)));
    }

    function primitiveSuggestion(result) {
        if (!result || !Object.prototype.hasOwnProperty.call(CONFIDENCE, result.type)) return null;
        const confidence = Number(result.confidence) || 0;
        if (confidence + 1e-9 < CONFIDENCE[result.type]) return null;

        const suggestion = {
            kind: "primitive",
            type: result.type,
            label: LABELS[result.type],
            confidence,
        };
        if (result.type === "line") {
            suggestion.start = G.point(result.start.x, result.start.y);
            suggestion.end = G.point(result.end.x, result.end.y);
        } else if (result.type === "rectangle") {
            suggestion.origin = G.point(result.origin.x, result.origin.y);
            suggestion.widthMm = G.roundMm(result.widthMm);
            suggestion.heightMm = G.roundMm(result.heightMm);
        } else if (result.type === "circle") {
            suggestion.center = G.point(result.center.x, result.center.y);
            suggestion.radiusMm = G.roundMm(result.radiusMm);
        } else if (result.type === "arc") {
            suggestion.center = G.point(result.center.x, result.center.y);
            suggestion.radiusMm = G.roundMm(result.radiusMm);
            suggestion.startAngleDeg = G.roundMm(result.startAngleDeg);
            suggestion.sweepAngleDeg = G.roundMm(result.sweepAngleDeg);
        }
        return Object.freeze(suggestion);
    }

    function closeSuggestion(points) {
        const raw = F.dedupe(points);
        if (raw.length < 3) return null;
        let prepared = raw;
        if (G.distance(raw[0], raw[raw.length - 1]) <= G.EPSILON_MM) {
            prepared = raw.slice(0, -1);
        }
        if (prepared.length < 3) return null;
        return Object.freeze({
            kind: "close",
            type: "close",
            label: LABELS.close,
            confidence: 1,
            points: freezePoints(prepared),
        });
    }

    function analyze(points, options = {}) {
        const raw = F.dedupe(points);
        if (raw.length < 2) return null;

        // A near-closed gesture may be a circle or rectangle. We analyze a copy as
        // closed, but never mutate the user's stored path. If the primitive fit is
        // weak, the only suggestion is to close the original path exactly as drawn.
        const closeReady = Boolean(options.closeReady);
        const recognition = F.recognize(raw, {
            ...options,
            closed: closeReady,
            preserveEndpoints: true,
        });
        const primitive = primitiveSuggestion(recognition);
        if (primitive) return primitive;
        return closeReady ? closeSuggestion(raw) : null;
    }

    function candidateObject(suggestion, sourceId, sourceStyle = {}) {
        if (!suggestion || !sourceId) return null;
        if (suggestion.type === "line") {
            return G.line(sourceId, suggestion.start, suggestion.end, sourceStyle);
        }
        if (suggestion.type === "rectangle") {
            return G.rectangle(sourceId, suggestion.origin, suggestion.widthMm, suggestion.heightMm, sourceStyle);
        }
        if (suggestion.type === "circle") {
            return G.circle(sourceId, suggestion.center, suggestion.radiusMm, sourceStyle);
        }
        if (suggestion.type === "arc") {
            return G.arc(
                sourceId,
                suggestion.center,
                suggestion.radiusMm,
                suggestion.startAngleDeg,
                suggestion.sweepAngleDeg,
                sourceStyle
            );
        }
        if (suggestion.type === "close") {
            return G.path(sourceId, suggestion.points, true, sourceStyle);
        }
        return null;
    }

    root.SmartSuggestionPolicy = Object.freeze({
        CONFIDENCE,
        LABELS,
        primitiveSuggestion,
        closeSuggestion,
        analyze,
        candidateObject,
    });
})();
