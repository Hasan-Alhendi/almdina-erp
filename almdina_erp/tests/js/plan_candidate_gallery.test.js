"use strict";
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const root=path.resolve(__dirname,'../../');
const settings={packing_mode:'smart',cutting_machine_type:'CNC Router',kerf_mm:3,trim_margin_mm:0,optimization_time_limit_sec:10};
const candidates=['a','b'].map((id,index)=>({candidate_id:id,manufacturing_status:'Validated',summary:{settings,totals:{required_boards:index+1},quality:{largest_reusable_free_area_m2:.4+index},validation:{status:'Valid',needs_recalculation:false}}}));
const plan=id=>({sheets:[{id}],preview_candidate_id:id});
let previews=0, selects=0, commits=0, continuations=0, pendingSelect=null, receiptId='b';
let now=1000;
const frm={doctype:'Door Cutting Order',doc:{name:'DCO'}};
const window={cur_frm:frm,addEventListener(){},dispatchEvent(){},AlmdinaDocumentContext:{formIdentity:f=>f.doc.name},
 AlmdinaPlanWorkspaceAPI:{
  async preview(){previews++;return {preview_id:'p',order_name:'DCO',source_plan_name:'CP',source_plan_revision:1,source_plan_modified:'before',candidates,candidate_id:'a',plan:plan('a'),summary:candidates[0].summary,can_continue:true,search_budget_sec:10,expires_in_sec:60};},
  async selectCandidate(name,token,id){selects++;if(pendingSelect)return pendingSelect;return {preview_id:token,order_name:name,candidate_id:id,plan:plan(id),summary:candidates.find(c=>c.candidate_id===id).summary};},
  async continueSearch(){continuations++;return {...(await this.preview()),preview_id:'p2',search_round:1};},
  async commitPreview(name,token,id){commits++;return {exact_preview_commit:true,committed_preview_id:token,committed_candidate_id:receiptId,name,cutting_plan:'CP',plan_revision:1,plan_source_type:'System',plan_status:'Draft',...settings};}
 }};
const context=vm.createContext({window,frappe:{msgprint(){},utils:{escape_html:String}},CustomEvent:class{},Date:{now:()=>now},__:m=>m,console});
vm.runInContext(fs.readFileSync(path.join(root,'public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_preview_session.js'),'utf8'),context);
const owner=window.AlmdinaPlanPreviewSession;
async function firstPlanFlow(){
 const state={status:'ready',data:{plans:{},calculation_settings:settings},editing:false};
 const first={doctype:'Door Cutting Order',doc:{name:'FIRST',status:'Draft'},fields_dict:{},is_new:()=>false,trigger(){}};
 let previewCalls=0;
 const surface={cur_frm:first,addEventListener(){},requestAnimationFrame(){return 1;},
  AlmdinaPermissions:{canDocument:(_frm,capability)=>capability==='recalculate_plan'},
  AlmdinaPlanWorkspaceAPI:{}, // No bootstrap/save transport is needed.
  AlmdinaPlanWorkspaceState:{snapshot:()=>state,activePlan:()=>null,storeFor:()=>({beginEdit(seed){state.editing=true;state.draft=seed;}})},
  AlmdinaPlanWorkspacePresenterAdapter:{activeSettings:()=>settings},
  AlmdinaPlanPreviewSession:{reset(){},isBusy:()=>false,async preview(){previewCalls++;return true;}},
  AlmdinaPlanEditSessionUX:{syncPhaseLocks(){},canEditPlanSettings:()=>false,isEditing:()=>state.editing,startEditing(){assert.fail('settings-edit authority required for initial preview');}},
  AlmdinaTextBoardPlanUX:{preparePlanInputs:async()=>true}
 };
 const ctx=vm.createContext({window:surface,frappe:{ui:{form:{on(){}}},msgprint(){assert.fail('unexpected dialog');}},console,__:m=>m});
 for(const name of ['controls_ux','preview_edit_ux'])vm.runInContext(fs.readFileSync(path.join(root,`public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_${name}.js`),'utf8'),ctx);
 assert.equal(surface.AlmdinaPlanControlsUX.canCalculate(first),true);
 assert.equal(await surface.AlmdinaPlanControlsUX.runRecalculation(first),true);
 assert.equal(previewCalls,1);assert.equal(state.editing,true);
 assert.equal(surface.AlmdinaPlanEditSessionUX.canEditPlanSettings(first),false,'physical controls remain locked');
}
async function run(){
 assert.equal(await owner.preview(frm,settings),true);
 assert.equal(await owner.selectCandidate(frm,'b'),true);
 assert.equal(owner.previewPlan(frm).sheets[0].id,'b');
 assert.equal(previews,1);assert.equal(selects,1);assert.equal(commits,0);
 assert.equal(await owner.selectCandidate(frm,'forged'),false);
 assert.equal((await owner.commit(frm)).committed_candidate_id,'b');
 await owner.preview(frm,settings);await owner.selectCandidate(frm,'b');receiptId='a';
 assert.equal(await owner.commit(frm),false,'wrong candidate receipt must never be accepted');
 await owner.preview(frm,settings);assert.equal(await owner.continueSearch(frm),true);assert.equal(continuations,1);assert.equal(owner.snapshot(frm).previewId,'p2');
 owner.reset(frm);assert.equal(owner.isReady(frm),false);
 await owner.preview(frm,settings);now+=61000;assert.equal(owner.isCommittable(frm),false,'expired preview cannot save');
 owner.reset(frm);await owner.preview(frm,settings);
 let resolve;pendingSelect=new Promise(r=>{resolve=r;});const request=owner.selectCandidate(frm,'b');
 assert.equal(owner.isCommittable(frm),false,'selection request locks Save');
 owner.invalidate(frm);pendingSelect=null;
 resolve({preview_id:'p',order_name:'DCO',candidate_id:'b',plan:plan('b'),summary:candidates[1].summary});
 assert.equal(await request,false);assert.equal(owner.isBusy(frm),false,'invalidating in-flight selection must unlock the next preview');
 await owner.preview(frm,settings);
 pendingSelect=Promise.resolve({preview_id:'p',order_name:'DCO',candidate_id:'b',plan:plan('a'),summary:candidates[1].summary});
 await assert.rejects(owner.selectCandidate(frm,'b'),/Invalid cutting-plan candidate response/);
 pendingSelect=null;assert.equal(owner.isCommittable(frm),false,'mismatched snapshot identity fails closed');
 await firstPlanFlow();
 console.log('Candidate selection, exact receipt, continuation, expiry and stale response tests passed');
}
run().catch(e=>{console.error(e);process.exitCode=1;});
