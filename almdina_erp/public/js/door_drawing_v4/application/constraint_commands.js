(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);
    const geometry = root.Geometry;
    const documentModel = root.DocumentModel;
    const geometryCommands = root.GeometryCommands;
    if (!geometry || !documentModel || !geometryCommands) {
        throw new Error("Drawing V4 constraint dependencies must load before constraint commands");
    }

    function existing(document, segmentId, type) {
        const id = String(segmentId || "");
        return (document.constraints || []).find(constraint => (
            constraint.segmentId === id && constraint.type === type
        )) || null;
    }

    function ensureRelation(document, segmentId, type, options = {}) {
        const id = String(segmentId || "");
        if (!documentModel.segmentById(document, id)) throw new Error(`Drawing segment not found: ${id}`);
        if (![documentModel.CONSTRAINT_TYPES.HORIZONTAL, documentModel.CONSTRAINT_TYPES.VERTICAL].includes(type)) {
            throw new Error(`Unsupported geometric relation constraint: ${type}`);
        }
        const current = existing(document, id, type);
        if (current) return Object.freeze({ document, constraintId: current.id, created: false });
        const idFactory = options.idFactory || geometryCommands.createIdFactory("constraint");
        const constraintId = String(options.id || idFactory("constraint"));
        return Object.freeze({
            document: documentModel.addConstraint(document, { id: constraintId, type, segmentId: id }),
            constraintId,
            created: true,
        });
    }

    function ensureHorizontal(document, segmentId, options = {}) {
        return ensureRelation(document, segmentId, documentModel.CONSTRAINT_TYPES.HORIZONTAL, options);
    }

    function ensureVertical(document, segmentId, options = {}) {
        return ensureRelation(document, segmentId, documentModel.CONSTRAINT_TYPES.VERTICAL, options);
    }

    function ensureFixedLength(document, segmentId, valueMm, options = {}) {
        const id = String(segmentId || "");
        const segment = documentModel.segmentById(document, id);
        if (!segment) throw new Error(`Drawing segment not found: ${id}`);
        const value = geometry.roundMm(valueMm);
        if (value <= geometry.EPSILON_MM) throw new Error("Fixed length must be greater than zero");

        const current = existing(document, id, documentModel.CONSTRAINT_TYPES.FIXED_LENGTH);
        const anchorNodeId = String(
            options.anchorNodeId !== undefined && options.anchorNodeId !== null
                ? options.anchorNodeId
                : (current && current.anchorNodeId) || segment.startNodeId
        );
        if (![segment.startNodeId, segment.endNodeId].includes(anchorNodeId)) {
            throw new Error("Fixed-length anchor must be a segment endpoint");
        }

        if (current) {
            const unchanged = current.valueMm === value && current.anchorNodeId === anchorNodeId;
            return Object.freeze({
                document: unchanged ? document : documentModel.updateConstraint(document, current.id, {
                    valueMm: value,
                    anchorNodeId,
                }),
                constraintId: current.id,
                created: false,
                changed: !unchanged,
            });
        }

        const idFactory = options.idFactory || geometryCommands.createIdFactory("constraint");
        const constraintId = String(options.id || idFactory("constraint"));
        return Object.freeze({
            document: documentModel.addConstraint(document, {
                id: constraintId,
                type: documentModel.CONSTRAINT_TYPES.FIXED_LENGTH,
                segmentId: id,
                valueMm: value,
                anchorNodeId,
            }),
            constraintId,
            created: true,
            changed: true,
        });
    }

    function remove(document, constraintId) {
        const id = String(constraintId || "");
        if (!documentModel.constraintById(document, id)) {
            return Object.freeze({ document, constraintId: id, removed: false });
        }
        return Object.freeze({
            document: documentModel.removeConstraint(document, id),
            constraintId: id,
            removed: true,
        });
    }

    root.ConstraintCommands = Object.freeze({
        existing,
        ensureHorizontal,
        ensureVertical,
        ensureFixedLength,
        remove,
    });
})();
