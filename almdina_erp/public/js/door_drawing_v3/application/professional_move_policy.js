(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    const S = root.Snapping;
    const Selection = root.VectorSelectionGeometry;
    if (!G || !S || !Selection) throw new Error("Door Drawing V3 snapping and selection geometry must load before professional move policy");

    const ALIGN_PX = 8;
    const SPACING_PX = 9;

    function translateBounds(box, dx, dy) {
        return Selection.bounds(box.left + dx, box.top + dy, box.right + dx, box.bottom + dy);
    }

    function axisValues(box, axis) {
        if (axis === "x") return [
            { role: "left", value: box.left },
            { role: "center-x", value: box.cx },
            { role: "right", value: box.right },
        ];
        return [
            { role: "bottom", value: box.bottom },
            { role: "center-y", value: box.cy },
            { role: "top", value: box.top },
        ];
    }

    function otherBounds(document, excludedIds) {
        const excluded = new Set((excludedIds || []).map(String));
        return ((document && document.objects) || [])
            .filter(object => !excluded.has(String(object.id)))
            .map(object => ({ object, box: Selection.boundsOfObject(object) }))
            .filter(item => item.box);
    }

    function bestAlignment(moved, others, axis, toleranceMm) {
        let best = null;
        const sourceValues = axisValues(moved, axis);
        for (const target of others) {
            for (const source of sourceValues) {
                for (const destination of axisValues(target.box, axis)) {
                    const correction = destination.value - source.value;
                    const distance = Math.abs(correction);
                    if (distance > toleranceMm) continue;
                    if (!best || distance < best.distance - G.EPSILON_MM) {
                        best = {
                            axis,
                            correction,
                            distance,
                            sourceRole: source.role,
                            targetRole: destination.role,
                            targetId: String(target.object.id),
                            targetBox: target.box,
                        };
                    }
                }
            }
        }
        return best;
    }

    function overlap(a1, a2, b1, b2) {
        return Math.min(a2, b2) - Math.max(a1, b1);
    }

    function nearestNeighbors(moved, others, axis) {
        let before = null, after = null;
        for (const item of others) {
            const box = item.box;
            const crossOverlap = axis === "x"
                ? overlap(moved.top, moved.bottom, box.top, box.bottom)
                : overlap(moved.left, moved.right, box.left, box.right);
            const crossSize = axis === "x" ? Math.min(moved.height, box.height) : Math.min(moved.width, box.width);
            if (crossSize > G.EPSILON_MM && crossOverlap < -crossSize * 0.15) continue;
            const beforeGap = axis === "x" ? moved.left - box.right : moved.top - box.bottom;
            const afterGap = axis === "x" ? box.left - moved.right : box.top - moved.bottom;
            if (beforeGap >= -G.EPSILON_MM && (!before || beforeGap < before.gap)) before = { ...item, gap: Math.max(0, beforeGap) };
            if (afterGap >= -G.EPSILON_MM && (!after || afterGap < after.gap)) after = { ...item, gap: Math.max(0, afterGap) };
        }
        return { before, after };
    }

    function referenceGaps(others, axis) {
        const ordered = others.slice().sort((a, b) => axis === "x" ? a.box.left - b.box.left : a.box.top - b.box.top);
        const gaps = [];
        for (let i = 0; i < ordered.length - 1; i += 1) {
            const first = ordered[i], second = ordered[i + 1];
            const gap = axis === "x" ? second.box.left - first.box.right : second.box.top - first.box.bottom;
            if (gap < -G.EPSILON_MM) continue;
            gaps.push({ axis, value: Math.max(0, gap), first, second });
        }
        return gaps;
    }

    function bestSpacing(moved, others, axis, toleranceMm) {
        const neighbors = nearestNeighbors(moved, others, axis);
        let best = null;

        if (neighbors.before && neighbors.after) {
            const delta = neighbors.before.gap - neighbors.after.gap;
            if (Math.abs(delta) <= toleranceMm * 2) {
                const correction = -delta / 2;
                best = {
                    axis,
                    correction,
                    distance: Math.abs(delta) / 2,
                    gap: (neighbors.before.gap + neighbors.after.gap) / 2,
                    before: neighbors.before,
                    after: neighbors.after,
                    mode: "balanced",
                };
            }
        }

        const references = referenceGaps(others, axis);
        for (const reference of references) {
            for (const side of ["before", "after"]) {
                const neighbor = neighbors[side];
                if (!neighbor) continue;
                const delta = neighbor.gap - reference.value;
                if (Math.abs(delta) > toleranceMm) continue;
                const correction = side === "before" ? -delta : delta;
                const candidate = {
                    axis,
                    correction,
                    distance: Math.abs(delta),
                    gap: reference.value,
                    before: side === "before" ? neighbor : null,
                    after: side === "after" ? neighbor : null,
                    reference,
                    mode: "match-gap",
                };
                if (!best || candidate.distance < best.distance - G.EPSILON_MM) best = candidate;
            }
        }
        return best;
    }

    function lineGuide(axis, moved, alignment) {
        if (!alignment) return null;
        const target = alignment.targetBox;
        if (axis === "x") {
            const x = alignment.targetRole === "left" ? target.left : alignment.targetRole === "right" ? target.right : target.cx;
            return Object.freeze({ type: "alignment", axis: "x", x, from: Math.min(moved.top, target.top), to: Math.max(moved.bottom, target.bottom), targetId: alignment.targetId, role: alignment.targetRole });
        }
        const y = alignment.targetRole === "bottom" ? target.bottom : alignment.targetRole === "top" ? target.top : target.cy;
        return Object.freeze({ type: "alignment", axis: "y", y, from: Math.min(moved.left, target.left), to: Math.max(moved.right, target.right), targetId: alignment.targetId, role: alignment.targetRole });
    }

    function spacingGuides(axis, moved, spacing) {
        if (!spacing) return [];
        const guides = [];
        if (spacing.before) {
            const from = axis === "x" ? spacing.before.box.right : spacing.before.box.bottom;
            const to = axis === "x" ? moved.left : moved.top;
            guides.push(Object.freeze({ type: "spacing", axis, from, to, at: axis === "x" ? moved.cy : moved.cx, distanceMm: Math.abs(to - from) }));
        }
        if (spacing.after) {
            const from = axis === "x" ? moved.right : moved.bottom;
            const to = axis === "x" ? spacing.after.box.left : spacing.after.box.top;
            guides.push(Object.freeze({ type: "spacing", axis, from, to, at: axis === "x" ? moved.cy : moved.cx, distanceMm: Math.abs(to - from) }));
        }
        if (spacing.reference) {
            const first = spacing.reference.first.box, second = spacing.reference.second.box;
            const from = axis === "x" ? first.right : first.bottom;
            const to = axis === "x" ? second.left : second.top;
            const at = axis === "x" ? (first.cy + second.cy) / 2 : (first.cx + second.cx) / 2;
            guides.push(Object.freeze({ type: "spacing-reference", axis, from, to, at, distanceMm: spacing.reference.value }));
        }
        return guides;
    }

    function resolve(document, sourceObjects, requestedDx, requestedDy, options = {}) {
        const sourceBounds = Selection.unionBounds(sourceObjects || []);
        if (!sourceBounds) return Object.freeze({ dx: 0, dy: 0, guides: Object.freeze([]), snapped: false });
        const excludedIds = (sourceObjects || []).map(object => String(object.id));
        const others = otherBounds(document, excludedIds);
        const alignTolerance = S.worldTolerance(options.viewportScale, options.alignPx || ALIGN_PX);
        const spacingTolerance = S.worldTolerance(options.viewportScale, options.spacingPx || SPACING_PX);
        const lockedAxis = options.lockedAxis === "x" || options.lockedAxis === "y" ? options.lockedAxis : null;
        let dx = G.number(requestedDx), dy = G.number(requestedDy);
        if (lockedAxis === "x") dy = 0;
        if (lockedAxis === "y") dx = 0;

        let moved = translateBounds(sourceBounds, dx, dy);
        const alignmentX = lockedAxis === "y" ? null : bestAlignment(moved, others, "x", alignTolerance);
        const alignmentY = lockedAxis === "x" ? null : bestAlignment(moved, others, "y", alignTolerance);
        const spacingX = lockedAxis === "y" || alignmentX ? null : bestSpacing(moved, others, "x", spacingTolerance);
        const spacingY = lockedAxis === "x" || alignmentY ? null : bestSpacing(moved, others, "y", spacingTolerance);

        if (alignmentX) dx += alignmentX.correction;
        else if (spacingX) dx += spacingX.correction;
        if (alignmentY) dy += alignmentY.correction;
        else if (spacingY) dy += spacingY.correction;
        moved = translateBounds(sourceBounds, dx, dy);

        const guides = [];
        const xGuide = lineGuide("x", moved, alignmentX);
        const yGuide = lineGuide("y", moved, alignmentY);
        if (xGuide) guides.push(xGuide);
        if (yGuide) guides.push(yGuide);
        guides.push(...spacingGuides("x", moved, spacingX));
        guides.push(...spacingGuides("y", moved, spacingY));
        if (lockedAxis) guides.push(Object.freeze({ type: "axis-lock", axis: lockedAxis, box: moved }));

        return Object.freeze({
            dx: G.roundMm(dx),
            dy: G.roundMm(dy),
            requestedDx: G.roundMm(requestedDx),
            requestedDy: G.roundMm(requestedDy),
            movedBounds: moved,
            lockedAxis,
            alignmentX,
            alignmentY,
            spacingX,
            spacingY,
            guides: Object.freeze(guides),
            snapped: Boolean(alignmentX || alignmentY || spacingX || spacingY),
        });
    }

    root.ProfessionalMovePolicy = Object.freeze({
        ALIGN_PX, SPACING_PX, translateBounds, axisValues, otherBounds, bestAlignment, nearestNeighbors, referenceGaps, bestSpacing, resolve,
    });
})();
