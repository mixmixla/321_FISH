// Headless browsers use the normal lobby, game panel, HTTP and EventSource.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const cfg = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
process.env.PLAYWRIGHT_BROWSERS_PATH = cfg.cache;
const { chromium } = require(cfg.runtime);
const shots = [];
const errors = [];
const requests = [];
const report = {source_id:cfg.source.id, served_sha256:cfg.source.served_sha256, rooms:[], boundaries:{}};
const labels = ['月影合成牌桌第一席长昵称', '紫苑合成牌桌第二席长昵称', '暮星合成牌桌第三席长昵称',
  '薄荷合成牌桌第四席长昵称', '铃兰合成牌桌第五席长昵称'];
const board = '#gpanel #gmain .mp-table';

function save(name, value) {
  fs.writeFileSync(path.join(cfg.output, name), JSON.stringify(value, null, 2));
}
function drawButton(page, index) {
  return page.locator(board + ' .mp-back[data-index="' + index + '"]');
}

async function main() {
  const browser = await chromium.launch({headless:true, args:['--disable-background-networking','--disable-sync']});
  try {
    async function player(name, mobile=false) {
      const context = await browser.newContext({
        viewport:mobile ? {width:390,height:844} : {width:1360,height:900},
        deviceScaleFactor:1, hasTouch:true, isMobile:mobile, reducedMotion:'reduce'
      });
      const page = await context.newPage();
      page.setDefaultTimeout(12000);
      page.on('pageerror', error => errors.push({name,message:error.message}));
      page.on('request', request => {
        if (!request.url().endsWith('/api/game') || request.method() !== 'POST') return;
        const {op,room_id,game,action} = request.postDataJSON();
        if (action) {
          const {target,index,seq,round_key} = action;
          requests.push({name,op,room_id,target,index,seq,round_key});
        } else requests.push({name,op,room_id,game});
      });
      await page.addInitScript(() => {
        window.matchpairsObserved = [];
        const NativeEventSource = window.EventSource;
        window.EventSource = class extends NativeEventSource {
          constructor(...args) {
            super(...args);
            this.addEventListener('message', event => {
              const frame = JSON.parse(event.data);
              if (frame.t === 'game_state' || frame.t === 'game_private') {
                window.matchpairsObserved.push(frame);
              }
            });
          }
        };
      });
      const response = await page.goto(cfg.url, {waitUntil:'domcontentloaded'});
      const loaded = crypto.createHash('sha256').update(await response.body()).digest('hex');
      assert.equal(loaded, cfg.source.served_sha256, 'served page hash');
      await page.locator('#nick').fill(name);
      await page.locator('#btnLogin').click();
      await page.waitForFunction(() => state.uid > 0 && document.querySelector('#main').offsetWidth > 0);
      return {context,page,uid:await page.evaluate(() => state.uid),name,mobile};
    }
    async function lobby(p) {
      if (await p.page.locator('#uxRail [data-ux-nav="game"]').isVisible()) {
        await p.page.locator('#uxRail [data-ux-nav="game"]').click();
      } else {
        if (!(await p.page.locator('#side').evaluate(side=>side.classList.contains('open')))) {
          await p.page.locator('#btnSide').click();
        }
        await p.page.locator('#side [title="游戏大厅"]').click();
      }
      await p.page.locator('#globby').waitFor();
    }
    async function join(p, rid, label) {
      await lobby(p);
      await p.page.locator('#glRooms > div').filter({hasText:'（'+rid+'）'})
        .getByRole('button',{name:label,exact:true}).click();
      await p.page.waitForFunction(({rid,uid}) => state.groom===rid && state.gst?.room?.room_id===rid
        && (state.gst.room.players.includes(uid)||state.gst.room.spectators.includes(uid)), {rid,uid:p.uid});
    }
    async function start(p) {
      await p.page.locator('#ghead').getByRole('button',{name:/开始对局/}).click();
    }
    async function ready(p, rid, round, seq, privateRequired=true) {
      await p.page.waitForFunction(({rid,round,seq,privateRequired}) => {
        const r=state.gst?.room,s=state.gst?.state,v=state.gpriv;
        return state.groom===rid && r?.room_id===rid && r.round===round && s?.seq===seq
          && document.querySelector('#gpanel #gmain .mp-table')
          && (!privateRequired || (v?.owner_uid===state.uid && v.round_key===s.round_key && v.seq===seq));
      }, {rid,round,seq,privateRequired});
    }
    async function shot(p, name, stage) {
      const viewport = p.page.viewportSize();
      const identity = await p.page.evaluate(() => ({
        room:state.gst.room.room_id, round:state.gst.room.round, seq:state.gst.state.seq,
        viewer:state.uid, current:state.gst.state.turn_uid, scrollWidth:document.documentElement.scrollWidth,
        tableWidth:Math.round(document.querySelector('#gpanel .mp-table').getBoundingClientRect().width)
      }));
      assert.ok(identity.scrollWidth <= viewport.width, 'page overflow at '+viewport.width);
      const file = path.join(cfg.output, name+'.png');
      await p.page.screenshot({path:file,animations:'disabled'});
      shots.push({file:path.basename(file),sha256:crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'),
        source_id:cfg.source.id,served_sha256:cfg.source.served_sha256,stage,viewport,...identity});
      save('screenshots.json',shots);
    }
    async function session(count, prefix) {
      const players=[];
      for(let i=0;i<count;i++) players.push(await player(prefix+labels[i],i===1));
      const [host] = players;
      const spectator=await player(prefix+'合成旁观',true);
      await lobby(host);
      await host.page.locator('#glQuery').fill('matchpairs');
      await host.page.locator('#glGames [data-game="matchpairs"]').getByRole('button',{name:'创建房间'}).click();
      await host.page.waitForFunction(() => state.gst?.room?.game==='matchpairs' && state.groom===state.gst.room.room_id);
      const rid=await host.page.evaluate(() => state.groom);
      for(const p of players.slice(1)) await join(p,rid,'加入');
      await start(host);
      await ready(host,rid,1,0);
      await join(spectator,rid,'观战');
      await ready(spectator,rid,1,0,false);
      await Promise.all(players.map(p=>ready(p,rid,1,0)));
      return {rid,players,host,spectator,checks:[]};
    }
    function actionCount() { return requests.filter(r=>r.op==='action').length; }
    async function snapshot(p) {
      return p.page.evaluate(() => ({s:state.gst.state, hand:state.gpriv?.hand||[], privateDraw:state.gpriv?.drawn_card}));
    }
    async function exerciseBoundaries(game, firstAction) {
      const current = await snapshot(game.host);
      const actor = game.players.find(p=>p.uid===current.s.turn_uid);
      const page = actor.page;
      const b = drawButton(page,0);
      const before = actionCount();
      report.boundaries.old_callbacks = await b.evaluate(button => {
        const saved = {token:state.token, uid:state.uid, groom:state.groom, gst:state.gst, gpriv:state.gpriv};
        const probes = [
          ['token',()=>state.token='other-synthetic-login'],
          ['account',()=>state.uid=-100],
          ['room_id',()=>state.groom='g-other'],
          ['room_object',()=>state.gst={...saved.gst,room:{...saved.gst.room}}],
          ['round',()=>state.gst={...saved.gst,room:{...saved.gst.room,round:saved.gst.room.round+1}}],
          ['public_frame',()=>state.gst={...saved.gst,state:{...saved.gst.state}}],
          ['private_frame',()=>state.gpriv={...saved.gpriv}],
          ['target',()=>saved.gst.state.draw_from_uid=-100]
        ];
        for (const [, change] of probes) {
          const target=saved.gst.state.draw_from_uid;
          try { change(); button.onclick(); }
          finally { saved.gst.state.draw_from_uid=target; Object.assign(state,saved); }
        }
        openGamePanel('g-other');
        if (document.querySelector('#gmain .mp-back:enabled')) throw Error('old room rendered actionable');
        button.onclick();
        openGamePanel(saved.groom);
        return [...probes.map(([name])=>name),'open_panel_with_previous_state','detached_button'];
      });
      assert.equal(actionCount(),before);
      await ready(actor,game.rid,1,current.s.seq);

      const abort = async route => {
        if(route.request().postDataJSON()?.op==='action') await route.abort('failed');
        else await route.continue();
      };
      await page.route('**/api/game',abort);
      const failed = page.waitForEvent('requestfailed',{predicate:r=>r.url().endsWith('/api/game')&&r.postDataJSON()?.op==='action'});
      await b.click({position:{x:11,y:30}});
      await failed;
      await page.unroute('**/api/game',abort);
      await page.waitForFunction(()=>Boolean(document.querySelector('#gmain .mp-back:enabled')));
      assert.equal((await snapshot(actor)).s.seq,current.s.seq);
      report.boundaries.http_failure_retry = true;

      const invalid = async route => {
        const payload=route.request().postDataJSON();
        if(payload?.op==='action') {
          payload.action.index=999;
          await route.continue({postData:JSON.stringify(payload)});
        } else await route.continue();
      };
      await page.route('**/api/game',invalid);
      const rejection = page.waitForResponse(r=>r.url().endsWith('/api/game')&&r.request().postDataJSON()?.op==='action');
      await b.click({position:{x:11,y:30}});
      const reply=await rejection;
      assert.equal(reply.status(),409);
      assert.equal((await reply.json()).ok,false);
      await page.unroute('**/api/game',invalid);
      await page.waitForFunction(()=>Boolean(document.querySelector('#gmain .mp-back:enabled')));
      assert.equal((await snapshot(actor)).s.seq,current.s.seq);
      report.boundaries.server_rejection = {http:409, forwarded_index:999, same_sequence:true};

      const oldActor=game.players.find(p=>p.name===firstAction.name);
      const stale = await oldActor.page.evaluate(({rid,action})=>gameAPI('action',{room_id:rid,action},true),
        {rid:game.rid,action:{op:'draw',target:firstAction.target,index:firstAction.index,
          round_key:firstAction.round_key,seq:firstAction.seq}});
      assert.equal(stale.ok,false);
      assert.equal((await snapshot(game.host)).s.seq,current.s.seq);
      report.boundaries.stale_wire_replay = true;
    }
    async function pull(game, round, seq, index, options={}) {
      const {rid,players,host,spectator,checks}=game;
      const before = await snapshot(host);
      assert.equal(before.s.seq,seq);
      const actor = players.find(p=>p.uid===before.s.turn_uid);
      const target = players.find(p=>p.uid===before.s.draw_from_uid);
      const [own,other] = await Promise.all([snapshot(actor),snapshot(target)]);
      const selected = other.hand[index];
      assert.ok(selected);
      const rank = selected.slice(0,-1);
      const peer = own.hand.find(card=>card.slice(0,-1)===rank);
      const b = drawButton(actor.page,index);
      const countBefore = actionCount();
      let allowRequest, routed;
      if (options.proof) {
        assert.equal(actor.uid,host.uid);
        await shot(actor,'desktop-start','opening');
        await actor.page.setViewportSize({width:390,height:844});
        await shot(actor,'mobile-start','opening');
        await actor.page.setViewportSize({width:1360,height:900});
        await actor.page.keyboard.press('Tab');
        await b.focus();
        assert.equal(await b.evaluate(e=>e.matches(':focus-visible')),true);
        await shot(actor,'desktop-choice','keyboard focus');
        await actor.page.setViewportSize({width:390,height:844});
        const paused = new Promise(resolve => {routed=resolve;});
        const release = new Promise(resolve => {allowRequest=resolve;});
        await actor.page.route('**/api/game',async route=>{
          if (route.request().postDataJSON()?.op==='action') {
            routed();
            await release;
          }
          await route.continue();
        });
        await b.tap({position:{x:11,y:30}});
        await paused;
        await actor.page.locator(board+' .mp-picked').waitFor();
        await shot(actor,'mobile-choice','touch, request in flight');
        assert.equal(actionCount(),countBefore+1);
        if(options.guard) {
          await actor.page.locator('#ghead').getByRole('button',{name:/放大/}).click();
          assert.equal(await b.isDisabled(),true);
          await b.evaluate(button=>button.onclick());
          assert.equal(actionCount(),countBefore+1,'same-frame redraw emitted another action');
          const countSync = await actor.page.evaluate(({rid,seq}) => matchpairsObserved
            .filter(f=>f.t==='game_state'&&f.room_id===rid&&f.state?.seq===seq).length,{rid,seq});
          await actor.page.evaluate(rid=>gameAPI('sync',{room_id:rid},true),rid);
          await actor.page.waitForFunction(({rid,seq,countSync}) => matchpairsObserved
            .filter(f=>f.t==='game_state'&&f.room_id===rid&&f.state?.seq===seq).length>countSync,{rid,seq,countSync});
          assert.equal(await b.isDisabled(),true);
          await b.evaluate(button=>button.onclick());
          assert.equal(actionCount(),countBefore+1,'duplicate authoritative frame released pending action');
          report.boundaries.same_frame_redraw = true;
          report.boundaries.same_revision_sync = true;
        }
        allowRequest();
      } else if (options.keyboard) {
        await b.focus();
        await b.press('Enter');
      } else if (actor.mobile) {
        await b.tap({position:{x:11,y:30}});
      } else {
        await b.click({position:{x:11,y:33}});
      }
      const total = Object.values(before.s.hand_size).reduce((sum,value)=>sum+value,0) - (peer?2:0);
      await Promise.all(players.map(p=>ready(p,rid,round,seq+1)));
      await ready(spectator,rid,round,seq+1,false);
      if(options.proof) await actor.page.unroute('**/api/game');
      assert.equal(actionCount(),countBefore+1);
      const [after,afterOther,publicViewer] = await Promise.all([snapshot(actor),snapshot(target),snapshot(spectator)]);
      assert.equal(after.s.last_draw.index,index);
      assert.equal(after.s.last_draw.target,target.uid);
      assert.equal(after.s.last_draw.paired,Boolean(peer));
      assert.equal(after.s.discarded_pairs,before.s.discarded_pairs+(peer?1:0));
      assert.equal(afterOther.hand.includes(selected),false);
      if (peer) {
        assert.deepEqual(after.s.last_pair.cards,[selected,peer]);
        assert.deepEqual(after.hand,own.hand.filter(card=>card!==peer));
        assert.equal(await spectator.page.locator(board+' .mp-pile [aria-label]').count(),2);
      } else {
        assert.deepEqual(after.hand,[...own.hand,selected]);
        assert.equal(after.privateDraw,selected);
        assert.equal(JSON.stringify(after.s).includes(selected),false);
      }
      assert.equal(publicViewer.hand.length,0);
      assert.equal(await spectator.page.locator(board+' .mp-hand .mp-face').count(),0);
      assert.equal(await spectator.page.locator(board+' .mp-back:enabled').count(),0);
      assert.equal(Object.values(after.s.hand_size).reduce((sum,value)=>sum+value,0),total);
      checks.push({round,seq:seq+1,actor:actor.uid,target:target.uid,index,paired:Boolean(peer),total,
        input:options.keyboard?'keyboard':actor.mobile||options.proof?'touch':'mouse'});
      if (options.proof) {
        await shot(actor,'mobile-pair','confirmed pair');
        await actor.page.setViewportSize({width:1360,height:900});
        await shot(actor,'desktop-pair','confirmed pair');
        await shot(spectator,'mobile-spectator','spectator');
      }
      return after.s;
    }

    const five = await session(5,'五人');
    const plan = cfg.plans[5][0];
    await pull(five,1,0,plan[0],{proof:true,guard:cfg.stage==='final'});
    report.rooms.push({players:5,seed:108,round:1,checks:five.checks});
    if (cfg.stage === 'final') {
      await exerciseBoundaries(five,requests.find(r=>r.op==='action'));
      for(let i=1;i<plan.length;i++) await pull(five,1,i,plan[i]);
      await five.host.page.waitForFunction(() => state.gst?.room.status==='ended');
      await shot(five.host,'desktop-finish','natural finish');
      await shot(five.spectator,'mobile-finish','natural finish spectator');
      const final = await snapshot(five.host);
      assert.ok(final.s.loser_uid);
      assert.equal(Object.values(final.s.hand_size).reduce((sum,n)=>sum+n,0),1);
      assert.equal(await five.host.page.locator(board+' .mp-back:enabled').count(),0);
      assert.equal(await five.spectator.page.locator(board+' .mp-last-back').isDisabled(),true);
      await five.host.page.locator('#ghead').getByRole('button',{name:/开始对局/}).waitFor();
      await start(five.host);
      await Promise.all(five.players.map(p=>ready(p,five.rid,2,0)));
      await ready(five.spectator,five.rid,2,0,false);
      assert.notEqual((await snapshot(five.host)).s.round_key,final.s.round_key);
      const second=cfg.plans[5][1];
      let safe=null;
      for(let i=0;i<second.length;i++) {
        const s=await pull(five,2,i,second[i]);
        safe=five.players.find(p=>p!==five.host&&s.safe.includes(p.uid));
        if(safe&&s.loser_uid==null) {
          await safe.page.locator('#ghead').getByRole('button',{name:/离开/}).click();
          await five.host.page.waitForFunction(uid=>!state.gst.room.players.includes(uid),safe.uid);
          await safe.page.waitForFunction(()=>state.groom===null);
          report.boundaries.safe_player_left = true;
          break;
        }
      }
      assert.ok(report.boundaries.safe_player_left);

      const two=await session(2,'两人');
      const secondPlan=cfg.plans[2][0];
      for(let i=0;i<secondPlan.length;i++) await pull(two,1,i,secondPlan[i],{keyboard:i===0});
      await two.host.page.waitForFunction(()=>state.gst?.room.status==='ended');
      const finalTwo = await snapshot(two.host);
      assert.ok(finalTwo.s.loser_uid);
      report.rooms.push({players:2,seed:19,round:1,checks:two.checks,loser:finalTwo.s.loser_uid});
      report.boundaries.restart = true;
      assert.ok(five.checks.some(c=>!c.paired),'natural unmatched draw missing');
      for(const g of [five,two]) {
        const frames=await g.spectator.page.evaluate(()=>matchpairsObserved);
        assert.equal(frames.filter(f=>f.t==='game_private').length,0);
        assert.ok(frames.some(f=>f.t==='game_state'&&f.state?.last_draw));
        for(const f of frames.filter(f=>f.t==='game_state'&&f.state?.game==='matchpairs')) {
          assert.ok(!('hands' in f.state) && !('drawn_card' in f.state));
          assert.ok(!f.state.last_draw || !('card' in f.state.last_draw));
        }
      }
    }
    assert.equal(errors.length,0,JSON.stringify(errors));
    Object.assign(report,{production_http:true,production_sse:true,requests,errors});
    save('actions.json',report);
    console.log(JSON.stringify({stage:cfg.stage,shots:shots.length,requests:requests.length,errors:errors.length}));
  } finally {
    await browser.close();
    save('browser-exit.json',{browser_closed:true,errors});
  }
}
main().catch(error=>{
  save('failure.json',{message:error.message,stack:error.stack,requests,errors,shots});
  console.error(error.stack);
  process.exitCode=1;
});
