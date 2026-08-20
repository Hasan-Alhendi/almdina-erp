(() => {
    "use strict";
    const root = window.AlmdinaSpecialShapeDocumentation = window.AlmdinaSpecialShapeDocumentation || Object.create(null);

    function create(canvas) {
        const context = canvas.getContext("2d");
        let document = null, selectedId = null, preview = null, image = null, imageUrl = "", viewport = null;

        function resize() {
            const rect = canvas.getBoundingClientRect();
            const ratio = Math.max(1, window.devicePixelRatio || 1);
            const width = Math.max(1, Math.round(rect.width * ratio));
            const height = Math.max(1, Math.round(rect.height * ratio));
            if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
            context.setTransform(ratio, 0, 0, ratio, 0, 0);
            return { width: rect.width, height: rect.height };
        }
        function calculateViewport(size) {
            const canvasWidth = Math.max(1, Number(document.canvas.widthMm));
            const canvasHeight = Math.max(1, Number(document.canvas.heightMm));
            const scale = Math.min((size.width - 100) / canvasWidth, (size.height - 80) / canvasHeight);
            return { scale: Math.max(0.05, scale), x: (size.width - canvasWidth * scale) / 2, y: (size.height - canvasHeight * scale) / 2, width: canvasWidth * scale, height: canvasHeight * scale };
        }
        function toScreen(point) { return { x: viewport.x + point.xMm * viewport.scale, y: viewport.y + point.yMm * viewport.scale }; }
        function toMm(point) { return { xMm: (point.x - viewport.x) / viewport.scale, yMm: (point.y - viewport.y) / viewport.scale }; }
        function screenPoint(event) { const rect = canvas.getBoundingClientRect(); return { x: event.clientX - rect.left, y: event.clientY - rect.top }; }
        function screenToMm(event) {
            const point = toMm(screenPoint(event));
            return { xMm: Math.max(0, Math.min(document.canvas.widthMm, point.xMm)), yMm: Math.max(0, Math.min(document.canvas.heightMm, point.yMm)) };
        }
        function loadReference() {
            const url = document && document.reference && document.reference.fileUrl;
            if (!url || url === imageUrl) return;
            imageUrl = url; image = new Image(); image.onload = draw; image.onerror = () => { image = null; draw(); }; image.src = url;
        }
        function grid() {
            context.save(); context.beginPath(); context.rect(viewport.x, viewport.y, viewport.width, viewport.height); context.clip();
            context.strokeStyle = "rgba(148,163,184,.16)"; context.lineWidth = 1;
            const step = Math.max(24, 100 * viewport.scale);
            for (let x = viewport.x; x <= viewport.x + viewport.width; x += step) { context.beginPath(); context.moveTo(x, viewport.y); context.lineTo(x, viewport.y + viewport.height); context.stroke(); }
            for (let y = viewport.y; y <= viewport.y + viewport.height; y += step) { context.beginPath(); context.moveTo(viewport.x, y); context.lineTo(viewport.x + viewport.width, y); context.stroke(); }
            context.restore();
        }
        function reference() {
            if (!image || !document.reference) return;
            context.save(); context.globalAlpha = document.reference.opacity; context.translate(viewport.x + viewport.width / 2, viewport.y + viewport.height / 2); context.rotate(document.reference.rotationDeg * Math.PI / 180);
            const ratio = Math.min(viewport.width / image.width, viewport.height / image.height);
            const width = image.width * ratio, height = image.height * ratio;
            context.drawImage(image, -width / 2, -height / 2, width, height); context.restore();
        }
        function style(element, selected = false) {
            context.strokeStyle = selected ? "#0b5fff" : String(element.style && element.style.color || "#1463e6");
            context.fillStyle = selected ? "#0b5fff" : String(element.style && element.style.color || "#1463e6");
            context.lineWidth = (Number(element.style && element.style.width) || 3) + (selected ? 1 : 0);
            context.lineCap = "round"; context.lineJoin = "round";
        }
        function path(points, closePath) {
            if (!points || points.length < 2) return;
            context.beginPath(); const first = toScreen(points[0]); context.moveTo(first.x, first.y);
            points.slice(1).forEach(point => { const screen = toScreen(point); context.lineTo(screen.x, screen.y); });
            if (closePath) context.closePath(); context.stroke();
        }
        function arrowHead(end, start) {
            const angle = Math.atan2(end.y - start.y, end.x - start.x), length = 9;
            context.beginPath(); context.moveTo(end.x, end.y); context.lineTo(end.x - length * Math.cos(angle - Math.PI / 6), end.y - length * Math.sin(angle - Math.PI / 6)); context.lineTo(end.x - length * Math.cos(angle + Math.PI / 6), end.y - length * Math.sin(angle + Math.PI / 6)); context.closePath(); context.fill();
        }
        function drawElement(element) {
            const selected = element.id === selectedId; context.save(); style(element, selected);
            if (element.type === "stroke") path(element.points, Boolean(element.closed));
            else if (["line", "arrow", "dimension"].includes(element.type)) {
                const start = toScreen(element.start), end = toScreen(element.end); context.beginPath(); context.moveTo(start.x, start.y); context.lineTo(end.x, end.y); context.stroke();
                if (element.type === "arrow") arrowHead(end, start);
                if (element.type === "dimension") {
                    arrowHead(end, start); arrowHead(start, end); const unit = element.unit || "mm"; const value = unit === "cm" ? Number(element.valueMm) / 10 : Number(element.valueMm);
                    const label = `${Math.round(value * 10) / 10} ${unit}`; context.font = "600 13px sans-serif"; const metrics = context.measureText(label); const x = (start.x + end.x) / 2, y = (start.y + end.y) / 2;
                    context.fillStyle = "#fff"; context.fillRect(x - metrics.width / 2 - 5, y - 18, metrics.width + 10, 22); context.fillStyle = selected ? "#0b5fff" : "#173c75"; context.fillText(label, x - metrics.width / 2, y - 3);
                }
            } else if (["rect", "ellipse"].includes(element.type)) {
                const start = toScreen({ xMm: element.xMm, yMm: element.yMm }); const width = element.widthMm * viewport.scale, height = element.heightMm * viewport.scale;
                context.beginPath(); if (element.type === "rect") context.rect(start.x, start.y, width, height); else context.ellipse(start.x + width / 2, start.y + height / 2, Math.abs(width / 2), Math.abs(height / 2), 0, 0, Math.PI * 2); context.stroke();
            } else if (element.type === "text") {
                const point = toScreen(element.position); context.font = "600 14px sans-serif"; context.fillStyle = selected ? "#0b5fff" : "#9a4b00"; context.fillText(element.text, point.x, point.y);
            }
            if (selected) handles(element); context.restore();
        }
        function bounds(element) {
            let points = [];
            if (element.type === "stroke") points = element.points || [];
            else if (["line", "arrow", "dimension"].includes(element.type)) points = [element.start, element.end];
            else if (["rect", "ellipse"].includes(element.type)) points = [{ xMm: element.xMm, yMm: element.yMm }, { xMm: element.xMm + element.widthMm, yMm: element.yMm + element.heightMm }];
            else if (element.type === "text") points = [element.position, { xMm: element.position.xMm + 100, yMm: element.position.yMm + 30 }];
            const xs = points.map(point => point.xMm), ys = points.map(point => point.yMm); if (!xs.length) return null;
            return { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };
        }
        function handles(element) { const box = bounds(element); if (!box) return; [{ xMm: box.minX, yMm: box.minY }, { xMm: box.maxX, yMm: box.maxY }].forEach(point => { const screen = toScreen(point); context.fillStyle = "#fff"; context.strokeStyle = "#0b5fff"; context.lineWidth = 2; context.fillRect(screen.x - 4, screen.y - 4, 8, 8); context.strokeRect(screen.x - 4, screen.y - 4, 8, 8); }); }
        function draw() {
            if (!document) return; const size = resize(); viewport = calculateViewport(size); context.clearRect(0, 0, size.width, size.height);
            context.fillStyle = "#f5f7fb"; context.fillRect(0, 0, size.width, size.height); context.fillStyle = "#fff"; context.fillRect(viewport.x, viewport.y, viewport.width, viewport.height); grid(); reference();
            document.elements.forEach(drawElement); if (preview && preview.length > 1) { context.save(); context.strokeStyle = "#0b5fff"; context.lineWidth = 3; context.setLineDash([7, 5]); path(preview, false); context.restore(); }
            context.strokeStyle = "rgba(15,23,42,.12)"; context.lineWidth = 1; context.strokeRect(viewport.x, viewport.y, viewport.width, viewport.height);
        }
        function render(nextDocument, options = {}) { document = nextDocument; selectedId = options.selectedId || null; preview = options.preview || null; loadReference(); draw(); }
        function hitTest(event) { const point = screenToMm(event), tolerance = 18 / viewport.scale; return [...document.elements].reverse().find(element => { const box = bounds(element); return box && point.xMm >= box.minX - tolerance && point.xMm <= box.maxX + tolerance && point.yMm >= box.minY - tolerance && point.yMm <= box.maxY + tolerance; }) || null; }
        function selectionRegion(event, element) {
            const box = bounds(element); if (!box) return null; const point = screenPoint(event); const start = toScreen({ xMm: box.minX, yMm: box.minY }), end = toScreen({ xMm: box.maxX, yMm: box.maxY });
            if (Math.hypot(point.x - start.x, point.y - start.y) <= 12) return "resize-start";
            if (Math.hypot(point.x - end.x, point.y - end.y) <= 12) return "resize-end";
            return "move";
        }
        return Object.freeze({ render, draw, screenToMm, hitTest, selectionRegion });
    }
    root.CanvasRenderer = Object.freeze({ create });
})();
