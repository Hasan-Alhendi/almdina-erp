(() => {
    "use strict";

    if (window.AlmdinaFactoryProductionSettingsCustomerBot) return;

    const EVENT_NAMESPACE = ".almdinaCustomerBotSettings";

    function catalog(t) {
        return {
            fields: {
                welcome: t("Welcome"),
                "service_title.order_status": t("Order status title"),
                "service_title.final_cost": t("Final cost title"),
                "service_title.approved_cutting_plan": t("Cutting plan title"),
                "service_title.measurements": t("Measurements title"),
                invalid_menu_choice: t("Invalid menu choice"),
                no_current_orders: t("No current orders"),
                ask_order_number: t("Ask for the full order number"),
                current_order_line: t("Current order line"),
                order_not_found: t("Order not found"),
                order_not_current: t("Not the current revision"),
                order_cancelled: t("Cancelled order"),
                order_status: t("Order status result"),
                final_price: t("Approved final price result"),
                final_price_unavailable: t("Final price not approved"),
                invoice_failed: t("Invoice PDF failed"),
                price_data_changed: t("Price changed during invoice preparation"),
                approved_plan: t("Approved cutting plan result"),
                approved_plan_unavailable: t("Cutting plan not approved"),
                plan_pdf_failed: t("Cutting plan PDF failed"),
                plan_data_changed: t("Cutting plan changed during preparation"),
                unregistered_phone: t("Unregistered number"),
                invalid_order_number: t("Invalid order number"),
                service_unavailable: t("Service unavailable"),
                "status_label.awaiting_start": t("Status: waiting to start"),
                "status_label.in_progress": t("Status: in progress"),
                "status_label.ready_for_pickup": t("Status: ready for pickup"),
                "status_label.delivered": t("Status: delivered"),
                "status_label.cancelled": t("Status: cancelled"),
                "status_label.unsupported": t("Status: unsupported"),
            },
            groups: {
                welcome_menu: t("Welcome and menu"),
                orders: t("Orders"),
                statuses: t("Statuses"),
                guidance: t("Errors and guidance"),
            },
            variables: {
                order_name: t("Stored order number, unchanged"),
                order_date: t("Order date as stored. Empty when the order has no date"),
                public_status: t("Status label for the order's public status"),
                service_id: t("Editable title of the selected service"),
                return_digit: t("Fixed return digit 0"),
                amount: t("Approved amount, formatted by the service"),
                currency: t("Approved currency from the approval record"),
            },
            scenarios: [
                ["unknown_number", t("Unknown number"), t("Type any message. The sample number is not a customer.")],
                ["no_orders", t("Customer with no orders"), t("Type a greeting then 1. There is no current order.")],
                ["one_order", t("One current order"), t("Type a greeting then 1. The sample order is PREVIEW-DCO-00001.")],
                ["many_orders", t("Several current orders"), t("Type a greeting then 1 then PREVIEW-DCO-00001 or PREVIEW-DCO-00002.")],
                ["delivered_order", t("Earlier delivered order"), t("Type a greeting then 1 then PREVIEW-DCO-DELIVERED.")],
                ["cancelled_order", t("Cancelled order"), t("Type a greeting then 1 then PREVIEW-DCO-CANCELLED.")],
            ],
            issues: {
                missing_key: t("A required text is missing."),
                unknown_key: t("A text is not part of the customer bot."),
                not_text: t("A text must be plain text."),
                empty: t("A text is required."),
                too_long: t("A text is longer than the allowed limit."),
                invalid_syntax: t("A text has an unsupported placeholder."),
                unknown_variable: t("A text uses a variable that is not allowed."),
                invalid_characters: t("A text contains a character that is not allowed."),
            },
        };
    }

    function attach(options = {}) {
        const api = options.api;
        const renderer = options.renderer;
        const frontend = options.frontend;
        const lifecycle = options.lifecycle;
        const translate = options.translate;
        const $body = options.$body;
        if (
            !api
            || !renderer
            || !frontend
            || !lifecycle
            || !$body
            || typeof translate !== "function"
            || typeof frontend.createLatestRequestGate !== "function"
            || typeof renderer.renderCustomerBot !== "function"
        ) {
            throw new Error("Customer bot settings panel dependencies are unavailable");
        }
        const t = (message, replacements) => (
            replacements ? translate(message, replacements) : translate(message)
        );
        const text = catalog(t);
        const loads = frontend.createLatestRequestGate();
        const mutations = frontend.createLatestRequestGate();
        const previews = frontend.createLatestRequestGate();
        let snapshot = null;
        let previewState = null;
        let previewLines = [];
        let previewSource = "draft";
        let busy = false;

        function isActive() {
            return typeof options.isActive !== "function" || options.isActive();
        }

        function root() {
            return $body.find("[data-bot-root]");
        }

        function errorMessage(error, fallback) {
            return frontend.errorMessage(error, fallback);
        }

        function modelFrom(data) {
            const draft = data.draft || {};
            const groups = {};
            (data.fields || []).forEach(field => {
                const group = field.group || "guidance";
                if (!groups[group]) groups[group] = [];
                groups[group].push({
                    key: field.key,
                    label: text.fields[field.key] || field.key,
                    value: Object.prototype.hasOwnProperty.call(draft, field.key) ? draft[field.key] : "",
                    variables: (field.variables || []).map(variable => ({
                        name: variable.name,
                        meaning: text.variables[variable.name] || variable.name,
                        example: variable.example || "",
                    })),
                });
            });
            return {
                enabled: Boolean(data.enabled),
                statusLabel: data.enabled ? t("Marked on for a later connection") : t("Stopped"),
                toggleLabel: data.enabled ? t("Turn the bot off") : t("Mark the bot on"),
                toggleHelp: t("This does not connect WhatsApp or send a message."),
                notice: t("The bot connection to WhatsApp is not active yet. These settings prepare its behavior when the link is complete."),
                meta: [
                    t("Revision {0}", [data.revision]),
                    data.modified ? t("Last change {0}", [data.modified]) : "",
                    data.published_on ? t("Published {0}", [data.published_on]) : t("Not published yet"),
                ].filter(Boolean).join(" · "),
                unpublished: Boolean(data.unpublished),
                previewSource,
                groups: ["welcome_menu", "orders", "statuses", "guidance"].filter(id => groups[id]).map(id => ({
                    id,
                    label: text.groups[id] || id,
                    fields: groups[id],
                })),
                scenarios: text.scenarios.map(item => ({ id: item[0], label: item[1], hint: item[2] })),
            };
        }

        function paint(data) {
            if (!root().length) return;
            renderer.renderCustomerBot(modelFrom(data));
            showHint(root().find("[data-bot-scenario]").val());
            paintTranscript();
            updateBanners();
        }

        function paintTranscript() {
            const host = root().find("[data-bot-transcript]").get(0);
            if (!host) return;
            host.replaceChildren();
            previewLines.forEach(line => {
                const node = document.createElement("p");
                node.className = "aps-bot-line";
                node.textContent = line;
                host.appendChild(node);
            });
        }

        function showHint(id) {
            const row = text.scenarios.find(item => item[0] === id) || text.scenarios[0];
            root().find("[data-bot-hint]").text(row ? row[2] : "");
        }

        function collectTexts() {
            const texts = {};
            root().find("[data-bot-field]").each(function collectField() {
                texts[this.getAttribute("data-bot-field")] = this.value;
            });
            return texts;
        }

        function stable(texts) {
            return JSON.stringify(Object.keys(texts).sort().map(key => [key, texts[key]]));
        }

        function updateBanners() {
            if (!snapshot) return;
            const current = collectTexts();
            root().find("[data-bot-unsaved]").prop("hidden", stable(current) === stable(snapshot.draft || {}));
            root().find("[data-bot-unpublished]").prop("hidden", stable(current) === stable(snapshot.published || {}));
        }

        function showAlert(message) {
            const host = root().find("[data-bot-alert]").get(0);
            if (!host) {
                const node = root().get(0);
                if (node && message) node.textContent = message;
                return;
            }
            host.replaceChildren();
            if (!message) return;
            const node = document.createElement("p");
            node.className = "aps-bot-alert";
            node.textContent = message;
            host.appendChild(node);
        }

        function markIssues(issues) {
            root().find("[data-bot-field]").attr("aria-invalid", "false");
            (issues || []).forEach(issue => {
                root().find("[data-bot-field]").filter(function matchField() {
                    return this.getAttribute("data-bot-field") === issue.key;
                }).attr("aria-invalid", "true");
            });
        }

        function issueMessage(issues) {
            return (issues || []).map(issue => {
                const label = text.fields[issue.key] || issue.key;
                const detail = text.issues[issue.code] || t("The customer bot texts are not valid.");
                return label + ": " + detail;
            }).join("\n");
        }

        function setBusy(next) {
            busy = next;
            root().find("button, textarea, input, select").prop("disabled", next);
        }

        function load() {
            if (!isActive() || !root().length) return Promise.resolve(null);
            const token = loads.begin();
            return api.getCustomerBotSettings({ freeze: false }).then(data => {
                if (!isActive() || !loads.isCurrent(token)) return null;
                if (!data || data.ok === false) {
                    showAlert(t("Could not load customer bot settings."));
                    return null;
                }
                snapshot = data;
                paint(data);
                return data;
            }).catch(error => {
                if (!isActive() || !loads.isCurrent(token)) return null;
                showAlert(errorMessage(error, t("Could not load customer bot settings.")));
                return null;
            });
        }

        function failureMessage(data) {
            if (data && data.code === "conflict") {
                return t("Another change was saved first. Reload the section and review it before saving again.");
            }
            if (data && data.issues && data.issues.length) return issueMessage(data.issues);
            return t("Could not save the customer bot settings. The text is still in the form.");
        }

        function mutate(request, successMessage) {
            if (busy || !snapshot) return;
            const token = mutations.begin();
            setBusy(true);
            showAlert("");
            request(snapshot.revision, collectTexts()).then(data => {
                if (!isActive() || !mutations.isCurrent(token)) return;
                setBusy(false);
                if (!data || data.ok === false) {
                    markIssues(data && data.issues);
                    showAlert(failureMessage(data));
                    return;
                }
                snapshot = data;
                paint(data);
                showAlert(successMessage(data));
            }).catch(error => {
                if (!isActive() || !mutations.isCurrent(token)) return;
                setBusy(false);
                showAlert(errorMessage(error, t("Could not save the customer bot settings. The text is still in the form.")));
            });
        }

        function previewFailure(data) {
            if (data && data.issues && data.issues.length) return issueMessage(data.issues);
            if (data && data.code === "empty_message") return t("Type a customer message first.");
            return t("The preview could not render these texts.");
        }

        function sendPreview() {
            if (busy || !snapshot) return;
            const input = root().find("[data-bot-preview-input]");
            const message = String(input.val() || "");
            if (!message.trim()) return;
            const source = String(root().find("input[name='aps-bot-source']:checked").val() || "draft");
            const scenario = String(root().find("[data-bot-scenario]").val() || "unknown_number");
            previewSource = source;
            const token = previews.begin();
            setBusy(true);
            previewLines.push(t("Sample customer") + ": " + message);
            paintTranscript();
            input.val("");
            api.previewCustomerBot({
                source,
                scenario,
                text: message,
                state: previewState,
                texts: collectTexts(),
            }, { freeze: false }).then(data => {
                if (!isActive() || !previews.isCurrent(token)) return;
                setBusy(false);
                if (!data || data.ok === false) {
                    previewLines.push(previewFailure(data));
                    paintTranscript();
                    markIssues(data && data.issues);
                    return;
                }
                previewState = data.state || null;
                (data.lines || []).forEach(line => previewLines.push(t("Bot reply") + ": " + String(line)));
                paintTranscript();
            }).catch(error => {
                if (!isActive() || !previews.isCurrent(token)) return;
                setBusy(false);
                previewLines.push(errorMessage(error, t("The preview could not render these texts.")));
                paintTranscript();
            });
        }

        function restartPreview() {
            previewState = null;
            previewLines = [];
            paintTranscript();
        }

        $body.on(`click${EVENT_NAMESPACE}`, "[data-bot-save]", () => {
            mutate(
                (revision, texts) => api.saveCustomerBotDraft(revision, texts, { freeze: false }),
                () => t("Draft saved.")
            );
        });
        $body.on(`click${EVENT_NAMESPACE}`, "[data-bot-publish]", () => {
            mutate(
                (revision, texts) => api.publishCustomerBotTexts(revision, texts, { freeze: false }),
                () => t("Texts published. The bot stays in its current on or off state.")
            );
        });
        $body.on(`click${EVENT_NAMESPACE}`, "[data-bot-toggle]", () => {
            if (!snapshot) return;
            const next = !snapshot.enabled;
            mutate(
                revision => api.setCustomerBotEnabled(revision, next, { freeze: false }),
                data => (data.enabled
                    ? t("The bot is now marked on for a later connection.")
                    : t("The bot is stopped."))
            );
        });
        $body.on(`click${EVENT_NAMESPACE}`, "[data-bot-preview-send]", sendPreview);
        $body.on(`click${EVENT_NAMESPACE}`, "[data-bot-restart]", restartPreview);
        $body.on(`input${EVENT_NAMESPACE}`, "[data-bot-field]", updateBanners);
        $body.on(`change${EVENT_NAMESPACE}`, "[data-bot-scenario]", function onScenario() {
            showHint(this.value);
            restartPreview();
        });
        $body.on(`change${EVENT_NAMESPACE}`, "input[name='aps-bot-source']", function onSource() {
            previewSource = this.value === "published" ? "published" : "draft";
            restartPreview();
        });
        $body.on(`keydown${EVENT_NAMESPACE}`, "[data-bot-preview-input]", function onPreviewKey(event) {
            if (event.key === "Enter") {
                event.preventDefault();
                sendPreview();
            }
        });
        lifecycle.track(() => $body.off(EVENT_NAMESPACE), "customer-bot-settings-panel");

        return Object.freeze({
            refresh: load,
            deactivate() {},
            dispose() {
                $body.off(EVENT_NAMESPACE);
            },
        });
    }

    window.AlmdinaFactoryProductionSettingsCustomerBot = Object.freeze({ attach });
})();
