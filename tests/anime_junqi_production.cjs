const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
(async()=>{
 const [port,out,control]=process.argv.slice(2),url='http://127.0.0.1:'+port;
 const browser=await chromium.launch({headless:true,executablePath:process.env.ANIME_CHROMIUM||undefined}),errors=[],tabs=[];
 try{
  async function tab(nick,width){
   const context=await browser.newContext({viewport:{width,height:900},isMobile:width===390,hasTouch:width===390});
   const p=await context.newPage();p.on('pageerror',e=>errors.push(String(e)));await p.goto(url);
   await p.waitForFunction(()=>typeof enterMain==='function'&&typeof GRENDER.junqi==='function');
   const uid=await p.evaluate(async nick=>{const d=await(await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({nick})})).json();if(!d.ok)throw Error(JSON.stringify(d));enterMain(d);return d.uid},nick);
   const api=(op,extra={})=>p.evaluate(({op,extra})=>gameAPI(op,extra),{op,extra}),wait=fn=>p.waitForFunction(fn);
   const cell=(x,y)=>p.locator(`.jq-cell[data-x="${x}"][data-y="${y}"]`),shot=name=>p.locator('.jq-table').screenshot({path:path.join(out,name+'.png')});
   const t={p,uid,api,wait,cell,shot};tabs.push(t);return t;
  }
  const a=await tab('合成红军指挥',1100),b=await tab('合成蓝军指挥',390),c=await tab('合成军棋观战',390);
  await a.api('create',{game:'junqi'});await a.wait(()=>state.groom&&state.gst?.room.game==='junqi');const room=await a.p.evaluate(()=>state.groom);
  await b.api('join',{room_id:room});await c.api('spectate',{room_id:room});await a.api('start',{room_id:room});
  for(const t of tabs)await t.wait(()=>document.querySelectorAll('.jq-counter').length===50);
  for(const t of tabs)assert.equal(await t.p.locator('.jq-board').evaluate(e=>{const r=e.getBoundingClientRect(),p=document.querySelector('#gmain').getBoundingClientRect();return r.top>=p.top&&r.bottom<=p.bottom+1}),true);
  const staleGuards=await a.p.evaluate(()=>{
    const b=document.querySelector('.jq-cell[aria-disabled=false]'),handler=b.onclick;
    const saved={token:state.token,room:state.gst.room,public:state.gst.state,private:state.gpriv,rid:state.groom};
    const rejects=[];
    for(const kind of ['token','room','public','private','closed']){
      state.gsel=null;
      if(kind==='token')state.token='synthetic-replaced-token';
      if(kind==='room')state.gst.room={...saved.room};
      if(kind==='public')state.gst.state={...saved.public};
      if(kind==='private')state.gpriv={...saved.private};
      if(kind==='closed')state.groom=null;
      handler();rejects.push(state.gsel===null);
      state.token=saved.token;state.gst.room=saved.room;state.gst.state=saved.public;state.gpriv=saved.private;state.groom=saved.rid;
    }
    return rejects.every(Boolean);
  });assert.equal(staleGuards,true);
  await a.shot('production-initial');await b.shot('production-initial-390');
  async function initialMove(t,touch){
    const move=await t.p.evaluate(()=>state.gpriv.legal.find(m=>{const v=state.gst.state.board[m.to[1]][m.to[0]];return v!==10&&v!==40}));assert.ok(move);
    await t.cell(...move.from)[touch?'tap':'click']();await t.wait(()=>state.gsel);await t.shot(touch?'production-decision-390':'production-decision');
    await t.cell(...move.to)[touch?'tap':'click']();await t.p.waitForFunction(uid=>state.gst.state.turn_uid!==uid,t.uid);
  }
  await initialMove(a,false);await b.wait(()=>state.gst.state.turn_uid===state.uid);await initialMove(b,true);
  await c.shot('production-spectator-390');assert.equal(await c.p.locator('.jq-cell[aria-disabled=false]').count(),0);
  await fetch('http://127.0.0.1:'+control+'/capture',{method:'POST'});for(const t of tabs)await t.api('sync',{room_id:room});
  await a.wait(()=>state.gst.state.board[4][0]===13);await a.cell(0,4).click();await a.wait(()=>state.gsel);await a.cell(0,5).click();for(const t of tabs)await t.wait(()=>state.gst.state.last_event?.kind==='mine_clear');
  await b.cell(4,6).tap();await b.wait(()=>state.gsel);await b.cell(4,5).tap();for(const t of tabs)await t.wait(()=>state.gst.state.last_event?.kind==='eat');
  await a.shot('production-captures');await b.shot('production-captures-390');
  await fetch('http://127.0.0.1:'+control+'/flag',{method:'POST'});for(const t of tabs)await t.api('sync',{room_id:room});
  await a.wait(()=>state.gst.state.board[5][0]===40);await a.cell(0,4).focus();await a.p.keyboard.press('Enter');await a.wait(()=>state.gsel);
  await a.cell(0,4).focus();await a.p.keyboard.press('ArrowDown');await a.p.keyboard.press('Enter');for(const t of tabs)await t.wait(()=>state.gst.state.winner_uid!=null);
  await a.shot('production-finished');await b.shot('production-finished-390');assert.equal(await a.p.locator('.jq-cell[aria-disabled=false]').count(),0);assert.deepEqual(errors,[]);
  const report={production_http:true,production_sse:true,stale_guards:staleGuards,players:2,spectators:1,real_mouse_move:true,real_touch_move:true,engineer_clears_mine:true,opponent_capture:true,keyboard_flag_finish:true,viewports:[390,1100],exceptions:errors,terminal_fixture:'separate synthetic one-step-before-flag state; final action uses production HTTP and rules'};
  fs.writeFileSync(path.join(out,'production-actions.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
