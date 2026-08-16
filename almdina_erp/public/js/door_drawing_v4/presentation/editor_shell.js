(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);

    function toolButton(tool, shortcut, label, icon) {
        return `<button type="button" class="ald-v4-tool" data-tool="${tool}" aria-label="${label}" title="${label} (${shortcut})"><span class="ald-v4-tool-icon" aria-hidden="true">${icon}</span><span class="ald-v4-tool-key">${shortcut}</span></button>`;
    }

    function mount(container) {
        if (!container) throw new Error("Drawing V4 editor container is required");
        container.innerHTML = `
            <section class="ald-v4-editor" dir="rtl" aria-label="محرر رسم الدرفة">
                <div class="ald-v4-toolbar" role="toolbar" aria-label="أدوات الرسم">
                    ${toolButton("select", "V", "تحديد", "↖")}
                    ${toolButton("node", "A", "تعديل النقاط", "◇")}
                    <span class="ald-v4-toolbar-separator" aria-hidden="true"></span>
                    ${toolButton("pen", "P", "القلم الذكي", "⌁")}
                    ${toolButton("hand", "Space", "تحريك اللوحة", "✋")}
                </div>
                <div class="ald-v4-canvas-wrap">
                    <canvas class="ald-v4-canvas" tabindex="0" aria-label="مساحة الرسم"></canvas>
                    <input class="ald-v4-length-input" type="text" inputmode="decimal" autocomplete="off" spellcheck="false" aria-label="طول الضلع بالميليمتر" placeholder="الطول mm" hidden>
                    <div class="ald-v4-hint" aria-live="polite"></div>
                    <div class="ald-v4-zoom-controls" dir="ltr" aria-label="التكبير والتصغير">
                        <button type="button" data-view-action="zoom-out" aria-label="تصغير">−</button>
                        <button type="button" class="ald-v4-zoom-value" data-view-action="fit" aria-label="ملاءمة الرسم للشاشة">100%</button>
                        <button type="button" data-view-action="zoom-in" aria-label="تكبير">+</button>
                    </div>
                </div>
                <div class="ald-v4-status" aria-live="polite">
                    <span class="ald-v4-status-tool">تحديد</span>
                    <span class="ald-v4-status-separator">•</span>
                    <span class="ald-v4-status-coordinates">X 0 · Y 0 mm</span>
                    <span class="ald-v4-status-snap"></span>
                </div>
            </section>`;

        const editor = container.querySelector(".ald-v4-editor");
        const canvasWrap = editor.querySelector(".ald-v4-canvas-wrap");
        const canvas = editor.querySelector(".ald-v4-canvas");
        const lengthInput = editor.querySelector(".ald-v4-length-input");
        const hint = editor.querySelector(".ald-v4-hint");
        const statusTool = editor.querySelector(".ald-v4-status-tool");
        const statusCoordinates = editor.querySelector(".ald-v4-status-coordinates");
        const statusSnap = editor.querySelector(".ald-v4-status-snap");
        const zoomValue = editor.querySelector(".ald-v4-zoom-value");

        function setActiveTool(tool) {
            editor.querySelectorAll("[data-tool]").forEach(button => {
                const active = button.dataset.tool === tool;
                button.classList.toggle("is-active", active);
                button.setAttribute("aria-pressed", active ? "true" : "false");
            });
        }

        function setReadOnly(readOnly) {
            const locked = Boolean(readOnly);
            editor.classList.toggle("is-readonly", locked);
            editor.querySelectorAll("[data-tool]").forEach(button => {
                const allowed = button.dataset.tool === "hand";
                button.disabled = locked && !allowed;
            });
            lengthInput.disabled = locked;
        }

        function setHint(text = "") {
            hint.textContent = text;
            hint.classList.toggle("is-visible", Boolean(text));
        }

        function showLengthInput(screenPoint, initialValue = "") {
            if (lengthInput.disabled) return;
            lengthInput.hidden = false;
            const width = 116;
            const x = Math.max(12, Math.min(canvas.clientWidth - width - 12, Number(screenPoint.x) + 14));
            const y = Math.max(12, Math.min(canvas.clientHeight - 44, Number(screenPoint.y) + 14));
            lengthInput.style.left = `${x}px`;
            lengthInput.style.top = `${y}px`;
            lengthInput.value = initialValue;
            lengthInput.focus({ preventScroll: true });
            lengthInput.setSelectionRange(lengthInput.value.length, lengthInput.value.length);
        }

        function hideLengthInput() {
            lengthInput.hidden = true;
            lengthInput.value = "";
        }

        return Object.freeze({
            editor,
            canvasWrap,
            canvas,
            lengthInput,
            hint,
            statusTool,
            statusCoordinates,
            statusSnap,
            zoomValue,
            setActiveTool,
            setReadOnly,
            setHint,
            showLengthInput,
            hideLengthInput,
            destroy() {
                container.innerHTML = "";
            },
        });
    }

    root.EditorShell = Object.freeze({ mount });
})();