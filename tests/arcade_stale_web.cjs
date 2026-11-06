// Exercise retained production DOM callbacks after session / room / frame changes.
const {chromium}=require(process.env.ARCADE_PLAYWRIGHT||'playwright-core');const {spawn}=require('node:child_process');const fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..'),out=path.join(root,'docs/review-assets/ANIME-ARCADE-20261106');
const server=spawn(process.env.ARCADE_PYTHON||'D:/Project/321_FISH/.venv/Scripts/python.exe',[path.join(__dirname,'arcade_web_server.py')],{cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});
(async()=>{let browser;try{
 const port=await new Promise((res,rej)=>{server.stdout.once('data',d=>res(Number(String(d).trim())));server.once('exit',c=>rej(Error('Fixture exited '+c)));server.stderr.on('data',d=>process.stderr.write(d));});
 browser=await chromium.launch({headless:true,executablePath:process.env.ARCADE_CHROMIUM||'C:/Users/liang/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe'});const page=await browser.newPage();await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());await page.goto('http://127.0.0.1:'+port);
 const report=await page.evaluate(()=>{
  const original=gameAPI,tests=[];let calls=[];gameAPI=(op,payload)=>{calls.push({op,action:payload.action});return Promise.resolve({ok:true});};
  const cases={
   halloween:{s:{game:'halloween',status:'playing',turn:7,score:{7:0,8:0},left:{7:10,8:10},counts:{'🍓':5},area:['🍓'],flipped:true,can_slap:true},selector:'.orch-bell'},
   yahtzee:{s:{game:'yahtzee',status:'playing',players:[7,8],turn_uid:7,round:1,rolled:false,dice:[1,1,1,1,1],scores:{7:{},8:{}},totals:{7:0,8:0}},selector:'.yacht-cup'},
   drawguess:{s:{game:'drawguess',status:'drawing',drawer_uid:7,round:1,scores:{7:0,8:0},strokes:[]},selector:'.atelier-clear'},
   calc24:{s:{game:'calc24',status:'answering',round:1,players:[7,8],scores:{7:0,8:0},cards:[1,2,3,4]},selector:'.calc-workbench',form:true},
   guess_number:{s:{game:'guess_number',status:'playing',round:1,owner_uid:8,low:1,high:100,scores:{7:0,8:0}},selector:'.number-card'},
   tile2048:{s:{game:'tile2048',status:'playing',players:[7],turn_uid:7,board:[[2,2,0,0],[0,0,0,0],[0,0,0,0],[0,0,0,0]],score:0},selector:'.t2048-btn'}
  };
  try{for(const [game,config] of Object.entries(cases))for(const mutation of ['current','token','room-object','round','uid','snapshot','room-id','closed']){
   const s=structuredClone(config.s),r={game,room_id:'SYNTHETIC',round:1,status:'playing',players:[7,8],spectators:[9]};state.groom=r.room_id;state.token='synthetic-session';state.uid=7;state.gst={room:r,state:s};state.gpriv={word:'合成画题'};
   const box=document.createElement('div');GRENDER[game](box,s);document.body.append(box);const target=box.querySelector(config.selector);if(!target||target.disabled)throw Error(game+' has no live action');
   if(config.form)box.querySelector('input').value='(1+2+3)*4';const callback=config.form?()=>target.onsubmit({preventDefault(){}}):()=>target.onclick({preventDefault(){}});
   if(mutation==='token')state.token='synthetic-relogin';if(mutation==='room-object')state.gst.room={...r};if(mutation==='round')r.round++;
   if(mutation==='uid')state.uid=8;if(mutation==='snapshot')state.gst.state={...s};if(mutation==='room-id')state.groom='OTHER';if(mutation==='closed')state.gst=null;
   calls=[];callback();const count=calls.length;if(count!==(mutation==='current'?1:0))throw Error(game+' '+mutation+' submitted '+count);
   tests.push({game,mutation,submissions:count});box.remove();
  }}finally{gameAPI=original;}return {tests,total:tests.length,all_passed:true};
 });fs.writeFileSync(path.join(out,'arcade-web-stale-callbacks.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({total:report.total,all_passed:report.all_passed}));
}finally{if(browser)await browser.close();server.kill();}})().catch(e=>{console.error(e);process.exitCode=1;});
