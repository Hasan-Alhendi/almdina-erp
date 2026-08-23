(() => {
    "use strict";

    const DOCUMENTATION_SCHEMA = "almdina.special-shape-documentation";
    const DRAWING_VERSION = 1;
    const PARSE_CACHE_LIMIT = 300;
    const drawingCache = new Map();

    function geometry() {
        return window.AlmdinaSpecialShapeGeometry || null;
    }

    function deepFreeze(value) {
        if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
        Object.values(value).forEach(deepFreeze);
        return Object.freeze(value);
    }

    function cloneJson(value) {
        try {
            return JSON.parse(JSON.stringify(value));
        } catch (error) {
            return null;
        }
    }

    function cacheDrawing(raw, payload) {
        drawingCache.set(raw, payload);
        if (drawingCache.size > PARSE_CACHE_LIMIT) {
            drawingCache.delete(drawingCache.keys().next().value);
        }
        return payload;
    }

    function parseDrawing(raw) {
        if (!raw) return null;
        if (typeof raw === "string" && drawingCache.has(raw)) {
            return drawingCache.get(raw);
        }
        try {
            const source = typeof raw === "string" ? JSON.parse(raw) : cloneJson(raw);
            if (
                !source
                || typeof source !== "object"
                || Array.isArray(source)
                || source.schema !== DOCUMENTATION_SCHEMA
                || Number(source.version) !== DRAWING_VERSION
                || !Array.isArray(source.elements)
            ) {
                return null;
            }
            const payload = deepFreeze(source);
            return typeof raw === "string" ? cacheDrawing(raw, payload) : payload;
        } catch (error) {
            return null;
        }
    }

    function parseGeometry(raw) {
        const module = geometry();
        if (!module) return null;
        const parsed = module.parse(raw);
        if (!parsed || Object.isFrozen(parsed)) return parsed;
        return module.parse(JSON.stringify(parsed));
    }

    function drawingFromPiece(piece) {
        const payload = parseDrawing(piece && (
            piece.special_shape_drawing_json
            || piece.drawing_json
        ));
        return payload && (payload.reference || payload.elements.length) ? payload : null;
    }

    function geometryFromPiece(piece) {
        const payload = parseGeometry(piece && (
            piece.special_shape_geometry_json
            || piece.geometry_json
        ));
        return payload && payload.points.length >= 3 ? payload : null;
    }

    function canonicalGeometryPiece(piece) {
        if (!piece || piece.special_shape_geometry_json || !piece.geometry_json) return piece;
        return {
            ...piece,
            special_shape_geometry_json: piece.geometry_json,
        };
    }

    function visual(piece) {
        const drawing = drawingFromPiece(piece);
        if (drawing) {
            return Object.freeze({ kind: "documentation", payload: drawing });
        }
        const polygon = geometryFromPiece(piece);
        return polygon
            ? Object.freeze({ kind: "geometry", payload: polygon })
            : null;
    }

    function hasVisual(piece) {
        return Boolean(visual(piece));
    }

    function hasExactCutPath(piece) {
        const module = geometry();
        return Boolean(
            module
            && module.isExact(canonicalGeometryPiece(piece))
        );
    }

    function pointsAttribute(piece, width = 100, height = 100) {
        const module = geometry();
        const canonical = canonicalGeometryPiece(piece);
        return module && module.isExact(canonical)
            ? module.pointsAttribute(canonical, width, height)
            : "";
    }

    function dxfPoints(piece, x, y, width, height) {
        const module = geometry();
        const canonical = canonicalGeometryPiece(piece);
        return module && module.isExact(canonical)
            ? module.dxfPoints(canonical, x, y, width, height)
            : [];
    }

    window.AlmdinaShapeOutputContract = Object.freeze({
        DOCUMENTATION_SCHEMA,
        DRAWING_VERSION,
        parseDrawing,
        parseGeometry,
        drawingFromPiece,
        geometryFromPiece,
        visual,
        hasVisual,
        hasExactCutPath,
        pointsAttribute,
        dxfPoints,
    });
})();
