(() => {
    "use strict";

    if (window.AlmdinaDcoWorkspaceAssetStatusUX) return;

    const FEATURE_FIELDS = Object.freeze({
        plan: "cutting_plan_html",
        cost: "order_cost_invoice_html",
    });

    function wrapper(frm, feature) {
        const fieldname = FEATURE_FIELDS[String(feature || "")];
        const field = fieldname && frm && frm.fields_dict && frm.fields_dict[fieldname];
        return field && field.$wrapper ? field.$wrapper : null;
    }

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
                text = text.split("{" + index + "}").join(String(value));
            });
        }
        return text;
    }

    function featureLabel(feature) {
        return feature === "plan" ? translate("Cutting plan") : translate("Order cost");
    }

    function uiButton(options) {
        const ui = window.AlmdinaUi;
        if (!ui || typeof ui.button !== "function") {
            throw new Error("AlmdinaUi.button is required for DCO workspace asset status");
        }
        return ui.button(options);
    }

    function renderLoading(frm, feature) {
        const target = wrapper(frm, feature);
        if (!target || (typeof target.children === "function" && target.children().length)) return false;
        target.html(`
            <div class="dco-workspace-asset-status" data-phase="loading" role="status" aria-live="polite"
                 style="padding:18px;text-align:center;border:1px dashed var(--border-color,#dfe3e8);border-radius:12px;background:var(--subtle-fg,#fafbfc);color:var(--text-muted,#667085);">
                <strong style="display:block;margin-bottom:5px;color:var(--text-color,#26313b);">${frappe.utils.escape_html(translate("Preparing the section"))}</strong>
                <span>${frappe.utils.escape_html(translate("Loading {0} on this device for the first time.", [featureLabel(feature)]))}</span>
            </div>
        `);
        return true;
    }

    function clearStatus(frm, feature) {
        const target = wrapper(frm, feature);
        if (!target || typeof target.find !== "function") return false;
        target.find(".dco-workspace-asset-status").remove();
        return true;
    }

    function renderFailure(frm, feature, errorMessage) {
        const target = wrapper(frm, feature);
        if (!target) return false;
        const label = featureLabel(feature);
        target.html(`
            <div class="almdina-ui dco-workspace-asset-status" data-phase="failed" role="alert"
                 style="padding:18px;text-align:center;border:1px solid rgba(220,53,69,.25);border-radius:12px;background:rgba(220,53,69,.04);">
                <strong style="display:block;margin-bottom:6px;color:var(--text-color,#26313b);">${frappe.utils.escape_html(translate("Could not load {0}", [label]))}</strong>
                <span style="display:block;margin-bottom:12px;color:var(--text-muted,#667085);">${frappe.utils.escape_html(errorMessage || translate("Check the internet connection, then try again."))}</span>
                ${uiButton({
                    label: translate("Try again"),
                    variant: "primary",
                    size: "btn-sm",
                    className: "dco-workspace-assets-retry",
                })}
            </div>
        `);
        const button = target.find(".dco-workspace-assets-retry");
        if (button && typeof button.off === "function" && typeof button.on === "function") {
            button.off("click.almdinaWorkspaceAssets").on("click.almdinaWorkspaceAssets", () => retry(frm, feature));
        }
        return true;
    }

    function retry(frm, feature) {
        const registry = window.AlmdinaDcoWorkspaceAssetRegistry;
        const lifecycle = window.AlmdinaDcoWorkspaceActivationLifecycle;
        if (!registry || typeof registry.ensure !== "function") return Promise.resolve(false);
        renderLoading(frm, feature);
        return Promise.resolve(registry.ensure(feature, { force: true }))
            .then(() => {
                clearStatus(frm, feature);
                if (lifecycle && typeof lifecycle.schedule === "function") {
                    lifecycle.schedule(frm, { force: true });
                }
                return true;
            })
            .catch(error => {
                renderFailure(frm, feature, String(error && error.message || error || ""));
                return false;
            });
    }

    window.addEventListener("almdina:workspace-assets-status", event => {
        const detail = event && event.detail || {};
        const feature = String(detail.feature || "");
        const frm = window.cur_frm;
        if (!frm || frm.doctype !== "Door Cutting Order" || !FEATURE_FIELDS[feature]) return;
        if (detail.phase === "loading") {
            renderLoading(frm, feature);
            return;
        }
        if (detail.phase === "loaded") {
            clearStatus(frm, feature);
            return;
        }
        if (detail.phase === "failed") {
            renderFailure(frm, feature, String(detail.error || ""));
        }
    });

    window.AlmdinaDcoWorkspaceAssetStatusUX = Object.freeze({
        clearStatus,
        renderFailure,
        renderLoading,
        retry,
    });
})();
