"""Evidence collection on an ephemeral, version-pinned Frappe Desk site."""

import json
import os
from pathlib import Path
from urllib.parse import parse_qs

from playwright.sync_api import sync_playwright


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
    with sync_playwright() as playwright:
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

    with sync_playwright() as playwright:
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
                # Capture popup writes and hold the real renderer at its async identity boundary.
                page.evaluate("""() => {
                    window.__p0PrintWrites=[];
                    window.__p0OldOpen=window.open;
                    window.open=()=>({document:{open(){},write(html){window.__p0PrintWrites.push(html)},close(){}},close(){}});
                    window.__p0OldIdentity=AlmdinaFactoryPrintIdentity;
                    window.AlmdinaFactoryPrintIdentity={...window.__p0OldIdentity,
                        get:()=>new Promise(resolve=>window.__p0ResolveIdentity=resolve)};
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
                page.wait_for_function("!!window.__p0ResolveIdentity", timeout=10000)
                before = page.evaluate("""() => ({...window.__p0PrintStart,
                    writes:window.__p0PrintWrites.length})""")
                # Route change while identity lookup is pending is a real Desk navigation.
                state_a_during = route(a["name"])
                page.evaluate("""() => window.__p0ResolveIdentity({})""")
                page.wait_for_function("window.__p0PrintWrites.length >= 2", timeout=10000)
                html = page.evaluate("window.__p0PrintWrites.at(-1)")
                (evidence_dir / "final-print.html").write_text(html, encoding="utf-8")
                result = page.evaluate("""async () => await window.__p0PrintResult""")
                return {"method": "controlled A geometry; renderer started for immutable B identity, then real B to A Desk route during identity await",
                        "before": before, "b_before_print": state_b_print,
                        "a_during": state_a_during, "result": result,
                        "html_file": "final-print.html", "html_checks": {
                            "dco_a": a["name"] in html, "dco_b": b["name"] in html,
                            "board_a": a["board"] in html, "board_b": b["board"] in html,
                            "geometry_a": "P0-A-GEOMETRY" in html,
                            "plan_name": "P0-PLAN-A" in html,
                            "revision": "P0-REV-A" in html,
                            "header": "dco-print" in html}}

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
    """Separate real persisted Plan response from controlled cross-order injection."""
    fixture = json.loads(Path(os.environ["P0_FIXTURE_PATH"]).read_text())
    evidence_dir = Path(os.environ["P0_EVIDENCE_DIR"])
    saved_plan = json.loads((evidence_dir / "saved-plan-fixture.json").read_text())
    a, b = fixture["orders"]["A"], fixture["orders"]["B"]
    evidence = {"saved_plan": {key: value for key, value in saved_plan.items()
                               if key != "first_piece"}, "orders": fixture["orders"]}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(locale="en-US")
            _login(page, fixture)
            held = []

            def delay_actual_a_plan(route):
                request = route.request
                if a["name"] in (request.url + (request.post_data or "")):
                    held.append((route, None))
                    response = route.fetch()
                    held[-1] = (route, response)
                    page.evaluate("window.__p0PlanHeld = true")
                else:
                    route.continue_()

            page.route("**/api/method/*get_plan_workspace_snapshot*", delay_actual_a_plan)
            page.evaluate("name => { frappe.set_route('Form','Door Cutting Order',name); }", a["name"])
            page.wait_for_function("name => cur_frm?.doc?.name === name", arg=a["name"], timeout=45000)
            page.wait_for_function("() => AlmdinaPlanWorkspaceState?.canView(cur_frm)", timeout=15000)
            a_identity = page.evaluate("""() => ({name:cur_frm.doc.name,
                identity:AlmdinaDocumentContext.formIdentity(cur_frm),
                generation:AlmdinaDocumentContext.capture(cur_frm).generation,
                modified:cur_frm.doc.modified})""")
            page.evaluate("() => { window.__p0FrmA=cur_frm; }")
            # Start the production Plan state transport while A is visible, hold
            # its *real* HTTP response, then navigate B before releasing it.
            with page.expect_request(lambda request: "get_plan_workspace_snapshot" in request.url
                                     and a["name"] in (request.url + (request.post_data or "")),
                                     timeout=15000):
                page.evaluate("() => { AlmdinaPlanWorkspaceState.load(cur_frm,{force:true}); }")
            page.wait_for_function("window.__p0PlanHeld === true", timeout=15000)
            assert held and held[0][1], "No real A Plan API response was intercepted"
            payload = held[0][1].json().get("message")
            assert payload and payload.get("order_name") == a["name"], payload
            row = payload.get("plans", {}).get("system_draft") or {}
            assert row.get("name") == saved_plan["name"] and row.get("revision") == saved_plan["revision"], row
            evidence["actual_api"] = {"order_name": payload["order_name"],
                                      "plan_name": row["name"], "revision": row["revision"],
                                      "snapshot_json": row.get("snapshot_json")}

            page.evaluate("name => { frappe.set_route('Form','Door Cutting Order',name); }", b["name"])
            page.wait_for_function("name => cur_frm?.doc?.name === name", arg=b["name"], timeout=45000)
            before_release = page.evaluate("""() => ({sameFrm:cur_frm===window.__p0FrmA,
                name:cur_frm.doc.name,board:cur_frm.doc.board_description,
                state:AlmdinaPlanWorkspaceState.snapshot(cur_frm)})""")
            held[0][0].fulfill(response=held[0][1])
            page.unroute("**/api/method/*get_plan_workspace_snapshot*", delay_actual_a_plan)
            page.wait_for_function("() => AlmdinaPlanWorkspaceState.snapshot(cur_frm)?.status !== 'loading'",
                                   timeout=10000)
            evidence["natural_late_response"] = {"before": before_release,
                "after": page.evaluate("""() => ({name:cur_frm.doc.name,
                    board:cur_frm.doc.board_description,
                    state:AlmdinaPlanWorkspaceState.snapshot(cur_frm)})""")}

            # Controlled identity-defense probe, using the unmodified response
            # returned by the real server for a saved A plan.
            page.get_by_text("Cutting Plan", exact=True).first.click()
            page.evaluate("""async () => {
                await AlmdinaDcoWorkspaceAssetRegistry.ensure('plan');
                await AlmdinaPlanWorkspaceState.load(cur_frm,{force:true});
            }""")
            evidence["controlled_projection"] = page.evaluate("""args => {
                const frm=cur_frm, store=AlmdinaPlanWorkspaceState.storeFor(frm);
                store.reset(args.identity);
                const requestId=store.beginLoad(args.identity);
                const accepted=store.resolveLoad(args.identity,requestId,args.payload);
                const projected=AlmdinaPlanWorkspacePresenterAdapter.project(frm);
                return {accepted,projected,name:frm.doc.name,
                    board:frm.doc.board_description,
                    plan:AlmdinaPlanWorkspaceState.planForTab(frm,'System')?.name,
                    modelPlan:frm.doc.system_plan_json};
            }""", {"identity": a_identity["identity"], "payload": payload})
            evidence["print_button_state"] = page.evaluate("""() => {
                AlmdinaDoorCuttingPlanUX.renderActions(cur_frm);
                return {permission:AlmdinaPermissions?.canDocument(cur_frm,'print_cutting_plan'),
                    actionField:!!cur_frm.fields_dict.plan_control_actions,
                    buttons:document.querySelectorAll('.dco-print-cutting-plan').length};
            }""")
            page.evaluate("""() => {
                window.__p0PrintWrites=[];
                window.open=()=>({document:{open(){},write(html){__p0PrintWrites.push(html)},close(){}},close(){}});
                const oldIdentity=AlmdinaFactoryPrintIdentity;
                window.AlmdinaFactoryPrintIdentity={...oldIdentity,
                    get:()=>new Promise(resolve=>window.__p0ResolveIdentity=resolve)};
                const renderer=AlmdinaCuttingPlanRender;
                const original=renderer.print;
                renderer.print=(frm,plan)=>{
                    window.__p0PrintedSource={dco:frm.doc.name,
                        planName:AlmdinaPlanWorkspaceState.planForTab(frm,'System')?.name,
                        revision:AlmdinaPlanWorkspaceState.planForTab(frm,'System')?.revision};
                    window.__p0PrintResult=original(frm,plan);
                    return window.__p0PrintResult;
                };
            }""")
            button = page.locator(".dco-print-cutting-plan:visible").first
            if button.count():
                button.click()
                evidence["print_invocation"] = "clicked visible .dco-print-cutting-plan on B"
            else:
                page.evaluate("() => AlmdinaPlanTabsUX.printActivePlan(cur_frm)")
                evidence["print_invocation"] = "production PlanTabsUX handler; B has no visible print action"
            page.wait_for_function("!!window.__p0ResolveIdentity", timeout=10000)
            evidence["print_start"] = page.evaluate("window.__p0PrintedSource")
            page.evaluate("name => { frappe.set_route('Form','Door Cutting Order',name); }", a["name"])
            page.wait_for_function("name => cur_frm?.doc?.name === name", arg=a["name"], timeout=45000)
            page.evaluate("window.__p0ResolveIdentity({})")
            page.wait_for_function("window.__p0PrintWrites.length >= 2", timeout=10000)
            html = page.evaluate("window.__p0PrintWrites.at(-1)")
            (evidence_dir / "saved-plan-final-print.html").write_text(html, encoding="utf-8")
            evidence["print_result"] = page.evaluate("async () => await window.__p0PrintResult")
            a_piece = saved_plan["first_piece"]
            a_geometry = f"{int(float(a_piece['w']) * 10)} × {int(float(a_piece['h']) * 10)}"
            b_geometry = f"{b['width_cm'] * 10} × {b['length_cm'] * 10}"
            evidence["html_checks"] = {"title_b": f"خطة قص - {b['name']}" in html,
                "title_a": f"خطة قص - {a['name']}" in html,
                "board_a": a["board"] in html, "board_b": b["board"] in html,
                "geometry_a": a_geometry in html, "geometry_b": b_geometry in html,
                "plan_name_rendered": saved_plan["name"] in html,
                "revision_rendered": None,
                "revision_note": "Renderer has no plan revision field; compare API/source identity"}
            evidence["final_html_file"] = "saved-plan-final-print.html"
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


def test_recovery_new_saved_intersection():
    """Observe the real NEW→Saved boundary without mutating Recovery code."""
    fixture = json.loads(Path(os.environ["P0_FIXTURE_PATH"]).read_text())
    evidence_dir = Path(os.environ["P0_EVIDENCE_DIR"])
    evidence = {"scope": "Develop NEW checkpoint, Start New cancel, Continue restore, Native Save, EDIT and Plan/Cost state"}

    def mark_step(name):
        evidence["last_completed_step"] = name
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / "recovery-intersection.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(locale="en-US")
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
                const name=frappe.model.make_new_doc_and_get_name('Door Cutting Order');
                frappe.set_route('Form','Door Cutting Order',name);
            }""")
            page.wait_for_function("() => cur_frm?.doctype === 'Door Cutting Order' && !!cur_frm.is_new()",
                                   timeout=45000)
            page.wait_for_function("() => !!AlmdinaDcoRecovery?.LocalCheckpoint?.snapshot(cur_frm)",
                                   timeout=15000)
            evidence["new_before_save"] = page.evaluate("""() => ({
                identity:AlmdinaDocumentContext.formIdentity(cur_frm),
                generation:AlmdinaDocumentContext.capture(cur_frm)?.generation,
                isNew:!!cur_frm.is_new(),
                recovery:AlmdinaDcoRecovery?.LocalCheckpoint?.snapshot(cur_frm) || null,
                edit:AlmdinaDcoEditSessionCoordinator?.snapshot(cur_frm) || null})""")
            mark_step("NEW_Form_open")
            evidence["input"] = page.evaluate("""async args => {
                const frm=cur_frm;
                for (const [field,value] of Object.entries(args.fields)) await frm.set_value(field,value);
                const piece=frappe.model.add_child(frm.doc,'Door Cutting Order Detail','pieces');
                piece.piece_type='Regular'; piece.width_cm=31; piece.length_cm=62; piece.qty=1;
                frm.refresh_field('pieces');
                AlmdinaDcoRecovery?.LocalCheckpoint?.markDirty(frm);
                return {name:frm.doc.name,board:frm.doc.board_description,
                    pieces:frm.doc.pieces.map(row=>({name:row.name,width_cm:row.width_cm})),
                    recovery:AlmdinaDcoRecovery?.LocalCheckpoint?.snapshot(frm) || null};
            }""", {"fields": {"customer": fixture["customer"],
                "board_description": fixture["recovery_board"],
                "board_width_cm": 122, "board_length_cm": 244,
                "default_edge_type": fixture["edge_type"], "edge_color": "P0 Recovery edge",
                "board_rate_usd": 7, "cutting_cost_per_board_usd": 2}})
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
                isNew:!!cur_frm.is_new()})""")
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
                recovery:AlmdinaDcoRecovery.LocalCheckpoint.snapshot(cur_frm)})""")
            mark_step("draft_restored")
            page.evaluate("""() => {
                const frm=cur_frm;
                window.__p0NativeSave={status:'pending',startName:frm.doc.name};
                Promise.resolve().then(()=>frm.save()).then(
                    ()=>window.__p0NativeSave={status:'settled',ok:!frm.is_new(),
                        name:frm.doc.name,board:frm.doc.board_description,
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
            mark_step("native_save_settled")
            if evidence["native_save"]["ok"]:
                saved = evidence["native_save"]["name"]
                page.evaluate("name => { frappe.set_route('Form','Door Cutting Order',name); }",
                              fixture["orders"]["B"]["name"])
                page.wait_for_function("name => cur_frm?.doc?.name === name",
                                       arg=fixture["orders"]["B"]["name"], timeout=45000)
                page.evaluate("name => { frappe.set_route('Form','Door Cutting Order',name); }", saved)
                page.wait_for_function("name => cur_frm?.doc?.name === name", arg=saved, timeout=45000)
                evidence["saved_reopen"] = page.evaluate("""() => ({name:cur_frm.doc.name,
                    board:cur_frm.doc.board_description,
                    edit:AlmdinaDcoEditSessionCoordinator?.snapshot(cur_frm) || null,
                    recovery:AlmdinaDcoRecovery?.LocalCheckpoint?.snapshot(cur_frm) || null,
                    plan:AlmdinaPlanWorkspaceState.snapshot(cur_frm),
                    cost:AlmdinaCostWorkspaceState.snapshot(cur_frm)})""")
        except Exception as exc:
            evidence["failure"] = repr(exc)
            evidence["browser_state"] = page.evaluate("""() => ({route:frappe.get_route?.(),
                current:cur_frm?.doc?.name,isNew:!!cur_frm?.is_new?.(),
                modal:document.querySelector('.modal.show')?.innerText.slice(0,600) || null,
                body:document.body.innerText.slice(-700)})""")
            page.screenshot(path=str(evidence_dir / "recovery-failure.png"), full_page=True)
            raise
        finally:
            evidence_dir.mkdir(parents=True, exist_ok=True)
            (evidence_dir / "recovery-intersection.json").write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            browser.close()
