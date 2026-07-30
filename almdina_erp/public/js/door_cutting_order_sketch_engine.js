(() => {
    "use strict";

    const DEFAULT_CANVAS = Object.freeze({ width: 1000, height: 650 });
    const DEFAULT_ERASER_RADIUS = 14;
    const MIN_ERASER_RADIUS = 8;
    const MAX_ERASER_RADIUS = 36;
    const DEFAULT_SNAP_RADIUS = 18;

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function pointDistance(first, second) {
        return Math.hypot(second[0] - first[0], second[1] - first[1]);
    }

    function sanitizePoints(points) {
        return (points || [])
            .map(point => [Number(point && point[0]), Number(point && point[1])])
            .filter(point => Number.isFinite(point[0]) && Number.isFinite(point[1]));
    }

    function removeCrowdedPoints(points, minimumDistance = 1.8) {
        const source = sanitizePoints(points);
        if (source.length < 3) return source;
        const result = [source[0]];
        for (let index = 1; index < source.length - 1; index += 1) {
            if (pointDistance(result[result.length - 1], source[index]) >= minimumDistance) {
                result.push(source[index]);
            }
        }
        const last = source[source.length - 1];
        if (pointDistance(result[result.length - 1], last) >= 0.35) {
            result.push(last);
        } else if (result.length > 1) {
            result[result.length - 1] = last;
        }
        return result;
    }

    function pointSegmentDistance(point, start, end) {
        const dx = end[0] - start[0];
        const dy = end[1] - start[1];
        const lengthSquared = dx * dx + dy * dy;
        if (!lengthSquared) return pointDistance(point, start);
        const ratio = Math.max(0, Math.min(
            1,
            ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / lengthSquared
        ));
        return Math.hypot(
            point[0] - (start[0] + ratio * dx),
            point[1] - (start[1] + ratio * dy)
        );
    }

    function densifyPolyline(points, maximumStep = 4) {
        const source = sanitizePoints(points);
        if (source.length < 2) return source;
        const result = [source[0]];
        for (let index = 1; index < source.length; index += 1) {
            const start = source[index - 1];
            const end = source[index];
            const distance = pointDistance(start, end);
            const steps = Math.max(1, Math.ceil(distance / Math.max(1, maximumStep)));
            for (let step = 1; step <= steps; step += 1) {
                const ratio = step / steps;
                result.push([
                    start[0] + (end[0] - start[0]) * ratio,
                    start[1] + (end[1] - start[1]) * ratio,
                ]);
            }
        }
        return result;
    }

    function simplifyPolyline(points, tolerance) {
        if (points.length < 3) return points.slice();
        const keep = new Array(points.length).fill(false);
        const stack = [[0, points.length - 1]];
        keep[0] = true;
        keep[points.length - 1] = true;

        while (stack.length) {
            const [startIndex, endIndex] = stack.pop();
            let furthestIndex = -1;
            let furthestDistance = tolerance;
            for (let index = startIndex + 1; index < endIndex; index += 1) {
                const distance = pointSegmentDistance(
                    points[index],
                    points[startIndex],
                    points[endIndex]
                );
                if (distance > furthestDistance) {
                    furthestDistance = distance;
                    furthestIndex = index;
                }
            }
            if (furthestIndex >= 0) {
                keep[furthestIndex] = true;
                stack.push([startIndex, furthestIndex], [furthestIndex, endIndex]);
            }
        }
        return points.filter((point, index) => keep[index]);
    }

    function compactEraserFragment(points) {
        const spaced = removeCrowdedPoints(points, 1);
        if (
            spaced.length < 2
            || pointDistance(spaced[0], spaced[spaced.length - 1]) < 1.5
        ) {
            return [];
        }
        return simplifyPolyline(spaced, 0.8);
    }

    function erasePenStroke(
        element,
        eraserStart,
        eraserEnd,
        radius = DEFAULT_ERASER_RADIUS,
        createId = null
    ) {
        const safeRadius = Math.max(
            MIN_ERASER_RADIUS,
            Math.min(MAX_ERASER_RADIUS, Number(radius) || DEFAULT_ERASER_RADIUS)
        );
        const source = densifyPolyline(
            element && element.points,
            Math.max(2, safeRadius / 3)
        );
        if (source.length < 2) return { changed: false, fragments: [element] };

        const keep = source.map(point =>
            pointSegmentDistance(point, eraserStart, eraserEnd) > safeRadius
        );
        if (keep.every(Boolean)) return { changed: false, fragments: [element] };

        const groups = [];
        let current = [];
        source.forEach((point, index) => {
            if (keep[index]) {
                current.push(point);
            } else if (current.length) {
                groups.push(current);
                current = [];
            }
        });
        if (current.length) groups.push(current);

        const nextId = typeof createId === "function"
            ? createId
            : index => `${String(element && element.id || "pen")}-fragment-${index}`;
        const fragments = groups
            .map(compactEraserFragment)
            .filter(points => points.length >= 2)
            .map((points, index) => ({
                ...element,
                id: index === 0 ? element.id : nextId(index),
                points,
            }));
        return { changed: true, fragments };
    }

    function fitNearlyStraightLine(points) {
        if (points.length < 2) return null;
        const first = points[0];
        const last = points[points.length - 1];
        if (pointDistance(first, last) < 12) return null;

        const center = points.reduce(
            (sum, point) => [sum[0] + point[0], sum[1] + point[1]],
            [0, 0]
        ).map(value => value / points.length);
        let xx = 0;
        let xy = 0;
        let yy = 0;
        points.forEach(point => {
            const dx = point[0] - center[0];
            const dy = point[1] - center[1];
            xx += dx * dx;
            xy += dx * dy;
            yy += dy * dy;
        });

        const angle = 0.5 * Math.atan2(2 * xy, xx - yy);
        let ux = Math.cos(angle);
        let uy = Math.sin(angle);
        if ((last[0] - first[0]) * ux + (last[1] - first[1]) * uy < 0) {
            ux *= -1;
            uy *= -1;
        }

        const projections = [];
        const deviations = [];
        let minimumProjection = Infinity;
        let maximumProjection = -Infinity;
        points.forEach(point => {
            const dx = point[0] - center[0];
            const dy = point[1] - center[1];
            const projection = dx * ux + dy * uy;
            const deviation = Math.abs(-dx * uy + dy * ux);
            projections.push(projection);
            deviations.push(deviation);
            minimumProjection = Math.min(minimumProjection, projection);
            maximumProjection = Math.max(maximumProjection, projection);
        });

        const span = maximumProjection - minimumProjection;
        if (span < 12) return null;
        const rmsDeviation = Math.sqrt(
            deviations.reduce((sum, value) => sum + value * value, 0) / deviations.length
        );
        const maximumDeviation = Math.max(...deviations);
        const rmsLimit = Math.max(3.5, Math.min(7, span * 0.018 + 1.5));
        const maximumLimit = Math.max(8, Math.min(16, span * 0.032 + 2));
        let backwardsDistance = 0;
        for (let index = 1; index < projections.length; index += 1) {
            backwardsDistance += Math.max(0, projections[index - 1] - projections[index]);
        }
        if (
            rmsDeviation > rmsLimit
            || maximumDeviation > maximumLimit
            || backwardsDistance > Math.max(7, span * 0.09)
        ) {
            return null;
        }

        let start = [
            center[0] + minimumProjection * ux,
            center[1] + minimumProjection * uy,
        ];
        let end = [
            center[0] + maximumProjection * ux,
            center[1] + maximumProjection * uy,
        ];
        const axisSnapAngle = 7 * Math.PI / 180;
        const absoluteAngle = Math.abs(Math.atan2(uy, ux));
        const horizontalAngle = Math.min(absoluteAngle, Math.abs(Math.PI - absoluteAngle));
        const verticalAngle = Math.abs(Math.PI / 2 - absoluteAngle);
        if (horizontalAngle <= axisSnapAngle) {
            start = [start[0], center[1]];
            end = [end[0], center[1]];
        } else if (verticalAngle <= axisSnapAngle) {
            start = [center[0], start[1]];
            end = [center[0], end[1]];
        }
        return [start, end];
    }

    function smoothCorners(points) {
        if (points.length < 3) return points.slice();
        const result = [points[0]];
        for (let index = 1; index < points.length - 1; index += 1) {
            const previous = points[index - 1];
            const current = points[index];
            const next = points[index + 1];
            const incomingLength = pointDistance(previous, current);
            const outgoingLength = pointDistance(current, next);
            if (!incomingLength || !outgoingLength) {
                result.push(current);
                continue;
            }
            const directionCosine = (
                (current[0] - previous[0]) * (next[0] - current[0])
                + (current[1] - previous[1]) * (next[1] - current[1])
            ) / (incomingLength * outgoingLength);
            if (directionCosine < 0.72) {
                result.push(current);
                continue;
            }
            result.push([
                previous[0] * 0.2 + current[0] * 0.6 + next[0] * 0.2,
                previous[1] * 0.2 + current[1] * 0.6 + next[1] * 0.2,
            ]);
        }
        result.push(points[points.length - 1]);
        return result;
    }

    function normalizePenStroke(points) {
        const spaced = removeCrowdedPoints(points);
        if (spaced.length < 2) return spaced;

        const straightLine = fitNearlyStraightLine(spaced);
        if (straightLine) return straightLine;
        if (spaced.length < 3) return spaced;

        let result = simplifyPolyline(spaced, 2.1);
        result = smoothCorners(result);
        result = smoothCorners(result);
        return simplifyPolyline(result, 1.15);
    }

    function elementAnchorPoints(element) {
        if (!element) return [];
        if (element.type === "pen") {
            const points = sanitizePoints(element.points);
            return points.length > 1 ? [points[0], points[points.length - 1]] : points;
        }
        if (element.type === "line" || element.type === "dimension") {
            return [
                [Number(element.x1), Number(element.y1)],
                [Number(element.x2), Number(element.y2)],
            ];
        }
        if (element.type === "rectangle") {
            const x = Number(element.x);
            const y = Number(element.y);
            const width = Number(element.width);
            const height = Number(element.height);
            return [[x, y], [x + width, y], [x, y + height], [x + width, y + height]];
        }
        if (element.type === "ellipse") {
            const cx = Number(element.cx);
            const cy = Number(element.cy);
            const rx = Number(element.rx);
            const ry = Number(element.ry);
            return [[cx - rx, cy], [cx + rx, cy], [cx, cy - ry], [cx, cy + ry]];
        }
        return [];
    }

    function nearestAnchor(point, elements, radius = DEFAULT_SNAP_RADIUS) {
        let nearest = null;
        let nearestDistance = Number(radius);
        (elements || []).forEach(element => {
            elementAnchorPoints(element).forEach(anchor => {
                const distance = pointDistance(point, anchor);
                if (distance <= nearestDistance) {
                    nearestDistance = distance;
                    nearest = anchor;
                }
            });
        });
        return nearest ? [nearest[0], nearest[1]] : null;
    }

    function snapLineEnd(start, end, forceAngle = false) {
        const dx = Number(end.x) - Number(start.x);
        const dy = Number(end.y) - Number(start.y);
        const length = Math.hypot(dx, dy);
        if (length < 0.001) return { x: Number(end.x), y: Number(end.y) };
        const angle = Math.atan2(dy, dx);
        const interval = forceAngle ? Math.PI / 12 : Math.PI / 2;
        const snappedAngle = Math.round(angle / interval) * interval;
        const difference = Math.abs(Math.atan2(
            Math.sin(angle - snappedAngle),
            Math.cos(angle - snappedAngle)
        ));
        if (!forceAngle && difference > 7 * Math.PI / 180) {
            return { x: Number(end.x), y: Number(end.y) };
        }
        return {
            x: Number(start.x) + Math.cos(snappedAngle) * length,
            y: Number(start.y) + Math.sin(snappedAngle) * length,
        };
    }

    function polylineLength(points) {
        let length = 0;
        for (let index = 1; index < points.length; index += 1) {
            length += pointDistance(points[index - 1], points[index]);
        }
        return length;
    }

    function snapPenEndpoints(points, elements, radius = DEFAULT_SNAP_RADIUS) {
        const result = sanitizePoints(points).map(point => point.slice());
        if (result.length < 2) return result;
        const firstAnchor = nearestAnchor(result[0], elements, radius);
        if (firstAnchor) result[0] = firstAnchor;
        const lastIndex = result.length - 1;
        const lastAnchor = nearestAnchor(result[lastIndex], elements, radius);
        if (lastAnchor) result[lastIndex] = lastAnchor;
        if (
            result.length >= 3
            && polylineLength(result) >= 70
            && pointDistance(result[0], result[lastIndex]) <= radius * 1.35
        ) {
            result[lastIndex] = result[0].slice();
        }
        return result;
    }

    function templatePoints(template) {
        if (template === "single-slope") {
            return [[340, 150], [750, 150], [750, 500], [250, 500], [340, 150]];
        }
        if (template === "double-clipped") {
            return [[340, 150], [660, 150], [750, 240], [750, 500], [250, 500], [250, 240], [340, 150]];
        }
        if (template === "clipped-corner" || template === "angled") {
            return [[250, 155], [750, 155], [750, 500], [430, 500], [250, 320], [250, 155]];
        }
        if (template === "lshape") {
            return [[250, 150], [750, 150], [750, 500], [500, 500], [500, 330], [250, 330], [250, 150]];
        }
        if (template === "trapezoid") {
            return [[340, 150], [710, 150], [790, 500], [210, 500], [340, 150]];
        }
        if (template === "arch") {
            const points = [[280, 500], [280, 300]];
            for (let index = 0; index <= 24; index += 1) {
                const angle = Math.PI - Math.PI * index / 24;
                points.push([
                    500 + Math.cos(angle) * 220,
                    300 - Math.sin(angle) * 220,
                ]);
            }
            points.push([720, 500], [280, 500]);
            return points;
        }
        return [];
    }

    function normalizeCanvas(options = {}) {
        return {
            width: Number(options.width) > 0 ? Number(options.width) : DEFAULT_CANVAS.width,
            height: Number(options.height) > 0 ? Number(options.height) : DEFAULT_CANVAS.height,
        };
    }

    function translateElement(element, dx, dy, canvasOptions = {}) {
        const canvas = normalizeCanvas(canvasOptions);
        const moved = clone(element);
        if (moved.type === "pen") {
            moved.points = sanitizePoints(moved.points).map(point => [
                Math.max(0, Math.min(canvas.width, point[0] + dx)),
                Math.max(0, Math.min(canvas.height, point[1] + dy)),
            ]);
        } else if (moved.type === "line" || moved.type === "dimension") {
            moved.x1 = Math.max(0, Math.min(canvas.width, Number(moved.x1) + dx));
            moved.y1 = Math.max(0, Math.min(canvas.height, Number(moved.y1) + dy));
            moved.x2 = Math.max(0, Math.min(canvas.width, Number(moved.x2) + dx));
            moved.y2 = Math.max(0, Math.min(canvas.height, Number(moved.y2) + dy));
        } else if (moved.type === "rectangle") {
            moved.x = Math.max(0, Math.min(
                canvas.width - Number(moved.width),
                Number(moved.x) + dx
            ));
            moved.y = Math.max(0, Math.min(
                canvas.height - Number(moved.height),
                Number(moved.y) + dy
            ));
        } else if (moved.type === "ellipse") {
            moved.cx = Math.max(Number(moved.rx), Math.min(
                canvas.width - Number(moved.rx),
                Number(moved.cx) + dx
            ));
            moved.cy = Math.max(Number(moved.ry), Math.min(
                canvas.height - Number(moved.ry),
                Number(moved.cy) + dy
            ));
        } else if (moved.type === "note") {
            moved.x = Math.max(0, Math.min(canvas.width - 120, Number(moved.x) + dx));
            moved.y = Math.max(31, Math.min(canvas.height, Number(moved.y) + dy));
        }
        return moved;
    }

    function defaultNoteFontSize(value) {
        const numeric = Number(value);
        if (!Number.isFinite(numeric)) return 18;
        return Math.max(12, Math.min(32, Math.round(numeric)));
    }

    function elementBounds(element, options = {}) {
        if (!element) return null;
        if (element.type === "pen") {
            const points = sanitizePoints(element.points);
            if (!points.length) return null;
            const xs = points.map(point => point[0]);
            const ys = points.map(point => point[1]);
            return {
                x: Math.min(...xs),
                y: Math.min(...ys),
                width: Math.max(...xs) - Math.min(...xs),
                height: Math.max(...ys) - Math.min(...ys),
            };
        }
        if (element.type === "line" || element.type === "dimension") {
            return {
                x: Math.min(Number(element.x1), Number(element.x2)),
                y: Math.min(Number(element.y1), Number(element.y2))
                    - (element.type === "dimension" ? 35 : 0),
                width: Math.abs(Number(element.x2) - Number(element.x1)),
                height: Math.abs(Number(element.y2) - Number(element.y1))
                    + (element.type === "dimension" ? 35 : 0),
            };
        }
        if (element.type === "rectangle") {
            return {
                x: Number(element.x),
                y: Number(element.y),
                width: Number(element.width),
                height: Number(element.height),
            };
        }
        if (element.type === "ellipse") {
            return {
                x: Number(element.cx) - Number(element.rx),
                y: Number(element.cy) - Number(element.ry),
                width: Number(element.rx) * 2,
                height: Number(element.ry) * 2,
            };
        }
        if (element.type === "note") {
            const resolveFontSize = typeof options.noteFontSize === "function"
                ? options.noteFontSize
                : defaultNoteFontSize;
            const text = String(element.text || "");
            const fontSize = resolveFontSize(element.font_size || element.fontSize);
            const width = Math.min(
                460,
                Math.max(fontSize * 2, Math.min(34, text.length) * fontSize * 0.62)
            );
            const x = Number(element.x);
            const anchor = element.text_anchor === "middle" ? "middle" : "end";
            return {
                x: anchor === "middle" ? x - width / 2 : x - width,
                y: Number(element.y) - fontSize * 0.7,
                width,
                height: fontSize * 1.4,
            };
        }
        return null;
    }

    function clampViewBox(viewBox, options = {}) {
        const canvas = normalizeCanvas(options);
        const maxZoom = Number(options.maxZoom) > 1 ? Number(options.maxZoom) : 4;
        const width = Math.max(
            canvas.width / maxZoom,
            Math.min(canvas.width, viewBox.width)
        );
        const height = Math.max(
            canvas.height / maxZoom,
            Math.min(canvas.height, viewBox.height)
        );
        return {
            x: Math.max(0, Math.min(canvas.width - width, Number(viewBox.x) || 0)),
            y: Math.max(0, Math.min(canvas.height - height, Number(viewBox.y) || 0)),
            width,
            height,
        };
    }

    window.AlmdinaSketchEngine = Object.freeze({
        DEFAULT_CANVAS,
        DEFAULT_ERASER_RADIUS,
        MIN_ERASER_RADIUS,
        MAX_ERASER_RADIUS,
        DEFAULT_SNAP_RADIUS,
        pointDistance,
        sanitizePoints,
        removeCrowdedPoints,
        pointSegmentDistance,
        densifyPolyline,
        simplifyPolyline,
        erasePenStroke,
        fitNearlyStraightLine,
        smoothCorners,
        normalizePenStroke,
        elementAnchorPoints,
        nearestAnchor,
        snapLineEnd,
        polylineLength,
        snapPenEndpoints,
        templatePoints,
        translateElement,
        elementBounds,
        clampViewBox,
    });
})();
