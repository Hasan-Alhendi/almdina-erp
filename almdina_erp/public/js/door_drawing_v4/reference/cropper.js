(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingReference = window.AlmdinaDoorDrawingReference || Object.create(null);
    const domain = root.Domain;
    if (!domain) throw new Error("Reference image domain must load before cropper");

    const MIN_CROP_PX = 32;
    const MAX_OUTPUT_EDGE_PX = 3200;

    function imageFromFile(file) {
        return new Promise((resolve, reject) => {
            const url = URL.createObjectURL(file);
            const image = new Image();
            image.decoding = "async";
            image.onload = () => resolve({ image, url });
            image.onerror = () => {
                URL.revokeObjectURL(url);
                reject(new Error("Failed to decode image"));
            };
            image.src = url;
        });
    }

    function clamp(value, min, max) {
        return Math.max(min, Math.min(max, value));
    }

    function rectCopy(rect) {
        return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
    }

    function outputMime(file) {
        return String(file && file.type || "").toLowerCase() === "image/png" ? "image/png" : "image/jpeg";
    }

    function canvasBlob(canvas, mime) {
        return new Promise((resolve, reject) => {
            canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error("Failed to encode cropped image")), mime, mime === "image/jpeg" ? 0.94 : undefined);
        });
    }

    async function open(file, options = {}) {
        const validation = domain.validateFile(file);
        if (!validation.ok) throw Object.assign(new Error(validation.message), { code: validation.code });

        const decoded = await imageFromFile(file);
        const image = decoded.image;
        const sourceWidth = Math.max(1, Number(image.naturalWidth || image.width));
        const sourceHeight = Math.max(1, Number(image.naturalHeight || image.height));
        let crop = {
            x: sourceWidth * 0.04,
            y: sourceHeight * 0.04,
            width: sourceWidth * 0.92,
            height: sourceHeight * 0.92,
        };
        let display = null;
        let drag = null;
        let settled = false;
        const disposers = [];

        const overlay = document.createElement("div");
        overlay.className = "ald-ref-cropper-overlay";
        overlay.innerHTML = `
            <section class="ald-ref-cropper" dir="rtl" role="dialog" aria-modal="true" aria-label="قص صورة الخطة">
                <header class="ald-ref-cropper-header">
                    <div>
                        <strong>قص صورة الخطة</strong>
                        <span>حدد الجزء الذي يمثل الدرفة فقط</span>
                    </div>
                    <button type="button" class="ald-ref-icon-button" data-cropper-close aria-label="إغلاق">×</button>
                </header>
                <div class="ald-ref-cropper-stage" data-cropper-stage>
                    <img data-cropper-image alt="معاينة صورة الخطة">
                    <div class="ald-ref-crop-box" data-crop-box tabindex="0" aria-label="منطقة القص">
                        <span class="ald-ref-crop-shade ald-ref-crop-shade-top"></span>
                        <span class="ald-ref-crop-handle" data-handle="nw"></span>
                        <span class="ald-ref-crop-handle" data-handle="ne"></span>
                        <span class="ald-ref-crop-handle" data-handle="sw"></span>
                        <span class="ald-ref-crop-handle" data-handle="se"></span>
                        <span class="ald-ref-crop-size" data-crop-size></span>
                    </div>
                </div>
                <footer class="ald-ref-cropper-footer">
                    <div class="ald-ref-cropper-footer-start">
                        <button type="button" class="ald-ref-secondary-button" data-cropper-full>استخدام كامل الصورة</button>
                        <span class="ald-ref-cropper-help">اسحب الإطار لتحريكه، واسحب الزوايا لتغيير حجمه</span>
                    </div>
                    <div class="ald-ref-cropper-footer-end">
                        <button type="button" class="ald-ref-secondary-button" data-cropper-cancel>إلغاء</button>
                        <button type="button" class="ald-ref-primary-button" data-cropper-confirm>تأكيد القص</button>
                    </div>
                </footer>
            </section>`;

        const stage = overlay.querySelector("[data-cropper-stage]");
        const imageNode = overlay.querySelector("[data-cropper-image]");
        const cropBox = overlay.querySelector("[data-crop-box]");
        const cropSize = overlay.querySelector("[data-crop-size]");
        const confirmButton = overlay.querySelector("[data-cropper-confirm]");
        imageNode.src = decoded.url;

        function listen(target, event, handler, listenerOptions) {
            target.addEventListener(event, handler, listenerOptions);
            disposers.push(() => target.removeEventListener(event, handler, listenerOptions));
        }

        function imageDisplayRect() {
            const stageRect = stage.getBoundingClientRect();
            const inset = 26;
            const availableWidth = Math.max(1, stageRect.width - inset * 2);
            const availableHeight = Math.max(1, stageRect.height - inset * 2);
            const scale = Math.min(availableWidth / sourceWidth, availableHeight / sourceHeight);
            const width = sourceWidth * scale;
            const height = sourceHeight * scale;
            return {
                left: (stageRect.width - width) / 2,
                top: (stageRect.height - height) / 2,
                width,
                height,
                scale,
            };
        }

        function render() {
            display = imageDisplayRect();
            imageNode.style.left = `${display.left}px`;
            imageNode.style.top = `${display.top}px`;
            imageNode.style.width = `${display.width}px`;
            imageNode.style.height = `${display.height}px`;
            const left = display.left + crop.x * display.scale;
            const top = display.top + crop.y * display.scale;
            const width = crop.width * display.scale;
            const height = crop.height * display.scale;
            cropBox.style.left = `${left}px`;
            cropBox.style.top = `${top}px`;
            cropBox.style.width = `${width}px`;
            cropBox.style.height = `${height}px`;
            cropSize.textContent = `${Math.round(crop.width)} × ${Math.round(crop.height)} px`;
        }

        function pointerSourcePoint(event) {
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
            const point = pointerSourcePoint(event);
            drag = {
                pointerId: event.pointerId,
                mode: handle ? "resize" : "move",
                handle: handle ? handle.dataset.handle : "",
                startPoint: point,
                startCrop: rectCopy(crop),
            };
            cropBox.setPointerCapture(event.pointerId);
            cropBox.classList.add("is-dragging");
        }

        function moveCrop(point, start) {
            const dx = point.x - drag.startPoint.x;
            const dy = point.y - drag.startPoint.y;
            return {
                x: clamp(start.x + dx, 0, sourceWidth - start.width),
                y: clamp(start.y + dy, 0, sourceHeight - start.height),
                width: start.width,
                height: start.height,
            };
        }

        function resizeCrop(point, start) {
            let left = start.x;
            let top = start.y;
            let right = start.x + start.width;
            let bottom = start.y + start.height;
            if (drag.handle.includes("w")) left = clamp(point.x, 0, right - MIN_CROP_PX);
            if (drag.handle.includes("e")) right = clamp(point.x, left + MIN_CROP_PX, sourceWidth);
            if (drag.handle.includes("n")) top = clamp(point.y, 0, bottom - MIN_CROP_PX);
            if (drag.handle.includes("s")) bottom = clamp(point.y, top + MIN_CROP_PX, sourceHeight);
            return { x: left, y: top, width: right - left, height: bottom - top };
        }

        function handlePointerMove(event) {
            if (!drag || event.pointerId !== drag.pointerId) return;
            const point = pointerSourcePoint(event);
            crop = drag.mode === "move" ? moveCrop(point, drag.startCrop) : resizeCrop(point, drag.startCrop);
            render();
        }

        function endDrag(event) {
            if (!drag || (event && event.pointerId !== drag.pointerId)) return;
            if (cropBox.hasPointerCapture && cropBox.hasPointerCapture(drag.pointerId)) cropBox.releasePointerCapture(drag.pointerId);
            drag = null;
            cropBox.classList.remove("is-dragging");
        }

        function fullImage() {
            crop = { x: 0, y: 0, width: sourceWidth, height: sourceHeight };
            render();
        }

        function cleanup() {
            disposers.splice(0).forEach(dispose => dispose());
            overlay.remove();
            URL.revokeObjectURL(decoded.url);
        }

        const resultPromise = new Promise((resolve, reject) => {
            function finish(value) {
                if (settled) return;
                settled = true;
                cleanup();
                resolve(value);
            }

            async function confirm() {
                if (confirmButton.disabled) return;
                confirmButton.disabled = true;
                confirmButton.textContent = "يتم تجهيز الصورة…";
                try {
                    const sourceCrop = {
                        x: Math.round(crop.x),
                        y: Math.round(crop.y),
                        width: Math.max(1, Math.round(crop.width)),
                        height: Math.max(1, Math.round(crop.height)),
                    };
                    const outputScale = Math.min(1, MAX_OUTPUT_EDGE_PX / Math.max(sourceCrop.width, sourceCrop.height));
                    const canvas = document.createElement("canvas");
                    canvas.width = Math.max(1, Math.round(sourceCrop.width * outputScale));
                    canvas.height = Math.max(1, Math.round(sourceCrop.height * outputScale));
                    const context = canvas.getContext("2d", { alpha: false });
                    context.fillStyle = "#ffffff";
                    context.fillRect(0, 0, canvas.width, canvas.height);
                    context.imageSmoothingEnabled = true;
                    context.imageSmoothingQuality = "high";
                    context.drawImage(
                        image,
                        sourceCrop.x,
                        sourceCrop.y,
                        sourceCrop.width,
                        sourceCrop.height,
                        0,
                        0,
                        canvas.width,
                        canvas.height
                    );
                    const mime = outputMime(file);
                    const blob = await canvasBlob(canvas, mime);
                    finish(Object.freeze({
                        blob,
                        metadata: domain.buildMetadata({
                            source: options.source,
                            originalName: file.name,
                            originalMime: file.type,
                            sourceWidthPx: sourceWidth,
                            sourceHeightPx: sourceHeight,
                            crop: sourceCrop,
                            outputWidthPx: canvas.width,
                            outputHeightPx: canvas.height,
                            outputMime: mime,
                            scanner: options.scanner,
                        }),
                    }));
                } catch (error) {
                    confirmButton.disabled = false;
                    confirmButton.textContent = "تأكيد القص";
                    reject(error);
                    cleanup();
                }
            }

            listen(cropBox, "pointerdown", beginDrag);
            listen(cropBox, "pointermove", handlePointerMove);
            listen(cropBox, "pointerup", endDrag);
            listen(cropBox, "pointercancel", endDrag);
            listen(overlay.querySelector("[data-cropper-full]"), "click", fullImage);
            listen(overlay.querySelector("[data-cropper-close]"), "click", () => finish(null));
            listen(overlay.querySelector("[data-cropper-cancel]"), "click", () => finish(null));
            listen(confirmButton, "click", confirm);
            listen(document, "keydown", event => {
                if (event.key === "Escape") {
                    event.preventDefault();
                    finish(null);
                }
            });
        });

        document.body.appendChild(overlay);
        let resizeObserver = null;
        if (typeof ResizeObserver === "function") {
            resizeObserver = new ResizeObserver(render);
            resizeObserver.observe(stage);
            disposers.push(() => resizeObserver.disconnect());
        } else {
            listen(window, "resize", render);
        }
        window.requestAnimationFrame(render);
        return resultPromise;
    }

    root.Cropper = Object.freeze({ open, MAX_OUTPUT_EDGE_PX });
})();