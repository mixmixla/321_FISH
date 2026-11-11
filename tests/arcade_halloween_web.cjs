// Run with ARCADE_PLAYWRIGHT pointing at an isolated playwright-core install.
const {chromium}=require(process.env.ARCADE_PLAYWRIGHT||'playwright-core');
const {spawn}=require('node:child_process');
const fs=require('node:fs');const path=require('node:path');
const root=path.resolve(__dirname,'..'),out=path.join(root,'docs/review-assets/ANIME-ARCADE-20261106');
const server=spawn(process.env.ARCADE_PYTHON||'D:/Project/321_FISH/.venv/Scripts/python.exe',[path.join(__dirname,'arcade_web_server.py')],{cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});
(async()=>{
 let browser;
 try{
  const port=await new Promise((resolve,reject)=>{let data='';server.stdout.on('data',chunk=>{data+=chunk;if(data.includes('\n'))resolve(Number(data.trim().split('\n')[0]));});server.once('exit',code=>reject(Error('Fixture exited '+code)));server.stderr.on('data',d=>process.stderr.write(d));});
  browser=await chromium.launch({headless:true,executablePath:process.env.ARCADE_CHROMIUM||'C:/Users/liang/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe'});
  const page=await browser.newPage({viewport:{width:1100,height:900}}),errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.route('**/*',route=>{if(new URL(route.request().url()).hostname!=='127.0.0.1')return route.abort();return route.continue();});
  await page.goto('http://127.0.0.1:'+port+'/');
  async function refresh(uid=7){const fixture=await (await fetch('http://127.0.0.1:'+port+'/fixture')).json();await page.evaluate(({s,uid})=>{state.uid=uid;state.groom='SYNTHETIC';state.gst={room:{game:'halloween',room_id:'SYNTHETIC',status:s.status==='ended'?'ended':'playing',players:[7,8],spectators:[9]},state:s};if(!document.querySelector('#gpanel'))openGamePanel('SYNTHETIC');renderGamePanel();}, {s:fixture.state,uid});return fixture;}
  await fetch('http://127.0.0.1:'+port+'/start');await refresh();
  await page.locator('#gpanel .card').screenshot({path:path.join(out,'halloween-web-start.png')});
  await fetch('http://127.0.0.1:'+port+'/decision');await refresh();
  await page.locator('.orch-action[data-op="flip"]').click();await page.waitForTimeout(120);let f=await refresh();
  if(f.state.counts['🍓']!==5||f.actions[0].op!=='flip')throw Error('Flip failed');
  if(f.state.area_cards.map(c=>c.uid).join(',')!=='7,8,7,8,7')throw Error('Flipper ownership failed');
  await page.waitForFunction(()=>[...document.images].every(i=>i.complete));await page.waitForTimeout(180);
  await page.locator('#gpanel .card').screenshot({path:path.join(out,'halloween-web-five.png')});
  await page.locator('.orch-action[data-op="slap"]').click();await page.waitForTimeout(100);f=await refresh();
  if(f.state.score['7']!==5||f.state.area.length)throw Error('Slap failed');
  await page.setViewportSize({width:390,height:844});await refresh();
  await page.locator('#gpanel .card').screenshot({path:path.join(out,'halloween-web-mobile.png')});
  const overflow=await page.locator('.orch-table').evaluate(e=>e.scrollWidth>e.clientWidth+1);if(overflow)throw Error('Mobile overflow');
  if((await page.locator('.orch-bell').boundingBox()).width<100)throw Error('Central bell too small');
  for(const uid of [8,9]){await refresh(uid);if(await page.locator('.orch-action:enabled').count())throw Error('Seat gate failed '+uid);}
  await fetch('http://127.0.0.1:'+port+'/final');await refresh();
  for(const op of ['flip','slap']){await page.locator('.orch-action[data-op="'+op+'"]').click();await page.waitForTimeout(100);f=await refresh();}
  if(f.state.status!=='ended'||f.state.winner_uid!==7||await page.locator('.orch-action:enabled').count())throw Error('Final state failed');
  await page.locator('#gpanel .card').screenshot({path:path.join(out,'halloween-web-ended.png')});
  if(errors.length)throw Error(errors.join('\n'));
  const report={actions:f.actions,score:f.state.score,desktop:'private Windows desktop',browser:'headless Chromium',mobile_width:390,observer_gate:true,opponent_gate:true,overflow,page_errors:errors};fs.writeFileSync(path.join(out,'halloween-web-actions.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});
