(() => {
    "use strict";

    if (window.AlmdinaCuttingPlanPieceGeometry) return;

    const MODEL_VERSION = 1;
    const DXF_SCHEMA_VERSION = 1;
    const DXF_UNIT = "mm";
    const DXF_COORDINATE_SPACE = "usable_sheet";
    const VIEWBOX_SIZE = 100;
    const EPSILON = 1e-6;

    function number(value) {
        const result = Number(value);
        return Number.isFinite(result) ? result : 0;
    }

    function rounded(value, precision = 4) {
        const factor = 10 ** precision;
        return Math.round(number(value) * factor) / factor;
    }

    function finitePoint(value, field) {
        if (
            !Array.isArray(value)
            || value.length !== 2
            || !Number.isFinite(Number(value[0]))
            || !Number.isFinite(Number(value[1]))
        ) {
            throw new Error(`${field} must be a finite [x, y] point.`);
        }
        return [Number(value[0]), Number(value[1])];
    }

    function ring(value, field) {
        if (!Array.isArray(value) || value.length < 3) {
            throw new Error(`${field} must contain at least three points.`);
        }
        const points = value.map((point, index) => finitePoint(point, `${field}[${index}]`));
        if (
            points.length > 3
            && Math.abs(points[0][0] - points[points.length - 1][0]) <= EPSILON
            && Math.abs(points[0][1] - points[points.length - 1][1]) <= EPSILON
        ) {
            points.pop();
        }
        if (points.length < 3) throw new Error(`${field} must contain three distinct points.`);
        return points;
    }

    function geometryBounds(points) {
        let minX = Infinity;
        let minY = Infinity;
        let maxX = -Infinity;
        let maxY = -Infinity;
        points.forEach(point => {
            minX = Math.min(minX, point[0]);
            minY = Math.min(minY, point[1]);
            maxX = Math.max(maxX, point[0]);
            maxY = Math.max(maxY, point[1]);
        });
        const width = maxX - minX;
        const height = maxY - minY;
        if (!(width > EPSILON) || !(height > EPSILON)) {
            throw new Error("Piece geometry must have positive bounds.");
        }
        return { minX, minY, maxX, maxY, width, height };
    }

    function localize(points, bounds) {
        return points.map(point => [point[0] - bounds.minX, point[1] - bounds.minY]);
    }

    function normalizedRing(points, bounds) {
        return points.map(point => [
            rounded(point[0] / bounds.width * VIEWBOX_SIZE),
            rounded(point[1] / bounds.height * VIEWBOX_SIZE),
        ]);
    }

    function ringPath(points) {
        return points
            .map((point, index) => `${index ? "L" : "M"}${rounded(point[0])} ${rounded(point[1])}`)
            .join(" ") + " Z";
    }

    function pathData(outer, holes = []) {
        return [outer, ...holes].map(ringPath).join(" ");
    }

    function pointInRing(point, points) {
        let inside = false;
        for (let index = 0, previous = points.length - 1; index < points.length; previous = index, index += 1) {
            const currentPoint = points[index];
            const previousPoint = points[previous];
            const crosses = (
                (currentPoint[1] > point[1]) !== (previousPoint[1] > point[1])
                && point[0] < (
                    (previousPoint[0] - currentPoint[0])
                    * (point[1] - currentPoint[1])
                    / (previousPoint[1] - currentPoint[1])
                    + currentPoint[0]
                )
            );
            if (crosses) inside = !inside;
        }
        return inside;
    }

    function pointInMaterial(point, outer, holes = []) {
        return pointInRing(point, outer) && !holes.some(hole => pointInRing(point, hole));
    }

    function segmentDistanceSquared(point, start, end) {
        let x = start[0];
        let y = start[1];
        let dx = end[0] - x;
        let dy = end[1] - y;
        if (dx !== 0 || dy !== 0) {
            const ratio = (
                (point[0] - x) * dx + (point[1] - y) * dy
            ) / (dx * dx + dy * dy);
            if (ratio > 1) {
                x = end[0];
                y = end[1];
            } else if (ratio > 0) {
                x += dx * ratio;
                y += dy * ratio;
            }
        }
        dx = point[0] - x;
        dy = point[1] - y;
        return dx * dx + dy * dy;
    }

    function materialDistance(point, outer, holes) {
        let minimum = Infinity;
        [outer, ...holes].forEach(points => {
            for (let index = 0, previous = points.length - 1; index < points.length; previous = index, index += 1) {
                minimum = Math.min(
                    minimum,
                    segmentDistanceSquared(point, points[previous], points[index])
                );
            }
        });
        const distance = Math.sqrt(minimum);
        return pointInMaterial(point, outer, holes) ? distance : -distance;
    }

    function polygonCentroid(points) {
        let area = 0;
        let x = 0;
        let y = 0;
        for (let index = 0, previous = points.length - 1; index < points.length; previous = index, index += 1) {
            const start = points[previous];
            const end = points[index];
            const factor = start[0] * end[1] - end[0] * start[1];
            x += (start[0] + end[0]) * factor;
            y += (start[1] + end[1]) * factor;
            area += factor;
        }
        if (Math.abs(area) <= EPSILON) return [points[0][0], points[0][1]];
        return [x / (3 * area), y / (3 * area)];
    }

    function makeCell(x, y, halfSize, outer, holes) {
        const distance = materialDistance([x, y], outer, holes);
        return {
            x,
            y,
            halfSize,
            distance,
            maximum: distance + halfSize * Math.SQRT2,
        };
    }

    function pushCell(heap, cell) {
        heap.push(cell);
        let index = heap.length - 1;
        while (index > 0) {
            const parent = Math.floor((index - 1) / 2);
            if (heap[parent].maximum >= heap[index].maximum) break;
            [heap[parent], heap[index]] = [heap[index], heap[parent]];
            index = parent;
        }
    }

    function popCell(heap) {
        const first = heap[0];
        const last = heap.pop();
        if (heap.length && last) {
            heap[0] = last;
            let index = 0;
            while (true) {
                const left = index * 2 + 1;
                const right = left + 1;
                let largest = index;
                if (left < heap.length && heap[left].maximum > heap[largest].maximum) largest = left;
                if (right < heap.length && heap[right].maximum > heap[largest].maximum) largest = right;
                if (largest === index) break;
                [heap[index], heap[largest]] = [heap[largest], heap[index]];
                index = largest;
            }
        }
        return first;
    }

    function visualCenter(outer, holes = [], precision = 0.5) {
        const bounds = geometryBounds(outer);
        const cellSize = Math.min(bounds.width, bounds.height);
        const halfSize = cellSize / 2;
        const heap = [];
        for (let x = bounds.minX; x < bounds.maxX; x += cellSize) {
            for (let y = bounds.minY; y < bounds.maxY; y += cellSize) {
                pushCell(heap, makeCell(x + halfSize, y + halfSize, halfSize, outer, holes));
            }
        }

        const centroid = polygonCentroid(outer);
        let best = makeCell(centroid[0], centroid[1], 0, outer, holes);
        const boundsCenter = makeCell(
            bounds.minX + bounds.width / 2,
            bounds.minY + bounds.height / 2,
            0,
            outer,
            holes
        );
        if (boundsCenter.distance > best.distance) best = boundsCenter;

        let iterations = 0;
        while (heap.length && iterations < 10000) {
            iterations += 1;
            const cell = popCell(heap);
            if (cell.distance > best.distance) best = cell;
            if (cell.maximum - best.distance <= precision) continue;
            const nextHalf = cell.halfSize / 2;
            pushCell(heap, makeCell(cell.x - nextHalf, cell.y - nextHalf, nextHalf, outer, holes));
            pushCell(heap, makeCell(cell.x + nextHalf, cell.y - nextHalf, nextHalf, outer, holes));
            pushCell(heap, makeCell(cell.x - nextHalf, cell.y + nextHalf, nextHalf, outer, holes));
            pushCell(heap, makeCell(cell.x + nextHalf, cell.y + nextHalf, nextHalf, outer, holes));
        }
        return [rounded(best.x), rounded(best.y)];
    }

    function isAxisAlignedRectangle(points, holes) {
        if (holes.length || points.length !== 4) return false;
        const bounds = geometryBounds(points);
        return points.every(point => (
            (Math.abs(point[0] - bounds.minX) <= EPSILON || Math.abs(point[0] - bounds.maxX) <= EPSILON)
            && (Math.abs(point[1] - bounds.minY) <= EPSILON || Math.abs(point[1] - bounds.maxY) <= EPSILON)
        )) && points.every((point, index) => {
            const next = points[(index + 1) % points.length];
            return Math.abs(point[0] - next[0]) <= EPSILON || Math.abs(point[1] - next[1]) <= EPSILON;
        });
    }

    function geometryHash(source, outer, holes) {
        const payload = `${source}|${JSON.stringify([outer, ...holes])}`;
        let hash = 2166136261;
        for (let index = 0; index < payload.length; index += 1) {
            hash ^= payload.charCodeAt(index);
            hash = Math.imul(hash, 16777619);
        }
        return `pg-${(hash >>> 0).toString(16)}`;
    }

    function freezeModel(model) {
        model.geometry.outer.forEach(Object.freeze);
        model.geometry.holes.forEach(hole => {
            hole.forEach(Object.freeze);
            Object.freeze(hole);
        });
        Object.freeze(model.geometry.outer);
        Object.freeze(model.geometry.holes);
        Object.freeze(model.geometry.boundsMm);
        Object.freeze(model.geometry);
        Object.freeze(model.placement);
        Object.freeze(model.labelPoint);
        return Object.freeze(model);
    }

    function createModel({ source, outerMm, holesMm = [], placement, exact = false, invalid = false }) {
        const bounds = geometryBounds(outerMm);
        const localOuter = localize(outerMm, bounds);
        const localHoles = holesMm.map(points => localize(points, bounds));
        const localBounds = { minX: 0, minY: 0, maxX: bounds.width, maxY: bounds.height, width: bounds.width, height: bounds.height };
        const outer = normalizedRing(localOuter, localBounds);
        const holes = localHoles.map(points => normalizedRing(points, localBounds));
        const vector = !isAxisAlignedRectangle(outer, holes);
        const labelPoint = vector ? visualCenter(outer, holes) : [50, 50];
        return freezeModel({
            schemaVersion: MODEL_VERSION,
            source,
            exact: Boolean(exact),
            invalid: Boolean(invalid),
            vector,
            geometryIdentity: geometryHash(source, localOuter, localHoles),
            geometry: {
                unit: DXF_UNIT,
                coordinateSpace: "piece_local",
                outer,
                holes,
                boundsMm: localBounds,
                pathData: pathData(outer, holes),
                outerPathData: pathData(outer),
            },
            placement: {
                xCm: number(placement.xCm),
                yCm: number(placement.yCm),
                widthCm: number(placement.widthCm),
                heightCm: number(placement.heightCm),
                rotationDegrees: number(placement.rotationDegrees),
                mirrored: false,
            },
            labelPoint: {
                xPercent: labelPoint[0],
                yPercent: labelPoint[1],
            },
        });
    }

    function piecePlacement(piece) {
        return {
            xCm: number(piece && piece.x),
            yCm: number(piece && piece.y),
            widthCm: number(piece && piece.w),
            heightCm: number(piece && piece.h),
            rotationDegrees: piece && piece.rotated ? 90 : 0,
        };
    }

    function persistedDxfModel(piece) {
        if (!Object.prototype.hasOwnProperty.call(piece || {}, "geometry")) return null;
        const geometry = piece.geometry;
        if (!geometry || typeof geometry !== "object" || Array.isArray(geometry)) {
            throw new Error("Persisted DXF geometry must be an object.");
        }
        if (
            geometry.schema_version !== DXF_SCHEMA_VERSION
            || geometry.unit !== DXF_UNIT
            || geometry.coordinate_space !== DXF_COORDINATE_SPACE
            || !Array.isArray(geometry.holes)
        ) {
            throw new Error("Persisted DXF geometry contract is unsupported.");
        }
        const outerMm = ring(geometry.outer, "geometry.outer");
        const holesMm = geometry.holes.map((hole, index) => ring(hole, `geometry.holes[${index}]`));
        const bounds = geometryBounds(outerMm);
        return createModel({
            source: "dxf",
            outerMm,
            holesMm,
            exact: true,
            placement: {
                xCm: bounds.minX / 10,
                yCm: bounds.minY / 10,
                widthCm: bounds.width / 10,
                heightCm: bounds.height / 10,
                // The accepted DXF contour is already transformed in usable-sheet
                // coordinates. Metadata rotation must never be applied a second time.
                rotationDegrees: 0,
            },
        });
    }

    function manualSpecialModel(piece) {
        const contract = window.AlmdinaShapeOutputContract;
        if (!contract || !contract.hasExactCutPath(piece) || typeof contract.points !== "function") return null;
        const placement = piecePlacement(piece);
        const widthMm = placement.widthCm * 10;
        const heightMm = placement.heightCm * 10;
        if (!(widthMm > 0) || !(heightMm > 0)) return null;
        const outerMm = ring(contract.points(piece, widthMm, heightMm), "special_shape_geometry_json.points");
        return createModel({ source: "manual-special", outerMm, placement, exact: true });
    }

    function cornerModel(piece) {
        const corner = window.AlmdinaClippedCornerGeometry;
        if (!corner || !corner.isCornerCut(piece) || typeof corner.points !== "function") return null;
        const placement = piecePlacement(piece);
        const widthMm = placement.widthCm * 10;
        const heightMm = placement.heightCm * 10;
        if (!(widthMm > 0) || !(heightMm > 0)) return null;
        const outerMm = ring(corner.points(piece, widthMm, heightMm), "corner.points");
        return createModel({ source: "corner", outerMm, placement, exact: true });
    }

    function rectangleModel(piece, options = {}) {
        const placement = piecePlacement(piece);
        const widthMm = Math.max(EPSILON, placement.widthCm * 10);
        const heightMm = Math.max(EPSILON, placement.heightCm * 10);
        return createModel({
            source: options.source || "rectangle",
            exact: false,
            invalid: Boolean(options.invalid),
            placement,
            outerMm: [[0, 0], [widthMm, 0], [widthMm, heightMm], [0, heightMm]],
        });
    }

    function resolve(piece) {
        try {
            const dxf = persistedDxfModel(piece);
            if (dxf) return dxf;
        } catch {
            return rectangleModel(piece, { source: "invalid-dxf", invalid: true });
        }
        return manualSpecialModel(piece) || cornerModel(piece) || rectangleModel(piece);
    }

    window.AlmdinaCuttingPlanPieceGeometry = Object.freeze({
        MODEL_VERSION,
        DXF_SCHEMA_VERSION,
        DXF_UNIT,
        DXF_COORDINATE_SPACE,
        resolve,
        pathData,
        pointInMaterial,
        visualCenter,
    });
})();
