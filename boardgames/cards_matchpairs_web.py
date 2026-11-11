"""Production matchpairs renderer and responsive tabletop styling."""
from boardgames.cards_pending_web import CARDS_PENDING_JS

WEB_CSS = r"""
body.hasBgArt #gpanel:has(.mp-table) > .card,
#gpanel:has(.mp-table) > .card {
  width:min(1020px,96vw); padding:12px; gap:8px;
  background:#2b2032; color:#f9ebcc; border:1px solid #8e6e4e;
}
#gpanel:has(.mp-table) > .card.full { width:min(1200px,98vw); height:auto; }
#gpanel:has(.mp-table) #ghead { color:#f1dfbc; min-width:0; font-size:12px; }
#gpanel:has(.mp-table) #ghead > span:first-child { min-width:0; }
#gpanel:has(.mp-table) #ghead .gbtn {
  flex:none; padding:5px 10px; background:#47354c; color:#fff0d6; border-color:#745b69;
}
#gpanel:has(.mp-table) #ghead .gbtn:hover { background:#68516a; }
#gpanel:has(.mp-table) #gmain { max-height:calc(90dvh - 60px); min-height:0; overflow-x:hidden; }
#gpanel:has(.mp-table) #glog,
#gpanel:has(.mp-table) #gmain > .gsec { display:none; }
.mp-table {
  box-sizing:border-box; width:100%; min-width:0; padding:20px; color:#f5e8d2;
  background:linear-gradient(145deg,#42314c,#2b2339 64%,#30243d);
  border:1px solid #9e7b55; border-radius:17px;
  font-family:"Microsoft YaHei UI",sans-serif; font-size:14px;
}
.mp-title { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:16px; }
.mp-title h3 { margin:0; color:#fff4d9; font-size:clamp(19px,2.5vw,27px); letter-spacing:.08em; }
.mp-title b { font-size:13px; color:#f3d89a; text-align:right; }
.mp-seats { display:grid; grid-template-columns:repeat(var(--mp-seats),minmax(0,1fr)); gap:7px; margin:0 0 13px; }
.mp-seat {
  min-width:0; display:grid; grid-template-columns:auto minmax(0,1fr); align-items:center;
  gap:8px; padding:7px 8px; min-height:48px;
  border:1px solid #765c70; background:#4a3954; border-radius:8px; color:#fff1db;
}
.mp-seat.current { border-color:#f6d692; background:#70514d; box-shadow:0 0 0 1px #9f764b; }
.mp-seat.target { border-color:#bd9bb9; background:#574364; }
.mp-seat.safe { border-color:#769384; background:#3b514a; }
.mp-seat.loser { border-color:#f4a18a; background:#79494e; }
.mp-medal {
  display:grid; place-items:center; width:25px; height:25px; border-radius:50%;
  background:#34273e; color:#f4cf86; border:1px solid #ab8059; font:700 13px Georgia,serif;
}
.mp-seat-name { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-weight:700; font-size:12px; }
.mp-seat-detail { display:block; color:#f2dfc7; font-size:11px; white-space:nowrap; }
.mp-felt {
  display:grid; grid-template-columns:clamp(102px,15vw,148px) minmax(0,1fr) clamp(115px,16vw,156px);
  grid-template-areas:"host draw discard"; align-items:center; gap:14px; padding:16px;
  border:1px solid #bd9968; border-radius:19px;
  background:repeating-linear-gradient(115deg,#fff1 0 1px,transparent 1px 5px),radial-gradient(ellipse at 49% 35%,#59466c,#392b4b 82%);
  box-shadow:inset 0 0 0 4px #51405e,inset 0 0 0 5px #a280604f,0 5px 13px #25182a66;
}
.mp-host { grid-area:host; margin:0; min-width:0; }
.mp-host img {
  display:block; width:100%; height:auto; aspect-ratio:3 / 4; object-fit:contain;
  background:#3c304a; border:2px solid #bd9568; border-radius:10px;
}
.mp-draw { grid-area:draw; min-width:0; text-align:center; }
.mp-label { margin:0 0 4px; font-size:13px; font-weight:700; color:#f8e0ad; }
.mp-note { min-height:18px; margin:0; font-size:12px; color:#e6cfdc; }
.mp-draw .mp-label { font-size:15px; }
.mp-card-row {
  display:flex; min-width:0; max-width:100%; overflow-x:auto; overflow-y:hidden;
  padding:13px 7px 10px; margin:0; scrollbar-width:thin; scrollbar-color:#ac86a6 #40304c;
  overscroll-behavior-inline:contain;
}
.mp-card-row:before,.mp-card-row:after { content:""; flex:1 0 0; }
.mp-fan { --mp-card-width:80px; --mp-card-height:114px; --mp-overlap:28px; min-height:143px; }
.mp-table .mp-back, .mp-face {
  box-sizing:border-box; position:relative; flex:0 0 var(--mp-card-width);
  width:var(--mp-card-width); height:var(--mp-card-height);
  margin:0 calc(-1 * var(--mp-overlap)) 0 0; border-radius:8px; transform-origin:50% 92%;
}
.mp-card-row > :nth-last-child(1) { margin-right:0; }
#gpanel .mp-table .mp-back {
  padding:0; border:0; outline:0; background:none; box-shadow:none; cursor:pointer;
}
#gpanel .mp-table .mp-back:disabled { opacity:1; cursor:default; }
.mp-back-art {
  position:absolute; inset:0; pointer-events:none; border-radius:8px;
  border:2px solid #f3d9a4; color:#f8e6bf; transform-origin:50% 92%;
  background:repeating-linear-gradient(45deg,#f7e6a815 0 1px,transparent 1px 6px),
    repeating-linear-gradient(-45deg,#f7e6a815 0 1px,transparent 1px 6px),#563b6e;
  box-shadow:2px 4px 6px #26182bbb;
  transform:translateY(var(--mp-rise,0px)) rotate(var(--mp-tilt,0deg));
  transition:transform .15s ease,box-shadow .15s ease;
}
.mp-back:disabled .mp-back-art { border-color:#bda7b2; }
.mp-back:not(:disabled):hover .mp-back-art,
.mp-back:not(:disabled):focus-visible .mp-back-art,
.mp-back.mp-picked .mp-back-art {
  border-color:#fff0b1; outline:2px solid #f0c976; outline-offset:1px;
  transform:translateY(-10px) rotate(0deg); box-shadow:0 5px 11px #21142fbb;
}
.mp-back.mp-picked { z-index:2; }
.mp-back-art:before { content:""; position:absolute; inset:5px; border:1px solid #d1b494; border-radius:4px; }
.mp-back-center {
  position:absolute; top:50%; left:50%; width:31px; height:31px; display:grid; place-items:center;
  transform:translate(-50%,-50%) rotate(45deg); border:1px solid #d9b77b; background:#432e58;
  pointer-events:none;
}
.mp-back-center span { transform:rotate(-45deg); color:#ffe5a9; font:700 19px Georgia,serif; }
.mp-discard {
  grid-area:discard; min-width:0; padding:8px 5px; text-align:center;
  border:1px dashed #bd996c; border-radius:11px; background:#30243d66;
}
.mp-pile { display:flex; align-items:center; justify-content:center; padding:5px 0 8px; min-height:80px; }
.mp-pile .mp-face { --mp-card-width:47px; --mp-card-height:66px; --mp-overlap:7px; }
.mp-stack {
  width:44px; height:63px; border:2px solid #bca283; border-radius:6px; transform:rotate(-11deg);
  background:repeating-linear-gradient(45deg,#846485 0 2px,#674e78 2px 5px);
  box-shadow:3px 3px #f4dca9,6px 5px #8c7288,8px 7px #c5a88c;
}
.mp-face {
  display:block; border:1px solid #b9a88e; color:#24232d; background:#fffaf0;
  box-shadow:2px 3px 5px #21172899;
}
.mp-face.red { color:#ab2944; }
.mp-face-corner { position:absolute; top:4px; left:5px; display:flex; flex-direction:column; align-items:center; font:700 17px/1 Georgia,serif; }
.mp-face-corner small { font:11px/1 "Segoe UI Symbol",sans-serif; margin-top:2px; }
.mp-face-suit { position:absolute; top:50%; left:51%; transform:translate(-50%,-42%); font:31px/1 "Segoe UI Symbol",sans-serif; }
.mp-pile .mp-face-corner { font-size:15px; }
.mp-pile .mp-face-suit { font-size:24px; transform:translate(-46%,-25%); }
.mp-hand {
  min-width:0; margin-top:12px; padding:8px 10px 5px; border-radius:10px;
  border:1px solid #91728a; background:#392b47;
}
.mp-hand .mp-label { text-align:left; padding:0 3px; }
.mp-hand-row { --mp-card-width:75px; --mp-card-height:105px; --mp-overlap:24px; padding-top:5px; }
.mp-hand-row .mp-face { transform:rotate(var(--mp-tilt,0deg)); }
.mp-hand-row .mp-face.arrived, .mp-pile.arrived .mp-face { animation:mp-arrive .38s ease-out both; }
.mp-pile.arrived .mp-face:nth-child(2) { animation-delay:.05s; }
.mp-empty { min-height:36px; display:grid; place-items:center; color:#e4cad8; font-size:13px; }
.mp-feedback { margin-top:8px; min-height:20px; color:#f4dbb3; font-size:12px; text-align:center; }
@keyframes mp-arrive { from { opacity:.5; transform:translate(-15px,-14px) rotate(-8deg); } to { opacity:1; transform:translate(0,0) rotate(0); } }
@media(prefers-reduced-motion:reduce) {
  .mp-back-art { transition:none; }
  .mp-hand-row .mp-face.arrived, .mp-pile.arrived .mp-face { animation:none; }
}
@media(max-width:560px) {
  body.hasBgArt #gpanel:has(.mp-table) > .card,
  #gpanel:has(.mp-table) > .card { width:98vw; padding:6px; }
  #gpanel:has(.mp-table) #ghead { gap:3px; flex-wrap:wrap; }
  #gpanel:has(.mp-table) #ghead .gbtn { padding:4px 5px; }
  .mp-table { padding:10px; border-radius:11px; }
  .mp-title { margin-bottom:10px; }
  .mp-title b { font-size:11px; }
  .mp-seats { gap:4px; margin-bottom:8px; }
  .mp-seat { min-height:42px; padding:4px; gap:3px; grid-template-columns:minmax(0,1fr); }
  .mp-medal { display:none; }
  .mp-seat-name { font-size:11px; }
  .mp-seat-detail { font-size:10px; }
  .mp-felt { grid-template-columns:minmax(0,1fr) 73px; grid-template-areas:"draw draw" "discard host"; gap:6px 9px; padding:9px; }
  .mp-fan { --mp-card-width:66px; --mp-card-height:93px; --mp-overlap:22px; min-height:116px; }
  .mp-discard { align-self:stretch; display:grid; grid-template-columns:minmax(66px,1fr) 96px; grid-template-areas:"title pile" "note pile"; align-items:center; padding:5px 6px; }
  .mp-discard .mp-label { grid-area:title; align-self:end; }
  .mp-discard .mp-pile { grid-area:pile; }
  .mp-discard .mp-note { grid-area:note; align-self:start; }
  .mp-hand { margin-top:8px; padding:6px 5px 4px; }
  .mp-hand-row { --mp-card-width:62px; --mp-card-height:87px; --mp-overlap:18px; }
  .mp-face-suit { font-size:28px; }
}
"""

WEB_JS = CARDS_PENDING_JS + r"""
  const envelope = state.gst;
  const room = envelope && envelope.room;
  const uid = state.uid;
  const token = state.token;
  const roomId = state.groom;
  const round = room && room.round;
  const roundKey = s.round_key;
  const seq = s.seq;
  const privateFrame = state.gpriv;
  const target = s.draw_from_uid;
  const make = (tag, className, label) => {
    const element = document.createElement(tag);
    element.className = className;
    if (label != null) element.textContent = label;
    return element;
  };
  const root = make('section', 'mp-table');
  root.dataset.game = 'matchpairs';
  box.append(root);
  if (!room || room.game !== 'matchpairs' || room.room_id !== roomId || envelope.state !== s
      || !roundKey || !Number.isInteger(seq)) {
    root.append(make('p', 'mp-empty', '正在同步牌桌…'));
    return;
  }

  // Duplicate sync messages carry the same authoritative revision. Keep the
  // pending latch and selection through redraws and repeated copies of it.
  let table = state.matchpairsTable;
  if (!table || table.roomId !== roomId || table.round !== round
      || table.roundKey !== roundKey || table.uid !== uid) {
    table = state.matchpairsTable = {roomId, round, roundKey, uid, seq, frame:{}, selection:null, animatedPair:0, animatedHand:0};
  }
  if (seq < table.seq) {
    root.append(make('p', 'mp-empty', '正在同步牌桌…'));
    return;
  }
  if (seq > table.seq) {
    table.seq = seq;
    table.frame = {};
    table.selection = null;
  }
  const members = s.players || [];
  const member = () => members.includes(uid) && (room.players || []).includes(uid)
    && !(room.spectators || []).includes(uid);
  const matchingPrivate = member() && privateFrame && privateFrame.owner_uid === uid
    && privateFrame.round_key === roundKey && privateFrame.seq === seq
    && Array.isArray(privateFrame.hand);
  const hand = matchingPrivate ? privateFrame.hand : [];
  const safe = s.safe || [];
  const loser = s.loser_uid;
  const ended = room.status === 'ended' || loser != null;
  const count = Number((s.hand_size || {})[target]) || 0;
  const actionable = () => room.status === 'playing' && s.status === 'playing'
    && member() && matchingPrivate && s.loser_uid == null && s.turn_uid === uid
    && members.includes(target) && target !== uid && count > 0;
  const valid = () => actionable() && root.isConnected && state.token === token && state.uid === uid
    && state.groom === roomId && state.gst === envelope && envelope.room === room
    && room.room_id === roomId && room.round === round && room.game === 'matchpairs'
    && envelope.state === s && s.game === 'matchpairs' && s.seq === seq && s.round_key === roundKey
    && state.gpriv === privateFrame && s.draw_from_uid === target
    && state.matchpairsTable === table && table.seq === seq;
  const pending = cardPendingFor('matchpairs', {uid, roomId, round, publicFrame:table.frame, privateFrame:table.frame});
  const view = pending.attach(root, valid);
  const header = make('header', 'mp-title');
  const status = ended ? (loser != null ? gnick(loser) + ' 落单' : '本局结束')
    : !member() ? '观战中' : s.turn_uid === uid ? '轮到你' : '轮到 ' + gnick(s.turn_uid);
  header.append(make('h3', '', '抽牌配对'), make('b', 'mp-status', status));
  root.append(header);

  const seats = make('div', 'mp-seats');
  seats.style.setProperty('--mp-seats', Math.max(1, members.length));
  members.forEach((player, index) => {
    const isSafe = safe.includes(player);
    const current = !ended && player === s.turn_uid;
    const next = !ended && player === target;
    const seat = make('div', 'mp-seat' + (current ? ' current' : next ? ' target' : isSafe ? ' safe' : player === loser ? ' loser' : ''));
    const name = gnick(player);
    const detail = isSafe ? '安全' : ((s.hand_size || {})[player] || 0) + ' 张'
      + (current ? ' · 行动' : next ? ' · 下家' : '');
    seat.title = name + ' · ' + detail;
    const info = make('div', 'mp-seat-info');
    info.append(make('span','mp-seat-name', player === uid ? '你 · ' + name : name), make('span','mp-seat-detail',detail));
    seat.append(make('span','mp-medal',index+1), info);
    seats.append(seat);
  });
  root.append(seats);

  function face(label, extra = '') {
    if (typeof label !== 'string' || !/^(10|[2-9AJQK])[♠♥♦♣]$/.test(label)) return null;
    const suit = label.slice(-1);
    const card = make('div', 'mp-face' + ('♥♦'.includes(suit) ? ' red' : '') + extra);
    card.setAttribute('role','img');
    card.setAttribute('aria-label',label);
    const corner = make('span','mp-face-corner',label.slice(0,-1));
    corner.append(make('small','',suit + '\uFE0E'));
    card.append(corner,make('span','mp-face-suit',suit + '\uFE0E'));
    return card;
  }

  const felt = make('div','mp-felt');
  const host = make('figure','mp-host');
  const portrait = make('img','');
  portrait.src = '/game-art/cards-matchpairs-hostess.webp';
  portrait.width = 1086;
  portrait.height = 1448;
  portrait.alt = '牌桌主持人';
  host.append(portrait);

  const draw = make('section','mp-draw');
  draw.append(make('h4','mp-label',target != null ? gnick(target) + ' 的手牌'
    : loser != null ? '最后一张牌' : '抽牌结束'));
  const hint = make('p','mp-note',table.selection != null ? '正在抽牌…'
    : actionable() ? '点一张牌背抽取' : ended ? '' : member() && s.turn_uid === uid ? '等待手牌同步' : '等待行动');
  draw.append(hint);
  const fan = make('div','mp-card-row mp-fan');
  fan.setAttribute('aria-label','下家牌背');
  function send(index, button) {
    if (!button.isConnected || !valid() || pending.isPending() || index >= count) return;
    table.selection = index;
    button.classList.add('mp-picked');
    button.scrollIntoView({block:'nearest',inline:'nearest'});
    hint.textContent = '正在抽牌…';
    pending.submit(() => {
      const failed = () => {
        if (state.matchpairsTable === table && table.seq === seq) {
          table.selection = null;
          const active = document.querySelector('#gmain .mp-table');
          if (active) {
            active.querySelector('.mp-picked')?.classList.remove('mp-picked');
            const activeHint = active.querySelector('.mp-draw .mp-note');
            if (activeHint) activeHint.textContent = '抽取失败，可重新选牌';
          }
        }
        return {ok:false};
      };
      return gameAPI('action',{room_id:roomId,action:{op:'draw',target,index,round_key:roundKey,seq}})
        .then(reply => {
          if (reply?.refresh && state.matchpairsTable === table && table.seq === seq
              && state.token === token && state.uid === uid && state.groom === roomId
              && state.gst?.room?.room_id === roomId && state.gst.room.round === round
              && state.gst.state?.round_key === roundKey) {
            gameAPI('sync',{room_id:roomId},true).catch(()=>{});
          }
          return reply && reply.ok === false ? failed() : reply;
        }, failed);
    });
  }
  function back(className = '') {
    const button = make('button','mp-back' + className);
    button.type = 'button';
    const art = make('span','mp-back-art');
    art.setAttribute('aria-hidden','true');
    const mark = make('span','mp-back-center');
    mark.append(make('span','','✦'));
    art.append(mark);
    button.append(art);
    return button;
  }
  for (let index=0; index<count && index<13; index++) {
    const button = back(table.selection === index ? ' mp-picked' : '');
    button.dataset.index = index;
    button.setAttribute('aria-label', '从 ' + gnick(target) + ' 抽第 ' + (index+1) + ' 张牌');
    const tilt = Math.max(-7, Math.min(7, (index - (count-1)/2) * 2));
    button.style.setProperty('--mp-tilt', tilt + 'deg');
    button.style.setProperty('--mp-rise', Math.abs(tilt)*.45 + 'px');
    view.watch(button, actionable());
    button.onclick = () => send(index, button);
    fan.append(button);
  }
  if (ended && loser != null && (s.hand_size || {})[loser] === 1) {
    const lastBack = back(' mp-last-back');
    lastBack.disabled = true;
    lastBack.setAttribute('aria-label','最后一张未配对的牌背');
    fan.append(lastBack);
  } else if (!count) {
    fan.append(make('p','mp-empty',ended ? '本局已结束' : '等待发牌'));
  }
  draw.append(fan);

  const discard = make('section','mp-discard');
  discard.append(make('h4','mp-label','弃对堆'));
  const pile = make('div','mp-pile');
  const pair = s.last_pair;
  if (pair && Array.isArray(pair.cards)) {
    if (pair.seq > table.animatedPair) {
      if (pair.seq === seq && s.last_draw && s.last_draw.paired) pile.classList.add('arrived');
      table.animatedPair = pair.seq;
    }
    for (const label of pair.cards) {
      const card = face(label);
      if (card) pile.append(card);
    }
  } else if (s.discarded_pairs > 0) {
    pile.append(make('span','mp-stack'));
  }
  discard.append(pile,make('p','mp-note',(s.discarded_pairs || 0) + ' 对'));
  felt.append(host,draw,discard);
  root.append(felt);

  const own = make('section','mp-hand');
  own.append(make('h4','mp-label',member() ? '我的手牌' : '玩家手牌未公开'));
  const row = make('div','mp-card-row mp-hand-row');
  const drawn = matchingPrivate ? privateFrame.drawn_card : null;
  const animateDraw = drawn && s.last_draw && s.last_draw.uid === uid && seq > table.animatedHand;
  hand.forEach((label,index) => {
    const card = face(label, animateDraw && label === drawn ? ' arrived' : '');
    if (card) {
      card.style.setProperty('--mp-tilt', Math.max(-5,Math.min(5,(index-(hand.length-1)/2)*1.6)) + 'deg');
      row.append(card);
    }
  });
  if (animateDraw) table.animatedHand = seq;
  if (hand.length) own.append(row);
  else if (member()) own.append(make('p','mp-empty',safe.includes(uid) ? '手牌配完，已安全'
    : loser === uid ? '最后一张留在你手里' : ended ? '本局已结束' : '等待手牌'));
  root.append(own);
  const last = s.last_draw;
  const feedback = ended && loser != null ? gnick(loser) + ' 留下了最后一张牌'
    : last && last.paired && pair ? gnick(last.uid) + ' 配成一对 ' + pair.cards[0].slice(0,-1)
    : drawn ? '你抽到了 ' + drawn : last ? gnick(last.uid) + ' 抽了一张牌' : '';
  const message = make('p','mp-feedback',feedback);
  message.setAttribute('role','status');
  root.append(message);
  view.refresh();
"""
