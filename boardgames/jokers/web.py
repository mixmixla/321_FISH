"""Authoritative private cards and public played cards on a responsive poker table."""
import json
from boardgames.jokers.catalog import JOKERS

WEB_JS = r"""
const JokerTableWeb=(()=>{
  const defs=__JOKERS__,suits={h:'♥',s:'♠',d:'♦',c:'♣'};
  function node(tag,cls,label){const e=document.createElement(tag);if(cls)e.className=cls;if(label!=null)e.textContent=String(label);return e;}
  function poker(card,action,selected){
    const e=node(action?'button':'div','jt-poker'+(selected?' is-selected':''));if(action)e.type='button';
    e.dataset.cid=String(card.id);e.dataset.rank=String(card.c);e.dataset.suit=String(card.s);
    const rank=card.c==='T'?'10':card.c,suit=suits[card.s]||'?';e.style.setProperty('--suit',card.s==='h'||card.s==='d'?'#b33548':'#233c3b');
    e.setAttribute('aria-label',suit+' '+rank+(selected?'，已入台':''));
    e.append(node('span','jt-rank',rank),node('span','jt-suit',suit),node('strong','jt-center-rank',rank),node('span','jt-center-suit',suit));
    const badges=[{foil:'箔饰',holo:'全息',poly:'多彩'}[card.edt],{bonus:'宝珠',mult:'曙光',face:'节庆',glass:'琉璃',steel:'钢印',stone:'石牌'}[card.enh],{red:'赤印',gold:'金印',purple:'紫印'}[card.seal]].filter(Boolean);
    if(badges.length)e.append(node('small','jt-card-badges',badges.join(' · ')));
    if(action){e.setAttribute('aria-pressed',String(!!selected));e.onclick=action;}return e;
  }
  function illustration(id){
    const def=defs[id]||{},a=node('div','jt-joker-art');a.setAttribute('role','img');a.setAttribute('aria-label',def.name||id);
    if(def.file){a.dataset.art=String(def.index);a.dataset.artFile=def.file;
      a.style.backgroundImage='url("/game-art/'+def.file+'?v=anime-jokers-v1")';a.style.backgroundSize='400% 200%';
      a.style.backgroundPosition=(def.index%4*100/3)+'% '+Math.floor(def.index/4)*100+'%';}
    return a;
  }
  function paint(box,s){
    const room=state.gst?.room;if(!room||room.game!=='balatro')return;
    const uid=state.uid,rid=room.room_id,token=state.token,pv0=state.gpriv;
    const member=(room.players||[]).includes(uid)&&(s.players||[]).includes(uid)&&!(room.spectators||[]).includes(uid);
    const pv=room.status!=='playing'?{}:member&&pv0&&pv0.owner_uid!==undefined&&pv0.owner_uid!==uid?{}:
      member&&pv0&&pv0.game&&pv0.game!=='balatro'?{}:member?(pv0||{}):{};
    let move=state.jokerView;
    if(!move||move.uid!==uid||move.rid!==rid||move.round!==room.round||move.token!==token||move.game!=='balatro'){
      move={uid,rid,round:room.round,token,game:'balatro',discard:false,inspect:null,busy:null};state.jokerView=move;
    }
    if(move.busy&&move.busy.private!==pv0)move.busy=null;
    const root=node('section','jt-table');box.appendChild(root);
    const current=()=>state.jokerView===move&&state.uid===uid&&state.token===token&&state.groom===rid
      &&state.gst?.room===room&&state.gst?.room?.round===move.round&&state.gst?.state===s&&state.gpriv===pv0&&root.isConnected;
    const myTurn=()=>current()&&member&&room.status==='playing'&&s.game==='balatro'&&s.turn_uid===uid
      &&(s.alive||[]).includes(uid)&&!s.done&&s.winner==null&&Array.isArray(pv.hand)&&!move.busy&&!move.inspect;
    function refresh(){if(current())renderGamePanel();}
    const hand=Array.isArray(pv.hand)?pv.hand:[],sel=Array.isArray(pv.sel)?pv.sel:[],selected=hand.filter(c=>sel.includes(c.id));
    const finished=s.done||room.status==='ended';
    function send(action){
      if(!myTurn())return;const cid=action.cid,op=action.op,exists=hand.some(c=>c.id===cid);
      if(op==='select'&&(!exists||sel.includes(cid)||sel.length>=5))return;
      if(op==='unselect'&&!sel.includes(cid))return;
      if(op==='discard'&&(!exists||sel.includes(cid)||Number(s.discards_left?.[uid]??3)<=0))return;
      if(op==='play'&&!sel.length)return;
      if(!['select','unselect','discard','play'].includes(op))return;
      move.busy={private:pv0};refresh();
      const retry=()=>{if(state.jokerView===move&&state.uid===uid&&state.token===token&&state.groom===rid){move.busy=null;renderGamePanel();}};
      gameAPI('action',{room_id:rid,action}).then(reply=>{if(reply?.ok===false)retry();},retry);
    }
    const header=node('header','jt-head');header.append(node('strong','','小丑牌'),node('span','','第 '+(s.blind||1)+' 盲注'));
    header.append(node('b','',finished?'本局结束':s.turn_uid===uid?'你的回合':'轮到 '+gnick(s.turn_uid)));root.append(header);
    const seats=node('div','jt-seats');root.append(seats);
    for(const player of s.players||[]){
      const seat=node('div','jt-seat'+(s.turn_uid===player?' is-turn':''));seat.append(node('strong','',gnick(player)+(player===uid?'（你）':'')),
        node('span','','♥ '+(s.hp?.[player]??0)),node('b','','◉ '+(s.score?.[player]??0)),node('small','',s.alive?.includes(player)?'手牌 '+(s.hand_size?.[player]||0):'已出局'));seats.append(seat);
    }
    const middle=node('div','jt-middle'),arena=node('section','jt-arena'),tools=node('aside','jt-tools');middle.append(arena,tools);root.append(middle);
    const last=s.last_play,shown=selected.length?selected:(last?.cards||[]);
    const arenaTitle=selected.length?(pv.preview?.name||'已选')+' · '+selected.length+'/5':last?'上次结算 · '+gnick(last.uid)+' · '+last.name+' +'+last.points:'点选手牌，最多五张入台';
    arena.append(node('h3','',arenaTitle));const row=node('div','jt-stage');arena.append(row);
    for(let i=0;i<5;i++){
      const card=shown[i];if(card)row.append(poker(card,selected.length&&myTurn()?()=>send({op:'unselect',cid:card.id}):null,!!selected.length));
      else row.append(node('span','jt-empty-card','＋'));
    }
    const discard=node('button','jt-pile jt-discard'+(move.discard?' is-armed':''));discard.type='button';discard.setAttribute('aria-pressed',String(move.discard));
    discard.append(node('strong','','弃牌堆'),node('small','',finished?'只读':member?'剩 '+(s.discards_left?.[uid]??'—')+' 次补抽':'观战只读'));discard.disabled=!myTurn();
    discard.onclick=()=>{if(!myTurn())return;move.discard=!move.discard;refresh();};tools.append(discard);
    const play=node('button','jt-settle');play.type='button';play.append(node('strong','',finished?'本局结束':'出牌结算'),node('small','',finished?'回看公开结算':'目标 '+(s.blind_targets?.[uid]??'—')+' · 余 '+(s.plays_left?.[uid]??'—')+' 手'));
    play.disabled=!myTurn()||!sel.length;play.onclick=()=>send({op:'play'});tools.append(play);
    if(last&&!selected.length){const result=node('p','jt-result',last.effects?.length?last.effects.join(' · '):'按实际牌型结算');arena.append(result);}
    if(member&&hand.length){
      const own=node('section','jt-own-hand');root.append(own);
      own.append(node('h3','',move.discard?'弃牌模式 · 点未入台手牌弃掉并补抽':'我的手牌 · 点选入台 / 再点撤回'));
      const cards=node('div','jt-hand');own.append(cards);
      for(const card of hand){const on=sel.includes(card.id),c=poker(card,myTurn()?()=>send({op:on?'unselect':move.discard?'discard':'select',cid:card.id}):null,on);
        if(c.tagName==='BUTTON'){c.disabled=move.discard&&on;c.setAttribute('aria-label',suits[card.s]+' '+(card.c==='T'?'10':card.c)+(on?'，已入台':move.discard?'，弃掉并补抽':'，选入出战区'));}cards.append(c);}
    }else root.append(node('p','jt-private-note',finished?'本局已结束 · 仅保留公开结算牌':member?(Array.isArray(pv.hand)?'本盲注手牌已用完':'等待本人私有手牌'):'观战 · 仅显示公开结算牌'));
    const companions=node('section','jt-companions');root.append(companions);companions.append(node('h3','','常驻 Joker · 点卡阅读能力'));
    const collection=node('div','jt-jokers');companions.append(collection);
    const owned=member?(s.jokers?.[uid]||[]):[];
    for(const id of owned){const def=defs[id]||{name:id,desc:''};const card=node('button','jt-joker');card.type='button';card.dataset.joker=id;
      card.append(illustration(id),node('strong','',def.name),node('small','',def.desc));
      card.onclick=()=>{if(!current())return;move.inspect=id;refresh();};collection.append(card);}
    if(!owned.length)collection.append(node('p','jt-private-note','每名玩家保留自己的常驻能力'));
    if(move.inspect&&defs[move.inspect]){
      const id=move.inspect,def=defs[id],inspector=node('section','jt-inspector');inspector.setAttribute('role','dialog');inspector.setAttribute('aria-label',def.name);
      const close=node('button','jt-close','返回牌桌 ×');close.type='button';close.onclick=()=>{if(!current())return;move.inspect=null;refresh();};
      inspector.append(close,illustration(id),node('h3','',def.name),node('p','',def.desc));root.append(inspector);
      inspector.onkeydown=e=>{if(e.key==='Escape'){move.inspect=null;refresh();}};
      inspector.scrollIntoView?.({block:'nearest'});
      close.focus?.();
    }
    root.onkeydown=e=>{if(e.key==='Escape'&&move.discard&&current()){move.discard=false;refresh();}};
    if(s.done&&s.winner!=null)root.append(node('p','jt-winner',gnick(s.winner)+' 获胜'));
  }
  return {paint,poker,illustration};
})();
Object.assign(GRENDER,{balatro:(box,s)=>JokerTableWeb.paint(box,s)});
""".replace("__JOKERS__", json.dumps(JOKERS, ensure_ascii=False))

WEB_CSS = r"""
#gpanel .card:has(.jt-table){width:min(1030px,calc(100vw - 16px));box-sizing:border-box}#gmain:has(.jt-table){max-height:calc(92vh - 140px)}
.jt-table{position:relative;box-sizing:border-box;padding:12px;background:#16463f;border:2px solid #c09b55;border-radius:12px;color:#fff2cf;font-family:'Microsoft YaHei UI',sans-serif;min-width:0}
.jt-table *{box-sizing:border-box}.jt-table h3{margin:0 0 7px;font-size:12px;color:#f5dfaa}.jt-table button{font:inherit;cursor:pointer}.jt-table button:disabled{cursor:default;opacity:1}.jt-table button:focus-visible{outline:3px solid #66dfca;outline-offset:2px}
.jt-head{display:flex;align-items:center;gap:12px;border-bottom:1px solid #9d8d55;padding-bottom:9px;font-size:12px}.jt-head strong{font-size:19px;letter-spacing:.12em}.jt-head>b{margin-left:auto;color:#ffe19d}
.jt-seats{display:flex;flex-wrap:wrap;gap:7px;margin:9px 0 12px}.jt-seat{display:flex;align-items:center;gap:8px;flex-wrap:wrap;background:#12382f;border:1px solid #537d67;border-radius:7px;padding:6px 9px;font-size:11px}.jt-seat.is-turn{border-color:#e2bf67;color:#fff1bb}.jt-seat small{color:#c0d5c6}
.jt-middle{display:grid;grid-template-columns:minmax(0,1fr) 130px;gap:11px}.jt-arena{min-width:0;padding:10px;border:1px solid #739371;border-radius:8px;background:#205146}.jt-stage{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:7px;align-items:center;max-width:490px;margin:0 auto;min-height:128px}
.jt-table .jt-poker{position:relative;display:block;min-width:0;width:100%;aspect-ratio:.69;background:#fff8e7!important;color:var(--suit)!important;border:1px solid #a99468!important;border-radius:7px;padding:0!important;box-shadow:0 3px 0 #0a2e2b;overflow:hidden;text-align:center;font-family:Georgia,'Segoe UI Symbol',serif}
.jt-table .jt-poker.is-selected{border:3px solid #55c9ae!important;transform:translateY(-5px);box-shadow:0 0 0 2px #55c9ae33,0 4px 0 #0a2e2b}.jt-rank{position:absolute;left:7%;top:5%;font-size:clamp(12px,1.6vw,20px);font-weight:800}.jt-suit{position:absolute;right:7%;top:5%;font-size:clamp(13px,1.8vw,21px)}
.jt-center-rank{position:absolute;top:29%;left:0;width:100%;font-size:clamp(21px,3.3vw,39px);line-height:1}.jt-center-suit{position:absolute;bottom:11%;left:0;width:100%;font-size:clamp(22px,3.5vw,40px);line-height:1}.jt-card-badges{position:absolute;bottom:2%;left:3%;right:3%;font:9px/1.2 sans-serif;color:#765283;background:#fff6dcee}
.jt-empty-card{display:grid;place-items:center;aspect-ratio:.69;border:1px dashed #779a7a;border-radius:7px;color:#779a7a;font-size:25px;min-width:0}.jt-tools{display:flex;flex-direction:column;gap:12px;justify-content:space-around;padding:3px}
.jt-table .jt-pile{position:relative;min-height:82px;border:3px solid #cfad62!important;border-radius:7px;padding:8px!important;color:#fff6d6!important;background:repeating-linear-gradient(135deg,#285d54 0 5px,#346c5f 5px 8px)!important;box-shadow:3px 3px #d0b57c,5px 5px #35574b}
.jt-pile strong,.jt-pile small,.jt-settle strong,.jt-settle small{display:block}.jt-pile small,.jt-settle small{font-size:10px;margin-top:6px}.jt-table .jt-pile.is-armed{background:#8d4056!important;outline:2px solid #ffd789}.jt-table .jt-settle{border:2px solid #f7df9c!important;border-radius:50%;min-height:75px;padding:9px!important;background:#dfbd6d!important;color:#273d32!important;box-shadow:0 3px #a57b36}.jt-table .jt-settle:disabled{background:#b0b494!important;color:#526551!important;border-color:#a5ac89!important}
.jt-own-hand{margin-top:17px}.jt-hand{display:grid;grid-template-columns:repeat(8,minmax(0,1fr));gap:7px;max-width:890px;margin:auto;padding:5px 2px}.jt-result{margin:8px 0 0;font-size:11px;color:#ffe4a6}.jt-private-note{font-size:12px;color:#c7dac8;margin:10px 0}
.jt-companions{margin-top:14px}.jt-jokers{display:flex;gap:10px;flex-wrap:wrap}.jt-table .jt-joker{display:grid;grid-template-columns:78px minmax(0,1fr);grid-template-rows:auto 1fr;column-gap:9px;width:225px;max-width:100%;text-align:left;padding:5px!important;border:1px solid #c29c57!important;background:#fff0d2!important;color:#2c4439!important;border-radius:6px;overflow:hidden}
.jt-joker-art{aspect-ratio:3/4;min-width:0;background-color:#b9a586;background-repeat:no-repeat;border-radius:3px}.jt-joker .jt-joker-art{grid-row:1/3}.jt-joker>strong{font-size:13px;padding-top:6px}.jt-joker>small{font-size:11px;line-height:1.5;padding-top:5px;color:#745b39}
.jt-inspector{position:absolute;inset:0;z-index:5;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;background:#123b35f8;padding:16px;border-radius:8px}.jt-inspector>.jt-joker-art{width:min(320px,65vw);flex:none}.jt-inspector p{margin:0;font-size:13px}.jt-table .jt-close{position:absolute;right:10px;top:10px;border:1px solid #d4b46a;border-radius:5px;background:#fff0cf;color:#2b493f;padding:7px 10px}.jt-winner{font-size:18px;font-weight:700;color:#ffe19d;text-align:center}
@media(max-width:560px){.jt-table{padding:8px}.jt-head{gap:7px}.jt-head strong{font-size:16px}.jt-head>b{font-size:11px}.jt-seats{gap:5px}.jt-seat{font-size:10px;gap:6px;padding:5px 7px}.jt-middle{grid-template-columns:minmax(0,1fr) 85px;gap:7px}.jt-arena{padding:7px}.jt-stage{min-height:85px;gap:4px}.jt-arena h3{font-size:10px}.jt-tools{gap:10px}.jt-table .jt-pile{min-height:70px;padding:5px!important;font-size:12px}.jt-pile small,.jt-settle small{font-size:9px}.jt-table .jt-settle{min-height:65px;font-size:12px;padding:6px!important}.jt-hand{grid-template-columns:repeat(4,minmax(0,1fr));gap:9px;max-width:355px}.jt-center-rank{font-size:30px}.jt-center-suit{font-size:31px}.jt-rank{font-size:16px}.jt-suit{font-size:17px}.jt-stage .jt-center-rank{font-size:16px}.jt-stage .jt-center-suit{font-size:16px}.jt-stage .jt-rank{font-size:9px}.jt-stage .jt-suit{font-size:10px}.jt-jokers{gap:8px}.jt-table .jt-joker{grid-template-columns:61px minmax(0,1fr);width:calc(50% - 4px);column-gap:5px}.jt-joker>strong{font-size:11px}.jt-joker>small{font-size:9px;padding-top:3px}.jt-inspector>.jt-joker-art{width:min(280px,65vw)}}
"""
