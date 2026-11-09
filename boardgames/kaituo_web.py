"""Responsive Kaituo table for the production chat page."""
import json
from games_pkg.kaituo import RES_COST, RES_ORDER
from boardgames.kaituo_objects import GOODS, HARBOUR, LAND, MODELS, PIPS

WEB_CSS = r"""
body.hasBgArt #gpanel .card:has(.kt-table), #gpanel .card:has(.kt-table) {
  width:min(1100px,96vw); max-height:94vh; background:#f3f5ed; background-image:none;
}
#gmain:has(.kt-table){max-height:calc(94vh - 146px);min-height:0}
.kt-table{container-type:inline-size;background:#e7ede3;border:1px solid #b6c4b8;border-radius:12px;overflow:hidden;color:#233d43;font:13px 'Microsoft YaHei UI',sans-serif}
.kt-sync{padding:16px;color:var(--txt)}.kt-table *{box-sizing:border-box}.kt-table h3,.kt-table p{margin:0;color:inherit}
.kt-header{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:12px 15px;background:#24464b;color:#fff5df}
.kt-header h3{font-size:18px;font-weight:700;letter-spacing:.05em}.kt-header p{font-size:12px;text-align:right;color:#edf0db}
#gmain .kt-table button{color:inherit;font:inherit;box-shadow:none;transition:none;touch-action:manipulation;transform:none}
#gmain .kt-table button:focus-visible{outline:2px solid #317c70;outline-offset:2px}
#gmain .kt-table button:disabled{cursor:default;opacity:1}
.kt-tabs{display:none}
.kt-layout{display:grid;grid-template-columns:minmax(0,1.24fr) minmax(270px,1fr);gap:12px;padding:13px;align-items:start}
.kt-map-frame{grid-row:span 2;min-width:0;background:#d5e0d4;border:1px solid #9aafa3;border-radius:10px;padding:40px 16px 15px}
.kt-map{position:relative;width:100%;aspect-ratio:1;background:#698678;border:2px solid #77958a}
.kt-land-grid{position:absolute;inset:0;display:grid;grid-template-columns:repeat(5,1fr);grid-template-rows:repeat(5,1fr);gap:2px;background:#77958a}
.kt-land{position:relative;min-width:0;min-height:0;overflow:hidden;background:#afbf93}
.kt-terrain{position:absolute;inset:0;display:block;background-repeat:no-repeat;background-size:300% 200%;pointer-events:none}
.kt-land.kt-produced::after{content:'';position:absolute;inset:0;border:3px solid #fff1b0;pointer-events:none;z-index:1}
.kt-number{position:absolute;z-index:1;left:50%;top:65%;transform:translate(-50%,-50%);min-width:21px;line-height:19px;padding:0 3px;text-align:center;border:1px solid #82734f;border-radius:50%;background:#fff4d4;color:#293f3c;font-size:11px;font-weight:750}
.kt-bandit{position:absolute;z-index:2;width:52%;aspect-ratio:1;right:0;top:0}
#gmain .kt-table .kt-land-action{position:absolute;inset:0;z-index:3;border:1px dashed #fff3c9;border-radius:0;background:#fdf2bb12;padding:0}
.kt-road-overlay{position:absolute;inset:0;pointer-events:none;width:100%;height:100%;z-index:3;overflow:visible}
#gmain .kt-table .kt-vertex{position:absolute;z-index:5;display:block;width:24px;height:24px;margin:-12px 0 0 -12px;background:transparent;border:none;padding:0;min-width:0;overflow:visible}
.kt-vertex::after{content:'';position:absolute;left:7px;top:7px;width:10px;height:10px;background:#f2d47e;border:1px solid #705e3b;border-radius:50%}
.kt-vertex.kt-marker::after{width:6px;height:6px;left:9px;top:9px;background:#698478;border-color:#dce5ce}
.kt-building{position:absolute;z-index:6;pointer-events:none;width:clamp(24px,11%,59px);aspect-ratio:1;transform:translate(-50%,-83%)}
.kt-building .kt-piece{position:absolute;inset:0 0 3px}.kt-plinth{position:absolute;bottom:1px;left:9%;right:9%;height:19%;border-radius:50%;border:1px solid #fff1d2;background:var(--kt-owner)}
#gmain .kt-table .kt-edge{position:absolute;z-index:4;padding:0;width:9%;height:10px;margin-top:-5px;min-width:0;background:#ead292bb;border:2px dashed #fff4c8;border-radius:3px}
.kt-edge.kt-horizontal{margin-left:-4.5%}.kt-edge.kt-vertical{margin-left:-4.5%;rotate:90deg}
.kt-controls{display:grid;gap:9px;min-width:0}.kt-dice-row{display:flex;gap:8px;align-items:center}
#gmain .kt-table .kt-dice-tray{display:flex;align-items:center;justify-content:center;gap:8px;min-height:62px;flex:1;border:1px solid #a9bfae;border-radius:8px;background:#dbe8dd;padding:5px 8px;color:#27483f}
.kt-dice-tray .kt-piece{width:48px;aspect-ratio:1;flex:none}.kt-die{position:relative;display:block;flex:none;width:34px;height:34px;border:1px solid #baad82;border-radius:7px;background:#fff9e8;box-shadow:2px 3px 0 #ab9b74}.kt-die i{position:absolute;width:5px;height:5px;transform:translate(-50%,-50%);border-radius:50%;background:#304d45}
.kt-roll-label{font-size:10px;white-space:nowrap}
#gmain .kt-table .kt-turn{width:54px;flex:none;display:grid;justify-items:center;background:none;border:0;padding:0;color:#2c4546}.kt-turn .kt-piece{width:42px;aspect-ratio:1}.kt-turn small{font-size:10px}
.kt-rack{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:4px;padding:6px;background:#f8efdc;border:1px solid #cfbf9f;border-radius:8px}
#gmain .kt-table .kt-model{display:grid;justify-items:center;min-width:0;border:1px solid transparent;border-radius:6px;background:transparent;padding:3px 2px;color:#263e43}
#gmain .kt-table .kt-model.kt-selected{background:#dcebe0;border-color:#90b0a0}
.kt-model .kt-piece{width:min(100%,72px);aspect-ratio:1}.kt-model small{font-size:11px;font-weight:700}.kt-fees{display:flex;justify-content:center;gap:1px;flex-wrap:wrap;min-height:19px;margin-top:2px}
.kt-chip{display:flex;align-items:center;gap:0;font-size:11px;min-width:18px}.kt-chip .kt-piece{width:clamp(15px,2.2cqw,21px);aspect-ratio:1}.kt-chip.kt-short b{color:#a14135}
.kt-piece{display:block;background-repeat:no-repeat;background-size:300% 200%;pointer-events:none}
.kt-harbour{display:grid;grid-template-columns:23% minmax(0,1fr);gap:8px;min-width:0;padding:6px;background:#eee6d5;border:1px solid #cbbca0;border-radius:8px}
.kt-merchant{align-self:center;display:grid;justify-items:center;gap:5px;max-width:110px;color:#2c4546;font-size:10px}.kt-merchant img{display:block;width:100%;height:auto;aspect-ratio:11/12;object-fit:contain;border:1px solid #c8b798;border-radius:5px;background:#f7efdc}
.kt-ledger{display:grid;gap:5px;min-width:0}.kt-ledger h4{font-size:11px;margin:0;font-weight:700;color:#294146}
.kt-cargo-row{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:3px}
#gmain .kt-table .kt-cargo{display:grid;justify-items:center;align-content:center;min-width:0;padding:2px 1px;border:1px solid #d5cbb4;border-radius:6px;background:#fffbf1;color:#233d43}
#gmain .kt-table .kt-cargo.kt-selected{background:#d6ebe0;border-color:#619f87;box-shadow:0 1px 0 #79a290}
.kt-cargo .kt-piece{width:100%;max-width:42px;aspect-ratio:1}.kt-count{width:100%;text-align:center;border-top:1px solid #ded8c9;font-weight:700;font-size:12px;line-height:16px}.kt-cargo.kt-short .kt-count{color:#a14135}
.kt-receipt{display:flex;align-items:center;justify-content:space-between;gap:4px;padding:2px 3px 2px 6px;border-radius:6px;background:#f8f1df;color:#294146;min-height:36px}
.kt-receipt p{font-size:11px}.kt-receipt.kt-ready{background:#dbeadd}
#gmain .kt-table .kt-seal{display:grid;justify-items:center;flex:none;width:42px;padding:1px 0;border:0;border-radius:3px;background:transparent;color:#235c53}.kt-seal .kt-piece{width:32px;height:32px}.kt-seal small{font-weight:700;font-size:10px}.kt-seal:disabled .kt-piece{opacity:.5}
.kt-seats{display:flex;flex-wrap:wrap;gap:6px;padding:0 13px 10px}.kt-seat{flex:1;min-width:96px;border-left:4px solid var(--kt-owner);background:#fffaf0;color:#233d43;padding:5px 8px;border-radius:4px;font-size:11px}.kt-seat b{display:inline-block;margin-left:6px}.kt-seat.kt-current{background:#d8e9dc}
@container (max-width:650px){
 .kt-header{padding:9px 10px}.kt-header h3{font-size:15px}.kt-header p{font-size:10px}
 .kt-tabs{display:flex;gap:5px;padding:7px 9px 0}#gmain .kt-table .kt-tabs .kt-tab{padding:5px 10px;border:1px solid #b4c5b5;background:#fffbf1;color:#28454a;border-radius:6px;font-size:11px}
 #gmain .kt-table .kt-tab[aria-pressed=true]{background:#d6e8da;border-color:#87a997}
 .kt-layout{display:flex;flex-direction:column;gap:8px;padding:8px 10px}.kt-map-frame,.kt-controls,.kt-harbour{width:100%}
 .kt-map-frame{padding:31px 12px 12px}.kt-map{max-height:none}.kt-rack{padding:4px}.kt-model .kt-piece{width:min(100%,51px)}
 .kt-layout[data-view=map] .kt-harbour,.kt-layout[data-view=harbour] .kt-map-frame,.kt-layout[data-view=harbour] .kt-controls{display:none}
 .kt-harbour{grid-template-columns:22% minmax(0,1fr);gap:5px}.kt-cargo-row{gap:2px}.kt-merchant{align-self:center}.kt-dice-tray .kt-piece{width:40px}.kt-die{width:28px;height:28px}
 .kt-seats{padding:0 10px 8px}
}
"""

WEB_JS = r"""
const KaituoTable = (() => {
  const {resources, costs, pips, goods, models, land, harbour} = @@KAITUO_DATA@@;
  const names = ['木材','砖块','羊','麦穗','矿石'];
  const modelNames = {road:'道路', settle:'村庄', city:'城市'};
  const colours = ['#a53e37','#3b668e','#31776b','#8e6131'];
  const points = Array.from({length:36}, (_, i) => [Math.floor(i/6),i%6]);
  let pending = null, selection = null;

  function node(tag, cls, text) {
    const result = document.createElement(tag);
    if (cls) result.className = cls;
    if (text != null) result.textContent = text;
    return result;
  }
  function sprite(file, index, extra) {
    const result = node('span', 'kt-piece'+(extra?' '+extra:''));
    result.style.backgroundImage = `url('/game-art/${file}')`;
    result.style.backgroundPosition = `${index%3*50}% ${Math.floor(index/3)*100}%`;
    return result;
  }
  function button(cls, label, handler, enabled = true) {
    const result = node('button', cls);
    result.type = 'button';
    result.setAttribute('aria-label', label);
    result.title = label;
    result.disabled = !enabled;
    result.onclick = () => { if (result.isConnected && !result.disabled) handler(); };
    return result;
  }
  const samePoint = (a,b) => a && b && a[0]===b[0] && a[1]===b[1];
  const key = point => point.join(',');
  const edgeKey = (a,b) => [key(a),key(b)].sort().join('>');
  const neighbours = ([r,c]) => [[r-1,c],[r+1,c],[r,c-1],[r,c+1]].filter(([r,c]) => r>=0 && c>=0 && r<=5 && c<=5);
  const revision = s => s.action_seq ?? JSON.stringify(s);

  function frameFor(s,room) {
    return [state.token,state.uid,room.room_id,room.round,revision(s)];
  }
  const sameFrame = (a,b) => a && b && a.every((part,i) => part===b[i]);
  function reject(request) {
    if (!pending || pending.request!==request) return;
    pending = null;
    if (state.gst?.room?.game === 'kaituo') renderGamePanel();
  }

  function targets(s, me, model, start) {
    if (s.robber_pending) return {vertices:[], edges:[]};
    const free = p => !s.board[key(p)] && neighbours(p).every(q=>!s.board[key(q)]);
    if (s.phase === 'setup') {
      if (!start) return {vertices:points.filter(free), edges:[]};
      return {vertices:[start], edges:neighbours(start).filter(q=>!s.roads[edgeKey(start,q)]).map(q=>[start,q])};
    }
    const stock = s.res[me] || {};
    if (!s.rolled || !costs[model] || Object.entries(costs[model]).some(([r,n])=>(stock[r]||0)<n)) {
      return {vertices:[],edges:[]};
    }
    const anchors = new Set(Object.keys(s.board).filter(k=>s.board[k].owner===me));
    for (const [road,owner] of Object.entries(s.roads)) {
      if (owner===me) road.split('>').forEach(k=>anchors.add(k));
    }
    if (model==='road') {
      const edges = [];
      for (const a of points) for (const b of neighbours(a)) {
        if (key(a)<key(b) && !s.roads[edgeKey(a,b)] && (anchors.has(key(a))||anchors.has(key(b)))) edges.push([a,b]);
      }
      return {vertices:[],edges};
    }
    const vertices = points.filter(p => model==='city'
      ? s.board[key(p)]?.owner===me && !s.board[key(p)].city
      : free(p) && neighbours(p).some(q=>anchors.has(key(q))));
    return {vertices, edges:[]};
  }

  function paint(box,s) {
    const view = state.gst;
    const room = view?.room;
    const roomId = room?.room_id;
    const sameRoom = () => typeof roomId === 'string' && roomId === state.groom
      && room.room_id === roomId && view.room_id === roomId
      && room.game === 'kaituo' && s.game === 'kaituo';
    if (!sameRoom() || view.state !== s) {
      box.appendChild(node('p','kt-sync','正在同步牌桌…'));
      return;
    }
    const me = state.uid;
    const frame = frameFor(s,room);
    if (pending && !sameFrame(pending.frame,frame)) pending=null;
    if (!selection || !sameFrame(selection.frame.slice(0,4),frame.slice(0,4))) {
      selection={frame,tab:'map',model:null,start:null,give:null,want:null};
    } else if (!sameFrame(selection.frame,frame)) {
      Object.assign(selection,{frame,start:null,give:null,want:null});
    }
    const choice=selection;
    const shell=node('section','kt-table');
    box.appendChild(shell);
    const ownStock=s.res[me]||{};
    const setup=s.phase==='setup', robber=s.robber_pending;
    const canAct=()=>shell.isConnected && sameRoom() && state.gst===view && state.gst?.state===s && state.gst?.room===room
      && sameFrame(frame,frameFor(s,room)) && room?.status==='playing' && s.status==='playing'
      && s.winner_uid==null && s.turn_uid===me && s.players.includes(me)
      && (room.players||[]).includes(me) && !(room.spectators||[]).includes(me) && !pending;
    function send(action) {
      if (!canAct() || (robber && action.op!=='robber')) return;
      const request=Array.from(crypto.getRandomValues(new Uint8Array(16)), value=>value.toString(16).padStart(2,'0')).join('');
      pending={frame,request};
      draw();
      gameAPI('action',{room_id:roomId,action:{...action,_kt_request:request}})
        .then(result=>{ if (result?.ok===false) reject(request); })
        .catch(()=>{ if (pending?.request===request) showStatus('等待房间同步，请勿重复操作'); });
    }
    function choose(field,value) {
      if (!canAct()) return;
      choice[field]=value;
      if (field==='model') choice.start=null;
      draw();
    }
    const owner=uid=>colours[s.players.indexOf(uid)]||'#718880';

    function map() {
      const frameEl=node('div','kt-map-frame'), board=node('div','kt-map');
      const landGrid=node('div','kt-land-grid');
      const produced=new Set((s.rolled?s.production||[]:[]).map(entry=>`${entry.r},${entry.c}`));
      for (let r=0;r<5;r++) for (let c=0;c<5;c++) {
        const coord=`${r},${c}`, terrain=s.tiles[coord];
        const square=node('div','kt-land'+(produced.has(coord)?' kt-produced':''));
        square.dataset.tile=coord;
        const material=resources.indexOf(terrain.res);
        square.append(sprite(land,material<0?5:material,'kt-terrain'),node('span','kt-number',material<0?'沙':terrain.num));
        if (samePoint([r,c],s.robber)) square.appendChild(sprite(models,5,'kt-bandit'));
        else if (canAct() && robber) {
          const target=button('kt-land-action','将盗匪移到此地块',()=>send({op:'robber',r,c}));
          target.dataset.land=coord;
          square.appendChild(target);
        }
        landGrid.appendChild(square);
      }
      board.appendChild(landGrid);
      const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
      svg.setAttribute('class','kt-road-overlay');
      svg.setAttribute('viewBox','0 0 500 500');
      for (const [id,uid] of Object.entries(s.roads)) {
        const [a,b]=id.split('>').map(k=>k.split(',').map(Number));
        for (const [ink,width] of [['#f8ead0',13],[owner(uid),8]]) {
          const line=document.createElementNS('http://www.w3.org/2000/svg','line');
          for (const [attribute,value] of Object.entries({x1:a[1]*100,y1:a[0]*100,x2:b[1]*100,y2:b[0]*100,stroke:ink,'stroke-width':width,'stroke-linecap':'round'})) line.setAttribute(attribute,value);
          svg.appendChild(line);
        }
      }
      board.appendChild(svg);
      const available=canAct()?targets(s,me,choice.model,choice.start):{vertices:[],edges:[]};
      for (const p of points) {
        const [r,c]=p, site=s.board[key(p)], draft=samePoint(p,choice.start);
        const allowed=available.vertices.some(q=>samePoint(q,p));
        if (site || draft) {
          const building=node('div','kt-building');
          building.style.cssText=`left:${c*20}%;top:${r*20}%;--kt-owner:${owner(site?.owner??me)}`;
          building.append(node('span','kt-plinth'),sprite(models,site?.city?2:1));
          board.appendChild(building);
        }
        const vertex=button('kt-vertex'+(allowed?'':' kt-marker'),`${r+1}行 ${c+1}列顶点`,()=>{
          if (!allowed || !canAct()) return;
          if (setup) choose('start',draft?null:p);
          else send({op:'build',kind:choice.model,i:r,j:c});
        },allowed);
        vertex.dataset.vertex=key(p);
        vertex.style.left=c*20+'%';vertex.style.top=r*20+'%';
        board.appendChild(vertex);
      }
      for (const [a,b] of available.edges) {
        const action={op:setup?'setup':'build',i:a[0],j:a[1],b_i:b[0],b_j:b[1]};
        if (!setup) action.kind='road';
        const edge=button('kt-edge '+(a[0]===b[0]?'kt-horizontal':'kt-vertical'),'在此边放道路',()=>send(action));
        edge.dataset.edge=edgeKey(a,b);
        edge.style.left=(a[1]+b[1])*10+'%';edge.style.top=(a[0]+b[0])*10+'%';
        board.appendChild(edge);
      }
      frameEl.appendChild(board);
      return frameEl;
    }

    function controls() {
      const section=node('div','kt-controls'), row=node('div','kt-dice-row');
      const faces=s.rolled?s.last_dice||[null,null]:[null,null];
      const dice=button('kt-dice-tray','掷骰',()=>send({op:'roll'}),canAct()&&!setup&&!robber&&!s.rolled);
      dice.dataset.control='roll';dice.appendChild(sprite(models,3));
      for (const value of faces) {
        const face=node('span','kt-die');face.dataset.face=value??'';
        for (const [x,y] of pips[value]||[]) {
          const pip=node('i');pip.style.left=x+'%';pip.style.top=y+'%';face.appendChild(pip);
        }
        dice.appendChild(face);
      }
      if (!s.rolled || !s.last_dice) dice.appendChild(node('small','kt-roll-label',s.rolled?`合计 ${s.last_roll??'—'}`:'待掷'));
      const turn=button('kt-turn','交接回合',()=>send({op:'skip'}),canAct()&&!setup&&!robber);
      turn.dataset.control='skip';turn.append(sprite(models,4),node('small',null,'交接'));
      row.append(dice,turn);section.appendChild(row);
      const rack=node('div','kt-rack');
      for (const [i,model] of Object.keys(modelNames).entries()) {
        const item=button('kt-model'+(choice.model===model?' kt-selected':''),`选择${modelNames[model]}`,()=>choose('model',model),canAct()&&!setup&&!robber&&s.rolled);
        item.dataset.mode=model;item.append(sprite(models,i),node('small',null,modelNames[model]));
        const fees=node('div','kt-fees');
        for (const [material,amount] of Object.entries(costs[model])) {
          const chip=node('span','kt-chip'+((ownStock[material]||0)<amount?' kt-short':''));
          chip.append(sprite(goods,resources.indexOf(material)),node('b',null,amount));fees.appendChild(chip);
        }
        item.appendChild(fees);rack.appendChild(item);
      }
      section.appendChild(rack);return section;
    }

    function port() {
      const section=node('div','kt-harbour'), merchant=node('div','kt-merchant');
      const portrait=node('img');portrait.src=`/game-art/${harbour}`;portrait.alt='港务员胸像';
      merchant.append(portrait,node('small',null,'港务员'));
      section.appendChild(merchant);
      const ledger=node('div','kt-ledger');
      const enabled=canAct()&&!setup&&!robber&&s.rolled;
      for (const kind of ['give','want']) {
        ledger.appendChild(node('h4',null,kind==='give'?'交货 4 件':'取货 1 件'));
        const row=node('div','kt-cargo-row');
        for (const [i,material] of resources.entries()) {
          const count=kind==='give'?(ownStock[material]||0):1;
          const extra=(choice[kind]===material?' kt-selected':'')+(kind==='give'&&count<4?' kt-short':'');
          const cargo=button('kt-cargo'+extra,`${names[i]} ${kind==='give'?`库存 ${count}，交货需 4`:'取 1'}`,()=>choose(kind,material),enabled);
          cargo.dataset[kind]=material;cargo.append(sprite(goods,i),node('b','kt-count',count));row.appendChild(cargo);
        }
        ledger.appendChild(row);
      }
      const {give,want}=choice;
      const good=Boolean(give&&want&&give!==want&&(ownStock[give]||0)>=4);
      const trade=s.last_trade;
      let message=enabled?'选货物，再盖章':'码头等待开市';
      if (pending) message='等待成交确认';
      else if (give&&(ownStock[give]||0)<4) message=`${names[resources.indexOf(give)]}库存 ${ownStock[give]||0}，需 4`;
      else if (give&&give===want) message='请选择不同货物';
      else if (good) message=`${names[resources.indexOf(give)]} −4 / ${names[resources.indexOf(want)]} +1`;
      else if (trade?.uid===me) message=`已成交　${names[resources.indexOf(trade.give)]} −${trade.n} / ${names[resources.indexOf(trade.want)]} +1`;
      const receipt=node('div','kt-receipt'+(enabled&&good?' kt-ready':''));
      const seal=button('kt-seal','盖章成交',()=>{if (enabled&&good) send({op:'trade',give,want,n:4});},enabled&&good);
      seal.dataset.control='swap';seal.append(sprite(goods,5),node('small',null,'成交'));
      receipt.append(node('p',null,message),seal);ledger.appendChild(receipt);section.appendChild(ledger);
      return section;
    }

    function draw() {
      shell.replaceChildren();
      const header=node('header','kt-header');
      const status=s.winner_uid!=null?`${gnick(s.winner_uid)} 获胜`:!s.players.includes(me)?'旁观'
        :pending?'等待确认':s.turn_uid!==me?`等待 ${gnick(s.turn_uid)}`
        :robber?'移动盗匪':setup?(choice.start?'选择相邻道路':'选择村址'):'轮到你';
      header.append(node('h3',null,'开拓 · 海风商路'),node('p',null,status));shell.appendChild(header);
      const tabs=node('nav','kt-tabs');
      for (const [tab,label] of [['map','地图与建造'],['harbour','港口贸易']]) {
        const control=button('kt-tab',label,()=>{choice.tab=tab;draw();});
        control.dataset.tab=tab;control.setAttribute('aria-pressed',String(choice.tab===tab));control.textContent=label;tabs.appendChild(control);
      }
      shell.appendChild(tabs);
      const layout=node('div','kt-layout');layout.dataset.view=choice.tab;
      layout.append(map(),controls(),port());shell.appendChild(layout);
      const seats=node('footer','kt-seats');
      for (const uid of s.players) {
        const seat=node('div','kt-seat'+(uid===s.turn_uid?' kt-current':''),gnick(uid)+(uid===me?'（我）':''));
        seat.style.setProperty('--kt-owner',owner(uid));seat.appendChild(node('b',null,`${s.score[uid]} 分`));seats.appendChild(seat);
      }
      shell.appendChild(seats);
    }
    draw();
  }
  return {paint,reject};
})();
""".replace("@@KAITUO_DATA@@", json.dumps({
    "resources":RES_ORDER, "costs":RES_COST, "pips":PIPS, "goods":GOODS,
    "models":MODELS, "land":LAND, "harbour":HARBOUR,
}, separators=(",",":")))
