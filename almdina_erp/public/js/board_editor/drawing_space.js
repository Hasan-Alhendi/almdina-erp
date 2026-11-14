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

    const BEZIER_KAPPA = 0.5522847498307936;
    const SHAPE_CORNERS = Object.freeze(["top_left", "top_right", "bottom_left", "bottom_right"]);
    const SHAPE_ORDER = Object.freeze([
        "rectangle",
        "circle",
        "ellipse",
        "arc",
        "polygon",
        "trapezoid",
        "l_shape",
        "clipped_corner",
        "bezier",
    ]);
    const SHAPE_PARAM_KEYS = Object.freeze({
        rectangle: ["x_mm", "y_mm", "width_mm", "height_mm", "rotation_deg"],
        circle: ["cx_mm", "cy_mm", "radius_mm"],
        ellipse: ["cx_mm", "cy_mm", "rx_mm", "ry_mm", "rotation_deg"],
        arc: ["cx_mm", "cy_mm", "radius_mm", "start_angle_deg", "sweep_angle_deg"],
        polygon: ["cx_mm", "cy_mm", "radius_mm", "sides", "rotation_deg"],
        trapezoid: ["x_mm", "y_mm", "bottom_width_mm", "top_width_mm", "height_mm"],
        l_shape: ["x_mm", "y_mm", "width_mm", "height_mm", "notch_width_mm", "notch_height_mm"],
        clipped_corner: ["x_mm", "y_mm", "width_mm", "height_mm", "cut_width_mm", "cut_height_mm", "corner"],
    });
    const POSITIVE_SHAPE_KEYS = new Set([
        "width_mm", "height_mm", "radius_mm", "rx_mm", "ry_mm",
        "bottom_width_mm", "top_width_mm", "notch_width_mm", "notch_height_mm",
        "cut_width_mm", "cut_height_mm",
    ]);

    function shapeTools() {
        return SHAPE_ORDER.map((id) => ({
            id,
            labelKey: {
                rectangle: "Rectangle",
                circle: "Circle",
                ellipse: "Ellipse",
                arc: "Arc",
                polygon: "Polygon",
                trapezoid: "Trapezoid",
                l_shape: "L shape",
                clipped_corner: "Clipped corner",
                bezier: "Bézier curve",
            }[id],
        }));
    }

    function shapeFieldDefs(kind) {
        const labels = {
            x_mm: "X (mm)",
            y_mm: "Y (mm)",
            cx_mm: "X (mm)",
            cy_mm: "Y (mm)",
            width_mm: kind === "l_shape" ? "Outer width (mm)" : "Width (mm)",
            height_mm: kind === "l_shape" ? "Outer height (mm)" : "Height (mm)",
            radius_mm: "Radius (mm)",
            rx_mm: "Radius X (mm)",
            ry_mm: "Radius Y (mm)",
            rotation_deg: "Angle (°)",
            start_angle_deg: "Start angle (°)",
            sweep_angle_deg: "Sweep (°)",
            sides: "Sides",
            bottom_width_mm: "Bottom width (mm)",
            top_width_mm: "Top width (mm)",
            notch_width_mm: "Cutout width (mm)",
            notch_height_mm: "Cutout height (mm)",
            cut_width_mm: "Cut width (mm)",
            cut_height_mm: "Cut height (mm)",
            corner: "Corner",
            end_x_mm: "End X (mm)",
            end_y_mm: "End Y (mm)",
        };
        if (kind === "bezier") {
            return ["end_x_mm", "end_y_mm"].map((key) => ({ key, labelKey: labels[key] }));
        }
        return (SHAPE_PARAM_KEYS[kind] || []).map((key) => ({ key, labelKey: labels[key] || key }));
    }

    function quantizeDeg(value) {
        const number = Number(value);
        if (!Number.isFinite(number) || Math.abs(number) > 3600) return null;
        return quantizeMm(number);
    }

    function shapeFailure(messageKey) {
        return { ok: false, messageKey, params: null, figure: null };
    }

    function turnedPoint(point, pivot, degrees) {
        const next = rotate(point, pivot, degrees || 0);
        const x = quantizeMm(next.x);
        const y = quantizeMm(next.y);
        if (x == null || y == null) return null;
        return { x, y };
    }

    function sampleArc(cx, cy, rx, ry, startDeg, sweepDeg, rotation, steps) {
        const count = Math.max(2, steps);
        const points = [];
        for (let index = 0; index <= count; index += 1) {
            const angle = startDeg + (sweepDeg * index) / count;
            const local = polarPoint({ x: 0, y: 0 }, 1, angle);
            const raw = { x: cx + local.x * rx, y: cy + local.y * ry };
            const point = turnedPoint(raw, { x: cx, y: cy }, rotation || 0);
            if (!point) return null;
            points.push(point);
        }
        return points;
    }

    function shapeFigure(kind, params) {
        if (kind === "rectangle") {
            const raw = [
                { x: params.x_mm, y: params.y_mm },
                { x: params.x_mm + params.width_mm, y: params.y_mm },
                { x: params.x_mm + params.width_mm, y: params.y_mm + params.height_mm },
                { x: params.x_mm, y: params.y_mm + params.height_mm },
            ];
            const points = raw.map((point) => turnedPoint(point, raw[0], params.rotation_deg));
            if (points.some((point) => !point)) return null;
            return { type: "polygon", closed: true, points, handles: points.map((point) => ({ ...point, role: "corner" })) };
        }
        if (kind === "circle") {
            const points = sampleArc(params.cx_mm, params.cy_mm, params.radius_mm, params.radius_mm, 0, 360, 0, 48);
            if (!points) return null;
            const east = turnedPoint(
                { x: params.cx_mm + params.radius_mm, y: params.cy_mm },
                { x: params.cx_mm, y: params.cy_mm },
                0
            );
            return {
                type: "circle",
                closed: true,
                points,
                handles: [
                    { x: params.cx_mm, y: params.cy_mm, role: "center" },
                    east && { ...east, role: "radius" },
                ].filter(Boolean),
            };
        }
        if (kind === "ellipse") {
            const points = sampleArc(params.cx_mm, params.cy_mm, params.rx_mm, params.ry_mm, 0, 360, params.rotation_deg, 64);
            if (!points) return null;
            return {
                type: "ellipse",
                closed: true,
                points,
                handles: [
                    { x: params.cx_mm, y: params.cy_mm, role: "center" },
                    points[0] && { ...points[0], role: "radius" },
                ].filter(Boolean),
            };
        }
        if (kind === "arc") {
            const points = sampleArc(
                params.cx_mm,
                params.cy_mm,
                params.radius_mm,
                params.radius_mm,
                params.start_angle_deg,
                params.sweep_angle_deg,
                0,
                32
            );
            if (!points) return null;
            return {
                type: "arc",
                closed: false,
                points,
                handles: [
                    { x: params.cx_mm, y: params.cy_mm, role: "center" },
                    { ...points[0], role: "start" },
                    { ...points[points.length - 1], role: "end" },
                ],
            };
        }
        if (kind === "polygon") {
            const points = [];
            for (let index = 0; index < params.sides; index += 1) {
                const angle = params.rotation_deg + (index * 360) / params.sides;
                const point = turnedPoint(polarPoint({ x: params.cx_mm, y: params.cy_mm }, params.radius_mm, angle), { x: 0, y: 0 }, 0);
                if (!point) return null;
                points.push(point);
            }
            return { type: "polygon", closed: true, points, handles: points.map((point) => ({ ...point, role: "corner" })) };
        }
        if (kind === "trapezoid") {
            const inset = (params.bottom_width_mm - params.top_width_mm) / 2;
            const raw = [
                { x: params.x_mm + inset, y: params.y_mm },
                { x: params.x_mm + inset + params.top_width_mm, y: params.y_mm },
                { x: params.x_mm + params.bottom_width_mm, y: params.y_mm + params.height_mm },
                { x: params.x_mm, y: params.y_mm + params.height_mm },
            ];
            const points = raw.map((point) => turnedPoint(point, point, 0));
            if (points.some((point) => !point)) return null;
            return { type: "polygon", closed: true, points, handles: points.map((point) => ({ ...point, role: "corner" })) };
        }
        if (kind === "l_shape") {
            const x = params.x_mm;
            const y = params.y_mm;
            const right = x + params.width_mm;
            const bottom = y + params.height_mm;
            const notchX = right - params.notch_width_mm;
            const notchY = y + params.notch_height_mm;
            const raw = [
                { x, y },
                { x: notchX, y },
                { x: notchX, y: notchY },
                { x: right, y: notchY },
                { x: right, y: bottom },
                { x, y: bottom },
            ];
            const points = raw.map((point) => turnedPoint(point, point, 0));
            if (points.some((point) => !point)) return null;
            return { type: "polygon", closed: true, points, handles: points.map((point) => ({ ...point, role: "corner" })) };
        }
        if (kind === "clipped_corner") {
            const x = params.x_mm;
            const y = params.y_mm;
            const right = x + params.width_mm;
            const bottom = y + params.height_mm;
            const cutX = params.cut_width_mm;
            const cutY = params.cut_height_mm;
            const raw = {
                top_left: [
                    { x: x + cutX, y },
                    { x: right, y },
                    { x: right, y: bottom },
                    { x, y: bottom },
                    { x, y: y + cutY },
                ],
                top_right: [
                    { x, y },
                    { x: right - cutX, y },
                    { x: right, y: y + cutY },
                    { x: right, y: bottom },
                    { x, y: bottom },
                ],
                bottom_left: [
                    { x, y },
                    { x: right, y },
                    { x: right, y: bottom },
                    { x: x + cutX, y: bottom },
                    { x, y: bottom - cutY },
                ],
                bottom_right: [
                    { x, y },
                    { x: right, y },
                    { x: right, y: bottom - cutY },
                    { x: right - cutX, y: bottom },
                    { x, y: bottom },
                ],
            }[params.corner];
            const points = (raw || []).map((point) => turnedPoint(point, point, 0));
            if (!points.length || points.some((point) => !point)) return null;
            return { type: "polygon", closed: true, points, handles: points.map((point) => ({ ...point, role: "corner" })) };
        }
        return null;
    }

    function normalizeShape(kind, raw) {
        const keys = SHAPE_PARAM_KEYS[kind];
        if (!keys || !raw || typeof raw !== "object") return shapeFailure("Enter a valid dimension.");
        const params = {};
        for (let index = 0; index < keys.length; index += 1) {
            const key = keys[index];
            if (key === "corner") {
                const corner = String(raw.corner || "");
                if (SHAPE_CORNERS.indexOf(corner) < 0) return shapeFailure("Choose a corner.");
                params.corner = corner;
                continue;
            }
            if (key === "sides") {
                const sides = Number(raw.sides);
                if (!Number.isInteger(sides) || sides < 3 || sides > 360) {
                    return shapeFailure("A polygon needs between 3 and 360 sides.");
                }
                params.sides = sides;
                continue;
            }
            const number = key.endsWith("_deg") ? quantizeDeg(raw[key]) : quantizeMm(raw[key]);
            if (number == null) {
                return shapeFailure(key.endsWith("_deg") ? "Enter a valid angle." : "Enter a valid dimension.");
            }
            if (POSITIVE_SHAPE_KEYS.has(key) && !(number > 0)) {
                return shapeFailure(key.indexOf("radius") >= 0 || key === "rx_mm" || key === "ry_mm"
                    ? "Enter a positive radius."
                    : "Enter a positive dimension.");
            }
            params[key] = number;
        }
        if (kind === "arc" && Math.abs(params.sweep_angle_deg) <= 1e-9) return shapeFailure("Enter a sweep angle.");
        if (kind === "l_shape" && (params.notch_width_mm >= params.width_mm || params.notch_height_mm >= params.height_mm)) {
            return shapeFailure("The cutout must stay inside the outer shape.");
        }
        if (kind === "clipped_corner" && (params.cut_width_mm >= params.width_mm || params.cut_height_mm >= params.height_mm)) {
            return shapeFailure("The clipped corner must stay inside the outer shape.");
        }
        const figure = shapeFigure(kind, params);
        if (!figure) return shapeFailure("That point is outside the drawing range.");
        return { ok: true, messageKey: "", params, figure };
    }

    function shapeFromDrag(kind, anchor, point) {
        const start = anchor || { x: 0, y: 0 };
        const end = point || start;
        const x = Math.min(num(start.x), num(end.x));
        const y = Math.min(num(start.y), num(end.y));
        const width = Math.abs(num(end.x) - num(start.x));
        const height = Math.abs(num(end.y) - num(start.y));
        const radius = lengthMm(start.x, start.y, end.x, end.y);
        if (kind === "rectangle") {
            return normalizeShape(kind, { x_mm: x, y_mm: y, width_mm: width, height_mm: height, rotation_deg: 0 });
        }
        if (kind === "circle") return normalizeShape(kind, { cx_mm: start.x, cy_mm: start.y, radius_mm: radius });
        if (kind === "ellipse") {
            return normalizeShape(kind, { cx_mm: start.x, cy_mm: start.y, rx_mm: width, ry_mm: height, rotation_deg: 0 });
        }
        if (kind === "arc") {
            let sweep = angleDeg(start.x, start.y, end.x, end.y);
            if (Math.abs(sweep) < 1) sweep = 90;
            return normalizeShape(kind, {
                cx_mm: start.x,
                cy_mm: start.y,
                radius_mm: radius,
                start_angle_deg: 0,
                sweep_angle_deg: sweep,
            });
        }
        if (kind === "polygon") {
            return normalizeShape(kind, { cx_mm: start.x, cy_mm: start.y, radius_mm: radius, sides: 6, rotation_deg: 0 });
        }
        if (kind === "trapezoid") {
            const top = quantizeMm(width * 0.6);
            return normalizeShape(kind, {
                x_mm: x,
                y_mm: y,
                bottom_width_mm: width,
                top_width_mm: top == null ? width : top,
                height_mm: height,
            });
        }
        if (kind === "l_shape") {
            return normalizeShape(kind, {
                x_mm: x,
                y_mm: y,
                width_mm: width,
                height_mm: height,
                notch_width_mm: width / 3,
                notch_height_mm: height / 3,
            });
        }
        if (kind === "clipped_corner") {
            return normalizeShape(kind, {
                x_mm: x,
                y_mm: y,
                width_mm: width,
                height_mm: height,
                cut_width_mm: Math.min(width, height) / 4,
                cut_height_mm: Math.min(width, height) / 4,
                corner: "top_right",
            });
        }
        return shapeFailure("That shape is not available.");
    }

    function lineParts(points, closed) {
        const nodes = points.map((point) => ({ x_mm: point.x, y_mm: point.y }));
        const segments = [];
        const limit = closed ? points.length : points.length - 1;
        for (let index = 0; index < limit; index += 1) {
            segments.push({
                kind: "line",
                from: index,
                to: (index + 1) % points.length,
            });
        }
        return { closed, nodes, segments };
    }

    function shapePathParts(kind, params) {
        const built = normalizeShape(kind, params);
        if (!built.ok) return null;
        if (kind === "circle" || (kind === "arc" && Math.abs(Math.abs(params.sweep_angle_deg) - 360) < 1e-6)) {
            const radius = kind === "circle" ? params.radius_mm : params.radius_mm;
            const cx = params.cx_mm;
            const cy = params.cy_mm;
            const east = turnedPoint({ x: cx + radius, y: cy }, { x: cx, y: cy }, 0);
            const west = turnedPoint({ x: cx - radius, y: cy }, { x: cx, y: cy }, 0);
            if (!east || !west) return null;
            return {
                closed: true,
                nodes: [{ x_mm: east.x, y_mm: east.y }, { x_mm: west.x, y_mm: west.y }],
                segments: [
                    { kind: "arc", from: 0, to: 1, radius_mm: radius, large_arc: false, sweep_clockwise: true },
                    { kind: "arc", from: 1, to: 0, radius_mm: radius, large_arc: false, sweep_clockwise: true },
                ],
            };
        }
        if (kind === "arc") {
            const figure = built.figure;
            const start = figure.points[0];
            const end = figure.points[figure.points.length - 1];
            return {
                closed: false,
                nodes: [{ x_mm: start.x, y_mm: start.y }, { x_mm: end.x, y_mm: end.y }],
                segments: [{
                    kind: "arc",
                    from: 0,
                    to: 1,
                    radius_mm: params.radius_mm,
                    large_arc: Math.abs(params.sweep_angle_deg) > 180,
                    sweep_clockwise: params.sweep_angle_deg > 0,
                }],
            };
        }
        if (kind === "ellipse") {
            const cx = params.cx_mm;
            const cy = params.cy_mm;
            const rx = params.rx_mm;
            const ry = params.ry_mm;
            const k = BEZIER_KAPPA;
            const locals = [
                { x: cx + rx, y: cy },
                { x: cx, y: cy + ry },
                { x: cx - rx, y: cy },
                { x: cx, y: cy - ry },
            ];
            const controls = [
                [{ x: cx + rx, y: cy + k * ry }, { x: cx + k * rx, y: cy + ry }],
                [{ x: cx - k * rx, y: cy + ry }, { x: cx - rx, y: cy + k * ry }],
                [{ x: cx - rx, y: cy - k * ry }, { x: cx - k * rx, y: cy - ry }],
                [{ x: cx + k * rx, y: cy - ry }, { x: cx + rx, y: cy - k * ry }],
            ];
            const pivot = { x: cx, y: cy };
            const nodes = locals.map((point) => turnedPoint(point, pivot, params.rotation_deg));
            if (nodes.some((point) => !point)) return null;
            const segments = controls.map((pair, index) => {
                const mapped = pair.map((point) => turnedPoint(point, pivot, params.rotation_deg));
                if (mapped.some((point) => !point)) return null;
                return {
                    kind: "bezier",
                    from: index,
                    to: (index + 1) % 4,
                    controls: mapped.map((point) => ({ x_mm: point.x, y_mm: point.y })),
                };
            });
            if (segments.some((segment) => !segment)) return null;
            return {
                closed: true,
                nodes: nodes.map((point) => ({ x_mm: point.x, y_mm: point.y })),
                segments,
            };
        }
        return lineParts(built.figure.points, true);
    }

    function bezierFromPoints(start, end) {
        const x1 = quantizeMm(start && start.x);
        const y1 = quantizeMm(start && start.y);
        const x2 = quantizeMm(end && end.x);
        const y2 = quantizeMm(end && end.y);
        if (x1 == null || y1 == null || x2 == null || y2 == null) return shapeFailure("Enter a valid dimension.");
        if (x1 === x2 && y1 === y2) return shapeFailure("A zero-length segment was not created.");
        const dx = x2 - x1;
        const dy = y2 - y1;
        const span = Math.hypot(dx, dy) || 1;
        const offset = Math.min(40, span / 4);
        const ox = quantizeMm((-dy / span) * offset);
        const oy = quantizeMm((dx / span) * offset);
        if (ox == null || oy == null) return shapeFailure("That point is outside the drawing range.");
        const c1 = { x_mm: quantizeMm(x1 + dx / 3 + ox), y_mm: quantizeMm(y1 + dy / 3 + oy) };
        const c2 = { x_mm: quantizeMm(x1 + (2 * dx) / 3 + ox), y_mm: quantizeMm(y1 + (2 * dy) / 3 + oy) };
        if (c1.x_mm == null || c1.y_mm == null || c2.x_mm == null || c2.y_mm == null) {
            return shapeFailure("That point is outside the drawing range.");
        }
        return {
            ok: true,
            messageKey: "",
            parts: {
                closed: false,
                nodes: [{ x_mm: x1, y_mm: y1 }, { x_mm: x2, y_mm: y2 }],
                segments: [{ kind: "bezier", from: 0, to: 1, controls: [c1, c2] }],
            },
        };
    }

    function pointInPolygon(point, points) {
        const rows = points || [];
        if (!point || rows.length < 3) return false;
        let inside = false;
        for (let index = 0, previous = rows.length - 1; index < rows.length; previous = index, index += 1) {
            const current = rows[index];
            const prior = rows[previous];
            const crosses = (num(current.y) > num(point.y)) !== (num(prior.y) > num(point.y));
            if (!crosses) continue;
            const xCross = ((num(prior.x) - num(current.x)) * (num(point.y) - num(current.y))) / ((num(prior.y) - num(current.y)) || 1e-9) + num(current.x);
            if (num(point.x) < xCross) inside = !inside;
        }
        return inside;
    }

    function outlineDistance(point, points, closed) {
        const rows = points || [];
        if (!rows.length || !point) return Infinity;
        const limit = closed ? rows.length : Math.max(0, rows.length - 1);
        let best = Infinity;
        for (let index = 0; index < limit; index += 1) {
            const from = rows[index];
            const to = rows[(index + 1) % rows.length];
            const dx = num(to.x) - num(from.x);
            const dy = num(to.y) - num(from.y);
            const lengthSq = dx * dx + dy * dy;
            let distance;
            if (lengthSq <= 0) distance = lengthMm(point.x, point.y, from.x, from.y);
            else {
                let t = ((num(point.x) - num(from.x)) * dx + (num(point.y) - num(from.y)) * dy) / lengthSq;
                t = Math.max(0, Math.min(1, t));
                distance = lengthMm(point.x, point.y, num(from.x) + dx * t, num(from.y) + dy * t);
            }
            if (distance < best) best = distance;
        }
        return best;
    }

    function pathMarkup(frame, path) {
        const nodes = {};
        (path.nodes || []).forEach((node) => { nodes[node.id] = node; });
        const mapPoint = (x, y) => (frame ? doorToWorld(frame, x, y) : { x, y });
        const mirrored = Boolean(frame && frame.flipH) !== Boolean(frame && frame.flipV);
        let markup = "";
        (path.segments || []).forEach((segment, index) => {
            const from = nodes[segment.from_node];
            const to = nodes[segment.to_node];
            if (!from || !to) return;
            const start = mapPoint(from.x_mm, from.y_mm);
            const end = mapPoint(to.x_mm, to.y_mm);
            if (index === 0) markup += `M${start.x} ${start.y}`;
            if (segment.kind === "arc") {
                const sweep = (segment.sweep_clockwise === true) !== mirrored ? 1 : 0;
                markup += ` A${segment.radius_mm} ${segment.radius_mm} 0 ${segment.large_arc ? 1 : 0} ${sweep} ${end.x} ${end.y}`;
            } else if (segment.kind === "bezier" && segment.controls && segment.controls.length === 2) {
                const c1 = mapPoint(segment.controls[0].x_mm, segment.controls[0].y_mm);
                const c2 = mapPoint(segment.controls[1].x_mm, segment.controls[1].y_mm);
                markup += ` C${c1.x} ${c1.y} ${c2.x} ${c2.y} ${end.x} ${end.y}`;
            } else {
                markup += ` L${end.x} ${end.y}`;
            }
        });
        if (path.closed) markup += " Z";
        return markup;
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

    // Pen samples are door-local millimetres. The fit does not use the
    // documentation pen's 6mm tolerance: that gap erases small geometry.
    // Off/Low/Medium/High change the allowed deviation and the corner angle.
    // Straight spans stay lines. Curved spans become cubic Bézier segments
    // through the simplified knots, then split again if a sample is too far.
    const PEN_SAMPLE_MM = 0.2;
    const PEN_RAW_LIMIT = 6000;
    const PEN_LEVELS = Object.freeze({
        off: Object.freeze({ id: "off", labelKey: "Off", noiseMm: 0.05, toleranceMm: 0.12, cornerDeg: 18, straightMm: 0.15, maxErrorMm: 0.28, relaxMm: 0.35 }),
        low: Object.freeze({ id: "low", labelKey: "Low", noiseMm: 0.12, toleranceMm: 0.30, cornerDeg: 34, straightMm: 0.30, maxErrorMm: 0.55, relaxMm: 0.80 }),
        medium: Object.freeze({ id: "medium", labelKey: "Medium", noiseMm: 0.25, toleranceMm: 0.70, cornerDeg: 48, straightMm: 0.65, maxErrorMm: 1.05, relaxMm: 1.60 }),
        high: Object.freeze({ id: "high", labelKey: "High", noiseMm: 0.50, toleranceMm: 1.25, cornerDeg: 64, straightMm: 1.15, maxErrorMm: 1.80, relaxMm: 2.20 }),
    });

    function penLevel(id) {
        return PEN_LEVELS[id] || PEN_LEVELS.low;
    }

    function penTools() {
        return ["off", "low", "medium", "high"].map((id) => PEN_LEVELS[id]);
    }

    function penDistance(a, b) {
        return Math.hypot(b.x - a.x, b.y - a.y);
    }

    function penPerp(point, start, end) {
        const dx = end.x - start.x;
        const dy = end.y - start.y;
        const lengthSq = dx * dx + dy * dy;
        if (lengthSq <= 0) return penDistance(point, start);
        const t = Math.max(0, Math.min(1, ((point.x - start.x) * dx + (point.y - start.y) * dy) / lengthSq));
        return penDistance(point, { x: start.x + dx * t, y: start.y + dy * t });
    }

    function penPathLength(points) {
        let total = 0;
        for (let index = 1; index < points.length; index += 1) total += penDistance(points[index - 1], points[index]);
        return total;
    }

    function penDedupe(points, gap) {
        const clean = [];
        (points || []).forEach((point) => {
            const x = Number(point && point.x);
            const y = Number(point && point.y);
            if (!Number.isFinite(x) || !Number.isFinite(y)) return;
            const next = { x, y };
            if (!clean.length || penDistance(clean[clean.length - 1], next) >= gap) clean.push(next);
        });
        const source = points || [];
        const last = source.length ? source[source.length - 1] : null;
        if (last && clean.length) {
            const end = { x: Number(last.x), y: Number(last.y) };
            if (Number.isFinite(end.x) && Number.isFinite(end.y) && penDistance(clean[clean.length - 1], end) > 0.001) {
                clean.push(end);
            }
        }
        return clean;
    }

    function penTurn(a, b, c) {
        let delta = (Math.atan2(c.y - b.y, c.x - b.x) - Math.atan2(b.y - a.y, b.x - a.x)) * 180 / Math.PI;
        while (delta > 180) delta -= 360;
        while (delta < -180) delta += 360;
        return Math.abs(delta);
    }

    function penRdp(points, tolerance) {
        if (points.length <= 2) return points.slice();
        const keep = new Array(points.length).fill(false);
        keep[0] = true;
        keep[points.length - 1] = true;
        const stack = [[0, points.length - 1]];
        while (stack.length) {
            const range = stack.pop();
            let max = 0;
            let index = -1;
            for (let cursor = range[0] + 1; cursor < range[1]; cursor += 1) {
                const deviation = penPerp(points[cursor], points[range[0]], points[range[1]]);
                if (deviation > max) {
                    max = deviation;
                    index = cursor;
                }
            }
            if (index >= 0 && max > tolerance) {
                keep[index] = true;
                stack.push([range[0], index], [index, range[1]]);
            }
        }
        const simplified = [];
        for (let index = 0; index < points.length; index += 1) {
            if (keep[index]) simplified.push(points[index]);
        }
        return simplified;
    }

    function penStraight(points, tolerance) {
        if (!points || points.length < 2) return false;
        let max = 0;
        for (let index = 1; index < points.length - 1; index += 1) {
            max = Math.max(max, penPerp(points[index], points[0], points[points.length - 1]));
        }
        return max <= tolerance;
    }

    function penCorners(points, settings) {
        const indexes = [0];
        const minLeg = Math.max(0.4, settings.noiseMm * 2);
        for (let index = 1; index < points.length - 1; index += 1) {
            if (penDistance(points[index - 1], points[index]) < minLeg) continue;
            if (penDistance(points[index], points[index + 1]) < minLeg) continue;
            if (penTurn(points[index - 1], points[index], points[index + 1]) >= settings.cornerDeg) indexes.push(index);
        }
        indexes.push(points.length - 1);
        return indexes;
    }

    function cubicPoint(curve, t) {
        const u = 1 - t;
        return {
            x: (u * u * u * curve.from.x) + (3 * u * u * t * curve.c1.x) + (3 * u * t * t * curve.c2.x) + (t * t * t * curve.to.x),
            y: (u * u * u * curve.from.y) + (3 * u * u * t * curve.c1.y) + (3 * u * t * t * curve.c2.y) + (t * t * t * curve.to.y),
        };
    }

    function penCubics(knots) {
        const curves = [];
        for (let index = 0; index < knots.length - 1; index += 1) {
            const p1 = knots[index];
            const p2 = knots[index + 1];
            const prev = index === 0 ? { x: (p1.x * 2) - p2.x, y: (p1.y * 2) - p2.y } : knots[index - 1];
            const next = index + 2 >= knots.length ? { x: (p2.x * 2) - p1.x, y: (p2.y * 2) - p1.y } : knots[index + 2];
            curves.push({
                from: p1,
                to: p2,
                c1: { x: p1.x + ((p2.x - prev.x) / 6), y: p1.y + ((p2.y - prev.y) / 6) },
                c2: { x: p2.x - ((next.x - p1.x) / 6), y: p2.y - ((next.y - p1.y) / 6) },
            });
        }
        return curves;
    }

    function distanceToCurves(point, curves) {
        let best = Infinity;
        curves.forEach((curve) => {
            if (!curve.c1) {
                best = Math.min(best, penPerp(point, curve.from, curve.to));
                return;
            }
            for (let step = 0; step <= 20; step += 1) {
                best = Math.min(best, penDistance(point, cubicPoint(curve, step / 20)));
            }
        });
        return best;
    }

    function worstSpanPoint(span, curves, knots) {
        let worst = null;
        span.forEach((point) => {
            if (knots.some((knot) => penDistance(knot, point) <= 0.001)) return;
            const deviation = distanceToCurves(point, curves);
            if (!worst || deviation > worst.deviation) worst = { point, deviation };
        });
        return worst;
    }

    function fitSpan(span, settings, nodeBudget) {
        if (!span || span.length < 2) return [];
        if (span.length === 2 || penStraight(span, settings.straightMm)) {
            return [{ kind: "line", from: span[0], to: span[span.length - 1] }];
        }
        let knots = penRdp(span, settings.toleranceMm);
        if (knots.length < 3) return [{ kind: "line", from: span[0], to: span[span.length - 1] }];
        const indexOf = new Map();
        span.forEach((point, index) => indexOf.set(point, index));
        let curves = penCubics(knots);
        for (let guard = 0; guard < 8; guard += 1) {
            const worst = worstSpanPoint(span, curves, knots);
            if (!worst || worst.deviation <= settings.maxErrorMm || knots.length >= nodeBudget) break;
            const at = indexOf.get(worst.point);
            let insertAt = knots.length;
            for (let index = 0; index < knots.length; index += 1) {
                if (indexOf.get(knots[index]) > at) {
                    insertAt = index;
                    break;
                }
            }
            knots = knots.slice();
            knots.splice(insertAt, 0, worst.point);
            curves = penCubics(knots);
        }
        return curves;
    }

    function assemblePen(pieces) {
        const nodes = [];
        const segments = [];
        const add = (point) => {
            const xMm = quantizeMm(point.x);
            const yMm = quantizeMm(point.y);
            if (xMm == null || yMm == null) return -1;
            const last = nodes[nodes.length - 1];
            if (last && last.x_mm === xMm && last.y_mm === yMm) return nodes.length - 1;
            nodes.push({ x_mm: xMm, y_mm: yMm });
            return nodes.length - 1;
        };
        for (let index = 0; index < pieces.length; index += 1) {
            const piece = pieces[index];
            const from = add(piece.from);
            const to = add(piece.to);
            if (from < 0 || to < 0) return null;
            if (from === to) continue;
            if (!piece.c1) {
                segments.push({ kind: "line", from, to });
                continue;
            }
            const c1 = { x_mm: quantizeMm(piece.c1.x), y_mm: quantizeMm(piece.c1.y) };
            const c2 = { x_mm: quantizeMm(piece.c2.x), y_mm: quantizeMm(piece.c2.y) };
            if (c1.x_mm == null || c1.y_mm == null || c2.x_mm == null || c2.y_mm == null) return null;
            segments.push({ kind: "bezier", from, to, controls: [c1, c2] });
        }
        return { nodes, segments };
    }

    function fitPenOnce(points, settings, maxNodes) {
        if (penStraight(points, settings.straightMm)) {
            return assemblePen([{ kind: "line", from: points[0], to: points[points.length - 1] }]);
        }
        const corners = penCorners(points, settings);
        const pieces = [];
        const budget = Math.max(4, Math.min(80, maxNodes));
        for (let index = 0; index < corners.length - 1; index += 1) {
            const span = points.slice(corners[index], corners[index + 1] + 1);
            fitSpan(span, settings, budget).forEach((piece) => pieces.push(piece));
        }
        return assemblePen(pieces);
    }

    function suggestPenClose(points) {
        if (!points || points.length < 3) return false;
        const length = penPathLength(points);
        const gap = penDistance(points[0], points[points.length - 1]);
        const limit = Math.max(2, Math.min(8, length * 0.015));
        return length >= 12 && gap > 0.001 && gap <= limit;
    }

    function penCurvesFromParts(parts) {
        return (parts.segments || []).map((segment) => {
            const from = parts.nodes[segment.from];
            const to = parts.nodes[segment.to];
            const curve = {
                from: { x: from.x_mm, y: from.y_mm },
                to: { x: to.x_mm, y: to.y_mm },
            };
            if (segment.kind === "bezier" && segment.controls && segment.controls.length === 2) {
                curve.c1 = { x: segment.controls[0].x_mm, y: segment.controls[0].y_mm };
                curve.c2 = { x: segment.controls[1].x_mm, y: segment.controls[1].y_mm };
            }
            return curve;
        });
    }

    function penDeviationMm(points, parts) {
        if (!parts || !parts.nodes || !parts.segments) return Infinity;
        const curves = penCurvesFromParts(parts);
        let max = 0;
        (points || []).forEach((point) => {
            const x = Number(point && point.x);
            const y = Number(point && point.y);
            if (!Number.isFinite(x) || !Number.isFinite(y)) return;
            max = Math.max(max, distanceToCurves({ x, y }, curves));
        });
        return max;
    }

    function fitPenStroke(rawPoints, levelOrId, options) {
        const base = levelOrId && typeof levelOrId === "object" ? levelOrId : penLevel(levelOrId);
        const maxNodes = Math.max(2, Number(options && options.maxNodes) || 4000);
        const cleaned = penDedupe(rawPoints, base.noiseMm);
        const rejected = (code, messageKey) => ({
            ok: false,
            code,
            messageKey,
            suggestClose: false,
            parts: null,
            stats: null,
        });
        if (cleaned.length < 2 || penPathLength(cleaned) < 0.2) {
            return rejected("short_stroke", "The stroke is too short.");
        }
        let tolerance = base.toleranceMm;
        let straight = base.straightMm;
        let maxError = base.maxErrorMm;
        let built = null;
        for (let attempt = 0; attempt < 5; attempt += 1) {
            built = fitPenOnce(cleaned, {
                noiseMm: base.noiseMm,
                cornerDeg: base.cornerDeg,
                toleranceMm: tolerance,
                straightMm: straight,
                maxErrorMm: maxError,
            }, maxNodes);
            if (!built) return rejected("invalid_point", "That point is outside the drawing range.");
            if (built.segments.length && built.nodes.length <= maxNodes) break;
            if (tolerance >= base.relaxMm) break;
            const nextTolerance = Math.min(base.relaxMm, tolerance * 1.75);
            if (nextTolerance <= tolerance) break;
            tolerance = nextTolerance;
            straight = Math.min(base.relaxMm, straight * 1.75);
            maxError = Math.min(base.relaxMm * 1.4, maxError * 1.75);
        }
        if (!built || built.nodes.length < 2 || !built.segments.length) {
            return rejected("short_stroke", "The stroke is too short.");
        }
        if (built.nodes.length > maxNodes || built.segments.length > maxNodes) {
            return rejected("too_many_elements", "This stroke has too many points to store. The existing drawing was kept.");
        }
        const parts = { closed: false, nodes: built.nodes, segments: built.segments };
        return {
            ok: true,
            code: "",
            messageKey: "",
            suggestClose: suggestPenClose(cleaned),
            parts,
            stats: {
                input: cleaned.length,
                nodes: built.nodes.length,
                segments: built.segments.length,
                maxErrorMm: penDeviationMm(cleaned, parts),
                level: base.id,
            },
        };
    }

    function penPreviewPoints(points, maxCount) {
        const source = points || [];
        const limit = Math.max(2, Number(maxCount) || 480);
        if (source.length <= limit) return source.map((point) => ({ x: point.x, y: point.y }));
        const sampled = [];
        for (let index = 0; index < limit; index += 1) {
            const cursor = Math.round((index * (source.length - 1)) / (limit - 1));
            sampled.push({ x: source[cursor].x, y: source[cursor].y });
        }
        return sampled;
    }

    function penResample(points, count) {
        if (points.length <= count) return points.slice();
        const sampled = [];
        for (let index = 0; index < count; index += 1) {
            const cursor = Math.round((index * (points.length - 1)) / (count - 1));
            const point = points[cursor];
            const last = sampled[sampled.length - 1];
            if (!last || penDistance(last, point) > 0.001) sampled.push({ x: point.x, y: point.y });
        }
        return sampled;
    }

    function createPenGesture(levelId) {
        const level = penLevel(levelId);
        let pointerId = null;
        let points = [];
        let active = false;
        let finished = false;

        function push(sample, force) {
            const x = Number(sample && sample.x);
            const y = Number(sample && sample.y);
            if (!Number.isFinite(x) || !Number.isFinite(y)) return false;
            const next = { x, y };
            const last = points[points.length - 1];
            if (last && penDistance(last, next) <= (force ? 0.001 : PEN_SAMPLE_MM)) return false;
            points.push(next);
            if (points.length > PEN_RAW_LIMIT) points = penResample(points, Math.floor(PEN_RAW_LIMIT / 2));
            return true;
        }

        return {
            pointerDown(sample) {
                if (active || finished || !sample || sample.pointerId == null) return false;
                pointerId = sample.pointerId;
                active = true;
                points = [];
                push(sample, true);
                return true;
            },
            pointerMove(sample) {
                if (!active || !sample || sample.pointerId !== pointerId) return false;
                return push(sample, false);
            },
            pointerUp(sample) {
                if (!active) return null;
                if (sample && sample.pointerId != null && sample.pointerId !== pointerId) return null;
                if (sample) push(sample, true);
                active = false;
                finished = true;
                return fitPenStroke(points, level);
            },
            pointerCancel(sample) {
                if (!active) return false;
                if (sample && sample.pointerId != null && sample.pointerId !== pointerId) return false;
                active = false;
                finished = true;
                points = [];
                return true;
            },
            cancel() {
                active = false;
                finished = true;
                points = [];
            },
            active() { return active; },
            pointerId() { return pointerId; },
            preview() { return points.map((point) => ({ x: point.x, y: point.y })); },
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
        shapeTools,
        shapeFieldDefs,
        normalizeShape,
        shapeFromDrag,
        shapePathParts,
        bezierFromPoints,
        outlineDistance,
        pointInPolygon,
        pathMarkup,
        penLevel,
        penTools,
        fitPenStroke,
        penDeviationMm,
        penPreviewPoints,
        createPenGesture,
    });
})();
