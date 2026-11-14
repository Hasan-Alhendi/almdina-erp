(() => {
    "use strict";

    // Door-local millimetres: origin is the blank's top-left, +X right, +Y down.
    // Board translation, editor rotation, and flip are applied only for display.
    // Source nesting rotation is the one 90° clockwise bake already in the
    // placement rectangle; it is not applied again to DXF outlines.

    const SNAP_PX = 8;
    const ANGLE_STEP_DEG = 15;

    function num(value) {
        const number = Number(value);
        return Number.isFinite(number) ? number : 0;
    }

    function quantizeMm(value) {
        const number = Number(value);
        if (!Number.isFinite(number) || Math.abs(number) > 100000) return null;
        const quantized = Math.round((number + Number.EPSILON) * 1000) / 1000;
        return quantized === 0 ? 0 : quantized;
    }

    function cmToMm(value) {
        const number = Number(value);
        if (!Number.isFinite(number) || number <= 0) return null;
        return quantizeMm(number * 10);
    }

    function rotate(point, pivot, angleDeg) {
        const dx = num(point.x) - num(pivot.x);
        const dy = num(point.y) - num(pivot.y);
        const rad = (num(angleDeg) * Math.PI) / 180;
        const cos = Math.cos(rad);
        const sin = Math.sin(rad);
        return {
            x: num(pivot.x) + dx * cos + dy * sin,
            y: num(pivot.y) - dx * sin + dy * cos,
        };
    }

    function reflect(point, pivot, flipH, flipV) {
        return {
            x: flipH ? num(pivot.x) * 2 - num(point.x) : num(point.x),
            y: flipV ? num(pivot.y) * 2 - num(point.y) : num(point.y),
        };
    }

    function pieceFrame(piece, boards, blank) {
        const placement = (piece && piece.placement_cm) || {};
        const entryPivot = (piece && piece.entry_pivot_mm) || (piece && piece.pivot_mm) || { x: 0, y: 0 };
        const livePivot = (piece && piece.pivot_mm) || entryPivot;
        const sheetNo = piece && piece.sheet_no;
        const board = (boards && sheetNo != null && boards[String(sheetNo)]) || {};
        return {
            entryOrigin: {
                x: num(placement.x) * 10,
                y: num(placement.y) * 10,
            },
            entryPivot: { x: num(entryPivot.x), y: num(entryPivot.y) },
            livePivot: { x: num(livePivot.x), y: num(livePivot.y) },
            translation: {
                x: num(livePivot.x) - num(entryPivot.x),
                y: num(livePivot.y) - num(entryPivot.y),
            },
            rotationDeg: num(piece && piece.rotation_deg),
            flipH: Boolean(piece && piece.flip_h),
            flipV: Boolean(piece && piece.flip_v),
            sourceRotated: Boolean(
                (piece && piece.source_rotated_dims)
                || placement.rotated
            ),
            blankWidthMm: num(blank && blank.widthMm),
            boardOrigin: {
                x: num(board.origin_x_mm) + num(board.trim_x_mm),
                y: num(board.origin_y_mm) + num(board.trim_y_mm),
            },
        };
    }

    function doorToEntry(frame, xMm, yMm) {
        const origin = frame.entryOrigin;
        if (frame.sourceRotated) {
            return {
                x: origin.x + num(yMm),
                y: origin.y + frame.blankWidthMm - num(xMm),
            };
        }
        return { x: origin.x + num(xMm), y: origin.y + num(yMm) };
    }

    function entryToDoor(frame, point) {
        const origin = frame.entryOrigin;
        if (frame.sourceRotated) {
            return {
                x: origin.y + frame.blankWidthMm - num(point.y),
                y: num(point.x) - origin.x,
            };
        }
        return {
            x: num(point.x) - origin.x,
            y: num(point.y) - origin.y,
        };
    }

    function doorToWorld(frame, xMm, yMm) {
        const flipped = reflect(
            doorToEntry(frame, xMm, yMm),
            frame.entryPivot,
            frame.flipH,
            frame.flipV
        );
        const moved = {
            x: flipped.x + frame.translation.x,
            y: flipped.y + frame.translation.y,
        };
        const turned = rotate(moved, frame.livePivot, frame.rotationDeg);
        return {
            x: turned.x + frame.boardOrigin.x,
            y: turned.y + frame.boardOrigin.y,
        };
    }

    function worldToDoor(frame, xMm, yMm) {
        const unturned = rotate(
            { x: num(xMm) - frame.boardOrigin.x, y: num(yMm) - frame.boardOrigin.y },
            frame.livePivot,
            -frame.rotationDeg
        );
        const unmoved = {
            x: unturned.x - frame.translation.x,
            y: unturned.y - frame.translation.y,
        };
        const unflipped = reflect(unmoved, frame.entryPivot, frame.flipH, frame.flipV);
        return entryToDoor(frame, unflipped);
    }

    function lengthMm(x1, y1, x2, y2) {
        return Math.hypot(num(x2) - num(x1), num(y2) - num(y1));
    }

    function angleDeg(x1, y1, x2, y2) {
        return Math.atan2(num(y2) - num(y1), num(x2) - num(x1)) * 180 / Math.PI;
    }

    function snapAngleDeg(angle, enabled) {
        if (!enabled) return num(angle);
        let wrapped = num(angle) % 360;
        if (wrapped < 0) wrapped += 360;
        const snapped = Math.round(wrapped / ANGLE_STEP_DEG) * ANGLE_STEP_DEG;
        return snapped === 360 ? 0 : snapped;
    }

    function polarPoint(origin, distanceMm, angle) {
        const rad = num(angle) * Math.PI / 180;
        return {
            x: num(origin.x) + num(distanceMm) * Math.cos(rad),
            y: num(origin.y) + num(distanceMm) * Math.sin(rad),
        };
    }

    // One door-local endpoint for preview and commit. 0° is +X (right),
    // 90° is +Y (down). Zoom, scroll, and door rotation are not inputs.
    function segmentEnd(origin, distanceMm, angle) {
        const length = quantizeMm(distanceMm);
        const degrees = Number(angle);
        if (!origin || length == null || !(length > 0) || !Number.isFinite(degrees)) return null;
        const raw = polarPoint(origin, length, degrees);
        const x = quantizeMm(raw.x);
        const y = quantizeMm(raw.y);
        if (x == null || y == null) return null;
        return { x, y, lengthMm: length, angleDeg: degrees };
    }

    function samePoint(a, b) {
        const ax = quantizeMm(a && a.x);
        const ay = quantizeMm(a && a.y);
        const bx = quantizeMm(b && b.x);
        const by = quantizeMm(b && b.y);
        return ax != null && ay != null && ax === bx && ay === by;
    }

    function endpointSnap(paths, pointer, thresholdMm, ignore) {
        const limit = Math.max(0, num(thresholdMm));
        let best = null;
        let bestDistance = limit;
        (paths || []).forEach((path) => {
            const nodes = (path && path.nodes) || [];
            if (!nodes.length) return;
            const candidates = path.closed ? [nodes[0]] : [nodes[0], nodes[nodes.length - 1]];
            candidates.forEach((node) => {
                if (!node) return;
                if (ignore && ignore.nodeId === node.id && ignore.pathId === path.id) return;
                const point = { x: num(node.x_mm), y: num(node.y_mm) };
                const distance = lengthMm(pointer.x, pointer.y, point.x, point.y);
                if (distance <= bestDistance) {
                    bestDistance = distance;
                    best = {
                        pathId: path.id,
                        nodeId: node.id,
                        x: point.x,
                        y: point.y,
                        start: node.id === nodes[0].id,
                    };
                }
            });
        });
        return best;
    }

    function thresholdMm(scale) {
        const pixelsPerMm = Math.max(0.0001, num(scale) || 1);
        return SNAP_PX / pixelsPerMm;
    }

    function screenToWorld(point, camera) {
        const scale = num(camera && camera.scale) || 1;
        return {
            x: (num(point.x) + num(camera.scrollX) - num(camera.padX)) / scale + num(camera.minX),
            y: (num(point.y) + num(camera.scrollY) - num(camera.padY)) / scale + num(camera.minY),
        };
    }

    function worldToScreen(point, camera) {
        const scale = num(camera && camera.scale) || 1;
        return {
            x: (num(point.x) - num(camera.minX)) * scale + num(camera.padX) - num(camera.scrollX),
            y: (num(point.y) - num(camera.minY)) * scale + num(camera.padY) - num(camera.scrollY),
        };
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.DrawingSpace = Object.freeze({
        SNAP_PX,
        ANGLE_STEP_DEG,
        quantizeMm,
        cmToMm,
        pieceFrame,
        doorToWorld,
        worldToDoor,
        lengthMm,
        angleDeg,
        snapAngleDeg,
        polarPoint,
        segmentEnd,
        samePoint,
        endpointSnap,
        thresholdMm,
        screenToWorld,
        worldToScreen,
        rotate,
    });
})();
