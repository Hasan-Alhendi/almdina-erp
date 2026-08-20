(() => {
    "use strict";
    const root = window.AlmdinaSpecialShapeDocumentation = window.AlmdinaSpecialShapeDocumentation || Object.create(null);
    const DEFINITIONS = Object.freeze([
        Object.freeze({ id: "clipped-corner", label: "زاوية مقصوصة", icon: "⌜" }),
        Object.freeze({ id: "top-arch", label: "قوس علوي", icon: "∩" }),
        Object.freeze({ id: "side-arch", label: "قوس جانبي", icon: "◖" }),
        Object.freeze({ id: "trapezoid", label: "شبه منحرف", icon: "⏢" }),
        Object.freeze({ id: "inner-opening", label: "فتحة داخلية", icon: "▣" }),
        Object.freeze({ id: "slanted-edge", label: "حافة مائلة", icon: "◩" }),
    ]);
    const p = (xMm, yMm) => ({ xMm, yMm });
    function documentContract() {
        if (!root.Document) throw new Error("Special-shape document contract is unavailable");
        return root.Document;
    }
    function stroke(points, closed = true) { return { id: documentContract().id("template"), type: "stroke", points, closed, style: { color: "#1463e6", width: 3 } }; }
    function build(templateId, canvas) {
        const D = documentContract();
        const w = Number(canvas.widthMm), h = Number(canvas.heightMm), inset = Math.max(16, Math.min(w, h) * 0.06);
        const l = inset, r = w - inset, t = inset, b = h - inset;
        const midX = w / 2, midY = h / 2;
        let points;
        if (templateId === "clipped-corner") points = [p(l, t), p(r - w * 0.22, t), p(r, t + h * 0.18), p(r, b), p(l, b), p(l, t)];
        else if (templateId === "top-arch") points = [p(l, b), p(l, t + h * 0.16), p(l + w * 0.08, t + h * 0.07), p(midX, t), p(r - w * 0.08, t + h * 0.07), p(r, t + h * 0.16), p(r, b), p(l, b)];
        else if (templateId === "side-arch") points = [p(l, t), p(r - w * 0.16, t), p(r - w * 0.07, t + h * 0.08), p(r, midY), p(r - w * 0.07, b - h * 0.08), p(r - w * 0.16, b), p(l, b), p(l, t)];
        else if (templateId === "trapezoid") points = [p(l + w * 0.16, t), p(r - w * 0.16, t), p(r, b), p(l, b), p(l + w * 0.16, t)];
        else if (templateId === "slanted-edge") points = [p(l, t + h * 0.12), p(r, t), p(r, b), p(l, b), p(l, t + h * 0.12)];
        else if (templateId === "inner-opening") return [
            { id: D.id("template"), type: "rect", xMm: l, yMm: t, widthMm: r - l, heightMm: b - t, style: { color: "#1463e6", width: 3 } },
            { id: D.id("opening"), type: "rect", xMm: w * 0.25, yMm: h * 0.25, widthMm: w * 0.5, heightMm: h * 0.5, style: { color: "#f59e0b", width: 3 } },
        ];
        else return [];
        return [stroke(points)];
    }
    function apply(document, templateId) {
        return documentContract().replaceElements(document, build(templateId, document.canvas), { templateId, source: document.reference ? "mixed" : "template" });
    }
    root.Templates = Object.freeze({ DEFINITIONS, build, apply });
})();
