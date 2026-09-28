import {test,expect,Browser,BrowserContext} from '@playwright/test';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {randomUUID} from 'node:crypto';
import {execFileSync} from 'node:child_process';
const project='a0000000-0000-4000-8000-000000000002';
const base='/api/v1/projects/'+project;
const accounts=readFileSync('.local/demo-accounts.md','utf8');
const ids=JSON.parse(readFileSync('.local/demo-identities.json','utf8'));
async function login(browser:Browser,name:string){
 const context=await browser.newContext();const page=await context.newPage();
 await page.goto('/');await page.getByRole('link',{name:'Sign in with Keycloak'}).click();
 await page.locator('#username').fill(name);
 const password=accounts.split('\n').find(l=>l.startsWith('- '+name+':'))!.split('`')[1];
 await page.locator('#password').fill(password);await page.locator('#kc-login').click();
 await expect(page.getByRole('button',{name:'Sign out'})).toBeVisible();return context;
}
async function call(ctx:BrowserContext,path:string,method='GET',body?:unknown,version?:number,key?:string){
 const cookies=await ctx.cookies();const csrf=cookies.find(c=>c.name==='anvil_csrf')?.value||'';
 const r=await ctx.request.fetch(base+path,{method,data:body,headers:{Origin:'http://127.0.0.1:3202','X-CSRF-Token':csrf,'Idempotency-Key':key||randomUUID(),...(version?{'If-Match':String(version)}:{})}});
 const result=await r.json();expect(r.status(),JSON.stringify(result)).toBeLessThan(300);return result.data;
}
async function transition(ctx:BrowserContext,col:string,r:any,action:string,body={}){
 const latest=await call(ctx,`/${col}/${r.id}`);return call(ctx,`/${col}/${r.id}/${action}`,'POST',body,latest.row_version);
}
async function approve(ctx:BrowserContext,col:string,r:any,purpose:string){return transition(ctx,col,r,'decisions',{purpose,decision:'approve',rationale:'Independent synthetic fixture review for local pipeline verification only.'});}

test('real OIDC, qualified six-episode fixture journey, independent reviews and isolation',async({browser})=>{
 const contexts:Record<string,BrowserContext>={};
 for(const name of ['researcher','advisor','product-owner','data-engineer','reviewer-1','reviewer-2','adjudicator','sales','outsider'])contexts[name]=await login(browser,name);
 const R=contexts.researcher,A=contexts.advisor,P=contexts['product-owner'],D=contexts['data-engineer'];
 const objective=await call(R,'/objectives','POST',{title:'Synthetic commercial-constraint diagnostic '+Date.now(),origin:'adi_initiated',entry_type:'capability',hypothesis:'Supplied hard constraints are preserved in recommendations.',business_context:'Original synthetic fixture exercise; no measured model performance.',measurement_plan:'Three original cases; two deterministic candidates; one attempt each; anchored rubric and critical overrides; descriptive results only.',researcher_id:ids.researcher,advisor_id:ids.advisor,product_owner_id:ids['product-owner']});
 await transition(R,'objectives',objective,'submit');await approve(R,'objectives',objective,'research');await approve(A,'objectives',objective,'advisor');await approve(P,'objectives',objective,'scope');
 const imp={case_ids:['MKT-001','FIN-001','STR-001'],reviewer_id:ids['reviewer-1'],advisor_id:ids.advisor};
 const cases=await call(D,'/fixtures/import','POST',imp);await call(D,'/fixtures/import','POST',imp);
 expect((await call(D,'/cases?limit=100')).filter((c:any)=>c.content.source_origin==='original_synthetic_fixture').length).toBe(3);
 for(const source of cases)await call(P,`/cases/${source.id}/rights`,'POST',{operation:'managed_evaluation',destination:'local_fixture',status:'approved',evidence:'Reviewed original synthetic fixture rights for local pipeline testing only; no external processing.'},source.row_version);
 for(const rubric of await call(D,'/rubrics'))if(rubric.lifecycle==='draft'){
  await transition(D,'rubrics',rubric,'submit');await approve(contexts['reviewer-1'],'rubrics',rubric,'content');await approve(A,'rubrics',rubric,'calibration');
 }
 for(const task of await call(D,'/tasks'))if(task.lifecycle==='draft'){
  await transition(D,'tasks',task,'submit');await approve(contexts['reviewer-1'],'tasks',task,'content');await approve(A,'tasks',task,'research');await transition(D,'tasks',task,'publish');
 }
 const tasks=await call(R,'/tasks');expect(tasks.length).toBe(3);
 const suite=await call(R,'/suites','POST',{title:'Three-case original synthetic suite',objective_revision_id:objective.current_revision_id,task_revision_ids:tasks.map((t:any)=>t.current_revision_id),selection_method:'All three supplied original fixtures.',exposure_note:'Known development fixtures; no generalization or faculty validation.',advisor_id:ids.advisor,planned_source_count:200});
 await transition(R,'suites',suite,'submit');await approve(A,'suites',suite,'technical');await transition(R,'suites',suite,'freeze');
 const protocol=await call(R,'/protocols','POST',{title:'Deterministic two-candidate pilot',objective_revision_id:objective.current_revision_id,suite_revision_id:suite.current_revision_id,candidates:['fixture-correct','fixture-constraint-blind'],reviewer_ids:[ids['reviewer-1'],ids['reviewer-2']],adjudicator_id:ids.adjudicator,advisor_id:ids.advisor,comparison_policy:'Same frozen actor inputs, descriptive fixture pipeline checks; no model ranking.',pass_policy:'Rubric threshold and critical override; all pilot episodes independently double reviewed.'});
 await transition(R,'protocols',protocol,'submit');await approve(A,'protocols',protocol,'technical');
 const run=await call(R,'/runs','POST',{protocol_revision_id:protocol.current_revision_id});
 const launchKey=randomUUID();await call(R,`/runs/${run.id}/launch`,'POST',{},run.row_version,launchKey);await call(R,`/runs/${run.id}/launch`,'POST',{},run.row_version,launchKey);
 await expect.poll(async()=>{const r=await call(R,`/runs/${run.id}`);return r.episodes.filter((e:any)=>e.state==='awaiting_review').length;},{timeout:30000}).toBe(6);
 let before=await call(R,`/runs/${run.id}`);expect(before.episodes.every((e:any)=>e.invocation_count===1)).toBeTruthy();
 await expect.poll(async()=> (await call(R,'/sales-kits')).some((k:any)=>k.content.run_id===run.id&&k.content.stage==='provisional'),{timeout:30000}).toBeTruthy();
 const provisional=(await call(R,'/sales-kits')).find((k:any)=>k.content.run_id===run.id&&k.content.stage==='provisional');
 expect(provisional.content.facts.mean_score).toBeNull();expect(provisional.content.label).toContain('PROVISIONAL');
 execFileSync('python3',['scripts/local.py','worker-restart']);
 for(const episode of before.episodes){
  for(const name of ['reviewer-1','reviewer-2']){
   const detail=await call(contexts[name],`/reviews/${episode.id}`);
   expect(JSON.stringify(detail)).not.toContain('candidate_key');expect(detail.submitted_assessments).toBeUndefined();
   const output=JSON.parse(detail.output);
   const bad=output.constraint_checks.includes('despite')||output.constraint_checks.includes('even though');
   const scores={R1:4,R2:bad?0:4,R3:4};
   const quote='"selected_option": "'+output.selected_option+'"';
   await call(contexts[name],`/episodes/${episode.id}/assessments`,'POST',{scores,critical:bad?detail.rubric.critical_rules:[],evidence:{R1:quote,R2:quote,R3:quote},rationale:'Scripted independent synthetic judgment; fixture verification only.'},detail.row_version);
  }
 }
 await expect.poll(async()=>(await call(R,`/runs/${run.id}`)).state,{timeout:30000}).toBe('reviewed');
 const final=await call(R,`/runs/${run.id}`);expect(final.episodes.filter((e:any)=>e.outcome==='pass').length).toBe(3);expect(final.episodes.reduce((s:number,e:any)=>s+Number(e.score),0)/6).toBe(85);expect(final.episodes.every((e:any)=>e.invocation_count===1)).toBeTruthy();
 for(const source of cases)await call(P,`/cases/${source.id}/rights`,'POST',{operation:'report_sharing',destination:'internal_fixture',status:'approved',evidence:'Reviewed synthetic aggregate-only internal draft sharing. No raw case redistribution or external customer delivery.'},source.row_version);
 const report=await call(R,'/reports','POST',{title:'Reviewed synthetic diagnostic',run_id:run.id,finding_revision_ids:[],advisor_id:ids.advisor,reviewer_id:ids['reviewer-1'],product_owner_id:ids['product-owner'],audience:'internal_fixture'});
 await transition(R,'reports',report,'submit');await approve(A,'reports',report,'technical');await approve(contexts['reviewer-1'],'reports',report,'domain');await approve(P,'reports',report,'audience');await approve(P,'reports',report,'release');
 await expect.poll(async()=> (await call(R,'/sales-kits')).some((k:any)=>k.content.report_revision_id===report.current_revision_id&&k.lifecycle==='approved'),{timeout:30000}).toBeTruthy();
 await transition(R,'reports',report,'build');
 mkdirSync('artifacts/test-runs',{recursive:true});
 for(const name of ['sales-kit.pdf','sales-kit.html','evidence.zip','email-draft.txt']){const download=await contexts.sales.request.get(base+`/reports/${report.id}/download/${name}`);expect(download.status()).toBe(200);writeFileSync('artifacts/test-runs/'+name,await download.body());}
 const graph=await call(R,'/diagnostics');expect(graph.nodes.length).toBeGreaterThan(0);expect(graph.edges.length).toBeGreaterThan(0);
 const denied=await contexts.sales.request.get(base+'/rubrics');expect(denied.status()).toBe(403);
 const outsider=await contexts.outsider.request.get(base+'/objectives/'+objective.id);expect(outsider.status()).toBe(404);
 const csrf=await R.request.post(base+'/objectives',{data:{}});expect(csrf.status()).toBe(403);
 const page=await R.newPage();await page.goto('/p/'+project+'/objectives');await expect(page.getByRole('heading',{name:'Research objectives',exact:true})).toBeVisible();
 mkdirSync('artifacts/test-runs',{recursive:true});await page.screenshot({path:'artifacts/test-runs/objectives.png',fullPage:true});
 writeFileSync('artifacts/test-runs/journey.json',JSON.stringify({run_id:run.id,objective,suite,protocol,report,episodes:final.episodes},null,2));
 const disputedRun=await call(R,'/runs','POST',{protocol_revision_id:protocol.current_revision_id});
 await call(R,`/runs/${disputedRun.id}/launch`,'POST',{},disputedRun.row_version);
 await expect.poll(async()=>(await call(R,`/runs/${disputedRun.id}`)).episodes.filter((e:any)=>e.state==='awaiting_review').length,{timeout:30000}).toBe(6);
 const episode=(await call(R,`/runs/${disputedRun.id}`)).episodes[0];
 for(const [name,value] of [['reviewer-1',4],['reviewer-2',0]] as const){
  const detail=await call(contexts[name],`/reviews/${episode.id}`);
  expect(detail.submitted_assessments).toBeUndefined();
  const quote='"selected_option": "'+JSON.parse(detail.output).selected_option+'"';
  await call(contexts[name],`/episodes/${episode.id}/assessments`,'POST',{scores:{R1:value,R2:value,R3:value},critical:[],evidence:{R1:quote,R2:quote,R3:quote},rationale:'Deliberate synthetic disagreement to verify independent adjudication.'},detail.row_version);
 }
 const disputed=await call(contexts.adjudicator,`/reviews/${episode.id}`);
 expect(disputed.state).toBe('disputed');expect(disputed.submitted_assessments).toHaveLength(2);
 const quote='"selected_option": "'+JSON.parse(disputed.output).selected_option+'"';
 await call(contexts.adjudicator,`/episodes/${episode.id}/adjudicate`,'POST',{scores:{R1:4,R2:4,R3:4},critical:[],evidence:{R1:quote,R2:quote,R3:quote},rationale:'Independent third identity resolves deliberate fixture dispute.'},disputed.row_version);
 await expect.poll(async()=>(await call(R,`/runs/${disputedRun.id}`)).episodes.find((e:any)=>e.id===episode.id).state,{timeout:30000}).toBe('finalized');
 const cancelTarget=await call(R,`/runs/${disputedRun.id}`);
 await call(R,`/runs/${disputedRun.id}/cancel`,'POST',{},cancelTarget.row_version);
 const cancelled=await call(R,`/runs/${disputedRun.id}`);
 expect(cancelled.state).toBe('cancelled');expect(cancelled.episodes.filter((e:any)=>e.state==='cancelled')).toHaveLength(5);
 expect(cancelled.episodes.every((e:any)=>e.invocation_count===1)).toBeTruthy();
 for(const ctx of Object.values(contexts))await ctx.close();
});
