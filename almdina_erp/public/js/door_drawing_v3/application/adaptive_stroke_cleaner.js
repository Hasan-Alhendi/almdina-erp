(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const Domain = root.ShapePreservingStrokeDomain;
    if (!Domain) throw new Error("Door Drawing V3 shape-preserving stroke domain must load before adaptive cleaner");

    const PROFILES = Object.freeze({
        mouse: Object.freeze({
            trendPasses: 2,
            trendRadius: 4,
            smoothingPasses: 3,
            smoothingRadius: 3,
            smoothingStrength: 0.86,
            maxCurveDisplacementMm: 3.0,
            simplifyToleranceMm: 0.5,
            cornerAngleDeg: 48,
            cornerWindow: 4,
            cornerProtectionRadius: 1,
            minimumCornerArmMm: 5.5,
            minimumStraightSamples: 5,
            minimumStraightLengthMm: 12,
            straightRatio: 1.15,
            straightMinimumDeviationMm: 1.25,
            straightDeviationBaseMm: 0.9,
            straightDeviationSlope: 0.02,
            straightMaximumDeviationMm: 7.0,
            straightRmsFactor: 0.82,
            curveBiasThreshold: 0.68,
            curveEvidenceMinimumMm: 1.1,
            overallMaximumDeviationMm: 8.0,
        }),
        pen: Object.freeze({
            trendPasses: 2,
            trendRadius: 3,
            smoothingPasses: 2,
            smoothingRadius: 2,
            smoothingStrength: 0.72,
            maxCurveDisplacementMm: 2.2,
            simplifyToleranceMm: 0.38,
            cornerAngleDeg: 46,
            cornerWindow: 3,
            cornerProtectionRadius: 1,
            minimumCornerArmMm: 4.5,
            minimumStraightSamples: 5,
            minimumStraightLengthMm: 10,
            straightRatio: 1.13,
            straightMinimumDeviationMm: 1.0,
            straightDeviationBaseMm: 0.7,
            straightDeviationSlope: 0.017,
            straightMaximumDeviationMm: 5.2,
            straightRmsFactor: 0.78,
            curveBiasThreshold: 0.7,
            curveEvidenceMinimumMm: 0.9,
            overallMaximumDeviationMm: 6.0,
        }),
        touch: Object.freeze({
            trendPasses: 3,
            trendRadius: 5,
            smoothingPasses: 4,
            smoothingRadius: 4,
            smoothingStrength: 0.9,
            maxCurveDisplacementMm: 4.2,
            simplifyToleranceMm: 0.7,
            cornerAngleDeg: 50,
            cornerWindow: 5,
            cornerProtectionRadius: 1,
            minimumCornerArmMm: 7,
            minimumStraightSamples: 5,
            minimumStraightLengthMm: 16,
            straightRatio: 1.18,
            straightMinimumDeviationMm: 1.8,
            straightDeviationBaseMm: 1.2,
            straightDeviationSlope: 0.024,
            straightMaximumDeviationMm: 9.0,
            straightRmsFactor: 0.85,
            curveBiasThreshold: 0.66,
            curveEvidenceMinimumMm: 1.5,
            overallMaximumDeviationMm: 10.0,
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
