const {chromium} = require('playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
(async()=>{
 const [url,out]=process.argv.slice(2), browser=await chromium.launch({headless:true,executablePath:process.env.ANIME_CHROMIUM||undefined});
 const errors=[],context=await browser.newContext({viewport:{width:390,height:844}});
 const page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));
 try{
  await page.goto(url);
  await page.evaluate(()=>{
   document.body.innerHTML='<div id="probe-root"></div>';
   document.body.style.cssText='margin:0;padding:8px;box-sizing:border-box;background:#edf3e8';
   state.uid=1;state.groom='g1';window.probeCalls=[];
   window.probeRefresh=async(uid=state.uid)=>{
    const p=await (await fetch('/probe/state/'+uid)).json();
    state.uid=uid;state.gst={room:p.room,state:p.state};state.gpriv=p.private;
    const box=document.querySelector('#probe-root');box.innerHTML='';GRENDER.dou(box,p.state);
   };
   renderGamePanel=()=>window.probeRefresh();
   gameAPI=async(op,payload)=>{
    window.probeCalls.push(payload.action);
    const r=await(await fetch('/probe/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({uid:state.uid,action:payload.action})})).json();
    if(!r.ok)throw new Error(r.error);await window.probeRefresh();
   };
  });
  const refresh=uid=>page.evaluate(uid=>window.probeRefresh(uid),uid);
  const cell=(x,y)=>page.locator(`.dou-cell[data-x="${x}"][data-y="${y}"]`);
  const shot=name=>page.screenshot({path:path.join(out,name+'.png'),fullPage:true});
  await refresh(1);await page.locator('.dou-portrait').first().waitFor();
  await page.evaluate(async()=>{const img=new Image();img.src='/game-art/dou-beastgirls.webp';await img.decode()});
  assert.equal(await page.locator('.dou-portrait').count(),16);
  await shot('web-initial-390');
  await cell(0,2).click();await page.waitForFunction(()=>document.querySelector('.dou-cell[data-selected=true]'));
  assert.ok(await page.locator('.dou-cell[data-legal=true]').count());await shot('web-decision-390');
  await cell(0,3).click();await page.waitForFunction(()=>state.gst.state.board[3][0]===1);
  await refresh(2);await cell(6,6).click();await page.waitForFunction(()=>state.gsel&&state.gsel[0]===6);
  await cell(6,5).click();await page.waitForFunction(()=>state.gst.state.board[5][6]===11);await shot('web-player2-390');
  await refresh(3);const count=await page.evaluate(()=>probeCalls.length);await cell(0,3).click({force:true});await cell(0,4).click({force:true});
  assert.equal(await page.evaluate(()=>probeCalls.length),count);assert.match(await page.locator('.dou-identity').innerText(),/旁观者/);await shot('web-spectator-390');
  await page.request.post(url+'/probe/fixture',{data:{name:'capture'}});await refresh(1);
  await cell(0,2).click();await page.waitForFunction(()=>state.gsel);await cell(0,1).click();await page.waitForFunction(()=>state.gst.state.last_event?.kind==='eat');
  await refresh(2);await cell(6,6).click();await page.waitForFunction(()=>state.gsel);await cell(6,7).click();await page.waitForFunction(()=>state.gst.state.board[7][6]===17);await shot('web-captures-390');
  await page.request.post(url+'/probe/fixture',{data:{name:'den'}});await refresh(1);
  await cell(3,7).focus();await page.keyboard.press('Enter');await page.waitForFunction(()=>state.gsel);
  await cell(3,7).focus();await page.keyboard.press('ArrowDown');assert.equal(await page.evaluate(()=>document.activeElement.dataset.y),'8');
  await page.keyboard.press('Enter');await page.waitForFunction(()=>state.gst.state.winner_uid===1);await shot('web-finished-390');
  const rects=await page.locator('.dou-cell').evaluateAll(es=>es.map(e=>{const r=e.getBoundingClientRect();return [r.left,r.right]}));
  assert.ok(rects.every(([left,right])=>left>=0&&right<=390));
  const before=await page.evaluate(()=>probeCalls.length);await cell(3,8).click({force:true});assert.equal(await page.evaluate(()=>probeCalls.length),before);
  await page.setViewportSize({width:1000,height:900});await refresh(1);await shot('web-finished-wide');
  assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:true,viewports:[390,1000],nativeKeyboard:true,actions:await page.evaluate(()=>probeCalls)}));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
