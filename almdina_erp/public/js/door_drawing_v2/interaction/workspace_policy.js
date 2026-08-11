(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV2 = window.AlmdinaDoorDrawingV2 || Object.create(null);
    const precision = root.Precision;
    if (!precision) throw new Error("Door Drawing V2 Precision must load before WorkspacePolicy");

    const MODE = "free";
    const INPUT_UNITS = "mm";
    const LEGACY_STORAGE_UNITS = "cm";
    const LEGACY_CM_PER_MM = 0.1;

    function legacyCmFromInputMm(value) {
        return precision.serialized(precision.assertFinite(value, "lengthMm") * LEGACY_CM_PER_MM);
    }

    function inputMmFromLegacyCm(value) {
        return precision.serialized(precision.assertFinite(value, "lengthCm") / LEGACY_CM_PER_MM);
    }

    function isFreeTransform(transform) {
        return Boolean(transform && transform.freeWorkspace === true);
    }

    function resolveFreeWorkspace(options = {}) {
        if (options.freeWorkspace !== undefined) return Boolean(options.freeWorkspace);
        return true;
    }

    root.WorkspacePolicy = Object.freeze({
        MODE,
        INPUT_UNITS,
        LEGACY_STORAGE_UNITS,
        isFree: true,
        legacyCmFromInputMm,
        inputMmFromLegacyCm,
        isFreeTransform,
        resolveFreeWorkspace,
    });
})();
