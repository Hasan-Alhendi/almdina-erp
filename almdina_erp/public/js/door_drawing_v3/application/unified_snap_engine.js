(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const Base = root.Snapping;
    const G = root.Geometry;
    if (!Base || !G || typeof Base.collectSegments !== "function") {
        throw new Error("Door Drawing V3 smart guides must load before unified snap engine");
    }

    const MOVE_CAPTURE_PX = 20;
    const MOVE_RELEASE_FACTOR = 1.6;
    const ENDPOINT_PX = 20;
    const INTERSECTION_PX = 12;
    const MIDPOINT_PX = 12;
    const SURFACE_PX = 12;
    const ALIGN_PX = 8;
    const EQUAL_LENGTH_PX = 8;
    const ANGLE_TOLERANCE_DEG = 2;
    const INTENT_PRIORITY = Object.freeze({
        joint: 1000,
        intersection: 950,
        endpoint: 900,
        midpoint: 850,
        surface: 800,
        perpendicular: 760,
        collinear: 720,
        parallel: 700,
        alignment: 500,
        "equal-length": 450,
    });

    function clamp01(value) { return Math.max(0, Math.min(1, Number(value) || 0)); }
    function angleDistance180(a, b) {
        const delta = Math.abs((((Number(a) || 0) - (Number(b) || 0)) % 180 + 180) % 180);
        return Math.min(delta, 180 - delta);
    }
    function cross(ax, ay, bx, by) { return ax * by - ay * bx; }
    function pointKey(point) { return `${G.roundMm(point.x, 3)}:${G.roundMm(point.y, 3)}`; }
    function freezeTarget(objectId, role, point, priority, kind, extra = {}) {
        return Object.freeze({
            objectId: String(objectId || ""),
            role: String(role || "point"),
            point: G.point(point && point.x, point && point.y),
            priority: Number(priority) || 0,
            kind: String(kind || "reference"),
            ...extra,
        });
    }
    function guide(type, point, targetPoint = null, extra = {}) {
        return Object.freeze({
            type,
            point: G.point(point.x, point.y),
            targetPoint: targetPoint ? G.point(targetPoint.x, targetPoint.y) : null,
            ...extra,
        });
    }
    function result(base, patch) { return Object.freeze({ ...base, ...patch }); }
    function tolerance(scale, px) { return Base.worldTolerance(scale, px); }

    function segmentMidpoint(segment) {
        return G.point((segment.start.x + segment.end.x) / 2, (segment.start.y + segment.end.y) / 2);
    }

    function projectInfinite(point, start, end) {
        const p = G.point(point.x, point.y), a = G.point(start.x, start.y), b = G.point(end.x, end.y);
        const dx = b.x - a.x, dy = b.y - a.y;
        const len2 = dx * dx + dy * dy;
        if (len2 <= G.EPSILON_MM * G.EPSILON_MM) return null;
        const t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2;
        const projected = G.point(a.x + dx * t, a.y + dy * t);
        return Object.freeze({ point: projected, t, distanceMm: G.distance(p, projected) });
    }

    function segmentIntersection(a, b) {
        const p = G.point(a.start.x, a.start.y), q = G.point(b.start.x, b.start.y);
        const rx = a.end.x - a.start.x, ry = a.end.y - a.start.y;
        const sx = b.end.x - b.start.x, sy = b.end.y - b.start.y;
        const denom = cross(rx, ry, sx, sy);
        if (Math.abs(denom) <= G.EPSILON_MM) return null;
        const qpx = q.x - p.x, qpy = q.y - p.y;
        const t = cross(qpx, qpy, sx, sy) / denom;
        const u = cross(qpx, qpy, rx, ry) / denom;
        if (t < -G.EPSILON_MM || t > 1 + G.EPSILON_MM || u < -G.EPSILON_MM || u > 1 + G.EPSILON_MM) return null;
        return G.point(p.x + rx * clamp01(t), p.y + ry * clamp01(t));
    }

    function segments(drawing, options = {}) {
        return Base.collectSegments(drawing, options);
    }

    function midpointAnchors(drawing, options = {}) {
        return Object.freeze(segments(drawing, options).map(segment => freezeTarget(
            segment.objectId,
            `midpoint:${segment.role}`,
            segmentMidpoint(segment),
            75,
            "midpoint",
            { segmentRole: segment.role }
        )));
    }

    function intersectionAnchors(drawing, options = {}) {
        const items = segments(drawing, options);
        const found = [], seen = new Set();
        for (let i = 0; i < items.length; i += 1) {
            for (let j = i + 1; j < items.length; j += 1) {
                const a = items[i], b = items[j];
                if (String(a.objectId) === String(b.objectId)) continue;
                const point = segmentIntersection(a, b);
                if (!point) continue;
                const key = pointKey(point);
                if (seen.has(key)) continue;
                seen.add(key);
                found.push(freezeTarget(
                    `${a.objectId}|${b.objectId}`,
                    `intersection:${a.role}|${b.role}`,
                    point,
                    130,
                    "intersection",
                    { segmentA: a, segmentB: b }
                ));
            }
        }
        return Object.freeze(found);
    }

    function endpointAnchors(drawing, options = {}) {
        return Object.freeze(Base.collectAnchors(drawing, options).filter(anchor => Base.isJoint(anchor)).map(anchor => Object.freeze({
            ...anchor,
            intent: "endpoint",
        })));
    }

    function intentAnchors(drawing, options = {}) {
        return Object.freeze([
            ...endpointAnchors(drawing, options),
            ...intersectionAnchors(drawing, options),
            ...midpointAnchors(drawing, options),
        ]);
    }

    function nearestPoint(candidate, anchors, toleranceMm, kind = null) {
        const raw = G.point(candidate.x, candidate.y);
        let best = null;
        for (const target of anchors || []) {
            if (kind && target.kind !== kind) continue;
            const distanceMm = G.distance(raw, target.point);
            if (distanceMm > toleranceMm) continue;
            if (!best || distanceMm < best.distanceMm - G.EPSILON_MM || (Math.abs(distanceMm - best.distanceMm) <= G.EPSILON_MM && target.priority > best.target.priority)) {
                best = { target, distanceMm };
            }
        }
        return best;
    }

    function axisCompatible(reference, axis, point) {
        if (!reference || !axis) return true;
        return axis === "horizontal"
            ? Math.abs(point.y - reference.y) <= Base.AXIS_EPSILON_MM
            : Math.abs(point.x - reference.x) <= Base.AXIS_EPSILON_MM;
    }

    function nearestSurface(drawing, candidate, toleranceMm, options = {}, reference = null, axis = null) {
        let best = null;
        for (const segment of segments(drawing, options)) {
            let projection = Base.projectSegment(candidate, segment.start, segment.end);
            if (!projection) continue;
            if (reference && axis && !axisCompatible(reference, axis, projection.point)) {
                const axisSegment = axis === "vertical"
                    ? { start: G.point(reference.x, candidate.y - toleranceMm * 4), end: G.point(reference.x, candidate.y + toleranceMm * 4) }
                    : { start: G.point(candidate.x - toleranceMm * 4, reference.y), end: G.point(candidate.x + toleranceMm * 4, reference.y) };
                const crossing = segmentIntersection(segment, axisSegment);
                if (!crossing) continue;
                projection = { point: crossing, distanceMm: G.distance(candidate, crossing), t: 0.5 };
            }
            if (projection.distanceMm > toleranceMm) continue;
            if (!best || projection.distanceMm < best.distanceMm - G.EPSILON_MM || (Math.abs(projection.distanceMm - best.distanceMm) <= G.EPSILON_MM && segment.priority > best.segment.priority)) {
                best = { segment, ...projection };
            }
        }
        return best;
    }

    function alignmentCandidate(drawing, point, toleranceMm, options = {}, sourcePoints = null) {
        const targets = [...endpointAnchors(drawing, options), ...midpointAnchors(drawing, options)];
        const sources = sourcePoints && sourcePoints.length ? sourcePoints : [{ role: "point", point }];
        let bestX = null, bestY = null;
        for (const source of sources) {
            for (const target of targets) {
                const dx = target.point.x - source.point.x;
                const dy = target.point.y - source.point.y;
                if (Math.abs(dx) <= toleranceMm && (!bestX || Math.abs(dx) < Math.abs(bestX.delta) - G.EPSILON_MM)) bestX = { source, target, delta: dx };
                if (Math.abs(dy) <= toleranceMm && (!bestY || Math.abs(dy) < Math.abs(bestY.delta) - G.EPSILON_MM)) bestY = { source, target, delta: dy };
            }
        }
        return { bestX, bestY };
    }

    function exactAngleCandidate(drawing, reference, candidate, options = {}) {
        if (!reference) return null;
        const requestedLength = G.distance(reference, candidate);
        if (requestedLength <= G.EPSILON_MM) return null;
        const requestedAngle = G.angleDeg(reference, candidate);
        let best = null;
        for (const segment of segments(drawing, options)) {
            const baseAngle = G.angleDeg(segment.start, segment.end);
            for (const spec of [
                { kind: "parallel", angle: baseAngle, symbol: "∥" },
                { kind: "perpendicular", angle: baseAngle + 90, symbol: "⊥" },
            ]) {
                const distanceDeg = angleDistance180(requestedAngle, spec.angle);
                if (distanceDeg > ANGLE_TOLERANCE_DEG) continue;
                const forward = spec.angle;
                const reverse = spec.angle + 180;
                const forwardDelta = Math.abs((((requestedAngle - forward + 180) % 360) + 360) % 360 - 180);
                const reverseDelta = Math.abs((((requestedAngle - reverse + 180) % 360) + 360) % 360 - 180);
                const exactAngle = reverseDelta < forwardDelta ? reverse : forward;
                if (!best || distanceDeg < best.distanceDeg - 1e-9) best = { segment, ...spec, exactAngle, distanceDeg, point: G.pointAt(reference, requestedLength, exactAngle) };
            }
        }
        return best;
    }

    function perpendicularFootCandidate(drawing, reference, candidate, toleranceMm, options = {}) {
        if (!reference) return null;
        let best = null;
        for (const segment of segments(drawing, options)) {
            const projection = Base.projectSegment(reference, segment.start, segment.end);
            if (!projection) continue;
            const distanceMm = G.distance(candidate, projection.point);
            if (distanceMm > toleranceMm) continue;
            if (!best || distanceMm < best.distanceMm - G.EPSILON_MM) best = { segment, point: projection.point, distanceMm };
        }
        return best;
    }

    function normalizePointResult(raw, point, target, distanceMm, kind, axis, reference, smartGuide = null) {
        return Object.freeze({
            point,
            rawPoint: raw,
            snapped: Boolean(target),
            target: target || null,
            source: null,
            distanceMm: target && Number.isFinite(distanceMm) ? G.roundMm(distanceMm) : null,
            toleranceMm: null,
            joinToleranceMm: null,
            axis: axis || null,
            anchor: reference || null,
            kind: kind || "reference",
            intent: kind || "reference",
            smartGuide,
        });
    }

    function resolvePoint(drawing, candidate, options = {}) {
        const raw = G.point(candidate && candidate.x, candidate && candidate.y);
        const reference = options.anchor ? G.point(options.anchor.x, options.anchor.y) : null;
        const forcedAxis = options.forcedAxis === "horizontal" || options.forcedAxis === "vertical" ? options.forcedAxis : null;
        const useAxis = Boolean(reference && (forcedAxis || (options.axisLock && options.shiftKey)));
        const locked = useAxis ? Base.axisLock(reference, raw, forcedAxis) : null;
        const point = locked ? locked.point : raw;
        const axis = locked ? locked.axis : null;
        const scale = options.viewportScale;
        const endpointTol = tolerance(scale, options.joinSnapPx || ENDPOINT_PX);
        const intersectionTol = tolerance(scale, options.intersectionSnapPx || INTERSECTION_PX);
        const midpointTol = tolerance(scale, options.midpointSnapPx || MIDPOINT_PX);
        const surfaceTol = tolerance(scale, options.surfaceSnapPx || SURFACE_PX);
        const alignTol = tolerance(scale, options.alignSnapPx || ALIGN_PX);
        const equalTol = tolerance(scale, options.equalLengthSnapPx || EQUAL_LENGTH_PX);

        const endpoints = endpointAnchors(drawing, options).filter(target => axisCompatible(reference, axis, target.point));
        const endpoint = nearestPoint(point, endpoints, endpointTol);
        if (endpoint) return normalizePointResult(raw, endpoint.target.point, endpoint.target, endpoint.distanceMm, "joint", axis, reference, guide("endpoint", endpoint.target.point, null, { symbol: "●" }));

        const intersections = intersectionAnchors(drawing, options).filter(target => axisCompatible(reference, axis, target.point));
        const intersection = nearestPoint(point, intersections, intersectionTol);
        if (intersection) return normalizePointResult(raw, intersection.target.point, intersection.target, intersection.distanceMm, "intersection", axis, reference, guide("intersection", intersection.target.point, null, { symbol: "×" }));

        const midpoints = midpointAnchors(drawing, options).filter(target => axisCompatible(reference, axis, target.point));
        const midpoint = nearestPoint(point, midpoints, midpointTol);
        if (midpoint) return normalizePointResult(raw, midpoint.target.point, midpoint.target, midpoint.distanceMm, "midpoint", axis, reference, guide("midpoint", midpoint.target.point, null, { symbol: "◇" }));

        if (reference && !axis) {
            const perpendicular = perpendicularFootCandidate(drawing, reference, point, surfaceTol, options);
            if (perpendicular) {
                const target = freezeTarget(perpendicular.segment.objectId, perpendicular.segment.role, perpendicular.point, perpendicular.segment.priority, "surface", { segmentRole: perpendicular.segment.role });
                return normalizePointResult(raw, perpendicular.point, target, perpendicular.distanceMm, "perpendicular", axis, reference, guide("perpendicular", perpendicular.point, reference, { symbol: "⊥", objectId: String(perpendicular.segment.objectId) }));
            }
        }

        const surface = nearestSurface(drawing, point, surfaceTol, options, reference, axis);
        if (surface) {
            const target = freezeTarget(surface.segment.objectId, surface.segment.role, surface.point, surface.segment.priority, "surface", { segmentRole: surface.segment.role });
            return normalizePointResult(raw, surface.point, target, surface.distanceMm, "surface", axis, reference, guide("surface", surface.point, null, { symbol: "●", objectId: String(surface.segment.objectId), role: surface.segment.role }));
        }

        if (reference && !axis) {
            const angular = exactAngleCandidate(drawing, reference, point, options);
            if (angular) {
                const target = freezeTarget(angular.segment.objectId, angular.segment.role, angular.point, angular.segment.priority, angular.kind);
                return normalizePointResult(raw, angular.point, target, angular.distanceDeg, angular.kind, axis, reference, guide(angular.kind, angular.point, angular.segment.end, { symbol: angular.symbol, angleDeg: angular.exactAngle, objectId: String(angular.segment.objectId) }));
            }
        }

        const alignment = alignmentCandidate(drawing, point, alignTol, options);
        if (alignment.bestX || alignment.bestY) {
            let aligned = point;
            let type = "alignment";
            if (axis === "vertical" && alignment.bestY) aligned = G.point(reference.x, point.y + alignment.bestY.delta);
            else if (axis === "horizontal" && alignment.bestX) aligned = G.point(point.x + alignment.bestX.delta, reference.y);
            else if (!axis) aligned = G.point(point.x + (alignment.bestX ? alignment.bestX.delta : 0), point.y + (alignment.bestY ? alignment.bestY.delta : 0));
            else return normalizePointResult(raw, point, null, null, "reference", axis, reference, null);
            const targetInfo = alignment.bestX || alignment.bestY;
            const target = targetInfo.target;
            const guideType = !axis && alignment.bestX && alignment.bestY ? "xy-alignment" : (axis === "vertical" || (!axis && alignment.bestY && !alignment.bestX)) ? "horizontal-alignment" : "vertical-alignment";
            type = "alignment";
            return normalizePointResult(raw, aligned, target, Math.min(alignment.bestX ? Math.abs(alignment.bestX.delta) : Infinity, alignment.bestY ? Math.abs(alignment.bestY.delta) : Infinity), type, axis, reference, guide(guideType, aligned, target.point, {
                xAnchor: alignment.bestX ? alignment.bestX.target : null,
                yAnchor: alignment.bestY ? alignment.bestY.target : null,
            }));
        }

        if (reference && typeof Base.equalLengthCandidate === "function") {
            const equal = Base.equalLengthCandidate(drawing, reference, point, equalTol, options);
            if (equal) {
                let exact = equal.point;
                if (axis === "vertical") exact = G.point(reference.x, reference.y + Math.sign(point.y - reference.y || 1) * equal.lengthMm);
                if (axis === "horizontal") exact = G.point(reference.x + Math.sign(point.x - reference.x || 1) * equal.lengthMm, reference.y);
                const target = freezeTarget(equal.segment.objectId, equal.segment.role, equal.segment.end, equal.segment.priority, "equal-length");
                return normalizePointResult(raw, exact, target, equal.distanceMm, "equal-length", axis, reference, guide("equal-length", exact, equal.segment.end, { symbol: "=", lengthMm: equal.lengthMm, objectId: String(equal.segment.objectId) }));
            }
        }

        return normalizePointResult(raw, point, null, null, "reference", axis, reference, null);
    }

    function sourceFeatures(object) {
        const anchors = (typeof Base.anchorsForObject === "function" ? Base.anchorsForObject(object) : Base.objectAnchors(object)).filter(Base.isJoint).map(anchor => Object.freeze({ ...anchor, sourceKind: "endpoint" }));
        for (const segment of Base.collectSegments({ objects: [object] })) {
            anchors.push(freezeTarget(object.id, `midpoint:${segment.role}`, segmentMidpoint(segment), 70, "midpoint", { sourceKind: "midpoint", segmentRole: segment.role }));
        }
        return anchors;
    }

    function targetSegment(drawing, identity, excludeId) {
        if (!identity) return null;
        return segments(drawing, { excludeId }).find(segment => String(segment.objectId) === String(identity.objectId) && String(segment.role) === String(identity.segmentRole || identity.role)) || null;
    }

    function sourceByIdentity(features, identity) {
        if (!identity) return null;
        return features.find(source => String(source.objectId) === String(identity.objectId) && String(source.role) === String(identity.role)) || null;
    }

    function targetByIdentity(drawing, identity, excludeId) {
        if (!identity) return null;
        return intentAnchors(drawing, { excludeId }).find(target => String(target.objectId) === String(identity.objectId) && String(target.role) === String(identity.role)) || null;
    }

    function moveCandidate(kind, source, target, correctionX, correctionY, distanceMm, smartGuide, sticky = false) {
        return { kind, source, target, correctionX, correctionY, distanceMm, smartGuide, sticky, rank: INTENT_PRIORITY[kind] || 0 };
    }

    function betterMove(current, candidate) {
        if (!candidate) return current;
        if (!current) return candidate;
        if (candidate.rank !== current.rank) return candidate.rank > current.rank ? candidate : current;
        return candidate.distanceMm < current.distanceMm - G.EPSILON_MM ? candidate : current;
    }

    function resolveStickyMove(drawing, moved, object, options, releaseToleranceMm) {
        if (!options.stickySource || !options.stickyTarget) return null;
        const sources = sourceFeatures(moved);
        const source = sourceByIdentity(sources, options.stickySource);
        if (!source) return null;
        if (options.stickyTarget.kind === "surface") {
            const segment = targetSegment(drawing, options.stickyTarget, object.id);
            const projection = segment && Base.projectSegment(source.point, segment.start, segment.end);
            if (!projection || projection.distanceMm > releaseToleranceMm) return null;
            const target = freezeTarget(segment.objectId, segment.role, projection.point, segment.priority, "surface", { segmentRole: segment.role });
            return moveCandidate("surface", source, target, projection.point.x - source.point.x, projection.point.y - source.point.y, projection.distanceMm, guide("surface", projection.point, null, { symbol: "●", objectId: String(segment.objectId) }), true);
        }
        const target = targetByIdentity(drawing, options.stickyTarget, object.id);
        if (!target) return null;
        const distanceMm = G.distance(source.point, target.point);
        if (distanceMm > releaseToleranceMm) return null;
        const kind = target.kind === "intersection" ? "intersection" : target.kind === "midpoint" ? "midpoint" : "joint";
        const symbol = kind === "intersection" ? "×" : kind === "midpoint" ? "◇" : "●";
        return moveCandidate(kind, source, target, target.point.x - source.point.x, target.point.y - source.point.y, distanceMm, guide(kind === "joint" ? "endpoint" : kind, target.point, null, { symbol }), true);
    }

    function resolveObjectMove(drawing, object, deltaX, deltaY, options = {}) {
        const dx = G.number(deltaX), dy = G.number(deltaY);
        const moved = G.translateObject(object, dx, dy);
        const scale = options.viewportScale;
        const captureMm = tolerance(scale, options.moveJoinSnapPx || MOVE_CAPTURE_PX);
        const releaseToleranceMm = captureMm * MOVE_RELEASE_FACTOR;
        const surfaceTol = tolerance(scale, options.surfaceSnapPx || SURFACE_PX);
        const alignTol = tolerance(scale, options.alignSnapPx || ALIGN_PX);
        const sources = sourceFeatures(moved);
        const targets = intentAnchors(drawing, { excludeId: object && object.id });
        let best = resolveStickyMove(drawing, moved, object, options, releaseToleranceMm);

        if (!best) {
            for (const source of sources) {
                for (const target of targets) {
                    const distanceMm = G.distance(source.point, target.point);
                    const allowed = target.kind === "intersection"
                        ? Math.min(captureMm, tolerance(scale, INTERSECTION_PX))
                        : target.kind === "midpoint"
                            ? Math.min(captureMm, tolerance(scale, MIDPOINT_PX))
                            : captureMm;
                    if (distanceMm > allowed) continue;
                    const kind = target.kind === "intersection" ? "intersection" : target.kind === "midpoint" ? "midpoint" : "joint";
                    const symbol = kind === "intersection" ? "×" : kind === "midpoint" ? "◇" : "●";
                    best = betterMove(best, moveCandidate(kind, source, target, target.point.x - source.point.x, target.point.y - source.point.y, distanceMm, guide(kind === "joint" ? "endpoint" : kind, target.point, null, { symbol })));
                }
            }
        }

        if (!best) {
            for (const source of sources.filter(item => item.sourceKind === "endpoint")) {
                const surface = nearestSurface(drawing, source.point, surfaceTol, { excludeId: object.id });
                if (!surface) continue;
                const target = freezeTarget(surface.segment.objectId, surface.segment.role, surface.point, surface.segment.priority, "surface", { segmentRole: surface.segment.role });
                best = betterMove(best, moveCandidate("surface", source, target, surface.point.x - source.point.x, surface.point.y - source.point.y, surface.distanceMm, guide("surface", surface.point, null, { symbol: "●", objectId: String(surface.segment.objectId), role: surface.segment.role })));
            }
        }

        if (!best) {
            const movingSegments = Base.collectSegments({ objects: [moved] });
            for (const sourceSegment of movingSegments) {
                const midpoint = segmentMidpoint(sourceSegment);
                for (const targetSegmentItem of segments(drawing, { excludeId: object.id })) {
                    if (angleDistance180(G.angleDeg(sourceSegment.start, sourceSegment.end), G.angleDeg(targetSegmentItem.start, targetSegmentItem.end)) > ANGLE_TOLERANCE_DEG) continue;
                    const projection = projectInfinite(midpoint, targetSegmentItem.start, targetSegmentItem.end);
                    if (!projection || projection.distanceMm > alignTol) continue;
                    const source = freezeTarget(object.id, `segment:${sourceSegment.role}`, midpoint, 60, "collinear", { segmentRole: sourceSegment.role });
                    const target = freezeTarget(targetSegmentItem.objectId, targetSegmentItem.role, projection.point, targetSegmentItem.priority, "collinear", { segmentRole: targetSegmentItem.role });
                    best = betterMove(best, moveCandidate("collinear", source, target, projection.point.x - midpoint.x, projection.point.y - midpoint.y, projection.distanceMm, guide("collinear", projection.point, midpoint, { symbol: "∥", objectId: String(targetSegmentItem.objectId) })));
                }
            }
        }

        if (!best) {
            const alignment = alignmentCandidate(drawing, null, alignTol, { excludeId: object.id }, sources);
            if (alignment.bestX || alignment.bestY) {
                const correctionX = alignment.bestX ? alignment.bestX.delta : 0;
                const correctionY = alignment.bestY ? alignment.bestY.delta : 0;
                const source = (alignment.bestX || alignment.bestY).source;
                const target = (alignment.bestX || alignment.bestY).target;
                const correctedSource = G.point(source.point.x + correctionX, source.point.y + correctionY);
                const type = alignment.bestX && alignment.bestY ? "xy-alignment" : alignment.bestX ? "vertical-alignment" : "horizontal-alignment";
                best = moveCandidate("alignment", source, target, correctionX, correctionY, Math.min(alignment.bestX ? Math.abs(alignment.bestX.delta) : Infinity, alignment.bestY ? Math.abs(alignment.bestY.delta) : Infinity), guide(type, correctedSource, target.point, {
                    xAnchor: alignment.bestX ? alignment.bestX.target : null,
                    yAnchor: alignment.bestY ? alignment.bestY.target : null,
                }));
            }
        }

        if (!best) {
            return Object.freeze({
                object: moved,
                point: null,
                rawPoint: null,
                snapped: false,
                target: null,
                source: null,
                distanceMm: null,
                toleranceMm: G.roundMm(captureMm),
                releaseToleranceMm: G.roundMm(releaseToleranceMm),
                axis: null,
                anchor: null,
                kind: "move",
                intent: "move",
                sticky: false,
                smartGuide: null,
            });
        }

        const corrected = G.translateObject(moved, best.correctionX, best.correctionY);
        return Object.freeze({
            object: corrected,
            point: G.point(best.source.point.x + best.correctionX, best.source.point.y + best.correctionY),
            rawPoint: best.source.point,
            snapped: true,
            target: best.target,
            source: best.source,
            distanceMm: G.roundMm(best.distanceMm),
            toleranceMm: G.roundMm(captureMm),
            releaseToleranceMm: G.roundMm(releaseToleranceMm),
            axis: null,
            anchor: best.source.point,
            kind: best.kind,
            intent: best.kind,
            sticky: Boolean(best.sticky),
            smartGuide: best.smartGuide || null,
        });
    }

    root.Snapping = Object.freeze({
        ...Base,
        MOVE_CAPTURE_PX,
        MOVE_RELEASE_FACTOR,
        ENDPOINT_PX,
        INTERSECTION_PX,
        MIDPOINT_PX,
        SURFACE_PX,
        ALIGN_PX,
        EQUAL_LENGTH_PX,
        ANGLE_TOLERANCE_DEG,
        INTENT_PRIORITY,
        segmentIntersection,
        midpointAnchors,
        intersectionAnchors,
        intentAnchors,
        nearestSurface,
        alignmentCandidate,
        exactAngleCandidate,
        resolvePoint,
        resolveObjectMove,
    });
    root.UnifiedSnapEngine = Object.freeze({
        MOVE_CAPTURE_PX,
        MOVE_RELEASE_FACTOR,
        INTENT_PRIORITY,
        segmentIntersection,
        midpointAnchors,
        intersectionAnchors,
        intentAnchors,
        resolvePoint,
        resolveObjectMove,
    });
})();
