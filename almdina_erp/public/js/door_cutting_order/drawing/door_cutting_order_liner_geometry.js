/* Parametric liner strip. Millimetres, origin at the piece top-left, y downward.
   This is the client port of domain/cutting/liner_geometry.py. */
(() => {
    "use strict";

    if (window.AlmdinaLinerGeometry) return;

    const CLIPPED = "Clipped Corner";
    const L_SHAPED = "L-Shaped Corner";
    const SIDE_TOP = "edge_width_top";
    const SIDE_BOTTOM = "edge_width_bottom";
    const SIDE_LEFT = "edge_long_left";
    const SIDE_RIGHT = "edge_long_right";
    const SIDE_BREAK = "edge_break";
    const SIDE_BREAK_ONLY = "edge_break_only";
    const OUTER_SIDES = [SIDE_TOP, SIDE_BOTTOM, SIDE_LEFT, SIDE_RIGHT];
    const TOLERANCE_MM = 0.25;
    const BOARD_EDGE_TOLERANCE_MM = 0.05;
    const SIDE_LABELS = {
        [SIDE_TOP]: "أعلى",
        [SIDE_BOTTOM]: "أسفل",
        [SIDE_RIGHT]: "يمين",
        [SIDE_LEFT]: "يسار",
        [SIDE_BREAK]: "الكسر",
        [SIDE_BREAK_ONLY]: "الكسر فقط",
    };

    function num(value) {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function hypot(dx, dy) {
        return Math.sqrt((dx * dx) + (dy * dy));
    }

    function dist(a, b) {
        return hypot(b[0] - a[0], b[1] - a[1]);
    }

    function availableSides(pieceType) {
        if (pieceType === CLIPPED) return OUTER_SIDES.concat([SIDE_BREAK, SIDE_BREAK_ONLY]);
        if (pieceType === L_SHAPED) return OUTER_SIDES.concat([SIDE_BREAK]);
        if (!pieceType || pieceType === "Regular") return OUTER_SIDES.slice();
        return [];
    }

    function sideLabel(side, pieceType) {
        if (pieceType === L_SHAPED && side === SIDE_BREAK) return "زاوية L";
        return SIDE_LABELS[side] || side;
    }

    function pieceFromRow(row) {
        const source = row || {};
        const width = num(source.cut_width_cm) || num(source.width_cm) || num(source.original_w) || num(source.w);
        const length = num(source.cut_length_cm) || num(source.length_cm) || num(source.original_h) || num(source.h);
        return {
            pieceType: source.piece_type || "Regular",
            widthCm: width,
            lengthCm: length,
            position: source.clipped_corner_position || "Top Right",
            cutWidthCm: num(source.clipped_corner_width_cm),
            cutLengthCm: num(source.clipped_corner_length_cm),
        };
    }

    function cornerPolygon(piece, width, height, cutX, cutY) {
        const position = piece.position || "Top Right";
        const shaped = piece.pieceType === L_SHAPED;
        const polygons = shaped
            ? {
                "Top Right": [[0, 0], [width - cutX, 0], [width - cutX, cutY], [width, cutY], [width, height], [0, height]],
                "Top Left": [[cutX, 0], [width, 0], [width, height], [0, height], [0, cutY], [cutX, cutY]],
                "Bottom Right": [[0, 0], [width, 0], [width, height - cutY], [width - cutX, height - cutY], [width - cutX, height], [0, height]],
                "Bottom Left": [[0, 0], [width, 0], [width, height], [cutX, height], [cutX, height - cutY], [0, height - cutY]],
            }
            : {
                "Top Right": [[0, 0], [width - cutX, 0], [width, cutY], [width, height], [0, height]],
                "Top Left": [[cutX, 0], [width, 0], [width, height], [0, height], [0, cutY]],
                "Bottom Right": [[0, 0], [width, 0], [width, height - cutY], [width - cutX, height], [0, height]],
                "Bottom Left": [[0, 0], [width, 0], [width, height], [cutX, height], [0, height - cutY]],
            };
        return polygons[position] || null;
    }

    function piecePolygonMm(piece) {
        const width = piece.widthCm * 10;
        const height = piece.lengthCm * 10;
        if (piece.pieceType !== CLIPPED && piece.pieceType !== L_SHAPED) {
            return [[0, 0], [width, 0], [width, height], [0, height]];
        }
        const cutX = Math.min(Math.max(piece.cutWidthCm * 10, 0), width * 0.95);
        const cutY = Math.min(Math.max(piece.cutLengthCm * 10, 0), height * 0.95);
        return cornerPolygon(piece, width, height, cutX, cutY);
    }

    function edgePaths(piece) {
        const width = piece.widthCm * 10;
        const height = piece.lengthCm * 10;
        if (piece.pieceType !== CLIPPED && piece.pieceType !== L_SHAPED) {
            return {
                [SIDE_TOP]: [[0, 0], [width, 0]],
                [SIDE_BOTTOM]: [[0, height], [width, height]],
                [SIDE_LEFT]: [[0, 0], [0, height]],
                [SIDE_RIGHT]: [[width, 0], [width, height]],
            };
        }
        const cutX = Math.min(Math.max(piece.cutWidthCm * 10, 0), width * 0.95);
        const cutY = Math.min(Math.max(piece.cutLengthCm * 10, 0), height * 0.95);
        const position = piece.position || "Top Right";
        const clipped = {
            "Top Right": {
                [SIDE_TOP]: [[0, 0], [width - cutX, 0]],
                [SIDE_RIGHT]: [[width, cutY], [width, height]],
                [SIDE_BOTTOM]: [[width, height], [0, height]],
                [SIDE_LEFT]: [[0, height], [0, 0]],
                [SIDE_BREAK]: [[0, 0], [width - cutX, 0], [width, cutY], [width, height]],
                [SIDE_BREAK_ONLY]: [[width - cutX, 0], [width, cutY]],
            },
            "Top Left": {
                [SIDE_TOP]: [[cutX, 0], [width, 0]],
                [SIDE_RIGHT]: [[width, 0], [width, height]],
                [SIDE_BOTTOM]: [[width, height], [0, height]],
                [SIDE_LEFT]: [[0, height], [0, cutY]],
                [SIDE_BREAK]: [[width, 0], [cutX, 0], [0, cutY], [0, height]],
                [SIDE_BREAK_ONLY]: [[cutX, 0], [0, cutY]],
            },
            "Bottom Right": {
                [SIDE_TOP]: [[0, 0], [width, 0]],
                [SIDE_RIGHT]: [[width, 0], [width, height - cutY]],
                [SIDE_BOTTOM]: [[width - cutX, height], [0, height]],
                [SIDE_LEFT]: [[0, height], [0, 0]],
                [SIDE_BREAK]: [[width, 0], [width, height - cutY], [width - cutX, height], [0, height]],
                [SIDE_BREAK_ONLY]: [[width, height - cutY], [width - cutX, height]],
            },
            "Bottom Left": {
                [SIDE_TOP]: [[0, 0], [width, 0]],
                [SIDE_RIGHT]: [[width, 0], [width, height]],
                [SIDE_BOTTOM]: [[width, height], [cutX, height]],
                [SIDE_LEFT]: [[0, height - cutY], [0, 0]],
                [SIDE_BREAK]: [[0, 0], [0, height - cutY], [cutX, height], [width, height]],
                [SIDE_BREAK_ONLY]: [[0, height - cutY], [cutX, height]],
            },
        };
        const shaped = {
            "Top Right": { [SIDE_BREAK]: [[width - cutX, 0], [width - cutX, cutY], [width, cutY]] },
            "Top Left": { [SIDE_BREAK]: [[cutX, 0], [cutX, cutY], [0, cutY]] },
            "Bottom Right": { [SIDE_BREAK]: [[width, height - cutY], [width - cutX, height - cutY], [width - cutX, height]] },
            "Bottom Left": { [SIDE_BREAK]: [[0, height - cutY], [cutX, height - cutY], [cutX, height]] },
        };
        const paths = Object.assign({}, clipped[position]);
        if (piece.pieceType === L_SHAPED) {
            paths[SIDE_BREAK] = shaped[position][SIDE_BREAK];
            delete paths[SIDE_BREAK_ONLY];
        }
        return paths;
    }

    function onSegment(point, start, end, tolerance) {
        const dx = end[0] - start[0];
        const dy = end[1] - start[1];
        const lengthSq = (dx * dx) + (dy * dy);
        if (lengthSq <= 1e-12) return dist(point, start) <= tolerance;
        const ratio = Math.min(1, Math.max(0, (((point[0] - start[0]) * dx) + ((point[1] - start[1]) * dy)) / lengthSq));
        const nearest = [start[0] + (dx * ratio), start[1] + (dy * ratio)];
        return dist(point, nearest) <= tolerance;
    }

    function pointInPolygon(point, polygon, tolerance = TOLERANCE_MM) {
        if (!polygon || polygon.length < 3) return false;
        for (let index = 0; index < polygon.length; index += 1) {
            const start = polygon[index];
            const end = polygon[(index + 1) % polygon.length];
            if (onSegment(point, start, end, tolerance)) return true;
        }
        let inside = false;
        for (let index = 0; index < polygon.length; index += 1) {
            const start = polygon[index];
            const end = polygon[(index + 1) % polygon.length];
            if ((start[1] > point[1]) === (end[1] > point[1])) continue;
            const crossingX = start[0] + ((point[1] - start[1]) * (end[0] - start[0]) / (end[1] - start[1]));
            if (crossingX > point[0]) inside = !inside;
        }
        return inside;
    }

    function leftNormal(start, end) {
        const dx = end[0] - start[0];
        const dy = end[1] - start[1];
        const length = hypot(dx, dy) || 1;
        return [-dy / length, dx / length];
    }

    function inwardSign(polyline, polygon) {
        let best = -1;
        let segment = [polyline[0], polyline[1]];
        for (let index = 0; index < polyline.length - 1; index += 1) {
            const length = dist(polyline[index], polyline[index + 1]);
            if (length > best) {
                best = length;
                segment = [polyline[index], polyline[index + 1]];
            }
        }
        const normal = leftNormal(segment[0], segment[1]);
        const midpoint = [(segment[0][0] + segment[1][0]) / 2, (segment[0][1] + segment[1][1]) / 2];
        const probe = [midpoint[0] + normal[0], midpoint[1] + normal[1]];
        return pointInPolygon(probe, polygon) ? 1 : -1;
    }

    function intersectOffsetLines(first, second) {
        const direction = [first[1][0] - first[0][0], first[1][1] - first[0][1]];
        const other = [second[1][0] - second[0][0], second[1][1] - second[0][1]];
        const denominator = (direction[0] * other[1]) - (direction[1] * other[0]);
        if (Math.abs(denominator) <= 1e-9) return null;
        const step = (
            ((second[0][0] - first[0][0]) * other[1])
            - ((second[0][1] - first[0][1]) * other[0])
        ) / denominator;
        return [first[0][0] + (direction[0] * step), first[0][1] + (direction[1] * step)];
    }

    function offsetPolyline(polyline, distance, sign) {
        const segments = [];
        for (let index = 0; index < polyline.length - 1; index += 1) {
            const normal = leftNormal(polyline[index], polyline[index + 1]);
            const shift = [sign * normal[0] * distance, sign * normal[1] * distance];
            segments.push([
                [polyline[index][0] + shift[0], polyline[index][1] + shift[1]],
                [polyline[index + 1][0] + shift[0], polyline[index + 1][1] + shift[1]],
            ]);
        }
        if (!segments.length) return [];
        const points = [segments[0][0]];
        for (let index = 1; index < segments.length; index += 1) {
            const joint = intersectOffsetLines(segments[index - 1], segments[index]);
            points.push(joint || segments[index - 1][1]);
        }
        points.push(segments[segments.length - 1][1]);
        return points;
    }

    function quantizeCm(value) {
        return Math.round(num(value) * 1000) / 1000;
    }

    function contourNotchCm(input) {
        const source = input || {};
        const finished = {
            cutWidthCm: num(source.notchWidthCm),
            cutLengthCm: num(source.notchLengthCm),
        };
        if (source.pieceType !== L_SHAPED) return finished;
        if (source.edgeBreak && (source.innerMm === null || source.innerMm === undefined)) {
            return finished;
        }
        const pair = {
            "Top Right": ["long_right", "width_top"],
            "Bottom Right": ["long_right", "width_bottom"],
            "Top Left": ["long_left", "width_top"],
            "Bottom Left": ["long_left", "width_bottom"],
        }[source.position || "Top Right"];
        if (!pair) return finished;
        const inner = source.edgeBreak ? num(source.innerMm) : 0;
        const sides = source.sideThicknessMm || {};
        return {
            cutWidthCm: quantizeCm(finished.cutWidthCm - (num(sides[pair[0]]) / 10) + (inner / 10)),
            cutLengthCm: quantizeCm(finished.cutLengthCm - (num(sides[pair[1]]) / 10) + (inner / 10)),
        };
    }

    function validationCode(piece, side, offsetCm, widthCm) {
        if (!(piece.widthCm > 0) || !(piece.lengthCm > 0)) return "missing_dimensions";
        if (piece.pieceType === CLIPPED || piece.pieceType === L_SHAPED) {
            if (!(piece.cutWidthCm > 0) || !(piece.cutLengthCm > 0)) return "missing_corner";
            if (!["Top Right", "Top Left", "Bottom Right", "Bottom Left"].includes(piece.position)) {
                return "invalid_corner";
            }
        }
        if (!availableSides(piece.pieceType).includes(side)) return "side_unavailable";
        const offset = Number(offsetCm);
        const width = Number(widthCm);
        if (!Number.isFinite(offset) || offset < 0) return "offset_invalid";
        if (!Number.isFinite(width) || width <= 0) return "width_invalid";
        const polygon = piecePolygonMm(piece);
        const reference = edgePaths(piece)[side];
        if (!polygon || !reference) return "side_unavailable";
        const sign = inwardSign(reference, polygon);
        const samples = offsetPolyline(reference, (offset + width) * 10, sign)
            .concat(offsetPolyline(reference, offset * 10, sign));
        if (samples.some(point => !pointInPolygon(point, polygon, TOLERANCE_MM))) return "strip_outside";
        return "";
    }

    function stripPolygonMm(piece, side, offsetCm, widthCm) {
        const error = validationCode(piece, side, offsetCm, widthCm);
        if (error) {
            const failure = new Error(error);
            failure.code = error;
            throw failure;
        }
        const polygon = piecePolygonMm(piece);
        const reference = edgePaths(piece)[side];
        const sign = inwardSign(reference, polygon);
        const near = offsetPolyline(reference, Number(offsetCm) * 10, sign);
        const far = offsetPolyline(reference, (Number(offsetCm) + Number(widthCm)) * 10, sign);
        return near.concat(far.slice().reverse());
    }

    function cutterCenterOffsetsMm(widthMm, diameterMm) {
        if (!Number.isFinite(widthMm) || !Number.isFinite(diameterMm) || diameterMm <= TOLERANCE_MM || widthMm <= TOLERANCE_MM) {
            const error = new Error("cutter_diameter_invalid");
            error.code = "cutter_diameter_invalid";
            throw error;
        }
        if (widthMm + TOLERANCE_MM < diameterMm) {
            const error = new Error("liner_narrower_than_cutter");
            error.code = "liner_narrower_than_cutter";
            throw error;
        }
        const radius = diameterMm / 2;
        if (Math.abs(widthMm - diameterMm) <= TOLERANCE_MM) return [widthMm / 2];
        const leading = [radius];
        const trailing = [widthMm - radius];
        while (trailing[0] - leading[leading.length - 1] > diameterMm + 1e-9) {
            leading.push(leading[leading.length - 1] + diameterMm);
            if (trailing[0] - leading[leading.length - 1] > diameterMm + 1e-9) {
                trailing.unshift(trailing[0] - diameterMm);
            }
        }
        return leading.concat(trailing);
    }

    function boundaryDistance(point, polygon) {
        const edges = polygon.map((start, index) => [start, polygon[(index + 1) % polygon.length]]);
        return Math.min(...edges.map(edge => pointSegDist(point, edge[0], edge[1])));
    }

    function pointSegDist(point, start, end) {
        const dx = end[0] - start[0];
        const dy = end[1] - start[1];
        const lengthSq = (dx * dx) + (dy * dy);
        if (lengthSq <= 1e-12) return dist(point, start);
        const ratio = Math.min(1, Math.max(0, (((point[0] - start[0]) * dx) + ((point[1] - start[1]) * dy)) / lengthSq));
        return dist(point, [start[0] + (dx * ratio), start[1] + (dy * ratio)]);
    }

    function rayExit(origin, direction, polygon) {
        let best = null;
        polygon.forEach((start, index) => {
            const end = polygon[(index + 1) % polygon.length];
            const edge = [end[0] - start[0], end[1] - start[1]];
            const denominator = (direction[0] * edge[1]) - (direction[1] * edge[0]);
            if (Math.abs(denominator) <= 1e-12) return;
            const offset = [start[0] - origin[0], start[1] - origin[1]];
            const travel = ((offset[0] * edge[1]) - (offset[1] * edge[0])) / denominator;
            const along = ((offset[0] * direction[1]) - (offset[1] * direction[0])) / denominator;
            if (travel <= 1e-6 || along < -1e-6 || along > 1 + 1e-6) return;
            if (best === null || travel < best) best = travel;
        });
        if (best === null) return null;
        return [origin[0] + (direction[0] * best), origin[1] + (direction[1] * best)];
    }

    function fail(code) {
        const error = new Error(code);
        error.code = code;
        throw error;
    }

    function polylineLength(path) {
        let length = 0;
        for (let index = 1; index < path.length; index += 1) length += dist(path[index - 1], path[index]);
        return length;
    }

    function pointAlong(path, distance) {
        if (path.length < 2) fail("side_unavailable");
        if (distance <= 1e-9) return { point: path[0], index: 0 };
        let walked = 0;
        for (let index = 1; index < path.length; index += 1) {
            const start = path[index - 1];
            const end = path[index];
            const length = dist(start, end);
            if (walked + length >= distance - 1e-9) {
                const ratio = length <= 1e-12 ? 0 : Math.min(1, Math.max(0, (distance - walked) / length));
                return {
                    point: [start[0] + ((end[0] - start[0]) * ratio), start[1] + ((end[1] - start[1]) * ratio)],
                    index: index - 1,
                };
            }
            walked += length;
        }
        return { point: path[path.length - 1], index: path.length - 2 };
    }

    function subpolyline(path, startMm, endMm) {
        const total = polylineLength(path);
        if (startMm <= TOLERANCE_MM && endMm >= total - TOLERANCE_MM) return path.map(point => point.slice());
        const start = pointAlong(path, startMm);
        const end = pointAlong(path, endMm);
        const points = [start.point];
        for (let index = start.index + 1; index <= end.index; index += 1) {
            if (dist(points[points.length - 1], path[index]) > 1e-6) points.push(path[index]);
        }
        if (dist(points[points.length - 1], end.point) > 1e-6) points.push(end.point);
        if (points.length < 2) points.push(end.point);
        return points;
    }

    function spanHitsBend(path, startMm, endMm) {
        const total = polylineLength(path);
        let walked = 0;
        for (let index = 1; index < path.length - 1; index += 1) {
            walked += dist(path[index - 1], path[index]);
            if (walked <= TOLERANCE_MM || Math.abs(walked - total) <= TOLERANCE_MM) continue;
            if (Math.abs(walked - startMm) <= TOLERANCE_MM || Math.abs(walked - endMm) <= TOLERANCE_MM) return true;
        }
        return false;
    }

    function resolvedSpanMm(reference, startCm, lengthCm) {
        const edge = polylineLength(reference);
        const start = Math.max(0, num(startCm) * 10);
        if (num(startCm) < -TOLERANCE_MM / 10) fail("liner_start_invalid");
        const explicit = !(lengthCm == null || lengthCm === "" || !(num(lengthCm) > 0));
        let length = explicit ? num(lengthCm) * 10 : edge - start;
        if (!(length > TOLERANCE_MM)) fail("liner_length_invalid");
        if (start + length > edge + TOLERANCE_MM) fail("liner_span_exceeds_edge");
        return { start, end: start + Math.min(length, edge - start), edge };
    }

    function preparedReference(piece, side, startCm, lengthCm) {
        const reference = edgePaths(piece)[side];
        if (!reference) fail("side_unavailable");
        const span = resolvedSpanMm(reference, startCm, lengthCm);
        if (spanHitsBend(reference, span.start, span.end)) fail("liner_span_on_corner");
        return {
            reference,
            clipped: subpolyline(reference, span.start, span.end),
            boundaryStart: span.start <= TOLERANCE_MM,
            boundaryEnd: Math.abs(span.end - span.edge) <= TOLERANCE_MM,
        };
    }

    function extendCenterline(polyline, extension, polygon, ends) {
        const points = polyline.map(point => point.slice());
        if (points.length < 2) fail("liner_extension_unsafe");
        const which = ends || { start: true, end: true };
        const pairs = [];
        if (which.start) pairs.push([0, 1]);
        if (which.end) pairs.push([points.length - 1, points.length - 2]);
        pairs.forEach(pair => {
            const origin = points[pair[0]];
            const toward = points[pair[1]];
            const delta = [origin[0] - toward[0], origin[1] - toward[1]];
            const length = Math.hypot(delta[0], delta[1]) || 1;
            const direction = [delta[0] / length, delta[1] / length];
            const hit = boundaryDistance(origin, polygon) <= TOLERANCE_MM
                ? origin
                : rayExit(origin, direction, polygon);
            if (!hit) {
                const error = new Error("liner_extension_unsafe");
                error.code = "liner_extension_unsafe";
                throw error;
            }
            const amount = pair[0] === 0
                ? (which.startExtension != null ? which.startExtension : extension)
                : (which.endExtension != null ? which.endExtension : extension);
            points[pair[0]] = [hit[0] + (direction[0] * amount), hit[1] + (direction[1] * amount)];
        });
        return points;
    }

    function centerlineMm(piece, side, offsetCm, widthCm, startCm, lengthCm) {
        const error = validationCode(piece, side, offsetCm, widthCm);
        if (error) fail(error);
        const prepared = preparedReference(piece, side, startCm, lengthCm);
        const polygon = piecePolygonMm(piece);
        const sign = inwardSign(prepared.reference, polygon);
        const distance = (num(offsetCm) * 10) + ((num(widthCm) * 10) / 2);
        const reference = prepared.clipped;
        return offsetPolyline(reference, distance, sign);
    }

    function collinearPoint(start, middle, end) {
        const area = Math.abs(
            ((middle[0] - start[0]) * (end[1] - start[1]))
            - ((middle[1] - start[1]) * (end[0] - start[0]))
        );
        return area <= TOLERANCE_MM * Math.max(dist(start, end), 1);
    }

    function chainPresent(path, points) {
        if (points.length < 2) return true;
        for (let startIndex = 0; startIndex < path.length; startIndex += 1) {
            if (dist(path[startIndex], points[0]) > TOLERANCE_MM) continue;
            let cursor = 1;
            for (let laterIndex = startIndex + 1; laterIndex < path.length; laterIndex += 1) {
                const later = path[laterIndex];
                if (dist(later, points[cursor]) <= TOLERANCE_MM) {
                    cursor += 1;
                    if (cursor === points.length) return true;
                    continue;
                }
                if (!collinearPoint(points[cursor - 1], later, points[cursor])) break;
            }
        }
        return false;
    }

    function spanPresent(path, endpoints) {
        return chainPresent(path, endpoints) || chainPresent(path, endpoints.slice().reverse());
    }

    function prependClosure(path, endpoints) {
        if (spanPresent(path, endpoints)) return path;
        const ordered = endpoints.slice();
        if (dist(ordered[ordered.length - 1], path[0]) > TOLERANCE_MM) ordered.reverse();
        if (dist(ordered[ordered.length - 1], path[0]) > TOLERANCE_MM) fail("liner_extension_unsafe");
        return ordered.slice(0, -1).concat(path);
    }

    function appendClosure(path, endpoints, returnPass) {
        if (spanPresent(path, endpoints)) return path.slice();
        const points = path.slice();
        const nearEnd = Math.min(dist(points[points.length - 1], endpoints[0]), dist(points[points.length - 1], endpoints[endpoints.length - 1]));
        if (nearEnd > TOLERANCE_MM) {
            const retrace = returnPass.slice();
            if (dist(points[points.length - 1], retrace[0]) > TOLERANCE_MM) retrace.reverse();
            if (dist(points[points.length - 1], retrace[0]) > TOLERANCE_MM) fail("liner_extension_unsafe");
            retrace.slice(1).forEach(point => points.push(point));
        }
        const ordered = endpoints.slice();
        if (dist(points[points.length - 1], ordered[0]) > TOLERANCE_MM) ordered.reverse();
        if (dist(points[points.length - 1], ordered[0]) > TOLERANCE_MM) fail("liner_extension_unsafe");
        ordered.slice(1).forEach(point => points.push(point));
        return points;
    }

    function resolveSawn(explicit, boundary) {
        if (explicit == null) return boundary;
        return Boolean(explicit) && boundary;
    }

    function boardEdge(start, end, board) {
        if (!board) return false;
        const sides = [
            [0, num(board.minX)],
            [0, num(board.maxX)],
            [1, num(board.minY)],
            [1, num(board.maxY)],
        ];
        return sides.some(([axis, value]) => (
            Math.abs(start[axis] - value) <= BOARD_EDGE_TOLERANCE_MM
            && Math.abs(end[axis] - value) <= BOARD_EDGE_TOLERANCE_MM
        ));
    }

    function transformDirection(direction, mirrored, quarterTurns, width, height) {
        const origin = transformPoint([0, 0], mirrored, quarterTurns, width, height);
        const moved = transformPoint(direction, mirrored, quarterTurns, width, height);
        return [moved[0] - origin[0], moved[1] - origin[1]];
    }

    function faceEdge(polygon, point, direction) {
        const length = Math.hypot(direction[0], direction[1]) || 1;
        const unit = [direction[0] / length, direction[1] / length];
        let best = null;
        let bestScore = -1;
        polygon.forEach((start, index) => {
            const end = polygon[(index + 1) % polygon.length];
            if (pointSegDist(point, start, end) > TOLERANCE_MM) return;
            const normal = leftNormal(start, end);
            const score = Math.abs((normal[0] * unit[0]) + (normal[1] * unit[1]));
            if (score > bestScore) {
                best = [start, end];
                bestScore = score;
            }
        });
        return best;
    }

    function sawnBoundaryEnds(piece, linerPiece, board) {
        if (!board) return null;
        const prepared = preparedReference(
            linerPiece,
            piece.liner_reference_side,
            piece.liner_start_cm,
            piece.liner_length_cm
        );
        const polygon = placedPolygonMm(piece);
        const width = linerPiece.widthCm * 10;
        const height = linerPiece.lengthCm * 10;
        const mirrored = Boolean(piece.corner_mirrored);
        const turns = piece.rotated ? 1 : 0;
        function endSawn(atStart, boundary) {
            if (!boundary) return false;
            const clipped = prepared.clipped;
            const origin = atStart ? clipped[0] : clipped[clipped.length - 1];
            const toward = atStart ? clipped[1] : clipped[clipped.length - 2];
            const direction = transformDirection(
                [origin[0] - toward[0], origin[1] - toward[1]],
                mirrored,
                turns,
                width,
                height
            );
            const placed = placeLocalPath(piece, linerPiece, [origin])[0];
            const edge = faceEdge(polygon, placed, direction);
            if (!edge) return true;
            return !boardEdge(edge[0], edge[1], board);
        }
        return {
            startSawn: endSawn(true, prepared.boundaryStart),
            endSawn: endSawn(false, prepared.boundaryEnd),
        };
    }

    function toolpathMm(piece, side, offsetCm, widthCm, cutterDiameterMm, startCm, lengthCm, ends) {
        const error = validationCode(piece, side, offsetCm, widthCm);
        if (error) fail(error);
        const centers = cutterCenterOffsetsMm(num(widthCm) * 10, num(cutterDiameterMm));
        const polygon = piecePolygonMm(piece);
        const prepared = preparedReference(piece, side, startCm, lengthCm);
        const sign = inwardSign(prepared.reference, polygon);
        const radius = num(cutterDiameterMm) / 2;
        const startSawn = resolveSawn(ends && ends.startSawn, prepared.boundaryStart);
        const endSawn = resolveSawn(ends && ends.endSawn, prepared.boundaryEnd);
        const extendStart = prepared.boundaryStart;
        const extendEnd = prepared.boundaryEnd;
        const needsFlat = !startSawn || !endSawn;
        if (needsFlat && centers.length < 2) fail("liner_flat_end_unmachinable");
        const trimStart = extendStart ? 0 : radius;
        const trimEnd = extendEnd ? 0 : radius;
        if (polylineLength(prepared.clipped) + TOLERANCE_MM < trimStart + trimEnd) {
            fail("liner_flat_end_unmachinable");
        }
        const lines = centers.map(center => {
            let line = offsetPolyline(prepared.clipped, (num(offsetCm) * 10) + center, sign);
            if (trimStart) line = subpolyline(line, trimStart, polylineLength(line));
            if (trimEnd) line = subpolyline(line, 0, polylineLength(line) - trimEnd);
            if (line.length < 2) fail("liner_flat_end_unmachinable");
            if (extendStart || extendEnd) {
                line = extendCenterline(line, radius, polygon, {
                    start: extendStart,
                    end: extendEnd,
                });
            }
            return line;
        });
        let path = [];
        lines.forEach((line, index) => {
            const sequence = index % 2 ? line.slice().reverse() : line.slice();
            if (path.length && dist(path[path.length - 1], sequence[0]) <= 1e-6) sequence.shift();
            sequence.forEach(point => path.push(point));
        });
        if (!startSawn) path = prependClosure(path, lines.map(line => line[0]));
        if (!endSawn) path = appendClosure(path, lines.map(line => line[line.length - 1]), lines[lines.length - 1]);
        return path;
    }

    function segmentsCross(a, b, c, d) {
        function side(p, q, r) {
            return ((q[0] - p[0]) * (r[1] - p[1])) - ((q[1] - p[1]) * (r[0] - p[0]));
        }
        const ab = side(a, b, c) * side(a, b, d);
        const cd = side(c, d, a) * side(c, d, b);
        return ab < -1e-8 && cd < -1e-8;
    }

    function extensionConflict(path, diameterMm, board, obstacles) {
        const radius = num(diameterMm) / 2;
        const blocks = obstacles || [];
        for (let index = 0; index < path.length - 1; index += 1) {
            const start = path[index];
            const end = path[index + 1];
            for (let obstacleIndex = 0; obstacleIndex < blocks.length; obstacleIndex += 1) {
                const ring = obstacleRing(blocks[obstacleIndex]);
                if (ring.length < 3) continue;
                if (pointInPolygon(start, ring) || pointInPolygon(end, ring)) {
                    return "liner_extension_hits_piece";
                }
                const crossing = ring.some((corner, cornerIndex) => segmentsCross(
                    start,
                    end,
                    corner,
                    ring[(cornerIndex + 1) % ring.length]
                ));
                if (crossing) return "liner_extension_hits_piece";
                const gap = Math.min(
                    ...ring.map(corner => pointSegDist(corner, start, end)),
                    ...ring.map((corner, cornerIndex) => Math.min(
                        pointSegDist(start, corner, ring[(cornerIndex + 1) % ring.length]),
                        pointSegDist(end, corner, ring[(cornerIndex + 1) % ring.length])
                    ))
                );
                if (gap < radius - TOLERANCE_MM) return "liner_extension_hits_piece";
            }
        }
        return "";
    }

    function obstacleRing(obstacle) {
        if (obstacle && Array.isArray(obstacle.polygon) && obstacle.polygon.length >= 3) {
            return obstacle.polygon;
        }
        const rect = obstacle || {};
        return [
            [num(rect.minX), num(rect.minY)],
            [num(rect.maxX), num(rect.minY)],
            [num(rect.maxX), num(rect.maxY)],
            [num(rect.minX), num(rect.maxY)],
        ];
    }

    function placedPolygonMm(piece) {
        const linerPiece = pieceFromRow(piece);
        const polygon = piecePolygonMm(linerPiece);
        if (!polygon) return [];
        const turns = piece && piece.rotated ? 1 : 0;
        const mirrored = Boolean(piece && piece.corner_mirrored);
        const originX = num(piece && piece.x) * 10;
        const originY = num(piece && piece.y) * 10;
        return polygon.map(point => {
            const placed = transformPoint(
                point,
                mirrored,
                turns,
                linerPiece.widthCm * 10,
                linerPiece.lengthCm * 10
            );
            return [placed[0] + originX, placed[1] + originY];
        });
    }

    function transformPoint(point, mirrored, quarterTurns, width, height) {
        let x = point[0];
        let y = point[1];
        let boxWidth = width;
        let boxHeight = height;
        if (mirrored) x = boxWidth - x;
        const turns = ((Number(quarterTurns) % 4) + 4) % 4;
        for (let index = 0; index < turns; index += 1) {
            const nextX = boxHeight - y;
            y = x;
            x = nextX;
            const swap = boxWidth;
            boxWidth = boxHeight;
            boxHeight = swap;
        }
        return [x, y];
    }

    function roundMm(value) {
        return Math.round(value * 1000) / 1000;
    }

    function linerRequested(piece) {
        return Boolean(String(piece && piece.liner_reference_side || "").trim())
            && num(piece && piece.liner_width_cm) > 0;
    }

    function placeLocalPath(piece, linerPiece, local) {
        const turns = piece.rotated ? 1 : 0;
        const mirrored = Boolean(piece.corner_mirrored);
        const originX = num(piece.x) * 10;
        const originY = num(piece.y) * 10;
        return local.map(point => {
            const placed = transformPoint(
                point,
                mirrored,
                turns,
                linerPiece.widthCm * 10,
                linerPiece.lengthCm * 10
            );
            return [roundMm(placed[0] + originX), roundMm(placed[1] + originY)];
        });
    }

    function linerOverlayGate(piece) {
        if (!piece) return null;
        const overlays = Array.isArray(piece.overlays) ? piece.overlays : [];
        if (overlays.some(overlay => overlay && overlay.kind === "liner")) return null;
        if (piece.geometry && Array.isArray(piece.geometry.outer) && overlays.length) return null;
        if (!linerRequested(piece)) return null;
        return pieceFromRow(piece);
    }

    function visualCenterline(piece) {
        if (!linerRequested(piece)) return null;
        const linerPiece = pieceFromRow(piece);
        let local;
        try {
            local = centerlineMm(
                linerPiece,
                piece.liner_reference_side,
                piece.liner_offset_cm,
                piece.liner_width_cm,
                piece.liner_start_cm,
                piece.liner_length_cm
            );
        } catch (error) {
            return {
                kind: "liner",
                layer: "Liner",
                synthetic: true,
                error: error.code || "liner_extension_unsafe",
            };
        }
        return {
            kind: "liner",
            layer: "Liner",
            synthetic: true,
            geometry: {
                schema_version: 1,
                unit: "mm",
                coordinate_space: "usable_sheet",
                closed: false,
                toolpath: false,
                path: placeLocalPath(piece, linerPiece, local),
            },
        };
    }

    function centerlineOverlay(piece) {
        const linerPiece = linerOverlayGate(piece);
        if (!linerPiece) return null;
        let local;
        try {
            local = centerlineMm(
                linerPiece,
                piece.liner_reference_side,
                piece.liner_offset_cm,
                piece.liner_width_cm,
                piece.liner_start_cm,
                piece.liner_length_cm
            );
        } catch (error) {
            return {
                kind: "liner",
                layer: "Liner",
                synthetic: true,
                error: error.code || "liner_extension_unsafe",
            };
        }
        return {
            kind: "liner",
            layer: "Liner",
            synthetic: true,
            geometry: {
                schema_version: 1,
                unit: "mm",
                coordinate_space: "usable_sheet",
                closed: false,
                toolpath: false,
                path: placeLocalPath(piece, linerPiece, local),
            },
        };
    }

    function syntheticOverlay(piece) {
        const linerPiece = linerOverlayGate(piece);
        if (!linerPiece) return null;
        const diameter = num(piece.kerf_mm);
        if (!(diameter > TOLERANCE_MM)) {
            return { kind: "liner", layer: "Liner", synthetic: true, error: "cutter_diameter_invalid" };
        }
        let local;
        try {
            const ends = piece.board ? sawnBoundaryEnds(piece, linerPiece, piece.board) : null;
            local = toolpathMm(
                linerPiece,
                piece.liner_reference_side,
                piece.liner_offset_cm,
                piece.liner_width_cm,
                diameter,
                piece.liner_start_cm,
                piece.liner_length_cm,
                ends
            );
        } catch (error) {
            return {
                kind: "liner",
                layer: "Liner",
                synthetic: true,
                error: error.code || "liner_extension_unsafe",
            };
        }
        return {
            kind: "liner",
            layer: "Liner",
            synthetic: true,
            geometry: {
                schema_version: 1,
                unit: "mm",
                coordinate_space: "usable_sheet",
                closed: false,
                toolpath: true,
                path: placeLocalPath(piece, linerPiece, local),
            },
        };
    }

    function contourNotchFromOrder(frm, row) {
        const source = row || {};
        const banding = window.AlmdinaMultiEdgeBanding;
        const calculated = banding && typeof banding.calculate === "function"
            ? banding.calculate(frm, source)
            : null;
        const sides = (calculated && calculated.sides) || {};
        const thickness = {};
        ["long_right", "long_left", "width_top", "width_bottom"].forEach(side => {
            thickness[side] = sides[side] && sides[side].selected ? num(sides[side].thickness) : 0;
        });
        const typeName = source.edge_type || (frm && frm.doc && frm.doc.default_edge_type) || "";
        let inner = null;
        if (!Number(source.edge_break)) inner = 0;
        else if (banding && typeof banding.thicknessForType === "function") {
            inner = banding.thicknessForType(frm, typeName);
        }
        return contourNotchCm({
            pieceType: source.piece_type,
            notchWidthCm: source.clipped_corner_width_cm,
            notchLengthCm: source.clipped_corner_length_cm,
            position: source.clipped_corner_position,
            sideThicknessMm: thickness,
            edgeBreak: Boolean(Number(source.edge_break)),
            innerMm: inner,
        });
    }

    function summary(row) {
        if (!row || !Number(row.extra_liner) || !row.liner_reference_side) return "";
        const piece = pieceFromRow(row);
        return `${sideLabel(row.liner_reference_side, piece.pieceType)} · ${num(row.liner_offset_cm)} / ${num(row.liner_width_cm)} سم`;
    }

    window.AlmdinaLinerGeometry = Object.freeze({
        availableSides,
        sideLabel,
        pieceFromRow,
        piecePolygonMm,
        edgePaths,
        validationCode,
        stripPolygonMm,
        cutterCenterOffsetsMm,
        centerlineMm,
        toolpathMm,
        extensionConflict,
        placedPolygonMm,
        contourNotchCm,
        contourNotchFromOrder,
        transformPoint,
        centerlineOverlay,
        visualCenterline,
        syntheticOverlay,
        summary,
    });
})();
