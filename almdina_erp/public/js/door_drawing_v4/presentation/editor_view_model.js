(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);
    const geometry = root.Geometry;
    const dimensionDomain = root.DimensionDomain;
    if (!geometry || !dimensionDomain) throw new Error("Drawing V4 geometry and dimension domain must load before editor view model");

    function round(value) {
        const numeric = Number(value);
        return Number.isFinite(numeric) ? geometry.roundMm(numeric) : null;
    }

    function byId(items) {
        return new Map((items || []).map(item => [item.id, item]));
    }

    function pathNodes(document, path) {
        const nodes = byId(document.nodes);
        const segments = byId(document.segments);
        const ids = new Set();
        if (path && path.startNodeId) ids.add(path.startNodeId);
        (path && path.segmentIds || []).forEach(segmentId => {
            const segment = segments.get(segmentId);
            if (!segment) return;
            ids.add(segment.startNodeId);
            ids.add(segment.endNodeId);
        });
        return Array.from(ids).map(id => nodes.get(id)).filter(Boolean);
    }

    function bounds(nodes) {
        if (!nodes.length) return null;
        const xs = nodes.map(node => Number(node.xMm)).filter(Number.isFinite);
        const ys = nodes.map(node => Number(node.yMm)).filter(Number.isFinite);
        if (!xs.length || !ys.length) return null;
        const minX = Math.min(...xs);
        const minY = Math.min(...ys);
        const maxX = Math.max(...xs);
        const maxY = Math.max(...ys);
        return Object.freeze({
            xMm: round(minX),
            yMm: round(minY),
            widthMm: round(maxX - minX),
            heightMm: round(maxY - minY),
        });
    }

    function layerModel(document, selection) {
        const selectedKind = selection && selection.kind;
        const selectedId = selection && selection.id;
        const paths = (document.paths || []).map((path, index) => Object.freeze({
            id: path.id,
            kind: "path",
            label: (document.paths || []).length === 1 ? "محيط الدرفة" : `مسار ${index + 1}`,
            closed: Boolean(path.closed),
            selected: selectedKind === "path" && selectedId === path.id,
        }));
        const dimensions = (document.dimensions || []).map((dimension, index) => {
            const measurement = dimensionDomain.resolve(document, dimension.id);
            return Object.freeze({
                id: dimension.id,
                kind: "dimension",
                label: `بُعد ${index + 1}`,
                valueMm: measurement ? round(measurement.valueMm) : null,
                driving: Boolean(measurement && measurement.driving),
                selected: selectedKind === "dimension" && selectedId === dimension.id,
            });
        });
        return Object.freeze({ paths: Object.freeze(paths), dimensions: Object.freeze(dimensions) });
    }

    function documentProperties(document) {
        return Object.freeze({
            kind: "document",
            title: "الرسم",
            xMm: null,
            yMm: null,
            widthMm: round(document.blank && document.blank.widthMm),
            heightMm: round(document.blank && document.blank.heightMm),
            rotationDeg: null,
            nodeCount: (document.nodes || []).length,
            segmentCount: (document.segments || []).length,
            pathCount: (document.paths || []).length,
            dimensionCount: (document.dimensions || []).length,
        });
    }

    function selectedProperties(document, selection) {
        if (!selection || !selection.kind || !selection.id) return documentProperties(document);
        if (selection.kind === "node") {
            const node = (document.nodes || []).find(item => item.id === selection.id);
            if (!node) return documentProperties(document);
            return Object.freeze({
                kind: "node",
                id: node.id,
                title: "نقطة",
                xMm: round(node.xMm),
                yMm: round(node.yMm),
                widthMm: null,
                heightMm: null,
                rotationDeg: null,
            });
        }
        if (selection.kind === "path") {
            const path = (document.paths || []).find(item => item.id === selection.id);
            if (!path) return documentProperties(document);
            const box = bounds(pathNodes(document, path));
            return Object.freeze({
                kind: "path",
                id: path.id,
                title: "محيط الدرفة",
                xMm: box && box.xMm,
                yMm: box && box.yMm,
                widthMm: box && box.widthMm,
                heightMm: box && box.heightMm,
                rotationDeg: null,
                closed: Boolean(path.closed),
                segmentCount: (path.segmentIds || []).length,
            });
        }
        if (selection.kind === "dimension") {
            const measurement = dimensionDomain.resolve(document, selection.id);
            if (!measurement) return documentProperties(document);
            return Object.freeze({
                kind: "dimension",
                id: measurement.id,
                title: measurement.driving ? "بُعد ثابت" : "بُعد مرجعي",
                xMm: round(measurement.midpoint && measurement.midpoint.xMm),
                yMm: round(measurement.midpoint && measurement.midpoint.yMm),
                widthMm: null,
                heightMm: null,
                rotationDeg: round(measurement.angleDeg),
                valueMm: round(measurement.valueMm),
                driving: Boolean(measurement.driving),
            });
        }
        return documentProperties(document);
    }

    function build(document, interactionState = {}) {
        if (!document || typeof document !== "object") throw new Error("Drawing V4 editor view model requires a document");
        const selection = interactionState.selection || null;
        const toolState = interactionState.toolState || Object.freeze({ activeTool: null, effectiveTool: null });
        return Object.freeze({
            selection,
            activeTool: toolState.activeTool || null,
            effectiveTool: toolState.effectiveTool || toolState.activeTool || null,
            layers: layerModel(document, selection),
            properties: selectedProperties(document, selection),
            summary: Object.freeze({
                nodes: (document.nodes || []).length,
                segments: (document.segments || []).length,
                paths: (document.paths || []).length,
                dimensions: (document.dimensions || []).length,
            }),
        });
    }

    root.EditorViewModel = Object.freeze({ build, bounds, pathNodes });
})();
