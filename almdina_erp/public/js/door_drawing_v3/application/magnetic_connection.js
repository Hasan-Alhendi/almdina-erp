(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const S = root.Snapping;
    const V = root.ShapeView;
    const Editor = root.Editor;
    if (!S || !V || !Editor) throw new Error("Door Drawing V3 editor must load before magnetic connection UX");

    const DRAW_TOOLS = new Set(["line", "rectangle", "circle", "arc"]);
    const MAGNETIC_KINDS = new Set(["joint", "surface", "intersection", "midpoint"]);
    const MAGNETIC_LABELS = Object.freeze({
        joint: "وصل",
        surface: "على الضلع",
        intersection: "تقاطع",
        midpoint: "منتصف",
    });

    function updateBadge(c, state) {
        if (!c || !c.root) return;
        let badge = c.root.querySelector(".ddv3-magnetic-badge");
        const kind = state && state.kind;
        const visible = Boolean(state && state.snapped && state.point && MAGNETIC_KINDS.has(kind));
        if (!visible) {
            if (badge) badge.classList.remove("is-visible");
            c.canvas.classList.remove("has-magnetic-snap");
            return;
        }
        if (!badge) {
            badge = document.createElement("div");
            badge.className = "ddv3-magnetic-badge";
            const workspace = c.root.querySelector(".ddv3-workspace");
            if (workspace) workspace.appendChild(badge);
        }
        if (!badge) return;
        badge.textContent = MAGNETIC_LABELS[kind] || "وصل";
        const p = V.worldToScreen(c, state.point);
        badge.style.left = `${Math.max(8, Math.min(c.viewport.widthPx - 76, p.x + 12))}px`;
        badge.style.top = `${Math.max(8, Math.min(c.viewport.heightPx - 34, p.y - 26))}px`;
        badge.classList.add("is-visible");
        c.canvas.classList.add("has-magnetic-snap");
    }

    function hoverSnap(c, event) {
        if (!c || c.readOnly || c.gesture || c.clickDraft || c.arcDraft || !DRAW_TOOLS.has(c.tool)) return false;
        const previous = c.snapState && c.snapState.target;
        const result = S.resolvePoint(c.history.current(), V.eventWorld(c, event), {
            viewportScale: c.viewport.scale,
            stickyTarget: previous,
        });
        c.snapState = result;
        V.render(c);
        updateBadge(c, result);
        return true;
    }

    function magneticMove(c, event) {
        const gesture = c && c.gesture;
        if (!gesture || gesture.type !== "move" || gesture.pointerId !== event.pointerId || !gesture.object) return false;
        const pointer = V.eventWorld(c, event);
        const result = S.resolveObjectMove(
            c.history.current(),
            gesture.object,
            pointer.x - gesture.startWorld.x,
            pointer.y - gesture.startWorld.y,
            {
                viewportScale: c.viewport.scale,
                stickySource: gesture.magneticSource || null,
                stickyTarget: gesture.magneticTarget || null,
            }
        );

        if (result.snapped && MAGNETIC_KINDS.has(result.kind)) {
            gesture.magneticSource = result.source;
            gesture.magneticTarget = result.target;
        } else {
            gesture.magneticSource = null;
            gesture.magneticTarget = null;
        }

        c.previewObject = result.object;
        c.snapState = result;
        V.render(c);
        updateBadge(c, result);
        event.preventDefault();
        event.stopImmediatePropagation();
        return true;
    }

    function install(c) {
        if (!c || !c.canvas || c.__magneticConnectionInstalled) return c;
        c.__magneticConnectionInstalled = true;

        const onPointerMoveCapture = event => {
            if (magneticMove(c, event)) return;
            hoverSnap(c, event);
        };
        const onPointerLeave = () => {
            if (c.gesture || c.clickDraft || c.arcDraft) return;
            c.snapState = null;
            updateBadge(c, null);
            V.render(c);
        };
        const onPointerUp = () => window.requestAnimationFrame(() => updateBadge(c, c.snapState));

        c.canvas.addEventListener("pointermove", onPointerMoveCapture, true);
        c.canvas.addEventListener("pointerleave", onPointerLeave, true);
        c.canvas.addEventListener("pointerup", onPointerUp, true);

        if (c.dialog && c.dialog.$wrapper) {
            c.dialog.$wrapper.one("hidden.bs.modal.ddv3-magnetic-cleanup", () => {
                c.canvas.removeEventListener("pointermove", onPointerMoveCapture, true);
                c.canvas.removeEventListener("pointerleave", onPointerLeave, true);
                c.canvas.removeEventListener("pointerup", onPointerUp, true);
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

    root.MagneticConnection = Object.freeze({ install, hoverSnap, magneticMove, updateBadge, MAGNETIC_KINDS });
})();
