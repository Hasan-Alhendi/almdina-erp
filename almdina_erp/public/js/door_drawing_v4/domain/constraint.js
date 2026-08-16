(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);
    const geometry = root.Geometry;
    const documentModel = root.DocumentModel;
    if (!geometry || !documentModel) throw new Error("Drawing V4 document must load before constraint domain");

    function resolve(document, constraintOrId) {
        const constraint = typeof constraintOrId === "object"
            ? constraintOrId
            : documentModel.constraintById(document, constraintOrId);
        if (!constraint) return null;
        const segment = documentModel.segmentById(document, constraint.segmentId);
        if (!segment) return null;
        const start = documentModel.nodeById(document, segment.startNodeId);
        const end = documentModel.nodeById(document, segment.endNodeId);
        if (!start || !end) return null;

        let residualMm = 0;
        if (constraint.type === documentModel.CONSTRAINT_TYPES.HORIZONTAL) {
            residualMm = Math.abs(end.yMm - start.yMm);
        } else if (constraint.type === documentModel.CONSTRAINT_TYPES.VERTICAL) {
            residualMm = Math.abs(end.xMm - start.xMm);
        } else if (constraint.type === documentModel.CONSTRAINT_TYPES.FIXED_LENGTH) {
            residualMm = Math.abs(geometry.distance(start, end) - constraint.valueMm);
        } else {
            return null;
        }

        return Object.freeze({
            id: constraint.id,
            type: constraint.type,
            segmentId: segment.id,
            anchorNodeId: constraint.anchorNodeId || null,
            valueMm: constraint.type === documentModel.CONSTRAINT_TYPES.FIXED_LENGTH
                ? constraint.valueMm
                : null,
            start,
            end,
            residualMm: geometry.roundMm(residualMm),
        });
    }

    function all(document) {
        return Object.freeze((document.constraints || []).map(constraint => resolve(document, constraint)).filter(Boolean));
    }

    function forSegment(document, segmentId) {
        const id = String(segmentId || "");
        return Object.freeze(all(document).filter(constraint => constraint.segmentId === id));
    }

    function isSatisfied(document, toleranceMm = 0.01) {
        const tolerance = Math.max(0, geometry.finiteNumber(toleranceMm));
        return all(document).every(constraint => constraint.residualMm <= tolerance);
    }

    root.ConstraintDomain = Object.freeze({
        resolve,
        all,
        forSegment,
        isSatisfied,
    });
})();
