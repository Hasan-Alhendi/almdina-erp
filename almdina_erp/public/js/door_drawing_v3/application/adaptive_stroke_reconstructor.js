(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const Domain = root.SmartStrokeReconstructionDomain;
    if (!Domain) throw new Error("Door Drawing V3 smart stroke reconstruction domain must load first");

    const PROFILES = Object.freeze({
        mouse: Object.freeze({
            resampleSpacingMm: 3.0,
            trendPasses: 3,
            trendRadius: 3,
            cornerWindow: 3,
            cornerAngleDeg: 42,
            cornerMinGapMm: 8,
            minimumStraightLengthMm: 10,
            straightMaxDeviationRatio: 0.06,
            straightRmsRatio: 0.028,
            straightMaxHeadingDeviationDeg: 17,
            straightTotalTurnDeg: 70,
            straightLengthRatio: 1.22,
            deliberateCurveBias: 0.76,
            deliberateCurveEvidenceRatio: 0.009,
            deliberateCurveEvidenceMinMm: 1.0,
            curveAnchorToleranceRatio: 0.011,
            curveAnchorToleranceMinMm: 0.8,
            curveAnchorToleranceMaxMm: 3.2,
            curveHandleScale: 0.29,
            maximumCurveAnchors: 18,
        }),
        pen: Object.freeze({
            resampleSpacingMm: 2.2,
            trendPasses: 2,
            trendRadius: 3,
            cornerWindow: 3,
            cornerAngleDeg: 40,
            cornerMinGapMm: 6,
            minimumStraightLengthMm: 8,
            straightMaxDeviationRatio: 0.045,
            straightRmsRatio: 0.022,
            straightMaxHeadingDeviationDeg: 14,
            straightTotalTurnDeg: 60,
            straightLengthRatio: 1.16,
            deliberateCurveBias: 0.78,
            deliberateCurveEvidenceRatio: 0.008,
            deliberateCurveEvidenceMinMm: 0.8,
            curveAnchorToleranceRatio: 0.009,
            curveAnchorToleranceMinMm: 0.65,
            curveAnchorToleranceMaxMm: 2.5,
            curveHandleScale: 0.29,
            maximumCurveAnchors: 20,
        }),
        touch: Object.freeze({
            resampleSpacingMm: 4.0,
            trendPasses: 4,
            trendRadius: 4,
            cornerWindow: 4,
            cornerAngleDeg: 45,
            cornerMinGapMm: 10,
            minimumStraightLengthMm: 12,
            straightMaxDeviationRatio: 0.07,
            straightRmsRatio: 0.032,
            straightMaxHeadingDeviationDeg: 19,
            straightTotalTurnDeg: 80,
            straightLengthRatio: 1.26,
            deliberateCurveBias: 0.74,
            deliberateCurveEvidenceRatio: 0.012,
            deliberateCurveEvidenceMinMm: 1.5,
            curveAnchorToleranceRatio: 0.014,
            curveAnchorToleranceMinMm: 1.1,
            curveAnchorToleranceMaxMm: 4.2,
            curveHandleScale: 0.28,
            maximumCurveAnchors: 16,
        }),
    });

    function profile(pointerType) {
        const key = String(pointerType || "mouse").toLowerCase();
        return PROFILES[key] || PROFILES.mouse;
    }

    function optionsFor(pointerType, overrides = {}) {
        return Object.freeze({ ...profile(pointerType), ...(overrides || {}) });
    }

    function wholeStrokeStraight(points, options) {
        const sampled = Domain.resampleUniform(points, options);
        if (sampled.length < 2) return null;
        // A whole-stroke straight decision gets a broader trend filter than local
        // segmentation. This removes alternating hand tremor from heading/turn
        // measurements without weakening the deliberate-curve guard that protects
        // bows, arches and other intended curves from being flattened.
        const evidence = Domain.straightEvidence(sampled, {
            ...options,
            trendPasses: Math.max(4, Number(options.trendPasses) || 0),
            trendRadius: Math.max(4, Number(options.trendRadius) || 0),
            straightMaxHeadingDeviationDeg: Math.max(26, Number(options.straightMaxHeadingDeviationDeg) || 0),
            straightTotalTurnDeg: Math.max(90, Number(options.straightTotalTurnDeg) || 0),
            straightLengthRatio: Math.max(1.28, Number(options.straightLengthRatio) || 1),
        });
        if (!evidence.eligible) return null;
        const first = sampled[0];
        const last = sampled[sampled.length - 1];
        return Object.freeze({
            points: Object.freeze([first, last]),
            nodes: Object.freeze([
                Object.freeze({ type: "corner", in: null, out: null }),
                Object.freeze({ type: "corner", in: null, out: null }),
            ]),
            changed: sampled.length !== 2,
            cornerCount: 0,
            straightSegmentCount: 1,
            curveSegmentCount: 0,
            spans: Object.freeze([
                Object.freeze({ startIndex: 0, endIndex: sampled.length - 1, kind: "line", evidence }),
            ]),
        });
    }

    function reconstruct(points, pointerType = "mouse", overrides = {}) {
        const options = optionsFor(pointerType, overrides);
        return wholeStrokeStraight(points, options) || Domain.reconstruct(points, options);
    }

    root.AdaptiveStrokeReconstructor = Object.freeze({
        PROFILES,
        profile,
        optionsFor,
        wholeStrokeStraight,
        reconstruct,
    });
})();
