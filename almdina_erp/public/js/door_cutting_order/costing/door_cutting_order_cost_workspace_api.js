(() => {
    "use strict";

    function translate(message, replacements) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") {
            return locale.translate(message, replacements);
        }
        if (typeof __ === "function") {
            return replacements === undefined ? __(message) : __(message, replacements);
        }
        let text = String(message == null ? "" : message);
        if (Array.isArray(replacements)) {
            replacements.forEach((value, index) => {
                text = text.split(`{${index}}`).join(String(value));
            });
        }
        return text;
    }

    if (window.AlmdinaCostWorkspaceAPI) return;

    const READ_METHOD =
        "almdina_erp.almdina_erp.services.cost_permission_service.get_order_cost_snapshot";
    const SAVE_SETTINGS_METHOD =
        "almdina_erp.almdina_erp.services.cost_permission_service.update_order_cost_settings";
    const SAVE_WORKSPACE_METHOD =
        "almdina_erp.almdina_erp.services.cost_permission_service.save_cost_workspace";
    const APPROVE_FINAL_PRICE_METHOD =
        "almdina_erp.almdina_erp.services.final_price_approval_service.approve_order_final_price";
    const CANCEL_FINAL_PRICE_METHOD =
        "almdina_erp.almdina_erp.services.final_price_approval_service.cancel_order_final_price_approval";

    function unwrapResponse(response) {
        return response && response.message !== undefined ? response.message : response;
    }

    function legacyCall(runtime, request) {
        return new Promise((resolve, reject) => {
            let settled = false;
            const succeed = (response) => {
                if (settled) return;
                settled = true;
                resolve(unwrapResponse(response));
            };
            const fail = (error) => {
                if (settled) return;
                settled = true;
                reject(error);
            };

            try {
                runtime.call({ ...request, callback: succeed, error: fail });
            } catch (error) {
                fail(error);
            }
        });
    }

    async function call(method, args, options = {}) {
        const runtime = window.frappe || null;
        if (!runtime) throw new Error("Frappe RPC is unavailable");

        // Frappe v16 exposes xcall as the native Promise RPC boundary. Using it
        // first avoids the legacy jQuery Deferred callback path that can surface
        // opaque errors such as "s is not a function" in the Cost workspace.
        if (typeof runtime.xcall === "function" && !options.freeze) {
            const result = await runtime.xcall(method, args || {});
            return unwrapResponse(result);
        }

        if (typeof runtime.call !== "function") {
            throw new Error("Frappe RPC is unavailable");
        }

        return legacyCall(runtime, {
            method,
            args,
            freeze: Boolean(options.freeze),
            freeze_message: options.freezeMessage || undefined,
        });
    }

    function load(orderName) {
        return call(READ_METHOD, { order_name: orderName });
    }

    function saveSettings(orderName, settings, expectedModified) {
        const values = settings || {};
        return saveWorkspace(orderName, {
            cost_settings: {
                board_rate_usd: values.board_rate_usd,
                cutting_cost_per_board_usd: values.cutting_cost_per_board_usd,
                offcut_price_usd: values.offcut_price_usd,
            },
        }, expectedModified);
    }

    function saveWorkspace(orderName, payload, expectedModified) {
        const values = payload || {};
        return call(
            SAVE_WORKSPACE_METHOD,
            {
                order_name: orderName,
                cost_settings: values.cost_settings || undefined,
                special_prices: values.special_prices || undefined,
                expected_modified: expectedModified,
            },
            {
                freeze: true,
                freezeMessage: translate("Saving cost and special door prices..."),
            }
        );
    }

    function approveFinalPrice(orderName, expectedPriceBasisToken, approvalNote) {
        const args = {
            order_name: orderName,
            expected_price_basis_token: expectedPriceBasisToken,
        };
        if (approvalNote !== undefined) {
            args.approval_note = approvalNote;
        }
        return call(
            APPROVE_FINAL_PRICE_METHOD,
            args,
            {
                freeze: true,
                freezeMessage: translate("Approving the final price..."),
            }
        );
    }

    function cancelFinalPriceApproval(orderName, expectedCurrentPriceApproval) {
        return call(
            CANCEL_FINAL_PRICE_METHOD,
            {
                order_name: orderName,
                expected_current_price_approval: expectedCurrentPriceApproval,
            },
            {
                freeze: true,
                freezeMessage: translate("Cancelling the final price approval..."),
            }
        );
    }

    window.AlmdinaCostWorkspaceAPI = Object.freeze({
        READ_METHOD,
        SAVE_SETTINGS_METHOD,
        SAVE_WORKSPACE_METHOD,
        APPROVE_FINAL_PRICE_METHOD,
        CANCEL_FINAL_PRICE_METHOD,
        load,
        saveSettings,
        saveWorkspace,
        approveFinalPrice,
        cancelFinalPriceApproval,
    });
})();
