(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    const D = root.DocumentModel;
    const T = root.PathTopologyDomain;
    const View = root.PathTopologyView;
    const Editor = root.Editor;
    if (!G || !D || !T || !View || !Editor) throw new Error("Door Drawing V3 path topology dependencies must load first");

    let sequence = 0;
    function nextId() { sequence += 1; return `path-${Date.now()}-split-${sequence}`; }
    function ids(c) {
        const values = Array.isArray(c.selectedIds) && c.selectedIds.length ? c.selectedIds : (c.selectedId ? [c.selectedId] : []);
        return [...new Set(values.filter(Boolean).map(String))];
    }
    function selectedPaths(c) {
        const document = c.history.current();
        return ids(c).map(id => D.objectById(document, id)).filter(object => object && object.type === G.PATH_TYPE);
    }
    function selectedNodes(c, object) {
        const values = Array.isArray(c.selectedNodeIndices) && c.selectedNodeIndices.length ? c.selectedNodeIndices : (Number.isInteger(c.selectedNodeIndex) ? [c.selectedNodeIndex] : []);
        return [...new Set(values.map(Number).filter(index => Number.isInteger(index) && index >= 0 && index < object.geometry.points.length))];
    }
    function selectedSegments(c, object) {
        const count = G.pathSegments(object).length;
        return [...new Set((c.selectedSegmentIndices || []).map(Number).filter(index => Number.isInteger(index) && index >= 0 && index < count))];
    }
    function render(c) { root.ShapeView.render(c); View.schedule(c); }
    function execute(c, document, label) { c.history.execute(document, label); c.dirty = true; render(c); }
    function alert(message, indicator = "orange") {
        if (window.frappe && frappe.show_alert) frappe.show_alert({ message, indicator });
    }
    function resetSubselection(c) {
        c.nodeEditId = "";
        c.selectedNodeIndex = null;
        c.selectedNodeIndices = [];
        c.selectedSegmentIndices = [];
        c.previewObject = null;
    }
    function selectObjects(c, objectIds, primary = null) {
        const clean = [...new Set((objectIds || []).filter(Boolean).map(String))];
        c.selectedIds = clean;
        c.selectedId = primary && clean.includes(String(primary)) ? String(primary) : (clean[clean.length - 1] || "");
        resetSubselection(c);
    }

    function toggleClosed(c) {
        const paths = selectedPaths(c);
        if (paths.length !== 1) return false;
        const object = paths[0];
        const nodes = selectedNodes(c, object);
        const breakIndex = object.geometry.closed && nodes.length === 1 ? nodes[0] : 0;
        const next = T.togglePathClosed(object, breakIndex);
        if (next === object) {
            alert(object.geometry.closed ? "تعذر فتح المسار" : "يحتاج إغلاق المسار إلى ثلاث نقاط على الأقل");
            return true;
        }
        selectObjects(c, [next.id], next.id);
        execute(c, D.replaceObject(c.history.current(), next), object.geometry.closed ? "Open path" : "Close path");
        return true;
    }

    function reverseSelected(c) {
        const paths = selectedPaths(c);
        if (paths.length !== 1) return false;
        const next = T.reversePath(paths[0]);
        selectObjects(c, [next.id], next.id);
        execute(c, D.replaceObject(c.history.current(), next), "Reverse path direction");
        return true;
    }

    function applySplit(c, results, label) {
        if (!Array.isArray(results) || !results.length) return false;
        let document = D.replaceObject(c.history.current(), results[0]);
        for (const object of results.slice(1)) document = D.addObject(document, object);
        const resultIds = results.map(object => object.id);
        selectObjects(c, resultIds, resultIds[resultIds.length - 1]);
        execute(c, document, label);
        return true;
    }

    function splitAtNode(c) {
        const paths = selectedPaths(c);
        if (paths.length !== 1) return false;
        const object = paths[0];
        const nodes = selectedNodes(c, object);
        if (nodes.length !== 1) return false;
        const result = T.splitPathAtNode(object, nodes[0], nextId());
        if (!result) { alert("اختر نقطة داخلية لتقسيم المسار المفتوح"); return true; }
        return applySplit(c, result, object.geometry.closed ? "Cut closed path at node" : "Split path at node");
    }

    function splitAtSegment(c) {
        const paths = selectedPaths(c);
        if (paths.length !== 1) return false;
        const object = paths[0];
        const segments = selectedSegments(c, object);
        if (segments.length !== 1) return false;
        const result = T.splitPathAtSegmentMidpoint(object, segments[0], nextId());
        if (!result) { alert("تعذر تقسيم هذا الضلع"); return true; }
        return applySplit(c, result, object.geometry.closed ? "Cut closed path at segment midpoint" : "Split path at segment midpoint");
    }

    function joinSelected(c) {
        const paths = selectedPaths(c);
        if (paths.length !== 2 || paths.some(path => path.geometry.closed)) return false;
        const result = T.joinOpenPaths(paths[0], paths[1]);
        if (!result) { alert("اختر مسارين مفتوحين للربط"); return true; }
        let document = D.replaceObject(c.history.current(), result.object);
        document = D.removeObject(document, result.consumedId);
        selectObjects(c, [result.object.id], result.object.id);
        execute(c, document, "Join open paths");
        if (result.gapMm > G.EPSILON_MM) alert(`تم ربط المسارين بخط مستقيم بطول ${result.gapMm} mm`, "blue");
        return true;
    }

    function handleAction(c, action) {
        if (!action || c.readOnly) return false;
        if (action === "toggle-closed") return toggleClosed(c);
        if (action === "reverse") return reverseSelected(c);
        if (action === "split-node") return splitAtNode(c);
        if (action === "split-segment") return splitAtSegment(c);
        if (action === "join") return joinSelected(c);
        return false;
    }

    function schedule(c) {
        const run = () => View.schedule(c);
        if (typeof queueMicrotask === "function") queueMicrotask(run);
        else Promise.resolve().then(run);
    }

    function install(c) {
        if (!c || !c.root || c.__pathTopologyInstalled) return c;
        c.__pathTopologyInstalled = true;

        const onClickCapture = event => {
            const action = event.target && event.target.closest ? event.target.closest("[data-ddv3-path-topology-action]") : null;
            if (action && handleAction(c, action.dataset.ddv3PathTopologyAction)) {
                event.preventDefault();
                event.stopImmediatePropagation();
                return;
            }
            const legacyToggle = event.target && event.target.closest ? event.target.closest("[data-ddv3-path-toggle]") : null;
            if (legacyToggle && toggleClosed(c)) {
                event.preventDefault();
                event.stopImmediatePropagation();
                return;
            }
            schedule(c);
        };
        const onSelectionSettled = () => schedule(c);
        const onKeyDown = event => {
            if (c.readOnly) return;
            const target = event.target;
            if (target && ((target.matches && target.matches("input, textarea, select")) || target.isContentEditable)) return;
            const key = String(event.key || "").toLowerCase();
            if ((event.ctrlKey || event.metaKey) && !event.shiftKey && !event.altKey && key === "j" && joinSelected(c)) {
                event.preventDefault();
                event.stopImmediatePropagation();
            }
        };

        c.root.addEventListener("click", onClickCapture, true);
        c.root.addEventListener("pointerup", onSelectionSettled, false);
        c.root.addEventListener("dblclick", onSelectionSettled, false);
        window.addEventListener("keydown", onKeyDown, true);
        View.decorate(c);

        if (c.dialog && c.dialog.$wrapper) {
            c.dialog.$wrapper.one("hidden.bs.modal.ddv3-path-topology-cleanup", () => {
                c.root.removeEventListener("click", onClickCapture, true);
                c.root.removeEventListener("pointerup", onSelectionSettled, false);
                c.root.removeEventListener("dblclick", onSelectionSettled, false);
                window.removeEventListener("keydown", onKeyDown, true);
            });
        }
        return c;
    }

    const originalOpen = Editor.open.bind(Editor);
    const originalView = Editor.view.bind(Editor);
    root.Editor = Object.freeze({
        open(frm, row, options = {}) { return install(originalOpen(frm, row, options)); },
        view(frm, row) { return install(originalView(frm, row)); },
    });
    root.PathTopology = Object.freeze({
        install, handleAction, toggleClosed, reverseSelected, splitAtNode, splitAtSegment, joinSelected,
    });
})();
