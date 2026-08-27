(() => {
    "use strict";

    const root = window.AlmdinaSpecialShapeDocumentation = window.AlmdinaSpecialShapeDocumentation || Object.create(null);
    const MIN_SIZE = 0.02;
    const FULL = Object.freeze({ x: 0, y: 0, width: 1, height: 1 });

    function finite(value, fallback = 0) {
        const resolved = Number(value);
        return Number.isFinite(resolved) ? resolved : fallback;
    }
    function clamp(value, minimum, maximum) { return Math.max(minimum, Math.min(maximum, value)); }
    function rounded(value) { return Math.round(value * 1_000_000) / 1_000_000; }
    function normalize(value) {
        const raw = value && typeof value === "object" ? value : FULL;
        const x = clamp(finite(raw.x), 0, 1 - MIN_SIZE);
        const y = clamp(finite(raw.y), 0, 1 - MIN_SIZE);
        const width = clamp(finite(raw.width, 1), MIN_SIZE, 1 - x);
        const height = clamp(finite(raw.height, 1), MIN_SIZE, 1 - y);
        return { x: rounded(x), y: rounded(y), width: rounded(width), height: rounded(height) };
    }
    function isFull(value) {
        const crop = normalize(value);
        return crop.x <= 0.000001 && crop.y <= 0.000001 && crop.width >= 0.999999 && crop.height >= 0.999999;
    }
    function transform(value, region, delta = {}) {
        const crop = normalize(value);
        const dx = finite(delta.x), dy = finite(delta.y);
        if (region === "move") {
            return normalize({
                ...crop,
                x: clamp(crop.x + dx, 0, 1 - crop.width),
                y: clamp(crop.y + dy, 0, 1 - crop.height),
            });
        }
        let left = crop.x, top = crop.y, right = crop.x + crop.width, bottom = crop.y + crop.height;
        if (String(region).includes("w")) left = clamp(left + dx, 0, right - MIN_SIZE);
        if (String(region).includes("e")) right = clamp(right + dx, left + MIN_SIZE, 1);
        if (String(region).includes("n")) top = clamp(top + dy, 0, bottom - MIN_SIZE);
        if (String(region).includes("s")) bottom = clamp(bottom + dy, top + MIN_SIZE, 1);
        return normalize({ x: left, y: top, width: right - left, height: bottom - top });
    }
    function median(values) {
        const sorted = values.slice().sort((a, b) => a - b);
        return sorted[Math.floor(sorted.length / 2)] || 0;
    }
    function detectContentBounds(imageData, options = {}) {
        const width = Math.floor(finite(imageData && imageData.width));
        const height = Math.floor(finite(imageData && imageData.height));
        const data = imageData && imageData.data;
        if (!width || !height || !data || data.length < width * height * 4) return null;

        const patch = Math.max(1, Math.min(12, width, height, Math.floor(Math.min(width, height) * 0.025) || 1));
        const channels = [[], [], []];
        const corners = [[0, 0], [width - patch, 0], [0, height - patch], [width - patch, height - patch]];
        corners.forEach(([startX, startY]) => {
            for (let y = startY; y < startY + patch; y += 1) for (let x = startX; x < startX + patch; x += 1) {
                const offset = (y * width + x) * 4;
                if (data[offset + 3] < 24) continue;
                channels[0].push(data[offset]); channels[1].push(data[offset + 1]); channels[2].push(data[offset + 2]);
            }
        });
        const background = channels.map(median);
        const backgroundLuminance = background[0] * 0.2126 + background[1] * 0.7152 + background[2] * 0.0722;
        const contrastThreshold = Math.max(12, finite(options.contrastThreshold, 28));
        const darknessThreshold = Math.max(8, finite(options.darknessThreshold, 16));
        const rowCounts = new Uint32Array(height), columnCounts = new Uint32Array(width);
        let contentPixels = 0;
        for (let y = 0; y < height; y += 1) for (let x = 0; x < width; x += 1) {
            const offset = (y * width + x) * 4;
            if (data[offset + 3] < 24) continue;
            const red = data[offset], green = data[offset + 1], blue = data[offset + 2];
            const contrast = Math.max(Math.abs(red - background[0]), Math.abs(green - background[1]), Math.abs(blue - background[2]));
            const luminance = red * 0.2126 + green * 0.7152 + blue * 0.0722;
            if (contrast < contrastThreshold && backgroundLuminance - luminance < darknessThreshold) continue;
            rowCounts[y] += 1; columnCounts[x] += 1; contentPixels += 1;
        }
        if (contentPixels < Math.max(12, width * height * 0.00015)) return null;
        const minimumRow = Math.max(1, Math.floor(width * 0.0015));
        const minimumColumn = Math.max(1, Math.floor(height * 0.0015));
        let minX = 0, maxX = width - 1, minY = 0, maxY = height - 1;
        while (minX < width && columnCounts[minX] < minimumColumn) minX += 1;
        while (maxX >= 0 && columnCounts[maxX] < minimumColumn) maxX -= 1;
        while (minY < height && rowCounts[minY] < minimumRow) minY += 1;
        while (maxY >= 0 && rowCounts[maxY] < minimumRow) maxY -= 1;
        if (minX > maxX || minY > maxY) return null;
        const paddingX = Math.max(3, Math.round((maxX - minX + 1) * 0.04));
        const paddingY = Math.max(3, Math.round((maxY - minY + 1) * 0.04));
        minX = Math.max(0, minX - paddingX); maxX = Math.min(width - 1, maxX + paddingX);
        minY = Math.max(0, minY - paddingY); maxY = Math.min(height - 1, maxY + paddingY);
        return normalize({ x: minX / width, y: minY / height, width: (maxX - minX + 1) / width, height: (maxY - minY + 1) / height });
    }

    root.ReferenceCrop = Object.freeze({ FULL, MIN_SIZE, normalize, isFull, transform, detectContentBounds });
})();
