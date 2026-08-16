(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);
    const geometry = root.Geometry;
    if (!geometry) throw new Error("Drawing V4 geometry must load before document model");

    const SCHEMA = "almdina.door-drawing";
    const VERSION = 4;
    const UNITS = "mm";
    const DIMENSION_TYPES = Object.freeze({ SEGMENT_LENGTH: "segment-length" });
    const CONSTRAINT_TYPES = Object.freeze({
        HORIZONTAL: "horizontal",
        VERTICAL: "vertical",
        FIXED_LENGTH: "fixed-length",
    });
    const KNOWN_CONSTRAINT_TYPES = Object.freeze(Object.values(CONSTRAINT_TYPES));

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

    function freezeConstraint(constraint) {
        const type = String(constraint && constraint.type || "");
        if (!KNOWN_CONSTRAINT_TYPES.includes(type)) {
            throw new Error(`Unsupported drawing constraint type: ${type}`);
        }
        const base = {
            id: String(constraint.id),
            type,
            segmentId: String(constraint.segmentId),
        };
        if (type !== CONSTRAINT_TYPES.FIXED_LENGTH) return Object.freeze(base);
        const valueMm = geometry.roundMm(constraint.valueMm);
        if (valueMm <= geometry.EPSILON_MM) {
            throw new Error("Fixed-length constraint must be greater than zero");
        }
        return Object.freeze({
            ...base,
            valueMm,
            anchorNodeId: String(constraint.anchorNodeId || ""),
        });
    }

    function assertUniqueEntityIds(groups) {
        const seen = new Set();
        groups.forEach(group => group.forEach(entity => {
            if (!entity.id || seen.has(entity.id)) throw new Error(`Duplicate drawing entity id: ${entity.id}`);
            seen.add(entity.id);
        }));
    }

    function freezeDocument(document) {
        const nodes = Object.freeze((document.nodes || []).map(freezeNode));
        const segments = Object.freeze((document.segments || []).map(freezeSegment));
        const paths = Object.freeze((document.paths || []).map(freezePath));
        const dimensions = Object.freeze((document.dimensions || []).map(freezeDimension));
        const constraints = Object.freeze((document.constraints || []).map(freezeConstraint));
        assertUniqueEntityIds([nodes, segments, paths, dimensions, constraints]);

        const nodeIds = new Set(nodes.map(node => node.id));
        const segmentById = new Map(segments.map(segment => [segment.id, segment]));
        dimensions.forEach(dimension => {
            if (!segmentById.has(dimension.segmentId)) {
                throw new Error(`Drawing dimension references missing segment: ${dimension.segmentId}`);
            }
        });

        const semanticConstraints = new Set();
        constraints.forEach(constraint => {
            const segment = segmentById.get(constraint.segmentId);
            if (!segment) throw new Error(`Drawing constraint references missing segment: ${constraint.segmentId}`);
            const semanticKey = `${constraint.type}:${constraint.segmentId}`;
            if (semanticConstraints.has(semanticKey)) {
                throw new Error(`Duplicate drawing constraint: ${semanticKey}`);
            }
            semanticConstraints.add(semanticKey);
            if (constraint.type === CONSTRAINT_TYPES.FIXED_LENGTH) {
                if (!nodeIds.has(constraint.anchorNodeId)) {
                    throw new Error(`Drawing constraint references missing anchor node: ${constraint.anchorNodeId}`);
                }
                if (![segment.startNodeId, segment.endNodeId].includes(constraint.anchorNodeId)) {
                    throw new Error("Fixed-length constraint anchor must be one of the segment endpoints");
                }
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
            constraints,
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
            constraints: options.constraints || [],
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

    function constraintById(document, id) {
        return (document.constraints || []).find(constraint => constraint.id === String(id)) || null;
    }

    function ensureUniqueId(document, id) {
        const value = String(id || "");
        if (!value) throw new Error("Drawing entity id is required");
        if (
            nodeById(document, value)
            || segmentById(document, value)
            || pathById(document, value)
            || dimensionById(document, value)
            || constraintById(document, value)
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

    function updateNodePositions(document, positions) {
        const getPosition = nodeId => positions instanceof Map
            ? positions.get(nodeId)
            : positions && positions[nodeId];
        let changed = false;
        const nodes = document.nodes.map(node => {
            const next = getPosition(node.id);
            if (!next) return node;
            const xMm = geometry.roundMm(next.xMm);
            const yMm = geometry.roundMm(next.yMm);
            if (node.xMm === xMm && node.yMm === yMm) return node;
            changed = true;
            return { ...node, xMm, yMm };
        });
        return changed ? freezeDocument({ ...document, nodes }) : document;
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

    function addConstraint(document, constraint) {
        const id = ensureUniqueId(document, constraint && constraint.id);
        return freezeDocument({
            ...document,
            constraints: [...document.constraints, { ...constraint, id }],
        });
    }

    function updateConstraint(document, constraintId, patch = {}) {
        const id = String(constraintId || "");
        const current = constraintById(document, id);
        if (!current) throw new Error(`Drawing constraint not found: ${id}`);
        return freezeDocument({
            ...document,
            constraints: document.constraints.map(constraint => constraint.id === id
                ? { ...constraint, ...patch, id }
                : constraint),
        });
    }

    function removeConstraint(document, constraintId) {
        const id = String(constraintId || "");
        if (!constraintById(document, id)) return document;
        return freezeDocument({
            ...document,
            constraints: document.constraints.filter(constraint => constraint.id !== id),
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
        CONSTRAINT_TYPES,
        KNOWN_CONSTRAINT_TYPES,
        create,
        nodeById,
        segmentById,
        pathById,
        dimensionById,
        constraintById,
        pathEndNodeId,
        addNode,
        moveNode,
        updateNodePositions,
        addPath,
        addLineToPath,
        closePath,
        addDimension,
        removeDimension,
        addConstraint,
        updateConstraint,
        removeConstraint,
        serialize,
    });
})();