(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);
    const base = root.CanvasRenderer;
    const viewport = root.Viewport;
    if (!base || !viewport) throw new Error("Canvas renderer and viewport must load before smart stroke preview");

    function drawStrokePreview(canvas, input = {}) {
        const points = input.interactionState && input.interactionState.strokePreview;
        if (!Array.isArray(points) || points.length < 2) return;
        const camera = input.camera;
        const ratio = Math.max(1, Number(input.dpr || window.devicePixelRatio || 1));
        const ctx = canvas.getContext("2d");
        ctx.save();
        ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
        ctx.strokeStyle = "#0d99ff";
        ctx.lineWidth = 2.25;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.globalAlpha = 0.9;
        ctx.beginPath();
        points.forEach((point, index) => {
            const screen = viewport.worldToScreen(camera, point);
            if (index === 0) ctx.moveTo(screen.x, screen.y);
            else ctx.lineTo(screen.x, screen.y);
        });
        ctx.stroke();
        ctx.restore();
    }

    function render(canvas, input = {}) {
        base.render(canvas, input);
        if (canvas && input.camera) drawStrokePreview(canvas, input);
    }

    root.CanvasRenderer = Object.freeze({ ...base, render, drawStrokePreview });
})();
