const {chromium}=require(process.env.CI_REPORT_PLAYWRIGHT||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {fileURLToPath,pathToFileURL}=require('node:url');
const url=process.argv[2],output=process.argv[3];
if(!url||!output)throw Error('Usage: workflow_browser_check.cjs FILE_URL OUTPUT_DIRECTORY');
(async()=>{
  fs.mkdirSync(output,{recursive:true});
  const browser=await chromium.launch({channel:process.env.CI_REPORT_BROWSER_CHANNEL||'chrome',headless:true});
  try{
    const context=await browser.newContext({viewport:{width:1280,height:1000},offline:true});
    const page=await context.newPage(),errors=[],requests=[];
    page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requests.push(r.url()));
    page.on('console',m=>{if(['error','warning'].includes(m.type()))errors.push(m.text())});
    await page.goto(url);await page.locator('#elapsed-chart svg').waitFor();
    assert.equal(new URL(url).protocol,'file:');
    const data=JSON.parse(await page.locator('#report-data').textContent());
    const view=data.views.find(v=>v.window===32),series=view.series[0];
    const selected=series.runs.find(r=>r.pipeline_id===view.pipeline_ids[0]);
    assert.equal(await page.locator('#elapsed-chart .measurement').count(),32);
    assert.equal(await page.locator('#active-chart .measurement').count(),32);
    for(const metric of ['elapsed_seconds','active_seconds','gap_seconds','queue_sum_seconds']){
      assert.equal(await page.locator(`[data-metric="${metric}"]`).getAttribute('data-seconds'),String(selected.metrics[metric]??''));
    }
    for(const run of series.runs){
      assert.equal(await page.locator(`#elapsed-chart [data-pipeline="${run.pipeline_id}"]`).getAttribute('data-seconds'),String(run.metrics.elapsed_seconds??''));
      assert.equal(await page.locator(`#active-chart [data-pipeline="${run.pipeline_id}"]`).getAttribute('data-seconds'),String(run.metrics.active_seconds??''));
    }
    assert.match(await page.locator('#elapsed-comparison').innerText(),new RegExp('N='+series.comparisons.elapsed_seconds.n));
    assert.match(await page.locator('#elapsed-heading').innerText(),/min/);
    await page.screenshot({path:path.join(output,'workflow-desktop.png'),fullPage:true});
    await page.locator('#active-chart [data-pipeline="63"]').focus();await page.keyboard.press('Enter');
    assert.equal(await page.locator('#pipeline-select').inputValue(),'63');
    assert.equal(await page.locator('#elapsed-chart [aria-pressed="true"]').getAttribute('data-pipeline'),'63');
    assert.match(await page.locator('#selected-run').innerText(),/#63/);
    await page.getByRole('button',{name:'compile',exact:true}).last().click();
    assert.match(await page.locator('#job-title').innerText(),/compile/);
    await page.locator('#attempts button').first().click();
    assert.match(await page.locator('#attempt-detail').innerText(),/Started/);
    await page.locator('#window-select').selectOption('64');
    assert.equal(await page.locator('#elapsed-chart .measurement').count(),64);
    assert.equal(await page.locator('#pipeline-select').inputValue(),'63');
    await page.locator('#pipeline-select').selectOption('1');
    assert.match(await page.locator('#selected-run').innerText(),/unknown/);
    assert.equal(await page.locator('[data-metric="elapsed_seconds"]').getAttribute('data-seconds'),'');
    assert.equal(await page.locator('#elapsed-chart [data-pipeline="1"]').getAttribute('data-seconds'),'');
    await page.locator('#workflow-select').selectOption('maintenance/lint');
    assert.match(await page.locator('#type').innerText(),/Independent/);
    await page.locator('#pipeline-select').selectOption('63');
    assert.match(await page.locator('#selected-run').innerText(),/failed/);
    assert.equal(await page.locator('#elapsed-chart [data-pipeline="63"]').getAttribute('data-state'),'failed');
    await page.locator('#pipeline-select').selectOption('64');
    assert.equal(await page.locator('#elapsed-chart [data-pipeline="63"]').evaluate(e=>e.classList.contains('unavailable')),false);
    const lint=data.views[1].series.find(s=>s.id==='maintenance/lint');
    assert.ok(!lint.comparisons.elapsed_seconds.sample_pipeline_ids.includes(63));
    await page.locator('#workflow-select').selectOption('maintenance/audit');
    await page.locator('#pipeline-select').selectOption('62');
    assert.equal(await page.locator('[data-metric="elapsed_seconds"]').getAttribute('data-seconds'),'');
    await page.locator('#language').selectOption('ru');assert.equal(await page.locator('html').getAttribute('lang'),'ru');
    assert.match(await page.locator('h1').innerText(),/Производительность/);
    await page.locator('#language').selectOption('en');
    await page.locator('#workflow-select').selectOption('delivery');await page.locator('#pipeline-select').selectOption('64');
    await page.setViewportSize({width:360,height:800});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.screenshot({path:path.join(output,'workflow-mobile.png'),fullPage:true});
    await page.emulateMedia({colorScheme:'dark'});
    await page.screenshot({path:path.join(output,'workflow-dark.png'),fullPage:true});
    const detached=path.join(output,'standalone.html');fs.copyFileSync(fileURLToPath(url),detached);
    await page.goto(pathToFileURL(detached).href);assert.equal(await page.locator('#elapsed-chart .measurement').count(),32);
    fs.unlinkSync(detached);
    // Boundary fixtures are calculated by the helper from timestamps, not patched HTML.
    for(const [name,pattern] of [['boundary-300',/\(s\)/],['boundary-301',/\(min\)/]]){
      await page.goto(pathToFileURL(path.join(path.dirname(fileURLToPath(url)),name,'report.html')).href);
      assert.match(await page.locator('#elapsed-heading').innerText(),pattern);
    }
    await page.goto(pathToFileURL(path.join(path.dirname(fileURLToPath(url)),'report-ru.html')).href);
    assert.equal(await page.locator('html').getAttribute('lang'),'ru');
    assert.equal(await page.locator('#language').inputValue(),'ru');
    assert.match(await page.locator('h1').innerText(),/Производительность/);
    assert.match(await page.locator('#elapsed-heading').innerText(),/мин/);
    assert.deepEqual(JSON.parse(await page.locator('#report-data').textContent()),data);
    assert.deepEqual(errors,[]);assert.equal(requests.some(u=>!u.startsWith('file:')),false);
    const result={offline:true,checks:['canonical metric and chart parity','32/64 pipeline windows','shared keyboard/pipeline selection','job and attempt drill-down','independent operation series','failed baseline exclusion','unknown not zero','CLI and in-report language selection','desktop/mobile/dark rendering','300-second boundary','standalone rendering','no network or console errors']};
    fs.writeFileSync(path.join(output,'browser-results.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
  }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
