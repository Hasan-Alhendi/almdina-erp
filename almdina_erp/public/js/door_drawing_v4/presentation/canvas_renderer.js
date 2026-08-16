(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);
    const geometry = root.Geometry;
    const documentModel = root.DocumentModel;
    const dimensionDomain = root.DimensionDomain;
    const viewport = root.Viewport;
    if (!geometry || !documentModel || !dimensionDomain || !viewport) {
        throw new Error("Drawing V4 domain and viewport must load before renderer");
    }

    const TOKENS = Object.freeze({
        background: "#f4f6f8",
        blankFill: "#ffffff",
        blankStroke: "#d9dee5",
        gridMinor: "rgba(15, 23, 42, 0.045)",
        gridMajor: "rgba(15, 23, 42, 0.085)",
        geometry: "#111827",
        selected: "#2563eb",
        dimension: "#64748b",
        dimensionSelected: "#2563eb",
        nodeFill: "#ffffff",
        nodeStroke: "#2563eb",
        preview: "#2563eb",
        guide: "#d946ef",
        chipBackground: "rgba(17, 24, 39, 0.94)",
        chipText: "#ffffff",
    });

    const SNAP_LABELS = Object.freeze({
        close: "إغلاق",
        endpoint: "نقطة نهاية",
        intersection: "تقاطع",
        midpoint: "منتصف",
        perpendicular: "عمودي",
        edge: "على ضلع",
        parallel: "متوازي",
        extension: "امتداد",
        horizontal: "أفقي",
        vertical: "رأسي",
        grid: "شبكة",
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
        canvas.width = Math.max(1, Math.round(cssWidth * ratio));
        canvas.height = Math.max(1, Math.round(cssHeight * ratio));
        canvas.style.width = `${cssWidth}px`;
        canvas.style.height = `${cssHeight}px`;
        return Object.freeze({ widthPx: cssWidth, heightPx: cssHeight, dpr: ratio });
    }

    function clear(ctx, widthPx, heightPx) {
        ctx.clearRect(0, 0, widthPx, heightPx);
        ctx.fillStyle = TOKENS.background;
        ctx.fillRect(0, 0, widthPx, heightPx);
    }

    function drawGrid(ctx, camera) {
        const stepMm = viewport.gridStepMm(camera);
        if (stepMm * camera.scalePxPerMm < 8) return;
        const left = viewport.screenToWorld(camera, { x: 0, y: 0 }).xMm;
        const top = viewport.screenToWorld(camera, { x: 0, y: 0 }).yMm;
        const right = viewport.screenToWorld(camera, { x: camera.viewportWidthPx, y: 0 }).xMm;
        const bottom = viewport.screenToWorld(camera, { x: 0, y: camera.viewportHeightPx }).yMm;
        const startX = Math.floor(left / stepMm) * stepMm;
        const startY = Math.floor(top / stepMm) * stepMm;
        let count = 0;
        ctx.lineWidth = 1;
        for (let xMm = startX; xMm <= right + stepMm && count++ < 500; xMm += stepMm) {
            const x = viewport.worldToScreen(camera, { xMm, yMm: 0 }).x;
            ctx.strokeStyle = Math.round(xMm / stepMm) % 5 === 0 ? TOKENS.gridMajor : TOKENS.gridMinor;
            ctx.beginPath(); ctx.moveTo(Math.round(x) + 0.5, 0); ctx.lineTo(Math.round(x) + 0.5, camera.viewportHeightPx); ctx.stroke();
        }
        count = 0;
        for (let yMm = startY; yMm <= bottom + stepMm && count++ < 500; yMm += stepMm) {
            const y = viewport.worldToScreen(camera, { xMm: 0, yMm }).y;
            ctx.strokeStyle = Math.round(yMm / stepMm) % 5 === 0 ? TOKENS.gridMajor : TOKENS.gridMinor;
            ctx.beginPath(); ctx.moveTo(0, Math.round(y) + 0.5); ctx.lineTo(camera.viewportWidthPx, Math.round(y) + 0.5); ctx.stroke();
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

    function selectedSegmentIds(document, selection) {
        if (!selection || selection.kind !== "path") return new Set();
        const path = documentModel.pathById(document, selection.id);
        return new Set(path ? path.segmentIds : []);
    }

    function drawGeometry(ctx, camera, document, selection) {
        const selectedIds = selectedSegmentIds(document, selection);
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        (document.segments || []).forEach(segment => {
            const startNode = documentModel.nodeById(document, segment.startNodeId);
            const endNode = documentModel.nodeById(document, segment.endNodeId);
            if (!startNode || !endNode) return;
            const start = viewport.worldToScreen(camera, startNode);
            const end = viewport.worldToScreen(camera, endNode);
            const selected = selectedIds.has(segment.id);
            ctx.strokeStyle = selected ? TOKENS.selected : TOKENS.geometry;
            ctx.lineWidth = selected ? 3 : 1.75;
            ctx.beginPath();
            ctx.moveTo(start.x, start.y);
            ctx.lineTo(end.x, end.y);
            ctx.stroke();
        });
    }

    function drawDimensionLabel(ctx, text, x, y, color) {
        ctx.save();
        ctx.font = "700 11px system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
        const width = Math.ceil(ctx.measureText(text).width) + 10;
        const height = 20;
        ctx.fillStyle = "rgba(255,255,255,.94)";
        ctx.strokeStyle = color;
        ctx.lineWidth = 1;
        ctx.beginPath();
        if (typeof ctx.roundRect === "function") ctx.roundRect(x - width / 2, y - height / 2, width, height, 5);
        else ctx.rect(x - width / 2, y - height / 2, width, height);
        ctx.fill();
        ctx.stroke();
        ctx.fillStyle = color;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(text, x, y + 0.5);
        ctx.restore();
    }

    function outwardNormal(start, end, blankCenter) {
        const dx = end.x - start.x;
        const dy = end.y - start.y;
        const length = Math.hypot(dx, dy);
        if (length <= 0.001) return { x: 0, y: -1 };
        let nx = -dy / length;
        let ny = dx / length;
        const midpoint = { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 };
        const fromCenterX = midpoint.x - blankCenter.x;
        const fromCenterY = midpoint.y - blankCenter.y;
        if (fromCenterX * nx + fromCenterY * ny < 0) {
            nx *= -1;
            ny *= -1;
        }
        return { x: nx, y: ny };
    }

    function drawDimensions(ctx, camera, document, selection) {
        const measurements = dimensionDomain.all(document);
        if (!measurements.length) return;
        const blankCenter = viewport.worldToScreen(camera, {
            xMm: document.blank.widthMm / 2,
            yMm: document.blank.heightMm / 2,
        });
        measurements.forEach(measurement => {
            const start = viewport.worldToScreen(camera, measurement.start);
            const end = viewport.worldToScreen(camera, measurement.end);
            const normal = outwardNormal(start, end, blankCenter);
            const offsetPx = 30;
            const extensionPx = 7;
            const startDim = { x: start.x + normal.x * offsetPx, y: start.y + normal.y * offsetPx };
            const endDim = { x: end.x + normal.x * offsetPx, y: end.y + normal.y * offsetPx };
            const selected = Boolean(selection && selection.kind === "dimension" && selection.id === measurement.id);
            const color = selected ? TOKENS.dimensionSelected : TOKENS.dimension;

            ctx.save();
            ctx.strokeStyle = color;
            ctx.fillStyle = color;
            ctx.lineWidth = selected ? 1.5 : 1;
            ctx.beginPath();
            ctx.moveTo(start.x + normal.x * extensionPx, start.y + normal.y * extensionPx);
            ctx.lineTo(startDim.x, startDim.y);
            ctx.moveTo(end.x + normal.x * extensionPx, end.y + normal.y * extensionPx);
            ctx.lineTo(endDim.x, endDim.y);
            ctx.moveTo(startDim.x, startDim.y);
            ctx.lineTo(endDim.x, endDim.y);
            ctx.stroke();

            const dx = endDim.x - startDim.x;
            const dy = endDim.y - startDim.y;
            const length = Math.max(1, Math.hypot(dx, dy));
            const tx = dx / length;
            const ty = dy / length;
            const arrow = 6;
            [[startDim, 1], [endDim, -1]].forEach(([point, direction]) => {
                ctx.beginPath();
                ctx.moveTo(point.x, point.y);
                ctx.lineTo(
                    point.x + tx * arrow * direction + normal.x * arrow * 0.55,
                    point.y + ty * arrow * direction + normal.y * arrow * 0.55
                );
                ctx.lineTo(
                    point.x + tx * arrow * direction - normal.x * arrow * 0.55,
                    point.y + ty * arrow * direction - normal.y * arrow * 0.55
                );
                ctx.closePath();
                ctx.fill();
            });
            ctx.restore();

            drawDimensionLabel(
                ctx,
                `${geometry.roundMm(measurement.valueMm)} mm`,
                (startDim.x + endDim.x) / 2,
                (startDim.y + endDim.y) / 2,
                color
            );
        });
    }

    function drawNodes(ctx, camera, document, options = {}) {
        if (!options.showNodes) return;
        const selectedNodeId = options.selection && options.selection.kind === "node" ? options.selection.id : null;
        (document.nodes || []).forEach(node => {
            const screen = viewport.worldToScreen(camera, node);
            const selected = node.id === selectedNodeId;
            ctx.beginPath();
            ctx.arc(screen.x, screen.y, selected ? 6 : 4, 0, Math.PI * 2);
            ctx.fillStyle = selected ? TOKENS.selected : TOKENS.nodeFill;
            ctx.fill();
            ctx.lineWidth = selected ? 2 : 1.5;
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
        const clientWidth = ctx.canvas.clientWidth || ctx.canvas.width;
        const left = Math.min(Math.max(8, x + 12), Math.max(8, clientWidth - width - 8));
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

    function drawSnapGuides(ctx, camera, preview) {
        const guides = preview && Array.isArray(preview.guides) ? preview.guides : [];
        if (!guides.length) return;
        ctx.save();
        ctx.strokeStyle = TOKENS.guide;
        ctx.globalAlpha = 0.58;
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 5]);
        guides.forEach(guide => {
            if (!guide || !guide.start || !guide.end) return;
            const start = viewport.worldToScreen(camera, guide.start);
            const end = viewport.worldToScreen(camera, guide.end);
            ctx.beginPath();
            ctx.moveTo(start.x, start.y);
            ctx.lineTo(end.x, end.y);
            ctx.stroke();
        });
        ctx.restore();
    }

    function markerRadius(preview) {
        if (!preview) return 4;
        if (preview.type === "close") return 7;
        if (preview.type === "endpoint" || preview.type === "intersection") return 6;
        if (preview.type === "midpoint" || preview.type === "edge") return 5;
        return 4;
    }

    function drawSnapMarker(ctx, preview, end) {
        if (!preview || preview.type === "free") return;
        ctx.beginPath();
        ctx.arc(end.x, end.y, markerRadius(preview), 0, Math.PI * 2);
        ctx.fillStyle = TOKENS.blankFill;
        ctx.fill();
        ctx.strokeStyle = TOKENS.guide;
        ctx.lineWidth = preview.type === "close" ? 2.5 : 2;
        ctx.stroke();
    }

    function drawPreview(ctx, camera, document, interactionState) {
        const preview = interactionState && interactionState.preview;
        if (!preview) return;
        const pathId = interactionState && interactionState.activePathId;
        const end = viewport.worldToScreen(camera, preview.point);
        const semantic = semanticLabel(preview);
        drawSnapGuides(ctx, camera, preview);

        if (!pathId) {
            if (preview.type === "free") return;
            ctx.save();
            drawSnapMarker(ctx, preview, end);
            drawChip(ctx, semantic, end.x, end.y);
            ctx.restore();
            return;
        }

        const anchor = documentModel.nodeById(document, documentModel.pathEndNodeId(document, pathId));
        if (!anchor) return;
        const start = viewport.worldToScreen(camera, anchor);
        ctx.save();
        ctx.strokeStyle = preview.type === "free" ? TOKENS.preview : TOKENS.guide;
        ctx.lineWidth = 1.5;
        ctx.setLineDash(preview.type === "free" ? [] : [6, 5]);
        ctx.beginPath(); ctx.moveTo(start.x, start.y); ctx.lineTo(end.x, end.y); ctx.stroke();
        ctx.setLineDash([]);
        const measurement = `${geometry.roundMm(geometry.distance(anchor, preview.point))} mm`;
        drawChip(ctx, semantic ? `${semantic} · ${measurement}` : measurement, end.x, end.y);
        if (preview.type === "free") {
            ctx.beginPath(); ctx.arc(end.x, end.y, 4, 0, Math.PI * 2);
            ctx.fillStyle = TOKENS.blankFill; ctx.fill();
            ctx.strokeStyle = TOKENS.preview; ctx.lineWidth = 2; ctx.stroke();
        } else {
            drawSnapMarker(ctx, preview, end);
        }
        ctx.restore();
    }

    function drawDragFeedback(ctx, camera, drag) {
        if (!drag || drag.kind !== "node" || !drag.current || !drag.delta) return;
        const screen = viewport.worldToScreen(camera, drag.current);
        const dx = drag.delta.xMm >= 0 ? `+${drag.delta.xMm}` : String(drag.delta.xMm);
        const dy = drag.delta.yMm >= 0 ? `+${drag.delta.yMm}` : String(drag.delta.yMm);
        drawChip(ctx, `X ${geometry.roundMm(drag.current.xMm)} · Y ${geometry.roundMm(drag.current.yMm)} mm · Δ ${dx}, ${dy}`, screen.x, screen.y);
    }

    function render(canvas, input = {}) {
        if (!canvas || !input.camera || !input.document) return;
        const camera = input.camera;
        const document = input.document;
        const interactionState = input.interactionState || {};
        const ratio = Math.max(1, Number(input.dpr || window.devicePixelRatio || 1));
        const ctx = canvas.getContext("2d");
        ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
        clear(ctx, camera.viewportWidthPx, camera.viewportHeightPx);
        drawGrid(ctx, camera);
        drawBlank(ctx, camera, document.blank);
        drawGeometry(ctx, camera, document, interactionState.selection);
        drawDimensions(ctx, camera, document, interactionState.selection);
        drawNodes(ctx, camera, document, { showNodes: Boolean(input.showNodes), selection: interactionState.selection });
        drawPreview(ctx, camera, document, interactionState);
        drawDragFeedback(ctx, camera, interactionState.drag);
    }

    root.CanvasRenderer = Object.freeze({ TOKENS, resizeCanvas, render });
})();