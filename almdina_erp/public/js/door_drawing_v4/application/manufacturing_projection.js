(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);
    const geometry = root.Geometry;
    const documentModel = root.DocumentModel;
    if (!geometry || !documentModel) {
        throw new Error("Drawing V4 geometry and document model must load before manufacturing projection");
    }

    const MANUFACTURING_VERSION = 1;
    const MM_PER_CM = 10;

    function failure(code, details = {}) {
        return Object.freeze({ ok: false, code: String(code), ...details });
    }

    function cm(valueMm) {
        return geometry.roundMm(geometry.finiteNumber(valueMm) / MM_PER_CM);
    }

    function validateDocument(document) {
        if (
            !document
            || document.schema !== documentModel.SCHEMA
            || Number(document.version) !== documentModel.VERSION
            || document.units !== documentModel.UNITS
        ) {
            return failure("invalid-document");
        }
        if (
            !document.blank
            || geometry.finiteNumber(document.blank.widthMm) <= geometry.EPSILON_MM
            || geometry.finiteNumber(document.blank.heightMm) <= geometry.EPSILON_MM
        ) {
            return failure("invalid-blank");
        }
        return null;
    }

    function project(document) {
        const invalid = validateDocument(document);
        if (invalid) return invalid;

        const paths = (Array.isArray(document.paths) ? document.paths : [])
            .filter(path => Array.isArray(path.segmentIds) && path.segmentIds.length > 0);
        if (paths.length !== 1) {
            return failure(paths.length ? "ambiguous-boundary" : "missing-boundary", {
                pathCount: paths.length,
            });
        }

        const path = paths[0];
        if (!path.closed) return failure("open-boundary", { pathId: path.id });
        if (path.segmentIds.length < 3) {
            return failure("too-few-edges", { pathId: path.id });
        }

        const startNode = documentModel.nodeById(document, path.startNodeId);
        if (!startNode) return failure("missing-start-node", { pathId: path.id });

        const points = [];
        let expectedNodeId = path.startNodeId;
        const seenSegmentIds = new Set();

        for (let index = 0; index < path.segmentIds.length; index += 1) {
            const segmentId = String(path.segmentIds[index]);
            if (seenSegmentIds.has(segmentId)) {
                return failure("duplicate-segment", { pathId: path.id, segmentId });
            }
            seenSegmentIds.add(segmentId);

            const segment = documentModel.segmentById(document, segmentId);
            if (!segment) return failure("missing-segment", { pathId: path.id, segmentId });
            if (segment.type !== "line") {
                return failure("unsupported-segment", { pathId: path.id, segmentId, segmentType: segment.type });
            }
            if (segment.startNodeId !== expectedNodeId) {
                return failure("disconnected-boundary", { pathId: path.id, segmentId });
            }

            const start = documentModel.nodeById(document, segment.startNodeId);
            const end = documentModel.nodeById(document, segment.endNodeId);
            if (!start || !end) return failure("missing-node", { pathId: path.id, segmentId });
            if (geometry.distance(start, end) <= geometry.EPSILON_MM) {
                return failure("zero-length-edge", { pathId: path.id, segmentId });
            }

            points.push(Object.freeze([cm(start.xMm), cm(start.yMm)]));
            expectedNodeId = segment.endNodeId;
        }

        if (expectedNodeId !== path.startNodeId) {
            return failure("unclosed-boundary", { pathId: path.id });
        }

        return Object.freeze({
            ok: true,
            geometry: Object.freeze({
                version: MANUFACTURING_VERSION,
                kind: "polygon",
                units: "cm",
                template: "custom",
                blank_width_cm: cm(document.blank.widthMm),
                blank_length_cm: cm(document.blank.heightMm),
                points: Object.freeze(points),
                exact: true,
            }),
        });
    }

    root.ManufacturingProjection = Object.freeze({
        MANUFACTURING_VERSION,
        MM_PER_CM,
        project,
    });
})();
