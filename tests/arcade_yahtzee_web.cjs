const {chromium}=require(process.env.ARCADE_PLAYWRIGHT||'playwright-core');
const {spawn}=require('node:child_process');const fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..'),out=path.join(root,'docs/review-assets/ANIME-ARCADE-20261106');
const server=spawn(process.env.ARCADE_PYTHON||'D:/Project/321_FISH/.venv/Scripts/python.exe',[path.join(__dirname,'arcade_web_server.py')],{cwd:root,env:{...process.env,ARCADE_GAME:'yahtzee'},windowsHide:true,stdio:['ignore','pipe','pipe']});
(async()=>{let browser;try{
 const port=await new Promise((resolve,reject)=>{server.stdout.once('data',d=>resolve(Number(String(d).trim())));server.once('exit',c=>reject(Error('Fixture exited '+c)));server.stderr.on('data',d=>process.stderr.write(d));});const url='http://127.0.0.1:'+port;
 browser=await chromium.launch({headless:true,executablePath:process.env.ARCADE_CHROMIUM||'C:/Users/liang/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe'});const page=await browser.newPage({viewport:{width:1100,height:960}}),errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort());await page.goto(url);
 async function refresh(uid=7){const f=await(await fetch(url+'/fixture')).json();await page.evaluate(({s,uid})=>{state.uid=uid;state.groom='SYNTHETIC';state.gst={room:{game:'yahtzee',room_id:'SYNTHETIC',status:s.status,players:[7,8],spectators:[9]},state:s};if(!document.querySelector('#gpanel'))openGamePanel('SYNTHETIC');renderGamePanel();},{s:f.state,uid});return f;}
 async function action(selector){await page.locator(selector).click();await page.waitForTimeout(100);return refresh();}
 async function shot(name){await page.locator('#gmain').evaluate(e=>e.scrollTop=0);await page.locator('#gpanel .card').screenshot({path:path.join(out,'yahtzee-web-'+name+'.png')});}
 await refresh();await shot('start');let f=await action('.yacht-cup');const before=f.state.dice.slice();
 for(const i of [1,4])await page.locator('.yacht-die[data-index="'+i+'"]').click();
 f=await action('.yacht-cup');if(f.state.dice[1]!==before[1]||f.state.dice[4]!==before[4]||f.actions[1].keep.join(',')!=='1,4')throw Error('Keep mapping failed');
 await shot('decision');await page.setViewportSize({width:390,height:844});await refresh();await shot('mobile');
 if(await page.locator('.yacht-table').evaluate(e=>e.scrollWidth>e.clientWidth+1))throw Error('Mobile overflow');
 if(await page.locator('#gmain input,#gmain select').count())throw Error('Legacy numeric controls remain');
 f=await action('.yacht-cell[data-cat="chance"]');if(f.state.scores['7'].chance==null)throw Error('Score failed');
 for(const uid of [8,9]){await refresh(uid);if(uid===9&&await page.locator('.yacht-cell:enabled,.yacht-cup:enabled,.yacht-die:enabled').count())throw Error('Spectator gate failed');}
 await fetch(url+'/final');await refresh();f=await action('.yacht-cell[data-cat="yahtzee"]');if(f.state.status!=='ended'||f.state.winner_uid!==7)throw Error('Final failed');await shot('ended');
 if(errors.length)throw Error(errors.join('\n'));const report={actions:f.actions,kept_positions:[1,4],before,final:f.state,legacy_inputs:0,mobile_width:390,page_errors:errors};fs.writeFileSync(path.join(out,'yahtzee-web-actions.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({actions:f.actions,kept_positions:[1,4],winner:f.state.winner_uid,page_errors:errors}));
}finally{if(browser)await browser.close();server.kill();}})().catch(e=>{console.error(e);process.exitCode=1;});
