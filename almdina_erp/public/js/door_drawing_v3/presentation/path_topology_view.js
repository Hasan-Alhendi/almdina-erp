(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const Base = root.ShapeView;
    const G = root.Geometry;
    const D = root.DocumentModel;
    if (!Base || !G || !D) throw new Error("Door Drawing V3 view stack must load before path topology view");

    function selectedIds(c) {
        const values = Array.isArray(c && c.selectedIds) && c.selectedIds.length
            ? c.selectedIds
            : (c && c.selectedId ? [c.selectedId] : []);
        return [...new Set(values.filter(Boolean).map(String))];
    }
    function selectedPaths(c) {
        const document = c.history.current();
        return selectedIds(c)
            .map(id => D.objectById(document, id))
            .filter(object => object && object.type === G.PATH_TYPE);
    }
    function selectedNodes(c, object) {
        const values = Array.isArray(c.selectedNodeIndices) && c.selectedNodeIndices.length
            ? c.selectedNodeIndices
            : (Number.isInteger(c.selectedNodeIndex) ? [c.selectedNodeIndex] : []);
        return [...new Set(values.map(Number).filter(index => Number.isInteger(index) && index >= 0 && index < object.geometry.points.length))];
    }
    function selectedSegments(c, object) {
        const count = G.pathSegments(object).length;
        return [...new Set((c.selectedSegmentIndices || []).map(Number).filter(index => Number.isInteger(index) && index >= 0 && index < count))];
    }

    function icon(name) {
        const paths = {
            join: '<path d="M4 12h5m6 0h5M9 8v8m6-8v8"/>',
            close: '<path d="M6 7l6-3 6 4v8l-6 4-6-4V7z"/><circle cx="6" cy="7" r="1.4"/><circle cx="18" cy="8" r="1.4"/>',
            open: '<path d="M6 7l6-3 6 4v5m-2.5 4L12 20l-6-4V7"/><circle cx="6" cy="7" r="1.4"/><circle cx="15.5" cy="17" r="1.4"/>',
            reverse: '<path d="M7 7h8a4 4 0 014 4v1m0 0l-3-3m3 3l-3 3M17 17H9a4 4 0 01-4-4v-1m0 0l3 3m-3-3l3-3"/>',
            splitNode: '<path d="M5 12h5m4 0h5"/><circle cx="12" cy="12" r="2.2"/><path d="M10.5 6l3 12"/>',
            splitSegment: '<path d="M4 12h16"/><path d="M12 5v14"/><circle cx="12" cy="12" r="2"/>',
        };
        return `<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${paths[name] || ""}</svg>`;
    }

    function button(action, iconName, label, title) {
        const element = document.createElement("button");
        element.type = "button";
        element.className = "ddv3-topology-control";
        element.dataset.ddv3PathTopologyAction = action;
        element.title = title;
        element.setAttribute("aria-label", title);
        element.innerHTML = `${icon(iconName)}<span>${label}</span>`;
        return element;
    }

    function ensureBar(c) {
        const workspace = c.root.querySelector(".ddv3-workspace") || c.root;
        let bar = workspace.querySelector(".ddv3-bezier-contextbar");
        if (!bar) {
            bar = document.createElement("div");
            bar.className = "ddv3-bezier-contextbar";
            bar.dir = "rtl";
            workspace.appendChild(bar);
        }
        return bar;
    }

    function decorate(c) {
        if (!c || !c.root || c.readOnly) return;
        const bar = ensureBar(c);
        bar.querySelectorAll(".ddv3-topology-control, .ddv3-topology-separator").forEach(element => element.remove());
        const paths = selectedPaths(c);
        const controls = [];

        if (paths.length === 2 && paths.every(path => !path.geometry.closed)) {
            controls.push(button("join", "join", "ربط", "ربط أقرب نهايتين للمسارين دون تحريكهما"));
        } else if (paths.length === 1) {
            const object = paths[0];
            controls.push(button(
                "toggle-closed",
                object.geometry.closed ? "open" : "close",
                object.geometry.closed ? "فتح" : "إغلاق",
                object.geometry.closed ? "فتح المسار عند العقدة المحددة" : "إغلاق المسار بخط بين النهايتين"
            ));
            controls.push(button("reverse", "reverse", "عكس", "عكس اتجاه المسار مع الحفاظ على منحنيات Bezier"));

            const nodes = selectedNodes(c, object);
            if (nodes.length === 1 && (object.geometry.closed || (nodes[0] > 0 && nodes[0] < object.geometry.points.length - 1))) {
                controls.push(button("split-node", "splitNode", "قص عند النقطة", "فتح أو تقسيم المسار عند النقطة المحددة"));
            }
            const segments = selectedSegments(c, object);
            if (segments.length === 1) {
                controls.push(button("split-segment", "splitSegment", "قص الضلع", "تقسيم المسار في منتصف الضلع المحدد بدقة"));
            }
        }

        if (controls.length) {
            if (bar.children.length) {
                const separator = document.createElement("span");
                separator.className = "ddv3-topology-separator";
                separator.setAttribute("aria-hidden", "true");
                bar.appendChild(separator);
            }
            controls.forEach(control => bar.appendChild(control));
            bar.classList.add("is-visible");
        } else if (!bar.children.length) {
            bar.classList.remove("is-visible");
        }
    }

    function schedule(c) {
        if (!c || c.__pathTopologyViewScheduled) return;
        c.__pathTopologyViewScheduled = true;
        const run = () => {
            c.__pathTopologyViewScheduled = false;
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
    root.PathTopologyView = Object.freeze({ selectedIds, selectedPaths, selectedNodes, selectedSegments, decorate, schedule });
})();
