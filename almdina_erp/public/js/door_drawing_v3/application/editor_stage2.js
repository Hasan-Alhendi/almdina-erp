(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry, D = root.DocumentModel, H = root.History, P = root.PersistenceAdapter, V = root.ShapeView;
    if (!G || !D || !H || !P || !V) throw new Error("Door Drawing V3 modules must load before editor stage 2");

    const DRAG_PX = 4;
    let activeController = null, sequence = 0, clipboard = null;
    function nextId(prefix) { sequence += 1; return `${prefix}-${Date.now()}-${sequence}`; }
    function clone(value) { return value == null ? value : JSON.parse(JSON.stringify(value)); }
    function selected(c) { return D.objectById(c.history.current(), c.selectedId); }
    function execute(c, doc, label) { c.history.execute(doc, label); c.dirty = true; V.render(c); }
    function select(c, id) { c.selectedId = id ? String(id) : ""; c.previewObject = null; V.render(c); }
    function clearDraft(c) { c.draftStart = null; c.draftObject = null; c.arcDraft = null; }
    function setTool(c, tool) { if (c.readOnly) return; c.tool = ["line", "rectangle", "circle", "arc"].includes(tool) ? tool : "select"; clearDraft(c); V.render(c); }
    function candidate(c, event, anchor) { const p = V.eventWorld(c, event); return event.shiftKey && anchor ? G.dominantAxisPoint(anchor, p) : p; }

    function makeDraft(c, start, end, event) {
        try {
            if (c.tool === "line") return G.line("draft", start, end);
            if (c.tool === "rectangle") return G.rectangleFromPoints("draft", start, end, Boolean(event.shiftKey));
            if (c.tool === "circle") return G.circle("draft", start, G.distance(start, end));
        } catch (error) { return null; }
        return null;
    }

    function commitDraft(c) {
        if (!c.draftObject) return false;
        const object = G.cloneObject(c.draftObject, nextId(c.draftObject.type));
        execute(c, D.addObject(c.history.current(), object), `Add ${object.type}`);
        c.selectedId = object.id; clearDraft(c); c.tool = "select"; V.render(c); return true;
    }

    function handleArcClick(c, event) {
        const p = V.eventWorld(c, event);
        if (!c.arcDraft) { c.arcDraft = { stage: "center", center: p, pointer: p }; V.render(c); return; }
        if (c.arcDraft.stage === "center") {
            const radius = G.distance(c.arcDraft.center, p); if (radius < G.EPSILON_MM) return;
            c.arcDraft = { stage: "radius", center: c.arcDraft.center, radiusMm: radius, startAngleDeg: G.angleDeg(c.arcDraft.center, p), pointer: p }; V.render(c); return;
        }
        const endAngle = G.angleDeg(c.arcDraft.center, p);
        let sweep = G.normalizeAngle(endAngle - c.arcDraft.startAngleDeg); if (Math.abs(sweep) < G.MIN_ARC_SWEEP_DEG) return;
        const object = G.arc(nextId("arc"), c.arcDraft.center, c.arcDraft.radiusMm, c.arcDraft.startAngleDeg, sweep);
        execute(c, D.addObject(c.history.current(), object), "Add arc"); c.selectedId = object.id; clearDraft(c); c.tool = "select"; V.render(c);
    }

    function beginPan(c, event) {
        const p = V.localPoint(c, event); c.gesture = { type: "pan", pointerId: event.pointerId, x: p.x, y: p.y, ox: c.viewport.offsetX, oy: c.viewport.offsetY };
        c.canvas.classList.add("is-panning"); try { c.canvas.setPointerCapture(event.pointerId); } catch (error) { /* optional */ }
    }

    function pointerDown(c, event) {
        if (c.readOnly && !c.spaceHeld) return;
        if (c.spaceHeld || event.button === 1) { beginPan(c, event); event.preventDefault(); return; }
        if (event.button !== 0) return;
        if (c.tool === "arc") { handleArcClick(c, event); event.preventDefault(); return; }
        if (["line", "rectangle", "circle"].includes(c.tool)) {
            const p = V.localPoint(c, event), start = V.eventWorld(c, event);
            c.gesture = { type: "draw", pointerId: event.pointerId, start, x: p.x, y: p.y }; c.draftStart = start; c.draftObject = null;
            try { c.canvas.setPointerCapture(event.pointerId); } catch (error) { /* optional */ } event.preventDefault(); return;
        }
        const handle = event.target.closest && event.target.closest("[data-ddv3-handle]");
        const target = event.target.closest && event.target.closest("[data-ddv3-object]");
        if (handle && c.selectedId) {
            const object = selected(c); if (!object || object.type !== "line") return;
            c.gesture = { type: "endpoint", pointerId: event.pointerId, role: handle.dataset.ddv3Handle, object }; c.previewObject = object;
        } else if (target) {
            const object = D.objectById(c.history.current(), target.dataset.ddv3Object); if (!object) return;
            c.selectedId = object.id; c.gesture = { type: "move", pointerId: event.pointerId, object, startWorld: V.eventWorld(c, event) }; c.previewObject = object; V.render(c);
        } else { select(c, ""); return; }
        try { c.canvas.setPointerCapture(event.pointerId); } catch (error) { /* optional */ } event.preventDefault();
    }

    function pointerMove(c, event) {
        if (!c.gesture) {
            if (c.tool === "arc" && c.arcDraft) {
                c.arcDraft.pointer = V.eventWorld(c, event);
                if (c.arcDraft.stage === "radius") {
                    const end = c.arcDraft.pointer, sweep = G.normalizeAngle(G.angleDeg(c.arcDraft.center, end) - c.arcDraft.startAngleDeg);
                    try { c.draftObject = G.arc("draft", c.arcDraft.center, c.arcDraft.radiusMm, c.arcDraft.startAngleDeg, Math.abs(sweep) < G.MIN_ARC_SWEEP_DEG ? G.MIN_ARC_SWEEP_DEG : sweep); } catch (error) { c.draftObject = null; }
                }
                V.render(c);
            }
            return;
        }
        const g = c.gesture; if (g.pointerId !== event.pointerId) return;
        if (g.type === "pan") { const p = V.localPoint(c, event); c.viewport.offsetX = g.ox + p.x - g.x; c.viewport.offsetY = g.oy + p.y - g.y; V.render(c); event.preventDefault(); return; }
        if (g.type === "draw") { c.draftObject = makeDraft(c, g.start, candidate(c, event, g.start), event); V.render(c); event.preventDefault(); return; }
        if (g.type === "endpoint") { try { c.previewObject = G.setLineEndpoint(g.object, g.role, candidate(c, event, g.role === "start" ? g.object.geometry.end : g.object.geometry.start)); V.render(c); } catch (error) { /* last valid */ } event.preventDefault(); return; }
        if (g.type === "move") { const p = V.eventWorld(c, event); c.previewObject = G.translateObject(g.object, p.x - g.startWorld.x, p.y - g.startWorld.y); V.render(c); event.preventDefault(); }
    }

    function pointerUp(c, event) {
        const g = c.gesture; if (!g || g.pointerId !== event.pointerId) return; c.gesture = null;
        try { c.canvas.releasePointerCapture(event.pointerId); } catch (error) { /* optional */ } c.canvas.classList.remove("is-panning");
        if (event.type === "pointercancel") { c.previewObject = null; clearDraft(c); V.render(c); return; }
        if (g.type === "draw") { const p = V.localPoint(c, event); if (Math.hypot(p.x - g.x, p.y - g.y) >= DRAG_PX) commitDraft(c); else { clearDraft(c); V.render(c); } return; }
        if ((g.type === "endpoint" || g.type === "move") && c.previewObject) { execute(c, D.replaceObject(c.history.current(), c.previewObject), g.type === "endpoint" ? "Move endpoint" : "Move object"); c.previewObject = null; }
    }

    function applyInspector(c, input) {
        if (c.readOnly || !input || input.disabled) return; const object = selected(c); if (!object) return;
        const key = input.dataset.ddv3Prop, value = G.number(input.value, NaN); if (!Number.isFinite(value)) return; let next = object, g = object.geometry;
        try {
            if (object.type === "line") { if (key === "length") next = G.resizeLine(object, value); else if (key === "angle") next = G.resizeLine(object, G.lineLength(object), value); else if (key === "x" || key === "y") next = G.translateObject(object, key === "x" ? value - g.start.x : 0, key === "y" ? value - g.start.y : 0); else return; }
            else if (object.type === "rectangle") next = G.setRectangle(object, { [key === "width" ? "widthMm" : key === "height" ? "heightMm" : key]: value });
            else if (object.type === "circle") next = G.setCircle(object, { [key === "radius" ? "radiusMm" : key === "diameter" ? "radiusMm" : key]: key === "diameter" ? value / 2 : value });
            else if (object.type === "arc") next = G.setArc(object, { [key === "radius" ? "radiusMm" : key === "startAngle" ? "startAngleDeg" : key === "sweep" ? "sweepAngleDeg" : key]: value });
            execute(c, D.replaceObject(c.history.current(), next), `Edit ${key}`);
        } catch (error) { V.renderInspector(c); }
    }

    function copySelected(c) { const object = selected(c); if (!object) return false; clipboard = clone(object); return true; }
    function paste(c) { if (c.readOnly || !clipboard) return false; try { const copy = G.translateObject(G.cloneObject(clipboard, nextId(clipboard.type)), 20, 20); execute(c, D.addObject(c.history.current(), copy), "Paste object"); c.selectedId = copy.id; V.render(c); return true; } catch (error) { return false; } }
    function duplicate(c) { return copySelected(c) && paste(c); }
    function deleteSelected(c) { if (c.readOnly || !c.selectedId) return false; execute(c, D.removeObject(c.history.current(), c.selectedId), "Delete object"); c.selectedId = ""; V.render(c); return true; }

    function zoomAt(c, factor, x, y) { const old = c.viewport.scale, next = Math.max(V.MIN_SCALE, Math.min(V.MAX_SCALE, old * factor)); if (Math.abs(next - old) < 1e-9) return; const world = V.screenToWorld(c, x, y); c.viewport.scale = next; c.viewport.offsetX = x - world.x * next; c.viewport.offsetY = y + world.y * next; V.render(c); }
    function fit(c) { c.viewport = V.viewport(c.canvas, c.history.current()); V.render(c); }
    function save(c) { const doc = c.history.current(); if (!doc.objects.length) { frappe.msgprint("ارسم عنصرًا واحدًا على الأقل قبل الحفظ."); return; } c.row.special_shape_drawing_json = P.toStored(doc, c.row); c.row.special_shape_status = "Documented"; c.frm.dirty(); c.dirty = false; c.allowClose = true; Promise.resolve(c.frm.script_manager.trigger("piece_type", c.row.doctype, c.row.name)).catch(console.error); c.dialog.hide(); if (window.AlmdinaDoorCuttingFastEntry && window.AlmdinaDoorCuttingFastEntry.render) window.AlmdinaDoorCuttingFastEntry.render(c.frm); frappe.show_alert({ message: "تم حفظ رسم الدرفة.", indicator: "green" }, 3); }

    function bind(c) {
        c.root.addEventListener("click", event => { const tool = event.target.closest && event.target.closest("[data-ddv3-tool]"); if (tool) return setTool(c, tool.dataset.ddv3Tool); if (event.target.closest && event.target.closest("[data-ddv3-close]")) return c.dialog.hide(); if (event.target.closest && event.target.closest("[data-ddv3-save]")) return save(c); if (event.target.closest && event.target.closest("[data-ddv3-undo]")) { c.history.undo(); c.dirty = true; return V.render(c); } if (event.target.closest && event.target.closest("[data-ddv3-redo]")) { c.history.redo(); c.dirty = true; return V.render(c); } const out = event.target.closest && event.target.closest("[data-ddv3-zoom-out]"), inside = event.target.closest && event.target.closest("[data-ddv3-zoom-in]"), reset = event.target.closest && event.target.closest("[data-ddv3-zoom-reset]"); if (out || inside) return zoomAt(c, inside ? 1.2 : 1 / 1.2, c.viewport.widthPx / 2, c.viewport.heightPx / 2); if (reset) fit(c); });
        c.inspector.addEventListener("change", e => applyInspector(c, e.target.closest && e.target.closest("[data-ddv3-prop]")));
        c.inspector.addEventListener("keydown", e => { if (e.key !== "Enter") return; const input = e.target.closest && e.target.closest("[data-ddv3-prop]"); if (input) { e.preventDefault(); applyInspector(c, input); input.blur(); } });
        c.canvas.addEventListener("pointerdown", e => pointerDown(c, e)); c.canvas.addEventListener("pointermove", e => pointerMove(c, e)); c.canvas.addEventListener("pointerup", e => pointerUp(c, e)); c.canvas.addEventListener("pointercancel", e => pointerUp(c, e));
        c.canvas.addEventListener("wheel", e => { e.preventDefault(); const p = V.localPoint(c, e); if (e.ctrlKey || e.metaKey) zoomAt(c, e.deltaY < 0 ? 1.12 : 1 / 1.12, p.x, p.y); else { c.viewport.offsetX -= e.deltaX; c.viewport.offsetY -= e.deltaY; V.render(c); } }, { passive: false });
        c.keyDown = e => { if (!c.dialog.$wrapper.is(":visible")) return; const t = e.target; if (t && (/INPUT|TEXTAREA|SELECT/.test(t.tagName) || t.isContentEditable)) return; const mod = e.ctrlKey || e.metaKey, key = String(e.key || "").toLowerCase(); if (e.code === "Space") { c.spaceHeld = true; V.render(c); e.preventDefault(); return; } if (mod && key === "z") { e.preventDefault(); e.shiftKey ? c.history.redo() : c.history.undo(); c.dirty = true; V.render(c); return; } if (mod && key === "c") { if (copySelected(c)) e.preventDefault(); return; } if (mod && key === "v") { if (paste(c)) e.preventDefault(); return; } if (mod && key === "d") { if (duplicate(c)) e.preventDefault(); return; } if (mod) return; const shortcuts = { v: "select", l: "line", r: "rectangle", o: "circle", a: "arc" }; if (shortcuts[key]) { setTool(c, shortcuts[key]); e.preventDefault(); return; } if ((e.key === "Delete" || e.key === "Backspace") && deleteSelected(c)) { e.preventDefault(); return; } if (e.key === "Escape") { if (c.draftObject || c.arcDraft) { clearDraft(c); V.render(c); } else if (c.selectedId) select(c, ""); else setTool(c, "select"); e.preventDefault(); } };
        c.keyUp = e => { if (e.code === "Space") { c.spaceHeld = false; V.render(c); } }; document.addEventListener("keydown", c.keyDown, true); document.addEventListener("keyup", c.keyUp, true);
        c.resizeObserver = new ResizeObserver(() => { const r = c.canvas.getBoundingClientRect(); if (!r.width || !r.height) return; if (!c.viewportReady) { c.viewport = V.viewport(c.canvas, c.history.current()); c.viewportReady = true; } else { c.viewport.offsetX += (r.width - c.viewport.widthPx) / 2; c.viewport.offsetY += (r.height - c.viewport.heightPx) / 2; c.viewport.widthPx = r.width; c.viewport.heightPx = r.height; } V.render(c); }); c.resizeObserver.observe(c.canvas);
        c.dialog.$wrapper.on("hide.bs.modal.ddv3-guard", e => { if (!c.dirty || c.allowClose) return; e.preventDefault(); frappe.confirm("لديك تعديلات غير محفوظة. هل تريد إغلاق الرسم؟", () => { c.allowClose = true; c.dialog.hide(); }); });
        c.dialog.$wrapper.one("hidden.bs.modal.ddv3-cleanup", () => { document.removeEventListener("keydown", c.keyDown, true); document.removeEventListener("keyup", c.keyUp, true); if (c.resizeObserver) c.resizeObserver.disconnect(); if (activeController === c) activeController = null; });
    }

    function open(frm, row, options = {}) {
        if (!window.frappe || !frappe.ui || !frappe.ui.Dialog) throw new Error("Frappe dialog API is required for Door Drawing V3");
        if ((row && row.piece_type || "Regular") !== "Special") { frappe.msgprint("حوّل نوع الدرفة إلى «خاصة» أولًا."); return null; }
        if (activeController) { activeController.allowClose = true; try { activeController.dialog.hide(); } catch (error) { /* optional */ } activeController = null; }
        const readOnly = Boolean(options.readOnly), initial = P.fromStored(row.special_shape_drawing_json, row), dialog = new frappe.ui.Dialog({ title: "Door Drawing", size: "extra-large", fields: [{ fieldname: "door_drawing_v3", fieldtype: "HTML", options: V.shell(row, readOnly) }] });
        dialog.$wrapper.addClass("dco-special-shape-modal ddv3-modal"); if (readOnly) dialog.$wrapper.addClass("dco-special-shape-readonly"); dialog.show();
        const rootElement = dialog.fields_dict.door_drawing_v3.$wrapper.find(".ddv3-app").get(0), canvas = rootElement && rootElement.querySelector(".ddv3-canvas"), inspector = rootElement && rootElement.querySelector("[data-ddv3-inspector]"); if (!rootElement || !canvas || !inspector) { dialog.hide(); frappe.msgprint("تعذر فتح محرر الرسم الجديد."); return null; }
        const c = { frm, row, dialog, root: rootElement, canvas, inspector, readOnly, history: H.create(initial, () => {}), selectedId: "", tool: "select", draftStart: null, draftObject: null, arcDraft: null, previewObject: null, gesture: null, spaceHeld: false, viewport: { scale: 1, baseScale: 1, offsetX: 0, offsetY: 0, widthPx: 1, heightPx: 1 }, viewportReady: false, resizeObserver: null, keyDown: null, keyUp: null, dirty: false, allowClose: false };
        activeController = c; bind(c); window.requestAnimationFrame(() => { c.viewport = V.viewport(canvas, c.history.current()); c.viewportReady = true; V.render(c); }); return c;
    }

    root.Editor = Object.freeze({ open, view(frm, row) { return open(frm, row, { readOnly: true }); } });
    root.EditorStage2 = Object.freeze({ setTool, handleArcClick, applyInspector, copySelected, paste, duplicate, deleteSelected });
})();