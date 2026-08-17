(() => {
    "use strict";

    function cardContext($card) {
        return {
            order: String($card.data("order") || ""),
            stage: String($card.data("stage") || ""),
            status: String($card.data("status") || ""),
            stageType: String($card.data("stage-type") || ""),
            next: String($card.data("next") || ""),
            canStart: String($card.attr("data-can-start") || "") === "1",
            canHandoff: String($card.attr("data-can-handoff") || "") === "1",
        };
    }

    function bind(shell, lifecycle, actions) {
        const namespace = ".almdinaShopFloorInbox";
        const $root = shell.$section;
        let $dragged = null;
        $root.off(namespace);

        $root.on(`click${namespace}`, ".almdina-sf-tab", function () {
            actions.setMode($(this).attr("data-sf-mode"));
        });
        $root.on(`click${namespace}`, ".almdina-sf-refresh", () => actions.refresh());
        $root.on(`click${namespace}`, ".almdina-sf-logout", () => actions.logout());
        $root.on(`click${namespace}`, ".shop-floor-order-card", function (event) {
            if ($(event.target).closest(".sf-quick-action").length) return;
            actions.openOrder(cardContext($(this)));
        });
        $root.on(`click${namespace}`, ".sf-quick-action", function (event) {
            event.preventDefault();
            event.stopPropagation();
            actions.quickAction(cardContext($(this).closest(".shop-floor-order-card")), this);
        });
        $root.on(`change${namespace}`, "#almdina-sf-route-filter", function () {
            actions.setRouteFilter(String($(this).val() || ""));
        });
        $root.on(`input${namespace}`, "#almdina-sf-board-search", function () {
            actions.setSearch(String($(this).val() || ""));
        });

        $root.on(`dragstart${namespace}`, '.almdina-sf-kanban-card[draggable="true"]', function (event) {
            $dragged = $(this);
            $dragged.addClass("is-dragging");
            const transfer = event.originalEvent && event.originalEvent.dataTransfer;
            if (transfer) {
                transfer.effectAllowed = "move";
                transfer.setData("text/plain", String($dragged.data("stage") || ""));
            }
        });
        $root.on(`dragend${namespace}`, '.almdina-sf-kanban-card[draggable="true"]', function () {
            $(this).removeClass("is-dragging");
            $root.find(".almdina-sf-kanban-column").removeClass("is-drag-over");
            $dragged = null;
        });
        $root.on(`dragover${namespace}`, ".almdina-sf-kanban-column", function (event) {
            if (!$dragged) return;
            const target = String($(this).attr("data-drop-stage") || "");
            const next = String($dragged.data("next") || "");
            if (target !== (next || "__ready__")) return;
            event.preventDefault();
            $(this).addClass("is-drag-over");
            const transfer = event.originalEvent && event.originalEvent.dataTransfer;
            if (transfer) transfer.dropEffect = "move";
        });
        $root.on(`dragleave${namespace}`, ".almdina-sf-kanban-column", function () {
            $(this).removeClass("is-drag-over");
        });
        $root.on(`drop${namespace}`, ".almdina-sf-kanban-column", function (event) {
            event.preventDefault();
            $(this).removeClass("is-drag-over");
            if (!$dragged) return;
            const target = String($(this).attr("data-drop-stage") || "");
            const context = cardContext($dragged);
            if (target !== (context.next || "__ready__")) return;
            actions.handoff(context);
        });

        lifecycle.track(() => {
            $root.off(namespace);
            $dragged = null;
        }, "shop-floor-inbox-events");
    }

    window.AlmdinaShopFloorInboxInteractions = Object.freeze({ bind, cardContext });
})();
