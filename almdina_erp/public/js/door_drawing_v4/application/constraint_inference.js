(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);
    const geometry = root.Geometry;
    const documentModel = root.DocumentModel;
    const constraintCommands = root.ConstraintCommands;
    if (!geometry || !documentModel || !constraintCommands) {
        throw new Error("Drawing V4 constraint commands must load before constraint inference");
    }

    const DEFAULT_AXIS_TOLERANCE_MM = 0.01;

    function pathContainingSegment(document, segmentId) {
        const id = String(segmentId || "");
        return (document.paths || []).find(path => path.segmentIds.includes(id)) || null;
    }

    function inferSegmentAxis(document, segmentId, options = {}) {
        const segment = documentModel.segmentById(document, segmentId);
        if (!segment) return Object.freeze({ document, segmentId: String(segmentId || ""), type: null, created: false });
        const start = documentModel.nodeById(document, segment.startNodeId);
        const end = documentModel.nodeById(document, segment.endNodeId);
        if (!start || !end) return Object.freeze({ document, segmentId: segment.id, type: null, created: false });
        const toleranceMm = Math.max(geometry.EPSILON_MM, Number(options.toleranceMm) || DEFAULT_AXIS_TOLERANCE_MM);
        const dx = Math.abs(end.xMm - start.xMm);
        const dy = Math.abs(end.yMm - start.yMm);
        if (geometry.distance(start, end) <= geometry.EPSILON_MM) {
            return Object.freeze({ document, segmentId: segment.id, type: null, created: false });
        }
        if (dy <= toleranceMm && dx > toleranceMm) {
            const result = constraintCommands.ensureHorizontal(document, segment.id, options);
            return Object.freeze({ ...result, segmentId: segment.id, type: documentModel.CONSTRAINT_TYPES.HORIZONTAL });
        }
        if (dx <= toleranceMm && dy > toleranceMm) {
            const result = constraintCommands.ensureVertical(document, segment.id, options);
            return Object.freeze({ ...result, segmentId: segment.id, type: documentModel.CONSTRAINT_TYPES.VERTICAL });
        }
        return Object.freeze({ document, segmentId: segment.id, type: null, created: false });
    }

    function inferPathOrthogonality(document, segmentId, options = {}) {
        const path = pathContainingSegment(document, segmentId);
        const segmentIds = path ? path.segmentIds : [String(segmentId || "")];
        let nextDocument = document;
        const createdConstraintIds = [];
        const inferred = [];
        segmentIds.forEach(id => {
            const result = inferSegmentAxis(nextDocument, id, options);
            nextDocument = result.document;
            if (result.type) inferred.push(Object.freeze({ segmentId: id, type: result.type }));
            if (result.created) createdConstraintIds.push(result.constraintId);
        });
        return Object.freeze({
            document: nextDocument,
            pathId: path ? path.id : null,
            inferred: Object.freeze(inferred),
            createdConstraintIds: Object.freeze(createdConstraintIds),
        });
    }

    root.ConstraintInference = Object.freeze({
        DEFAULT_AXIS_TOLERANCE_MM,
        pathContainingSegment,
        inferSegmentAxis,
        inferPathOrthogonality,
    });
})();
