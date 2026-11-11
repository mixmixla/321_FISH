const fs=require('node:fs'),cp=require('node:child_process'),path=require('node:path'),assert=require('node:assert/strict');
const [port,out,control]=process.argv.slice(2),game='kaituo',url='http://127.0.0.1:'+port;fs.mkdirSync(out,{recursive:true});const delay=ms=>new Promise(r=>setTimeout(r,ms));
const profile=path.resolve('_tmp_gui/economy-production-'+game+'-'+Date.now()),proc=cp.spawn('C:/Users/liang/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe',['--headless=new','--disable-gpu','--no-first-run','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:'ignore'});
const errors=[],tabs=[],wire=[];let root;
async function socket(url){const ws=new WebSocket(url);await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j});let id=0;const pending=new Map();ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.method==='Network.requestWillBeSent'&&m.params.request.url.endsWith('/api/game')&&m.params.request.postData){const p=JSON.parse(m.params.request.postData);if(p.op==='action'){const {_kt_request,...action}=p.action;wire.push({uid:channel.uid,room_id:p.room_id,action});}}if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text);const p=pending.get(m.id);if(p){pending.delete(m.id);m.error?p.j(Error(JSON.stringify(m.error))):p.r(m.result);}};const channel={ws,call(method,params={}){return new Promise((r,j)=>{const n=++id;pending.set(n,{r,j});ws.send(JSON.stringify({id:n,method,params}));});}};return channel;}
async function run(t,expression){const r=await t.call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;}
async function wait(t,expression){for(let i=0;i<160;i++){if(await run(t,expression))return;await delay(50);}throw Error('Wait failed: '+expression);}
async function click(t,selector,key=false){const q=JSON.stringify(selector);const b=await run(t,`(()=>{const b=document.querySelector(${q});if(!b)throw Error('Missing '+${q});if(b.disabled)throw Error('Disabled '+${q});b.scrollIntoView({block:'center'});b.focus();const r=b.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2};})()`);if(key){await t.call('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,text:'\r',unmodifiedText:'\r'});await t.call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});}else if(t.width===390){await t.call('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[b]});await t.call('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});}else{await t.call('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...b});await t.call('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...b});}await delay(65);}
async function shot(t,name){await run(t,'document.querySelector("#gmain").scrollTop=0');const r=await t.call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(path.join(out,name+'.png'),Buffer.from(r.data,'base64'));}
async function api(t,op,extra={}){return run(t,`gameAPI(${JSON.stringify(op)},${JSON.stringify(extra)})`);}
async function tab(nick,width){const ctx=await root.call('Target.createBrowserContext'),target=await root.call('Target.createTarget',{url:'about:blank',browserContextId:ctx.browserContextId});const endpoint='ws://127.0.0.1:'+root.port+'/devtools/page/'+target.targetId,t=await socket(endpoint);t.width=width;
 await t.call('Page.enable');await t.call('Runtime.enable');await t.call('Network.enable');await t.call('Emulation.setFocusEmulationEnabled',{enabled:true});await t.call('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width===390});await t.call('Page.navigate',{url});await wait(t,'typeof enterMain==="function"&&typeof GRENDER!=="undefined"');t.uid=await run(t,`(async()=>{const d=await(await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({nick:${JSON.stringify(nick)}})})).json();if(!d.ok)throw Error(JSON.stringify(d));enterMain(d);return d.uid})()`);tabs.push(t);return t;}
(async()=>{try{
 let lines;for(let i=0;i<100;i++){try{lines=fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n');break}catch{}await delay(100);}assert.ok(lines);root=await socket('ws://127.0.0.1:'+lines[0]+lines[1]);root.port=lines[0];
 const a=await tab('合成开拓甲',1024),b=await tab('合成开拓乙',390),observer=await tab('合成开拓旁观',390),players=[a,b];
 await api(a,'create',{game:'kaituo'});await wait(a,'state.groom&&state.gst?.room.game==="kaituo"');const rid=await run(a,'state.groom');await api(b,'join',{room_id:rid});await api(observer,'spectate',{room_id:rid});await api(a,'start',{room_id:rid});for(const t of tabs)await wait(t,'!!document.querySelector(".kt-table")');
 async function inject(stage){const s=await(await fetch('http://127.0.0.1:'+control+'/'+stage,{method:'POST'})).json();for(const t of tabs){await api(t,'sync',{room_id:rid});await wait(t,'JSON.stringify(state.gst.state)==='+JSON.stringify(JSON.stringify(s)));}return s;}
 async function act(t,action,fn){const count=wire.length,before=await run(t,'JSON.stringify(state.gst.state)');await fn();await wait(t,'JSON.stringify(state.gst.state)!=='+JSON.stringify(before));const now=await run(t,'JSON.stringify(state.gst.state)');for(const x of tabs)await wait(x,'JSON.stringify(state.gst.state)==='+JSON.stringify(now));assert.equal(wire.length,count+1);assert.deepEqual(wire.at(-1).action,action);}
 await inject('seed');await delay(250);
 const styles=await run(b,`(()=>{
   const theme=document.documentElement.dataset.theme;
   document.documentElement.dataset.theme='mist';
   const css=document.createElement('style');css.textContent='.kt2-map .kt2-land{background-image:url(/game-art/economy-kaituo-terrain-v2.webp)}';document.head.appendChild(css);
   const panel=document.createElement('div');panel.className='kt2-map';const old=document.createElement('button');old.disabled=true;old.className='kt2-land';panel.appendChild(old);document.body.appendChild(panel);
   const legacy=getComputedStyle(old).backgroundImage;
   const terrain=[...document.querySelectorAll('.kt-terrain')].map(el=>getComputedStyle(el).backgroundImage);
   const seat=document.querySelector('.kt-seat'),colour=getComputedStyle(seat).color,background=getComputedStyle(seat).backgroundColor;
   css.remove();panel.remove();document.documentElement.dataset.theme=theme;
   return {legacy,terrain,colour,background,theme};
 })()`);
 assert.equal(styles.legacy,'none');assert.equal(styles.terrain.length,25);assert.ok(styles.terrain.every(x=>x.includes('economy-kaituo-terrain-v2.webp')));
 fs.writeFileSync(path.join(out,'computed-style-390.json'),JSON.stringify(styles,null,2));await shot(a,'production-initial');await shot(b,'production-initial-390');
 const setups=[[[0,0],[0,1]],[[5,5],[5,4]],[[5,3],[4,3]],[[0,2],[0,3]]];
 for(let i=0;i<4;i++){const uid=await run(a,'state.gst.state.turn_uid'),t=players.find(t=>t.uid===uid),[v,end]=setups[i];await click(t,'[data-vertex="'+v.join(',')+'"]');if(!i)await shot(t,'production-decision');await act(t,{op:'setup',i:v[0],j:v[1],b_i:end[0],b_j:end[1]},()=>click(t,'[data-edge="'+[v.join(','),end.join(',')].sort().join('>')+'"]'));}
 assert.equal(await run(a,'state.gst.state.phase'),'play');await act(a,{op:'roll'},()=>click(a,'[data-control="roll"]',true));assert.equal(await run(a,'state.gst.state.last_roll'),7);assert.equal(await run(a,'state.gst.state.robber_pending'),true);await act(a,{op:'robber',r:0,c:0},()=>click(a,'[data-land="0,0"]'));
 await inject('produce');await act(a,{op:'roll'},()=>click(a,'[data-control="roll"]',true));assert.deepEqual(await run(a,'state.gst.state.last_dice'),[5,3]);assert.ok(await run(a,'document.querySelectorAll(".kt-produced").length>0'));await shot(a,'production-real-dice-and-producers');
 await inject('fund');
 const priorRoomActionCount = wire.length;
 const protectedSwitch = await run(a,`(()=>{
   const previous = state.groom;
   const oldFrame = state.gst;
   const oldButton = document.querySelector('[data-control="skip"]');
   if (!oldButton || oldButton.disabled) throw Error('Fixture did not have a playable turn');
   state.groom = 'unmatched-room';
   oldButton.click();
   renderGamePanel();
   const redrawn = document.querySelector('[data-control="skip"]');
   if (redrawn) redrawn.click();
   const protected = state.gst === oldFrame && (!redrawn || redrawn.disabled);
   state.groom = previous;
   renderGamePanel();
   return protected;
 })()`);
 assert.equal(protectedSwitch,true);
 await delay(120);
 assert.equal(wire.length,priorRoomActionCount);
 await click(a,'[data-mode="settle"]');await shot(a,'production-settlement-before');await act(a,{op:'build',kind:'settle',i:0,j:4},()=>click(a,'[data-vertex="0,4"]'));assert.equal(await run(a,'state.gst.state.res[state.uid].wood'),11);await shot(a,'production-settlement-after');
 await click(a,'[data-mode="road"]');await act(a,{op:'build',kind:'road',i:0,j:0,b_i:1,b_j:0},()=>click(a,'[data-edge="0,0>1,0"]'));
 await click(a,'[data-give="wood"]');await click(a,'[data-want="ore"]');const trade=await a.call('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(out,'production-trade-before-1024.png'),Buffer.from(trade.data,'base64'));
 await a.call('Emulation.setDeviceMetricsOverride',{width:390,height:900,deviceScaleFactor:1,mobile:true});a.width=390;await click(a,'[data-tab="harbour"]');await run(a,'document.querySelector(".kt-harbour").scrollIntoView({block:"center"})');fs.writeFileSync(path.join(out,'trade-ready-state.json'),JSON.stringify(await run(a,'state.gst.state'),null,2));const mobileBefore=await a.call('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(out,'production-trade-before-390.png'),Buffer.from(mobileBefore.data,'base64'));
 await act(a,{op:'trade',give:'wood',want:'ore',n:4},()=>click(a,'[data-control="swap"]'));assert.equal(await run(a,'state.gst.state.res[state.uid].wood'),6);assert.equal(await run(a,'state.gst.state.res[state.uid].ore'),13);await run(a,'document.querySelector(".kt-harbour").scrollIntoView({block:"center"})');const mobileAfter=await a.call('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(out,'production-trade-after-390.png'),Buffer.from(mobileAfter.data,'base64'));
 await a.call('Emulation.setDeviceMetricsOverride',{width:1024,height:900,deviceScaleFactor:1,mobile:false});a.width=1024;await run(a,'document.querySelector(".kt-harbour").scrollIntoView({block:"center"})');const after=await a.call('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(out,'production-trade-after-1024.png'),Buffer.from(after.data,'base64'));
 // Delay one real request while a value-identical public frame is drawn again.
 await click(a,'[data-give="wood"]');
 await click(a,'[data-want="ore"]');
 const beforeRejected=wire.length;
 const phase=async name=>{const response=await fetch('http://127.0.0.1:'+control+'/'+name,{method:'POST'});assert.equal(response.status,200);};
 await phase('block-wood');
 await run(a,`(()=>{
   const original=gameAPI;
   window.kaituoSendCount=0;
   gameAPI=(op,extra,quiet)=>{
     if(op==='action'&&extra.action.op==='trade'){
       window.kaituoSendCount++;
       return new Promise((resolve,reject)=>{
         window.kaituoFlush=()=>{gameAPI=original;return original(op,extra,quiet).then(resolve,reject);};
       });
     }
     return original(op,extra,quiet);
   };
 })()`);
 await click(a,'[data-control="swap"]');
 assert.equal(await run(a,`(()=>{
   state.gst={...state.gst,state:{...state.gst.state}};
   renderGamePanel();
   const seal=document.querySelector('[data-control="swap"]');
   const disabled=seal.disabled;
   seal.click();
   return disabled && window.kaituoSendCount===1;
 })()`),true);
 assert.equal(wire.length,beforeRejected);
 await run(a,'window.kaituoFlush()');
 await wait(a,`!document.querySelector('[data-control="swap"]').disabled`);
 assert.equal(wire.length,beforeRejected+1);
 await phase('restore-wood');
 await act(a,{op:'trade',give:'wood',want:'ore',n:4},()=>click(a,'[data-control="swap"]'));
 assert.equal(await run(a,'state.gst.state.res[state.uid].wood'),2);
 assert.equal(await run(a,'state.gst.state.res[state.uid].ore'),14);
 await click(a,'[data-mode="city"]');await act(a,{op:'build',kind:'city',i:0,j:0},()=>click(a,'[data-vertex="0,0"]'));await shot(a,'production-progress');await shot(b,'production-progress-390');await shot(observer,'production-spectator-390');
 assert.equal(await run(observer,'[...document.querySelectorAll(".kt-table button:not(.kt-tab)")].filter(b=>!b.disabled).length'),0);for(const t of tabs){assert.equal(await run(t,'document.querySelectorAll(".kt-table input,.kt-table select").length'),0);assert.equal(await run(t,'document.documentElement.scrollWidth<=innerWidth'),true);}
 await act(a,{op:'skip'},()=>click(a,'[data-control="skip"]'));
 assert.equal(await run(b,'state.gst.state.turn_uid===state.uid'),true);
 assert.equal(await run(b,'[...document.querySelectorAll(".kt-die")].every(d=>d.dataset.face==="")'),true);
 await inject('nearwin');await click(a,'[data-mode="city"]');await act(a,{op:'build',kind:'city',i:2,j:2},()=>click(a,'[data-vertex="2,2"]'));assert.equal(await run(a,'state.gst.state.winner_uid'),a.uid);assert.equal(await run(a,'state.gst.state.score[state.uid]'),10);await shot(a,'production-finished');await shot(b,'production-finished-390');assert.deepEqual(errors,[]);
 fs.writeFileSync(path.join(out,'production-final-state.json'),JSON.stringify({room:await run(a,'state.gst.room'),state:await run(a,'state.gst.state')},null,2));const report={game:'kaituo',production_http:true,production_sse:true,players:2,spectators:1,viewports:[1024,390],real_keyboard_roll:true,real_object_clicks:true,room_switch_with_old_redraw_blocked:true,same_revision_redraw_blocked:true,correlated_sse_rejection_retry:true,next_turn_blank_faces:true,actual_request_payloads_verified:true,fixtures:['deterministic seed1 normal setup and first dice','separate seeded actual [5,3] roll for real production highlighting','explicit funded midgame for build/trade','separate synthetic nine-point state before real city-upgrade terminal action'],natural_full_game_claim:false,actions:wire,exceptions:errors};fs.writeFileSync(path.join(out,'production-actions.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({game:'kaituo',actions:wire.length,production_http:true,production_sse:true,exceptions:errors}));
 }finally{if(root){try{await Promise.race([root.call('Browser.close'),delay(1700)])}catch{}root.ws.close();}for(const t of tabs)t.ws.close();if(proc.exitCode===null)proc.kill();}})().catch(e=>{console.error(e);process.exitCode=1});
