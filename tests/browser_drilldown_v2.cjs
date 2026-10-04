const {chromium}=require(process.env.CI_REPORT_PLAYWRIGHT||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const url=process.argv[2],out=process.argv[3];
if(!url||!out)throw Error('Usage: browser_drilldown_v2.cjs FILE_URL OUTPUT_DIRECTORY');
(async()=>{fs.mkdirSync(out,{recursive:true});const browser=await chromium.launch({channel:process.env.CI_REPORT_BROWSER_CHANNEL==='chromium'?undefined:(process.env.CI_REPORT_BROWSER_CHANNEL||'chrome'),headless:true});try{
 const context=await browser.newContext({offline:true,viewport:{width:1236,height:960}}),page=await context.newPage(),errors=[],requests=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(['warning','error'].includes(m.type()))errors.push(m.text());});page.on('request',r=>requests.push(r.url()));
 await page.goto(url);const R=await page.locator('#report-data').evaluate(e=>JSON.parse(e.textContent)),ru=await page.locator('html').getAttribute('lang')==='ru';
 assert.equal(await page.locator('#run-drilldown').count(),1,'reference-style drilldown must exist');
 assert.equal(await page.locator('#detail-metadata').evaluate(e=>e.open),false,'technical metadata is collapsed');
 let groupsChecked=0,operationsChecked=0,unknownChecked=0,cachedChecked=0;
 for(const jt of R.job_types){await page.locator(`[data-type="${jt.id}"]`).click();
  const a=R.attempts.find(a=>a.id===jt.latest_attempt_id),nodes=a.trace?.evidence||[],images=nodes.filter(n=>n.kind==='image'),commands=nodes.filter(n=>n.kind==='command'),groups=images.length?images:[...commands,...nodes.filter(n=>n.kind==='operation'&&!n.parent_id)];
  assert.equal(await page.locator('#runner-phases').evaluate(e=>e.open),false,'runner phases are collapsed');
  assert.equal(await page.locator('#phase-rows [data-evidence]').count(),nodes.filter(n=>n.kind==='phase').length);
  assert.equal(await page.locator('#image-timeline [data-evidence]').count(),groups.length,'saved groups are shown without invented merges');
  if(!groups.length)continue;
  assert.equal(await page.locator('#run-drilldown').evaluate(e=>e.open),true);
  assert.equal(await page.locator('#image-axis-end').getAttribute('data-seconds'),String(a.timing.execution.value_seconds));
  assert.match(await page.locator('#image-axis-label').innerText(),ru?/от первой отметки лога/:/from first log timestamp/,'parser offsets must not claim an API job-start anchor');
  for(const group of groups){const row=page.locator(`#image-timeline [data-evidence="${group.id}"]`);await row.focus();await page.keyboard.press('Enter');
   assert.equal(await row.getAttribute('aria-pressed'),'true');groupsChecked++;
   assert.equal(await row.locator('.timeline-label').evaluate(e=>getComputedStyle(e).color),await page.locator('body').evaluate(e=>getComputedStyle(e).color));
   assert.equal(await row.evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(237, 243, 255)');
   assert.equal(await page.locator('#group-evidence-note').getAttribute('data-group-id'),group.id,'group provenance remains accessible when operations are selected');
   assert.equal(await page.locator('#group-evidence-note').getAttribute('data-push-coverage'),group.push_coverage);
   assert.equal(await page.locator('#group-evidence-note').getAttribute('data-complete'),String(group.complete));
   assert.equal(await page.locator('#group-evidence-note').getAttribute('data-line-start'),String(group.lines.start));
   assert.equal(await page.locator('#group-evidence-note').getAttribute('data-line-end'),String(group.lines.end));
   const children=nodes.filter(n=>n.parent_id===group.id),ops=children.length?children:[group];
   assert.equal(await page.locator('#step-timeline [data-evidence]').count(),ops.length,'only selected group operations are visible');
   const span=group.timing.start_seconds!=null&&group.timing.end_seconds!=null?group.timing.end_seconds-group.timing.start_seconds:null;
   assert.equal(await page.locator('#step-axis-end').getAttribute('data-seconds'),String(span));
   for(const n of ops){const op=page.locator(`#step-timeline [data-evidence="${n.id}"]`);await op.click();operationsChecked++;
    assert.equal(await op.getAttribute('aria-pressed'),'true');assert.equal(await op.getAttribute('data-seconds'),String(n.timing.duration_seconds));
    assert.equal(await page.locator('#step-evidence-block').getAttribute('data-selected-evidence'),n.id);
    assert.equal(await page.locator('#step-evidence-note').getAttribute('data-line-start'),String(n.lines.start));
    assert.equal(await page.locator('#step-evidence-note').getAttribute('data-line-end'),String(n.lines.end));
    const parts=nodes.filter(p=>p.parent_id===n.id);assert.equal(await page.locator('#step-evidence .part-button').count(),parts.length);
    for(const part of parts){await op.click();const child=page.locator(`#step-evidence [data-evidence="${part.id}"]`);assert.equal(await child.getAttribute('data-parent'),n.id);await child.focus();await page.keyboard.press('Enter');assert.equal(await page.locator('#step-evidence-block').getAttribute('data-selected-evidence'),part.id);assert.equal(await page.locator('#step-evidence-note').getAttribute('data-line-start'),String(part.lines.start));assert.equal(await page.locator('#step-evidence-note').getAttribute('data-line-end'),String(part.lines.end));assert.equal(await page.evaluate(()=>document.activeElement.matches('#step-evidence-title,.evidence-button')),true,'nested selection retains keyboard focus');
     if(part.kind==='operation')for(const nested of nodes.filter(p=>p.parent_id===part.id)){const inner=page.locator(`#step-evidence [data-evidence="${nested.id}"]`);await inner.click();assert.equal(await page.locator('#step-evidence-block').getAttribute('data-selected-evidence'),nested.id);assert.equal(await page.evaluate(()=>document.activeElement.matches('#step-evidence-title,.evidence-button')),true);}
    }
    if(parts.length)await op.click();
    const bar=op.locator('.timeline-bar');
    if(n.cached){assert.match(await op.locator('.timeline-duration').innerText(),ru?/Из кэша/:/Cached/);cachedChecked++;assert.equal(await bar.count(),0,'cached is not a measured zero');}
    else if(n.timing.start_seconds==null||n.timing.end_seconds==null||span==null){assert.equal(await bar.count(),0,'unknown positions do not get invented bars');unknownChecked++;}
    else if(span>0){assert.equal(await bar.count(),1);assert.equal(await bar.getAttribute('data-start-seconds'),String(n.timing.start_seconds));assert.equal(await bar.getAttribute('data-end-seconds'),String(n.timing.end_seconds));}
   }
  }
 }
 for(const width of [320,375,1236])for(const theme of ['light','dark']){await page.setViewportSize({width,height:960});await page.emulateMedia({colorScheme:theme});await page.goto(url);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`${width}px ${theme} overflow`);
  const rows=page.locator('#image-timeline .timeline-row');if(await rows.count()){await rows.first().click();assert.ok(await rows.first().evaluate(e=>e.getBoundingClientRect().height)>=38);}
  await page.locator('#run-drilldown').evaluate(e=>window.scrollTo(0,scrollY+e.getBoundingClientRect().top-12));await page.screenshot({path:path.join(out,`drilldown-${width}-${theme}.png`)});
 }
 assert.deepEqual(errors,[]);assert.equal(requests.some(u=>!u.startsWith('file:')),false);
 const result={offline:true,groupsChecked,operationsChecked,unknownChecked,cachedChecked,checks:['two-level timeline','selected group only','source-line provenance','keyboard selection','relative operation axis','cached and unknown timings','collapsed metadata and phases','320/375/1236px light/dark','no network or console errors']};fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
