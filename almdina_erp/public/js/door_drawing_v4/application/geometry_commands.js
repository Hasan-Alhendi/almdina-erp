(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);
    const geometry = root.Geometry;
    const documentModel = root.DocumentModel;
    if (!geometry || !documentModel) throw new Error("Drawing V4 domain must load before geometry commands");

    function createIdFactory(prefix = "v4") {
        let sequence = 0;
        return kind => `${prefix}-${kind}-${++sequence}`;
    }

    function startPath(document, atPoint, options = {}) {
        const nextId = options.idFactory || createIdFactory();
        const nodeId = options.nodeId || nextId("node");
        const pathId = options.pathId || nextId("path");
        let nextDocument = documentModel.addNode(document, {
            id: nodeId,
            xMm: atPoint.xMm,
            yMm: atPoint.yMm,
        });
        nextDocument = documentModel.addPath(nextDocument, {
            id: pathId,
            startNodeId: nodeId,
        });
        return Object.freeze({ document: nextDocument, pathId, nodeId });
    }

    function appendLine(document, pathId, target, options = {}) {
        const nextId = options.idFactory || createIdFactory();
        const startNodeId = documentModel.pathEndNodeId(document, pathId);
        const startNode = documentModel.nodeById(document, startNodeId);
        let endNodeId = target && target.nodeId ? String(target.nodeId) : null;
        let nextDocument = document;

        if (endNodeId) {
            if (!documentModel.nodeById(document, endNodeId)) throw new Error("Snapped drawing node does not exist");
        } else {
            endNodeId = options.nodeId || nextId("node");
            nextDocument = documentModel.addNode(nextDocument, {
                id: endNodeId,
                xMm: target.point.xMm,
                yMm: target.point.yMm,
            });
        }

        const endNode = documentModel.nodeById(nextDocument, endNodeId);
        geometry.assertPositiveLength(startNode, endNode);
        const segmentId = options.segmentId || nextId("segment");
        nextDocument = documentModel.addLineToPath(nextDocument, pathId, {
            id: segmentId,
            startNodeId,
            endNodeId,
        });
        return Object.freeze({ document: nextDocument, pathId, nodeId: endNodeId, segmentId });
    }

    function closePath(document, pathId, options = {}) {
        const nextId = options.idFactory || createIdFactory();
        const path = documentModel.pathById(document, pathId);
        if (!path) throw new Error(`Drawing path not found: ${pathId}`);
        const currentEndNodeId = documentModel.pathEndNodeId(document, pathId);
        let nextDocument = document;

        if (currentEndNodeId !== path.startNodeId) {
            nextDocument = appendLine(nextDocument, pathId, {
                nodeId: path.startNodeId,
                point: documentModel.nodeById(nextDocument, path.startNodeId),
            }, {
                idFactory: nextId,
                segmentId: options.segmentId || nextId("segment"),
            }).document;
        }

        nextDocument = documentModel.closePath(nextDocument, pathId, options.segmentId || nextId("segment"));
        return Object.freeze({ document: nextDocument, pathId });
    }

    root.GeometryCommands = Object.freeze({
        createIdFactory,
        startPath,
        appendLine,
        closePath,
    });
})();