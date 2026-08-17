(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingWorkspace = window.AlmdinaDoorDrawingWorkspace || Object.create(null);

    function button(label, className, attribute) {
        return `<button type="button" class="${className}" ${attribute}>${label}</button>`;
    }

    function create(container) {
        if (!container) throw new Error("Door drawing workspace container is required");
        container.innerHTML = `
            <section class="ald-ddw" data-ddw-root>
                <header class="ald-ddw-topbar">
                    <div class="ald-ddw-topbar-start">
                        ${button("← العودة إلى الطلب", "ald-ddw-back", "data-ddw-back")}
                        <div class="ald-ddw-title">
                            <strong data-ddw-title>رسم الدرفة الخاصة</strong>
                            <span data-ddw-subtitle>—</span>
                        </div>
                    </div>
                    <div class="ald-ddw-topbar-center">
                        <div class="ald-ddw-source-actions" role="group" aria-label="مصدر توثيق الدرفة">
                            ${button("رفع صورة", "ald-ddw-source-action", "data-ddw-upload-image")}
                            ${button("سحب من Scanner", "ald-ddw-source-action", "data-ddw-scan")}
                        </div>
                        <span class="ald-ddw-piece-meta" data-ddw-piece-meta>—</span>
                    </div>
                    <div class="ald-ddw-topbar-end">
                        <span class="ald-ddw-mode-pill" data-ddw-mode>رسم</span>
                        <span class="ald-ddw-save-state" data-ddw-save-state data-state="saved">محفوظ</span>
                        ${button("حفظ والعودة", "ald-ddw-action ald-ddw-action-save-return", "data-ddw-save-return")}
                        ${button("حفظ", "ald-ddw-action ald-ddw-action-primary", "data-ddw-save")}
                    </div>
                </header>
                <div class="ald-ddw-body" data-ddw-body>
                    <div class="ald-ddw-editor-host" data-ddw-editor-host></div>
                </div>
            </section>`;

        const elements = {
            root: container.querySelector("[data-ddw-root]"),
            body: container.querySelector("[data-ddw-body]"),
            editorHost: container.querySelector("[data-ddw-editor-host]"),
            back: container.querySelector("[data-ddw-back]"),
            save: container.querySelector("[data-ddw-save]"),
            saveReturn: container.querySelector("[data-ddw-save-return]"),
            uploadImage: container.querySelector("[data-ddw-upload-image]"),
            scan: container.querySelector("[data-ddw-scan]"),
            mode: container.querySelector("[data-ddw-mode]"),
            title: container.querySelector("[data-ddw-title]"),
            subtitle: container.querySelector("[data-ddw-subtitle]"),
            pieceMeta: container.querySelector("[data-ddw-piece-meta]"),
            saveState: container.querySelector("[data-ddw-save-state]"),
        };

        function clearOverlay() {
            elements.body.querySelectorAll(".ald-ddw-loading,.ald-ddw-error,.ald-ddw-empty,.ald-ddw-readonly-banner").forEach(node => node.remove());
        }

        function overlay(className, title, message) {
            clearOverlay();
            const node = document.createElement("div");
            node.className = className;
            const card = document.createElement("div");
            card.className = `${className}-card`;
            if (title) {
                const strong = document.createElement("strong");
                strong.textContent = title;
                card.appendChild(strong);
            }
            const text = document.createElement("div");
            text.textContent = message || "";
            card.appendChild(text);
            node.appendChild(card);
            elements.body.appendChild(node);
        }

        function setLoading(message = "يتم تحميل مساحة الرسم…") {
            overlay("ald-ddw-loading", "", message);
        }

        function setError(message) {
            overlay("ald-ddw-error", "تعذر فتح مساحة الرسم", message || "حدث خطأ غير متوقع.");
        }

        function setEmpty(message) {
            overlay("ald-ddw-empty", "لم يتم تحديد درفة", message || "افتح مساحة الرسم من طلب القص.");
        }

        function setContext(context) {
            clearOverlay();
            const order = context.order || {};
            const piece = context.piece || {};
            elements.title.textContent = `رسم الدرفة ${piece.piece_no || "—"}`;
            elements.subtitle.textContent = `${order.name || "—"} · ${order.customer || "بدون زبون"}`;
            elements.pieceMeta.textContent = `${Number(piece.width_cm || 0)} × ${Number(piece.length_cm || 0)} سم · ${order.status || "—"}`;
        }

        function setMode(mode) {
            const imageMode = mode === "image";
            elements.root.dataset.contentMode = imageMode ? "image" : "drawing";
            elements.mode.textContent = imageMode ? "صورة" : "رسم";
            elements.mode.dataset.mode = imageMode ? "image" : "drawing";
            elements.uploadImage.textContent = imageMode ? "استبدال الصورة" : "رفع صورة";
            elements.scan.textContent = imageMode ? "مسح جديد من Scanner" : "سحب من Scanner";
        }

        function setReadOnly(reason) {
            elements.save.disabled = true;
            elements.saveReturn.disabled = true;
            elements.uploadImage.disabled = true;
            elements.scan.disabled = true;
            const banner = document.createElement("div");
            banner.className = "ald-ddw-readonly-banner";
            banner.textContent = reason || "هذه الرسمة متاحة للعرض فقط.";
            elements.body.appendChild(banner);
        }

        function setSourceBusy(isBusy, label = "") {
            const busy = Boolean(isBusy);
            elements.uploadImage.disabled = busy || elements.uploadImage.dataset.readonly === "1";
            elements.scan.disabled = busy || elements.scan.dataset.readonly === "1";
            elements.root.classList.toggle("is-source-busy", busy);
            if (busy && label) elements.saveState.textContent = label;
        }

        function setSaveState(state, label) {
            elements.saveState.dataset.state = state;
            elements.saveState.textContent = label;
            const saving = state === "saving";
            if (!elements.save.dataset.readonly) elements.save.disabled = saving;
            if (!elements.saveReturn.dataset.readonly) elements.saveReturn.disabled = saving;
        }

        function markReadOnlyControls() {
            [elements.save, elements.saveReturn, elements.uploadImage, elements.scan].forEach(control => {
                control.dataset.readonly = "1";
                control.disabled = true;
            });
        }

        return Object.freeze({
            elements,
            clearOverlay,
            setLoading,
            setError,
            setEmpty,
            setContext,
            setMode,
            setReadOnly,
            setSourceBusy,
            setSaveState,
            markReadOnlyControls,
        });
    }

    root.Shell = Object.freeze({ create });
})();