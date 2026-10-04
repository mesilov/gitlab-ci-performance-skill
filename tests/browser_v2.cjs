const {chromium}=require(process.env.CI_REPORT_PLAYWRIGHT||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const{pathToFileURL,fileURLToPath}=require('node:url');
const url=process.argv[2],out=process.argv[3];
if(!url||!out)throw Error('Usage: browser_v2.cjs FILE_URL OUTPUT_DIRECTORY');
(async()=>{fs.mkdirSync(out,{recursive:true});const browser=await chromium.launch({channel:process.env.CI_REPORT_BROWSER_CHANNEL==='chromium'?undefined:(process.env.CI_REPORT_BROWSER_CHANNEL||'chrome'),headless:true});
try{const context=await browser.newContext({offline:true,viewport:{width:1280,height:960}}),page=await context.newPage(),errors=[],requests=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(['warning','error'].includes(m.type()))errors.push(m.text());});page.on('request',r=>requests.push(r.url()));await page.goto(url);
const R=await page.locator('#report-data').evaluate(e=>JSON.parse(e.textContent));assert.equal(R.schema_version,'2.0.0');assert.equal(await page.locator('h1').count(),1);assert.equal(await page.locator('#jobs button').count(),R.job_types.length);
// Reviewed visual hierarchy must survive the canonical renderer and clean installs.
const ru=await page.locator('html').getAttribute('lang')==='ru';
assert.equal(await page.locator('h1').innerText(),ru?'Как работает CI':'How CI is performing');
assert.equal(await page.locator('body').evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(255, 255, 255)');
assert.equal(await page.locator('#priority-lead').count(),1,'reference priority panel starts with a short conclusion');
assert.equal(await page.locator('.priority-panel').evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(246, 247, 249)','reference priority panel has a gray surface');
assert.equal(await page.locator('#findings').evaluate(e=>getComputedStyle(e).gridTemplateColumns.split(' ').length),1,'reference priorities are vertical numbered rows');
assert.equal(await page.locator('#priority-method').evaluate(e=>e.open),false,'technical limitations are collapsed');
for(const item of await page.locator('#findings .priority').all()){
 assert.equal(await item.locator('.priority-evidence button').evaluate(e=>getComputedStyle(e).borderStyle),'none','evidence navigation is an inline link');
 const heading=await item.locator('h3').boundingBox(),cost=await item.locator('.cost').boundingBox();assert.ok(cost.x>heading.x&&Math.abs(cost.y-heading.y)<15,'category cost sits beside its action title');
}
assert.equal(await page.locator('#attempt-history').evaluate(e=>e.open),false,'history is collapsed initially');
assert.equal(await page.locator('#detail').isVisible(),true,'latest attempt is selected initially');
assert.equal(await page.locator('#jobs [data-baseline]').count(),R.job_types.length);
assert.equal(await page.locator('#jobs [data-outcomes]').count(),R.job_types.length);
await page.locator('#attempt-history summary').click();
for(const jt of R.job_types){
assert.equal(await page.locator(`[data-type="${jt.id}"]`).getAttribute('data-latest-seconds'),String(R.attempts.find(a=>a.id===jt.latest_attempt_id).timing.total.value_seconds));
assert.equal(await page.locator(`[data-baseline="${jt.id}"]`).getAttribute('data-seconds'),String(jt.baseline.metrics.total.median_seconds));
await page.locator(`[data-type="${jt.id}"]`).click();for(const size of ['32','64']){await page.locator('#size').selectOption(size);let w=R.windows.find(w=>w.type_id===jt.id&&w.size===Number(size)&&w.page===0);await verifyWindow(w);if(size==='32'&&w.has_older){await page.locator('#older').click();w=R.windows.find(v=>v.id===w.older_window_id);await verifyWindow(w);await page.locator('#latest').click();}}
}
async function verifyWindow(w){
assert.match(await page.locator('#detail-title').innerText(),new RegExp('#'+w.attempt_ids[0]+' '),'latest attempt selected in a new window');
const firstBar=page.locator('#chart [data-attempt]').first();await firstBar.focus();await page.keyboard.press('Enter');
assert.equal(await firstBar.getAttribute('aria-pressed'),'true','keyboard selects chart attempt');
assert.equal(await page.locator('#chart .axis-unit').textContent(),w.display_unit==='minutes'?(ru?'мин':'min'):(ru?'с':'s'));
assert.equal(await page.locator('#history tr').count(),w.attempt_ids.length);assert.equal(await page.locator('#chart [data-attempt]').count(),w.attempt_ids.length);for(const metric of ['queue','execution','total'])assert.equal(await page.locator(`[data-metric="${metric}"]`).getAttribute('data-seconds'),String(w.findings.metrics[metric].median_seconds));
for(const id of w.attempt_ids){await page.locator(`#history tr[data-attempt="${id}"] button`).click();assert.match(await page.locator('#detail-title').innerText(),new RegExp('#'+id+' '));const a=R.attempts.find(a=>a.id===id),nodes=a.trace?.evidence||[],images=nodes.filter(n=>n.kind==='image'),groups=images.length?images:nodes.filter(n=>n.kind==='command'||(n.kind==='operation'&&!n.parent_id));assert.equal(await page.locator('#image-timeline [data-evidence]').count(),groups.length);
for(const shown of await page.locator('#evidence [data-evidence]').evaluateAll(rows=>rows.map(e=>({id:e.dataset.evidence,parent:e.dataset.parent,seconds:e.dataset.seconds})))){const n=nodes.find(n=>n.id===shown.id);assert.ok(n,'only saved evidence is rendered');assert.equal(shown.parent,n.parent_id||'','saved parent relationship preserved');assert.equal(shown.seconds,String(n.timing.duration_seconds));}
for(const text of await page.locator('#attempt-detail .timing dd').allTextContents())if(text!=='—')assert.ok(text.endsWith(' '+(w.display_unit==='minutes'?(ru?'мин':'min'):(ru?'с':'s'))),'detail uses selected window unit');for(const k of ['queue','execution','total'])assert.equal(await page.locator(`#history tr[data-attempt="${id}"] [data-timing="${k}"]`).getAttribute('data-seconds'),String(a.timing[k].value_seconds));}
for(const code of w.findings.priority_codes){const c=w.findings.categories.find(c=>c.code===code),item=page.locator(`[data-category="${code}"]`);assert.equal(Number(await item.getAttribute('data-seconds')),c.median_seconds);assert.match(await item.locator('.priority-evidence').innerText(),new RegExp('^'+c.known+' '+(ru?'успешных джоб с замерами':'successful jobs with measurements')));if(c.missing)assert.match(await item.locator('.priority-evidence').innerText(),new RegExp((ru?'Нет измерений ':'Not measured ')+c.missing));if(c.representative){await item.locator('button').click();assert.equal(await page.evaluate(()=>document.activeElement.matches('#detail-title,#step-evidence-title,.evidence-button')),true,'inspect action focuses its destination');assert.match(await page.locator('#detail-title').innerText(),new RegExp('#'+c.representative.attempt_id+' '));if(c.representative.evidence_id)assert.equal(await page.locator('#step-evidence-block').getAttribute('data-selected-evidence'),c.representative.evidence_id);}}
}
for(const width of [320,375,1280])for(const theme of ['light','dark']){
 await page.setViewportSize({width,height:960});await page.emulateMedia({colorScheme:theme});await page.goto(url);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`${width}px ${theme} overflow`);
 // ResizeObserver can replace the SVG between locator resolution and evaluation.
 await page.waitForFunction(()=>{const e=document.querySelector('#chart .axis-unit');return e?.getScreenCTM()&&parseFloat(getComputedStyle(e).fontSize)*e.getScreenCTM().a>=10;});
 const textHeight=await page.evaluate(()=>{const e=document.querySelector('#chart .axis-unit');return parseFloat(getComputedStyle(e).fontSize)*e.getScreenCTM().a;});
 assert.ok(textHeight>=10,`chart text must stay readable at ${width}px: ${textHeight}`);
 const inspect=page.locator('#findings button').first();if(await inspect.count()){
  await inspect.click();const destination=page.locator('#detail-title:focus,#step-evidence-title:focus,.evidence-button:focus');assert.equal(await destination.count(),1,'inspect destination receives focus');
  const rect=await destination.boundingBox();assert.ok(rect.y>=0&&rect.y<960,'inspect destination is visible');
 }

 await page.locator('#attempt-history summary').click();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'expanded history does not overflow');await page.locator('#attempt-history summary').click();
 await page.screenshot({path:path.join(out,`report-v2-${width}-${theme}.png`),fullPage:true});
}
const unsafe=await page.locator('a[href]').evaluateAll(a=>a.filter(e=>!/^https:/.test(e.href)).map(e=>e.href));assert.deepEqual(unsafe,[]);

const standalone=path.join(out,'standalone.html');fs.copyFileSync(fileURLToPath(url),standalone);await page.goto(pathToFileURL(standalone).href);assert.equal(await page.locator('#jobs button').count(),R.job_types.length);fs.unlinkSync(standalone);assert.deepEqual(errors,[]);assert.equal(requests.some(u=>!u.startsWith('file:')),false);
const result={offline:true,job_types:R.job_types.length,windows:R.windows.length,attempts:R.source.retained_job_ids.length,checks:['all job/window/attempt selections','JSON numeric parity','evidence references','representative costs','reviewed layout and collapsed history','latest attempt on selection','baseline and outcome cards','keyboard and saved evidence parents','320/375/1280px overflow','en/ru light/dark','moved standalone file','no external network or JS errors']};fs.writeFileSync(path.join(out,'browser-v2-results.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
