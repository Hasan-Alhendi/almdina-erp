(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingProfessional = window.AlmdinaDoorDrawingProfessional || Object.create(null);
    const v4 = window.AlmdinaDoorDrawingV4;
    const geometry = v4.Geometry;
    const viewport = v4.Viewport;
    const viewModel = root.EditorViewModel;
    if (!geometry || !viewport || !viewModel) {
        throw new Error("Professional selection overlay dependencies are incomplete");
    }

    const BLUE = "#0d99ff";

    function roundedRect(ctx, x, y, width, height, radius) {
        if (typeof ctx.roundRect === "function") {
            ctx.beginPath();
            ctx.roundRect(x, y, width, height, radius);
            return;
        }
        const r = Math.min(radius, width / 2, height / 2);
        ctx.beginPath();
        ctx.moveTo(x + r, y);
        ctx.lineTo(x + width - r, y);
        ctx.quadraticCurveTo(x + width, y, x + width, y + r);
        ctx.lineTo(x + width, y + height - r);
        ctx.quadraticCurveTo(x + width, y + height, x + width - r, y + height);
        ctx.lineTo(x + r, y + height);
        ctx.quadraticCurveTo(x, y + height, x, y + height - r);
        ctx.lineTo(x, y + r);
        ctx.quadraticCurveTo(x, y, x + r, y);
        ctx.closePath();
    }

    function handle(ctx, x, y) {
        const size = 6;
        ctx.fillStyle = "#ffffff";
        ctx.strokeStyle = BLUE;
        ctx.lineWidth = 1.5;
        ctx.fillRect(x - size / 2, y - size / 2, size, size);
        ctx.strokeRect(x - size / 2, y - size / 2, size, size);
    }

    function sizeBadge(ctx, box, screenBox) {
        const text = `${geometry.roundMm(box.widthMm)} × ${geometry.roundMm(box.heightMm)}`;
        ctx.font = "600 11px Inter, 'Segoe UI', sans-serif";
        const width = Math.ceil(ctx.measureText(text).width) + 14;
        const height = 22;
        const x = screenBox.x + screenBox.width / 2 - width / 2;
        const y = screenBox.y + screenBox.height + 8;
        roundedRect(ctx, x, y, width, height, 5);
        ctx.fillStyle = BLUE;
        ctx.fill();
        ctx.fillStyle = "#ffffff";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(text, x + width / 2, y + height / 2 + 0.5);
    }

    function render(canvas, input = {}) {
        const selection = input.selection;
        if (!canvas || !input.camera || !input.document || !selection || selection.kind !== "path") return;
        const box = viewModel.pathBounds(input.document, selection.id);
        if (!box) return;
        const start = viewport.worldToScreen(input.camera, { xMm: box.xMm, yMm: box.yMm });
        const end = viewport.worldToScreen(input.camera, {
            xMm: box.xMm + box.widthMm,
            yMm: box.yMm + box.heightMm,
        });
        const screenBox = {
            x: Math.min(start.x, end.x),
            y: Math.min(start.y, end.y),
            width: Math.abs(end.x - start.x),
            height: Math.abs(end.y - start.y),
        };
        if (screenBox.width < 1 || screenBox.height < 1) return;

        const ratio = Math.max(1, Number(input.dpr || window.devicePixelRatio || 1));
        const ctx = canvas.getContext("2d");
        ctx.save();
        ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
        ctx.strokeStyle = BLUE;
        ctx.lineWidth = 1;
        ctx.setLineDash([]);
        ctx.strokeRect(
            Math.round(screenBox.x) + 0.5,
            Math.round(screenBox.y) + 0.5,
            Math.round(screenBox.width),
            Math.round(screenBox.height)
        );
        handle(ctx, screenBox.x, screenBox.y);
        handle(ctx, screenBox.x + screenBox.width, screenBox.y);
        handle(ctx, screenBox.x, screenBox.y + screenBox.height);
        handle(ctx, screenBox.x + screenBox.width, screenBox.y + screenBox.height);
        sizeBadge(ctx, box, screenBox);
        ctx.restore();
    }

    root.SelectionOverlay = Object.freeze({ render });
})();
