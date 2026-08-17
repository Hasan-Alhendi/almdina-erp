(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    const D = root.DocumentModel;
    const B = root.BooleanGeometryDomain;
    const View = root.BooleanOperationsView;
    const Editor = root.Editor;
    if (!G || !D || !B || !View || !Editor) throw new Error("Door Drawing V3 boolean dependencies must load first");

    let sequence = 0;
    const LABELS = Object.freeze({
        union: "Boolean union",
        subtract: "Boolean subtract",
        intersect: "Boolean intersect",
        exclude: "Boolean exclude",
    });

    function nextId(document) {
        let candidate;
        do {
            sequence += 1;
            candidate = `path-${Date.now()}-boolean-${sequence}`;
        } while (D.objectById(document, candidate));
        return candidate;
    }

    function alert(message, indicator = "orange") {
        if (window.frappe && frappe.show_alert) frappe.show_alert({ message, indicator });
    }

    function failureMessage(reason) {
        if (reason === "self_intersection") return "لا يمكن تنفيذ العملية: أحد الشكلين يحتوي على تقاطع ذاتي. أصلح المسار أولًا.";
        if (reason === "unsupported_operand") return "عمليات الأشكال تحتاج شكلين مغلقين: مستطيل أو دائرة أو مسار مغلق.";
        if (reason === "invalid_geometry") return "تعذر بناء حدود هندسية صالحة للشكلين.";
        return "تعذر تنفيذ عملية الأشكال على الهندسة الحالية.";
    }

    function clearSubselection(c) {
        c.nodeEditId = "";
        c.selectedNodeIndex = null;
        c.selectedNodeIndices = [];
        c.selectedSegmentIndices = [];
        c.previewObject = null;
    }

    function selectResult(c, ids) {
        const clean = [...new Set((ids || []).filter(Boolean).map(String))];
        c.selectedIds = clean;
        c.selectedId = clean[clean.length - 1] || "";
        clearSubselection(c);
    }

    function render(c) {
        root.ShapeView.render(c);
        View.schedule(c);
    }

    function execute(c, operation) {
        if (!c || c.readOnly || !B.OPERATIONS.includes(operation)) return false;
        const operands = View.selectedOperands(c);
        if (operands.length !== 2) return false;
        const primary = operands[0];
        const secondary = operands[1];
        const result = B.booleanContours(primary, secondary, operation, { toleranceMm: B.DEFAULT_TOLERANCE_MM });
        if (!result.ok) {
            alert(failureMessage(result.reason));
            return true;
        }

        let document = c.history.current();
        document = D.removeObject(document, primary.id);
        document = D.removeObject(document, secondary.id);
        const outputIds = [];

        result.contours.forEach((contour, index) => {
            const id = index === 0 ? String(primary.id) : nextId(document);
            const object = G.path(id, contour, true, primary.style || {});
            document = D.addObject(document, object);
            outputIds.push(id);
        });

        selectResult(c, outputIds);
        c.history.execute(document, LABELS[operation] || "Boolean operation");
        c.dirty = true;
        render(c);

        if (!result.contours.length) {
            alert("العملية صحيحة هندسيًا لكن نتيجتها فارغة. يمكنك التراجع مباشرةً بـ Ctrl+Z.", "blue");
        } else if (result.approximated) {
            alert(`تم تحويل المنحنيات إلى حدود فعلية بدقة ${result.toleranceMm} mm قبل العملية.`, "blue");
        }
        return true;
    }

    function install(c) {
        if (!c || !c.root || c.__booleanOperationsInstalled) return c;
        c.__booleanOperationsInstalled = true;

        const onClickCapture = event => {
            const button = event.target && event.target.closest ? event.target.closest("[data-ddv3-boolean-action]") : null;
            if (button && execute(c, String(button.dataset.ddv3BooleanAction || ""))) {
                event.preventDefault();
                event.stopImmediatePropagation();
                return;
            }
            View.schedule(c);
        };
        const onSelectionSettled = () => View.schedule(c);

        c.root.addEventListener("click", onClickCapture, true);
        c.root.addEventListener("pointerup", onSelectionSettled, false);
        c.root.addEventListener("dblclick", onSelectionSettled, false);
        View.decorate(c);

        if (c.dialog && c.dialog.$wrapper) {
            c.dialog.$wrapper.one("hidden.bs.modal.ddv3-boolean-cleanup", () => {
                c.root.removeEventListener("click", onClickCapture, true);
                c.root.removeEventListener("pointerup", onSelectionSettled, false);
                c.root.removeEventListener("dblclick", onSelectionSettled, false);
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
    root.BooleanOperations = Object.freeze({ install, execute, failureMessage });
})();
