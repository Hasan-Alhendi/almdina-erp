(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);
    const documentModel = root.DocumentModel;
    const dimensionDomain = root.DimensionDomain;
    const geometryCommands = root.GeometryCommands;
    if (!documentModel || !dimensionDomain || !geometryCommands) {
        throw new Error("Drawing V4 dimension dependencies must load before dimension commands");
    }

    function existingForSegment(document, segmentId) {
        const id = String(segmentId || "");
        return (document.dimensions || []).find(dimension => (
            dimension.type === documentModel.DIMENSION_TYPES.SEGMENT_LENGTH
            && dimension.segmentId === id
        )) || null;
    }

    function ensureSegmentLength(document, segmentId, options = {}) {
        const id = String(segmentId || "");
        if (!documentModel.segmentById(document, id)) {
            throw new Error(`Drawing segment not found: ${id}`);
        }
        const existing = existingForSegment(document, id);
        if (existing) {
            return Object.freeze({
                document,
                dimensionId: existing.id,
                created: false,
                measurement: dimensionDomain.resolve(document, existing),
            });
        }
        const idFactory = options.idFactory || geometryCommands.createIdFactory("dim");
        const dimensionId = String(options.id || idFactory("dimension"));
        const nextDocument = documentModel.addDimension(document, {
            id: dimensionId,
            type: documentModel.DIMENSION_TYPES.SEGMENT_LENGTH,
            segmentId: id,
        });
        return Object.freeze({
            document: nextDocument,
            dimensionId,
            created: true,
            measurement: dimensionDomain.resolve(nextDocument, dimensionId),
        });
    }

    function remove(document, dimensionId) {
        const id = String(dimensionId || "");
        if (!documentModel.dimensionById(document, id)) {
            return Object.freeze({ document, dimensionId: id, removed: false });
        }
        return Object.freeze({
            document: documentModel.removeDimension(document, id),
            dimensionId: id,
            removed: true,
        });
    }

    root.DimensionCommands = Object.freeze({
        existingForSegment,
        ensureSegmentLength,
        remove,
    });
})();