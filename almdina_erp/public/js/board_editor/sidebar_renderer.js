(() => {
    "use strict";

    function esc(value) {
        return frappe.utils.escape_html(String(value == null ? "" : value));
    }

    function aciSwatch(aci) {
        const map = {
            1: "#ff0000",
            2: "#ffff00",
            3: "#00ff00",
            4: "#00ffff",
            5: "#0000ff",
            6: "#ff00ff",
            7: "#9aa3b2",
            8: "#808080",
        };
        return map[Number(aci)] || "#98a2b3";
    }

    function frappeIcon(name) {
        if (window.frappe && frappe.utils && typeof frappe.utils.icon === "function") {
            return frappe.utils.icon(name, "sm", "", "", "currentColor", true);
        }
        return `<svg class="icon icon-sm abe-tool-icon" viewBox="0 0 24 24" aria-hidden="true"><use href="#icon-${esc(name)}"></use></svg>`;
    }

    function layerHint(layer, key) {
        const state = String(layer.content_state || "");
        if (state === "empty") return __("No content on this layer");
        if (state === "unavailable") return __("Content is unavailable for this layer");
        return layer.original_name || key;
    }

    function layerVisibilityAction(layers, visibility) {
        if (!layers.length) return null;
        let visible = 0;
        layers.forEach((layer) => {
            const key = String(layer.match_key || "");
            if (visibility[key] !== false) visible += 1;
        });
        if (visible === layers.length) {
            return {
                action: "hide-all",
                state: "all-visible",
                icon: "eye-off",
                label: __("All layers are visible. Hide all."),
            };
        }
        if (visible === 0) {
            return {
                action: "show-all",
                state: "all-hidden",
                icon: "eye",
                label: __("All layers are hidden. Show all."),
            };
        }
        return {
            action: "show-all",
            state: "mixed",
            icon: "eye",
            label: __("Some layers are hidden. Show all."),
        };
    }

    function hostingHtml(node, depth, sheetNo, selectedKeys) {
        const indent = Math.max(0, Number(depth) || 0);
        const guests = Array.isArray(node.guests) ? node.guests : [];
        const label = node.label || String(node.piece_id || "");
        const locked = node.editable === false
            ? `<span class="abe-host-hint">${esc(__("Not editable"))}</span>`
            : "";
        const selected = selectedKeys && selectedKeys.has && selectedKeys.has(node.piece_key);
        let html = `<button type="button" class="abe-piece-row${selected ? " is-selected" : ""}" data-piece-id="${esc(node.piece_id)}" data-piece-key="${esc(node.piece_key || "")}" data-sheet-no="${esc(sheetNo == null ? "" : sheetNo)}" style="padding-inline-start:${12 + indent * 14}px" title="${esc(label)}">
            <span class="abe-piece-label" dir="ltr">${esc(label)}</span>
            ${node.glass_host_piece_id != null ? `<span class="abe-host-hint">${esc(__("Hosted"))}</span>` : ""}
            ${locked}
        </button>`;
        guests.forEach((guest) => {
            html += hostingHtml(guest, indent + 1, sheetNo, selectedKeys);
        });
        return html;
    }

    function render(host, storeView, handlers) {
        const projection = storeView.projection || {};
        const session = storeView.session;
        const layers = projection.layers || [];
        const sheets = projection.sheets || [];
        const unplaced = projection.unplaced || [];
        const SessionDocument = window.AlmdinaBoardEditor.SessionDocument;
        const split = Math.round((Number(storeView.sidebarSplit) || 0.45) * 100);

        const layerRows = layers.map((layer) => {
            const key = String(layer.match_key || "");
            const checked = storeView.layerVisibility[key] !== false;
            const hint = layerHint(layer, key);
            return `<label class="abe-layer-row" title="${esc(hint)}">
                <input type="checkbox" data-layer-key="${esc(key)}" ${checked ? "checked" : ""}/>
                <span class="abe-layer-swatch" style="background:${esc(aciSwatch(layer.aci_color))}" aria-hidden="true"></span>
                <span class="abe-layer-name" dir="ltr" title="${esc(hint)}">${esc(layer.original_name || key)}</span>
            </label>`;
        }).join("");

        const visibleSheets = (session && session.boards)
            ? sheets.filter((sheet) => session.boards[String(sheet.sheet_no)])
            : sheets;
        const selectedKeySet = new Set(
            Array.isArray(storeView.selectedPieceKeys) && storeView.selectedPieceKeys.length
                ? storeView.selectedPieceKeys
                : (storeView.selectedPieceKey ? [storeView.selectedPieceKey] : [])
        );
        const sheetRows = visibleSheets.map((sheet) => {
            const sheetNo = sheet.sheet_no;
            const expanded = storeView.expandedSheets[String(sheetNo)] !== false;
            const selected = Number(storeView.selectedSheetNo) === Number(sheetNo);
            let pieceButtons = "";
            if (session && SessionDocument) {
                const roots = SessionDocument.hostingRoots(session, sheetNo);
                pieceButtons = roots.length
                    ? roots.map((node) => hostingHtml(node, 0, sheetNo, selectedKeySet)).join("")
                    : "";
            } else {
                const hosting = (sheet.hosting && sheet.hosting.roots) || [];
                pieceButtons = hosting.length
                    ? hosting.map((node) => hostingHtml(node, 0, sheetNo, selectedKeySet)).join("")
                    : (sheet.pieces || []).map((piece) => `<button type="button" class="abe-piece-row" data-piece-id="${esc(piece.piece_id)}" data-sheet-no="${esc(sheetNo)}" title="${esc(piece.label || piece.piece_id)}">
                        <span class="abe-piece-label" dir="ltr">${esc(piece.label || piece.piece_id)}</span>
                    </button>`).join("");
            }
            const resourceKind = String(sheet.resource_kind || "FULL_BOARD");
            const sheetLabel = __("Sheet {0}", [sheetNo]);
            const kindLabel = resourceKind.toUpperCase() === "FULL_BOARD"
                ? ""
                : `<span class="abe-sheet-kind" dir="ltr" title="${esc(resourceKind)}">${esc(resourceKind)}</span>`;
            return `<div class="abe-sheet-block${selected ? " is-selected" : ""}" data-sheet-block="${esc(sheetNo)}" data-resource-kind="${esc(resourceKind)}">
                <div class="abe-sheet-head">
                    <button type="button" class="abe-sheet-chevron" data-sheet-toggle="${esc(sheetNo)}" aria-expanded="${expanded ? "true" : "false"}">${expanded ? "▾" : "▸"}</button>
                    <button type="button" class="abe-sheet-title" data-sheet-select="${esc(sheetNo)}" title="${esc(sheetLabel)}">${esc(sheetLabel)}</button>
                    ${kindLabel}
                </div>
                <div class="abe-sheet-body" ${expanded ? "" : "hidden"}>${pieceButtons || `<div class="abe-empty-inline">${esc(__("No pieces on this sheet"))}</div>`}</div>
            </div>`;
        }).join("");

        let outsideHtml = "";
        if (session && SessionDocument) {
            const outsideRoots = SessionDocument.hostingRoots(session, null);
            if (outsideRoots.length) {
                outsideHtml = `<div class="abe-unplaced abe-outside-boards">
                    <div class="abe-unplaced-title">${esc(__("Outside boards"))}</div>
                    ${outsideRoots.map((node) => hostingHtml(node, 0, "", selectedKeySet)).join("")}
                </div>`;
            }
        }
        let excludedHtml = "";
        if (session && SessionDocument && typeof SessionDocument.excludedRoots === "function") {
            const excludedRoots = SessionDocument.excludedRoots(session);
            const reasonText = (reason) => (
                reason === "removed_with_host"
                    ? __("Removed with the host")
                    : __("Removed from the layout")
            );
            const excludedNode = (node, depth) => {
                const indent = Math.max(0, Number(depth) || 0);
                const guests = Array.isArray(node.guests) ? node.guests : [];
                let html = `<div class="abe-excluded-row" style="padding-inline-start:${12 + indent * 14}px">
                    <button type="button" class="abe-piece-row" data-piece-id="${esc(node.piece_id)}" data-piece-key="${esc(node.piece_key || "")}" data-sheet-no="" title="${esc(node.label || node.piece_id || "")}">
                        <span class="abe-piece-label" dir="ltr">${esc(node.label || node.piece_id || "")}</span>
                        <span class="abe-host-hint">${esc(reasonText(node.exclusion_reason))}</span>
                    </button>
                    <button type="button" class="abe-return-staging" data-return-key="${esc(node.piece_key || "")}">${esc(__("Return to staging"))}</button>
                </div>`;
                guests.forEach((guest) => {
                    html += excludedNode(guest, indent + 1);
                });
                return html;
            };
            if (excludedRoots.length) {
                excludedHtml = `<div class="abe-unplaced abe-excluded">
                    <div class="abe-unplaced-title">${esc(__("Excluded from distribution"))}</div>
                    ${excludedRoots.map((node) => excludedNode(node, 0)).join("")}
                </div>`;
            }
        }
        const unplacedHtml = (!outsideHtml && unplaced.length)
            ? `<div class="abe-unplaced">
                <div class="abe-unplaced-title">${esc(__("Unplaced pieces"))}</div>
                ${unplaced.map((piece) => `<div class="abe-piece-row is-unplaced"><span dir="ltr">${esc(piece.label || piece.piece_id || "—")}</span></div>`).join("")}
            </div>`
            : "";

        const previousLayers = host.querySelector(".abe-layers-scroll");
        const previousTree = host.querySelector(".abe-tree-scroll");
        const layersScrollTop = previousLayers ? previousLayers.scrollTop : 0;
        const treeScrollTop = previousTree ? previousTree.scrollTop : 0;

        const layerAction = layerVisibilityAction(layers, storeView.layerVisibility || {});
        const layerActionHtml = layerAction
            ? `<button type="button" class="abe-layer-visibility" data-abe-layer-action="${esc(layerAction.action)}" data-abe-layer-state="${esc(layerAction.state)}" title="${esc(layerAction.label)}" aria-label="${esc(layerAction.label)}">${frappeIcon(layerAction.icon)}</button>`
            : "";
        host.innerHTML = `
            <div class="abe-sidebar" style="--abe-split:${split}%">
                <section class="abe-sidebar-section abe-layers-section" aria-label="${esc(__("DXF layers"))}">
                    <header class="abe-section-head">
                        <h2>${esc(__("DXF layers"))}</h2>
                        <div class="abe-layer-actions">${layerActionHtml}</div>
                    </header>
                    <div class="abe-section-scroll abe-layers-scroll">${layerRows || `<div class="abe-empty-inline">${esc(__("No layers"))}</div>`}</div>
                </section>
                <div class="abe-split-handle" role="separator" aria-orientation="horizontal" aria-label="${esc(__("Resize sidebar sections"))}" tabindex="0"></div>
                <section class="abe-sidebar-section abe-tree-section" aria-label="${esc(__("Boards and pieces"))}">
                    <header class="abe-section-head"><h2>${esc(__("Boards and pieces"))}</h2></header>
                    <div class="abe-section-scroll abe-tree-scroll">${sheetRows || `<div class="abe-empty-inline">${esc(__("No boards"))}</div>`}${outsideHtml}${excludedHtml}${unplacedHtml}</div>
                </section>
            </div>
        `;
        const layersScroll = host.querySelector(".abe-layers-scroll");
        const treeScroll = host.querySelector(".abe-tree-scroll");
        if (layersScroll) layersScroll.scrollTop = layersScrollTop;
        if (treeScroll) treeScroll.scrollTop = treeScrollTop;

        host.querySelectorAll("input[data-layer-key]").forEach((input) => {
            input.addEventListener("change", () => {
                handlers && handlers.setLayerVisible && handlers.setLayerVisible(
                    input.getAttribute("data-layer-key"),
                    input.checked
                );
            });
        });
        const layerVisibility = host.querySelector(".abe-layer-visibility");
        if (layerVisibility) {
            layerVisibility.onclick = () => {
                const hide = layerVisibility.getAttribute("data-abe-layer-action") === "hide-all";
                handlers && handlers.setAllLayersVisible && handlers.setAllLayersVisible(!hide);
            };
        }

        host.querySelectorAll("[data-sheet-toggle]").forEach((button) => {
            button.addEventListener("click", () => handlers && handlers.toggleSheet && handlers.toggleSheet(button.getAttribute("data-sheet-toggle")));
        });
        host.querySelectorAll("[data-sheet-select]").forEach((button) => {
            button.addEventListener("click", () => handlers && handlers.selectSheet && handlers.selectSheet(button.getAttribute("data-sheet-select")));
        });
        host.querySelectorAll(".abe-return-staging").forEach((button) => {
            button.addEventListener("click", (event) => {
                event.preventDefault();
                event.stopPropagation();
                handlers && handlers.returnPiece && handlers.returnPiece(button.getAttribute("data-return-key"));
            });
        });
        const selectedKeys = new Set(
            Array.isArray(storeView.selectedPieceKeys) && storeView.selectedPieceKeys.length
                ? storeView.selectedPieceKeys
                : (storeView.selectedPieceKey ? [storeView.selectedPieceKey] : [])
        );
        host.querySelectorAll(".abe-piece-row[data-piece-id]").forEach((button) => {
            button.addEventListener("click", (event) => {
                handlers && handlers.selectPiece && handlers.selectPiece(
                    button.getAttribute("data-piece-id"),
                    button.getAttribute("data-sheet-no"),
                    {
                        shiftKey: Boolean(event.shiftKey),
                        pieceKey: button.getAttribute("data-piece-key"),
                    }
                );
            });
            const pieceKey = button.getAttribute("data-piece-key");
            const selected = pieceKey
                ? selectedKeys.has(pieceKey)
                : Number(button.getAttribute("data-piece-id")) === Number(storeView.selectedPieceId);
            if (selected) {
                button.classList.add("is-selected");
                const scroller = button.closest(".abe-section-scroll");
                if (scroller) {
                    const item = button.getBoundingClientRect();
                    const box = scroller.getBoundingClientRect();
                    if (item.top < box.top) scroller.scrollTop -= box.top - item.top;
                    else if (item.bottom > box.bottom) scroller.scrollTop += item.bottom - box.bottom;
                }
            }
        });

        const handle = host.querySelector(".abe-split-handle");
        if (handle) {
            let dragging = false;
            handle.addEventListener("pointerdown", (event) => {
                dragging = true;
                handle.setPointerCapture(event.pointerId);
            });
            handle.addEventListener("pointermove", (event) => {
                if (!dragging) return;
                const sidebar = host.querySelector(".abe-sidebar");
                if (!sidebar) return;
                const rect = sidebar.getBoundingClientRect();
                const ratio = (event.clientY - rect.top) / Math.max(rect.height, 1);
                handlers && handlers.setSidebarSplit && handlers.setSidebarSplit(ratio, rect.height);
            });
            handle.addEventListener("pointerup", () => { dragging = false; });
        }
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.SidebarRenderer = Object.freeze({ render });
})();
