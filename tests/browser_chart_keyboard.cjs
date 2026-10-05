const {chromium}=require(process.env.CI_REPORT_PLAYWRIGHT||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const url=process.argv[2],out=process.argv[3];
if(!url||!out)throw Error('Usage: browser_chart_keyboard.cjs FILE_URL OUTPUT_DIRECTORY');

(async()=>{
 fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({channel:process.env.CI_REPORT_BROWSER_CHANNEL==='chromium'?undefined:(process.env.CI_REPORT_BROWSER_CHANNEL||'chrome'),headless:true});
 try{
  const context=await browser.newContext({offline:true,viewport:{width:1280,height:960}}),page=await context.newPage(),errors=[],requests=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('console',m=>{if(['warning','error'].includes(m.type()))errors.push(m.text());});
  page.on('request',r=>requests.push(r.url()));
  await page.goto(url);
  const R=await page.locator('#report-data').evaluate(e=>JSON.parse(e.textContent)),ru=await page.locator('html').getAttribute('lang')==='ru';
  const bars=()=>page.locator('#chart .attempt-bar'),bar=id=>page.locator(`#chart .attempt-bar[data-attempt="${id}"]`);
  let windowsChecked=0,keysChecked=0;

  async function selected(id,focused=false){
   assert.deepEqual(await page.locator('#chart [aria-pressed=true]').evaluateAll(es=>es.map(e=>Number(e.dataset.attempt))),[id],'exactly one chart bar is selected');
   assert.deepEqual(await page.locator('#history tr[aria-selected=true]').evaluateAll(es=>es.map(e=>Number(e.dataset.attempt))),[id],'history selection follows chart');
   assert.match(await page.locator('#detail-title').innerText(),new RegExp('#'+id+' '),'details follow selected attempt');
   const attempt=R.attempts.find(a=>a.id===id);
   assert.equal(await page.locator('#attempt-links a').first().getAttribute('href'),attempt.metadata.web_url);
   if(focused)assert.equal(await bar(id).evaluate(e=>document.activeElement===e),true,'selected bar retains keyboard focus');
  }

  async function press(key,id){
   const before=await page.evaluate(()=>({x:scrollX,y:scrollY}));
   await page.keyboard.press(key);keysChecked++;
   await selected(id,true);
   assert.deepEqual(await page.evaluate(()=>({x:scrollX,y:scrollY})),before,'chart keys do not scroll the page');
  }

  async function verifyWindow(w){
   const ids=await bars().evaluateAll(es=>es.map(e=>Number(e.dataset.attempt)));
   assert.deepEqual(ids,[...w.attempt_ids].reverse(),'navigation follows visual order');
   await selected(w.attempt_ids[0]);
   const middle=Math.floor(ids.length/2);
   await bar(ids[middle]).click();await selected(ids[middle],true);
   await press('ArrowLeft',ids[Math.max(0,middle-1)]);
   await press('ArrowRight',ids[ids.length===1?0:middle]);

   await bar(ids[0]).click();await press('ArrowLeft',ids[0]);
   await bar(ids.at(-1)).click();await press('ArrowRight',ids.at(-1));
   for(const [i,id] of ids.entries()){
    if(i===0)await bar(id).click();else await press('ArrowRight',id);
   }
   for(let i=ids.length-2;i>=0;i--)await press('ArrowLeft',ids[i]);
   await bar(ids.at(-1)).focus();await press('Enter',ids.at(-1));
   await bar(ids[0]).focus();await press('Space',ids[0]);

   // Both the visible help and its accessibility association are localized.
   const help=page.locator('#chart-help');assert.equal(await help.isVisible(),true);
   assert.match(await help.innerText(),ru?/Выберите столбец.*←.*→/:/Select a bar.*←.*→/);
   assert.ok((await help.boundingBox()).y>=(await page.locator('#chart').boundingBox()).y+(await page.locator('#chart').boundingBox()).height,'help is below chart');
   for(const element of await bars().all())assert.equal(await element.getAttribute('aria-describedby'),'chart-help');

   // Only chart focus owns the arrow keys; dropdowns keep their native behavior.
   await page.locator('#size').focus();
   const outside=await page.locator('#size').evaluate(e=>{const event=new KeyboardEvent('keydown',{key:'ArrowLeft',bubbles:true,cancelable:true});e.dispatchEvent(event);return event.defaultPrevented;});
   assert.equal(outside,false,'arrows outside chart are not intercepted');await selected(ids[0]);
   // Modified arrow shortcuts are not captured by the chart.
   await bar(ids[0]).focus();
   for(const modifier of ['altKey','ctrlKey','metaKey','shiftKey']){
    const modified=await bar(ids[0]).evaluate((e,modifier)=>{const event=new KeyboardEvent('keydown',{key:'ArrowRight',[modifier]:true,bubbles:true,cancelable:true});e.dispatchEvent(event);return event.defaultPrevented;},modifier);
    assert.equal(modified,false,`${modifier} arrow shortcut remains native`);await selected(ids[0],true);
   }
   windowsChecked++;
  }

  await selected(R.job_types.find(j=>j.id===R.selection.job_type_id).latest_attempt_id);
  for(const jt of R.job_types){
   await page.locator(`[data-type="${jt.id}"]`).click();await selected(jt.latest_attempt_id);
   for(const size of ['16','32']){
    await page.locator('#size').selectOption(size);
    let w=R.windows.find(w=>w.type_id===jt.id&&w.size===Number(size)&&w.page===0);
    await verifyWindow(w);
    while(w.has_older){await page.locator('#older').click();w=R.windows.find(v=>v.id===w.older_window_id);await verifyWindow(w);}
    if(w.has_newer){await page.locator('#newer').click();w=R.windows.find(v=>v.id===w.newer_window_id);await selected(w.attempt_ids[0]);}
    if(w.page!==0){await page.locator('#latest').click();await selected(jt.latest_attempt_id);}
   }
  }

  await page.locator('#jobs button').first().click();
  const ids=await bars().evaluateAll(es=>es.map(e=>Number(e.dataset.attempt))),current=ids[Math.floor(ids.length/2)];
  await bar(current).click();await selected(current,true);
  for(const width of [375,1280]){
   await page.setViewportSize({width,height:960});
   await page.waitForFunction(()=>Math.abs(document.querySelector('#chart svg').viewBox.baseVal.width-Math.max(240,document.querySelector('#chart').clientWidth))<1);
   await selected(current,true);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'help does not cause overflow');
   for(const theme of ['light','dark']){
    await page.emulateMedia({colorScheme:theme});
    await page.screenshot({path:path.join(out,`chart-${width}-${theme}.png`),fullPage:true});
   }
   await press('ArrowLeft',ids[Math.max(0,ids.indexOf(current)-1)]);
   if(ids.length>1)await press('ArrowRight',current);
  }
  assert.deepEqual(errors,[]);assert.equal(requests.some(u=>!u.startsWith('file:')),false);
  const result={offline:true,language:ru?'ru':'en',windowsChecked,keysChecked,checks:['latest default','click focus','visual arrow order','details/history synchronization','boundaries','Enter/Space','localized help below chart','outside/modified arrows','resize focus','mobile/desktop light/dark','no external requests or JS errors']};
  fs.writeFileSync(path.join(out,'chart-keyboard-results.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
