(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);
    const geometry = root.Geometry;
    const documentModel = root.DocumentModel;
    if (!geometry || !documentModel) throw new Error("Drawing V4 document must load before dimension domain");

    function resolve(document, dimensionOrId) {
        const dimension = typeof dimensionOrId === "object"
            ? dimensionOrId
            : documentModel.dimensionById(document, dimensionOrId);
        if (!dimension) return null;
        if (dimension.type !== documentModel.DIMENSION_TYPES.SEGMENT_LENGTH) return null;
        const segment = documentModel.segmentById(document, dimension.segmentId);
        if (!segment) return null;
        const start = documentModel.nodeById(document, segment.startNodeId);
        const end = documentModel.nodeById(document, segment.endNodeId);
        if (!start || !end) return null;
        const valueMm = geometry.roundMm(geometry.distance(start, end));
        return Object.freeze({
            id: dimension.id,
            type: dimension.type,
            segmentId: segment.id,
            start,
            end,
            valueMm,
            midpoint: geometry.point(
                (start.xMm + end.xMm) / 2,
                (start.yMm + end.yMm) / 2
            ),
            angleDeg: geometry.angleDeg(start, end),
        });
    }

    function all(document) {
        return Object.freeze((document.dimensions || []).map(dimension => resolve(document, dimension)).filter(Boolean));
    }

    root.DimensionDomain = Object.freeze({ resolve, all });
})();