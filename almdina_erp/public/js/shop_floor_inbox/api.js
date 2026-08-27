(() => {
    "use strict";

    const Frontend = window.AlmdinaFrontend;
    if (!Frontend || typeof Frontend.rpc !== "function") {
        throw new Error("AlmdinaFrontend.rpc is required before Shop Floor Inbox API");
    }

    const METHODS = Object.freeze({
        context: "almdina_erp.almdina_erp.services.shop_floor_query_service.get_shop_floor_context",
        inbox: "almdina_erp.almdina_erp.services.shop_floor_query_service.get_my_inbox",
        archive: "almdina_erp.almdina_erp.services.shop_floor_query_service.get_my_archive",
        readyForDelivery: "almdina_erp.almdina_erp.services.shop_floor_query_service.get_ready_for_delivery",
        handoffContext: "almdina_erp.almdina_erp.services.shop_floor_commands.get_handoff_context",
        handoff: "almdina_erp.almdina_erp.services.shop_floor_commands.handoff_to_next",
        logout: "logout",
    });

    function getSessionContext() {
        return Frontend.rpc(METHODS.context);
    }

    function getInbox() {
        return Frontend.rpc(METHODS.inbox, {}, { freeze: false });
    }

    function getArchive() {
        return Frontend.rpc(METHODS.archive, {}, { freeze: false });
    }

    function getReadyForDelivery() {
        return Frontend.rpc(METHODS.readyForDelivery, {}, { freeze: false });
    }

    function getHandoffContext(stageName) {
        return Frontend.rpc(METHODS.handoffContext, { stage_name: stageName });
    }

    function handoffStage(stageName, nextAssignee = "") {
        const args = { stage_name: stageName };
        if (nextAssignee) args.next_assignee = nextAssignee;
        return Frontend.rpc(METHODS.handoff, args, { freeze: true });
    }

    function logout(freezeMessage = "") {
        return Frontend.rpc(METHODS.logout, {}, {
            freeze: true,
            freezeMessage,
        });
    }

    window.AlmdinaShopFloorInboxApi = Object.freeze({
        METHODS,
        getSessionContext,
        getInbox,
        getArchive,
        getReadyForDelivery,
        getHandoffContext,
        handoffStage,
        logout,
    });
})();
