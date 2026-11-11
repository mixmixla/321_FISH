const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const cfg=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
process.env.PLAYWRIGHT_BROWSERS_PATH=cfg.cache;
const {chromium}=require(cfg.module);
(async()=>{
 const browser=await chromium.launch({headless:true}),context=await browser.newContext({viewport:{width:1040,height:780}});
 try{
  await context.addCookies([{name:'mt_token',value:cfg.token,url:cfg.url}]);
  const page=await context.newPage(),errors=[],actions=[];
  page.on('pageerror',e=>errors.push(String(e)));
  page.on('request',r=>{if(r.url().endsWith('/api/game')&&r.method()==='POST'){const d=r.postDataJSON();if(d.op==='action')actions.push(d.action);}});
  await page.goto(cfg.url,{waitUntil:'networkidle'});
  await page.evaluate(()=>{for(const e of document.body.children)e.style.display='none';
   const host=document.createElement('main');host.id='cards-proof';host.style.cssText='width:100%;max-width:900px;margin:20px auto';document.body.append(host);});
  async function mount(reset=true,uid=cfg.uid,forcePrivate=false){
   const response=await context.request.get(cfg.url+(reset==='finish'?'/__cards/finish-ready':reset?'/__cards/reset':'/__cards/scene'));const scene=await response.json();
   await page.evaluate(({scene,uid,token,forcePrivate})=>{
    state.uid=uid;state.token=token;state.groom=scene.room.room_id;state.gst={room:scene.room,state:scene.state};
    state.gpriv=forcePrivate?scene.private:(scene.state.players.includes(uid)?scene.private:null);
    state.gnicks={};const box=document.getElementById('cards-proof');box.replaceChildren();GRENDER.uno(box,scene.state);
   },{scene,uid,token:cfg.token,forcePrivate});return scene;
  }
  async function clickAndState(locator){
   await Promise.all([page.waitForResponse(r=>r.url().endsWith('/api/game')&&r.request().method()==='POST'),locator.click()]);
   return (await context.request.get(cfg.url+'/__cards/scene')).json();
  }
  let scene=await mount();
  await page.locator('.cu-art').first().evaluate(async e=>{const url=getComputedStyle(e).backgroundImage.slice(5,-2);const im=new Image();im.src=url;await im.decode();if(!im.naturalWidth)throw new Error('Missing actual art');});
  await page.locator('#cards-proof').screenshot({path:path.join(cfg.out,'uno-web-desktop.png')});
  const duplicates=scene.private.hand.map((v,i)=>[v,scene.private.hand_ids[i]]).filter(v=>v[0]==='红7');assert.equal(duplicates.length,2);assert.notEqual(duplicates[0][1],duplicates[1][1]);
  assert.equal(await page.locator(`[data-card-id='${duplicates[0][1]}']`).evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(196, 56, 72)');
  await page.evaluate(()=>{window.cardsOldRoom=state.groom;state.groom='CHANGED_ROOM_BEFORE_REPAINT';});
  await page.locator(`[data-card-id='${duplicates[0][1]}']`).click({position:{x:15,y:15}});assert.equal(actions.length,0);
  await page.evaluate(()=>{state.groom=window.cardsOldRoom;state.gst={...state.gst};});
  await page.locator(`[data-card-id='${duplicates[0][1]}']`).click({position:{x:15,y:15}});assert.equal(actions.length,0);
  scene=await mount();
  for(const change of [()=>{state.gst.room.round+=1;},()=>{state.token+='changed';},()=>{state.gst.room={...state.gst.room};},()=>{state.uid+=1000;}]){
   await page.evaluate(change);await page.locator(`[data-card-id='${duplicates[0][1]}']`).click({position:{x:15,y:15}});assert.equal(actions.length,0);scene=await mount();
  }
  await page.evaluate(id=>{const b=document.querySelector(`[data-card-id='${id}']`);b.closest('.cu-table').remove();b.click();},duplicates[0][1]);assert.equal(actions.length,0);scene=await mount();
  scene=await clickAndState(page.locator(`[data-card-id='${duplicates[1][1]}']`));
  assert.equal(scene.state.top,'红7');assert.ok(!scene.private.hand_ids.includes(duplicates[1][1]));assert.ok(scene.private.hand_ids.includes(duplicates[0][1]));
  for(const color of ['red','yellow','green','blue']){
   scene=await mount();const id=scene.private.hand_ids[scene.private.hand.indexOf('万能')];
   await page.locator(`[data-card-id='${id}']`).click({position:{x:15,y:15}});assert.equal(await page.locator('.cu-picker').count(),1);
   await page.locator('#cards-proof').screenshot({path:path.join(cfg.out,`uno-web-picker-${color}.png`)});
   scene=await clickAndState(page.locator(`[data-color='${color}']`));assert.equal(scene.state.top_color,color);assert.ok(!scene.private.hand_ids.includes(id));
  }
  scene=await mount();const count=scene.private.hand.length;scene=await clickAndState(page.locator('[data-action=draw]'));assert.equal(scene.private.hand.length,count+1);
  // Illegal +4 is disabled, then all-new true state permits a regular card.
  scene=await mount();const plus=scene.private.hand_ids[scene.private.hand.indexOf('万能+4')];assert.equal(await page.locator(`[data-card-id='${plus}']`).isDisabled(),true);
  await clickAndState(page.locator(`[data-card-id='${duplicates[0][1]}']`));
  scene=await mount(false);assert.equal(await page.locator('.cu-hand button:enabled').count(),0);assert.equal(await page.locator('[data-action=draw]').isDisabled(),true);
  await page.locator('#cards-proof').screenshot({path:path.join(cfg.out,'uno-web-waiting.png')});
  await mount(true,99,true);assert.equal(await page.locator('.cu-hand button').count(),0);assert.equal(await page.locator('#cards-proof button:enabled').count(),0);
  await page.locator('#cards-proof').screenshot({path:path.join(cfg.out,'uno-web-spectator.png')});
  await page.setViewportSize({width:390,height:760});await mount();
  await page.locator('#cards-proof').screenshot({path:path.join(cfg.out,'uno-web-mobile.png')});
  const noOverflow=await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth);assert.equal(noOverflow,true);
  await mount('finish');scene=await clickAndState(page.locator('.cu-hand button').first());assert.equal(scene.state.winner_uid,cfg.uid);
  await mount(false);await page.locator('#cards-proof').screenshot({path:path.join(cfg.out,'uno-web-finished.png')});
  const pendingProbe=await require('./cards_pending_browser.cjs')(page,{game:'uno',selector:'[data-action=draw]',newFrame:()=>mount(true)});
  assert.equal(actions.length,8);assert.equal(errors.length,0,errors.join('\n'));
  const report={actions:actions.length,spectatorHidden:true,mobileNoOverflow:noOverflow,artLoaded:true,duplicateIdsDistinct:true,staleRoomBlocked:true,pendingProbe,packets:actions};
  fs.writeFileSync(path.join(cfg.out,'uno-web-actions.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{await context.close();await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
