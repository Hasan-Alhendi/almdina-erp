(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);
    const geometry = root.Geometry;
    const documentModel = root.DocumentModel;
    const viewport = root.Viewport;
    const baseRenderer = root.CanvasRenderer;
    if (!geometry || !documentModel || !viewport || !baseRenderer) {
        throw new Error("Drawing V4 geometry, viewport, and renderer must load before selection overlay");
    }

    const ACCENT = "#0d99ff";
    const HANDLE_SIZE_PX = 6;
    const BADGE_HEIGHT_PX = 22;
    const BADGE_OFFSET_PX = 10;

    function selectionBounds(document, selection) {
        if (!selection || selection.kind !== "path") return null;
        const path = documentModel.pathById(document, selection.id);
        if (!path) return null;
        const nodeIds = new Set([path.startNodeId]);
        (path.segmentIds || []).forEach(segmentId => {
            const segment = documentModel.segmentById(document, segmentId);
            if (!segment) return;
            nodeIds.add(segment.startNodeId);
            nodeIds.add(segment.endNodeId);
        });
        const nodes = Array.from(nodeIds)
            .map(nodeId => documentModel.nodeById(document, nodeId))
            .filter(Boolean);
        if (!nodes.length) return null;
        const minX = Math.min(...nodes.map(node => node.xMm));
        const minY = Math.min(...nodes.map(node => node.yMm));
        const maxX = Math.max(...nodes.map(node => node.xMm));
        const maxY = Math.max(...nodes.map(node => node.yMm));
        return Object.freeze({
            minX: geometry.roundMm(minX),
            minY: geometry.roundMm(minY),
            maxX: geometry.roundMm(maxX),
            maxY: geometry.roundMm(maxY),
            widthMm: geometry.roundMm(maxX - minX),
            heightMm: geometry.roundMm(maxY - minY),
        });
    }

    function roundedRect(ctx, x, y, width, height, radius) {
        ctx.beginPath();
        if (typeof ctx.roundRect === "function") ctx.roundRect(x, y, width, height, radius);
        else ctx.rect(x, y, width, height);
    }

    function drawHandle(ctx, x, y) {
        const half = HANDLE_SIZE_PX / 2;
        ctx.fillStyle = "#ffffff";
        ctx.strokeStyle = ACCENT;
        ctx.lineWidth = 1;
        ctx.fillRect(x - half, y - half, HANDLE_SIZE_PX, HANDLE_SIZE_PX);
        ctx.strokeRect(x - half + 0.5, y - half + 0.5, HANDLE_SIZE_PX - 1, HANDLE_SIZE_PX - 1);
    }

    function drawBadge(ctx, text, centerX, topY, canvasWidth) {
        ctx.save();
        ctx.font = "600 11px Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
        const horizontalPadding = 8;
        const width = Math.ceil(ctx.measureText(text).width) + horizontalPadding * 2;
        const left = Math.min(Math.max(8, centerX - width / 2), Math.max(8, canvasWidth - width - 8));
        roundedRect(ctx, left, topY, width, BADGE_HEIGHT_PX, 4);
        ctx.fillStyle = ACCENT;
        ctx.fill();
        ctx.fillStyle = "#ffffff";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(text, left + width / 2, topY + BADGE_HEIGHT_PX / 2 + 0.5);
        ctx.restore();
    }

    function draw(canvas, input = {}) {
        if (!canvas || !input.camera || !input.document) return;
        const selection = input.interactionState && input.interactionState.selection;
        const bounds = selectionBounds(input.document, selection);
        if (!bounds) return;

        const topLeft = viewport.worldToScreen(input.camera, { xMm: bounds.minX, yMm: bounds.minY });
        const bottomRight = viewport.worldToScreen(input.camera, { xMm: bounds.maxX, yMm: bounds.maxY });
        const left = Math.min(topLeft.x, bottomRight.x);
        const top = Math.min(topLeft.y, bottomRight.y);
        const right = Math.max(topLeft.x, bottomRight.x);
        const bottom = Math.max(topLeft.y, bottomRight.y);
        const width = right - left;
        const height = bottom - top;
        if (!Number.isFinite(width) || !Number.isFinite(height)) return;

        const ratio = Math.max(1, Number(input.dpr || window.devicePixelRatio || 1));
        const ctx = canvas.getContext("2d");
        ctx.save();
        ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
        ctx.strokeStyle = ACCENT;
        ctx.lineWidth = 1;
        ctx.strokeRect(Math.round(left) + 0.5, Math.round(top) + 0.5, Math.round(width), Math.round(height));
        drawHandle(ctx, left, top);
        drawHandle(ctx, right, top);
        drawHandle(ctx, right, bottom);
        drawHandle(ctx, left, bottom);
        drawBadge(
            ctx,
            `${bounds.widthMm} × ${bounds.heightMm}`,
            left + width / 2,
            bottom + BADGE_OFFSET_PX,
            input.camera.viewportWidthPx
        );
        ctx.restore();
    }

    root.SelectionOverlay = Object.freeze({ selectionBounds, draw });
    root.CanvasRenderer = Object.freeze({
        ...baseRenderer,
        render(canvas, input = {}) {
            baseRenderer.render(canvas, input);
            draw(canvas, input);
        },
    });
})();
