(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);
    const geometry = root.Geometry;
    const documentModel = root.DocumentModel;
    const viewport = root.Viewport;
    if (!geometry || !documentModel || !viewport) throw new Error("Drawing V4 domain and viewport must load before renderer");

    const TOKENS = Object.freeze({
        background: "#f4f6f8",
        blankFill: "#ffffff",
        blankStroke: "#d9dee5",
        gridMinor: "rgba(15, 23, 42, 0.045)",
        gridMajor: "rgba(15, 23, 42, 0.085)",
        geometry: "#111827",
        active: "#2563eb",
        nodeFill: "#ffffff",
        nodeStroke: "#2563eb",
        preview: "#2563eb",
        guide: "#d946ef",
        chipBackground: "rgba(17, 24, 39, 0.94)",
        chipText: "#ffffff",
    });

    const SNAP_LABELS = Object.freeze({
        endpoint: "نقطة نهاية",
        horizontal: "أفقي",
        vertical: "عمودي",
    });

    function semanticLabel(preview) {
        if (!preview || !preview.semantic) return "";
        if (preview.semantic === "angle") return `${Math.round(preview.angleDeg || 0)}°`;
        return SNAP_LABELS[preview.semantic] || "";
    }

    function resizeCanvas(canvas, widthPx, heightPx, dpr = window.devicePixelRatio || 1) {
        const cssWidth = Math.max(1, Math.round(Number(widthPx) || 1));
        const cssHeight = Math.max(1, Math.round(Number(heightPx) || 1));
        const ratio = Math.max(1, Number(dpr) || 1);
        const pixelWidth = Math.max(1, Math.round(cssWidth * ratio));
        const pixelHeight = Math.max(1, Math.round(cssHeight * ratio));
        if (canvas.width !== pixelWidth) canvas.width = pixelWidth;
        if (canvas.height !== pixelHeight) canvas.height = pixelHeight;
        if (canvas.style.width !== `${cssWidth}px`) canvas.style.width = `${cssWidth}px`;
        if (canvas.style.height !== `${cssHeight}px`) canvas.style.height = `${cssHeight}px`;
        return Object.freeze({ widthPx: cssWidth, heightPx: cssHeight, dpr: ratio });
    }

    function clear(ctx, widthPx, heightPx) {
        ctx.clearRect(0, 0, widthPx, heightPx);
        ctx.fillStyle = TOKENS.background;
        ctx.fillRect(0, 0, widthPx, heightPx);
    }

    function chooseGridStepMm(camera) {
        const preferredPx = 48;
        const rawMm = preferredPx / camera.scalePxPerMm;
        const powers = [1, 2, 5];
        const magnitude = Math.pow(10, Math.floor(Math.log10(Math.max(rawMm, 0.0001))));
        for (const factor of powers) {
            const candidate = factor * magnitude;
            if (candidate * camera.scalePxPerMm >= 28) return candidate;
        }
        return 10 * magnitude;
    }

    function drawGrid(ctx, camera) {
        const stepMm = chooseGridStepMm(camera);
        const stepPx = stepMm * camera.scalePxPerMm;
        if (stepPx < 8) return;

        const leftWorld = viewport.screenToWorld(camera, { x: 0, y: 0 }).xMm;
        const topWorld = viewport.screenToWorld(camera, { x: 0, y: 0 }).yMm;
        const rightWorld = viewport.screenToWorld(camera, { x: camera.viewportWidthPx, y: 0 }).xMm;
        const bottomWorld = viewport.screenToWorld(camera, { x: 0, y: camera.viewportHeightPx }).yMm;
        const startX = Math.floor(leftWorld / stepMm) * stepMm;
        const startY = Math.floor(topWorld / stepMm) * stepMm;
        let index = 0;

        ctx.lineWidth = 1;
        for (let xMm = startX; xMm <= rightWorld + stepMm; xMm += stepMm) {
            const screen = viewport.worldToScreen(camera, { xMm, yMm: 0 });
            const major = Math.round(xMm / stepMm) % 5 === 0;
            ctx.strokeStyle = major ? TOKENS.gridMajor : TOKENS.gridMinor;
            ctx.beginPath();
            ctx.moveTo(Math.round(screen.x) + 0.5, 0);
            ctx.lineTo(Math.round(screen.x) + 0.5, camera.viewportHeightPx);
            ctx.stroke();
            if (++index > 500) break;
        }

        index = 0;
        for (let yMm = startY; yMm <= bottomWorld + stepMm; yMm += stepMm) {
            const screen = viewport.worldToScreen(camera, { xMm: 0, yMm });
            const major = Math.round(yMm / stepMm) % 5 === 0;
            ctx.strokeStyle = major ? TOKENS.gridMajor : TOKENS.gridMinor;
            ctx.beginPath();
            ctx.moveTo(0, Math.round(screen.y) + 0.5);
            ctx.lineTo(camera.viewportWidthPx, Math.round(screen.y) + 0.5);
            ctx.stroke();
            if (++index > 500) break;
        }
    }

    function drawBlank(ctx, camera, blank) {
        if (!blank || !blank.widthMm || !blank.heightMm) return;
        const origin = viewport.worldToScreen(camera, { xMm: 0, yMm: 0 });
        const widthPx = blank.widthMm * camera.scalePxPerMm;
        const heightPx = blank.heightMm * camera.scalePxPerMm;
        ctx.fillStyle = TOKENS.blankFill;
        ctx.strokeStyle = TOKENS.blankStroke;
        ctx.lineWidth = 1;
        ctx.shadowColor = "rgba(15, 23, 42, 0.08)";
        ctx.shadowBlur = 18;
        ctx.shadowOffsetY = 4;
        ctx.fillRect(origin.x, origin.y, widthPx, heightPx);
        ctx.shadowColor = "transparent";
        ctx.strokeRect(Math.round(origin.x) + 0.5, Math.round(origin.y) + 0.5, widthPx, heightPx);
    }

    function drawGeometry(ctx, camera, document) {
        ctx.strokeStyle = TOKENS.geometry;
        ctx.lineWidth = 1.75;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        (document.segments || []).forEach(segment => {
            const startNode = documentModel.nodeById(document, segment.startNodeId);
            const endNode = documentModel.nodeById(document, segment.endNodeId);
            if (!startNode || !endNode) return;
            const start = viewport.worldToScreen(camera, startNode);
            const end = viewport.worldToScreen(camera, endNode);
            ctx.beginPath();
            ctx.moveTo(start.x, start.y);
            ctx.lineTo(end.x, end.y);
            ctx.stroke();
        });
    }

    function drawNodes(ctx, camera, document, options = {}) {
        if (!options.showNodes) return;
        (document.nodes || []).forEach(node => {
            const screen = viewport.worldToScreen(camera, node);
            ctx.beginPath();
            ctx.arc(screen.x, screen.y, 4, 0, Math.PI * 2);
            ctx.fillStyle = TOKENS.nodeFill;
            ctx.fill();
            ctx.lineWidth = 1.5;
            ctx.strokeStyle = TOKENS.nodeStroke;
            ctx.stroke();
        });
    }

    function drawChip(ctx, text, x, y) {
        if (!text) return;
        ctx.font = "600 12px system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
        const paddingX = 8;
        const height = 24;
        const width = Math.ceil(ctx.measureText(text).width) + paddingX * 2;
        const left = Math.min(Math.max(8, x + 12), Math.max(8, ctx.canvas.clientWidth - width - 8));
        const top = Math.max(8, y - height - 10);
        ctx.fillStyle = TOKENS.chipBackground;
        ctx.beginPath();
        if (typeof ctx.roundRect === "function") ctx.roundRect(left, top, width, height, 6);
        else ctx.rect(left, top, width, height);
        ctx.fill();
        ctx.fillStyle = TOKENS.chipText;
        ctx.textBaseline = "middle";
        ctx.fillText(text, left + paddingX, top + height / 2 + 0.5);
    }

    function drawPreview(ctx, camera, document, interactionState) {
        const preview = interactionState && interactionState.preview;
        const pathId = interactionState && interactionState.activePathId;
        if (!preview || !pathId) return;
        const anchorNodeId = documentModel.pathEndNodeId(document, pathId);
        const anchor = documentModel.nodeById(document, anchorNodeId);
        if (!anchor) return;

        const start = viewport.worldToScreen(camera, anchor);
        const end = viewport.worldToScreen(camera, preview.point);
        ctx.save();
        ctx.strokeStyle = preview.type === "free" ? TOKENS.preview : TOKENS.guide;
        ctx.lineWidth = 1.5;
        ctx.setLineDash(preview.type === "free" ? [] : [6, 5]);
        ctx.beginPath();
        ctx.moveTo(start.x, start.y);
        ctx.lineTo(end.x, end.y);
        ctx.stroke();
        ctx.setLineDash([]);

        const lengthMm = geometry.distance(anchor, preview.point);
        const measurement = `${geometry.roundMm(lengthMm)} mm`;
        const semantic = semanticLabel(preview);
        const label = semantic ? `${semantic} · ${measurement}` : measurement;
        drawChip(ctx, label, end.x, end.y);

        ctx.beginPath();
        ctx.arc(end.x, end.y, preview.type === "endpoint" ? 6 : 4, 0, Math.PI * 2);
        ctx.fillStyle = TOKENS.blankFill;
        ctx.fill();
        ctx.strokeStyle = preview.type === "free" ? TOKENS.preview : TOKENS.guide;
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.restore();
    }

    function render(canvas, input = {}) {
        if (!canvas) return;
        const camera = input.camera;
        const document = input.document;
        if (!camera || !document) return;
        const ratio = Math.max(1, Number(input.dpr || window.devicePixelRatio || 1));
        const ctx = canvas.getContext("2d");
        ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
        clear(ctx, camera.viewportWidthPx, camera.viewportHeightPx);
        drawGrid(ctx, camera);
        drawBlank(ctx, camera, document.blank);
        drawGeometry(ctx, camera, document);
        drawNodes(ctx, camera, document, { showNodes: Boolean(input.showNodes) });
        drawPreview(ctx, camera, document, input.interactionState);
    }

    root.CanvasRenderer = Object.freeze({
        TOKENS,
        resizeCanvas,
        render,
    });
})();