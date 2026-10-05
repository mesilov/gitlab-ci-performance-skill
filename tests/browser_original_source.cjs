const {chromium}=require(process.env.CI_REPORT_PLAYWRIGHT||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs');
const url=process.argv[2],out=process.argv[3];
(async()=>{fs.mkdirSync(out,{recursive:true});const browser=await chromium.launch({channel:process.env.CI_REPORT_BROWSER_CHANNEL==='chromium'?undefined:(process.env.CI_REPORT_BROWSER_CHANNEL||'chrome'),headless:true});
try{let originalTexts=[];for(const language of ['en','ru']){const context=await browser.newContext({offline:true,viewport:{width:1280,height:960}}),page=await context.newPage(),errors=[],requests=[];
 await page.addInitScript(()=>{Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{window.copied=text;}}});});
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requests.push(r.url()));await page.goto(url.replace('report.html',language+'.html'));
 const R=await page.locator('#report-data').evaluate(e=>JSON.parse(e.textContent)),a=R.attempts[0],t=a.trace;
 const raw=Buffer.from(t.source.raw_base64,'base64').toString('utf8');
 assert.equal(await page.locator('#trace-source-block').count(),1,'received log is visible even when parsing is partial');
 await page.locator('#trace-source-block > summary').click();
 assert.equal(await page.locator('#trace-source-block .source-fragment:not(.source-readable)').textContent(),raw);
 await page.locator('#trace-source-block .copy-source').click();assert.equal(await page.evaluate(()=>window.copied),raw);
 const downloaded=page.waitForEvent('download');await page.locator('#trace-source-block .save-source').click();const download=await downloaded;assert.deepEqual(fs.readFileSync(await download.path()),Buffer.from(t.source.raw_base64,'base64'),'original-byte download is lossless');

 for(const n of t.evidence.filter(n=>n.kind==='operation')){await page.locator(`#step-timeline [data-evidence="${n.id}"]`).click();
 assert.equal(await page.locator('#source-title').textContent(),n.source_label.text,'complete title includes original spaces');
 assert.ok((await page.locator('#step-timeline [data-evidence="'+n.id+'"]').boundingBox()).height<=110,'long source title is visually folded; full text remains in details');
 const text=await page.locator('#step-evidence .source-fragment:not(.source-readable)').textContent();assert.ok(text.includes('#'+n.buildkit.step_id+' '+n.source_label.text));
 await page.locator('#step-evidence .copy-source').click();assert.equal(await page.evaluate(()=>window.copied),text);
 originalTexts.push(await page.locator('#source-title').textContent());
 }
 await page.evaluate(()=>{Object.defineProperty(navigator,'clipboard',{value:undefined,configurable:true});document.addEventListener('copy',e=>{const set=e.clipboardData.setData.bind(e.clipboardData);e.clipboardData.setData=(type,text)=>{window.fallbackCopied=text;set(type,text);};},{capture:true});});
 await page.locator('#trace-source-block .copy-source').click();assert.equal(await page.evaluate(()=>window.fallbackCopied),raw,'fallback copy preserves CR/ANSI/source text');
 assert.equal(await page.evaluate(()=>window.executed),undefined,'source JS never executes');assert.equal(await page.locator('#step-evidence script,#step-evidence img').count(),0);
 for(const width of [320,375,1280]){await page.setViewportSize({width,height:960});for(const theme of ['light','dark']){await page.emulateMedia({colorScheme:theme});
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'no page-level overflow');
 await page.screenshot({path:out+'/'+language+'-'+width+'-'+theme+'.png',fullPage:true});}}
 await page.locator('#step-evidence .copy-source').focus();await page.keyboard.press('Enter');
 assert.deepEqual(errors,[]);assert.ok(requests.every(r=>r.startsWith('file:')),'offline standalone');await context.close();}
 assert.deepEqual(originalTexts.slice(0,originalTexts.length/2),originalTexts.slice(originalTexts.length/2),'source is identical in RU/EN');
 console.log('Original source QA: ru/en copy, full titles, injection, mobile, keyboard, offline PASS');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
