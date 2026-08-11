(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const geometry = root.Geometry;
    const documentModel = root.DocumentModel;
    const historyFactory = root.History;
    const persistence = root.PersistenceAdapter;
    if (!geometry || !documentModel || !historyFactory || !persistence) {
        throw new Error("Door Drawing V3 modules must load before the editor");
    }

    const SVG_NS = "http://www.w3.org/2000/svg";
    const MIN_SCALE = 0.02;
    const MAX_SCALE = 20;
    const LINE_HIT_PX = 14;
    const DRAG_THRESHOLD_PX = 4;
    let activeController = null;
    let sequence = 0;
    let clipboard = null;

    function esc(value) {
        const text = String(value ?? "");
        if (window.frappe && frappe.utils && frappe.utils.escape_html) {
            return frappe.utils.escape_html(text);
        }
        return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

    function clone(value) {
        return value == null ? value : JSON.parse(JSON.stringify(value));
    }

    function nextId(prefix = "line") {
        sequence += 1;
        return `${prefix}-${Date.now()}-${sequence}`;
    }

    function formatMm(value, precision = 1) {
        const rounded = geometry.roundMm(value, precision);
        return Number.isInteger(rounded) ? String(rounded) : String(rounded);
    }

    function icon(name) {
        const icons = {
            select: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 3l12.4 8.2-6 1.5 3.2 6.2-2.3 1.2-3.1-6.1L5 18V3z" fill="currentColor"/></svg>',
            line: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 19L19 5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
            undo: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 7L5 11l4 4M6 11h7a5 5 0 010 10" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
            redo: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 7l4 4-4 4m3-4h-7a5 5 0 000 10" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
            close: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
        };
        return icons[name] || "";
    }

    function shellHtml(row, readOnly) {
        const widthMm = Math.max(0, geometry.number(row && row.width_cm) * 10);
        const heightMm = Math.max(0, geometry.number(row && row.length_cm) * 10);
        const pieceNo = row && (row.idx || row.piece_no || "");
        return `
            <div class="ddv3-app${readOnly ? " is-readonly" : ""}" dir="ltr">
                <header class="ddv3-topbar">
                    <div class="ddv3-top-left">
                        <button type="button" class="ddv3-icon-button" data-ddv3-close title="إغلاق">${icon("close")}</button>
                    </div>
                    <div class="ddv3-title" dir="rtl">رسم الدرفة الخاصة رقم ${esc(pieceNo)}</div>
                    <div class="ddv3-top-right">
                        <span class="ddv3-size" dir="ltr">${formatMm(widthMm)} × ${formatMm(heightMm)} mm</span>
                        ${readOnly ? "" : '<button type="button" class="ddv3-save" data-ddv3-save>حفظ</button>'}
                    </div>
                </header>
                <div class="ddv3-body">
                    <main class="ddv3-workspace">
                        <svg class="ddv3-canvas" xmlns="http://www.w3.org/2000/svg" aria-label="مساحة رسم الدرفة"></svg>
                        ${readOnly ? "" : `
                            <nav class="ddv3-toolbar" aria-label="أدوات الرسم">
                                <button type="button" data-ddv3-tool="select" title="تحديد V">${icon("select")}</button>
                                <button type="button" data-ddv3-tool="line" title="مستقيم L">${icon("line")}</button>
                                <span class="ddv3-separator"></span>
                                <button type="button" data-ddv3-undo title="تراجع Ctrl+Z">${icon("undo")}</button>
                                <button type="button" data-ddv3-redo title="إعادة Ctrl+Shift+Z">${icon("redo")}</button>
                            </nav>`}
                        <div class="ddv3-zoom">
                            <button type="button" data-ddv3-zoom-out>−</button>
                            <button type="button" class="ddv3-zoom-value" data-ddv3-zoom-reset>100%</button>
                            <button type="button" data-ddv3-zoom-in>+</button>
                        </div>
                    </main>
                    <aside class="ddv3-inspector" dir="ltr">
                        <div class="ddv3-inspector-tabs"><span class="is-active">Design</span></div>
                        <div class="ddv3-inspector-content" data-ddv3-inspector></div>
                    </aside>
                </div>
            </div>`;
    }

    function createViewport(canvas, document) {
        const rect = canvas.getBoundingClientRect();
        const referenceWidth = Math.max(1200, document.blank.widthMm || 0);
        const referenceHeight = Math.max(900, document.blank.heightMm || 0);
        const availableWidth = Math.max(300, rect.width - 160);
        const availableHeight = Math.max(240, rect.height - 160);
        const scale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, Math.min(
            availableWidth / referenceWidth,
            availableHeight / referenceHeight
        )));
        return {
            scale,
            baseScale: scale,
            offsetX: rect.width / 2 - referenceWidth * scale / 2,
            offsetY: rect.height / 2 + referenceHeight * scale / 2,
            widthPx: rect.width,
            heightPx: rect.height,
        };
    }

    function worldToScreen(controller, world) {
        return {
            x: controller.viewport.offsetX + geometry.number(world && world.x) * controller.viewport.scale,
            y: controller.viewport.offsetY - geometry.number(world && world.y) * controller.viewport.scale,
        };
    }

    function screenToWorld(controller, x, y) {
        return geometry.point(
            (x - controller.viewport.offsetX) / controller.viewport.scale,
            (controller.viewport.offsetY - y) / controller.viewport.scale
        );
    }

    function localPoint(controller, event) {
        const rect = controller.canvas.getBoundingClientRect();
        return { x: event.clientX - rect.left, y: event.clientY - rect.top };
    }

    function eventWorld(controller, event) {
        const local = localPoint(controller, event);
        return screenToWorld(controller, local.x, local.y);
    }

    function lineLabelPlacement(start, end, offset = 17) {
        const dx = end.x - start.x;
        const dy = end.y - start.y;
        const length = Math.hypot(dx, dy);
        if (length < 0.001) return null;
        let nx = -dy / length;
        let ny = dx / length;
        if (Math.abs(ny) > 0.25) {
            if (ny < 0) { nx *= -1; ny *= -1; }
        } else if (nx < 0) {
            nx *= -1; ny *= -1;
        }
        let angle = Math.atan2(dy, dx) * 180 / Math.PI;
        if (angle > 90) angle -= 180;
        if (angle < -90) angle += 180;
        return {
            x: (start.x + end.x) / 2 + nx * offset,
            y: (start.y + end.y) / 2 + ny * offset,
            angle,
        };
    }

    function measurementMarkup(start, end, lengthMm, selected = false) {
        const placement = lineLabelPlacement(start, end);
        if (!placement) return "";
        const text = `${formatMm(lengthMm)} mm`;
        const width = Math.max(42, text.length * 6.2 + 12);
        return `<g class="ddv3-measure${selected ? " is-selected" : ""}" transform="translate(${placement.x} ${placement.y}) rotate(${placement.angle})">
            <rect x="${-width / 2}" y="-9" width="${width}" height="18" rx="3"></rect>
            <text x="0" y="0">${esc(text)}</text>
        </g>`;
    }

    function renderCanvas(controller) {
        const document = controller.history.current();
        const previewId = controller.previewObject && controller.previewObject.id;
        const selectedId = controller.selectedId;
        const objects = document.objects.map(object => previewId === object.id ? controller.previewObject : object);
        const gridSize = Math.max(8, 50 * controller.viewport.scale);
        const gridX = ((controller.viewport.offsetX % gridSize) + gridSize) % gridSize;
        const gridY = ((controller.viewport.offsetY % gridSize) + gridSize) % gridSize;
        const parts = [`
            <defs>
                <pattern id="ddv3-grid-small" width="${gridSize}" height="${gridSize}" patternUnits="userSpaceOnUse" x="${gridX}" y="${gridY}">
                    <path d="M ${gridSize} 0 L 0 0 0 ${gridSize}" fill="none" stroke="#d8d8d8" stroke-width="0.65"/>
                </pattern>
            </defs>
            <rect x="0" y="0" width="100%" height="100%" class="ddv3-canvas-bg"/>
            <rect x="0" y="0" width="100%" height="100%" fill="url(#ddv3-grid-small)" pointer-events="none"/>`];

        objects.forEach(object => {
            if (object.type !== "line") return;
            const start = worldToScreen(controller, object.geometry.start);
            const end = worldToScreen(controller, object.geometry.end);
            const selected = String(object.id) === String(selectedId);
            parts.push(`<line class="ddv3-object-hit" data-ddv3-object="${esc(object.id)}" x1="${start.x}" y1="${start.y}" x2="${end.x}" y2="${end.y}" stroke-width="${LINE_HIT_PX}"/>`);
            parts.push(`<line class="ddv3-line${selected ? " is-selected" : ""}" data-ddv3-object="${esc(object.id)}" x1="${start.x}" y1="${start.y}" x2="${end.x}" y2="${end.y}"/>`);
            if (selected) {
                parts.push(measurementMarkup(start, end, geometry.lineLength(object), true));
                parts.push(`<g data-ddv3-handle="start" class="ddv3-handle"><circle cx="${start.x}" cy="${start.y}" r="10" class="ddv3-handle-hit"/><rect x="${start.x - 3}" y="${start.y - 3}" width="6" height="6" class="ddv3-handle-square"/></g>`);
                parts.push(`<g data-ddv3-handle="end" class="ddv3-handle"><circle cx="${end.x}" cy="${end.y}" r="10" class="ddv3-handle-hit"/><rect x="${end.x - 3}" y="${end.y - 3}" width="6" height="6" class="ddv3-handle-square"/></g>`);
            }
        });

        if (controller.draftStart && controller.draftEnd) {
            const start = worldToScreen(controller, controller.draftStart);
            const end = worldToScreen(controller, controller.draftEnd);
            const length = geometry.distance(controller.draftStart, controller.draftEnd);
            parts.push(`<line class="ddv3-line is-draft" x1="${start.x}" y1="${start.y}" x2="${end.x}" y2="${end.y}"/>`);
            if (length >= geometry.EPSILON_MM) parts.push(measurementMarkup(start, end, length, false));
            parts.push(`<rect x="${start.x - 3}" y="${start.y - 3}" width="6" height="6" class="ddv3-handle-square is-draft"/>`);
            parts.push(`<rect x="${end.x - 3}" y="${end.y - 3}" width="6" height="6" class="ddv3-handle-square is-draft"/>`);
        }

        controller.canvas.innerHTML = parts.join("");
        controller.canvas.dataset.tool = controller.tool;
        renderInspector(controller);
        renderToolbar(controller);
        renderZoom(controller);
    }

    function renderToolbar(controller) {
        controller.root.querySelectorAll("[data-ddv3-tool]").forEach(button => {
            button.classList.toggle("is-active", button.dataset.ddv3Tool === controller.tool);
        });
        const undo = controller.root.querySelector("[data-ddv3-undo]");
        const redo = controller.root.querySelector("[data-ddv3-redo]");
        if (undo) undo.disabled = !controller.history.canUndo();
        if (redo) redo.disabled = !controller.history.canRedo();
    }

    function renderZoom(controller) {
        const target = controller.root.querySelector("[data-ddv3-zoom-reset]");
        if (!target) return;
        const percent = Math.round(controller.viewport.scale / controller.viewport.baseScale * 100);
        target.textContent = `${percent}%`;
    }

    function selectedObject(controller) {
        return documentModel.objectById(controller.history.current(), controller.selectedId);
    }

    function field(label, key, value, suffix) {
        return `<label class="ddv3-field"><span>${esc(label)}</span><div><input type="number" step="0.1" value="${esc(value)}" data-ddv3-prop="${esc(key)}"><b>${esc(suffix || "")}</b></div></label>`;
    }

    function renderInspector(controller) {
        const inspector = controller.inspector;
        const object = selectedObject(controller);
        if (!object || object.type !== "line") {
            inspector.innerHTML = `<div class="ddv3-empty" dir="rtl"><b>الخصائص</b><span>حدد مستقيمًا لتعديل موقعه وطوله وزاويته.</span></div>`;
            return;
        }
        const readonly = controller.readOnly ? " disabled" : "";
        const start = object.geometry.start;
        const length = geometry.lineLength(object);
        const angle = geometry.lineAngle(object);
        inspector.innerHTML = `
            <section class="ddv3-panel-section">
                <div class="ddv3-panel-title"><strong>Line</strong><span>⋯</span></div>
            </section>
            <section class="ddv3-panel-section">
                <div class="ddv3-section-title">Position</div>
                <div class="ddv3-field-grid">
                    ${field("X", "x", formatMm(start.x, 3), "mm")}
                    ${field("Y", "y", formatMm(start.y, 3), "mm")}
                </div>
                <div class="ddv3-field-grid is-single">
                    ${field("Rotation", "angle", formatMm(angle, 2), "°")}
                </div>
            </section>
            <section class="ddv3-panel-section">
                <div class="ddv3-section-title">Dimensions</div>
                <div class="ddv3-field-grid is-single">
                    ${field("Length", "length", formatMm(length, 3), "mm")}
                </div>
            </section>
            <section class="ddv3-panel-section">
                <div class="ddv3-section-title">Stroke</div>
                <div class="ddv3-stroke-row"><span class="ddv3-color-swatch"></span><span>#1E1E1E</span><b>1</b></div>
            </section>`;
        if (readonly) inspector.querySelectorAll("input").forEach(input => input.disabled = true);
    }

    function setTool(controller, tool) {
        if (controller.readOnly) return;
        controller.tool = tool === "line" ? "line" : "select";
        controller.draftStart = null;
        controller.draftEnd = null;
        controller.pendingStart = null;
        renderCanvas(controller);
    }

    function select(controller, id) {
        controller.selectedId = id ? String(id) : "";
        controller.previewObject = null;
        renderCanvas(controller);
    }

    function execute(controller, nextDocument, label) {
        controller.history.execute(nextDocument, label);
        controller.dirty = true;
        renderCanvas(controller);
    }

    function commitLine(controller, start, end) {
        if (geometry.distance(start, end) < geometry.EPSILON_MM) return false;
        const object = geometry.line(nextId("line"), start, end);
        execute(controller, documentModel.addObject(controller.history.current(), object), "Add line");
        controller.selectedId = object.id;
        controller.draftStart = null;
        controller.draftEnd = null;
        controller.pendingStart = null;
        controller.tool = "select";
        renderCanvas(controller);
        return true;
    }

    function pointerCandidate(controller, event, anchor) {
        const candidate = eventWorld(controller, event);
        return event.shiftKey && anchor ? geometry.dominantAxisPoint(anchor, candidate) : candidate;
    }

    function beginPan(controller, event) {
        const local = localPoint(controller, event);
        controller.gesture = {
            type: "pan",
            pointerId: event.pointerId,
            startX: local.x,
            startY: local.y,
            offsetX: controller.viewport.offsetX,
            offsetY: controller.viewport.offsetY,
        };
        controller.canvas.classList.add("is-panning");
        try { controller.canvas.setPointerCapture(event.pointerId); } catch (error) { /* optional */ }
    }

    function onPointerDown(controller, event) {
        if (controller.readOnly && !controller.spaceHeld) return;
        if (controller.spaceHeld || event.button === 1) {
            beginPan(controller, event);
            event.preventDefault();
            return;
        }
        if (event.button !== 0) return;

        if (controller.tool === "line") {
            const local = localPoint(controller, event);
            const fromPending = Boolean(controller.pendingStart);
            const start = controller.pendingStart || eventWorld(controller, event);
            const end = pointerCandidate(controller, event, start);
            controller.gesture = {
                type: "line",
                pointerId: event.pointerId,
                start,
                startX: local.x,
                startY: local.y,
                fromPending,
            };
            controller.draftStart = start;
            controller.draftEnd = end;
            try { controller.canvas.setPointerCapture(event.pointerId); } catch (error) { /* optional */ }
            renderCanvas(controller);
            event.preventDefault();
            return;
        }

        const handle = event.target.closest && event.target.closest("[data-ddv3-handle]");
        const objectTarget = event.target.closest && event.target.closest("[data-ddv3-object]");
        if (handle && controller.selectedId) {
            const object = selectedObject(controller);
            if (!object) return;
            controller.gesture = {
                type: "endpoint",
                role: handle.dataset.ddv3Handle,
                pointerId: event.pointerId,
                object,
            };
            controller.previewObject = object;
            try { controller.canvas.setPointerCapture(event.pointerId); } catch (error) { /* optional */ }
            event.preventDefault();
            return;
        }
        if (objectTarget) {
            const id = objectTarget.dataset.ddv3Object;
            const object = documentModel.objectById(controller.history.current(), id);
            if (!object) return;
            controller.selectedId = id;
            controller.gesture = {
                type: "move",
                pointerId: event.pointerId,
                object,
                startWorld: eventWorld(controller, event),
            };
            controller.previewObject = object;
            try { controller.canvas.setPointerCapture(event.pointerId); } catch (error) { /* optional */ }
            renderCanvas(controller);
            event.preventDefault();
            return;
        }
        select(controller, "");
    }

    function onPointerMove(controller, event) {
        const gesture = controller.gesture;
        if (!gesture) {
            if (controller.tool === "line" && controller.pendingStart) {
                controller.draftStart = controller.pendingStart;
                controller.draftEnd = pointerCandidate(controller, event, controller.pendingStart);
                renderCanvas(controller);
            }
            return;
        }
        if (gesture.pointerId !== event.pointerId) return;
        if (gesture.type === "pan") {
            const local = localPoint(controller, event);
            controller.viewport.offsetX = gesture.offsetX + local.x - gesture.startX;
            controller.viewport.offsetY = gesture.offsetY + local.y - gesture.startY;
            renderCanvas(controller);
            event.preventDefault();
            return;
        }
        if (gesture.type === "line") {
            controller.draftEnd = pointerCandidate(controller, event, gesture.start);
            renderCanvas(controller);
            event.preventDefault();
            return;
        }
        if (gesture.type === "endpoint") {
            const point = pointerCandidate(
                controller,
                event,
                gesture.role === "start" ? gesture.object.geometry.end : gesture.object.geometry.start
            );
            try {
                controller.previewObject = geometry.setLineEndpoint(gesture.object, gesture.role, point);
                renderCanvas(controller);
            } catch (error) { /* keep last valid preview */ }
            event.preventDefault();
            return;
        }
        if (gesture.type === "move") {
            const current = eventWorld(controller, event);
            controller.previewObject = geometry.translateLine(
                gesture.object,
                current.x - gesture.startWorld.x,
                current.y - gesture.startWorld.y
            );
            renderCanvas(controller);
            event.preventDefault();
        }
    }

    function finishGesture(controller, event) {
        const gesture = controller.gesture;
        if (!gesture || gesture.pointerId !== event.pointerId) return;
        controller.gesture = null;
        try { controller.canvas.releasePointerCapture(event.pointerId); } catch (error) { /* optional */ }
        controller.canvas.classList.remove("is-panning");
        if (event.type === "pointercancel") {
            controller.previewObject = null;
            renderCanvas(controller);
            return;
        }

        if (gesture.type === "line") {
            const local = localPoint(controller, event);
            const moved = Math.hypot(local.x - gesture.startX, local.y - gesture.startY) >= DRAG_THRESHOLD_PX;
            const end = controller.draftEnd || pointerCandidate(controller, event, gesture.start);
            if (gesture.fromPending || moved) {
                commitLine(controller, gesture.start, end);
            } else {
                controller.pendingStart = gesture.start;
                controller.draftStart = gesture.start;
                controller.draftEnd = gesture.start;
                renderCanvas(controller);
            }
            return;
        }

        if ((gesture.type === "endpoint" || gesture.type === "move") && controller.previewObject) {
            const next = documentModel.replaceObject(controller.history.current(), controller.previewObject);
            execute(controller, next, gesture.type === "endpoint" ? "Move endpoint" : "Move line");
            controller.previewObject = null;
            return;
        }
        renderCanvas(controller);
    }

    function applyInspector(controller, input) {
        if (controller.readOnly || !input) return;
        const object = selectedObject(controller);
        if (!object || object.type !== "line") return;
        const key = input.dataset.ddv3Prop;
        const value = geometry.number(input.value, NaN);
        if (!Number.isFinite(value)) return;
        let nextObject = object;
        try {
            if (key === "length") {
                nextObject = geometry.resizeLine(object, value, geometry.lineAngle(object), "start");
            } else if (key === "angle") {
                nextObject = geometry.resizeLine(object, geometry.lineLength(object), value, "start");
            } else if (key === "x" || key === "y") {
                const start = object.geometry.start;
                const dx = key === "x" ? value - start.x : 0;
                const dy = key === "y" ? value - start.y : 0;
                nextObject = geometry.translateLine(object, dx, dy);
            } else {
                return;
            }
            execute(controller, documentModel.replaceObject(controller.history.current(), nextObject), `Edit ${key}`);
        } catch (error) {
            renderInspector(controller);
        }
    }

    function copySelected(controller) {
        const object = selectedObject(controller);
        if (!object) return false;
        clipboard = clone(object);
        return true;
    }

    function paste(controller) {
        if (controller.readOnly || !clipboard || clipboard.type !== "line") return false;
        const offset = 20;
        const copy = geometry.line(
            nextId("line"),
            geometry.point(clipboard.geometry.start.x + offset, clipboard.geometry.start.y + offset),
            geometry.point(clipboard.geometry.end.x + offset, clipboard.geometry.end.y + offset),
            clipboard.style || {}
        );
        execute(controller, documentModel.addObject(controller.history.current(), copy), "Paste line");
        controller.selectedId = copy.id;
        renderCanvas(controller);
        return true;
    }

    function duplicate(controller) {
        if (!copySelected(controller)) return false;
        return paste(controller);
    }

    function deleteSelected(controller) {
        if (controller.readOnly || !controller.selectedId) return false;
        execute(controller, documentModel.removeObject(controller.history.current(), controller.selectedId), "Delete object");
        controller.selectedId = "";
        renderCanvas(controller);
        return true;
    }

    function zoomAt(controller, factor, screenX, screenY) {
        const oldScale = controller.viewport.scale;
        const nextScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, oldScale * factor));
        if (Math.abs(nextScale - oldScale) < 0.000001) return;
        const world = screenToWorld(controller, screenX, screenY);
        controller.viewport.scale = nextScale;
        controller.viewport.offsetX = screenX - world.x * nextScale;
        controller.viewport.offsetY = screenY + world.y * nextScale;
        renderCanvas(controller);
    }

    function fitViewport(controller) {
        controller.viewport = createViewport(controller.canvas, controller.history.current());
        renderCanvas(controller);
    }

    function save(controller) {
        const document = controller.history.current();
        if (!document.objects.length) {
            frappe.msgprint("ارسم عنصرًا واحدًا على الأقل قبل الحفظ.");
            return;
        }
        controller.row.special_shape_drawing_json = persistence.toStored(document, controller.row);
        controller.row.special_shape_status = "Documented";
        controller.frm.dirty();
        controller.dirty = false;
        controller.allowClose = true;
        Promise.resolve(
            controller.frm.script_manager.trigger("piece_type", controller.row.doctype, controller.row.name)
        ).catch(error => console.error(error));
        controller.dialog.hide();
        if (window.AlmdinaDoorCuttingFastEntry && window.AlmdinaDoorCuttingFastEntry.render) {
            window.AlmdinaDoorCuttingFastEntry.render(controller.frm);
        }
        frappe.show_alert({ message: "تم حفظ رسم الدرفة.", indicator: "green" }, 3);
    }

    function bind(controller) {
        controller.root.addEventListener("click", event => {
            const tool = event.target.closest && event.target.closest("[data-ddv3-tool]");
            if (tool) { setTool(controller, tool.dataset.ddv3Tool); return; }
            if (event.target.closest && event.target.closest("[data-ddv3-close]")) { controller.dialog.hide(); return; }
            if (event.target.closest && event.target.closest("[data-ddv3-save]")) { save(controller); return; }
            if (event.target.closest && event.target.closest("[data-ddv3-undo]")) {
                controller.history.undo(); controller.dirty = true; renderCanvas(controller); return;
            }
            if (event.target.closest && event.target.closest("[data-ddv3-redo]")) {
                controller.history.redo(); controller.dirty = true; renderCanvas(controller); return;
            }
            const zoomOut = event.target.closest && event.target.closest("[data-ddv3-zoom-out]");
            const zoomIn = event.target.closest && event.target.closest("[data-ddv3-zoom-in]");
            const zoomReset = event.target.closest && event.target.closest("[data-ddv3-zoom-reset]");
            if (zoomOut || zoomIn) {
                zoomAt(controller, zoomIn ? 1.2 : 1 / 1.2, controller.viewport.widthPx / 2, controller.viewport.heightPx / 2);
                return;
            }
            if (zoomReset) fitViewport(controller);
        });

        controller.inspector.addEventListener("change", event => {
            const input = event.target.closest && event.target.closest("[data-ddv3-prop]");
            if (input) applyInspector(controller, input);
        });
        controller.inspector.addEventListener("keydown", event => {
            if (event.key !== "Enter") return;
            const input = event.target.closest && event.target.closest("[data-ddv3-prop]");
            if (!input) return;
            event.preventDefault();
            applyInspector(controller, input);
            input.blur();
        });

        controller.canvas.addEventListener("pointerdown", event => onPointerDown(controller, event));
        controller.canvas.addEventListener("pointermove", event => onPointerMove(controller, event));
        controller.canvas.addEventListener("pointerup", event => finishGesture(controller, event));
        controller.canvas.addEventListener("pointercancel", event => finishGesture(controller, event));
        controller.canvas.addEventListener("wheel", event => {
            event.preventDefault();
            const local = localPoint(controller, event);
            if (event.ctrlKey || event.metaKey) {
                zoomAt(controller, event.deltaY < 0 ? 1.12 : 1 / 1.12, local.x, local.y);
            } else {
                controller.viewport.offsetX -= event.deltaX;
                controller.viewport.offsetY -= event.deltaY;
                renderCanvas(controller);
            }
        }, { passive: false });

        controller.keyDown = event => {
            if (!controller.dialog.$wrapper.is(":visible")) return;
            const target = event.target;
            if (target && (/INPUT|TEXTAREA|SELECT/.test(target.tagName) || target.isContentEditable)) return;
            const mod = event.ctrlKey || event.metaKey;
            const key = String(event.key || "").toLowerCase();
            if (event.code === "Space") {
                controller.spaceHeld = true;
                controller.canvas.classList.add("is-pan-ready");
                event.preventDefault();
                return;
            }
            if (mod && key === "z") {
                event.preventDefault();
                event.shiftKey ? controller.history.redo() : controller.history.undo();
                controller.dirty = true; renderCanvas(controller); return;
            }
            if (mod && key === "c") { if (copySelected(controller)) event.preventDefault(); return; }
            if (mod && key === "v") { if (paste(controller)) event.preventDefault(); return; }
            if (mod && key === "d") { if (duplicate(controller)) event.preventDefault(); return; }
            if (mod) return;
            if (key === "v") { setTool(controller, "select"); event.preventDefault(); return; }
            if (key === "l") { setTool(controller, "line"); event.preventDefault(); return; }
            if ((event.key === "Delete" || event.key === "Backspace") && deleteSelected(controller)) { event.preventDefault(); return; }
            if (event.key === "Escape") {
                if (controller.pendingStart || controller.draftStart) {
                    controller.pendingStart = null; controller.draftStart = null; controller.draftEnd = null; renderCanvas(controller);
                } else if (controller.selectedId) {
                    select(controller, "");
                } else {
                    setTool(controller, "select");
                }
                event.preventDefault();
            }
        };
        controller.keyUp = event => {
            if (event.code !== "Space") return;
            controller.spaceHeld = false;
            controller.canvas.classList.remove("is-pan-ready");
        };
        document.addEventListener("keydown", controller.keyDown, true);
        document.addEventListener("keyup", controller.keyUp, true);

        controller.resizeObserver = new ResizeObserver(() => {
            const rect = controller.canvas.getBoundingClientRect();
            if (!rect.width || !rect.height) return;
            if (!controller.viewportReady) {
                controller.viewport = createViewport(controller.canvas, controller.history.current());
                controller.viewportReady = true;
            } else {
                controller.viewport.offsetX += (rect.width - controller.viewport.widthPx) / 2;
                controller.viewport.offsetY += (rect.height - controller.viewport.heightPx) / 2;
                controller.viewport.widthPx = rect.width;
                controller.viewport.heightPx = rect.height;
            }
            renderCanvas(controller);
        });
        controller.resizeObserver.observe(controller.canvas);

        controller.dialog.$wrapper.on("hide.bs.modal.ddv3-guard", event => {
            if (!controller.dirty || controller.allowClose) return;
            event.preventDefault();
            frappe.confirm("لديك تعديلات غير محفوظة. هل تريد إغلاق الرسم؟", () => {
                controller.allowClose = true;
                controller.dialog.hide();
            });
        });
        controller.dialog.$wrapper.one("hidden.bs.modal.ddv3-cleanup", () => {
            document.removeEventListener("keydown", controller.keyDown, true);
            document.removeEventListener("keyup", controller.keyUp, true);
            if (controller.resizeObserver) controller.resizeObserver.disconnect();
            if (activeController === controller) activeController = null;
        });
    }

    function open(frm, row, options = {}) {
        if (!window.frappe || !frappe.ui || !frappe.ui.Dialog) {
            throw new Error("Frappe dialog API is required for Door Drawing V3");
        }
        if ((row && row.piece_type || "Regular") !== "Special") {
            frappe.msgprint("حوّل نوع الدرفة إلى «خاصة» أولًا.");
            return null;
        }
        if (activeController) {
            activeController.allowClose = true;
            try { activeController.dialog.hide(); } catch (error) { /* close previous editor */ }
            activeController = null;
        }

        const readOnly = Boolean(options.readOnly);
        const initialDocument = persistence.fromStored(row.special_shape_drawing_json, row);
        const dialog = new frappe.ui.Dialog({
            title: "Door Drawing",
            size: "extra-large",
            fields: [{ fieldname: "door_drawing_v3", fieldtype: "HTML", options: shellHtml(row, readOnly) }],
        });
        dialog.$wrapper.addClass("dco-special-shape-modal ddv3-modal");
        if (readOnly) dialog.$wrapper.addClass("dco-special-shape-readonly");
        dialog.show();
        const rootElement = dialog.fields_dict.door_drawing_v3.$wrapper.find(".ddv3-app").get(0);
        const canvas = rootElement && rootElement.querySelector(".ddv3-canvas");
        const inspector = rootElement && rootElement.querySelector("[data-ddv3-inspector]");
        if (!rootElement || !canvas || !inspector) {
            dialog.hide();
            frappe.msgprint("تعذر فتح محرر الرسم الجديد.");
            return null;
        }

        const controller = {
            frm,
            row,
            dialog,
            root: rootElement,
            canvas,
            inspector,
            readOnly,
            history: null,
            selectedId: "",
            tool: "select",
            draftStart: null,
            draftEnd: null,
            pendingStart: null,
            previewObject: null,
            gesture: null,
            spaceHeld: false,
            viewport: { scale: 1, baseScale: 1, offsetX: 0, offsetY: 0, widthPx: 1, heightPx: 1 },
            viewportReady: false,
            resizeObserver: null,
            keyDown: null,
            keyUp: null,
            dirty: false,
            allowClose: false,
        };
        controller.history = historyFactory.create(initialDocument, () => {});
        activeController = controller;
        bind(controller);
        window.requestAnimationFrame(() => {
            controller.viewport = createViewport(canvas, controller.history.current());
            controller.viewportReady = true;
            renderCanvas(controller);
        });
        return controller;
    }

    root.Editor = Object.freeze({
        open,
        view(frm, row) { return open(frm, row, { readOnly: true }); },
        worldToScreen,
        screenToWorld,
    });
})();
