// Native Node CDP, no browser plugin or foreground surface; production HTTP/SSE.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{spawn}=require('node:child_process');
const [port,browser,profile,output]=process.argv.slice(2),url='http://127.0.0.1:'+port;
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
   await send('Page.navigate',{url});await wait("typeof enterMain==='function'&&typeof BoardsBlokus==='object'");
   const uid=await ev(`(async()=>{const d=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({nick:${JSON.stringify(nick)}})}).then(r=>r.json());if(!d.ok)throw Error(JSON.stringify(d));enterMain(d);return d.uid})()`);
   await sleep(150);
   const click=async selector=>{const rect=await ev(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});if(!e||e.disabled)throw Error('Missing/enabled '+${JSON.stringify(selector)});e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()`);
    await send('Input.dispatchMouseEvent',{type:'mousePressed',...rect,button:'left',clickCount:1});await send('Input.dispatchMouseEvent',{type:'mouseReleased',...rect,button:'left',clickCount:1});};
   const shot=async name=>{await ev("document.querySelector('.bk-root').scrollIntoView({block:'center'})");await sleep(120);const clip=await ev("(()=>{const r=document.querySelector('.bk-root').getBoundingClientRect();return {x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height,scale:1}})()");
    const r=await send('Page.captureScreenshot',{format:'png',clip,captureBeyondViewport:true});fs.writeFileSync(path.join(output,name),Buffer.from(r.data,'base64'));};
   const api=async(op,extra={})=>ev(`gameAPI(${JSON.stringify(op)},${JSON.stringify(extra)})`);
   const item={uid,send,ev,wait,click,shot,api};tabs.push(item);return item;
  }
  async function staleGuard(page,selector){
   return page.ev(`(()=>{
    const e=document.querySelector(${JSON.stringify(selector)}),root=document.querySelector('.bk-root'),parent=root.parentNode,next=root.nextSibling;
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
  const a=await tab('合成红拼筑师'),b=await tab('合成蓝拼筑师',390,844),c=await tab('合成观战',390,844);
  await a.api('create',{game:'blokus'});await a.wait("state.groom&&state.gst&&state.gst.room.game==='blokus'");const room=await a.ev('state.groom');
  await b.api('join',{room_id:room});await c.api('spectate',{room_id:room});await a.api('start',{room_id:room});
  for(const t of tabs)await t.wait("document.querySelectorAll('.bk-cell').length===400");
  const guards=await staleGuard(a,'.bk-cell[data-row="0"][data-col="0"]');
  await a.shot('blokus-web-before.png');await b.shot('blokus-web-mobile-wait.png');
  assert.equal(await c.ev("document.querySelectorAll('.bk-root button:not(:disabled)').length"),0);
  await a.click('.bk-tile[data-piece="M"]');await a.click('.bk-cell[data-row="19"][data-col="0"]');
  for(const t of tabs)await t.wait(`state.gst.state.board[19][0]===${a.uid}`);
  await b.click('.bk-tile[data-piece="M"]');
  const touch=await b.ev("(()=>{const e=document.querySelector('.bk-cell[data-row=\"0\"][data-col=\"19\"]');e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()");
  await b.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[touch]});await b.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  await a.wait(`state.gst.state.board[0][19]===${b.uid}`);
  await a.click('.bk-tile[data-piece="D"]');await a.click('.bk-rotate');
  assert.equal(await a.ev('state.boardsBlokus.oi'),1);
  await a.ev("document.querySelector('.bk-root').focus()");await a.send('Input.dispatchKeyEvent',{type:'keyDown',key:'r',code:'KeyR',text:'r'});await a.send('Input.dispatchKeyEvent',{type:'keyUp',key:'r',code:'KeyR'});
  assert.equal(await a.ev('state.boardsBlokus.oi'),0);
  await a.shot('blokus-web-decision.png');
  await a.click('.bk-cell[data-row="17"][data-col="1"]');
  for(const t of tabs)await t.wait(`state.gst.state.board[17][1]===${a.uid}&&state.gst.state.board[18][1]===${a.uid}`);
  await b.shot('blokus-web-mobile-turn.png');await c.shot('blokus-web-spectator.png');
  await b.click('.bk-pass');await a.wait(`state.gst.state.turn_uid===${a.uid}`);await a.click('.bk-pass');
  for(const t of tabs)await t.wait(`state.gst.state.winner_uid===${a.uid}`);
  await a.shot('blokus-web-finished.png');await b.shot('blokus-web-mobile-finished.png');
  assert.equal(await a.ev("document.querySelectorAll('.bk-root button:not(:disabled)').length"),0);
  assert.equal(await b.ev("document.querySelector('.bk-root').scrollWidth<=document.querySelector('.bk-root').clientWidth+1"),true);
  const report={headless:true,production_http:true,production_sse:true,first_corner:true,mobile_touch:true,diagonal_contact:true,rotate:true,keyboard_rotate:true,
    row_column_wire:true,stale_guards:guards,spectator_read_only:true,consecutive_pass_terminal:true,state:await a.ev('state.gst.state'),exceptions:cdp.exceptions};
  assert.equal(report.exceptions.length,0);fs.writeFileSync(path.join(output,'blokus-web-actions.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({game:'blokus',checks:true,exceptions:report.exceptions}));
 }finally{if(cdp){try{await cdp.send('Browser.close')}catch(e){}cdp.close()}if(child.exitCode==null){await new Promise(resolve=>{const timer=setTimeout(()=>{child.kill();resolve()},5000);child.once('exit',()=>{clearTimeout(timer);resolve()})})}await sleep(200);}
})().catch(e=>{console.error(e.stack);process.exitCode=1});
