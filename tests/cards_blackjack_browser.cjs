const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const cfg=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));process.env.PLAYWRIGHT_BROWSERS_PATH=cfg.cache;
const {chromium}=require(cfg.module);
(async()=>{const browser=await chromium.launch({headless:true}),context=await browser.newContext({viewport:{width:1040,height:780}});
 try{await context.addCookies([{name:'mt_token',value:cfg.token,url:cfg.url}]);const page=await context.newPage(),errors=[],actions=[];
  page.on('pageerror',e=>errors.push(String(e)));page.on('request',r=>{if(r.url().endsWith('/api/game')&&r.method()==='POST'){const d=r.postDataJSON();if(d.op==='action')actions.push(d.action);}});
  await page.goto(cfg.url,{waitUntil:'networkidle'});await page.evaluate(()=>{for(const e of document.body.children)e.style.display='none';const e=document.createElement('main');e.id='cards-proof';e.style.cssText='width:100%;max-width:900px;margin:20px auto';document.body.append(e);});
  async function mount(uid=cfg.uid,token=cfg.token,reset=false){const scene=await (await context.request.get(cfg.url+(reset?'/__cards/reset':'/__cards/scene'))).json();
   await page.evaluate(({scene,uid,token})=>{state.uid=uid;state.token=token;state.gst=scene;state.groom=scene.room.room_id;state.gpriv=null;state.gnicks={};const root=document.getElementById('cards-proof');root.replaceChildren();GRENDER.blackjack(root,scene.state);},{scene,uid,token});return scene;}
  async function act(op,keyboard=false){const b=page.locator(`[data-action=${op}]`);const request=page.waitForResponse(r=>r.url().endsWith('/api/game')&&r.request().method()==='POST');
   if(keyboard){await b.focus();await b.press('Enter');}else await b.click();await request;return (await context.request.get(cfg.url+'/__cards/scene')).json();}
  let scene=await mount();assert.deepEqual(scene.state.dealer,['背牌','7♦']);assert.equal(scene.state.dealer_value,7);assert.equal(await page.locator('.bc-dealer-hand .back').count(),1);
  await page.locator('.bc-portrait').evaluate(async e=>{const value=getComputedStyle(e).backgroundImage;const image=new Image();image.src=value.slice(5,-2);await image.decode();});
  await page.locator('#cards-proof').screenshot({path:path.join(cfg.out,'blackjack-web-start.png')});
  await page.evaluate(()=>{window.cardsOldRoom=state.groom;state.groom='CHANGED_ROOM_BEFORE_REPAINT';});
  await page.locator('[data-action=hit]').click();assert.equal(actions.length,0);
  await page.evaluate(()=>{state.groom=window.cardsOldRoom;state.gst={...state.gst};});
  await page.locator('[data-action=hit]').click();assert.equal(actions.length,0);await mount();
  for(const change of [()=>{state.gst.room.round+=1;},()=>{state.token+='changed';},()=>{state.gst.room={...state.gst.room};},()=>{state.uid+=1000;}]){
   await page.evaluate(change);await page.locator('[data-action=hit]').click();assert.equal(actions.length,0);await mount();
  }
  await page.evaluate(()=>{const b=document.querySelector('[data-action=hit]');b.closest('.bc-table').remove();b.click();});assert.equal(actions.length,0);await mount();
  scene=await act('hit');assert.equal(scene.state.hand_values[cfg.uid],18);assert.equal(scene.state.deck_remaining,2);await mount();
  await page.locator('#cards-proof').screenshot({path:path.join(cfg.out,'blackjack-web-hit.png')});
  scene=await act('stand',true);assert.equal(scene.state.current_uid,cfg.other);await mount();assert.equal(await page.locator('[data-action=hit]').isDisabled(),true);
  await page.setViewportSize({width:390,height:760});await mount();
  await page.locator('#cards-proof').screenshot({path:path.join(cfg.out,'blackjack-web-mobile.png')});
  const mobileNoOverflow=await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth);assert.ok(mobileNoOverflow);
  await mount(99);assert.equal(await page.locator('[data-action=hit]').isDisabled(),true);assert.equal(await page.locator('[data-action=stand]').isDisabled(),true);
  await page.locator('#cards-proof').screenshot({path:path.join(cfg.out,'blackjack-web-spectator.png')});
  await context.addCookies([{name:'mt_token',value:cfg.otherToken,url:cfg.url}]);await mount(cfg.other,cfg.otherToken);scene=await act('stand');
  assert.equal(scene.state.status,'round_end');assert.deepEqual(scene.state.dealer,['9♣','7♦','2♠']);assert.equal(scene.state.dealer_value,18);assert.equal(scene.state.results[cfg.uid],'push');assert.equal(scene.state.results[cfg.other],'win');
  await mount(cfg.other,cfg.otherToken);assert.equal(await page.locator('.bc-dealer-hand .back').count(),0);
  await page.locator('#cards-proof').screenshot({path:path.join(cfg.out,'blackjack-web-finished.png')});
  await context.addCookies([{name:'mt_token',value:cfg.token,url:cfg.url}]);
  const pendingProbe=await require('./cards_pending_browser.cjs')(page,{game:'blackjack',selector:'[data-action=hit]',newFrame:()=>mount(cfg.uid,cfg.token,true)});
  assert.equal(actions.length,3);assert.equal(errors.length,0,errors.join('\n'));
  const report={actions:actions.length,holeHidden:true,revealed:true,mobileNoOverflow,pendingProbe,packets:actions};fs.writeFileSync(path.join(cfg.out,'blackjack-web-actions.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{await context.close();await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
