(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);
    const geometry = root.Geometry;
    if (!geometry) throw new Error("Drawing V4 geometry must load before document model");

    const SCHEMA = "almdina.door-drawing";
    const VERSION = 4;
    const UNITS = "mm";

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

    function freezeDocument(document) {
        return Object.freeze({
            schema: SCHEMA,
            version: VERSION,
            units: UNITS,
            blank: Object.freeze({
                widthMm: Math.max(0, geometry.roundMm(document.blank && document.blank.widthMm)),
                heightMm: Math.max(0, geometry.roundMm(document.blank && document.blank.heightMm)),
            }),
            nodes: Object.freeze((document.nodes || []).map(freezeNode)),
            segments: Object.freeze((document.segments || []).map(freezeSegment)),
            paths: Object.freeze((document.paths || []).map(freezePath)),
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

    function ensureUniqueId(document, id) {
        const value = String(id || "");
        if (!value) throw new Error("Drawing entity id is required");
        if (nodeById(document, value) || segmentById(document, value) || pathById(document, value)) {
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

    function serialize(document) {
        return JSON.stringify(document);
    }

    root.DocumentModel = Object.freeze({
        SCHEMA,
        VERSION,
        UNITS,
        create,
        nodeById,
        segmentById,
        pathById,
        pathEndNodeId,
        addNode,
        moveNode,
        addPath,
        addLineToPath,
        closePath,
        serialize,
    });
})();