(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);
    const documentModel = root.DocumentModel;
    const dimensionDomain = root.DimensionDomain;
    const constraintInference = root.ConstraintInference;
    const constraintSolver = root.ConstraintSolver;
    if (!documentModel || !dimensionDomain || !constraintInference || !constraintSolver) {
        throw new Error("Drawing V4 dimension and constraint services must load before driving dimension commands");
    }

    function drive(document, dimensionId, valueMm, options = {}) {
        const before = document;
        const measurement = dimensionDomain.resolve(document, dimensionId);
        if (!measurement) {
            return Object.freeze({ ok: false, code: "dimension-not-found", document: before, dimensionId: String(dimensionId || "") });
        }

        const inferred = constraintInference.inferPathOrthogonality(document, measurement.segmentId, options);
        const solved = constraintSolver.driveSegmentLength(inferred.document, measurement.segmentId, valueMm, options);
        if (!solved.ok) {
            return Object.freeze({
                ...solved,
                document: before,
                dimensionId: measurement.id,
                inferredConstraintIds: Object.freeze([]),
            });
        }

        return Object.freeze({
            ...solved,
            dimensionId: measurement.id,
            measurement: dimensionDomain.resolve(solved.document, measurement.id),
            inferredConstraintIds: inferred.createdConstraintIds,
        });
    }

    function release(document, dimensionId) {
        const measurement = dimensionDomain.resolve(document, dimensionId);
        if (!measurement) {
            return Object.freeze({ ok: false, code: "dimension-not-found", document, dimensionId: String(dimensionId || "") });
        }
        if (!measurement.constraintId) {
            return Object.freeze({ ok: true, changed: false, document, dimensionId: measurement.id });
        }
        return Object.freeze({
            ok: true,
            changed: true,
            document: documentModel.removeConstraint(document, measurement.constraintId),
            dimensionId: measurement.id,
            constraintId: measurement.constraintId,
        });
    }

    root.DrivingDimensionCommands = Object.freeze({ drive, release });
})();
