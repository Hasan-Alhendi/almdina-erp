(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const Base = root.ShapeView;
    if (!Base) throw new Error("Door Drawing V3 view must load before advanced snap feedback");

    function esc(value) {
        const text = String(value ?? "");
        if (window.frappe && frappe.utils && frappe.utils.escape_html) return frappe.utils.escape_html(text);
        return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\"/g, "&quot;");
    }

    function label(c, point, text) {
        const p = Base.worldToScreen(c, point);
        const width = Math.max(34, String(text).length * 7 + 14);
        return `<g class="ddv3-advanced-snap-label" transform="translate(${p.x + 12} ${p.y - 12})"><rect x="0" y="-15" width="${width}" height="21" rx="5"/><text x="7" y="0">${esc(text)}</text></g>`;
    }

    function guideMarkup(c) {
        const guide = c && c.snapState && c.snapState.smartGuide;
        if (!guide || !guide.point) return "";
        const p = Base.worldToScreen(c, guide.point);
        if (guide.type === "intersection") {
            return `<g class="ddv3-advanced-snap is-intersection" transform="translate(${p.x} ${p.y})"><circle r="6"/><path d="M-5 -5L5 5M5 -5L-5 5"/></g>${label(c, guide.point, "تقاطع")}`;
        }
        if (guide.type === "perpendicular") {
            return `<g class="ddv3-advanced-snap is-perpendicular" transform="translate(${p.x} ${p.y})"><path d="M-7 1H1V-7M-7 1V-7"/></g>${label(c, guide.point, "عمودي")}`;
        }
        if (guide.type === "parallel" || guide.type === "parallel-equal") {
            const text = guide.type === "parallel-equal" ? "متوازٍ · نفس الطول" : "متوازٍ";
            return `<g class="ddv3-advanced-snap is-parallel" transform="translate(${p.x} ${p.y})"><path d="M-7 4L-1 -4M1 4L7 -4"/></g>${label(c, guide.point, text)}`;
        }
        return "";
    }

    function render(c) {
        const result = Base.render(c);
        const markup = guideMarkup(c);
        if (markup && c && c.canvas) c.canvas.insertAdjacentHTML("beforeend", `<g class="ddv3-advanced-snap-layer">${markup}</g>`);
        return result;
    }

    root.ShapeView = Object.freeze({ ...Base, render, advancedSnapMarkup: guideMarkup });
    root.AdvancedSnapView = Object.freeze({ guideMarkup });
})();
