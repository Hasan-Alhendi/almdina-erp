(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const Domain = root.ShapePreservingStrokeDomain;
    if (!Domain) throw new Error("Door Drawing V3 shape-preserving stroke domain must load before adaptive cleaner");

    const PROFILES = Object.freeze({
        mouse: Object.freeze({
            smoothingPasses: 2,
            smoothingRadius: 2,
            smoothingStrength: 0.72,
            maxCurveDisplacementMm: 0.8,
            simplifyToleranceMm: 0.22,
            cornerAngleDeg: 32,
            minimumCornerArmMm: 3.5,
            minimumStraightLengthMm: 14,
            straightRatio: 1.055,
            straightMinimumDeviationMm: 0.55,
            straightDeviationBaseMm: 0.35,
            straightDeviationSlope: 0.004,
            straightMaximumDeviationMm: 1.8,
            overallMaximumDeviationMm: 2.0,
        }),
        pen: Object.freeze({
            smoothingPasses: 1,
            smoothingRadius: 2,
            smoothingStrength: 0.52,
            maxCurveDisplacementMm: 0.55,
            simplifyToleranceMm: 0.16,
            cornerAngleDeg: 30,
            minimumCornerArmMm: 3,
            minimumStraightLengthMm: 11,
            straightRatio: 1.045,
            straightMinimumDeviationMm: 0.42,
            straightDeviationBaseMm: 0.26,
            straightDeviationSlope: 0.0032,
            straightMaximumDeviationMm: 1.25,
            overallMaximumDeviationMm: 1.4,
        }),
        touch: Object.freeze({
            smoothingPasses: 2,
            smoothingRadius: 2,
            smoothingStrength: 0.76,
            maxCurveDisplacementMm: 1.0,
            simplifyToleranceMm: 0.28,
            cornerAngleDeg: 34,
            minimumCornerArmMm: 4.2,
            minimumStraightLengthMm: 18,
            straightRatio: 1.065,
            straightMinimumDeviationMm: 0.7,
            straightDeviationBaseMm: 0.45,
            straightDeviationSlope: 0.0045,
            straightMaximumDeviationMm: 2.2,
            overallMaximumDeviationMm: 2.4,
        }),
    });

    function profile(pointerType) {
        const key = String(pointerType || "mouse").toLowerCase();
        return PROFILES[key] || PROFILES.mouse;
    }

    function optionsFor(pointerType, overrides = {}) {
        return Object.freeze({ ...profile(pointerType), ...(overrides || {}) });
    }

    function clean(points, pointerType = "mouse", overrides = {}) {
        return Domain.cleanStroke(points, optionsFor(pointerType, overrides));
    }

    root.AdaptiveStrokeCleaner = Object.freeze({
        PROFILES,
        profile,
        optionsFor,
        clean,
    });
})();
