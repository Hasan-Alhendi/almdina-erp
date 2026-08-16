(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);
    const geometry = root.Geometry;
    if (!geometry) throw new Error("Drawing V4 geometry must load before document model");

    const SCHEMA = "almdina.door-drawing";
    const VERSION = 4;
    const UNITS = "mm";
    const DIMENSION_TYPES = Object.freeze({ SEGMENT_LENGTH: "segment-length" });

    function freezeNode(node) {
        return Object.freeze({
            id: String(node.id),
            xMm: geometry.roundMm(node.xMm),
            yMm: geometry.roundMm(node.yMm),
        });
    }

    function freezeSegment(segment) {
        return Object.freeze({
            id: String(segment.id),
            type: "line",
            startNodeId: String(segment.startNodeId),
            endNodeId: String(segment.endNodeId),
        });
    }

    function freezePath(path) {
        return Object.freeze({
            id: String(path.id),
            startNodeId: String(path.startNodeId),
            segmentIds: Object.freeze((path.segmentIds || []).map(String)),
            closed: Boolean(path.closed),
        });
    }

    function freezeDimension(dimension) {
        const type = String(dimension && dimension.type || "");
        if (type !== DIMENSION_TYPES.SEGMENT_LENGTH) {
            throw new Error(`Unsupported drawing dimension type: ${type}`);
        }
        return Object.freeze({
            id: String(dimension.id),
            type,
            segmentId: String(dimension.segmentId),
        });
    }

    function freezeDocument(document) {
        const nodes = Object.freeze((document.nodes || []).map(freezeNode));
        const segments = Object.freeze((document.segments || []).map(freezeSegment));
        const paths = Object.freeze((document.paths || []).map(freezePath));
        const dimensions = Object.freeze((document.dimensions || []).map(freezeDimension));
        const segmentIds = new Set(segments.map(segment => segment.id));
        dimensions.forEach(dimension => {
            if (!segmentIds.has(dimension.segmentId)) {
                throw new Error(`Drawing dimension references missing segment: ${dimension.segmentId}`);
            }
        });
        return Object.freeze({
            schema: SCHEMA,
            version: VERSION,
            units: UNITS,
            blank: Object.freeze({
                widthMm: Math.max(0, geometry.roundMm(document.blank && document.blank.widthMm)),
                heightMm: Math.max(0, geometry.roundMm(document.blank && document.blank.heightMm)),
            }),
            nodes,
            segments,
            paths,
            dimensions,
        });
    }

    function create(options = {}) {
        return freezeDocument({
            blank: {
                widthMm: options.widthMm,
                heightMm: options.heightMm,
            },
            nodes: options.nodes || [],
            segments: options.segments || [],
            paths: options.paths || [],
            dimensions: options.dimensions || [],
        });
    }

    function nodeById(document, id) {
        return (document.nodes || []).find(node => node.id === String(id)) || null;
    }

    function segmentById(document, id) {
        return (document.segments || []).find(segment => segment.id === String(id)) || null;
    }

    function pathById(document, id) {
        return (document.paths || []).find(path => path.id === String(id)) || null;
    }

    function dimensionById(document, id) {
        return (document.dimensions || []).find(dimension => dimension.id === String(id)) || null;
    }

    function ensureUniqueId(document, id) {
        const value = String(id || "");
        if (!value) throw new Error("Drawing entity id is required");
        if (
            nodeById(document, value)
            || segmentById(document, value)
            || pathById(document, value)
            || dimensionById(document, value)
        ) {
            throw new Error(`Duplicate drawing entity id: ${value}`);
        }
        return value;
    }

    function addNode(document, node) {
        const id = ensureUniqueId(document, node && node.id);
        return freezeDocument({
            ...document,
            nodes: [...document.nodes, { ...node, id }],
        });
    }

    function moveNode(document, nodeId, nextPoint) {
        const id = String(nodeId);
        if (!nodeById(document, id)) throw new Error(`Drawing node not found: ${id}`);
        return freezeDocument({
            ...document,
            nodes: document.nodes.map(node => node.id === id
                ? { ...node, xMm: nextPoint.xMm, yMm: nextPoint.yMm }
                : node),
        });
    }

    function addPath(document, path) {
        const id = ensureUniqueId(document, path && path.id);
        const startNodeId = String(path && path.startNodeId || "");
        if (!nodeById(document, startNodeId)) throw new Error("Path start node does not exist");
        return freezeDocument({
            ...document,
            paths: [...document.paths, { id, startNodeId, segmentIds: [], closed: false }],
        });
    }

    function pathEndNodeId(document, pathId) {
        const path = pathById(document, pathId);
        if (!path) throw new Error(`Drawing path not found: ${pathId}`);
        if (!path.segmentIds.length) return path.startNodeId;
        const lastSegment = segmentById(document, path.segmentIds[path.segmentIds.length - 1]);
        if (!lastSegment) throw new Error("Drawing path contains a missing segment");
        return lastSegment.endNodeId;
    }

    function addLineToPath(document, pathId, segment) {
        const path = pathById(document, pathId);
        if (!path) throw new Error(`Drawing path not found: ${pathId}`);
        if (path.closed) throw new Error("Cannot append to a closed drawing path");

        const id = ensureUniqueId(document, segment && segment.id);
        const expectedStartNodeId = pathEndNodeId(document, pathId);
        const startNodeId = String(segment && segment.startNodeId || "");
        const endNodeId = String(segment && segment.endNodeId || "");

        if (startNodeId !== expectedStartNodeId) {
            throw new Error("New drawing segment must continue from the current path endpoint");
        }
        const startNode = nodeById(document, startNodeId);
        const endNode = nodeById(document, endNodeId);
        if (!startNode || !endNode) throw new Error("Drawing segment nodes must exist");
        geometry.assertPositiveLength(startNode, endNode);

        const line = { id, type: "line", startNodeId, endNodeId };
        return freezeDocument({
            ...document,
            segments: [...document.segments, line],
            paths: document.paths.map(item => item.id === path.id
                ? { ...item, segmentIds: [...item.segmentIds, id] }
                : item),
        });
    }

    function closePath(document, pathId, closingSegmentId) {
        const path = pathById(document, pathId);
        if (!path) throw new Error(`Drawing path not found: ${pathId}`);
        if (path.closed) return document;
        if (path.segmentIds.length < 2) throw new Error("A drawing path needs at least two segments before closing");

        const endNodeId = pathEndNodeId(document, pathId);
        let nextDocument = document;
        if (endNodeId !== path.startNodeId) {
            nextDocument = addLineToPath(nextDocument, pathId, {
                id: closingSegmentId,
                startNodeId: endNodeId,
                endNodeId: path.startNodeId,
            });
        }

        return freezeDocument({
            ...nextDocument,
            paths: nextDocument.paths.map(item => item.id === path.id
                ? { ...item, closed: true }
                : item),
        });
    }

    function addDimension(document, dimension) {
        const id = ensureUniqueId(document, dimension && dimension.id);
        const type = String(dimension && dimension.type || "");
        const segmentId = String(dimension && dimension.segmentId || "");
        if (type !== DIMENSION_TYPES.SEGMENT_LENGTH) {
            throw new Error(`Unsupported drawing dimension type: ${type}`);
        }
        if (!segmentById(document, segmentId)) {
            throw new Error(`Drawing dimension segment not found: ${segmentId}`);
        }
        return freezeDocument({
            ...document,
            dimensions: [...document.dimensions, { id, type, segmentId }],
        });
    }

    function removeDimension(document, dimensionId) {
        const id = String(dimensionId || "");
        if (!dimensionById(document, id)) return document;
        return freezeDocument({
            ...document,
            dimensions: document.dimensions.filter(dimension => dimension.id !== id),
        });
    }

    function serialize(document) {
        return JSON.stringify(document);
    }

    root.DocumentModel = Object.freeze({
        SCHEMA,
        VERSION,
        UNITS,
        DIMENSION_TYPES,
        create,
        nodeById,
        segmentById,
        pathById,
        dimensionById,
        pathEndNodeId,
        addNode,
        moveNode,
        addPath,
        addLineToPath,
        closePath,
        addDimension,
        removeDimension,
        serialize,
    });
})();