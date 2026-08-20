(() => {
    "use strict";
    const root = window.AlmdinaSpecialShapeDocumentation = window.AlmdinaSpecialShapeDocumentation || Object.create(null);
    function points(element) {
        if (element.type === "stroke") return element.points || [];
        if (["line", "arrow", "dimension"].includes(element.type)) return [element.start, element.end];
        if (["rect", "ellipse"].includes(element.type)) return [{ xMm: element.xMm, yMm: element.yMm }, { xMm: element.xMm + element.widthMm, yMm: element.yMm + element.heightMm }];
        if (element.type === "text") return [element.position, { xMm: element.position.xMm + 100, yMm: element.position.yMm + 30 }];
        return [];
    }
    function bounds(element) { const value = points(element); const xs = value.map(p => p.xMm), ys = value.map(p => p.yMm); return xs.length ? { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) } : null; }
    function map(element, mapper) {
        const next = JSON.parse(JSON.stringify(element));
        if (next.type === "stroke") next.points = next.points.map(mapper);
        else if (["line", "arrow", "dimension"].includes(next.type)) { next.start = mapper(next.start); next.end = mapper(next.end); if (next.type === "dimension") next.valueMm = Math.round(Math.hypot(next.end.xMm - next.start.xMm, next.end.yMm - next.start.yMm) * 10) / 10; }
        else if (["rect", "ellipse"].includes(next.type)) { const start = mapper({ xMm: next.xMm, yMm: next.yMm }); const end = mapper({ xMm: next.xMm + next.widthMm, yMm: next.yMm + next.heightMm }); next.xMm = Math.min(start.xMm, end.xMm); next.yMm = Math.min(start.yMm, end.yMm); next.widthMm = Math.max(1, Math.abs(end.xMm - start.xMm)); next.heightMm = Math.max(1, Math.abs(end.yMm - start.yMm)); }
        else if (next.type === "text") next.position = mapper(next.position);
        return next;
    }
    function translate(element, dxMm, dyMm, canvas) {
        const box = bounds(element); if (!box) return element;
        const dx = Math.max(-box.minX, Math.min(Number(canvas.widthMm) - box.maxX, dxMm)); const dy = Math.max(-box.minY, Math.min(Number(canvas.heightMm) - box.maxY, dyMm));
        return map(element, point => ({ xMm: point.xMm + dx, yMm: point.yMm + dy }));
    }
    function resize(element, handle, target, canvas) {
        const box = bounds(element); if (!box) return element; const startHandle = handle === "resize-start"; const anchor = startHandle ? { xMm: box.maxX, yMm: box.maxY } : { xMm: box.minX, yMm: box.minY };
        const resolved = { xMm: Math.max(0, Math.min(Number(canvas.widthMm), target.xMm)), yMm: Math.max(0, Math.min(Number(canvas.heightMm), target.yMm)) };
        const oldWidth = Math.max(1, box.maxX - box.minX), oldHeight = Math.max(1, box.maxY - box.minY); const newWidth = Math.max(4, Math.abs(resolved.xMm - anchor.xMm)), newHeight = Math.max(4, Math.abs(resolved.yMm - anchor.yMm));
        return map(element, point => ({ xMm: anchor.xMm + (point.xMm - anchor.xMm) * (newWidth / oldWidth), yMm: anchor.yMm + (point.yMm - anchor.yMm) * (newHeight / oldHeight) }));
    }
    function replace(document, element) { return { ...document, elements: document.elements.map(item => item.id === element.id ? element : item) }; }
    root.ElementTransform = Object.freeze({ bounds, translate, resize, replace });
})();
