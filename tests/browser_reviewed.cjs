'use strict';
// Run against an already rendered synthetic v2 fixture; all data come from its embedded payload.
const {chromium}=require(process.env.CI_REPORT_PLAYWRIGHT || 'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {fileURLToPath,pathToFileURL}=require('node:url');
const url=process.argv[2],output=process.argv[3];
if(!url||!output)throw Error('Usage: browser_reviewed.cjs FILE_URL OUTPUT_DIRECTORY');
(async()=>{
  assert.equal(new URL(url).protocol,'file:');fs.mkdirSync(output,{recursive:true});
  const browser=await chromium.launch({channel:process.env.CI_REPORT_BROWSER_CHANNEL||'chrome',headless:true});
  try{
    const context=await browser.newContext({viewport:{width:1280,height:1000},offline:true});
    await context.route(/^https?:/,route=>route.abort());
    const page=await context.newPage(),errors=[],requests=[];
    page.on('pageerror',e=>errors.push(e.message));page.on('console',message=>{if(['warning','error'].includes(message.type()))errors.push(message.text());});page.on('request',r=>requests.push(r.url()));
    await page.goto(url);
    const report=await page.locator('#report-data').evaluate(e=>JSON.parse(e.textContent));
    assert.ok(report.types.length,'fixture requires job types');
    const ru=await page.locator('html').getAttribute('lang')==='ru',waitLabel=ru?'Ожидание раннера':'Runner wait',executionLabel=ru?'Выполнение':'Execution';
    assert.ok((await page.locator('#priority-summary > div').first().innerText()).startsWith(waitLabel),'wait precedes execution in summary');
    assert.equal(await page.locator('#legend > span').first().innerText(),waitLabel,'wait is first legend item');
    assert.deepEqual((await page.locator('#attempt-metadata .timing dt').allTextContents()).slice(0,2),[waitLabel,executionLabel],'wait precedes execution in selected details');
    assert.deepEqual((await page.locator('.attempts th').allTextContents()).slice(4,6),[waitLabel,executionLabel],'wait precedes execution in history columns');
    const fixedCodes=['canceling','limitation_trace_erased','limitation_job_not_run','limitation_trace_disabled','limitation_details_not_collected','limitation_trace_forbidden','limitation_trace_unavailable','limitation_trace_request_failed','limitation_trace_timeout','limitation_active_trace','limitation_trace_cache_write_failed','limitation_trace_byte_limit','limitation_runner_log_truncated'];
    assert.deepEqual(await page.evaluate(codes=>codes.filter(code=>t(code)===t('unknown_label')),fixedCodes),[],'fixed status and limitation codes are localized');
    assert.equal(await page.locator('#coverage-source').getAttribute('data-complete'),String(report.coverage.source_complete_available_history));
    assert.equal(await page.locator('#coverage-metadata').getAttribute('data-fresh'),String(report.coverage.metadata_fresh));
    assert.equal(await page.locator('#coverage-metadata').getAttribute('data-requested'),String(report.coverage.metadata_requests));
    assert.equal(await page.locator('#coverage-traces').getAttribute('data-requested'),String(report.coverage.trace_requests));
    for(const [status,count]of Object.entries(report.coverage.trace_status_counts))assert.equal(await page.locator('#coverage-traces [data-trace-status]').evaluateAll((rows,s)=>rows.find(e=>e.dataset.traceStatus===s)?.dataset.count,status),String(count));

    assert.equal(await page.locator('.job-card').count(),report.types.length);
    assert.equal(await page.locator('#job-detail').count(),1);
    assert.equal(await page.locator('#window-select').inputValue(),'32');
    assert.equal(await page.locator('#job-detail').getAttribute('data-type-id'),report.default_type_id);
    for(const type of report.types){
      await page.locator('.job-card').evaluateAll((cards,id)=>cards.find(c=>c.dataset.typeId===id).click(),type.id);
      assert.equal(await page.locator('#job-title').innerText(),type.name);
      for(const key of ['source_ref','configuration_sha256'])if(type.purpose?.[key])assert.ok((await page.locator('#purpose-provenance').innerText()).includes(type.purpose[key]),`catalog ${key} provenance visible`);
      assert.equal(await page.locator('#job-detail').getAttribute('data-type-id'),type.id);
      await page.locator('#window-select').selectOption('64');
      const window=type.windows.find(w=>w.size===64&&w.offset===0);
      assert.equal(await page.locator('#history .attempt-bar').count(),window.attempt_ids.length);
      assert.equal(await page.locator('#history .axis-unit').textContent(),window.unit==='minutes'?(await page.locator('html').getAttribute('lang')==='ru'?'мин':'min'):(await page.locator('html').getAttribute('lang')==='ru'?'с':'s'));
      for(const id of window.attempt_ids){
        const bar=page.locator(`#history .attempt-bar[data-id="${id}"]`);
        await bar.focus();assert.equal(await bar.evaluate(e=>e===document.activeElement),true);await page.keyboard.press('Enter');
        assert.equal(await page.locator('#attempt-detail').getAttribute('data-job-id'),String(id));
        const unit=window.unit==='minutes'?(await page.locator('html').getAttribute('lang')==='ru'?'мин':'min'):(await page.locator('html').getAttribute('lang')==='ru'?'с':'s');
        for(const timing of await page.locator('#attempt-metadata .timing dd').allTextContents())if(timing!=='—')assert.ok(timing.endsWith(' '+unit),`selected timing uses ${unit}: ${timing}`);
        assert.equal(await bar.getAttribute('aria-pressed'),'true');
        const aria=await bar.getAttribute('aria-label');assert.ok(aria.indexOf(waitLabel)<aria.indexOf(executionLabel),'wait precedes execution in accessible bar summary');
        assert.equal(/Unclassified evidence|Неклассифицированные данные/.test(await page.locator('#trace-provenance').innerText()),false,'trace limitations never use the unknown label');
        const detail=(Array.isArray(report.details)?report.details:Object.values(report.details)).find(d=>d.job_id===id);
        assert.equal(await page.locator('#trace-provenance [data-trace-status]').getAttribute('data-trace-status'),detail?.trace_status||'unavailable');
        const job=report.jobs.find(j=>j.id===id),execution=bar.locator('[data-component="execution"]'),queue=bar.locator('[data-component="queue"]');
        assert.equal(await bar.locator('circle').count(),0);
        if(await execution.count()){
          assert.equal(await execution.getAttribute('data-outcome'),job.status);
          assert.equal(await execution.getAttribute('fill'),job.status==='success'?'var(--success)':job.status==='failed'?'var(--failed)':job.status==='canceled'?'var(--canceled)':'var(--other)');
          assert.equal(await bar.locator('[data-component="not-run"]').count(),0);
          assert.notEqual(await bar.locator('.selection').evaluate(e=>getComputedStyle(e).stroke),await execution.evaluate(e=>getComputedStyle(e).fill));
          if(await queue.count())assert.ok(Number(await queue.getAttribute('y'))+Number(await queue.getAttribute('height'))<=Number(await execution.getAttribute('y'))+.01);
        }else assert.equal(await bar.locator(job.executed===false?'[data-component="not-run"]':'[data-component="unknown-execution"]').count(),1);
      }
      const priority=page.locator('#priorities button[data-job-id]').first();
      if(await priority.count()){
        const id=await priority.getAttribute('data-job-id');const p=window.priorities.find(p=>String(p.evidence?.job_id)===id);await priority.click();
        assert.equal(await page.locator('#attempt-detail').getAttribute('data-job-id'),id);
        const evidenceId=p.evidence.operation_id||p.evidence.phase_id||p.evidence.command_id;
        if(evidenceId)assert.equal(await page.locator('#run-evidence [data-evidence-selected="true"]').getAttribute('data-evidence-id'),evidenceId);
        else assert.equal(await page.locator('#history .attempt-bar[aria-pressed="true"]').getAttribute('data-id'),id);
        assert.equal(Number(await page.locator('#priorities .priority').first().locator('[data-cost-seconds]').getAttribute('data-cost-seconds')),window.priorities[0].median_cost_seconds);
        assert.equal(Number(await page.locator('#priorities .priority').first().locator('[data-evidence-seconds]').getAttribute('data-evidence-seconds')),window.priorities[0].evidence.duration_seconds);
      }
      await page.locator('#window-select').selectOption('32');
      const older=type.windows.find(w=>w.size===32&&w.offset===32);
      if(older?.count){await page.locator('#older-window').click();assert.equal(await page.locator('#history .attempt-bar').count(),older.count);await page.locator('#latest-window').click();}
    }
    const evidenceButton=page.locator('#run-evidence .evidence-button').first();
    if(await evidenceButton.count()){await evidenceButton.focus();await page.keyboard.press('Enter');assert.ok(await page.locator('#run-evidence [data-evidence-selected="true"]').count());}
    await page.locator('#same-ref-view summary').click();
    const sameRefMetric=page.locator('#same-ref-body tbody tr td:nth-child(3)').first();if(await sameRefMetric.count())assert.equal(await sameRefMetric.innerText(),waitLabel,'wait first in same-ref comparisons');
    await page.locator('#same-ref-view summary').click();
    const densest=report.types.reduce((a,b)=>a.retained_ids.length>b.retained_ids.length?a:b);
    await page.locator('.job-card').evaluateAll((cards,id)=>cards.find(c=>c.dataset.typeId===id).click(),densest.id);
    for(const width of [320,375,1280]){
      await page.setViewportSize({width,height:900});await page.locator('#window-select').selectOption('64');
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`page overflow at ${width}`);
      assert.equal(await page.locator('#history').evaluate(e=>e.scrollWidth<=e.clientWidth),true,`chart overflow at ${width}`);
      assert.equal(await page.locator('#older-window').isDisabled(),true);
      await page.locator('#attempt-history summary').click();
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`open table page overflow at ${width}`);
      await page.locator('#attempt-history summary').click();
      for(const theme of ['light','dark']){await page.emulateMedia({colorScheme:theme});await page.screenshot({path:path.join(output,`reviewed-${width}-${theme}.png`),fullPage:true});}
    }
    const unsafe=await page.locator('a[href]').evaluateAll(a=>a.filter(e=>!/^https?:/.test(e.href)).map(e=>e.href));assert.deepEqual(unsafe,[]);
    const detached=path.join(output,'standalone.html');fs.copyFileSync(fileURLToPath(url),detached);
    await page.goto(pathToFileURL(detached).href);assert.equal(await page.locator('.job-card').count(),report.types.length);fs.unlinkSync(detached);
    assert.deepEqual(errors,[]);assert.equal(requests.some(u=>!u.startsWith('file:')),false);
    const result={offline:true,language:await page.locator('html').getAttribute('lang'),checks:['wait-first ordering','fixed status/limitation translations','coverage transparency','job isolation','32/64 navigation','all retained attempts and reruns','job outcome colors','queue above execution','no executed circles','explicit window unit','priority evidence navigation','keyboard selection','320/375/1280 width','light and dark','safe links','moved standalone file','no network or JS errors']};
    fs.writeFileSync(path.join(output,'browser-results.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
