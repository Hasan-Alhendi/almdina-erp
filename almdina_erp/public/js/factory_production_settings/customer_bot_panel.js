(() => {
    "use strict";

    if (window.AlmdinaFactoryProductionSettingsCustomerBot) return;

    const EVENT_NAMESPACE = ".almdinaCustomerBotSettings";
    const ACTIVATING_POLL_MS = 4000;
    const STEADY_POLL_MS = 20000;
    const HOSTING_REASONS = {
        public_base_url_missing: true,
        ingest_user_failed: true,
        webhook_secret_failed: true,
        webhook_failed: true,
        gateway_key_role_insufficient: true,
    };
    const TEXT_TABS = ["texts", "preview"];
    const GROUP_ORDER = [
        ["welcome_menu", [
            "welcome",
            "service_title.order_status",
            "service_title.final_cost",
            "service_title.approved_cutting_plan",
            "service_title.measurements",
            "invalid_menu_choice",
        ]],
        ["order_selection", [
            "no_current_orders",
            "ask_order_number",
            "current_order_line",
            "order_not_found",
            "order_not_current",
            "order_cancelled",
            "invalid_order_number",
        ]],
        ["order_statuses", [
            "order_status",
            "status_label.awaiting_start",
            "status_label.in_progress",
            "status_label.ready_for_pickup",
            "status_label.delivered",
            "status_label.cancelled",
            "status_label.unsupported",
        ]],
        ["price_invoice", [
            "final_price",
            "final_price_unavailable",
            "invoice_failed",
            "price_data_changed",
        ]],
        ["cutting_plan", [
            "approved_plan",
            "approved_plan_unavailable",
            "plan_pdf_failed",
            "plan_data_changed",
        ]],
        ["measurements", [
            "order_measurements",
            "measurements_unavailable",
            "measurements_pdf_failed",
            "measurements_data_changed",
        ]],
        ["general_errors", [
            "unregistered_phone",
            "service_unavailable",
        ]],
    ];

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
                order_measurements: t("Order measurements attachment"),
                measurements_unavailable: t("No measurements available"),
                measurements_pdf_failed: t("Measurements document failed"),
                measurements_data_changed: t("Measurements changed during preparation"),
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
                order_selection: t("Order selection and guidance"),
                order_statuses: t("Order statuses"),
                price_invoice: t("Price and invoice"),
                cutting_plan: t("Cutting plan"),
                measurements: t("Measurements"),
                general_errors: t("General errors"),
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

    function groupIdFor(key) {
        for (let index = 0; index < GROUP_ORDER.length; index += 1) {
            if (GROUP_ORDER[index][1].indexOf(key) >= 0) return GROUP_ORDER[index][0];
        }
        return "general_errors";
    }

    function copyTexts(texts) {
        const copy = {};
        Object.keys(texts || {}).forEach(key => {
            copy[key] = texts[key] == null ? "" : String(texts[key]);
        });
        return copy;
    }

    function stable(texts) {
        return JSON.stringify(Object.keys(texts || {}).sort().map(key => [key, texts[key]]));
    }

    function shortStamp(value) {
        const text = String(value || "").trim().replace(/\.\d+$/, "");
        const match = text.match(/^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})/);
        return match ? `${match[1]} ${match[2]}` : "";
    }

    function attach(options = {}) {
        const api = options.api;
        const renderer = options.renderer;
        const frontend = options.frontend;
        const lifecycle = options.lifecycle;
        const translate = options.translate;
        const dialogs = options.dialogs;
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
            || typeof renderer.renderCustomerBotOperation !== "function"
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
        let working = null;
        let localEpoch = 0;
        let forceNextLoad = false;
        let previewState = null;
        let previewLines = [];
        let previewSource = "draft";
        let scenarioId = "unknown_number";
        let activeTab = "texts";
        let activeGroup = "welcome_menu";
        let searchQuery = "";
        let fieldIssues = [];
        let focusKey = "";
        let focusStart = null;
        let focusEnd = null;
        let busy = false;
        let operation = null;
        let operationFault = "";
        let actionMessage = "";
        let detailsOpen = false;
        let technicalOpen = false;
        let testDialog = null;
        let pollTimer = null;
        const inflight = { start: false, stop: false, check: false };
        const operationReads = frontend.createLatestRequestGate();
        const operationActions = frontend.createLatestRequestGate();

        function isActive() {
            return typeof options.isActive !== "function" || options.isActive();
        }

        function root() {
            return $body.find("[data-bot-root]");
        }

        function errorMessage(error, fallback) {
            return frontend.errorMessage(error, fallback);
        }

        function isDirty() {
            return Boolean(snapshot && working && stable(working) !== stable(snapshot.draft || {}));
        }

        function syncWorkingFromDom() {
            if (!working) return;
            root().find("[data-bot-field]").each(function readField() {
                const key = this.getAttribute("data-bot-field");
                if (key) working[key] = this.value;
            });
        }

        function rememberFocus(node) {
            if (!node || typeof node.getAttribute !== "function") return;
            focusKey = node.getAttribute("data-bot-field") || "";
            focusStart = typeof node.selectionStart === "number" ? node.selectionStart : null;
            focusEnd = typeof node.selectionEnd === "number" ? node.selectionEnd : focusStart;
        }

        function restoreFocus() {
            if (!focusKey || typeof document === "undefined") return;
            const active = document.activeElement;
            if (active && active !== document.body && active !== document.documentElement) return;
            const node = root().find("[data-bot-field]").filter(function matchFocus() {
                return this.getAttribute("data-bot-field") === focusKey;
            }).get(0);
            if (!node || typeof node.focus !== "function") return;
            node.focus();
            if (focusStart != null && typeof node.setSelectionRange === "function") {
                try {
                    node.setSelectionRange(focusStart, focusEnd == null ? focusStart : focusEnd);
                } catch (error) {
                    return error;
                }
            }
            return undefined;
        }

        function issueText(issue) {
            return text.issues[issue.code] || t("The customer bot texts are not valid.");
        }

        function fieldError(key) {
            const issue = fieldIssues.find(item => item.key === key);
            return issue ? issueText(issue) : "";
        }

        function matchesQuery(key, label) {
            const query = searchQuery.trim().toLowerCase();
            if (!query) return true;
            return String(key || "").toLowerCase().includes(query)
                || String(label || "").toLowerCase().includes(query);
        }

        function readPermissions() {
            if (typeof options.permissions !== "function") {
                return { canOperate: false, canEditTexts: true };
            }
            const value = options.permissions() || {};
            return {
                canOperate: Boolean(value.canOperate),
                canEditTexts: Boolean(value.canEditTexts),
            };
        }

        function reasonText(code) {
            const reasons = {
                texts_invalid: t("The published texts are not valid."),
                session_missing: t("No WhatsApp session is linked to this factory."),
                session_login_required: t("WhatsApp needs to be linked again from the current WhatsApp section. This panel does not create a session or a QR code."),
                session_unreachable: t("The WhatsApp connection is interrupted. The run decision and session data stay in place."),
                session_mismatch: t("The WhatsApp session does not match this factory."),
                public_base_url_missing: t("The public site address is not configured."),
                ingest_user_failed: t("The message intake account is not ready."),
                webhook_secret_failed: t("The connection secret could not be prepared."),
                webhook_failed: t("The gateway could not register the callback."),
                gateway_key_role_insufficient: t("The gateway key cannot register the callback."),
                queue_unproven: t("The work queue did not confirm a job."),
                pdf_unavailable: t("Document preparation is not available."),
                scheduler_disabled: t("Scheduled jobs are turned off."),
                operation_busy: t("Another activation is still running."),
                superseded: t("A newer run decision replaced this attempt."),
                operation_failed: t("The operation could not be completed."),
            };
            return reasons[code] || "";
        }

        function stateLabel(state) {
            const labels = {
                stopped: t("Stopped"),
                needs_setup: t("Needs setup"),
                activating: t("Activating"),
                ready: t("Ready"),
                degraded: t("Fault"),
            };
            return labels[state] || t("Needs setup");
        }

        function stateTone(state) {
            if (state === "ready") return "success";
            if (state === "activating") return "info";
            if (state === "needs_setup") return "warning";
            if (state === "degraded") return "danger";
            return "neutral";
        }

        function sessionStatus(data) {
            return String((data && data.session && data.session.status) || "");
        }

        function gatewayAnswered(data) {
            const status = sessionStatus(data);
            return status === "ready" || status === "login_required";
        }

        function connectionFailed(data) {
            if (sessionStatus(data) !== "unreachable") return false;
            return Boolean(
                data
                && (
                    data.state === "degraded"
                    || data.reason === "session_unreachable"
                    || data.last_error
                )
            );
        }

        function whatsAppValue(data) {
            const session = (data && data.session) || {};
            const status = String(session.status || "");
            if (status === "ready" && session.matches_factory === true) return t("Connected");
            if (status === "ready" && session.matches_factory === false) {
                return t("The WhatsApp session does not match this factory.");
            }
            if (status === "login_required") return t("Needs linking");
            if (status === "missing") return t("No session");
            if (connectionFailed(data)) return t("Connection interrupted");
            return t("Not checked");
        }

        function gatewayValue(data) {
            if (gatewayAnswered(data)) return t("Connected");
            if (connectionFailed(data)) return t("Connection interrupted");
            return t("Not checked");
        }

        function webhookValue(data) {
            if (data && data.webhook_registered) return t("Registered");
            if (gatewayAnswered(data)) return t("Not registered");
            return t("Not checked");
        }

        function provesReady(data) {
            return Boolean(
                data
                && data.state === "ready"
                && data.decision === "running"
                && data.transport_armed
                && data.connection_ready
            );
        }

        function replyValue(data) {
            if (provesReady(data)) return t("Ready to reply");
            const queue = (data && data.queue) || {};
            if (queue.checked_at) return queue.ok ? t("Proven") : t("Not proven");
            return t("Not checked");
        }

        function stampOrNone(value) {
            return shortStamp(value) || t("None yet");
        }

        function operationModel() {
            const perms = readPermissions();
            if (!perms.canOperate) {
                return {
                    visible: false,
                    unavailable: t("Operation controls are available to the account allowed to run the bot."),
                };
            }
            if (!operation && !operationFault) {
                return {
                    visible: true,
                    pending: true,
                    stateLabel: "",
                    tone: "neutral",
                    reason: t("Loading customer bot settings..."),
                    reasonTone: "neutral",
                    showStart: false,
                    showStop: false,
                    startDisabled: true,
                    stopDisabled: true,
                    checkDisabled: true,
                    detailsOpen: false,
                    technicalOpen: false,
                    technical: "",
                    facts: [],
                    events: [],
                };
            }
            const data = operation || {};
            const state = String(data.state || "needs_setup");
            const decision = String(data.decision || "stopped");
            const running = decision === "running" || state === "activating" || inflight.start;
            const reasonCode = String(data.reason || "");
            const specific = operationFault || (state === "ready" || (state === "stopped" && !reasonCode) ? "" : reasonText(reasonCode));
            let reason = "";
            let reasonTone = "neutral";
            if (specific) {
                reason = specific;
                reasonTone = "danger";
            } else if (actionMessage) {
                reason = actionMessage;
                reasonTone = (
                    actionMessage === t("Activation did not finish.")
                    || actionMessage === t("Could not start the bot.")
                    || actionMessage === t("Could not stop the bot.")
                    || actionMessage === t("Could not check the connection.")
                ) ? "danger" : "neutral";
            }
            return {
                visible: true,
                pending: false,
                stateLabel: stateLabel(state),
                tone: stateTone(state),
                reason,
                reasonTone,
                showStart: !running,
                showStop: running,
                startDisabled: Boolean(inflight.start || inflight.check),
                stopDisabled: Boolean(inflight.stop),
                checkDisabled: Boolean(inflight.start || inflight.stop || inflight.check),
                detailsOpen,
                technicalOpen,
                technical: HOSTING_REASONS[reasonCode]
                    ? t("A hosting administrator configures the public address, the gateway operator key, and the allowed callback hosts once. This screen does not ask you to run server commands.")
                    : "",
                facts: [
                    { label: t("WhatsApp"), value: whatsAppValue(data) },
                    { label: t("Gateway"), value: gatewayValue(data) },
                    { label: t("Webhook"), value: webhookValue(data) },
                    { label: t("Reply processing"), value: replyValue(data) },
                ],
                events: [
                    { label: t("Last accepted inbound"), value: stampOrNone(data.last_accepted_inbound_at), ltr: true },
                    { label: t("Last send accepted by the gateway"), value: stampOrNone(data.last_gateway_accept_at), ltr: true },
                    { label: t("Last error"), value: data.last_error ? String(data.last_error) : t("None yet"), ltr: Boolean(data.last_error) },
                ],
            };
        }

        function clearPoll() {
            if (pollTimer != null && typeof clearTimeout === "function") clearTimeout(pollTimer);
            pollTimer = null;
        }

        function schedulePoll() {
            clearPoll();
            if (!isActive() || !readPermissions().canOperate || typeof setTimeout !== "function") return;
            const delay = operation && operation.state === "activating" ? ACTIVATING_POLL_MS : STEADY_POLL_MS;
            pollTimer = setTimeout(() => {
                pollTimer = null;
                if (!isActive()) return;
                readOperation();
            }, delay);
        }

        function renderOperation() {
            if (!root().length || !readPermissions().canOperate) return;
            if (readPermissions().canEditTexts && !snapshot) return;
            if (!root().find("[data-bot-operation]").length) {
                paint();
                return;
            }
            renderer.renderCustomerBotOperation({ operation: operationModel() });
        }

        function readOperation() {
            if (!isActive() || !readPermissions().canOperate) return Promise.resolve(null);
            if (typeof api.getCustomerBotOperationStatus !== "function") return Promise.resolve(null);
            const token = operationReads.begin();
            return api.getCustomerBotOperationStatus({ freeze: false }).then(data => {
                if (!isActive() || !operationReads.isCurrent(token)) return null;
                operation = data || {};
                operationFault = "";
                renderOperation();
                schedulePoll();
                return data;
            }).catch(error => {
                if (!isActive() || !operationReads.isCurrent(token)) return null;
                operationFault = errorMessage(error, t("Could not read the bot operation status."));
                renderOperation();
                schedulePoll();
                return null;
            });
        }

        function actionResult(kind, data) {
            const state = data && data.state;
            if (kind === "stop") return "";
            if (kind === "check") {
                if (provesReady(data)) return t("The check is complete, and the bot is ready to reply.");
                return t("Connection check finished.");
            }
            if (state === "ready") return "";
            if (data && reasonText(data.reason)) return "";
            return t("Activation did not finish.");
        }

        function actionFailure(kind) {
            if (kind === "stop") return t("Could not stop the bot.");
            if (kind === "check") return t("Could not check the connection.");
            return t("Could not start the bot.");
        }

        function runOperation(kind) {
            if (!isActive() || !readPermissions().canOperate) return;
            const decision = operation && operation.decision;
            const state = operation && operation.state;
            const running = decision === "running" || state === "activating" || inflight.start;
            if (kind === "start" && running) return;
            if (kind === "stop" && !running) return;
            if (kind === "stop") {
                if (inflight.stop) return;
            } else if (inflight.start || inflight.stop || inflight.check) {
                return;
            }
            const method = kind === "start"
                ? api.startCustomerBotOperation
                : kind === "stop"
                    ? api.stopCustomerBotOperation
                    : api.checkCustomerBotOperation;
            if (typeof method !== "function") return;
            inflight[kind] = true;
            const token = operationActions.begin();
            operationReads.begin();
            actionMessage = "";
            renderOperation();
            method({ freeze: false }).then(data => {
                inflight[kind] = false;
                if (!isActive() || !operationActions.isCurrent(token)) return;
                operation = data || {};
                operationFault = "";
                actionMessage = actionResult(kind, data);
                renderOperation();
                schedulePoll();
            }).catch(error => {
                inflight[kind] = false;
                if (!isActive() || !operationActions.isCurrent(token)) return;
                actionMessage = errorMessage(error, actionFailure(kind));
                renderOperation();
                schedulePoll();
            });
        }

        function releaseOperation() {
            clearPoll();
            inflight.start = false;
            inflight.stop = false;
            inflight.check = false;
            operationReads.begin();
            operationActions.begin();
        }

        function modelFrom() {
            const data = snapshot || {};
            const fields = [];
            const grouped = {};
            (data.fields || []).forEach(field => {
                const groupId = groupIdFor(field.key);
                if (!grouped[groupId]) grouped[groupId] = [];
                const label = text.fields[field.key] || field.key;
                const value = working && Object.prototype.hasOwnProperty.call(working, field.key)
                    ? working[field.key]
                    : "";
                const view = {
                    key: field.key,
                    groupId,
                    label,
                    value,
                    maxLength: field.max_length || 0,
                    countLabel: field.max_length ? t("{0} / {1}", [String(value || "").length, field.max_length]) : "",
                    invalid: Boolean(fieldError(field.key)),
                    error: fieldError(field.key),
                    hidden: groupId !== activeGroup || !matchesQuery(field.key, label),
                    variables: (field.variables || []).map(variable => ({
                        name: variable.name,
                        meaning: text.variables[variable.name] || variable.name,
                        example: variable.example || "",
                    })),
                };
                grouped[groupId].push(view);
                fields.push(view);
            });
            const visibleGroups = GROUP_ORDER.map(([id]) => id).filter(id => grouped[id] && grouped[id].length);
            (data.fields || []).forEach(field => {
                if (visibleGroups.indexOf(groupIdFor(field.key)) < 0 && grouped[groupIdFor(field.key)]) {
                    visibleGroups.push(groupIdFor(field.key));
                }
            });
            if (visibleGroups.indexOf(activeGroup) < 0 && visibleGroups.length) activeGroup = visibleGroups[0];
            const publishedAt = shortStamp(data.published_on);
            const scenario = text.scenarios.find(item => item[0] === scenarioId) || text.scenarios[0];
            const perms = readPermissions();
            const tabs = perms.canEditTexts ? TEXT_TABS.slice() : [];
            if (tabs.length && tabs.indexOf(activeTab) < 0) activeTab = tabs[0];
            return {
                canEditTexts: perms.canEditTexts,
                publishedLabel: publishedAt ? t("Last published {0}", [publishedAt]) : t("Not published yet"),
                publishedAt,
                revisionLabel: t("Revision {0}", [data.revision == null ? "" : data.revision]),
                unsaved: isDirty(),
                unpublished: Boolean(working && stable(working) !== stable(data.published || {})),
                tabsLabel: t("Customer bot sections"),
                groupsLabel: t("Message texts"),
                searchPlaceholder: t("Search by title or message key"),
                saveHelp: t("Save draft stores all editor texts. Publish stores those same texts as the draft and the published copy."),
                query: searchQuery,
                searchEmpty: Boolean(searchQuery.trim()) && !fields.some(field => field.groupId === activeGroup && !field.hidden),
                activeTab,
                operation: operationModel(),
                tabs: [
                    ["texts", t("Message texts")],
                    ["preview", t("Preview")],
                ].filter(([id]) => perms.canEditTexts).map(([id, label]) => ({
                    id,
                    label,
                    selected: id === activeTab,
                })),
                groups: visibleGroups.map(id => ({
                    id,
                    label: text.groups[id] || id,
                    selected: id === activeGroup,
                    hasMatch: !searchQuery.trim() || (grouped[id] || []).some(field => matchesQuery(field.key, field.label)),
                })),
                fields,
                previewSource,
                previewNote: previewSource === "published"
                    ? t("This preview uses the published copy stored on the server and ignores unsaved edits.")
                    : t("This preview uses the texts currently in the editors, including edits that are not saved yet."),
                scenarios: text.scenarios.map(item => ({
                    id: item[0],
                    label: item[1],
                    hint: item[2],
                    selected: item[0] === (scenario ? scenario[0] : ""),
                })),
                scenarioHint: scenario ? scenario[2] : "",
            };
        }

        function paint() {
            if (!root().length) return;
            if (!snapshot && readPermissions().canEditTexts) return;
            renderer.renderCustomerBot(modelFrom());
            paintTranscript();
            restoreFocus();
            applyAlert();
        }

        function paintTranscript() {
            const host = root().find("[data-bot-transcript]").get(0);
            if (!host || typeof host.replaceChildren !== "function") return;
            host.replaceChildren();
            previewLines.forEach(line => {
                const node = document.createElement("p");
                node.className = "aps-bot-line";
                node.textContent = line;
                host.appendChild(node);
            });
        }

        function setChoiceVariant(node, selected) {
            if (!node || !node.classList) return;
            node.classList.remove("alm-btn-primary", "alm-btn-secondary");
            node.classList.add(selected ? "alm-btn-primary" : "alm-btn-secondary");
        }

        function applyChrome() {
            root().find("[data-bot-panel]").each(function showPanel() {
                this.hidden = this.getAttribute("data-bot-panel") !== activeTab;
            });
            root().find("[data-bot-tab]").each(function markTab() {
                const selected = this.getAttribute("data-bot-tab") === activeTab;
                this.setAttribute("aria-selected", selected ? "true" : "false");
                this.tabIndex = selected ? 0 : -1;
                setChoiceVariant(this, selected);
            });
            const hits = {};
            let visible = 0;
            root().find("[data-bot-field-wrap]").each(function showField() {
                const key = this.getAttribute("data-bot-field-wrap") || "";
                const label = this.getAttribute("data-bot-label") || "";
                const groupId = this.getAttribute("data-bot-group") || "";
                const match = matchesQuery(key, label);
                if (match) hits[groupId] = true;
                const show = match && groupId === activeGroup;
                this.hidden = !show;
                if (show) visible += 1;
            });
            root().find("[data-bot-group-button]").each(function markGroup() {
                const id = this.getAttribute("data-bot-group-button") || "";
                const selected = id === activeGroup;
                this.setAttribute("aria-pressed", selected ? "true" : "false");
                this.setAttribute("data-bot-group-match", !searchQuery.trim() || hits[id] ? "1" : "0");
                setChoiceVariant(this, selected);
            });
            root().find("[data-bot-search-empty]").prop("hidden", !(searchQuery.trim() && visible === 0));
            const note = previewSource === "published"
                ? t("This preview uses the published copy stored on the server and ignores unsaved edits.")
                : t("This preview uses the texts currently in the editors, including edits that are not saved yet.");
            root().find("[data-bot-preview-note]").text(note);
        }

        function updateBanners() {
            if (!snapshot || !working) return;
            syncWorkingFromDom();
            root().find("[data-bot-unsaved]").prop("hidden", !isDirty());
            root().find("[data-bot-unpublished]").prop(
                "hidden",
                stable(working) === stable(snapshot.published || {})
            );
        }

        function updateCount(node) {
            const key = node.getAttribute("data-bot-field");
            const field = (snapshot.fields || []).find(item => item.key === key);
            if (!field || !field.max_length) return;
            root().find("[data-bot-count]").filter(function matchCount() {
                return this.getAttribute("data-bot-count") === key;
            }).text(t("{0} / {1}", [String(node.value || "").length, field.max_length]));
        }

        function showAlert(message) {
            actionMessage = message || "";
            applyAlert();
        }

        function applyAlert() {
            const host = root().find("[data-bot-alert]").get(0);
            if (!host || typeof host.replaceChildren !== "function") return;
            host.replaceChildren();
            if (!actionMessage) return;
            const node = document.createElement("p");
            node.className = "aps-bot-alert";
            node.textContent = actionMessage;
            host.appendChild(node);
        }

        function markIssues(issues) {
            fieldIssues = Array.isArray(issues) ? issues : [];
            if (fieldIssues.length) {
                activeTab = "texts";
                activeGroup = groupIdFor(fieldIssues[0].key);
                searchQuery = "";
                root().find("[data-bot-search]").val("");
            }
            applyChrome();
            root().find("[data-bot-field]").each(function markField() {
                const key = this.getAttribute("data-bot-field");
                this.setAttribute("aria-invalid", fieldError(key) ? "true" : "false");
            });
            root().find("[data-bot-error]").each(function showError() {
                const key = this.getAttribute("data-bot-error");
                const message = fieldError(key);
                this.hidden = !message;
                this.textContent = message;
            });
        }

        function issueMessage(issues) {
            return (issues || []).map(issue => {
                const label = text.fields[issue.key] || issue.key;
                return `${label}: ${issueText(issue)}`;
            }).join("\n");
        }

        function setBusy(next) {
            busy = next;
            root().find("button, textarea, input, select").prop("disabled", next);
        }

        function load() {
            if (!isActive() || !root().length) return Promise.resolve(null);
            const perms = readPermissions();
            const jobs = [];
            if (perms.canEditTexts) jobs.push(loadSettings());
            else jobs.push(Promise.resolve(paint()));
            if (perms.canOperate) jobs.push(readOperation());
            if (!jobs.length) return Promise.resolve(null);
            return Promise.all(jobs).then(() => null);
        }

        function loadSettings() {
            if (!isActive() || !root().length || !readPermissions().canEditTexts) return Promise.resolve(null);
            const epoch = localEpoch;
            const token = loads.begin();
            return api.getCustomerBotSettings({ freeze: false }).then(data => {
                if (!isActive() || !loads.isCurrent(token)) return null;
                if (!data || data.ok === false) {
                    showAlert(t("Could not load customer bot settings."));
                    return null;
                }
                const editedDuringRequest = epoch !== localEpoch;
                const keepLocal = Boolean(snapshot && isDirty() && !forceNextLoad);
                if ((!keepLocal && !editedDuringRequest) || !snapshot) {
                    snapshot = data;
                    working = copyTexts(data.draft);
                    forceNextLoad = false;
                    fieldIssues = [];
                }
                paint();
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

        function mutate(request, successMessage, replaceTexts) {
            if (!readPermissions().canEditTexts || busy || !snapshot || !working) return;
            syncWorkingFromDom();
            const token = mutations.begin();
            setBusy(true);
            showAlert("");
            request(snapshot.revision, copyTexts(working)).then(data => {
                if (!isActive() || !mutations.isCurrent(token)) return;
                setBusy(false);
                if (!data || data.ok === false) {
                    if (data && data.code === "conflict") forceNextLoad = true;
                    markIssues(data && data.issues);
                    showAlert(failureMessage(data));
                    return;
                }
                snapshot = data;
                if (replaceTexts) {
                    working = copyTexts(data.draft);
                    localEpoch += 1;
                    fieldIssues = [];
                }
                paint();
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
            if (!readPermissions().canEditTexts || busy || !snapshot || !working) return;
            const input = root().find("[data-bot-preview-input]");
            const message = String(input.val() || "");
            if (!message.trim()) return;
            const source = String(root().find("input[name='aps-bot-source']:checked").val() || "draft");
            const scenario = String(root().find("[data-bot-scenario]").val() || scenarioId);
            previewSource = source === "published" ? "published" : "draft";
            scenarioId = scenario;
            syncWorkingFromDom();
            const token = previews.begin();
            setBusy(true);
            previewLines.push(`${t("Sample customer")}: ${message}`);
            paintTranscript();
            input.val("");
            api.previewCustomerBot({
                source: previewSource,
                scenario: scenarioId,
                text: message,
                state: previewState,
                texts: copyTexts(working),
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
                (data.lines || []).forEach(line => previewLines.push(`${t("Bot reply")}: ${String(line)}`));
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

        function testSteps() {
            return [
                t("Confirm the bot is running before you send a message."),
                t("Send one short message from the customer's saved WhatsApp number, such as a greeting or the digit 1."),
                t("The bot replies only while it is running, the number is registered to one customer, and the message is a supported service."),
                t("This window does not send a message and does not start the bot."),
            ];
        }

        function openTestDialog() {
            if (!dialogs || typeof dialogs.openCustomerBotTest !== "function") return;
            if (testDialog && typeof testDialog.show === "function") {
                testDialog.show();
                return;
            }
            testDialog = dialogs.openCustomerBotTest({
                title: t("Test the bot"),
                steps: testSteps(),
                closeLabel: t("Close"),
            }) || null;
        }

        function releaseTestDialog() {
            if (testDialog && typeof testDialog.hide === "function") testDialog.hide();
            testDialog = null;
        }

        function focusTab(id) {
            const button = root().find("[data-bot-tab]").filter(function matchTab() {
                return this.getAttribute("data-bot-tab") === id;
            }).get(0);
            if (button && typeof button.focus === "function") button.focus();
        }

        $body.on(`click${EVENT_NAMESPACE}`, "[data-bot-save]", () => {
            mutate(
                (revision, texts) => api.saveCustomerBotDraft(revision, texts, { freeze: false }),
                () => t("Draft saved."),
                true
            );
        });
        $body.on(`click${EVENT_NAMESPACE}`, "[data-bot-publish]", () => {
            mutate(
                (revision, texts) => api.publishCustomerBotTexts(revision, texts, { freeze: false }),
                () => t("Texts published. The bot stays in its current on or off state."),
                true
            );
        });
        $body.on(`click${EVENT_NAMESPACE}`, "[data-bot-start]", () => runOperation("start"));
        $body.on(`click${EVENT_NAMESPACE}`, "[data-bot-stop]", () => runOperation("stop"));
        $body.on(`click${EVENT_NAMESPACE}`, "[data-bot-check]", () => runOperation("check"));
        $body.on(`click${EVENT_NAMESPACE}`, "[data-bot-test]", () => {
            openTestDialog();
        });
        $body.on(`click${EVENT_NAMESPACE}`, "[data-bot-details-toggle]", () => {
            detailsOpen = !detailsOpen;
            renderOperation();
        });
        $body.on(`click${EVENT_NAMESPACE}`, "[data-bot-technical]", () => {
            technicalOpen = !technicalOpen;
            renderOperation();
        });
        $body.on(`click${EVENT_NAMESPACE}`, "[data-bot-tab]", function onTab() {
            const next = this.getAttribute("data-bot-tab");
            if (TEXT_TABS.indexOf(next) < 0 || !readPermissions().canEditTexts) return;
            activeTab = next;
            applyChrome();
        });
        $body.on(`keydown${EVENT_NAMESPACE}`, "[data-bot-tab]", function onTabKey(event) {
            if (!readPermissions().canEditTexts) return;
            if (["ArrowRight", "ArrowLeft", "Home", "End"].indexOf(event.key) < 0) return;
            const host = root().get(0);
            const rtl = Boolean(
                host
                && typeof getComputedStyle === "function"
                && getComputedStyle(host).direction === "rtl"
            );
            const forward = rtl ? "ArrowLeft" : "ArrowRight";
            let index = TEXT_TABS.indexOf(activeTab);
            if (event.key === "Home") index = 0;
            else if (event.key === "End") index = TEXT_TABS.length - 1;
            else if (event.key === forward) index = (index + 1) % TEXT_TABS.length;
            else index = (index - 1 + TEXT_TABS.length) % TEXT_TABS.length;
            event.preventDefault();
            activeTab = TEXT_TABS[index];
            applyChrome();
            focusTab(activeTab);
        });
        $body.on(`click${EVENT_NAMESPACE}`, "[data-bot-group-button]", function onGroup() {
            const next = this.getAttribute("data-bot-group-button");
            if (!next) return;
            activeGroup = next;
            applyChrome();
        });
        $body.on(`input${EVENT_NAMESPACE}`, "[data-bot-search]", function onSearch() {
            searchQuery = String(this.value || "");
            applyChrome();
        });
        $body.on(`input${EVENT_NAMESPACE}`, "[data-bot-field]", function onField() {
            const key = this.getAttribute("data-bot-field");
            if (working && key) working[key] = this.value;
            localEpoch += 1;
            rememberFocus(this);
            updateCount(this);
            updateBanners();
        });
        $body.on(`focusin${EVENT_NAMESPACE}`, "[data-bot-field]", function onFieldFocus() {
            rememberFocus(this);
        });
        $body.on(`click${EVENT_NAMESPACE}`, "[data-bot-preview-send]", sendPreview);
        $body.on(`click${EVENT_NAMESPACE}`, "[data-bot-restart]", restartPreview);
        $body.on(`change${EVENT_NAMESPACE}`, "[data-bot-scenario]", function onScenario() {
            scenarioId = this.value;
            const row = text.scenarios.find(item => item[0] === scenarioId);
            root().find("[data-bot-hint]").text(row ? row[2] : "");
            restartPreview();
        });
        $body.on(`change${EVENT_NAMESPACE}`, "input[name='aps-bot-source']", function onSource() {
            previewSource = this.value === "published" ? "published" : "draft";
            applyChrome();
            restartPreview();
        });
        $body.on(`keydown${EVENT_NAMESPACE}`, "[data-bot-preview-input]", function onPreviewKey(event) {
            if (event.key === "Enter") {
                event.preventDefault();
                sendPreview();
            }
        });
        lifecycle.track(() => {
            releaseOperation();
            $body.off(EVENT_NAMESPACE);
        }, "customer-bot-settings-panel");

        return Object.freeze({
            refresh: load,
            deactivate() {
                releaseOperation();
                releaseTestDialog();
            },
            dispose() {
                releaseOperation();
                releaseTestDialog();
                $body.off(EVENT_NAMESPACE);
            },
        });
    }

    window.AlmdinaFactoryProductionSettingsCustomerBot = Object.freeze({
        attach,
        groupOrder: GROUP_ORDER.map(([id, keys]) => ({ id, keys: keys.slice() })),
        groupIdFor,
        shortStamp,
        fieldKeys() {
            return Object.keys(catalog(message => message).fields);
        },
        ACTIVATING_POLL_MS,
        STEADY_POLL_MS,
    });
})();
