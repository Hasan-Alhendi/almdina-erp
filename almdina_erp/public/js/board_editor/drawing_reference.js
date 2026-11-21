(() => {
    "use strict";

    const MAX_MM = 100000;

    function quantize(value) {
        const number = Number(value);
        if (!Number.isFinite(number) || Math.abs(number) > MAX_MM) return null;
        const quantized = Math.round((number + Number.EPSILON) * 1000) / 1000;
        return quantized === 0 ? 0 : quantized;
    }

    function radians(value) {
        return Number(value || 0) * Math.PI / 180;
    }

    function rotateLocal(localX, localY, rotationDeg) {
        const angle = radians(rotationDeg);
        const cosine = Math.cos(angle);
        const sine = Math.sin(angle);
        return {
            x: (localX * cosine) - (localY * sine),
            y: (localX * sine) + (localY * cosine),
        };
    }

    function doorPoint(reference, localX, localY) {
        const rotated = rotateLocal(localX, localY, reference.rotation_deg);
        return {
            x: Number(reference.x_mm) + rotated.x,
            y: Number(reference.y_mm) + rotated.y,
        };
    }

    function toLocal(reference, point) {
        const angle = radians(reference.rotation_deg);
        const cosine = Math.cos(angle);
        const sine = Math.sin(angle);
        const dx = Number(point.x) - Number(reference.x_mm);
        const dy = Number(point.y) - Number(reference.y_mm);
        return {
            x: (dx * cosine) + (dy * sine),
            y: (-dx * sine) + (dy * cosine),
        };
    }

    function inside(reference, local) {
        return local.x >= -0.05
            && local.y >= -0.05
            && local.x <= Number(reference.width_mm) + 0.05
            && local.y <= Number(reference.height_mm) + 0.05;
    }

    function initialPlacement(blankWidth, blankLength, pixelWidth, pixelHeight) {
        const aspect = Number(pixelWidth) / Number(pixelHeight);
        let width = Number(blankWidth) * 0.8;
        let height = width / aspect;
        if (height > Number(blankLength) * 0.8) {
            height = Number(blankLength) * 0.8;
            width = height * aspect;
        }
        return {
            x_mm: quantize((Number(blankWidth) - width) / 2),
            y_mm: quantize((Number(blankLength) - height) / 2),
            width_mm: quantize(width),
            height_mm: quantize(height),
            rotation_deg: 0,
            opacity: 0.5,
        };
    }

    function applyCalibration(reference, start, end, knownDistance) {
        const known = Number(knownDistance);
        if (!Number.isFinite(known) || known <= 0 || !start || !end) return { ok: false, code: "invalid_calibration" };
        if (start.x === end.x && start.y === end.y) return { ok: false, code: "invalid_calibration" };
        const startLocal = toLocal(reference, start);
        const endLocal = toLocal(reference, end);
        if (!inside(reference, startLocal) || !inside(reference, endLocal)) return { ok: false, code: "calibration_outside" };
        const current = Math.hypot(end.x - start.x, end.y - start.y);
        if (!(current > 0.05)) return { ok: false, code: "invalid_calibration" };
        const factor = known / current;
        const width = quantize(Number(reference.width_mm) * factor);
        const height = quantize(Number(reference.height_mm) * factor);
        if (width == null || height == null || !(width > 0) || !(height > 0)) return { ok: false, code: "unbounded" };
        const rotated = rotateLocal(startLocal.x * factor, startLocal.y * factor, reference.rotation_deg);
        const originX = quantize(start.x - rotated.x);
        const originY = quantize(start.y - rotated.y);
        if (originX == null || originY == null) return { ok: false, code: "unbounded" };
        const scaledEnd = doorPoint({
            x_mm: originX,
            y_mm: originY,
            rotation_deg: reference.rotation_deg,
        }, endLocal.x * factor, endLocal.y * factor);
        return {
            ok: true,
            x_mm: originX,
            y_mm: originY,
            width_mm: width,
            height_mm: height,
            rotation_deg: quantize(reference.rotation_deg) || 0,
            calibration: {
                start_mm: { x_mm: quantize(start.x), y_mm: quantize(start.y) },
                end_mm: { x_mm: quantize(scaledEnd.x), y_mm: quantize(scaledEnd.y) },
                known_distance_mm: quantize(known),
            },
        };
    }

    function resizeReference(reference, corner, factorX, factorY) {
        const width = quantize(Number(reference.width_mm) * Math.abs(factorX));
        const height = quantize(Number(reference.height_mm) * Math.abs(factorY));
        if (width == null || height == null || !(width > 0) || !(height > 0)) return null;
        const anchor = { nw: "se", ne: "sw", sw: "ne", se: "nw" }[corner];
        const fixed = {
            nw: { x: 0, y: 0 },
            ne: { x: Number(reference.width_mm), y: 0 },
            sw: { x: 0, y: Number(reference.height_mm) },
            se: { x: Number(reference.width_mm), y: Number(reference.height_mm) },
        }[anchor];
        const nextFixed = {
            nw: { x: 0, y: 0 },
            ne: { x: width, y: 0 },
            sw: { x: 0, y: height },
            se: { x: width, y: height },
        }[anchor];
        if (!fixed || !nextFixed) return null;
        const fixedDoor = doorPoint(reference, fixed.x, fixed.y);
        const rotated = rotateLocal(nextFixed.x, nextFixed.y, reference.rotation_deg);
        const originX = quantize(fixedDoor.x - rotated.x);
        const originY = quantize(fixedDoor.y - rotated.y);
        if (originX == null || originY == null) return null;
        return { x_mm: originX, y_mm: originY, width_mm: width, height_mm: height };
    }

    function rotateAroundCenter(reference, rotationDeg) {
        const rotation = quantize(rotationDeg);
        if (rotation == null) return null;
        const center = doorPoint(reference, Number(reference.width_mm) / 2, Number(reference.height_mm) / 2);
        const rotated = rotateLocal(Number(reference.width_mm) / 2, Number(reference.height_mm) / 2, rotation);
        const originX = quantize(center.x - rotated.x);
        const originY = quantize(center.y - rotated.y);
        if (originX == null || originY == null) return null;
        return { x_mm: originX, y_mm: originY, rotation_deg: rotation };
    }

    function contains(reference, point) {
        return inside(reference, toLocal(reference, point));
    }

    function project(reference, doorToWorld) {
        const origin = doorPoint(reference, 0, 0);
        const xAxis = doorPoint(reference, Number(reference.width_mm), 0);
        const yAxis = doorPoint(reference, 0, Number(reference.height_mm));
        const map = (point) => (doorToWorld ? doorToWorld(point.x, point.y) : point);
        return { origin: map(origin), xAxis: map(xAxis), yAxis: map(yAxis) };
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.DrawingReference = Object.freeze({
        quantize,
        initialPlacement,
        applyCalibration,
        resizeReference,
        rotateAroundCenter,
        contains,
        toLocal,
        doorPoint,
        project,
    });
})();
