(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);
    const geometry = root.Geometry;
    const documentModel = root.DocumentModel;
    const constraintDomain = root.ConstraintDomain;
    const constraintCommands = root.ConstraintCommands;
    if (!geometry || !documentModel || !constraintDomain || !constraintCommands) {
        throw new Error("Drawing V4 constraint domain and commands must load before constraint solver");
    }

    const DEFAULT_TOLERANCE_MM = 0.01;
    const DEFAULT_MAX_ITERATIONS = 32;

    function pointCopy(node) {
        return { xMm: Number(node.xMm), yMm: Number(node.yMm) };
    }

    function mutablePoints(document) {
        return new Map((document.nodes || []).map(node => [node.id, pointCopy(node)]));
    }

    function segmentPoints(document, points, segmentId) {
        const segment = documentModel.segmentById(document, segmentId);
        if (!segment) return null;
        const start = points.get(segment.startNodeId);
        const end = points.get(segment.endNodeId);
        if (!start || !end) return null;
        return { segment, start, end };
    }

    function distance(left, right) {
        return Math.hypot(right.xMm - left.xMm, right.yMm - left.yMm);
    }

    function moveCoordinate(target, axis, value) {
        const before = target[axis];
        target[axis] = value;
        return Math.abs(before - value);
    }

    function applyAxisConstraint(document, points, constraint, pinned) {
        const resolved = segmentPoints(document, points, constraint.segmentId);
        if (!resolved) return 0;
        const { segment, start, end } = resolved;
        const axis = constraint.type === documentModel.CONSTRAINT_TYPES.HORIZONTAL ? "yMm" : "xMm";
        const startPinned = pinned.has(segment.startNodeId);
        const endPinned = pinned.has(segment.endNodeId);
        if (startPinned && endPinned) return 0;
        if (endPinned) return moveCoordinate(start, axis, end[axis]);
        return moveCoordinate(end, axis, start[axis]);
    }

    function applyFixedLength(document, points, constraint, pinned) {
        const resolved = segmentPoints(document, points, constraint.segmentId);
        if (!resolved) return 0;
        const { segment, start, end } = resolved;
        const anchorIsStart = constraint.anchorNodeId === segment.startNodeId;
        const anchor = anchorIsStart ? start : end;
        const movable = anchorIsStart ? end : start;
        const movableNodeId = anchorIsStart ? segment.endNodeId : segment.startNodeId;
        if (pinned.has(movableNodeId)) return 0;

        let dx = movable.xMm - anchor.xMm;
        let dy = movable.yMm - anchor.yMm;
        let currentLength = Math.hypot(dx, dy);
        if (currentLength <= geometry.EPSILON_MM) {
            const originalAnchor = documentModel.nodeById(document, constraint.anchorNodeId);
            const originalMovable = documentModel.nodeById(document, movableNodeId);
            if (!originalAnchor || !originalMovable) return 0;
            dx = originalMovable.xMm - originalAnchor.xMm;
            dy = originalMovable.yMm - originalAnchor.yMm;
            currentLength = Math.hypot(dx, dy);
            if (currentLength <= geometry.EPSILON_MM) return 0;
        }

        const scale = constraint.valueMm / currentLength;
        const nextX = anchor.xMm + dx * scale;
        const nextY = anchor.yMm + dy * scale;
        const movement = Math.hypot(nextX - movable.xMm, nextY - movable.yMm);
        movable.xMm = nextX;
        movable.yMm = nextY;
        return movement;
    }

    function orderedConstraints(document) {
        const rank = {
            [documentModel.CONSTRAINT_TYPES.HORIZONTAL]: 10,
            [documentModel.CONSTRAINT_TYPES.VERTICAL]: 10,
            [documentModel.CONSTRAINT_TYPES.FIXED_LENGTH]: 20,
        };
        return [...(document.constraints || [])].sort((left, right) => {
            const rankDelta = (rank[left.type] || 99) - (rank[right.type] || 99);
            if (rankDelta) return rankDelta;
            return String(left.id).localeCompare(String(right.id));
        });
    }

    function pinnedNodes(document, options = {}) {
        const pinned = new Set((options.pinnedNodeIds || []).map(String));
        (document.constraints || []).forEach(constraint => {
            if (constraint.type === documentModel.CONSTRAINT_TYPES.FIXED_LENGTH && constraint.anchorNodeId) {
                pinned.add(constraint.anchorNodeId);
            }
        });
        return pinned;
    }

    function validateGeometry(document) {
        for (const segment of document.segments || []) {
            const start = documentModel.nodeById(document, segment.startNodeId);
            const end = documentModel.nodeById(document, segment.endNodeId);
            if (!start || !end || geometry.distance(start, end) <= geometry.EPSILON_MM) {
                return Object.freeze({ ok: false, code: "invalid-geometry", segmentId: segment.id });
            }
        }
        return Object.freeze({ ok: true });
    }

    function solve(document, options = {}) {
        const toleranceMm = Math.max(geometry.EPSILON_MM, Number(options.toleranceMm) || DEFAULT_TOLERANCE_MM);
        const maxIterations = Math.max(1, Math.floor(Number(options.maxIterations) || DEFAULT_MAX_ITERATIONS));
        if (!(document.constraints || []).length) {
            return Object.freeze({ ok: true, changed: false, document, iterations: 0, residuals: Object.freeze([]) });
        }

        const points = mutablePoints(document);
        const pinned = pinnedNodes(document, options);
        const constraints = orderedConstraints(document);
        let iterations = 0;

        for (let iteration = 0; iteration < maxIterations; iteration += 1) {
            iterations = iteration + 1;
            let maxMovementMm = 0;
            constraints.forEach(constraint => {
                let movementMm = 0;
                if ([documentModel.CONSTRAINT_TYPES.HORIZONTAL, documentModel.CONSTRAINT_TYPES.VERTICAL].includes(constraint.type)) {
                    movementMm = applyAxisConstraint(document, points, constraint, pinned);
                } else if (constraint.type === documentModel.CONSTRAINT_TYPES.FIXED_LENGTH) {
                    movementMm = applyFixedLength(document, points, constraint, pinned);
                }
                maxMovementMm = Math.max(maxMovementMm, movementMm);
            });
            if (maxMovementMm <= toleranceMm / 10) break;
        }

        const candidate = documentModel.updateNodePositions(document, points);
        const geometryCheck = validateGeometry(candidate);
        if (!geometryCheck.ok) {
            return Object.freeze({ ...geometryCheck, changed: false, document, iterations, residuals: Object.freeze([]) });
        }

        const residuals = Object.freeze(constraintDomain.all(candidate).map(constraint => Object.freeze({
            constraintId: constraint.id,
            type: constraint.type,
            segmentId: constraint.segmentId,
            residualMm: constraint.residualMm,
        })));
        const maxResidualMm = residuals.reduce((maximum, item) => Math.max(maximum, item.residualMm), 0);
        if (maxResidualMm > toleranceMm) {
            return Object.freeze({
                ok: false,
                code: "constraint-conflict",
                changed: false,
                document,
                iterations,
                maxResidualMm,
                residuals,
            });
        }

        return Object.freeze({
            ok: true,
            changed: candidate !== document,
            document: candidate,
            iterations,
            maxResidualMm,
            residuals,
        });
    }

    function driveSegmentLength(document, segmentId, valueMm, options = {}) {
        const before = document;
        const prepared = constraintCommands.ensureFixedLength(document, segmentId, valueMm, options);
        const solved = solve(prepared.document, options);
        if (!solved.ok) {
            return Object.freeze({
                ...solved,
                document: before,
                constraintId: prepared.constraintId,
            });
        }
        return Object.freeze({
            ...solved,
            constraintId: prepared.constraintId,
            constraintCreated: prepared.created,
            constraintChanged: prepared.changed,
        });
    }

    root.ConstraintSolver = Object.freeze({
        DEFAULT_TOLERANCE_MM,
        DEFAULT_MAX_ITERATIONS,
        solve,
        driveSegmentLength,
    });
})();
