(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    const D = root.DocumentModel;
    const Editor = root.Editor;
    if (!G || !D || !Editor || !G.PATH_TYPE) throw new Error("Door Drawing V3 path domain and editor must load before node selection policy");

    function selectionButton(c, event) {
        const button = event.target && event.target.closest ? event.target.closest('[data-ddv3-tool="select"]') : null;
        return button && c.root.contains(button) ? button : null;
    }

    function pathById(c, id) {
        const object = D.objectById(c.history.current(), id);
        return object && object.type === G.PATH_TYPE ? object : null;
    }

    function validIndices(values, max) {
        return [...new Set((Array.isArray(values) ? values : []).map(Number)
            .filter(index => Number.isInteger(index) && index >= 0 && index <= max))].sort((a, b) => a - b);
    }

    function render(c) {
        root.ShapeView.render(c);
        if (root.VectorEditingView) root.VectorEditingView.schedule(c);
        if (root.BezierPathView) root.BezierPathView.schedule(c);
    }

    function rememberNodeEdit(c, event) {
        if (!selectionButton(c, event) || !c.nodeEditId) return;
        const object = pathById(c, c.nodeEditId);
        if (!object) return;
        c.__selectionToolNodeEditSnapshot = Object.freeze({
            objectId: String(object.id),
            selectedNodeIndex: Number.isInteger(c.selectedNodeIndex) ? Number(c.selectedNodeIndex) : null,
            selectedNodeIndices: Object.freeze((c.selectedNodeIndices || []).map(Number)),
            selectedSegmentIndices: Object.freeze((c.selectedSegmentIndices || []).map(Number)),
        });
    }

    function restoreNodeEdit(c, event) {
        if (!selectionButton(c, event)) return;
        const snapshot = c.__selectionToolNodeEditSnapshot;
        c.__selectionToolNodeEditSnapshot = null;
        if (!snapshot || c.readOnly || c.tool !== "select") return;
        const object = pathById(c, snapshot.objectId);
        if (!object) return;

        const maxNode = object.geometry.points.length - 1;
        const nodeIndices = validIndices(snapshot.selectedNodeIndices, maxNode);
        const segmentCount = G.pathSegments(object).length;
        const segmentIndices = validIndices(snapshot.selectedSegmentIndices, Math.max(-1, segmentCount - 1));

        c.selectedId = String(object.id);
        c.selectedIds = [String(object.id)];
        c.nodeEditId = String(object.id);
        c.selectedNodeIndices = nodeIndices;
        c.selectedNodeIndex = nodeIndices.length === 1
            ? nodeIndices[0]
            : (Number.isInteger(snapshot.selectedNodeIndex) && snapshot.selectedNodeIndex <= maxNode ? snapshot.selectedNodeIndex : null);
        c.selectedSegmentIndices = segmentIndices;
        render(c);
    }

    function editingTarget(event) {
        const target = event && event.target;
        return Boolean(target && ((target.matches && target.matches("input, textarea, select")) || target.isContentEditable));
    }

    function enterSelectedPath(c, event) {
        if (!event || event.key !== "Enter" || event.ctrlKey || event.metaKey || event.altKey || editingTarget(event)) return false;
        if (c.readOnly || c.tool !== "select" || c.nodeEditId) return false;
        const object = pathById(c, c.selectedId);
        if (!object) return false;
        c.selectedId = String(object.id);
        c.selectedIds = [String(object.id)];
        c.nodeEditId = String(object.id);
        c.selectedNodeIndex = null;
        c.selectedNodeIndices = [];
        c.selectedSegmentIndices = [];
        render(c);
        event.preventDefault();
        event.stopPropagation();
        if (event.stopImmediatePropagation) event.stopImmediatePropagation();
        return true;
    }

    function install(c) {
        if (!c || !c.root || c.__nodeSelectionPolicyInstalled) return c;
        c.__nodeSelectionPolicyInstalled = true;
        c.__selectionToolNodeEditSnapshot = null;

        const onPointerDown = event => rememberNodeEdit(c, event);
        const onClick = event => restoreNodeEdit(c, event);
        const onKeyDown = event => enterSelectedPath(c, event);
        c.root.addEventListener("pointerdown", onPointerDown, true);
        // Bubble phase intentionally runs after the base tool switch. SmartPen may leave
        // node-edit mode in capture phase; this policy restores the user's vector-edit intent.
        c.root.addEventListener("click", onClick, false);
        window.addEventListener("keydown", onKeyDown, true);

        if (c.dialog && c.dialog.$wrapper) c.dialog.$wrapper.one("hidden.bs.modal.ddv3-node-selection-policy-cleanup", () => {
            c.root.removeEventListener("pointerdown", onPointerDown, true);
            c.root.removeEventListener("click", onClick, false);
            window.removeEventListener("keydown", onKeyDown, true);
            c.__selectionToolNodeEditSnapshot = null;
        });
        return c;
    }

    const originalOpen = Editor.open.bind(Editor);
    const originalView = Editor.view.bind(Editor);
    root.Editor = Object.freeze({
        ...Editor,
        open(frm, row, options = {}) { return install(originalOpen(frm, row, options)); },
        view(frm, row) { return install(originalView(frm, row)); },
    });
    root.NodeSelectionPolicy = Object.freeze({ install, rememberNodeEdit, restoreNodeEdit, enterSelectedPath });
})();
