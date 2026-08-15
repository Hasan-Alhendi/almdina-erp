(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const Base = root.ShapeView;
    const D = root.DocumentModel;
    const B = root.BooleanGeometryDomain;
    if (!Base || !D || !B) throw new Error("Door Drawing V3 boolean domain and view stack must load before boolean presentation");

    function selectedIds(c) {
        const values = Array.isArray(c && c.selectedIds) && c.selectedIds.length
            ? c.selectedIds
            : (c && c.selectedId ? [c.selectedId] : []);
        return [...new Set(values.filter(Boolean).map(String))];
    }

    function selectedOperands(c) {
        if (!c || !c.history) return Object.freeze([]);
        const ids = selectedIds(c);
        if (ids.length !== 2) return Object.freeze([]);
        const document = c.history.current();
        const objects = ids.map(id => D.objectById(document, id));
        if (objects.some(object => !B.isBooleanOperand(object))) return Object.freeze([]);
        const activeId = ids.includes(String(c.selectedId || "")) ? String(c.selectedId) : ids[ids.length - 1];
        const primary = objects.find(object => String(object.id) === activeId) || objects[objects.length - 1];
        const secondary = objects.find(object => String(object.id) !== String(primary.id));
        return Object.freeze([primary, secondary]);
    }

    function icon(name) {
        const paths = {
            union: '<path d="M5 5h9v4h5v10h-9v-4H5z"/><path d="M10 9h4v6h-4z" class="ddv3-boolean-overlap"/>',
            subtract: '<path d="M5 5h10v10H5z"/><path d="M11 9h8v10h-8z" class="ddv3-boolean-cut"/>',
            intersect: '<path d="M5 5h10v10H5z" class="ddv3-boolean-muted"/><path d="M11 9h8v10h-8z" class="ddv3-boolean-muted"/><path d="M11 9h4v6h-4z"/>',
            exclude: '<path d="M5 5h10v4h-4v6H5z"/><path d="M15 9h4v10h-8v-4h4z"/>',
        };
        return `<svg viewBox="0 0 24 24" aria-hidden="true" fill="currentColor">${paths[name] || ""}</svg>`;
    }

    function button(action, label, title) {
        return `<button type="button" data-ddv3-boolean-action="${action}" title="${title}" aria-label="${title}">${icon(action)}<span>${label}</span></button>`;
    }

    function ensureBar(c) {
        const workspace = c.root.querySelector(".ddv3-workspace") || c.root;
        let bar = workspace.querySelector(".ddv3-boolean-actionbar");
        if (!bar) {
            bar = document.createElement("div");
            bar.className = "ddv3-boolean-actionbar";
            bar.dir = "rtl";
            workspace.appendChild(bar);
        }
        return bar;
    }

    function decorate(c) {
        if (!c || !c.root || c.readOnly) return;
        const bar = ensureBar(c);
        const operands = selectedOperands(c);
        if (operands.length !== 2) {
            bar.innerHTML = "";
            bar.classList.remove("is-visible");
            return;
        }
        bar.innerHTML = [
            '<span class="ddv3-boolean-summary" title="عمليات على شكلين مغلقين">أشكال</span>',
            button("union", "دمج", "دمج الشكلين Union"),
            button("subtract", "طرح", "طرح الشكل الآخر من الشكل المحدد أخيرًا A − B"),
            button("intersect", "تقاطع", "الإبقاء على منطقة التقاطع فقط Intersect"),
            button("exclude", "استبعاد", "استبعاد منطقة التداخل Exclude / XOR"),
        ].join("");
        bar.classList.add("is-visible");
    }

    function schedule(c) {
        if (!c || c.__booleanViewScheduled) return;
        c.__booleanViewScheduled = true;
        const run = () => {
            c.__booleanViewScheduled = false;
            decorate(c);
        };
        if (typeof requestAnimationFrame === "function") requestAnimationFrame(run);
        else setTimeout(run, 0);
    }

    function render(c) {
        const result = Base.render(c);
        decorate(c);
        return result;
    }

    root.ShapeView = Object.freeze({ ...Base, render });
    root.BooleanOperationsView = Object.freeze({ selectedIds, selectedOperands, decorate, schedule });
})();
