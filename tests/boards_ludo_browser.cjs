// Native Node CDP, no browser plugin or foreground surface; production HTTP/SSE.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{spawn}=require('node:child_process');
const [port,browser,profile,output,controlPort]=process.argv.slice(2),url='http://127.0.0.1:'+port;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
class CDP{
 constructor(ws){this.ws=ws;this.id=0;this.pending=new Map();this.exceptions=[];ws.addEventListener('message',e=>{const d=JSON.parse(e.data);
   if(d.id){const p=this.pending.get(d.id);if(p){this.pending.delete(d.id);d.error?p.reject(Error(JSON.stringify(d.error))):p.resolve(d.result)}}
   if(d.method==='Runtime.exceptionThrown')this.exceptions.push(d.params.exceptionDetails.text+':'+JSON.stringify(d.params.exceptionDetails.exception));});}
 static async open(url){const ws=new WebSocket(url);await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true})});return new CDP(ws)}
 async send(method,params={},sessionId){const id=++this.id;const result=new Promise((resolve,reject)=>this.pending.set(id,{resolve,reject}));this.ws.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{} )}));return result}
 close(){this.ws.close()}
}
(async()=>{
 fs.mkdirSync(profile,{recursive:true});fs.mkdirSync(output,{recursive:true});
 const child=spawn(browser,['--headless','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-sync','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:['ignore','ignore','pipe']});
 let stderr='';child.stderr.on('data',d=>stderr+=d);
 let cdp;
 try{
  const active=path.join(profile,'DevToolsActivePort');for(let i=0;i<100&&!fs.existsSync(active);i++)await sleep(100);
  assert.ok(fs.existsSync(active),'headless shell did not start: '+stderr);
  const [debugPort,wsPath]=fs.readFileSync(active,'utf8').trim().split('\n');cdp=await CDP.open('ws://127.0.0.1:'+debugPort+wsPath);
  const tabs=[];
  async function tab(nick,width=1150,height=950){
   const {browserContextId}=await cdp.send('Target.createBrowserContext');const {targetId}=await cdp.send('Target.createTarget',{url:'about:blank',browserContextId});
   const {sessionId}=await cdp.send('Target.attachToTarget',{targetId,flatten:true});const send=(m,p)=>cdp.send(m,p,sessionId);
   await send('Runtime.enable');await send('Page.enable');await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<500});
   const ev=async expression=>{const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value};
   const wait=async expression=>{for(let i=0;i<120;i++){if(await ev(expression))return;await sleep(80)}throw Error('Timeout: '+expression)};
   await send('Page.navigate',{url});await wait("typeof enterMain==='function'&&typeof BoardsLudo==='object'");
   const uid=await ev(`(async()=>{const d=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({nick:${JSON.stringify(nick)}})}).then(r=>r.json());if(!d.ok)throw Error(JSON.stringify(d));enterMain(d);return d.uid})()`);
   await sleep(150);
   const click=async selector=>{const rect=await ev(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});if(!e||e.disabled)throw Error('Missing/enabled '+${JSON.stringify(selector)});e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()`);
    await send('Input.dispatchMouseEvent',{type:'mousePressed',...rect,button:'left',clickCount:1});await send('Input.dispatchMouseEvent',{type:'mouseReleased',...rect,button:'left',clickCount:1});};
   const shot=async name=>{await ev("document.querySelector('.ld-root').scrollIntoView({block:'center'})");await sleep(120);const clip=await ev("(()=>{const r=document.querySelector('.ld-root').getBoundingClientRect();return {x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height,scale:1}})()");
    const r=await send('Page.captureScreenshot',{format:'png',clip,captureBeyondViewport:true});fs.writeFileSync(path.join(output,name),Buffer.from(r.data,'base64'));};
   const api=async(op,extra={})=>ev(`gameAPI(${JSON.stringify(op)},${JSON.stringify(extra)})`);
   const item={uid,send,ev,wait,click,shot,api};tabs.push(item);return item;
  }
  async function staleGuard(page,selector){
   return page.ev(`(()=>{
    const e=document.querySelector(${JSON.stringify(selector)}),root=document.querySelector('.ld-root'),parent=root.parentNode,next=root.nextSibling;
    const elementParent=e.parentNode,elementNext=e.nextSibling;
    const saved={token:state.token,uid:state.uid,groom:state.groom,gst:state.gst},api=gameAPI,calls=[],checks=[];
    gameAPI=(...args)=>{calls.push(args);return Promise.resolve({ok:true})};
    const restore=()=>{state.token=saved.token;state.uid=saved.uid;state.groom=saved.groom;state.gst=saved.gst;if(!root.isConnected)parent.insertBefore(root,next);if(!e.isConnected)elementParent.insertBefore(e,elementNext)};
    try{
     e.onclick();if(calls.length!==1)throw Error('Current object did not submit');calls.length=0;
     const tests=[
      ['token',()=>{state.token='synthetic-replaced-token'}],
      ['room_object',()=>{state.gst={...saved.gst,room:{...saved.gst.room}}}],
      ['round',()=>{state.gst={...saved.gst,room:{...saved.gst.room,round:saved.gst.room.round+1}}}],
      ['room_id',()=>{state.groom='synthetic-different-room'}],
      ['frame',()=>{state.gst={...saved.gst,state:{...saved.gst.state}}}],
      ['account',()=>{state.uid=9999}],
      ['membership',()=>{state.gst={...saved.gst,room:{...saved.gst.room,players:[],spectators:[saved.uid]}}}],
      ['destroyed_button',()=>e.remove()],
      ['destroyed_table',()=>root.remove()]
     ];
     for(const [name,change] of tests){restore();change();e.onclick();if(calls.length)throw Error('Stale object sent for '+name);checks.push(name)}
     restore();e.onclick();if(calls.length!==1)throw Error('Restored current object blocked');return checks;
    }finally{restore();gameAPI=api}
   })()`);
  }
  const a=await tab('合成红机队'),b=await tab('合成蓝机队',390,844),c=await tab('合成观战',390,844);
  await a.api('create',{game:'ludo'});await a.wait("state.groom&&state.gst&&state.gst.room.game==='ludo'");const room=await a.ev('state.groom');
  await b.api('join',{room_id:room});await c.api('spectate',{room_id:room});await a.api('start',{room_id:room});
  for(const t of tabs)await t.wait("document.querySelectorAll('.ld-plane').length===8");
  await a.shot('ludo-web-before.png');await b.shot('ludo-web-mobile-wait.png');
  await a.send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await a.shot('ludo-web-mobile-before.png');
  assert.equal(await c.ev("document.querySelectorAll('.ld-root button:not(:disabled)').length"),0);
  const dieGuards=await staleGuard(a,'.ld-die');
  await a.click('.ld-die');await a.wait('state.gst.state.dice===6');
  const planeGuards=await staleGuard(a,`.ld-plane[data-uid="${a.uid}"][data-plane="0"]`);
  await a.shot('ludo-web-mobile-six.png');
  const launch=await a.ev(`(()=>{const e=document.querySelector('.ld-plane[data-uid="${a.uid}"][data-plane="0"]');const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()`);
  await a.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[launch]});await a.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  await a.wait(`state.gst.state.positions[${JSON.stringify(String(a.uid))}][0]===0&&state.gst.state.dice==null`);
  await a.shot('ludo-web-mobile-launch.png');
  // Browser keyboard against its own focused board, then actual aircraft click.
  await a.ev("document.querySelector('.ld-root').focus()");await a.send('Input.dispatchKeyEvent',{type:'keyDown',key:'r',code:'KeyR',text:'r'});await a.send('Input.dispatchKeyEvent',{type:'keyUp',key:'r',code:'KeyR'});
  await a.wait('state.gst.state.dice===1');await a.shot('ludo-web-mobile-decision.png');await a.click(`.ld-plane[data-uid="${a.uid}"][data-plane="0"]`);
  for(const t of tabs)await t.wait(`state.gst.state.positions[${JSON.stringify(String(a.uid))}][0]===1&&state.gst.state.turn_uid===${b.uid}`);
  await a.shot('ludo-web-mobile-landed.png');await b.shot('ludo-web-mobile-turn.png');await c.shot('ludo-web-spectator.png');
  await a.send('Emulation.setDeviceMetricsOverride',{width:1150,height:950,deviceScaleFactor:1,mobile:false});
  await a.shot('ludo-web-moved.png');
  // Real mobile touch on the blue player's die, with server state broadcast back.
  const touch=await b.ev("(()=>{const e=document.querySelector('.ld-die');e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()");
  await b.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[touch]});await b.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  await b.wait(`state.gst.state.turn_uid===${a.uid}`); // seed19 third roll is 5; no blue plane can fly.
  assert.equal(await b.ev("document.querySelector('.ld-root').scrollWidth<=document.querySelector('.ld-root').clientWidth+1"),true);
  const firstHand=await a.ev('state.gst.state');
  await fetch('http://127.0.0.1:'+controlPort+'/finish-fixture',{method:'POST'});
  for(const t of tabs)await t.api('sync',{room_id:room});
  await a.wait(`state.gst.state.positions[${JSON.stringify(String(a.uid))}][0]===39`);
  await a.shot('ludo-web-finish-decision.png');
  await a.click(`.ld-plane[data-uid="${a.uid}"][data-plane="0"]`);
  for(const t of tabs)await t.wait(`state.gst.state.winner_uid===${a.uid}`);
  await a.shot('ludo-web-finished.png');await b.shot('ludo-web-mobile-finished.png');
  assert.equal(await a.ev("document.querySelectorAll('.ld-root button:not(:disabled)').length"),0);
  const report={headless:true,production_http:true,production_sse:true,launch:true,move:true,keyboard_roll:true,mobile_touch:true,spectator_read_only:true,
    forty_unique_cells:await a.ev("new Set(Array.from(document.querySelectorAll('[data-stall]')).map(e=>e.dataset.stall)).size===40"),first_hand:firstHand,
    terminal_fixture:'Separate synthetic near-finish fixture; real click finishes exactly at 40',exact_finish:true,stale_die_guards:dieGuards,stale_plane_guards:planeGuards,exceptions:cdp.exceptions};
  assert.equal(report.exceptions.length,0);fs.writeFileSync(path.join(output,'ludo-web-actions.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{if(cdp){try{await cdp.send('Browser.close')}catch(e){}cdp.close()}if(child.exitCode==null){await new Promise(resolve=>{const timer=setTimeout(()=>{child.kill();resolve()},5000);child.once('exit',()=>{clearTimeout(timer);resolve()})})}await sleep(200);}
})().catch(e=>{console.error(e.stack);process.exitCode=1});
