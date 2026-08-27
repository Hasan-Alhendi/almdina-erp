(() => {
    "use strict";

    const root = window.AlmdinaSpecialShapeDocumentation = window.AlmdinaSpecialShapeDocumentation || Object.create(null);

    function create(canvas) {
        const Viewport = root.CanvasViewport;
        const Crop = root.ReferenceCrop;
        if (!Viewport || !Crop) throw new Error("Special-shape canvas contracts are unavailable");

        const context = canvas.getContext("2d");
        let document = null;
        let selectedId = null;
        let preview = null;
        let cropSession = null;
        let image = null;
        let imageUrl = "";
        let viewport = null;
        let frameKey = "";

        function measure() {
            const rect = canvas.getBoundingClientRect();
            const ratio = Math.max(1, window.devicePixelRatio || 1);
            const width = Math.max(1, Math.round(rect.width * ratio));
            const height = Math.max(1, Math.round(rect.height * ratio));
            if (canvas.width !== width || canvas.height !== height) {
                canvas.width = width;
                canvas.height = height;
            }
            context.setTransform(ratio, 0, 0, ratio, 0, 0);
            return { width: rect.width, height: rect.height };
        }

        function ensureViewport(size) {
            if (!viewport) {
                viewport = Viewport.initial(size, document.canvas);
                return;
            }
            if (!viewport.size || viewport.size.width !== size.width || viewport.size.height !== size.height) {
                viewport = Viewport.resize(viewport, size);
            }
        }

        function toScreen(point) {
            return Viewport.toScreen(viewport, point);
        }

        function screenPoint(event) {
            const rect = canvas.getBoundingClientRect();
            return { x: event.clientX - rect.left, y: event.clientY - rect.top };
        }

        function screenToMm(event) {
            return Viewport.toWorld(viewport, screenPoint(event));
        }

        function gridStep() {
            const candidates = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000];
            return candidates.find(step => step * viewport.scale >= 32) || candidates[candidates.length - 1];
        }

        function grid(size) {
            const topLeft = Viewport.toWorld(viewport, { x: 0, y: 0 });
            const bottomRight = Viewport.toWorld(viewport, { x: size.width, y: size.height });
            const step = gridStep();
            const minX = Math.min(topLeft.xMm, bottomRight.xMm);
            const maxX = Math.max(topLeft.xMm, bottomRight.xMm);
            const minY = Math.min(topLeft.yMm, bottomRight.yMm);
            const maxY = Math.max(topLeft.yMm, bottomRight.yMm);

            context.save();
            context.strokeStyle = "rgba(100,116,139,.16)";
            context.lineWidth = 1;
            for (let xMm = Math.ceil(minX / step) * step; xMm <= maxX; xMm += step) {
                const x = toScreen({ xMm, yMm: 0 }).x;
                context.beginPath();
                context.moveTo(x, 0);
                context.lineTo(x, size.height);
                context.stroke();
            }
            for (let yMm = Math.ceil(minY / step) * step; yMm <= maxY; yMm += step) {
                const y = toScreen({ xMm: 0, yMm }).y;
                context.beginPath();
                context.moveTo(0, y);
                context.lineTo(size.width, y);
                context.stroke();
            }
            context.restore();
        }

        function loadReference() {
            const url = document && document.reference && document.reference.fileUrl;
            if (!url) {
                image = null;
                imageUrl = "";
                return;
            }
            if (url === imageUrl) return;
            imageUrl = url;
            image = new Image();
            image.onload = draw;
            image.onerror = () => { image = null; draw(); };
            image.src = url;
        }

        function referenceGeometry(editing = false) {
            if (!image || !document.reference) return null;
            const width = Number(document.canvas.widthMm) * viewport.scale;
            const height = Number(document.canvas.heightMm) * viewport.scale;
            const origin = toScreen({ xMm: 0, yMm: 0 });
            const naturalWidth = Math.max(1, Number(image.naturalWidth || image.width));
            const naturalHeight = Math.max(1, Number(image.naturalHeight || image.height));
            const crop = editing ? Crop.FULL : Crop.normalize(document.reference.crop);
            const sourceWidth = naturalWidth * crop.width;
            const sourceHeight = naturalHeight * crop.height;
            const ratio = Math.min(width / sourceWidth, height / sourceHeight);
            return {
                center: { x: origin.x + width / 2, y: origin.y + height / 2 },
                angle: document.reference.rotationDeg * Math.PI / 180,
                naturalWidth,
                naturalHeight,
                crop,
                source: { x: naturalWidth * crop.x, y: naturalHeight * crop.y, width: sourceWidth, height: sourceHeight },
                destination: { width: sourceWidth * ratio, height: sourceHeight * ratio },
            };
        }

        function cropOverlay(geometry, value) {
            const crop = Crop.normalize(value);
            const fullWidth = geometry.destination.width, fullHeight = geometry.destination.height;
            const left = -fullWidth / 2 + crop.x * fullWidth;
            const top = -fullHeight / 2 + crop.y * fullHeight;
            const width = crop.width * fullWidth;
            const height = crop.height * fullHeight;
            context.globalAlpha = 1;
            context.fillStyle = "rgba(15,23,42,.58)";
            context.fillRect(-fullWidth / 2, -fullHeight / 2, fullWidth, Math.max(0, top + fullHeight / 2));
            context.fillRect(-fullWidth / 2, top + height, fullWidth, Math.max(0, fullHeight / 2 - top - height));
            context.fillRect(-fullWidth / 2, top, Math.max(0, left + fullWidth / 2), height);
            context.fillRect(left + width, top, Math.max(0, fullWidth / 2 - left - width), height);
            context.strokeStyle = "#fff";
            context.lineWidth = 2;
            context.setLineDash([]);
            context.strokeRect(left, top, width, height);
            context.strokeStyle = "rgba(255,255,255,.72)";
            context.lineWidth = 1;
            context.beginPath();
            context.moveTo(left + width / 3, top); context.lineTo(left + width / 3, top + height);
            context.moveTo(left + width * 2 / 3, top); context.lineTo(left + width * 2 / 3, top + height);
            context.moveTo(left, top + height / 3); context.lineTo(left + width, top + height / 3);
            context.moveTo(left, top + height * 2 / 3); context.lineTo(left + width, top + height * 2 / 3);
            context.stroke();
            const handles = [[left, top], [left + width / 2, top], [left + width, top], [left + width, top + height / 2], [left + width, top + height], [left + width / 2, top + height], [left, top + height], [left, top + height / 2]];
            handles.forEach(([x, y]) => { context.fillStyle = "#fff"; context.strokeStyle = "#0b5fff"; context.lineWidth = 2; context.fillRect(x - 5, y - 5, 10, 10); context.strokeRect(x - 5, y - 5, 10, 10); });
        }

        function reference() {
            if (!image || !document.reference) return;
            const editing = Boolean(cropSession && cropSession.active);
            const geometry = referenceGeometry(editing);
            if (!geometry) return;

            context.save();
            context.globalAlpha = editing ? Math.max(0.82, document.reference.opacity) : document.reference.opacity;
            context.translate(geometry.center.x, geometry.center.y);
            context.rotate(geometry.angle);
            context.drawImage(
                image,
                geometry.source.x, geometry.source.y, geometry.source.width, geometry.source.height,
                -geometry.destination.width / 2, -geometry.destination.height / 2,
                geometry.destination.width, geometry.destination.height,
            );
            if (editing) cropOverlay(geometry, cropSession.value);
            context.restore();
        }

        function cropCoordinates(event) {
            const geometry = referenceGeometry(true);
            if (!geometry) return null;
            const point = screenPoint(event);
            const dx = point.x - geometry.center.x, dy = point.y - geometry.center.y;
            const cosine = Math.cos(geometry.angle), sine = Math.sin(geometry.angle);
            const localX = dx * cosine + dy * sine;
            const localY = -dx * sine + dy * cosine;
            return {
                geometry,
                local: { x: localX, y: localY },
                normalized: {
                    x: (localX + geometry.destination.width / 2) / geometry.destination.width,
                    y: (localY + geometry.destination.height / 2) / geometry.destination.height,
                },
            };
        }

        function cropPoint(event) {
            const resolved = cropCoordinates(event);
            return resolved ? resolved.normalized : null;
        }

        function cropRegion(event, value) {
            const resolved = cropCoordinates(event);
            if (!resolved) return null;
            const crop = Crop.normalize(value);
            const { geometry, local } = resolved;
            const left = -geometry.destination.width / 2 + crop.x * geometry.destination.width;
            const top = -geometry.destination.height / 2 + crop.y * geometry.destination.height;
            const right = left + crop.width * geometry.destination.width;
            const bottom = top + crop.height * geometry.destination.height;
            const handles = [
                ["nw", left, top], ["n", (left + right) / 2, top], ["ne", right, top], ["e", right, (top + bottom) / 2],
                ["se", right, bottom], ["s", (left + right) / 2, bottom], ["sw", left, bottom], ["w", left, (top + bottom) / 2],
            ];
            const handle = handles.find(([, x, y]) => Math.hypot(local.x - x, local.y - y) <= 22);
            if (handle) return handle[0];
            return local.x >= left && local.x <= right && local.y >= top && local.y <= bottom ? "move" : null;
        }

        function suggestReferenceCrop() {
            if (!image || !image.complete) return null;
            const naturalWidth = Math.max(1, Number(image.naturalWidth || image.width));
            const naturalHeight = Math.max(1, Number(image.naturalHeight || image.height));
            const scale = Math.min(1, 900 / Math.max(naturalWidth, naturalHeight));
            const width = Math.max(1, Math.round(naturalWidth * scale));
            const height = Math.max(1, Math.round(naturalHeight * scale));
            const sampler = window.document.createElement("canvas");
            sampler.width = width; sampler.height = height;
            const samplerContext = sampler.getContext("2d", { willReadFrequently: true });
            try {
                samplerContext.drawImage(image, 0, 0, width, height);
                return Crop.detectContentBounds(samplerContext.getImageData(0, 0, width, height));
            } catch (error) {
                console.warn("Reference auto-crop analysis failed", error);
                return null;
            }
        }

        function referenceImageSize() {
            if (!image || !image.complete) return null;
            const widthPx = Math.round(Number(image.naturalWidth || image.width));
            const heightPx = Math.round(Number(image.naturalHeight || image.height));
            return widthPx > 0 && heightPx > 0 ? { widthPx, heightPx } : null;
        }

        function style(element, selected = false) {
            context.strokeStyle = selected ? "#0b5fff" : String(element.style && element.style.color || "#1463e6");
            context.fillStyle = selected ? "#0b5fff" : String(element.style && element.style.color || "#1463e6");
            context.lineWidth = (Number(element.style && element.style.width) || 3) + (selected ? 1 : 0);
            context.lineCap = "round";
            context.lineJoin = "round";
        }

        function path(points, closePath) {
            if (!points || points.length < 2) return;
            context.beginPath();
            const first = toScreen(points[0]);
            context.moveTo(first.x, first.y);
            points.slice(1).forEach(point => {
                const screen = toScreen(point);
                context.lineTo(screen.x, screen.y);
            });
            if (closePath) context.closePath();
            context.stroke();
        }

        function arrowHead(end, start) {
            const angle = Math.atan2(end.y - start.y, end.x - start.x);
            const length = 9;
            context.beginPath();
            context.moveTo(end.x, end.y);
            context.lineTo(end.x - length * Math.cos(angle - Math.PI / 6), end.y - length * Math.sin(angle - Math.PI / 6));
            context.lineTo(end.x - length * Math.cos(angle + Math.PI / 6), end.y - length * Math.sin(angle + Math.PI / 6));
            context.closePath();
            context.fill();
        }

        function drawElement(element) {
            const selected = element.id === selectedId;
            context.save();
            style(element, selected);
            if (element.type === "stroke") {
                path(element.points, Boolean(element.closed));
            } else if (["line", "arrow", "dimension"].includes(element.type)) {
                const start = toScreen(element.start);
                const end = toScreen(element.end);
                context.beginPath();
                context.moveTo(start.x, start.y);
                context.lineTo(end.x, end.y);
                context.stroke();
                if (element.type === "arrow") arrowHead(end, start);
                if (element.type === "dimension") {
                    arrowHead(end, start);
                    arrowHead(start, end);
                    const unit = element.unit || "mm";
                    const value = unit === "cm" ? Number(element.valueMm) / 10 : Number(element.valueMm);
                    const label = `${Math.round(value * 10) / 10} ${unit}`;
                    context.font = "600 13px sans-serif";
                    const metrics = context.measureText(label);
                    const x = (start.x + end.x) / 2;
                    const y = (start.y + end.y) / 2;
                    context.fillStyle = "#fff";
                    context.fillRect(x - metrics.width / 2 - 5, y - 18, metrics.width + 10, 22);
                    context.fillStyle = selected ? "#0b5fff" : "#173c75";
                    context.fillText(label, x - metrics.width / 2, y - 3);
                }
            } else if (["rect", "ellipse"].includes(element.type)) {
                const start = toScreen({ xMm: element.xMm, yMm: element.yMm });
                const width = element.widthMm * viewport.scale;
                const height = element.heightMm * viewport.scale;
                context.beginPath();
                if (element.type === "rect") context.rect(start.x, start.y, width, height);
                else context.ellipse(start.x + width / 2, start.y + height / 2, Math.abs(width / 2), Math.abs(height / 2), 0, 0, Math.PI * 2);
                context.stroke();
            } else if (element.type === "text") {
                const point = toScreen(element.position);
                context.font = "600 14px sans-serif";
                context.fillStyle = selected ? "#0b5fff" : "#9a4b00";
                context.fillText(element.text, point.x, point.y);
            }
            if (selected) handles(element);
            context.restore();
        }

        function bounds(element) {
            let points = [];
            if (element.type === "stroke") points = element.points || [];
            else if (["line", "arrow", "dimension"].includes(element.type)) points = [element.start, element.end];
            else if (["rect", "ellipse"].includes(element.type)) points = [
                { xMm: element.xMm, yMm: element.yMm },
                { xMm: element.xMm + element.widthMm, yMm: element.yMm + element.heightMm },
            ];
            else if (element.type === "text") points = [element.position, { xMm: element.position.xMm + 100, yMm: element.position.yMm + 30 }];
            const xs = points.map(point => Number(point.xMm)).filter(Number.isFinite);
            const ys = points.map(point => Number(point.yMm)).filter(Number.isFinite);
            if (!xs.length || !ys.length) return null;
            return { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };
        }

        function documentBounds() {
            const values = document.elements.map(bounds).filter(Boolean);
            if (document.reference) values.push({ minX: 0, minY: 0, maxX: Number(document.canvas.widthMm), maxY: Number(document.canvas.heightMm) });
            if (!values.length) return { minX: 0, minY: 0, maxX: Number(document.canvas.widthMm), maxY: Number(document.canvas.heightMm) };
            return {
                minX: Math.min(...values.map(value => value.minX)),
                maxX: Math.max(...values.map(value => value.maxX)),
                minY: Math.min(...values.map(value => value.minY)),
                maxY: Math.max(...values.map(value => value.maxY)),
            };
        }

        function handles(element) {
            const box = bounds(element);
            if (!box) return;
            [{ xMm: box.minX, yMm: box.minY }, { xMm: box.maxX, yMm: box.maxY }].forEach(point => {
                const screen = toScreen(point);
                context.fillStyle = "#fff";
                context.strokeStyle = "#0b5fff";
                context.lineWidth = 2;
                context.fillRect(screen.x - 4, screen.y - 4, 8, 8);
                context.strokeRect(screen.x - 4, screen.y - 4, 8, 8);
            });
        }

        function draw() {
            if (!document) return;
            const size = measure();
            ensureViewport(size);
            context.clearRect(0, 0, size.width, size.height);
            context.fillStyle = "#eef1f5";
            context.fillRect(0, 0, size.width, size.height);
            grid(size);
            reference();
            document.elements.forEach(drawElement);
            if (preview && preview.length > 1) {
                context.save();
                context.strokeStyle = "#0b5fff";
                context.lineWidth = 3;
                context.setLineDash([7, 5]);
                path(preview, false);
                context.restore();
            }
        }

        function render(nextDocument, options = {}) {
            const nextFrameKey = `${nextDocument.canvas.widthMm}:${nextDocument.canvas.heightMm}`;
            if (frameKey && frameKey !== nextFrameKey) viewport = null;
            frameKey = nextFrameKey;
            document = nextDocument;
            selectedId = options.selectedId || null;
            preview = options.preview || null;
            cropSession = options.cropSession || null;
            loadReference();
            draw();
        }

        function hitTest(event) {
            const point = screenToMm(event);
            const tolerance = 18 / viewport.scale;
            return [...document.elements].reverse().find(element => {
                const box = bounds(element);
                return box && point.xMm >= box.minX - tolerance && point.xMm <= box.maxX + tolerance && point.yMm >= box.minY - tolerance && point.yMm <= box.maxY + tolerance;
            }) || null;
        }

        function selectionRegion(event, element) {
            const box = bounds(element);
            if (!box) return null;
            const point = screenPoint(event);
            const start = toScreen({ xMm: box.minX, yMm: box.minY });
            const end = toScreen({ xMm: box.maxX, yMm: box.maxY });
            if (Math.hypot(point.x - start.x, point.y - start.y) <= 12) return "resize-start";
            if (Math.hypot(point.x - end.x, point.y - end.y) <= 12) return "resize-end";
            return "move";
        }

        function zoomAt(event, factor) {
            if (!document) return;
            const size = measure();
            ensureViewport(size);
            viewport = Viewport.zoomAt(viewport, viewport.scale * Number(factor || 1), screenPoint(event));
            draw();
        }

        function zoomBy(factor) {
            if (!document) return;
            const size = measure();
            ensureViewport(size);
            viewport = Viewport.zoomAt(viewport, viewport.scale * Number(factor || 1), { x: size.width / 2, y: size.height / 2 });
            draw();
        }

        function resetZoom() {
            if (!document) return;
            const size = measure();
            ensureViewport(size);
            viewport = Viewport.zoomAt(viewport, Viewport.DEFAULT_SCALE, { x: size.width / 2, y: size.height / 2 });
            draw();
        }

        function panBy(dx, dy) {
            if (!document) return;
            const size = measure();
            ensureViewport(size);
            viewport = Viewport.pan(viewport, dx, dy);
            draw();
        }

        function fitToContent() {
            if (!document) return;
            const size = measure();
            viewport = Viewport.fit(size, documentBounds());
            draw();
        }

        function zoomPercentage() {
            return Viewport.percentage(viewport);
        }

        function screenDeltaToMm(pixels) {
            return Number(pixels || 0) / Math.max(Viewport.MIN_SCALE, viewport && viewport.scale || Viewport.DEFAULT_SCALE);
        }

        return Object.freeze({
            render,
            draw,
            screenPoint,
            screenToMm,
            hitTest,
            selectionRegion,
            zoomAt,
            zoomBy,
            resetZoom,
            panBy,
            fitToContent,
            zoomPercentage,
            screenDeltaToMm,
            cropPoint,
            cropRegion,
            suggestReferenceCrop,
            referenceImageSize,
        });
    }

    root.CanvasRenderer = Object.freeze({ create });
})();
