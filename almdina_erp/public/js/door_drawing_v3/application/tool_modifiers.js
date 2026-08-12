(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    const D = root.DocumentModel;
    const S = root.Snapping;
    const V = root.ShapeView;
    const M = root.ToolModifierPolicy;
    const Editor = root.Editor;
    if (!G || !D || !S || !V || !M || !Editor) throw new Error("Door Drawing V3 editor must load before tool modifiers");

    let sequence = 0;
    function nextId(type = "line") { sequence += 1; return `${type}-modifier-${Date.now()}-${sequence}`; }
    function render(c) { V.render(c); }
    function dialogVisible(c) { return Boolean(c && c.dialog && c.dialog.$wrapper && c.dialog.$wrapper.is(":visible")); }
    function editingText(event) {
        const target = event && event.target;
        return Boolean(target && ((target.matches && target.matches("input, textarea, select")) || target.isContentEditable));
    }

    function clearBaseDrafts(c) {
        c.draftStart = null;
        c.draftObject = null;
        c.arcDraft = null;
        c.clickDraft = null;
        c.precision = null;
        c.snapState = null;
    }

    function clearNodeEdit(c) {
        c.nodeEditId = "";
        c.selectedNodeIndex = null;
        c.smartNodeGesture = null;
        c.previewObject = null;
    }

    function effectiveTool(c) {
        return M.effectiveTool(c.persistentTool || c.tool, Boolean(c.ctrlSelectHeld));
    }

    function rememberTool(c, tool) {
        c.persistentTool = M.normalizeTool(tool, c.persistentTool || c.tool || "select");
        return c.persistentTool;
    }

    function syncEffectiveTool(c) {
        const expected = effectiveTool(c);
        if (c.tool !== expected) c.tool = expected;
        render(c);
        return expected;
    }

    function scheduleEffectiveTool(c) {
        Promise.resolve().then(() => {
            if (!dialogVisible(c)) return;
            syncEffectiveTool(c);
        });
    }

    function modifierState(c, event = {}) {
        return Object.freeze({
            altKey: Boolean(event.altKey || c.altHeld),
            shiftKey: Boolean(event.shiftKey || c.shiftHeld),
        });
    }

    function constraintMode(c, event = {}) {
        return M.penConstraint(modifierState(c, event));
    }

    function resolvePenStart(c, event) {
        return S.resolvePoint(c.history.current(), V.eventWorld(c, event), {
            viewportScale: c.viewport.scale,
            stickyTarget: c.snapState && c.snapState.target,
        });
    }

    function resolvePenEnd(c, gesture, rawPoint, mode) {
        const options = {
            viewportScale: c.viewport.scale,
            stickyTarget: c.snapState && c.snapState.target,
        };
        if (mode === M.PEN_CONSTRAINTS.AXIS) {
            options.anchor = gesture.start;
            options.axisLock = true;
            options.shiftKey = true;
        }
        return S.resolvePoint(c.history.current(), rawPoint, options);
    }

    function updateConstrainedPen(c, rawPoint, mode = null) {
        const gesture = c.modifierPenGesture;
        if (!gesture) return false;
        const activeMode = mode && mode !== M.PEN_CONSTRAINTS.FREEHAND ? mode : gesture.mode;
        const resolved = resolvePenEnd(c, gesture, rawPoint, activeMode);
        const endpoint = activeMode === M.PEN_CONSTRAINTS.AXIS
            ? M.constrainEndpoint(gesture.start, resolved.point, activeMode)
            : resolved.point;
        c.snapState = Object.freeze({ ...resolved, point: endpoint, axis: activeMode === M.PEN_CONSTRAINTS.AXIS ? resolved.axis : null });
        gesture.mode = activeMode;
        gesture.end = endpoint;
        c.penDraft = {
            points: [gesture.start, endpoint],
            pointer: endpoint,
            closeReady: false,
            freehand: false,
            stabilized: true,
            constrained: true,
            constraintMode: activeMode,
            inputKind: gesture.pointerType,
        };
        render(c);
        return true;
    }

    function beginConstrainedPen(c, event) {
        if (c.readOnly || c.spaceHeld || c.tool !== "pen" || event.button !== 0) return false;
        const mode = constraintMode(c, event);
        if (mode === M.PEN_CONSTRAINTS.FREEHAND) return false;
        const startSnap = resolvePenStart(c, event);
        c.modifierPenGesture = {
            pointerId: event.pointerId,
            pointerType: String(event.pointerType || "mouse").toLowerCase(),
            start: startSnap.point,
            end: startSnap.point,
            mode,
        };
        c.snapState = startSnap;
        c.penDraft = {
            points: [startSnap.point, startSnap.point],
            pointer: startSnap.point,
            closeReady: false,
            freehand: false,
            stabilized: true,
            constrained: true,
            constraintMode: mode,
            inputKind: c.modifierPenGesture.pointerType,
        };
        try { c.canvas.setPointerCapture(event.pointerId); } catch (error) { /* optional */ }
        render(c);
        return true;
    }

    function moveConstrainedPen(c, event) {
        const gesture = c.modifierPenGesture;
        if (!gesture || gesture.pointerId !== event.pointerId) return false;
        const liveMode = constraintMode(c, event);
        updateConstrainedPen(c, V.eventWorld(c, event), liveMode);
        return true;
    }

    function clearConstrainedPen(c, pointerId = null) {
        const gesture = c.modifierPenGesture;
        if (!gesture || (pointerId != null && gesture.pointerId !== pointerId)) return false;
        const activeId = gesture.pointerId;
        c.modifierPenGesture = null;
        c.penDraft = null;
        c.snapState = null;
        try { c.canvas.releasePointerCapture(activeId); } catch (error) { /* optional */ }
        render(c);
        return true;
    }

    function finishConstrainedPen(c, event) {
        const gesture = c.modifierPenGesture;
        if (!gesture || gesture.pointerId !== event.pointerId) return false;
        const liveMode = constraintMode(c, event);
        updateConstrainedPen(c, V.eventWorld(c, event), liveMode);
        const end = gesture.end;
        const start = gesture.start;
        c.modifierPenGesture = null;
        c.penDraft = null;
        c.snapState = null;
        try { c.canvas.releasePointerCapture(event.pointerId); } catch (error) { /* optional */ }
        if (!end || G.distance(start, end) < G.EPSILON_MM) {
            render(c);
            return true;
        }
        const object = G.line(nextId("line"), start, end);
        c.history.execute(D.addObject(c.history.current(), object), gesture.mode === M.PEN_CONSTRAINTS.AXIS ? "Axis-constrained pen line" : "Straight pen line");
        c.selectedId = object.id;
        c.nodeEditId = "";
        c.selectedNodeIndex = null;
        c.dirty = true;
        c.tool = effectiveTool(c);
        render(c);
        return true;
    }

    function promoteFreehandToConstraint(c, mode) {
        const stroke = c.penStroke;
        if (!stroke || c.modifierPenGesture || mode === M.PEN_CONSTRAINTS.FREEHAND) return false;
        const pointerId = stroke.pointerId;
        const start = stroke.startPoint;
        const raw = stroke.lastPoint || stroke.lastStablePoint || start;
        const pointerType = stroke.pointerType || "mouse";
        const smartPen = root.SmartPen;
        if (smartPen && typeof smartPen.cancelFreehandGesture === "function") smartPen.cancelFreehandGesture(c, pointerId);
        else {
            c.penStroke = null;
            c.penDraft = null;
            c.snapState = null;
        }
        c.modifierPenGesture = { pointerId, pointerType, start, end: start, mode };
        try { c.canvas.setPointerCapture(pointerId); } catch (error) { /* optional */ }
        updateConstrainedPen(c, raw, mode);
        return true;
    }

    function enterTemporarySelect(c) {
        if (c.ctrlSelectHeld) return false;
        rememberTool(c, c.persistentTool || c.tool);
        c.ctrlSelectHeld = true;
        clearBaseDrafts(c);
        if (c.modifierPenGesture) clearConstrainedPen(c);
        if (c.penStroke && root.SmartPen && typeof root.SmartPen.cancelFreehandGesture === "function") root.SmartPen.cancelFreehandGesture(c);
        c.tool = "select";
        render(c);
        return true;
    }

    function leaveTemporarySelect(c) {
        if (!c.ctrlSelectHeld) return false;
        c.ctrlSelectHeld = false;
        c.tool = M.normalizeTool(c.persistentTool || "select");
        render(c);
        return true;
    }

    function handleEscape(c, event) {
        let changed = false;
        if (c.modifierPenGesture) changed = clearConstrainedPen(c) || changed;
        if (c.penStroke && root.SmartPen && typeof root.SmartPen.cancelFreehandGesture === "function") changed = root.SmartPen.cancelFreehandGesture(c) || changed;
        if (c.draftObject || c.arcDraft || c.clickDraft || c.precision || c.draftStart) {
            clearBaseDrafts(c);
            changed = true;
        } else if (c.nodeEditId) {
            clearNodeEdit(c);
            changed = true;
        } else if (c.selectedId) {
            c.selectedId = "";
            c.previewObject = null;
            c.snapState = null;
            changed = true;
        }
        c.tool = effectiveTool(c);
        render(c);
        event.preventDefault();
        event.stopImmediatePropagation();
        return changed;
    }

    function install(c) {
        if (!c || !c.canvas || c.__toolModifiersInstalled) return c;
        c.__toolModifiersInstalled = true;
        c.persistentTool = M.normalizeTool(c.tool || "select");
        c.ctrlSelectHeld = false;
        c.altHeld = false;
        c.shiftHeld = false;
        c.modifierPenGesture = null;

        const onRootToolCapture = event => {
            const button = event.target.closest && event.target.closest("[data-ddv3-tool]");
            if (!button) return;
            rememberTool(c, button.dataset.ddv3Tool);
            scheduleEffectiveTool(c);
        };

        const onPointerDownCapture = event => {
            if (beginConstrainedPen(c, event)) {
                event.preventDefault();
                event.stopImmediatePropagation();
            }
        };
        const onPointerMoveCapture = event => {
            if (moveConstrainedPen(c, event)) {
                event.preventDefault();
                event.stopImmediatePropagation();
            }
        };
        const onPointerUpCapture = event => {
            if (finishConstrainedPen(c, event)) {
                event.preventDefault();
                event.stopImmediatePropagation();
            }
        };
        const onPointerCancelCapture = event => {
            if (clearConstrainedPen(c, event.pointerId)) {
                event.preventDefault();
                event.stopImmediatePropagation();
            }
        };
        const onPointerDownRestore = () => scheduleEffectiveTool(c);
        const onPointerUpRestore = () => scheduleEffectiveTool(c);
        const onWindowPointerUp = () => {
            if (c.ctrlSelectHeld) Promise.resolve().then(() => { if (dialogVisible(c) && c.ctrlSelectHeld) { c.tool = "select"; render(c); } });
        };

        const onKeyDownCapture = event => {
            if (!dialogVisible(c) || c.readOnly || editingText(event)) return;
            const key = String(event.key || "");
            const lower = key.toLowerCase();
            if (key === "Control") {
                enterTemporarySelect(c);
                return;
            }
            if (key === "Alt") {
                c.altHeld = true;
                if (M.normalizeTool(c.persistentTool || c.tool) === "pen") {
                    promoteFreehandToConstraint(c, constraintMode(c, event));
                    event.preventDefault();
                }
                return;
            }
            if (key === "Shift") {
                c.shiftHeld = true;
                if (M.normalizeTool(c.persistentTool || c.tool) === "pen") promoteFreehandToConstraint(c, constraintMode(c, event));
                return;
            }
            if (key === "Escape") {
                handleEscape(c, event);
                return;
            }
            if (!event.ctrlKey && !event.metaKey && !event.altKey) {
                const shortcuts = { v: "select", l: "line", r: "rectangle", o: "circle", a: "arc", p: "pen" };
                if (shortcuts[lower]) rememberTool(c, shortcuts[lower]);
            }
        };

        const onKeyUpCapture = event => {
            if (!dialogVisible(c)) return;
            if (event.key === "Control") {
                leaveTemporarySelect(c);
                return;
            }
            if (event.key === "Alt") {
                c.altHeld = false;
                if (M.normalizeTool(c.persistentTool || c.tool) === "pen") event.preventDefault();
                return;
            }
            if (event.key === "Shift") c.shiftHeld = false;
        };

        c.root.addEventListener("click", onRootToolCapture, true);
        c.canvas.addEventListener("pointerdown", onPointerDownCapture, true);
        c.canvas.addEventListener("pointermove", onPointerMoveCapture, true);
        c.canvas.addEventListener("pointerup", onPointerUpCapture, true);
        c.canvas.addEventListener("pointercancel", onPointerCancelCapture, true);
        c.canvas.addEventListener("pointerdown", onPointerDownRestore, false);
        c.canvas.addEventListener("pointerup", onPointerUpRestore, false);
        window.addEventListener("pointerup", onWindowPointerUp, true);
        window.addEventListener("keydown", onKeyDownCapture, true);
        window.addEventListener("keyup", onKeyUpCapture, true);

        if (c.dialog && c.dialog.$wrapper) {
            c.dialog.$wrapper.one("hidden.bs.modal.ddv3-tool-modifier-cleanup", () => {
                c.root.removeEventListener("click", onRootToolCapture, true);
                c.canvas.removeEventListener("pointerdown", onPointerDownCapture, true);
                c.canvas.removeEventListener("pointermove", onPointerMoveCapture, true);
                c.canvas.removeEventListener("pointerup", onPointerUpCapture, true);
                c.canvas.removeEventListener("pointercancel", onPointerCancelCapture, true);
                c.canvas.removeEventListener("pointerdown", onPointerDownRestore, false);
                c.canvas.removeEventListener("pointerup", onPointerUpRestore, false);
                window.removeEventListener("pointerup", onWindowPointerUp, true);
                window.removeEventListener("keydown", onKeyDownCapture, true);
                window.removeEventListener("keyup", onKeyUpCapture, true);
            });
        }
        render(c);
        return c;
    }

    const originalOpen = Editor.open.bind(Editor);
    const originalView = Editor.view.bind(Editor);
    root.Editor = Object.freeze({
        open(frm, row, options = {}) { return install(originalOpen(frm, row, options)); },
        view(frm, row) { return install(originalView(frm, row)); },
    });

    root.ToolModifiers = Object.freeze({
        install,
        rememberTool,
        effectiveTool,
        beginConstrainedPen,
        moveConstrainedPen,
        finishConstrainedPen,
        promoteFreehandToConstraint,
        enterTemporarySelect,
        leaveTemporarySelect,
        handleEscape,
    });
})();
