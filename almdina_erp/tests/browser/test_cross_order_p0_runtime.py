Warning: truncated output (original token count: 26073)
Total output lines: 1647

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
             …11073 tokens truncated…                   AlmdinaDcoEditSessionCoordinator.snapshot(cur_frm).activeKind === null
                    && Number(cur_frm.doc.kerf_mm) === value""", arg=new_kerf, timeout=60000)
            except Exception:
                evidence["plan_save_boundary"] = page.evaluate("""() => {
                    const snapshot=AlmdinaPlanWorkspaceState.snapshot(cur_frm);
                    const row=snapshot?.data?.plans?.system_draft;
                    return {token:AlmdinaDocumentContext.capture(cur_frm),
                        edit:AlmdinaDcoEditSessionCoordinator.snapshot(cur_frm),
                        preview:AlmdinaPlanPreviewSession.snapshot(cur_frm),
                        planStatus:snapshot?.status,planOrder:snapshot?.data?.order_name,
                        planName:row?.name,planRevision:row?.revision,
                        rowKerf:row?.settings?.kerf_mm,docKerf:cur_frm.doc.kerf_mm,
                        summary:document.querySelector('[data-fieldname="kerf_mm"]')?.innerText.slice(0,150),
                        modal:document.querySelector('.modal.show')?.innerText.slice(0,500) || null};
                }""")
                raise
            evidence["plan_saved"] = page.evaluate("""() => ({
                kerf:cur_frm.doc.kerf_mm,
                plan:AlmdinaPlanWorkspaceState.snapshot(cur_frm)?.data?.plans?.system_draft?.name,
                token:AlmdinaDocumentContext.capture(cur_frm)})""")
            requests = evidence["preview_commit_requests"]
            responses = evidence["preview_commit_responses"]
            assert len(requests) == len(responses) == 1, (requests, responses)
            assert requests[0]["order_name"] == saved
            assert requests[0]["preview_id"] == evidence["plan_preview"]["preview_id"]
            receipt = responses[0]["response"]
            assert responses[0]["http_status"] == 200 and isinstance(receipt, dict)
            assert receipt["exact_preview_commit"] is True
            assert receipt["committed_preview_id"] == requests[0]["preview_id"]
            assert receipt["name"] == saved
            assert receipt["cutting_plan"] == evidence["plan_preview"]["source_plan"]
            assert receipt["plan_revision"] == evidence["plan_preview"]["source_revision"]
            assert float(receipt["kerf_mm"]) == new_kerf
            mark_step("plan_preview_committed")

            # Exercise the same real Save button with a completed HTTP 200 whose
            # Frappe message is null. The endpoint is intercepted only for this
            # second preview, so the canonical server plan remains at Kerf 4.
            plan_toolbar.locator('.dco-tab-edit-start').click()
            kerf = page.locator('[data-almdina-plan-setting="kerf_mm"]:visible').first
            kerf.fill(str(new_kerf + 1))
            page.locator('.dco-recalculate-plan:visible').first.press("Enter")
            page.wait_for_function("""value => AlmdinaPlanPreviewSession?.isCommittable(cur_frm)
                && Number(AlmdinaPlanPreviewSession.snapshot(cur_frm)?.requestedSettings?.kerf_mm) === value""",
                arg=new_kerf + 1, timeout=60000)
            injected_preview = page.evaluate("AlmdinaPlanPreviewSession.snapshot(cur_frm).previewId")
            commit_route = "**/api/method/almdina_erp.almdina_erp.services.cutting_plan_preview_service.commit_cutting_plan_preview"
            page.route(commit_route, lambda route: route.fulfill(
                status=200, content_type="application/json", body='{"message":null}'))
            try:
                plan_toolbar.locator('.dco-tab-edit-save').click()
                page.wait_for_function("""() => AlmdinaPlanPreviewSession.snapshot(cur_frm).status === 'stale'
                    && AlmdinaDcoEditSessionCoordinator.snapshot(cur_frm).phase === 'editing'""",
                    timeout=15000)
                evidence["null_receipt_rejected"] = page.evaluate("""() => ({
                    preview:AlmdinaPlanPreviewSession.snapshot(cur_frm),
                    coordinator:AlmdinaDcoEditSessionCoordinator.snapshot(cur_frm),
                    canonicalKerf:AlmdinaPlanWorkspaceState.snapshot(cur_frm)?.data?.plans
                        ?.system_draft?.settings?.kerf_mm,
                    docKerf:cur_frm.doc.kerf_mm,
                })""")
                assert float(evidence["null_receipt_rejected"]["canonicalKerf"]) == new_kerf
                assert float(evidence["null_receipt_rejected"]["docKerf"]) == new_kerf
                assert evidence["preview_commit_requests"][-1]["preview_id"] == injected_preview
                assert evidence["preview_commit_responses"][-1]["response"] is None
            finally:
                page.unroute(commit_route)
            # The error modal may enter `.show` after the state snapshot above.
            # Wait for its real visibility before dismissing it through Frappe.
            message_modal = page.locator('.modal.show').filter(
                has_text="The cutting plan save could not be confirmed.")
            message_modal.wait_for(state="visible", timeout=15000)
            message_modal.locator('.modal-header button:visible').first.click()
            message_modal.wait_for(state="hidden", timeout=15000)
            plan_toolbar.locator('.dco-tab-edit-cancel').click()
            page.wait_for_function("""() => AlmdinaDcoEditSessionCoordinator.snapshot(cur_frm)
                .phase === 'idle'""", timeout=15000)
            mark_step("null_preview_receipt_rejected")

            # Prove the opposite ambiguous boundary on the REAL server: commit
            # Kerf 6 durably, but replace only its browser-facing response with
            # HTTP 200 + null. Canonical read-only reconciliation must close
            # editing without replaying the single-use preview token.
            original_preview_evidence = evidence["plan_preview"]
            original_saved_evidence = evidence["plan_saved"]
            reconciled_kerf = new_kerf + 2
            plan_toolbar.locator('.dco-tab-edit-start').click()
            kerf = page.locator('[data-almdina-plan-setting="kerf_mm"]:visible').first
            kerf.fill(str(reconciled_kerf))
            page.locator('.dco-recalculate-plan:visible').first.press("Enter")
            page.wait_for_function("""value => AlmdinaPlanPreviewSession?.isCommittable(cur_frm)
                && Number(AlmdinaPlanPreviewSession.snapshot(cur_frm)?.requestedSettings?.kerf_mm) === value""",
                arg=reconciled_kerf, timeout=60000)
            reconciled_preview_id = page.evaluate("AlmdinaPlanPreviewSession.snapshot(cur_frm).previewId")
            reconciled_source = page.evaluate("""() => ({
                source_plan:AlmdinaPlanPreviewSession.snapshot(cur_frm)?.payload?.source_plan_name,
                source_revision:AlmdinaPlanPreviewSession.snapshot(cur_frm)?.payload?.source_plan_revision,
                preview_id:AlmdinaPlanPreviewSession.snapshot(cur_frm)?.previewId,
            })""")
            actual_server_commit = {}

            def hide_only_successful_commit_response(route):
                response = route.fetch()
                actual_server_commit["status"] = response.status
                try:
                    message = response.json().get("message")
                    actual_server_commit["receipt"] = {
                        key: message.get(key) for key in (
                            "name", "cutting_plan", "plan_revision",
                            "committed_preview_id", "exact_preview_commit", "kerf_mm"
                        )
                    } if isinstance(message, dict) else message
                except Exception as exc:
                    actual_server_commit["parse_error"] = type(exc).__name__
                route.fulfill(status=200, content_type="application/json",
                              body='{"message":null}')

            page.route(commit_route, hide_only_successful_commit_response)
            try:
                plan_toolbar.locator('.dco-tab-edit-save').click()
                page.wait_for_function("""value =>
                    AlmdinaDcoEditSessionCoordinator.snapshot(cur_frm).phase === 'idle'
                    && Number(AlmdinaPlanWorkspaceState.snapshot(cur_frm)
                        ?.data?.plans?.system_draft?.settings?.kerf_mm) === value""",
                    arg=reconciled_kerf, timeout=60000)
                evidence["lost_response_durable_commit"] = {
                    "server": actual_server_commit,
                    "preview": reconciled_source,
                    "browser_response": evidence["preview_commit_responses"][-1],
                    "coordinator": page.evaluate(
                        "AlmdinaDcoEditSessionCoordinator.snapshot(cur_frm)"),
                    "canonical_kerf": page.evaluate("""() =>
                        AlmdinaPlanWorkspaceState.snapshot(cur_frm)
                        ?.data?.plans?.system_draft?.settings?.kerf_mm"""),
                }
                receipt = actual_server_commit.get("receipt")
                assert actual_server_commit.get("status") == 200 and isinstance(receipt, dict)
                assert receipt["exact_preview_commit"] is True
                assert receipt["committed_preview_id"] == reconciled_preview_id
                assert receipt["name"] == saved
                assert receipt["cutting_plan"] == reconciled_source["source_plan"]
                assert receipt["plan_revision"] == reconciled_source["source_revision"]
                assert float(receipt["kerf_mm"]) == reconciled_kerf
                assert evidence["preview_commit_requests"][-1]["preview_id"] == reconciled_preview_id
                assert evidence["preview_commit_responses"][-1]["response"] is None
            finally:
                page.unroute(commit_route)
            evidence["initial_plan_preview"] = original_preview_evidence
            evidence["initial_plan_saved"] = original_saved_evidence
            evidence["plan_preview"] = reconciled_source
            evidence["plan_saved"] = page.evaluate("""() => ({
                kerf:cur_frm.doc.kerf_mm,
                plan:AlmdinaPlanWorkspaceState.snapshot(cur_frm)?.data?.plans?.system_draft?.name,
                token:AlmdinaDocumentContext.capture(cur_frm)})""")
            assert float(evidence["plan_saved"]["kerf"]) == reconciled_kerf
            new_kerf = reconciled_kerf
            mark_step("lost_response_commit_verified_from_server")

            page.get_by_text("Order Cost", exact=True).first.click()
            page.wait_for_function("""name => AlmdinaCostWorkspaceState?.snapshot(cur_frm)?.status === 'ready'
                && AlmdinaCostWorkspaceState?.snapshot(cur_frm)?.data?.order_name === name""",
                arg=saved, timeout=45000)
            cost_toolbar = page.locator('.dco-tab-edit-toolbar[data-almdina-tab-edit-kind="cost"]')
            cost_toolbar.locator('.dco-tab-edit-start').click()
            board_rate = page.locator('[data-fieldname="board_rate_usd"] .almdina-workspace-field-editor .form-control:visible').first
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
            board_rate = page.locator('[data-fieldname="board_rate_usd"] .almdina-workspace-field-editor .form-control:visible').first
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
                page.get_by_text("Cutting Plan", exact=True).first.click()
                page.get_by_text("Order Cost", exact=True).first.click()
                page.wait_for_function("""name =>
                    AlmdinaPlanWorkspaceState?.snapshot(cur_frm)?.status === 'ready'
                    && AlmdinaPlanWorkspaceState.snapshot(cur_frm)?.data?.order_name === name
                    && AlmdinaCostWorkspaceState?.snapshot(cur_frm)?.status === 'ready'
                    && AlmdinaCostWorkspaceState.snapshot(cur_frm)?.data?.order_name === name""",
                    arg=fixture["orders"]["A"]["name"], timeout=45000)
                evidence["other_order_after_edit"] = page.evaluate("""() => ({
                    token:AlmdinaDocumentContext.capture(cur_frm),
                    docKerf:cur_frm.doc.kerf_mm, docRate:cur_frm.doc.board_rate_usd,
                    planKerf:AlmdinaPlanWorkspaceState.snapshot(cur_frm)?.data?.plans
                        ?.system_draft?.settings?.kerf_mm,
                    costRate:AlmdinaCostWorkspaceState.snapshot(cur_frm)?.data?.order?.board_rate_usd,
                    planOrder:AlmdinaPlanWorkspaceState.snapshot(cur_frm)?.data?.order_name,
                    costOrder:AlmdinaCostWorkspaceState.snapshot(cur_frm)?.data?.order_name,
                })""")
                other = evidence["other_order_after_edit"]
                assert other["token"]["identity"].endswith(f"::{fixture['orders']['A']['name']}")
                assert other["planOrder"] == other["costOrder"] == fixture["orders"]["A"]["name"]
                assert other["docKerf"] != new_kerf and other["planKerf"] != new_kerf
                assert other["docRate"] != new_rate and other["costRate"] != new_rate
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


def test_recovery_extra_fields_new_saved_in_desk():
    """Prove three distinct Extra rows survive NEW recovery and the first native Save."""
    fixture = json.loads(Path(os.environ["P0_FIXTURE_PATH"]).read_text())
    evidence_dir = Path(os.environ["P0_EVIDENCE_DIR"])
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_file = evidence_dir / "recovery-extras.json"
    extras = {
        "P0-LINER": {"extra_liner": 1, "liner_reference_side": "edge_width_top",
                     "liner_offset_cm": 2, "liner_width_cm": 1.8,
                     "liner_start_cm": 1, "liner_length_cm": 25},
        "P0-GROOVE": {"extra_back_groove": 1,
                      "back_groove_reference_side": "edge_long_right",
                      "back_groove_offset_cm": 1, "back_groove_width_cm": 0.7,
                      "back_groove_start_cm": 3, "back_groove_length_cm": 20},
        "P0-HANDLE": {"extra_recessed_handle_cutout": 1,
                      "recessed_handle_reference_side": "edge_width_bottom",
                      "recessed_handle_offset_cm": 3, "recessed_handle_width_cm": 1.2,
                      "recessed_handle_start_cm": 2, "recessed_handle_length_cm": 18},
    }
    evidence = {"expected": extras, "scope": "isolated Desk NEW, checkpoint, cancel, restore, Native Save, DB audit"}

    def capture(page):
        return page.evaluate("""() => ({name:cur_frm.doc.name,
            customer:cur_frm.doc.customer,board:cur_frm.doc.board_description,
            boardWidth:cur_frm.doc.board_width_cm,boardLength:cur_frm.doc.board_length_cm,
            token:AlmdinaDocumentContext.capture(cur_frm),
            rows:(cur_frm.doc.pieces || []).filter(row=>row.notes?.startsWith('P0-'))
                .map(row=>{const result={name:row.name,notes:row.notes};
                    for(const prefix of ['liner','back_groove','recessed_handle']) {
                        result[`extra_${prefix === 'recessed_handle' ? 'recessed_handle_cutout' : prefix}`]
                            = row[`extra_${prefix === 'recessed_handle' ? 'recessed_handle_cutout' : prefix}`];
                        for(const suffix of ['reference_side','offset_cm','width_cm','start_cm','length_cm'])
                            result[`${prefix}_${suffix}`]=row[`${prefix}_${suffix}`];
                    } return result;})})""")

    def verify_rows(rows):
        assert len(rows) == len(extras), rows
        assert set(row["notes"] for row in rows) == set(extras), rows
        for row in rows:
            for field, value in extras[row["notes"]].items():
                assert row[field] == value, (row["notes"], field, row[field], value)

    with browser_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(locale="en-US")
        evidence["savedocs_responses"] = []

        def record_save_response(response):
            if "frappe.desk.form.save.savedocs" not in response.url:
                return
            try:
                payload = response.json()
                evidence["savedocs_responses"].append({
                    "status": response.status, "keys": sorted(payload),
                    "exc_type": payload.get("exc_type"),
                    "exception": str(payload.get("exception") or "")[:500],
                    "server_messages": str(payload.get("_server_messages") or "")[:700],
                    "message_name": (payload.get("docs") or [{}])[0].get("name")
                        if isinstance(payload.get("docs"), list) else None,
                })
            except Exception as exc:
                evidence["savedocs_responses"].append({"status": response.status,
                                                         "parse_error": type(exc).__name__})

        page.on("response", record_save_response)
        try:
            _login(page, fixture)
            page.evaluate("name => frappe.set_route('Form','Door Cutting Order',name)",
                          fixture["orders"]["A"]["name"])
            page.wait_for_function("name => cur_frm?.doc?.name === name",
                                   arg=fixture["orders"]["A"]["name"], timeout=45000)

            def open_new(discovery=False):
                page.evaluate("""() => {
                    const name=frappe.model.make_new_doc_and_get_name('Door Cutting Order');
                    frappe.set_route('Form','Door Cutting Order',name);
                }""")
                page.wait_for_function("() => cur_frm?.doctype === 'Door Cutting Order' && !!cur_frm.is_new()",
                                       timeout=45000)
                if discovery:
                    page.locator('[data-recovery-action="new"]:visible').wait_for(timeout=15000)
                else:
                    page.wait_for_function("() => !!AlmdinaDcoRecovery?.LocalCheckpoint?.snapshot(cur_frm)",
                                           timeout=15000)

            open_new()
            page.evaluate("""args => {
                window.__p0ExtrasInput={status:'pending'};
                (async () => {
                    const frm=cur_frm;
                    for(const [field,value] of Object.entries(args.fields)) await frm.set_value(field,value);
                    for(const [note,fields] of Object.entries(args.extras)) {
                        const row=frappe.model.add_child(frm.doc,'Door Cutting Order Detail','pieces');
                        Object.assign(row,{piece_type:'Regular',width_cm:40,length_cm:60,qty:1,
                            notes:note},fields);
                    }
                    frm.refresh_field('pieces');
                    AlmdinaDcoRecovery.LocalCheckpoint.markDirty(frm);
                    const result=await AlmdinaDcoRecovery.LocalCheckpoint.flush(frm);
                    window.__p0ExtrasInput={status:'settled',ok:!!result?.ok,
                        error:result?.error?.code || null};
                })().catch(error=>window.__p0ExtrasInput={status:'rejected',error:String(error)});
            }""", {"fields": {"customer": fixture["customer"],
                "board_description": fixture["recovery_board"], "order_cutting_machine": "CNC",
                "board_width_cm": 122, "board_length_cm": 244,
                "default_edge_type": fixture["edge_type"], "edge_color": "P0 Extra edge",
                "board_rate_usd": 7,
                "cutting_cost_per_board_usd": 2}, "extras": extras})
            page.wait_for_function("window.__p0ExtrasInput?.status !== 'pending'", timeout=25000)
            evidence["checkpoint"] = page.evaluate("window.__p0ExtrasInput")
            assert evidence["checkpoint"]["status"] == "settled" and evidence["checkpoint"]["ok"]
            evidence["before"] = capture(page)
            verify_rows(evidence["before"]["rows"])
            page.evaluate("name => frappe.set_route('Form','Door Cutting Order',name)",
                          fixture["orders"]["B"]["name"])
            page.wait_for_function("name => cur_frm?.doc?.name === name",
                                   arg=fixture["orders"]["B"]["name"], timeout=45000)
            evidence["other_order"] = capture(page)
            assert not evidence["other_order"]["rows"]

            open_new(discovery=True)
            page.locator('[data-recovery-action="new"]:visible').click()
            page.wait_for_function("""() => !document.querySelector('.modal.show [data-recovery-action="new"]')""",
                                   timeout=15000)
            evidence["cancel"] = capture(page)
            assert not evidence["cancel"]["rows"]
            page.evaluate("name => frappe.set_route('Form','Door Cutting Order',name)",
                          fixture["orders"]["B"]["name"])
            page.wait_for_function("name => cur_frm?.doc?.name === name",
                                   arg=fixture["orders"]["B"]["name"], timeout=45000)
            open_new(discovery=True)
            page.locator('[data-recovery-action="continue"]:visible').first.click()
            page.wait_for_function("() => (cur_frm?.doc?.pieces || []).some(row => row.notes === 'P0-LINER')",
                                   timeout=15000)
            evidence["restore"] = capture(page)
            verify_rows(evidence["restore"]["rows"])
            assert evidence["restore"]["customer"] == fixture["customer"]
            assert evidence["restore"]["board"] == fixture["recovery_board"]
            assert evidence["restore"]["boardWidth"] == 122
            assert evidence["restore"]["boardLength"] == 244
            page.evaluate("""() => {
                const frm=cur_frm;
                window.__p0ExtrasSave={status:'pending'};
                Promise.resolve().then(()=>frm.save()).then(
                    value=>window.__p0ExtrasSave={status:'settled',name:frm.doc.name,
                        result:value === undefined ? 'undefined' : String(value).slice(0,100),
                        isNew:!!frm.is_new(),token:AlmdinaDocumentContext.capture(frm)},
                    error=>window.__p0ExtrasSave={status:'rejected',error:String(error)});
            }""")
            page.wait_for_function("window.__p0ExtrasSave?.status !== 'pending'", timeout=25000)
            evidence["native_save"] = page.evaluate("window.__p0ExtrasSave")
            assert evidence["native_save"]["status"] == "settled" and not evidence["native_save"]["isNew"]
            assert not evidence["native_save"]["name"].startswith("new-")
            assert evidence["native_save"]["token"]["generation"] == evidence["restore"]["token"]["generation"]
            evidence["saved"] = capture(page)
            verify_rows(evidence["saved"]["rows"])
            assert evidence["saved"]["customer"] == fixture["customer"]
            assert evidence["saved"]["board"] == fixture["recovery_board"]
            assert len({row["name"] for row in evidence["saved"]["rows"]}) == 3
            page.evaluate("name => frappe.set_route('Form','Door Cutting Order',name)",
                          fixture["orders"]["B"]["name"])
            page.wait_for_function("name => cur_frm?.doc?.name === name",
                                   arg=fixture["orders"]["B"]["name"], timeout=45000)
            assert not capture(page)["rows"]
        except Exception as exc:
            evidence["failure"] = repr(exc)
            evidence["failure_state"] = page.evaluate("""() => ({
                route:frappe.get_route?.(),name:cur_frm?.doc?.name,
                isNew:!!cur_frm?.is_new?.(),
                validated:frappe.validated, machine:cur_frm?.doc?.order_cutting_machine,
                edgeColor:cur_frm?.doc?.edge_color,pieces:cur_frm?.doc?.pieces?.length,
                checkpoint:AlmdinaDcoRecovery?.LocalCheckpoint?.snapshot(cur_frm) || null,
                modal:document.querySelector('.modal.show')?.innerText.slice(0,400) || null,
                tail:document.body.innerText.slice(-600)})""")
            page.screenshot(path=str(evidence_dir / "recovery-extras-failure.png"), full_page=True)
            raise
        finally:
            evidence_file.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            browser.close()
