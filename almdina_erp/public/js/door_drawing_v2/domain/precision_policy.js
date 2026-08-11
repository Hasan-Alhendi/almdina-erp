(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV2 = window.AlmdinaDoorDrawingV2 || Object.create(null);

    const UNITS = "mm";
    const DISPLAY_DECIMALS = 1;
    const SERIALIZATION_DECIMALS = 3;
    const EPSILON_MM = 0.001;

    function toNumber(value) {
        const normalized = typeof value === "string" ? value.trim().replace(",", ".") : value;
        const numeric = Number(normalized);
        return Number.isFinite(numeric) ? numeric : NaN;
    }

    function assertFinite(value, label = "value") {
        const numeric = toNumber(value);
        if (!Number.isFinite(numeric)) throw new TypeError(`${label} must be a finite number`);
        return numeric;
    }

    function round(value, decimals = SERIALIZATION_DECIMALS) {
        const numeric = assertFinite(value);
        const places = Math.max(0, Math.min(9, Math.trunc(Number(decimals) || 0)));
        const factor = 10 ** places;
        return Math.round((numeric + Number.EPSILON) * factor) / factor;
    }

    function serialized(value) {
        return round(value, SERIALIZATION_DECIMALS);
    }

    function displayed(value) {
        return round(value, DISPLAY_DECIMALS);
    }

    function nearlyEqual(first, second, tolerance = EPSILON_MM) {
        return Math.abs(assertFinite(first) - assertFinite(second)) <= Math.max(0, assertFinite(tolerance));
    }

    function point(value, label = "point") {
        if (!value || typeof value !== "object") throw new TypeError(`${label} must be an object`);
        return Object.freeze({
            x: serialized(assertFinite(value.x, `${label}.x`)),
            y: serialized(assertFinite(value.y, `${label}.y`)),
        });
    }

    function cmToMm(value) {
        return serialized(assertFinite(value) * 10);
    }

    function mmToCm(value) {
        return serialized(assertFinite(value) / 10);
    }

    root.Precision = Object.freeze({
        UNITS,
        DISPLAY_DECIMALS,
        SERIALIZATION_DECIMALS,
        EPSILON_MM,
        toNumber,
        assertFinite,
        round,
        serialized,
        displayed,
        nearlyEqual,
        point,
        cmToMm,
        mmToCm,
    });
})();
