(() => {
    "use strict";

    if (window.AlmdinaPlanBoardPresenter) return;

    const BOARD_GAP_PX = 8;
    const BOARD_CARD_CHROME_PX = 12;
    const BOARD_VIEWPORT_HEIGHT_RATIO = 0.68;
    const MOBILE_VIEWPORT_MAX_PX = 600;
    const TABLET_VIEWPORT_MAX_PX = 1024;
    const TWO_COLUMN_MIN_PX = 520;
    const THREE_COLUMN_MIN_PX = 760;
    const FOUR_COLUMN_MIN_PX = 1180;
    const FOCUS_INITIAL_ZOOM = 1.25;
    const FOCUS_MIN_ZOOM = 1;
    const FOCUS_MAX_ZOOM = 2;
    const FOCUS_ZOOM_STEP = 0.25;

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function desiredBoardColumns(width) {
        const available = Number(width || 0);
        const viewport = Number(window.innerWidth || available || 0);
        if (viewport <= MOBILE_VIEWPORT_MAX_PX || available < TWO_COLUMN_MIN_PX) return 1;
        if (viewport <= TABLET_VIEWPORT_MAX_PX || available < THREE_COLUMN_MIN_PX) return 2;
        if (available >= FOUR_COLUMN_MIN_PX) return 4;
        return 3;
    }

    function boardAspect(board) {
        if (!board) return 0.5;
        const width = parseFloat(board.style.width) || board.clientWidth || 0;
        const height = parseFloat(board.style.height) || board.clientHeight || 0;
        if (width > 0 && height > 0) return width / height;
        return 0.5;
    }

    function ensureBoardFocusButton(card) {
        const title = card && card.querySelector(":scope > .dco-sheet-title");
        if (!title || title.querySelector(":scope > .dco-board-focus-trigger")) return;
        const button = document.createElement("button");
        button.type = "button";
        button.className = "dco-board-focus-trigger";
        button.setAttribute("aria-label", "تكبير اللوح");
        button.setAttribute("title", "تكبير اللوح");
        button.innerHTML = '<span aria-hidden="true">⤢</span>';
        title.appendChild(button);
    }

    function ensureBoardGallery(planRoot) {
        if (!planRoot) return null;
        let gallery = planRoot.querySelector(":scope > .dco-board-gallery");
        const directCards = [...planRoot.querySelectorAll(":scope > .dco-sheet-card")];

        if (!gallery && directCards.length) {
            gallery = document.createElement("div");
            gallery.className = "dco-board-gallery";
            planRoot.insertBefore(gallery, directCards[0]);
        }

        if (!gallery) return null;
        directCards.forEach(card => gallery.appendChild(card));
        return gallery;
    }

    function layoutBoardGallery(planRoot) {
        const gallery = ensureBoardGallery(planRoot);
        if (!gallery) return;

        const rootWidth = planRoot.clientWidth || gallery.clientWidth || 0;
        const columns = desiredBoardColumns(rootWidth);
        planRoot.dataset.boardColumns = String(columns);

        const availableColumnWidth = rootWidth > 0
            ? Math.max(150, (rootWidth - BOARD_GAP_PX * Math.max(0, columns - 1)) / columns - BOARD_CARD_CHROME_PX)
            : 300;
        const viewportHeight = Math.max(480, window.innerHeight || 720);

        gallery.querySelectorAll(":scope > .dco-sheet-card").forEach(card => {
            const board = card.querySelector(":scope > .dco-sheet-board");
            if (!board) return;
            const aspect = boardAspect(board);
            board.style.setProperty("--dco-board-aspect", `${aspect} / 1`);

            if (columns === 1) {
                board.style.removeProperty("--dco-board-screen-max-width");
            } else {
                const viewportWidthCap = viewportHeight * BOARD_VIEWPORT_HEIGHT_RATIO * aspect;
                const widthCap = Math.max(145, Math.min(availableColumnWidth, viewportWidthCap));
                board.style.setProperty("--dco-board-screen-max-width", `${Math.round(widthCap)}px`);
            }
            ensureBoardFocusButton(card);
        });
    }

    function clamp(value, min, max) {
        return Math.min(max, Math.max(min, value));
    }

    function closeBoardFocus() {
        const overlay = document.querySelector(".dco-board-focus");
        if (overlay) overlay.remove();
        if (document.body && document.body.classList) {
            document.body.classList.remove("dco-board-focus-open");
        }
    }

    function focusFitWidth(aspect) {
        const viewportHeight = Math.max(520, window.innerHeight || 720);
        const viewportWidth = Math.max(720, window.innerWidth || 1280);
        const availableBoardHeight = Math.max(360, viewportHeight - 112);
        const byHeight = availableBoardHeight * 0.92 * aspect;
        const byWidth = viewportWidth * 0.82;
        return Math.max(240, Math.min(byHeight, byWidth));
    }

    function applyFocusZoom(overlay, fitWidth, zoom) {
        if (!overlay) return;
        const normalized = clamp(zoom, FOCUS_MIN_ZOOM, FOCUS_MAX_ZOOM);
        const board = overlay.querySelector(".dco-sheet-board");
        const label = overlay.querySelector(".dco-board-focus__zoom-value");
        if (board) {
            board.style.setProperty("--dco-focus-board-width", `${Math.round(fitWidth * normalized)}px`);
        }
        if (label) label.textContent = `${Math.round(normalized * 100)}%`;
        overlay.dataset.focusZoom = String(normalized);
    }

    function openBoardFocus(card) {
        if (!card) return;
        closeBoardFocus();

        const clone = card.cloneNode(true);
        clone.querySelectorAll(".dco-board-focus-trigger").forEach(button => button.remove());
        const board = clone.querySelector(".dco-sheet-board");
        const sourceBoard = card.querySelector(".dco-sheet-board");
        const aspect = boardAspect(sourceBoard);
        const fitWidth = focusFitWidth(aspect);
        if (board) {
            board.style.setProperty("--dco-board-aspect", `${aspect} / 1`);
        }

        const title = card.querySelector(".dco-sheet-title");
        const titleText = (title?.querySelector(":scope > :first-child")?.textContent || "تفاصيل اللوح").trim();
        const statsText = (title?.querySelector(":scope > :nth-child(2)")?.textContent || "").replace(/\s+/g, " ").trim();
        const overlay = document.createElement("div");
        overlay.className = "dco-board-focus";
        overlay.setAttribute("role", "dialog");
        overlay.setAttribute("aria-modal", "true");
        overlay.setAttribute("aria-label", titleText);
        overlay.innerHTML = `
            <div class="dco-board-focus__dialog">
                <div class="dco-board-focus__header">
                    <div class="dco-board-focus__identity">
                        <strong>${escapeHtml(titleText)}</strong>
                        <span class="dco-board-focus__stats">${escapeHtml(statsText)}</span>
                    </div>
                    <div class="dco-board-focus__actions">
                        <button type="button" class="dco-board-focus__fit">ملاءمة</button>
                        <div class="dco-board-focus__zoom" role="group" aria-label="تكبير وتصغير اللوح">
                            <button type="button" data-focus-zoom="out" aria-label="تصغير">−</button>
                            <span class="dco-board-focus__zoom-value">100%</span>
                            <button type="button" data-focus-zoom="in" aria-label="تكبير">+</button>
                        </div>
                        <button type="button" class="dco-board-focus__close" aria-label="إغلاق">×</button>
                    </div>
                </div>
                <div class="dco-board-focus__body"></div>
            </div>
        `;
        overlay.querySelector(".dco-board-focus__body").appendChild(clone);
        overlay.addEventListener("click", event => {
            if (event.target === overlay || event.target.closest(".dco-board-focus__close")) {
                closeBoardFocus();
                return;
            }
            if (event.target.closest(".dco-board-focus__fit")) {
                applyFocusZoom(overlay, fitWidth, 1);
                return;
            }
            const zoomButton = event.target.closest("[data-focus-zoom]");
            if (!zoomButton) return;
            const current = Number(overlay.dataset.focusZoom || 1);
            const delta = zoomButton.dataset.focusZoom === "in" ? FOCUS_ZOOM_STEP : -FOCUS_ZOOM_STEP;
            applyFocusZoom(overlay, fitWidth, current + delta);
        });
        document.body.appendChild(overlay);
        document.body.classList.add("dco-board-focus-open");
        const initialZoom = (window.innerWidth || 0) <= 760 ? 1 : FOCUS_INITIAL_ZOOM;
        applyFocusZoom(overlay, fitWidth, initialZoom);
        overlay.querySelector(".dco-board-focus__close")?.focus();
    }

    function installInteractions(root) {
        if (!root || root._dcoBoardGalleryInteractions) return;
        root.addEventListener("click", event => {
            const trigger = event.target.closest(".dco-board-focus-trigger");
            if (!trigger || !root.contains(trigger)) return;
            const card = trigger.closest(".dco-sheet-card");
            if (!card) return;
            event.preventDefault();
            event.stopPropagation();
            openBoardFocus(card);
        });
        root._dcoBoardGalleryInteractions = true;

        if (!document._dcoBoardFocusEscapeHandler) {
            document.addEventListener("keydown", event => {
                if (event.key === "Escape" && document.querySelector(".dco-board-focus")) {
                    closeBoardFocus();
                }
            });
            document._dcoBoardFocusEscapeHandler = true;
        }
    }

    window.AlmdinaPlanBoardPresenter = Object.freeze({
        layoutBoardGallery,
        installInteractions,
        closeBoardFocus,
        desiredBoardColumns,
    });
})();
