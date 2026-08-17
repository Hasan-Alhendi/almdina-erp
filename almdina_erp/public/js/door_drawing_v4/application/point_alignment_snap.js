(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);
    const geometry = root.Geometry;
    const base = root.SnapResolver;
    if (!geometry || !base) throw new Error("Geometry and base snap resolver must load before point alignment snap");

    const ALIGN_PRIORITY = 65;

    function stableId(value) {
        return String(value ?? "");
    }

    function guide(kind, start, end, nodeId) {
        return Object.freeze({
            kind,
            start: geometry.clonePoint(start),
            end: geometry.clonePoint(end),
            referenceNodeId: stableId(nodeId),
            referenceSegmentId: null,
        });
    }

    function alignmentCandidates(document, rawPoint, request, toleranceMm) {
        if (toleranceMm <= 0) return [];
        const excluded = new Set((request.excludeNodeIds || []).map(stableId));
        const candidates = [];
        (document.nodes || []).forEach(node => {
            if (!node || excluded.has(stableId(node.id))) return;
            const dx = Math.abs(rawPoint.xMm - node.xMm);
            const dy = Math.abs(rawPoint.yMm - node.yMm);
            if (dx <= toleranceMm + geometry.EPSILON_MM) {
                const point = geometry.point(node.xMm, rawPoint.yMm);
                if (!request.origin || geometry.distance(request.origin, point) > geometry.EPSILON_MM) {
                    candidates.push(Object.freeze({
                        key: `align-x:${node.id}`,
                        type: "alignment",
                        semantic: "align-x",
                        point,
                        nodeId: null,
                        segmentId: null,
                        referenceSegmentId: null,
                        referenceNodeId: stableId(node.id),
                        distanceMm: dx,
                        angleDeg: null,
                        priority: ALIGN_PRIORITY,
                        guides: Object.freeze([guide("align-x", node, point, node.id)]),
                    }));
                }
            }
            if (dy <= toleranceMm + geometry.EPSILON_MM) {
                const point = geometry.point(rawPoint.xMm, node.yMm);
                if (!request.origin || geometry.distance(request.origin, point) > geometry.EPSILON_MM) {
                    candidates.push(Object.freeze({
                        key: `align-y:${node.id}`,
                        type: "alignment",
                        semantic: "align-y",
                        point,
                        nodeId: null,
                        segmentId: null,
                        referenceSegmentId: null,
                        referenceNodeId: stableId(node.id),
                        distanceMm: dy,
                        angleDeg: null,
                        priority: ALIGN_PRIORITY,
                        guides: Object.freeze([guide("align-y", node, point, node.id)]),
                    }));
                }
            }
        });
        return candidates;
    }

    function compare(left, right) {
        if (left.priority !== right.priority) return left.priority - right.priority;
        if (Math.abs(left.distanceMm - right.distanceMm) > geometry.EPSILON_MM) return left.distanceMm - right.distanceMm;
        return left.key.localeCompare(right.key);
    }

    function resolve(document, request = {}) {
        const rawPoint = geometry.clonePoint(request.rawPoint);
        const toleranceMm = Math.max(0, geometry.finiteNumber(request.toleranceMm));
        const releaseToleranceMm = Math.max(
            toleranceMm,
            geometry.finiteNumber(request.releaseToleranceMm, toleranceMm * base.DEFAULT_RELEASE_MULTIPLIER)
        );
        const baseResult = base.resolve(document, request);
        const releaseCandidates = alignmentCandidates(document, rawPoint, request, releaseToleranceMm);
        const acquisitionCandidates = releaseCandidates
            .filter(item => item.distanceMm <= toleranceMm + geometry.EPSILON_MM)
            .sort(compare);
        const previousKey = request.previousSnap && request.previousSnap.key ? String(request.previousSnap.key) : "";
        const sticky = previousKey.startsWith("align-")
            ? releaseCandidates.filter(item => item.key === previousKey).sort(compare)[0] || null
            : null;
        const bestAlignment = sticky || acquisitionCandidates[0] || null;
        if (!bestAlignment) return baseResult;
        if (baseResult && baseResult.type !== "free" && Number(baseResult.priority) < ALIGN_PRIORITY) return baseResult;
        return Object.freeze({
            ...bestAlignment,
            candidates: Object.freeze([
                ...(Array.isArray(baseResult && baseResult.candidates) ? baseResult.candidates : []),
                ...acquisitionCandidates,
            ]),
        });
    }

    root.SnapResolver = Object.freeze({
        ...base,
        ALIGN_PRIORITY,
        resolve,
        alignmentCandidates,
    });
})();
