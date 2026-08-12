(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    if (!G) throw new Error("Door Drawing V3 geometry must load before shape handles");

    function freezeHandle(role, point, kind = "resize", axis = null) {
        return Object.freeze({
            role: String(role || "point"),
            kind: String(kind || "resize"),
            axis: axis === "horizontal" || axis === "vertical" ? axis : null,
            point: G.point(point && point.x, point && point.y),
        });
    }

    function rectangleCorners(object) {
        const g = object.geometry;
        const left = g.origin.x;
        const bottom = g.origin.y;
        const right = left + g.widthMm;
        const top = bottom + g.heightMm;
        return Object.freeze({
            "bottom-left": G.point(left, bottom),
            "bottom-right": G.point(right, bottom),
            "top-right": G.point(right, top),
            "top-left": G.point(left, top),
        });
    }

    function oppositeRectangleRole(role) {
        return {
            "bottom-left": "top-right",
            "bottom-right": "top-left",
            "top-right": "bottom-left",
            "top-left": "bottom-right",
        }[role] || null;
    }

    function handlesFor(object) {
        if (!object || !object.geometry) return Object.freeze([]);
        const g = object.geometry;
        if (object.type === "line") {
            return Object.freeze([
                freezeHandle("start", g.start),
                freezeHandle("end", g.end),
            ]);
        }
        if (object.type === "rectangle") {
            const corners = rectangleCorners(object);
            return Object.freeze([
                freezeHandle("bottom-left", corners["bottom-left"]),
                freezeHandle("bottom-right", corners["bottom-right"]),
                freezeHandle("top-right", corners["top-right"]),
                freezeHandle("top-left", corners["top-left"]),
            ]);
        }
        if (object.type === "circle") {
            const c = g.center;
            const r = g.radiusMm;
            return Object.freeze([
                freezeHandle("center", c, "move"),
                freezeHandle("east", G.point(c.x + r, c.y), "radius", "horizontal"),
                freezeHandle("north", G.point(c.x, c.y + r), "radius", "vertical"),
                freezeHandle("west", G.point(c.x - r, c.y), "radius", "horizontal"),
                freezeHandle("south", G.point(c.x, c.y - r), "radius", "vertical"),
            ]);
        }
        if (object.type === "arc") {
            return Object.freeze([
                freezeHandle("center", g.center, "move"),
                freezeHandle("start", G.arcStart(object), "arc-endpoint"),
                freezeHandle("end", G.arcEnd(object), "arc-endpoint"),
                freezeHandle("radius", G.arcMid(object), "radius"),
            ]);
        }
        return Object.freeze([]);
    }

    function handleByRole(object, role) {
        return handlesFor(object).find(handle => handle.role === String(role || "")) || null;
    }

    function signedSweep(startAngleDeg, endAngleDeg, sign) {
        const positive = G.positiveAngle(endAngleDeg - startAngleDeg);
        if (sign < 0) {
            const clockwise = G.positiveAngle(startAngleDeg - endAngleDeg);
            return -(clockwise <= G.MIN_ARC_SWEEP_DEG ? G.MIN_ARC_SWEEP_DEG : clockwise);
        }
        return positive <= G.MIN_ARC_SWEEP_DEG ? G.MIN_ARC_SWEEP_DEG : positive;
    }

    function resizeRectangle(object, role, candidate, square = false) {
        const oppositeRole = oppositeRectangleRole(role);
        if (!oppositeRole) throw new Error("Unsupported rectangle handle");
        const opposite = rectangleCorners(object)[oppositeRole];
        return G.rectangleFromPoints(object.id, opposite, candidate, Boolean(square), object.style);
    }

    function resizeCircle(object, role, candidate) {
        if (role === "center") {
            return G.setCircle(object, { cx: candidate.x, cy: candidate.y });
        }
        if (!["east", "north", "west", "south"].includes(role)) throw new Error("Unsupported circle handle");
        const radius = G.distance(object.geometry.center, candidate);
        return G.setCircle(object, { radiusMm: radius });
    }

    function resizeArc(object, role, candidate) {
        const g = object.geometry;
        if (role === "center") {
            return G.setArc(object, { cx: candidate.x, cy: candidate.y });
        }
        if (role === "radius") {
            return G.setArc(object, { radiusMm: G.distance(g.center, candidate) });
        }
        if (role === "start") {
            const endAngle = g.startAngleDeg + g.sweepAngleDeg;
            const nextStart = G.angleDeg(g.center, candidate);
            return G.setArc(object, {
                startAngleDeg: nextStart,
                sweepAngleDeg: signedSweep(nextStart, endAngle, Math.sign(g.sweepAngleDeg) || 1),
            });
        }
        if (role === "end") {
            const nextEnd = G.angleDeg(g.center, candidate);
            return G.setArc(object, {
                sweepAngleDeg: signedSweep(g.startAngleDeg, nextEnd, Math.sign(g.sweepAngleDeg) || 1),
            });
        }
        throw new Error("Unsupported arc handle");
    }

    function resize(object, role, candidate, options = {}) {
        const point = G.point(candidate && candidate.x, candidate && candidate.y);
        if (!object || !object.geometry) throw new Error("Expected a drawing object");
        if (object.type === "line") return G.setLineEndpoint(object, role, point);
        if (object.type === "rectangle") return resizeRectangle(object, role, point, Boolean(options.square));
        if (object.type === "circle") return resizeCircle(object, role, point);
        if (object.type === "arc") return resizeArc(object, role, point);
        throw new Error("Unsupported drawing object");
    }

    root.ShapeHandles = Object.freeze({
        handlesFor,
        handleByRole,
        rectangleCorners,
        oppositeRectangleRole,
        resize,
        resizeRectangle,
        resizeCircle,
        resizeArc,
    });
})();
