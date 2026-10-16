"""Evidence collection on an ephemeral, version-pinned Frappe Desk site."""

import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qs
import pytest


def browser_playwright():
    # The general Frappe integration job discovers this module without the
    # browser extra installed; the pinned Desk job supplies Playwright.
    from playwright.sync_api import sync_playwright
    return sync_playwright()


def _login(page, fixture):
    page.goto(os.environ["FRAPPE_DESK_URL"] + "/login", wait_until="domcontentloaded")
    page.locator("#login_email").fill(fixture["user"])
    page.locator("#login_password").fill(fixture["password"])
    page.locator(".btn-login").click()
    page.wait_for_function("user => !!frappe?.set_route && frappe.session?.user === user",
                           arg=fixture["user"], timeout=60000)
    page.wait_for_function("!!frappe.boot?.user?.can_read && !!frappe.router?.routes && !!frappe.app",
                           timeout=45000)


def test_desk_route_preflight():
    fixture = json.loads(Path(os.environ["P0_FIXTURE_PATH"]).read_text())
    evidence_dir = Path(os.environ["P0_EVIDENCE_DIR"])
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence = {"server": fixture["route_preflight"], "versions": fixture["versions"]}
    with browser_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(locale="en-US")
            _login(page, fixture)
            evidence["boot"] = page.evaluate("""() => ({
                user:frappe.session.user, setupComplete:frappe.boot.setup_complete,
                canReadDco:frappe.boot.user.can_read.includes('Door Cutting Order'),
                canReadCustomer:frappe.boot.user.can_read.includes('Customer'),
                routeDco:frappe.router.routes['door-cutting-order'] || null,
                routeCustomer:frappe.router.routes.customer || null,
                routeCount:Object.keys(frappe.router.routes).length
            })""")
            assert evidence["boot"]["canReadDco"] and evidence["boot"]["routeDco"], evidence
            assert evidence["boot"]["canReadCustomer"] and evidence["boot"]["routeCustomer"], evidence
            for doctype, name in (("Customer", fixture["customer"]),
                                  ("Door Cutting Order", fixture["orders"]["A"]["name"])):
                page.evaluate("args => frappe.set_route('Form', args[0], args[1])", [doctype, name])
                try:
                    page.wait_for_function("args => cur_frm?.doctype === args[0] && cur_frm?.doc?.name === args[1]",
                                           arg=[doctype, name], timeout=45000)
                    evidence[doctype] = page.evaluate("""() => ({href:location.href,
                        route:frappe.get_route(),frmName:cur_frm.doc.name,
                        frmDoctype:cur_frm.doctype})""")
                except Exception:
                    evidence[doctype] = page.evaluate("""() => ({href:location.href,
                        route:frappe.get_route(),frmName:cur_frm?.doc?.name || null,
                        body:document.body.innerText.slice(-1200)})""")
                    raise AssertionError(f"Frappe Form route unavailable: {doctype}: {evidence[doctype]}")
        finally:
            (evidence_dir / "route-preflight.json").write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
            browser.close()


def test_phase2a_isolated_desk_boundary():
    """A controlled stale workspace may not modify B or its native save."""
    fixture = json.loads(Path(os.environ["P0_FIXTURE_PATH"]).read_text())
    evidence_dir = Path(os.environ["P0_EVIDENCE_DIR"])
    a, b = fixture["orders"]["A"], fixture["orders"]["B"]
    evidence = {"kind": "controlled stale snapshot, not natural reproduction"}
    with browser_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(locale="en-US")
            _login(page, fixture)
            for order in (a, b):
                page.evaluate("name => { frappe.set_route('Form','Door Cutting Order',name); }",
                              order["name"])
                page.wait_for_function("name => cur_frm?.doc?.name === name",
                                       arg=order["name"], timeout=45000)
                if order is a:
                    evidence["a_token"] = page.evaluate("AlmdinaDocumentContext.capture(cur_frm)")
                    page.evaluate("""() => cur_frm.fields_dict.board_description.$input
                        .val(cur_frm.doc.board_description).trigger('input')""")
            evidence["before"] = page.evaluate("""() => ({name:cur_frm.doc.name,
                board:cur_frm.doc.board_description,
                customer:cur_frm.doc.customer,
                piece:cur_frm.doc.pieces[0].name,
                width:cur_frm.doc.pieces[0].width_cm,
                boardRate:cur_frm.doc.board_rate_usd})""")
            page.evaluate("""async () => {
                await AlmdinaDcoWorkspaceAssetRegistry.ensure('cost');
                await AlmdinaDcoWorkspaceAssetRegistry.ensure('plan');
            }""")
            evidence["projection"] = page.evaluate("""args => {
                const frm=cur_frm, identity=args.token.identity;
                const cost=AlmdinaCostWorkspaceState.storeFor(frm);
                cost.reset(identity);
                cost.resolveLoad(identity,cost.beginLoad(identity),{
                    order_name:args.a.name,
                    order:{customer:'Stale A Customer',board_description:args.a.board,
                        board_length_cm:111,board_rate_usd:987},
                    pieces:[{name:args.a.piece_name,width_cm:11,qty:77}]
                });
                const plan=AlmdinaPlanWorkspaceState.storeFor(frm);
                plan.reset(identity);
                plan.resolveLoad(identity,plan.beginLoad(identity),{
                    order_name:args.a.name,plans:{system_draft:{name:'STALE-A',
                        snapshot_json:JSON.stringify({sheets:[{sheet_no:'A'}]})}}
                });
                return {costAccepted:AlmdinaCostWorkspacePresenterAdapter.project(frm),
                    planAccepted:AlmdinaPlanWorkspacePresenterAdapter.project(frm),
                    costState:AlmdinaCostWorkspaceState.snapshot(frm),
                    planState:AlmdinaPlanWorkspaceState.snapshot(frm),
                    name:frm.doc.name,board:frm.doc.board_description,
                    customer:frm.doc.customer,boardRate:frm.doc.board_rate_usd,
                    width:frm.doc.pieces[0].width_cm,
                    piece:frm.doc.pieces[0].name,planJson:frm.doc.cutting_plan_json??null};
            }""", {"token": evidence["a_token"], "a": a})
            assert not evidence["projection"]["costAccepted"]
            assert not evidence["projection"]["planAccepted"]
            assert evidence["projection"]["board"] == b["board"]
            assert evidence["projection"]["customer"] == evidence["before"]["customer"]
            assert evidence["projection"]["boardRate"] == evidence["before"]["boardRate"]
            assert evidence["projection"]["width"] == b["width_cm"]
            assert evidence["projection"]["piece"] != a["piece_name"]
            assert evidence["projection"]["planJson"] is None
            page.evaluate("""() => {
                AlmdinaCostWorkspaceState.reset(cur_frm);
                AlmdinaPlanWorkspaceState.reset(cur_frm);
            }""")
            # A controlled stale DOM value with no B-owned input event must not
            # enter Frappe's native savedocs payload. This is an injection probe.
            evidence["stale_dom_probe"] = page.evaluate("""value => {
                const input=cur_frm.fields_dict.board_description.$input;
                input.val(value);
                return {control:input.val(),model:cur_frm.doc.board_description};
            }""", a["board"])
            assert evidence["stale_dom_probe"]["control"] == a["board"]
            assert evidence["stale_dom_probe"]["model"] == b["board"]
            payloads = []

            def capture(request):
                if "savedocs" not in request.url:
                    return
                raw = request.post_data or ""
                values = json.loads(raw) if raw.startswith("{") else {
                    key: entries[0] for key, entries in parse_qs(raw).items()
                }
                doc = values.get("doc")
                payloads.append(json.loads(doc) if isinstance(doc, str) else doc)

            page.on("request", capture)
            try:
                evidence["native_save"] = page.evaluate("""async () => {
                    cur_frm.dirty(); await cur_frm.save();
                    return {name:cur_frm.doc.name,board:cur_frm.doc.board_description};
                }""")
            finally:
                page.remove_listener("request", capture)
            evidence["savedocs"] = [{"name": doc["name"],
                "board": doc.get("board_description"),
                "piece_names": [row["name"] for row in doc.get("pieces", [])]}
                for doc in payloads]
            assert evidence["savedocs"] and all(
                doc["name"] == b["name"] and doc["board"] == b["board"]
                and a["piece_name"] not in doc["piece_names"]
                for doc in evidence["savedocs"]), evidence
            evidence["server_read"] = page.evaluate("""async name => {
                const response=await frappe.call({method:'frappe.client.get',
                    args:{doctype:'Door Cutting Order',name}});
                return {name:response.message.name,
                    board:response.message.board_description};
            }""", b["name"])
            assert evidence["server_read"] == {"name": b["name"], "board": b["board"]}
            edited_board = b["board"] + " — current visit edit"
            page.on("request", capture)
            try:
                evidence["legitimate_b_edit"] = page.evaluate("""async value => {
                    const frm=cur_frm;
                    frm.fields_dict.board_description.$input.val(value).trigger('input');
                    frm.dirty();
                    await frm.save();
                    const response=await frappe.call({method:'frappe.client.get',
                        args:{doctype:'Door Cutting Order',name:frm.doc.name}});
                    return {model:frm.doc.board_description,
                        server:response.message.board_description};
                }""", edited_board)
            finally:
                page.remove_listener("request", capture)
            assert evidence["legitimate_b_edit"] == {
                "model": edited_board, "server": edited_board}, evidence
            evidence["legitimate_b_savedocs"] = [doc.get("board_description")
                for doc in payloads if doc and doc.get("board_description") == edited_board]
            assert evidence["legitimate_b_savedocs"] == [edited_board], evidence
            evidence["restored_b"] = page.evaluate("""async value => {
                cur_frm.fields_dict.board_description.$input.val(value).trigger('input');
                cur_frm.dirty(); await cur_frm.save();
                const response=await frappe.call({method:'frappe.client.get',
                    args:{doctype:'Door Cutting Order',name:cur_frm.doc.name}});
                return response.message.board_description;
            }""", b["board"])
            assert evidence["restored_b"] == b["board"]
        finally:
            evidence_dir.mkdir(parents=True, exist_ok=True)
            (evidence_dir / "phase2a-runtime-isolation.json").write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            browser.close()


def test_cross_order_desk_runtime():
    fixture = json.loads(Path(os.environ["P0_FIXTURE_PATH"]).read_text())
    evidence_dir = Path(os.environ["P0_EVIDENCE_DIR"])
    evidence_dir.mkdir(parents=True, exist_ok=True)
    a, b = fixture["orders"]["A"], fixture["orders"]["B"]
    evidence = {"versions": fixture["versions"], "orders": fixture["orders"], "stages": {}}
    page = None
    diagnostics = []

    def stage(name, callback):
        try:
            evidence["stages"][name] = {"status": "OBSERVED", "value": callback()}
        except Exception as exc:
            evidence["stages"][name] = {"status": "NOT_TESTED", "reason": repr(exc)}

    with browser_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(locale="en-US", accept_downloads=False)
            page = context.new_page()
            evidence["browser_locale"] = page.evaluate("""() => ({language:navigator.language,
                parsed:new Intl.Locale(navigator.language).language})""")
            page.on("pageerror", lambda error: diagnostics.append({"kind": "pageerror", "message": str(error)[:500]}))
            page.on("console", lambda message: diagnostics.append({"kind": "console", "message": message.text[:500]})
                    if message.type == "error" else None)
            page.on("response", lambda response: diagnostics.append({"kind": "http", "url": response.url.split("?")[0],
                    "status": response.status}) if response.status >= 400 else None)
            _login(page, fixture)

            def route(name):
                page.evaluate("name => { frappe.set_route('Form', 'Door Cutting Order', name); }", name)
                try:
                    page.wait_for_function("name => window.cur_frm?.doc?.name === name", arg=name, timeout=45000)
                except Exception:
                    snapshot = page.evaluate("""() => ({href:location.href,
                        route:frappe.get_route?.(),curName:window.cur_frm?.doc?.name,
                        doctype:window.cur_frm?.doctype,bootReady:!!frappe.boot?.sysdefaults?.setup_complete,
                        visibleText:document.body.innerText.slice(-1200)})""")
                    evidence["route_failure"] = {"requested": name,
                                                 "snapshot": snapshot, "diagnostics": diagnostics[-30:]}
                    print("P0_ROUTE_DIAGNOSTIC=" + json.dumps(evidence["route_failure"], ensure_ascii=False), flush=True)
                    raise
                page.wait_for_function("!!window.AlmdinaCostWorkspaceState && !!window.AlmdinaPlanWorkspaceState",
                                       timeout=45000)
                return page.evaluate("""() => ({
                    name: cur_frm.doc.name,
                    board: cur_frm.doc.board_description,
                    pieces: cur_frm.doc.pieces.map(p => ({name:p.name,width_cm:p.width_cm,length_cm:p.length_cm})),
                    input: cur_frm.fields_dict.board_description?.$input?.val() ?? null,
                    cost: AlmdinaCostWorkspaceState.snapshot(cur_frm),
                    plan: AlmdinaPlanWorkspaceState.snapshot(cur_frm)
                })""")

            state_a = route(a["name"])
            a_identity = page.evaluate("""() => {
                window.__p0FrmA = cur_frm;
                window.__p0DocA = cur_frm.doc;
                const context = AlmdinaDocumentContext;
                const capture = context.capture(cur_frm);
                window.__p0Events = [];
                for (const event of ['before_load','onload','refresh']) {
                    frappe.ui.form.on('Door Cutting Order', {[event]: frm => {
                        window.__p0Events.push({event, name:frm.doc.name,
                            sameFrm:frm === window.__p0FrmA,
                            modified:frm.doc.modified,
                            costStatus:window.AlmdinaCostWorkspaceState?.snapshot(frm)?.status,
                            planStatus:window.AlmdinaPlanWorkspaceState?.snapshot(frm)?.status});
                    }});
                }
                return {name:cur_frm.doc.name, formIdentity:context.formIdentity(cur_frm),
                    generation:capture?.generation ?? null, modified:cur_frm.doc.modified,
                    planName:cur_frm.doc.system_plan || null,
                    planRevision:cur_frm.doc.system_plan_revision || null};
            }""")
            state_b = route(b["name"])
            evidence["stages"]["lifecycle"] = {"status": "OBSERVED", "value": {
                "a": state_a, "a_identity_before_navigation": a_identity, "b": state_b,
                "transition": page.evaluate("""() => ({sameFrm:cur_frm===window.__p0FrmA,
                    sameDoc:cur_frm.doc===window.__p0DocA,
                    events:window.__p0Events,
                    aCostReadOnB:AlmdinaCostWorkspaceState.snapshot(cur_frm)?.data?.order?.board_description,
                    model:cur_frm.doc.board_description,
                    input:cur_frm.fields_dict.board_description?.$input?.val() ?? null})""")}}

            # Production loads action/presenter assets when their tabs activate.
            # The order tab alone never loads the cutting renderer.
            evidence["stages"]["workspace_activation"] = {"status": "OBSERVED", "value":
                page.evaluate("""async () => ({cost:await AlmdinaDcoWorkspaceAssetRegistry.ensure('cost'),
                    plan:await AlmdinaDcoWorkspaceAssetRegistry.ensure('plan'),
                    presenter:!!window.AlmdinaCostWorkspacePresenterAdapter,
                    renderer:!!window.AlmdinaCuttingPlanRender})""")}

            def save_probe():
                # A real A-shaped workspace snapshot, projected through the production
                # presenter on B. Record this as controlled injection, not natural navigation.
                projected = page.evaluate("""args => {
                    const frm = cur_frm, owner = AlmdinaCostWorkspaceState;
                    const original = {board:frm.doc.board_description,
                        width:frm.doc.pieces[0].width_cm};
                    const store = owner.storeFor(frm);
                    const identity = args.identity.formIdentity;
                    store.reset(identity);
                    const requestId = store.beginLoad(identity);
                    store.resolveLoad(identity,requestId,{order_name:args.a.name,
                        order:{board_description:args.a.board},
                        pieces:[{name:args.a.piece_name,width_cm:args.a.width_cm}]});
                    const accepted = AlmdinaCostWorkspacePresenterAdapter.project(frm);
                    return {original, accepted, model:frm.doc.board_description,
                        width:frm.doc.pieces[0].width_cm,
                        input:frm.fields_dict.board_description?.$input?.val() ?? null,
                        state:owner.snapshot(frm)?.identity};
                }""", {"a": a, "identity": a_identity})
                payloads = []

                def capture(request):
                    if "savedocs" in request.url:
                        raw = request.post_data or ""
                        try:
                            values = json.loads(raw) if raw.startswith("{") else {
                                key: entries[0] for key, entries in parse_qs(raw).items()
                            }
                            doc = values.get("doc")
                            doc = json.loads(doc) if isinstance(doc, str) else doc
                            parsed = {"action": values.get("action"),
                                      "name": doc.get("name"),
                                      "board": doc.get("board_description"),
                                      "pieces": [{"name": row.get("name"),
                                                  "width_cm": row.get("width_cm")}
                                                 for row in doc.get("pieces", [])]}
                        except (ValueError, AttributeError, TypeError) as exc:
                            parsed = {"parse_error": repr(exc)}
                        payloads.append({"url": request.url, "body": raw, "parsed": parsed})

                page.on("request", capture)
                try:
                    save_result = page.evaluate("""async () => {
                        cur_frm.dirty();
                        try { await cur_frm.save(); return {ok:true,board:cur_frm.doc.board_description}; }
                        catch(error) { return {ok:false,error:String(error),board:cur_frm.doc.board_description}; }
                    }""")
                finally:
                    page.remove_listener("request", capture)
                # A separate bench process will read the database after this browser exits.
                db = page.evaluate("""async name => {
                    const response = await frappe.call({method:'frappe.client.get',
                        args:{doctype:'Door Cutting Order',name}});
                    return {name:response.message.name,
                        board:response.message.board_description,
                        pieces:response.message.pieces.map(p=>({name:p.name,width_cm:p.width_cm}))};
                }""", b["name"])
                return {"method": "controlled A cost store projected on B via production presenter",
                        "projected": projected, "save": save_result,
                        "native_savedocs_requests": payloads, "frappe_client_get": db,
                        "classification_at_browser": (
                            "PAYLOAD" if any(row["parsed"].get("name") == b["name"]
                                             and row["parsed"].get("board") == a["board"]
                                             for row in payloads)
                            else "MODEL" if projected["model"] == a["board"]
                            else "UI_ONLY" if projected["input"] == a["board"]
                            else "NOT_REPRODUCED")}

            stage("save", save_probe)
            # Frappe navigation makes a fresh B visit without reloading the browser.
            route(a["name"])
            state_b_print = route(b["name"])

            def print_probe():
                page.evaluate("args => {window.__p0Args=args}", {"a": a})
                # Controlled A geometry presented to B must fail *before* a
                # print window or async factory identity lookup is started.
                page.evaluate("""() => {
                    window.__p0PrintWrites=[];
                    window.__p0OldOpen=window.open;
                    window.open=()=>({document:{open(){},write(html){window.__p0PrintWrites.push(html)},close(){}},close(){}});
                    const a=window.__p0Args.a;
                    const plan={name:'P0-PLAN-A',revision:'P0-REV-A',
                        full_board_width_cm:122,full_board_length_cm:244,
                        usable_board_width_cm:122,usable_board_length_cm:244,
                        sheets:[{sheet_no:1,pieces:[{x:0,y:0,w:a.width_cm,h:a.length_cm,
                            original_w:a.width_cm,original_h:a.length_cm,
                            label:'P0-A-GEOMETRY',piece_type:'Regular',rotated:false}]}]};
                    window.__p0PrintStart={name:cur_frm.doc.name,
                        identity:AlmdinaDocumentContext.formIdentity(cur_frm),
                        modified:cur_frm.doc.modified};
                    window.__p0PrintResult=AlmdinaCuttingPlanRender.print(cur_frm,plan);
                }""")
                result = page.evaluate("""async () => await window.__p0PrintResult""")
                writes = page.evaluate("window.__p0PrintWrites")
                assert result is False and writes == [], (result, writes)
                return {"method": "controlled A geometry rejected while B is current",
                        "source": page.evaluate("window.__p0PrintStart"),
                        "b_before_print": state_b_print, "result": result,
                        "window_writes": writes, "classification": "REJECTED_WRONG_PLAN"}

            stage("print", print_probe)
            stage("recovery", lambda: page.evaluate("""() => ({
                available:!!window.AlmdinaDcoRecovery,
                api:window.AlmdinaDcoRecovery?Object.keys(window.AlmdinaDcoRecovery):[],
                currentName:cur_frm?.doc?.name,
                isNew:!!cur_frm?.is_new?.()
            })"""))
            page.screenshot(path=str(evidence_dir / "desk.png"), full_page=True)
        finally:
            evidence["diagnostics"] = diagnostics[-30:]
            if page:
                try:
                    page.screenshot(path=str(evidence_dir / "last-desk.png"), full_page=True)
                except Exception:
                    pass
            (evidence_dir / "runtime-evidence.json").write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
            browser.close()
    assert all(evidence["stages"].get(gate, {}).get("status") == "OBSERVED"
               for gate in ("lifecycle", "save", "print")), evidence


def test_saved_server_plan_print_runtime():
    """Final HTML uses one persisted plan and cancels on a route change."""
    fixture = json.loads(Path(os.environ["P0_FIXTURE_PATH"]).read_text())
    evidence_dir = Path(os.environ["P0_EVIDENCE_DIR"])
    saved_plan = json.loads((evidence_dir / "saved-plan-fixture.json").read_text())
    a, b = fixture["orders"]["A"], fixture["orders"]["B"]
    evidence = {"saved_plan": saved_plan, "orders": fixture["orders"]}
    with browser_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(locale="en-US")
            _login(page, fixture)
            evidence["browser_errors"] = []
            page.on("console", lambda message: evidence["browser_errors"].append(message.text)
                    if message.type == "error" else None)
            evidence["factory_identity"] = page.evaluate("""async () => {
                await frappe.require('/assets/almdina_erp/js/door_cutting_order/printing/door_cutting_order_print_identity.js');
                if (!window.AlmdinaFactoryPrintIdentity?.get)
                    throw new Error('Production factory print identity asset unavailable');
                return await AlmdinaFactoryPrintIdentity.get();
            }""")
            page.evaluate("""() => {
                window.__p0PrintWrites=[];
                window.open=()=>({document:{open(){},write(html){__p0PrintWrites.push(html)},close(){}},close(){}});
            }""")
            # Two bounded visits to each saved order exercise a fresh document
            # generation without retrying a failed print in the same visit.
            for visit, (label, order, other) in enumerate(
                    (("A", a, b), ("B", b, a), ("A", a, b), ("B", b, a)), 1):
                page.evaluate("name => frappe.set_route('Form','Door Cutting Order',name)", order["name"])
                page.wait_for_function("name => cur_frm?.doc?.name === name", arg=order["name"], timeout=45000)
                page.evaluate("""name => {
                    window.__p0ReadyEvent = null;
                    window.__p0ReadyFor = name;
                    if (!window.__p0ReadyListener) {
                        window.__p0ReadyListener = event => {
                            const detail = event.detail || {};
                            if (detail.orderName === window.__p0ReadyFor
                                && detail.snapshot?.status === 'ready')
                                window.__p0ReadyEvent = {order:detail.orderName,
                                    identity:detail.identity, status:detail.snapshot.status};
                        };
                        window.addEventListener('almdina:plan-workspace-updated', window.__p0ReadyListener);
                    }
                }""", order["name"])
                page.get_by_text("Cutting Plan", exact=True).first.click()
                if visit <= 2:
                    # Operator path: the real workspace event paints the action.
                    # A missing button is a distinct lifecycle/permission failure.
                    page.wait_for_function("""name => window.__p0ReadyEvent?.order === name
                        || (window.AlmdinaPlanWorkspaceState?.snapshot?.(cur_frm)?.status === 'ready'
                            && cur_frm?.doc?.name === name)""", arg=order["name"], timeout=45000)
                    button = page.locator('.dco-plan-context-actions-host .dco-print-cutting-plan:visible')
                    try:
                        button.wait_for(state="visible", timeout=15000)
                        assert button.is_enabled(), "Print action disabled despite ready Plan"
                    except Exception:
                        evidence.setdefault("operator_failures", {})[label] = page.evaluate("""() => ({
                            event:window.__p0ReadyEvent,tab:AlmdinaPlanTabsUX?.activeTab(cur_frm),
                            state:AlmdinaPlanWorkspaceState?.snapshot(cur_frm)?.status,
                            row:AlmdinaPlanWorkspaceState?.displayedPlanForTab(cur_frm,'System')?.name,
                            buttons:document.querySelectorAll('.dco-print-cutting-plan').length})""")
                        raise
                    action_source = page.evaluate("""() => ({
                        decorated:!!AlmdinaCuttingPlanRender?.__almadina179SourcePresentation,
                        visiblePlanRoot:!!cur_frm.fields_dict.cutting_plan_html.$wrapper
                            .get(0)?.querySelector('.dco-cutting-plan'),
                        selectedTab:AlmdinaPlanTabsUX.activeTab(cur_frm),
                        row:AlmdinaPlanWorkspaceState.displayedPlanForTab(cur_frm,'System')?.name
                    })""")
                    if not action_source["visiblePlanRoot"]:
                        try:
                            page.wait_for_function("""() => !!cur_frm?.fields_dict?.cutting_plan_html
                                ?.$wrapper?.get(0)?.querySelector('.dco-cutting-plan')""",
                                timeout=10000)
                            action_source["visiblePlanRoot"] = True
                        except Exception:
                            evidence.setdefault("paint_failure", {})[label] = page.evaluate("""() => ({
                                event:window.__p0ReadyEvent, tab:AlmdinaPlanTabsUX.activeTab(cur_frm),
                                identity:AlmdinaDocumentContext.formIdentity(cur_frm),
                                snapshotStatus:AlmdinaPlanWorkspaceState.snapshot(cur_frm)?.status,
                                freshness:AlmdinaPlanWorkspaceState.snapshot(cur_frm)?.freshness,
                                stateOrder:AlmdinaPlanWorkspaceState.snapshot(cur_frm)?.data?.order_name,
                                canonicalRow:AlmdinaPlanWorkspaceState.planForTab(cur_frm,'System')?.name,
                                displayedRow:AlmdinaPlanWorkspaceState.displayedPlanForTab(cur_frm,'System')?.name,
                                presenterReady:AlmdinaPlanWorkspacePresenterAdapter.ready(cur_frm),
                                planSurface:cur_frm.fields_dict.cutting_plan_html.$wrapper.get(0)
                                    ?.innerText.slice(-500)})""")
                    assert action_source["decorated"] and action_source["visiblePlanRoot"], action_source
                    before_click = page.evaluate('__p0PrintWrites.length')
                    button.click()
                    page.wait_for_function("count => window.__p0PrintWrites.length >= count + 2",
                                           arg=before_click, timeout=15000)
                    operator_html = page.evaluate('__p0PrintWrites.at(-1)')
                    assert order["name"] in operator_html and other["name"] not in operator_html
                    assert order["board"] in operator_html and saved_plan[label]["name"] in operator_html
                    evidence.setdefault("operator_clicks", {})[label] = {
                        "ready_event": page.evaluate('window.__p0ReadyEvent'),
                        "source": action_source,
                        "final_html": f"saved-plan-{label}-operator-final.html"}
                    (evidence_dir / f"saved-plan-{label}-operator-final.html").write_text(
                        operator_html, encoding="utf-8")
                    # Direct handler on the same ready visit, in a separate
                    # Playwright evaluation, to compare with the real click.
                    result = page.evaluate("""async () => {
                        const result=await AlmdinaPlanTabsUX.printActivePlan(cur_frm);
                        const row=AlmdinaPlanWorkspaceState.displayedPlanForTab(cur_frm,'System');
                        return {result,order:cur_frm.doc.name,row:row?.name,
                            writes:__p0PrintWrites.length,
                            revision:row?.revision,html:__p0PrintWrites.at(-1)};
                    }""")
                else:
                    # Same JS operation, while retaining the real async load
                    # and factory identity boundaries inside that operation.
                    result = page.evaluate("""async () => {
                    await AlmdinaDcoWorkspaceAssetRegistry.ensure('plan');
                    await AlmdinaPlanWorkspaceState.load(cur_frm,{force:true});
                    if (!AlmdinaPlanWorkspacePresenterAdapter.project(cur_frm))
                        throw new Error('Ready Plan projection unavailable');
                    const result=await AlmdinaPlanTabsUX.printActivePlan(cur_frm);
                    const row=AlmdinaPlanWorkspaceState.displayedPlanForTab(cur_frm,'System');
                    return {result,order:cur_frm.doc.name,row:row?.name,
                        writes:__p0PrintWrites.length,
                        revision:row?.revision,html:__p0PrintWrites.at(-1)};
                    }""")
                evidence.setdefault("attempts", {})[f"{label}-{visit}"] = {
                    key: value for key, value in result.items() if key != "html"}
                assert result["result"] is True and result["row"] == saved_plan[label]["name"], result
                html = result.pop("html")
                assert order["name"] in html and other["name"] not in html, result
                assert order["board"] in html and other["board"] not in html, result
                assert saved_plan[label]["name"] in html and str(saved_plan[label]["revision"]) in html
                assert 'class="dco-unified-print-header"' in html
                assert f"<title>Cutting plan - {order['name']}</title>" in html
                assert evidence["factory_identity"]["print_factory_name"] in html
                piece = saved_plan[label]["first_piece"]
                geometry = f"{int(float(piece['w']) * 10)} × {int(float(piece['h']) * 10)}"
                assert geometry in html, (label, geometry)
                (evidence_dir / f"saved-plan-{label}-final.html").write_text(html, encoding="utf-8")
                evidence[label] = {**result, "geometry": geometry,
                                   "html_file": f"saved-plan-{label}-final.html"}
                if label == "A":
                    a_plan = page.evaluate("""() => JSON.parse(
                        AlmdinaPlanWorkspaceState.planForTab(cur_frm,'System').snapshot_json)""")
            # The real saved A geometry cannot be passed to B's print command.
            writes_before = page.evaluate("__p0PrintWrites.length")
            rejected = page.evaluate("""async plan =>
                await AlmdinaCuttingPlanRender.print(cur_frm,plan)""", a_plan)
            assert rejected is False and page.evaluate("__p0PrintWrites.length") == writes_before
            evidence["wrong_plan_rejected"] = True
            # Separate controlled renderer case: retain B ownership but add an
            # OFFCUT sheet and Extra flag. This does not pretend to be a saved
            # server plan; the A/B HTML checks above use persisted API rows.
            controlled = page.evaluate("""async () => {
                const frm=cur_frm, state=AlmdinaPlanWorkspaceState;
                const payload=state.snapshot(frm).data;
                const row=payload.plans.system_draft;
                const geometry=JSON.parse(row.snapshot_json);
                const offcut=JSON.parse(JSON.stringify(geometry.sheets[0]));
                offcut.sheet_no=geometry.sheets.length+1;
                offcut.resource_kind='OFFCUT';
                offcut.pieces[0].id='CONTROLLED-OFFCUT-B';
                offcut.pieces[0].label='CONTROLLED-OFFCUT-B';
                offcut.pieces[0].piece_instance_id='CONTROLLED-OFFCUT-PIECE-B';
                offcut.pieces[0].source_piece_no=1;
                offcut.pieces[0].extra_double=1;
                geometry.sheets.push(offcut);
                const assignments=[{piece_instance_id:'CONTROLLED-OFFCUT-PIECE-B',
                    business_state:'FACTORY_FACTORY',business_state_label:'P0 FACTORY ASSIGNED'}];
                const testRow={...row,name:'CONTROLLED-PLAN-B',revision:Number(row.revision)+1,
                    snapshot_json:JSON.stringify(geometry),offcut:{assignments}};
                const id=AlmdinaDocumentContext.formIdentity(frm),store=state.storeFor(frm);
                store.reset(id);
                store.resolveLoad(id,store.beginLoad(id),{
                    ...payload,plans:{...payload.plans,system_draft:testRow}});
                const originalExtra=frm.doc.pieces[0].extra_double;
                frm.doc.pieces[0].extra_double=1;
                const before=__p0PrintWrites.length;
                const result=await AlmdinaCuttingPlanRender.print(frm,geometry,{tab:'System',row:testRow});
                frm.doc.pieces[0].extra_double=originalExtra;
                return {result,html:__p0PrintWrites.at(-1),before,
                    after:__p0PrintWrites.length};
            }""")
            assert controlled["result"] is True and controlled["after"] == controlled["before"] + 2
            controlled_html = controlled.pop("html")
            assert b["name"] in controlled_html and a["name"] not in controlled_html
            assert "CONTROLLED-PLAN-B" in controlled_html
            assert 'data-resource-kind="OFFCUT"' in controlled_html
            assert "CONTROLLED-OFFCUT-B" in controlled_html
            assert 'dco-offcut-business-context' in controlled_html
            assert 'P0 FACTORY ASSIGNED' in controlled_html
            assert 'data-addon-kind="double"' in controlled_html
            (evidence_dir / "controlled-multisheet-offcut-final.html").write_text(
                controlled_html, encoding="utf-8")
            evidence["controlled_multisheet_offcut"] = controlled
            writes_before = page.evaluate("__p0PrintWrites.length")
            # Freeze B, then navigate while the production print handler awaits
            # the asynchronous identity service. No final HTML may be issued.
            page.evaluate("""async () => {
                AlmdinaPlanWorkspaceState.reset(cur_frm);
                await AlmdinaPlanWorkspaceState.load(cur_frm,{force:true});
                AlmdinaPlanWorkspacePresenterAdapter.project(cur_frm);
                window.AlmdinaFactoryPrintIdentity={...window.AlmdinaFactoryPrintIdentity,
                    get:()=>new Promise(resolve=>__p0ResolveIdentity=resolve)};
                const row=AlmdinaPlanWorkspaceState.planForTab(cur_frm,'System');
                const plan=JSON.parse(row.snapshot_json);
                window.__p0Pending=AlmdinaCuttingPlanRender.print(cur_frm,plan,
                    {tab:'System',row});
            }""")
            page.wait_for_function("!!window.__p0ResolveIdentity", timeout=10000)
            pending_writes = page.evaluate("__p0PrintWrites.length")
            assert pending_writes == writes_before + 1
            page.evaluate("name => frappe.set_route('Form','Door Cutting Order',name)", a["name"])
            page.wait_for_function("name => cur_frm?.doc?.name === name", arg=a["name"], timeout=45000)
            page.evaluate("__p0ResolveIdentity({})")
            assert page.evaluate("async () => await __p0Pending") is False
            assert page.evaluate("__p0PrintWrites.length") == pending_writes
            evidence["mid_await_route_change_cancelled"] = {
                "preparation_writes": 1, "final_html_writes": 0}
        except Exception as exc:
            evidence["failure"] = repr(exc)
            evidence["browser_state"] = page.evaluate("""() => ({route:frappe.get_route?.(),
                current:cur_frm?.doc?.name, canView:AlmdinaPlanWorkspaceState?.canView(cur_frm),
                planState:AlmdinaPlanWorkspaceState?.snapshot(cur_frm)?.status,
                planAssets:AlmdinaDcoWorkspaceAssetRegistry?.isLoaded('plan'),
                body:document.body.innerText.slice(-700)})""")
            page.screenshot(path=str(evidence_dir / "saved-plan-failure.png"), full_page=True)
            raise
        finally:
            (evidence_dir / "saved-plan-print-evidence.json").write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            browser.close()


def test_recovery_saved_form_compatibility():
    """Observe saved EDIT/Recovery boundaries; NEW Form remains blocked separately."""
    fixture = json.loads(Path(os.environ["P0_FIXTURE_PATH"]).read_text())
    evidence_dir = Path(os.environ["P0_EVIDENCE_DIR"])
    evidence = {"new_form": "BLOCKED_RELEASE_GATE", "saved_forms": {}}
    with browser_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(locale="en-US")
            _login(page, fixture)
            for label in ("A", "B", "A"):
                name = fixture["orders"][label]["name"]
                page.evaluate("name => frappe.set_route('Form','Door Cutting Order',name)", name)
                page.wait_for_function("name => cur_frm?.doc?.name === name", arg=name, timeout=45000)
                entry = page.evaluate("""() => ({name:cur_frm.doc.name,
                    token:AlmdinaDocumentContext.capture(cur_frm),
                    edit:AlmdinaDcoEditSessionCoordinator?.snapshot(cur_frm) || null,
                    recovery:AlmdinaDcoRecovery?.LocalCheckpoint?.snapshot(cur_frm) || null,
                    isNew:!!cur_frm.is_new()})""")
                evidence["saved_forms"][f"{label}-{len(evidence['saved_forms'])}"] = entry
                assert not entry["isNew"] and entry["name"] == name
            first = evidence["saved_forms"]["A-0"]["token"]
            revisited = evidence["saved_forms"]["A-2"]["token"]
            assert revisited["generation"] > first["generation"], evidence
        finally:
            evidence_dir.mkdir(parents=True, exist_ok=True)
            (evidence_dir / "recovery-saved-compatibility.json").write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            browser.close()


def test_new_form_clean_preflight():
    """Open a first NEW Form before creating any recovery checkpoint."""
    fixture = json.loads(Path(os.environ["P0_FIXTURE_PATH"]).read_text())
    evidence_dir = Path(os.environ["P0_EVIDENCE_DIR"])
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence = {"scope": "fresh browser context, no recovery restore"}

    def record(name, value):
        evidence[name] = value
        (evidence_dir / "new-form-preflight.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    with browser_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(locale="en-US")
        page.on("pageerror", lambda error: record("page_error", {
            "message": str(error), "stack": getattr(error, "stack", None),
        }))
        try:
            _login(page, fixture)
            page.evaluate("name => { frappe.set_route('Form','Door Cutting Order',name); }",
                          fixture["orders"]["A"]["name"])
            page.wait_for_function("name => cur_frm?.doc?.name === name",
                                   arg=fixture["orders"]["A"]["name"], timeout=45000)
            record("saved_form", page.evaluate("""() => ({name:cur_frm.doc.name,
                route:frappe.get_route(),formFactory:!!frappe.views?.FormFactory,
                newDocApi:typeof frappe.new_doc})"""))
            record("new_local_name", page.evaluate("""() => {
                const name=frappe.model.make_new_doc_and_get_name('Door Cutting Order');
                window.__p0NewPreflightName=name;
                return name;
            }"""))
            page.evaluate("""() => {
                frappe.set_route('Form','Door Cutting Order',window.__p0NewPreflightName);
            }""")
            record("route_requested", True)
            page.wait_for_function("""() => cur_frm?.doctype === 'Door Cutting Order'
                && cur_frm?.doc?.name === window.__p0NewPreflightName && !!cur_frm.is_new()""",
                timeout=15000)
            page.wait_for_function("""() => !!AlmdinaDcoRecovery?.LocalCheckpoint
                ?.snapshot(cur_frm)""", timeout=15000)
            record("new_form", page.evaluate("""() => ({name:cur_frm.doc.name,
                route:frappe.get_route(),isNew:!!cur_frm.is_new(),
                token:AlmdinaDocumentContext.capture(cur_frm),
                recovery:AlmdinaDcoRecovery?.LocalCheckpoint?.snapshot(cur_frm) || null,
                modal:document.querySelector('.modal.show')?.innerText.slice(0,500) || null})"""))
            assert not evidence["new_form"]["modal"], evidence
        except Exception as error:
            record("failure", repr(error))
            try:
                record("browser_state", page.evaluate("""() => ({route:frappe.get_route?.(),
                    name:cur_frm?.doc?.name, isNew:!!cur_frm?.is_new?.(),
                    localName:window.__p0NewPreflightName,
                    modal:document.querySelector('.modal.show')?.innerText.slice(0,500) || null,
                    body:document.body.innerText.slice(-600)})"""))
                page.screenshot(path=str(evidence_dir / "new-form-preflight-failure.png"),
                                full_page=True)
            except Exception as probe_error:
                record("probe_error", repr(probe_error))
            raise
        finally:
            browser.close()


def _print_saved_plan_variant(source, prefix):
    """Real persisted manufacturing row prints via the visible Desk action."""
    fixture = json.loads(Path(os.environ["P0_FIXTURE_PATH"]).read_text())
    evidence_dir = Path(os.environ["P0_EVIDENCE_DIR"])
    selected = json.loads((evidence_dir / f"{prefix}-plan-fixture.json").read_text())
    evidence = {"fixture": selected}
    with browser_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(locale="en-US")
            _login(page, fixture)
            page.evaluate("""() => {
                window.__p0VariantWrites=[];
                window.open=()=>({document:{open(){},write(html){__p0VariantWrites.push(html)},
                    close(){}},close(){}});
            }""")
            page.evaluate("name => frappe.set_route('Form','Door Cutting Order',name)",
                          selected["order_name"])
            page.wait_for_function("name => cur_frm?.doc?.name === name",
                                   arg=selected["order_name"], timeout=45000)
            page.get_by_text("Cutting Plan", exact=True).first.click()
            source_tab = page.locator(f'.dco-plan-tabs [data-plan-tab="{source}"]')
            source_tab.wait_for(state="visible", timeout=45000)
            assert source_tab.is_enabled(), f"Operator source tab {source} is disabled"
            source_tab.click()
            page.wait_for_function("""args =>
                AlmdinaPlanWorkspaceState?.snapshot(cur_frm)?.status === 'ready'
                && AlmdinaPlanWorkspaceState?.snapshot(cur_frm)?.data?.order_name === args.name
                && AlmdinaPlanTabsUX.activeTab(cur_frm) === args.source
                && cur_frm.fields_dict.cutting_plan_html.$wrapper.get(0)
                    ?.querySelector(`[data-plan-tab="${args.source}"][aria-selected="true"]`)
                && AlmdinaPlanWorkspaceState?.displayedPlanForTab(cur_frm,args.source)?.name
                && !!cur_frm.fields_dict.cutting_plan_html.$wrapper.get(0)
                    ?.querySelector('.dco-cutting-plan')""",
                arg={"name": selected["order_name"], "source": source}, timeout=45000)
            evidence["source"] = page.evaluate("""source => ({
                selected:AlmdinaPlanTabsUX.activeTab(cur_frm),
                row:AlmdinaPlanWorkspaceState.displayedPlanForTab(cur_frm,source)?.name,
                revision:AlmdinaPlanWorkspaceState.displayedPlanForTab(cur_frm,source)?.revision,
                permission:AlmdinaPermissions.canDocument(cur_frm,'print_cutting_plan')})""", source)
            assert evidence["source"]["selected"] == source, evidence["source"]
            assert evidence["source"]["row"] == selected["plan_name"], evidence["source"]
            assert evidence["source"]["permission"]
            button = page.locator('.dco-plan-context-actions-host .dco-print-cutting-plan:visible')
            button.wait_for(state="visible", timeout=15000)
            assert button.is_enabled()
            button.click()
            page.wait_for_function("() => __p0VariantWrites.length >= 2", timeout=15000)
            html = page.evaluate("__p0VariantWrites.at(-1)")
            assert selected["order_name"] in html
            assert selected["plan_name"] in html
            assert str(selected["revision"]) in html
            assert selected["board"] in html
            assert html.count('class="dco-sheet-card"') == selected["sheets"]
            other_labels = ("B",) if prefix == "custom" else (("A",) if prefix == "approved" else ("A", "B"))
            for other in other_labels:
                assert fixture["orders"][other]["name"] not in html
            assert ("570 × 930" if prefix == "approved" else "420 × 810") in html
            if prefix == "multi":
                assert selected["sheets"] >= 2
                assert 'data-overlay-kind="liner"' in html
            if prefix == "offcut":
                assert selected["offcut_kind"] == "OFFCUT"
                assert selected["offcut_source"] == "FACTORY"
                assert selected["offcut_execution"] == "FACTORY"
                assert 'data-resource-kind="OFFCUT"' in html
                context = re.search(
                    r'<div class="dco-offcut-business-context"[^>]*>(.*?)</div>',
                    html, re.S,
                )
                assert context and "من المعمل" in context.group(1)
                assert "في المعمل" in context.group(1)
            filename = f"{prefix}-plan-operator-final.html"
            (evidence_dir / filename).write_text(html, encoding="utf-8")
            evidence["final_html"] = filename
        except Exception as exc:
            evidence["failure"] = repr(exc)
            try:
                evidence["browser_state"] = page.evaluate("""() => ({
                    route:frappe.get_route(), current:cur_frm?.doc?.name,
                    tab:AlmdinaPlanTabsUX?.activeTab(cur_frm),
                    plan:AlmdinaPlanWorkspaceState?.snapshot(cur_frm)?.status,
                    body:document.body.innerText.slice(-650)})""")
                page.screenshot(path=str(evidence_dir / f"{prefix}-plan-failure.png"), full_page=True)
            except Exception:
                pass
            raise
        finally:
            (evidence_dir / f"{prefix}-plan-print-evidence.json").write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            browser.close()


def test_saved_custom_plan_operator_print():
    _print_saved_plan_variant("Custom", "custom")


def test_saved_approved_plan_operator_print():
    _print_saved_plan_variant("Approved", "approved")


def test_saved_multiboard_extra_operator_print():
    _print_saved_plan_variant("System", "multi")


def test_saved_offcut_operator_print():
    _print_saved_plan_variant("Custom", "offcut")


def test_recovery_new_saved_intersection():
    """Observe the real NEW→Saved boundary without mutating Recovery code."""
    fixture = json.loads(Path(os.environ["P0_FIXTURE_PATH"]).read_text())
    evidence_dir = Path(os.environ["P0_EVIDENCE_DIR"])
    evidence = {"scope": "Develop NEW checkpoint, Start New cancel, Continue restore, Native Save, post-save Plan/Cost edits"}

    def mark_step(name):
        evidence["last_completed_step"] = name
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / "recovery-intersection.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    with browser_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(locale="en-US")
            page_errors = []
            page.on("pageerror", lambda error: page_errors.append({
                "message": str(error), "stack": getattr(error, "stack", None),
            }))
            _login(page, fixture)
            page.evaluate("name => { frappe.set_route('Form','Door Cutting Order',name); }",
                          fixture["orders"]["A"]["name"])
            page.wait_for_function("name => cur_frm?.doc?.name === name",
                                   arg=fixture["orders"]["A"]["name"], timeout=45000)
            evidence["saved_a"] = page.evaluate("""() => ({name:cur_frm.doc.name,
                isNew:!!cur_frm.is_new(),
                edit:AlmdinaDcoEditSessionCoordinator?.snapshot(cur_frm) || null,
                recovery:AlmdinaDcoRecovery?.LocalCheckpoint?.snapshot(cur_frm) || null,
                plan:AlmdinaPlanWorkspaceState.snapshot(cur_frm),
                cost:AlmdinaCostWorkspaceState.snapshot(cur_frm)})""")
            mark_step("saved_A_open")
            # Pinned Frappe new_doc opens Quick Entry when no create route is
            # registered. Construct the NEW document through its model API and
            # navigate by the standard Form route to exercise Desk lifecycle.
            page.evaluate("""() => {
                window.__p0NewName=frappe.model.make_new_doc_and_get_name('Door Cutting Order');
            }""")
            evidence["new_name"] = page.evaluate("window.__p0NewName")
            mark_step("NEW_model_created")
            page.evaluate("""() => {
                frappe.set_route('Form','Door Cutting Order',window.__p0NewName);
            }""")
            mark_step("NEW_route_requested")
            page.wait_for_function("() => cur_frm?.doctype === 'Door Cutting Order' && !!cur_frm.is_new()",
                                   timeout=45000)
            mark_step("NEW_route_open")
            page.wait_for_function("() => !!AlmdinaDcoRecovery?.LocalCheckpoint?.snapshot(cur_frm)",
                                   timeout=15000)
            mark_step("NEW_checkpoint_ready")
            evidence["new_before_save"] = page.evaluate("""() => ({
                identity:AlmdinaDocumentContext.formIdentity(cur_frm),
                generation:AlmdinaDocumentContext.capture(cur_frm)?.generation,
                isNew:!!cur_frm.is_new(),
                recovery:AlmdinaDcoRecovery?.LocalCheckpoint?.snapshot(cur_frm) || null,
                edit:AlmdinaDcoEditSessionCoordinator?.snapshot(cur_frm) || null})""")
            mark_step("NEW_Form_open")
            page.evaluate("""args => {
                window.__p0Input={status:'pending',field:null};
                (async () => {
                    const frm=cur_frm;
                    for (const [field,value] of Object.entries(args.fields)) {
                        window.__p0Input.field=field;
                        await frm.set_value(field,value);
                    }
                    const piece=frappe.model.add_child(frm.doc,'Door Cutting Order Detail','pieces');
                    piece.piece_type='Regular'; piece.width_cm=31; piece.length_cm=62; piece.qty=1;
                    frm.refresh_field('pieces');
                    AlmdinaDcoRecovery?.LocalCheckpoint?.markDirty(frm);
                    window.__p0Input={status:'settled',name:frm.doc.name,
                        board:frm.doc.board_description,
                        pieces:frm.doc.pieces.map(row=>({name:row.name,width_cm:row.width_cm})),
                        recovery:AlmdinaDcoRecovery?.LocalCheckpoint?.snapshot(frm) || null};
                })().catch(error=>window.__p0Input={status:'rejected',error:String(error)});
            }""", {"fields": {"customer": fixture["customer"],
                "board_description": fixture["recovery_board"],
                "order_cutting_machine": "CNC",
                "board_width_cm": 122, "board_length_cm": 244,
                "default_edge_type": fixture["edge_type"], "edge_color": "P0 Recovery edge",
                "board_rate_usd": 7, "cutting_cost_per_board_usd": 2}})
            mark_step("NEW_input_started")
            try:
                page.wait_for_function("window.__p0Input?.status !== 'pending'", timeout=20000)
            finally:
                evidence["input"] = page.evaluate("window.__p0Input")
                mark_step("NEW_input_wait_finished")
            assert evidence["input"]["status"] == "settled", evidence["input"]
            mark_step("NEW_input_complete")
            page.evaluate("""() => {
                window.__p0Flush={status:'pending'};
                Promise.resolve(AlmdinaDcoRecovery.LocalCheckpoint.flush(cur_frm)).then(
                    value=>window.__p0Flush={status:'settled',ok:!!value?.ok,
                        error:value?.error?.code || null},
                    error=>window.__p0Flush={status:'rejected',error:String(error)});
            }""")
            page.wait_for_function("window.__p0Flush?.status !== 'pending'", timeout=20000)
            evidence["checkpoint"] = page.evaluate("window.__p0Flush")
            mark_step("checkpoint_flush_settled")
            assert evidence["checkpoint"]["status"] == "settled", evidence["checkpoint"]
            assert evidence["checkpoint"].get("ok"), evidence["checkpoint"]
            page.evaluate("name => { frappe.set_route('Form','Door Cutting Order',name); }",
                          fixture["orders"]["B"]["name"])
            page.wait_for_function("name => cur_frm?.doc?.name === name",
                                   arg=fixture["orders"]["B"]["name"], timeout=45000)

            def open_new_form():
                page.evaluate("""() => {
                    const name=frappe.model.make_new_doc_and_get_name('Door Cutting Order');
                    frappe.set_route('Form','Door Cutting Order',name);
                }""")
                page.wait_for_function("() => cur_frm?.doctype === 'Door Cutting Order' && !!cur_frm.is_new()",
                                       timeout=45000)

            open_new_form()
            page.locator('[data-recovery-action="new"]:visible').wait_for(timeout=15000)
            evidence["discovery_before_cancel"] = page.evaluate("""() => ({
                draftCards:document.querySelectorAll('[data-draft-id]').length,
                board:cur_frm.doc.board_description || null})""")
            page.locator('[data-recovery-action="new"]:visible').click()
            page.wait_for_function("""() => !document.querySelector('.modal.show [data-recovery-action="new"]')""",
                                   timeout=15000)
            evidence["cancel_restore"] = page.evaluate("""() => ({
                board:cur_frm.doc.board_description || null,
                pieces:(cur_frm.doc.pieces || []).map(row=>row.width_cm),
                isNew:!!cur_frm.is_new()})""")
            assert evidence["cancel_restore"]["isNew"]
            assert not evidence["cancel_restore"]["board"]
            assert 31 not in evidence["cancel_restore"]["pieces"]
            mark_step("restore_cancelled_with_start_new")
            page.evaluate("name => { frappe.set_route('Form','Door Cutting Order',name); }",
                          fixture["orders"]["B"]["name"])
            page.wait_for_function("name => cur_frm?.doc?.name === name",
                                   arg=fixture["orders"]["B"]["name"], timeout=45000)
            open_new_form()
            page.locator('[data-recovery-action="continue"]:visible').wait_for(timeout=15000)
            page.locator('[data-recovery-action="continue"]:visible').first.click()
            page.wait_for_function("board => cur_frm?.doc?.board_description === board",
                                   arg=fixture["recovery_board"], timeout=15000)
            evidence["restore"] = page.evaluate("""() => ({
                board:cur_frm.doc.board_description,
                customer:cur_frm.doc.customer,
                pieceWidths:cur_frm.doc.pieces.map(row=>row.width_cm),
                token:AlmdinaDocumentContext.capture(cur_frm),
                recovery:AlmdinaDcoRecovery.LocalCheckpoint.snapshot(cur_frm)})""")
            assert evidence["restore"]["customer"] == fixture["customer"]
            assert 31 in evidence["restore"]["pieceWidths"]
            mark_step("draft_restored")
            page.evaluate("""() => {
                const frm=cur_frm;
                window.__p0NativeSave={status:'pending',startName:frm.doc.name};
                Promise.resolve().then(()=>frm.save()).then(
                    ()=>window.__p0NativeSave={status:'settled',ok:!frm.is_new(),
                        name:frm.doc.name,board:frm.doc.board_description,
                        token:AlmdinaDocumentContext.capture(frm),
                        pieceWidths:(frm.doc.pieces || []).map(row=>row.width_cm),
                        recovery:AlmdinaDcoRecovery?.LocalCheckpoint?.snapshot(frm) || null},
                    error=>window.__p0NativeSave={status:'rejected',ok:false,
                        error:String(error),name:frm.doc.name,
                        recovery:AlmdinaDcoRecovery?.LocalCheckpoint?.snapshot(frm) || null});
            }""")
            mark_step("native_save_started")
            try:
                page.wait_for_function("window.__p0NativeSave?.status !== 'pending'", timeout=20000)
                evidence["native_save"] = page.evaluate("window.__p0NativeSave")
            except Exception:
                evidence["native_save"] = page.evaluate("""() => ({
                    ...window.__p0NativeSave,ok:false,timeout:true,
                    modal:document.querySelector('.modal.show')?.innerText.slice(0,700) || null,
                    recovery:AlmdinaDcoRecovery?.LocalCheckpoint?.snapshot(cur_frm) || null})""")
            assert not evidence["native_save"].get("timeout"), evidence["native_save"]
            assert evidence["native_save"]["status"] == "settled" and evidence["native_save"]["ok"], evidence["native_save"]
            assert evidence["native_save"]["board"] == fixture["recovery_board"]
            assert not evidence["native_save"]["name"].startswith("new-"), evidence["native_save"]
            assert 31 in evidence["native_save"]["pieceWidths"]
            assert evidence["native_save"]["token"]["identity"].endswith(
                f"::{evidence['native_save']['name']}")
            assert evidence["native_save"]["token"]["generation"] == evidence["restore"]["token"]["generation"]
            mark_step("native_save_settled")
            # Continue within the same Desk visit and generation immediately after
            # the first Native Save. All edits use the visible operator controls.
            saved = evidence["native_save"]["name"]
            page.get_by_text("Cutting Plan", exact=True).first.click()
            page.wait_for_function("""name => cur_frm?.doc?.name === name
                && AlmdinaPlanWorkspaceState?.snapshot(cur_frm)?.status === 'ready'
                && AlmdinaPlanWorkspaceState?.snapshot(cur_frm)?.data?.order_name === name""",
                arg=saved, timeout=45000)
            first_plan = page.locator('.dco-recalculate-plan:visible').first()
            first_plan.wait_for(state="visible", timeout=15000)
            assert first_plan.is_enabled(), "First System plan bootstrap is not available"
            first_plan.click()
            page.wait_for_function("""name =>
                AlmdinaPlanWorkspaceState?.snapshot(cur_frm)?.status === 'ready'
                && AlmdinaPlanWorkspaceState?.snapshot(cur_frm)?.data?.order_name === name
                && !!AlmdinaPlanWorkspaceState?.snapshot(cur_frm)?.data?.plans?.system_draft?.name""",
                arg=saved, timeout=60000)
            evidence["plan_bootstrap"] = page.evaluate("""() => ({
                token:AlmdinaDocumentContext.capture(cur_frm),
                plan:AlmdinaPlanWorkspaceState.snapshot(cur_frm).data.plans.system_draft.name,
                kerf:cur_frm.doc.kerf_mm})""")
            assert evidence["plan_bootstrap"]["token"]["generation"] == evidence["native_save"]["token"]["generation"]
            mark_step("post_save_system_plan_bootstrapped")

            plan_toolbar = page.locator('.dco-tab-edit-toolbar[data-almdina-tab-edit-kind="plan"]')
            plan_toolbar.locator('.dco-tab-edit-start').click()
            kerf = page.locator('[data-almdina-plan-setting="kerf_mm"]:visible').first()
            kerf.wait_for(state="visible", timeout=15000)
            original_kerf = float(kerf.input_value())
            new_kerf = original_kerf + 1
            kerf.fill(str(new_kerf))
            evidence["plan_draft"] = page.evaluate("""() => ({
                edit:AlmdinaDcoEditSessionCoordinator.snapshot(cur_frm),
                draft:AlmdinaPlanEditSessionUX.snapshot?.(cur_frm) || null,
                token:AlmdinaDocumentContext.capture(cur_frm)})""")
            assert evidence["plan_draft"]["token"]["generation"] == evidence["native_save"]["token"]["generation"]
            plan_toolbar.locator('.dco-tab-edit-cancel').click()
            page.wait_for_function("""() => AlmdinaDcoEditSessionCoordinator.snapshot(cur_frm).activeKind === null""",
                                   timeout=15000)
            assert float(page.evaluate('cur_frm.doc.kerf_mm')) == original_kerf
            assert float(page.evaluate("""() => AlmdinaPlanWorkspaceState.snapshot(cur_frm)
                .data.plans.system_draft.settings.kerf_mm""")) == original_kerf
            mark_step("plan_draft_cancelled")
            plan_toolbar.locator('.dco-tab-edit-start').click()
            kerf = page.locator('[data-almdina-plan-setting="kerf_mm"]:visible').first()
            kerf.fill(str(new_kerf))
            recalculate = page.locator('.dco-recalculate-plan:visible').first()
            assert recalculate.is_enabled()
            recalculate.click()
            page.wait_for_function("""() => AlmdinaPlanPreviewSession?.snapshot(cur_frm)?.status === 'ready'
                && AlmdinaPlanPreviewSession?.isCommittable(cur_frm)""", timeout=60000)
            evidence["plan_preview"] = page.evaluate("""() => {
                const preview=AlmdinaPlanPreviewSession.snapshot(cur_frm);
                const row=AlmdinaPlanWorkspaceState.snapshot(cur_frm)?.data?.plans?.system_draft;
                return {preview_id:preview.previewId, status:preview.status,
                    source_plan:row?.name, source_revision:row?.revision,
                    token:AlmdinaDocumentContext.capture(cur_frm)};
            }""")
            save_plan = plan_toolbar.locator('.dco-tab-edit-save')
            assert save_plan.is_enabled()
            save_plan.click()
            page.wait_for_function("""value =>
                AlmdinaDcoEditSessionCoordinator.snapshot(cur_frm).activeKind === null
                && Number(cur_frm.doc.kerf_mm) === value""", arg=new_kerf, timeout=60000)
            evidence["plan_saved"] = page.evaluate("""() => ({
                kerf:cur_frm.doc.kerf_mm,
                plan:AlmdinaPlanWorkspaceState.snapshot(cur_frm)?.data?.plans?.system_draft?.name,
                token:AlmdinaDocumentContext.capture(cur_frm)})""")
            mark_step("plan_preview_committed")

            page.get_by_text("Order Cost", exact=True).first.click()
            page.wait_for_function("""name => AlmdinaCostWorkspaceState?.snapshot(cur_frm)?.status === 'ready'
                && AlmdinaCostWorkspaceState?.snapshot(cur_frm)?.data?.order_name === name""",
                arg=saved, timeout=45000)
            cost_toolbar = page.locator('.dco-tab-edit-toolbar[data-almdina-tab-edit-kind="cost"]')
            cost_toolbar.locator('.dco-tab-edit-start').click()
            board_rate = page.locator('[data-fieldname="board_rate_usd"] .almdina-workspace-field-editor .form-control:visible').first()
            board_rate.wait_for(state="visible", timeout=15000)
            original_rate = float(board_rate.input_value())
            new_rate = original_rate + 3
            board_rate.fill(str(new_rate))
            evidence["cost_draft"] = page.evaluate("""() => ({
                edit:AlmdinaDcoEditSessionCoordinator.snapshot(cur_frm),
                token:AlmdinaDocumentContext.capture(cur_frm)})""")
            assert evidence["cost_draft"]["token"]["generation"] == evidence["native_save"]["token"]["generation"]
            cost_toolbar.locator('.dco-tab-edit-cancel').click()
            page.wait_for_function("""() => AlmdinaDcoEditSessionCoordinator.snapshot(cur_frm).activeKind === null""",
                                   timeout=15000)
            assert float(page.evaluate('cur_frm.doc.board_rate_usd')) == original_rate
            assert float(page.evaluate("""() => AlmdinaCostWorkspaceState.snapshot(cur_frm)
                .data.order.board_rate_usd""")) == original_rate
            mark_step("cost_draft_cancelled")
            cost_toolbar.locator('.dco-tab-edit-start').click()
            board_rate = page.locator('[data-fieldname="board_rate_usd"] .almdina-workspace-field-editor .form-control:visible').first()
            board_rate.fill(str(new_rate))
            cost_toolbar.locator('.dco-tab-edit-save').click()
            page.wait_for_function("""value =>
                AlmdinaDcoEditSessionCoordinator.snapshot(cur_frm).activeKind === null
                && Number(cur_frm.doc.board_rate_usd) === value""", arg=new_rate, timeout=45000)
            evidence["cost_saved"] = page.evaluate("""() => ({
                board_rate:cur_frm.doc.board_rate_usd,
                token:AlmdinaDocumentContext.capture(cur_frm)})""")
            mark_step("cost_settings_committed")
            if evidence["native_save"]["ok"]:
                saved = evidence["native_save"]["name"]
                page.evaluate("name => { frappe.set_route('Form','Door Cutting Order',name); }",
                              fixture["orders"]["B"]["name"])
                page.wait_for_function("name => cur_frm?.doc?.name === name",
                                       arg=fixture["orders"]["B"]["name"], timeout=45000)
                page.evaluate("name => { frappe.set_route('Form','Door Cutting Order',name); }", saved)
                page.wait_for_function("name => cur_frm?.doc?.name === name", arg=saved, timeout=45000)
                page.get_by_text("Cutting Plan", exact=True).first.click()
                page.wait_for_function("""name =>
                    AlmdinaPlanWorkspaceState?.snapshot(cur_frm)?.status === 'ready'
                    && AlmdinaPlanWorkspaceState?.snapshot(cur_frm)?.data?.order_name === name""",
                    arg=saved, timeout=45000)
                page.get_by_text("Order Cost", exact=True).first.click()
                page.wait_for_function("""name =>
                    AlmdinaPlanWorkspaceState?.snapshot(cur_frm)?.status === 'ready'
                    && AlmdinaPlanWorkspaceState?.snapshot(cur_frm)?.data?.order_name === name
                    && AlmdinaCostWorkspaceState?.snapshot(cur_frm)?.status === 'ready'
                    && AlmdinaCostWorkspaceState?.snapshot(cur_frm)?.data?.order_name === name""",
                    arg=saved, timeout=45000)
                evidence["saved_reopen"] = page.evaluate("""() => ({name:cur_frm.doc.name,
                    board:cur_frm.doc.board_description,
                    customer:cur_frm.doc.customer,
                    pieceWidths:(cur_frm.doc.pieces || []).map(row=>row.width_cm),
                    token:AlmdinaDocumentContext.capture(cur_frm),
                    edit:AlmdinaDcoEditSessionCoordinator?.snapshot(cur_frm) || null,
                    recovery:AlmdinaDcoRecovery?.LocalCheckpoint?.snapshot(cur_frm) || null,
                    plan:AlmdinaPlanWorkspaceState.snapshot(cur_frm),
                    cost:AlmdinaCostWorkspaceState.snapshot(cur_frm)})""")
                assert evidence["saved_reopen"]["board"] == fixture["recovery_board"]
                assert evidence["saved_reopen"]["customer"] == fixture["customer"]
                assert 31 in evidence["saved_reopen"]["pieceWidths"]
                assert evidence["saved_reopen"]["token"]["identity"].endswith(f"::{saved}")
                assert float(page.evaluate("""() => AlmdinaPlanWorkspaceState.snapshot(cur_frm)
                    .data.plans.system_draft.settings.kerf_mm""")) == new_kerf
                assert float(page.evaluate("""() => AlmdinaCostWorkspaceState.snapshot(cur_frm)
                    .data.order.board_rate_usd""")) == new_rate
                page.evaluate("name => frappe.set_route('Form','Door Cutting Order',name)", fixture["orders"]["A"]["name"])
                page.wait_for_function("name => cur_frm?.doc?.name === name",
                                       arg=fixture["orders"]["A"]["name"], timeout=45000)
                assert float(page.evaluate('cur_frm.doc.kerf_mm')) != new_kerf
                assert float(page.evaluate('cur_frm.doc.board_rate_usd')) != new_rate
                mark_step("post_save_cross_order_isolated")
        except Exception as exc:
            evidence["failure"] = repr(exc)
            evidence["browser_state"] = page.evaluate("""() => ({route:frappe.get_route?.(),
                current:cur_frm?.doc?.name,isNew:!!cur_frm?.is_new?.(),
                modal:document.querySelector('.modal.show')?.innerText.slice(0,600) || null,
                body:document.body.innerText.slice(-700)})""")
            page.screenshot(path=str(evidence_dir / "recovery-failure.png"), full_page=True)
            raise
        finally:
            evidence["page_errors"] = page_errors
            evidence_dir.mkdir(parents=True, exist_ok=True)
            (evidence_dir / "recovery-intersection.json").write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            browser.close()
