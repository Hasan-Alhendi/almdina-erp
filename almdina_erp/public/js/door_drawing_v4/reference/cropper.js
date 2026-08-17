(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingReference = window.AlmdinaDoorDrawingReference || Object.create(null);
    const domain = root.Domain;
    if (!domain) throw new Error("Reference image domain must load before cropper");

    const MIN_CROP_PX = 32;
    const MAX_OUTPUT_EDGE_PX = 3200;

    function clamp(value, min, max) { return Math.max(min, Math.min(max, value)); }
    function copyRect(rect) { return { x: rect.x, y: rect.y, width: rect.width, height: rect.height }; }
    function outputMime(file) { return String(file && file.type || "").toLowerCase() === "image/png" ? "image/png" : "image/jpeg"; }
    function canvasBlob(canvas, mime) {
        return new Promise((resolve, reject) => canvas.toBlob(
            blob => blob ? resolve(blob) : reject(new Error("Failed to encode cropped image")),
            mime,
            mime === "image/jpeg" ? 0.94 : undefined
        ));
    }
    function decode(file) {
        return new Promise((resolve, reject) => {
            const url = URL.createObjectURL(file);
            const image = new Image();
            image.decoding = "async";
            image.onload = () => resolve({ image, url });
            image.onerror = () => { URL.revokeObjectURL(url); reject(new Error("تعذر قراءة الصورة.")); };
            image.src = url;
        });
    }

    function rotatedCanvas(image, rotationDeg) {
        const rotation = ((rotationDeg % 360) + 360) % 360;
        const swap = rotation === 90 || rotation === 270;
        const canvas = document.createElement("canvas");
        canvas.width = swap ? image.naturalHeight : image.naturalWidth;
        canvas.height = swap ? image.naturalWidth : image.naturalHeight;
        const ctx = canvas.getContext("2d");
        ctx.save();
        ctx.translate(canvas.width / 2, canvas.height / 2);
        ctx.rotate(rotation * Math.PI / 180);
        ctx.drawImage(image, -image.naturalWidth / 2, -image.naturalHeight / 2);
        ctx.restore();
        return canvas;
    }

    async function open(file, options = {}) {
        const validation = domain.validateFile(file);
        if (!validation.ok) throw Object.assign(new Error(validation.message), { code: validation.code });

        const decoded = await decode(file);
        const originalWidth = Math.max(1, Number(decoded.image.naturalWidth || decoded.image.width));
        const originalHeight = Math.max(1, Number(decoded.image.naturalHeight || decoded.image.height));
        let rotationDeg = 0;
        let working = rotatedCanvas(decoded.image, rotationDeg);
        let crop = null;
        let display = null;
        let drag = null;
        let settled = false;
        const disposers = [];

        function resetCrop() {
            crop = {
                x: working.width * 0.04,
                y: working.height * 0.04,
                width: working.width * 0.92,
                height: working.height * 0.92,
            };
        }
        resetCrop();

        const overlay = document.createElement("div");
        overlay.className = "ald-ref-cropper-overlay";
        overlay.innerHTML = `
            <section class="ald-ref-cropper" dir="rtl" role="dialog" aria-modal="true" aria-label="اقتصاص الصورة المرجعية">
                <header class="ald-ref-cropper-header">
                    <div><strong>اقتصاص الصورة المرجعية</strong><span>احتفظ فقط بالجزء المهم من الورقة أو المخطط</span></div>
                    <button type="button" class="ald-ref-icon-button" data-close aria-label="إغلاق">×</button>
                </header>
                <div class="ald-ref-cropper-stage" data-stage>
                    <canvas data-image aria-label="معاينة الصورة"></canvas>
                    <div class="ald-ref-crop-box" data-crop-box tabindex="0">
                        <span class="ald-ref-crop-handle" data-handle="nw"></span><span class="ald-ref-crop-handle" data-handle="ne"></span>
                        <span class="ald-ref-crop-handle" data-handle="sw"></span><span class="ald-ref-crop-handle" data-handle="se"></span>
                        <span class="ald-ref-crop-size" data-size></span>
                    </div>
                </div>
                <footer class="ald-ref-cropper-footer">
                    <div class="ald-ref-cropper-footer-start">
                        <button type="button" class="ald-ref-secondary-button" data-full>كامل الصورة</button>
                        <button type="button" class="ald-ref-secondary-button" data-rotate-left>↺ تدوير</button>
                        <button type="button" class="ald-ref-secondary-button" data-rotate-right>تدوير ↻</button>
                        <span class="ald-ref-cropper-help">اسحب الإطار لتحريكه والزوايا لتغيير حجمه</span>
                    </div>
                    <div class="ald-ref-cropper-footer-end">
                        <button type="button" class="ald-ref-secondary-button" data-cancel>إلغاء</button>
                        <button type="button" class="ald-ref-primary-button" data-confirm>اعتماد الصورة</button>
                    </div>
                </footer>
            </section>`;

        const stage = overlay.querySelector("[data-stage]");
        const imageCanvas = overlay.querySelector("[data-image]");
        const cropBox = overlay.querySelector("[data-crop-box]");
        const sizeNode = overlay.querySelector("[data-size]");
        const confirmButton = overlay.querySelector("[data-confirm]");

        function listen(target, type, handler, opts) {
            target.addEventListener(type, handler, opts);
            disposers.push(() => target.removeEventListener(type, handler, opts));
        }
        function imageDisplayRect() {
            const rect = stage.getBoundingClientRect();
            const inset = 26;
            const scale = Math.min(
                Math.max(1, rect.width - inset * 2) / working.width,
                Math.max(1, rect.height - inset * 2) / working.height
            );
            const width = working.width * scale;
            const height = working.height * scale;
            return { left: (rect.width - width) / 2, top: (rect.height - height) / 2, width, height, scale };
        }
        function render() {
            display = imageDisplayRect();
            imageCanvas.width = working.width;
            imageCanvas.height = working.height;
            imageCanvas.getContext("2d").drawImage(working, 0, 0);
            imageCanvas.style.left = `${display.left}px`;
            imageCanvas.style.top = `${display.top}px`;
            imageCanvas.style.width = `${display.width}px`;
            imageCanvas.style.height = `${display.height}px`;
            cropBox.style.left = `${display.left + crop.x * display.scale}px`;
            cropBox.style.top = `${display.top + crop.y * display.scale}px`;
            cropBox.style.width = `${crop.width * display.scale}px`;
            cropBox.style.height = `${crop.height * display.scale}px`;
            sizeNode.textContent = `${Math.round(crop.width)} × ${Math.round(crop.height)} px`;
        }
        function sourcePoint(event) {
            const rect = stage.getBoundingClientRect();
            const current = display || imageDisplayRect();
            return {
                x: (event.clientX - rect.left - current.left) / current.scale,
                y: (event.clientY - rect.top - current.top) / current.scale,
            };
        }
        function beginDrag(event) {
            const handle = event.target.closest("[data-handle]");
            if (!handle && !event.target.closest("[data-crop-box]")) return;
            event.preventDefault();
            drag = { pointerId: event.pointerId, mode: handle ? "resize" : "move", handle: handle ? handle.dataset.handle : "", startPoint: sourcePoint(event), startCrop: copyRect(crop) };
            if (cropBox.setPointerCapture) cropBox.setPointerCapture(event.pointerId);
            cropBox.classList.add("is-dragging");
        }
        function moveCrop(point, start) {
            const dx = point.x - drag.startPoint.x;
            const dy = point.y - drag.startPoint.y;
            return { x: clamp(start.x + dx, 0, working.width - start.width), y: clamp(start.y + dy, 0, working.height - start.height), width: start.width, height: start.height };
        }
        function resizeCrop(point, start) {
            let left = start.x, top = start.y, right = start.x + start.width, bottom = start.y + start.height;
            if (drag.handle.includes("w")) left = clamp(point.x, 0, right - MIN_CROP_PX);
            if (drag.handle.includes("e")) right = clamp(point.x, left + MIN_CROP_PX, working.width);
            if (drag.handle.includes("n")) top = clamp(point.y, 0, bottom - MIN_CROP_PX);
            if (drag.handle.includes("s")) bottom = clamp(point.y, top + MIN_CROP_PX, working.height);
            return { x: left, y: top, width: right - left, height: bottom - top };
        }
        function pointerMove(event) {
            if (!drag || event.pointerId !== drag.pointerId) return;
            const point = sourcePoint(event);
            crop = drag.mode === "move" ? moveCrop(point, drag.startCrop) : resizeCrop(point, drag.startCrop);
            render();
        }
        function endDrag(event) {
            if (!drag || (event && event.pointerId !== drag.pointerId)) return;
            if (cropBox.hasPointerCapture && cropBox.hasPointerCapture(drag.pointerId)) cropBox.releasePointerCapture(drag.pointerId);
            drag = null;
            cropBox.classList.remove("is-dragging");
        }
        function rotate(delta) {
            rotationDeg = (rotationDeg + delta + 360) % 360;
            working = rotatedCanvas(decoded.image, rotationDeg);
            resetCrop();
            render();
        }
        function fullImage() { crop = { x: 0, y: 0, width: working.width, height: working.height }; render(); }
        function cleanup() { disposers.splice(0).forEach(dispose => dispose()); overlay.remove(); URL.revokeObjectURL(decoded.url); }

        const promise = new Promise((resolve, reject) => {
            function finish(value) { if (settled) return; settled = true; cleanup(); resolve(value); }
            async function confirm() {
                if (confirmButton.disabled) return;
                confirmButton.disabled = true;
                confirmButton.textContent = "يتم تجهيز الصورة…";
                try {
                    const sourceCrop = { x: Math.round(crop.x), y: Math.round(crop.y), width: Math.max(1, Math.round(crop.width)), height: Math.max(1, Math.round(crop.height)) };
                    const scale = Math.min(1, MAX_OUTPUT_EDGE_PX / Math.max(sourceCrop.width, sourceCrop.height));
                    const output = document.createElement("canvas");
                    output.width = Math.max(1, Math.round(sourceCrop.width * scale));
                    output.height = Math.max(1, Math.round(sourceCrop.height * scale));
                    const ctx = output.getContext("2d", { alpha: false });
                    ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, output.width, output.height);
                    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = "high";
                    ctx.drawImage(working, sourceCrop.x, sourceCrop.y, sourceCrop.width, sourceCrop.height, 0, 0, output.width, output.height);
                    const mime = outputMime(file);
                    const blob = await canvasBlob(output, mime);
                    finish(Object.freeze({
                        blob,
                        metadata: domain.buildMetadata({ source: options.source, originalName: file.name, originalMime: file.type, sourceWidthPx: originalWidth, sourceHeightPx: originalHeight, rotationDeg, crop: sourceCrop, outputWidthPx: output.width, outputHeightPx: output.height, outputMime: mime, scanner: options.scanner }),
                    }));
                } catch (error) {
                    confirmButton.disabled = false; confirmButton.textContent = "اعتماد الصورة"; reject(error); cleanup();
                }
            }
            listen(cropBox, "pointerdown", beginDrag); listen(cropBox, "pointermove", pointerMove); listen(cropBox, "pointerup", endDrag); listen(cropBox, "pointercancel", endDrag);
            listen(overlay.querySelector("[data-full]"), "click", fullImage);
            listen(overlay.querySelector("[data-rotate-left]"), "click", () => rotate(-90));
            listen(overlay.querySelector("[data-rotate-right]"), "click", () => rotate(90));
            listen(overlay.querySelector("[data-close]"), "click", () => finish(null));
            listen(overlay.querySelector("[data-cancel]"), "click", () => finish(null));
            listen(confirmButton, "click", confirm);
            listen(document, "keydown", event => { if (event.key === "Escape") { event.preventDefault(); finish(null); } });
        });

        document.body.appendChild(overlay);
        if (typeof ResizeObserver === "function") {
            const observer = new ResizeObserver(render); observer.observe(stage); disposers.push(() => observer.disconnect());
        } else listen(window, "resize", render);
        requestAnimationFrame(render);
        return promise;
    }

    root.Cropper = Object.freeze({ open, MAX_OUTPUT_EDGE_PX });
})();
