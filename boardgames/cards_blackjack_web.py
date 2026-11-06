"""Real blackjack objects mounted in the production blackjack route."""
from boardgames.cards_pending_web import CARDS_PENDING_JS
WEB_CSS = r"""
.bc-table{width:100%;min-width:0;max-width:100%;padding:14px;color:#f7f1dc;background:#155345;border-radius:14px;font:14px 'Microsoft YaHei UI',sans-serif}
.bc-header{display:flex;justify-content:space-between;gap:10px;margin-bottom:12px}.bc-header h3{margin:0}.bc-header b{color:#e4bd69}
.bc-seats{display:flex;gap:5px;flex-wrap:wrap}.bc-seat{border:1px solid #aec5b5;background:#286b58;color:#fff;border-radius:20px;min-height:38px;padding:5px 10px;font-size:12px;cursor:pointer}.bc-seat.current{outline:2px solid #e4bd69}.bc-seat.selected{background:#f0dfb4;color:#183e32}
.bc-dealer{display:flex;align-items:center;gap:14px;margin:16px 0;min-width:0}.bc-portrait{width:80px;height:120px;flex:0 0 80px;border:2px solid #e4bd69;border-radius:8px;background:url(/game-art/cards-blackjack-dealer.webp) center 22% / cover}
.bc-dealer-hand{min-width:0;flex:1}.bc-caption{font-size:12px;color:#e4d7ae;margin:5px 0}.bc-row{min-width:0;display:flex;gap:8px;overflow-x:auto;padding:4px 2px 10px}
.bc-card{position:relative;display:inline-block;flex:0 0 58px;width:58px;height:84px;background:#fffdf7;border:1px solid #b5b89a;border-radius:6px;font-weight:bold;color:#20322d;overflow:hidden}.bc-card.red{color:#b83146}
.bc-rank{position:absolute;left:5px;top:2px;font-size:15px}.bc-suit{position:absolute;inset:24px 0 0;text-align:center;font-size:29px}.bc-card.back{background:url(/game-art/cards-blackjack-dealer.webp) center 20% / cover}.bc-card.back span{position:absolute;left:0;right:0;bottom:0;background:#254d43;color:white;font-size:12px;text-align:center}
.bc-player-zone{display:flex;gap:15px;align-items:center;min-width:0;margin-top:15px}.bc-player-cards{min-width:0;flex:1}.bc-shoe{position:relative;flex:0 0 66px;width:66px;height:104px;border:2px solid #e4bd69;border-radius:7px;background:url(/game-art/cards-blackjack-dealer.webp) center 20% / cover;cursor:pointer;padding:0;color:white}.bc-shoe span{position:absolute;left:0;right:0;bottom:0;background:#102f2b;padding:4px 0;font-size:13px}
.bc-stop{flex:0 0 64px;width:64px;height:64px;border:4px double #4e5942;border-radius:50%;background:#f0dfb4;color:#183e32;font-weight:bold;cursor:pointer;padding:0;font-size:14px}.bc-stop:disabled,.bc-shoe:disabled{opacity:.55;cursor:default}.bc-result{color:#ffe195;font-weight:bold;margin:7px 0}
#gpanel:has(.bc-table) #glog{display:none}@media(max-width:440px){.bc-table{padding:10px}.bc-dealer{gap:8px}.bc-portrait{width:56px;height:94px;flex-basis:56px}.bc-shoe{width:57px;height:92px;flex-basis:57px}.bc-card{width:52px;height:76px;flex-basis:52px}.bc-stop{width:56px;height:56px;flex-basis:56px}.bc-seat{font-size:11px;padding:5px 8px}}
"""

WEB_JS = CARDS_PENDING_JS + r"""
    const node=(tag,cls,value)=>{const e=document.createElement(tag);e.className=cls||'';if(value!=null)e.textContent=value;return e;};
    const me=state.uid,origin=state.gst,roomId=state.groom,room=(state.gst||{}).room||{},member=(s.players||[]).includes(me)&&!(room.spectators||[]).includes(me)&&(room.players||s.players||[]).includes(me);
    const token=state.token,roomRound=room.round;
    const can=member&&s.game==='blackjack'&&s.status==='playing'&&s.current_uid===me&&room.status==='playing'&&room.game==='blackjack'&&room.room_id===roomId;
    const table=node('section','bc-table');table.dataset.game='blackjack';const heading=node('header','bc-header');
    heading.append(node('h3','','21点 · 翡翠牌厅'),node('b','',s.status==='round_end'?'本轮结算':can?'你来决定':'等待 '+gnick(s.current_uid)));table.append(heading);
    let selected=member?me:(s.players||[])[0];const privateFrame=state.gpriv;
    const pending=cardPendingFor('blackjack',{uid:me,roomId,round:roomRound,publicFrame:s,privateFrame});
    const stillCurrent=()=>can&&table.isConnected&&state.token===token&&state.uid===me&&state.gst===origin&&state.gst.room===room&&room.round===roomRound&&room.room_id===roomId&&room.game==='blackjack'&&room.status==='playing'&&(room.players||[]).includes(me)&&!(room.spectators||[]).includes(me)&&s.game==='blackjack'&&s.status==='playing'&&s.current_uid===me&&(s.players||[]).includes(me)&&state.groom===roomId&&(state.gst||{}).state===s&&state.gpriv===privateFrame;
    const view=pending.attach(table,stillCurrent);
    const send=action=>{if(!stillCurrent())return;pending.submit(()=>gameAPI('action',{room_id:roomId,action}));};
    function card(label){const back=label==='背牌';const e=node('div','bc-card'+(back?' back':/[♥♦]$/.test(label)?' red':''));e.setAttribute('role','img');e.setAttribute('aria-label',back?'庄家暗牌':label);
      if(back)e.append(node('span','','暗牌'));else{e.append(node('span','bc-rank',label.slice(0,-1)),node('span','bc-suit',label.slice(-1)));}return e;}
    const seats=node('div','bc-seats'),player=node('div','bc-player-cards'),buttons=new Map();
    const names={win:'胜 +1',lose:'负',push:'平',blackjack:'21点'};
    function show(uid){selected=uid;player.replaceChildren();for(const [id,b] of buttons){b.classList.toggle('selected',id===uid);b.style.background=id===uid?'#f0dfb4':'#286b58';b.style.color=id===uid?'#183e32':'#ffffff';}
      const value=(s.hand_values||{})[uid]||0,result=(s.results||{})[uid];
      player.append(node('div','bc-caption',(uid===me?'我的手牌':gnick(uid)+'的明牌')+' · '+value+' 点'));
      if(result)player.append(node('div','bc-result',names[result]||result));else if(value>21)player.append(node('div','bc-result','爆牌'));else if((s.stand||[]).includes(uid))player.append(node('div','bc-caption','已停牌'));
      const hand=node('div','bc-row');hand.setAttribute('aria-label','玩家手牌');for(const label of (s.hands||{})[uid]||[])hand.append(card(label));player.append(hand);}
    for(const uid of s.players||[]){const b=node('button','bc-seat'+(s.current_uid===uid?' current':''),(uid===me?'我':gnick(uid))+' · '+((s.scores||{})[uid]||0)+'分');
      b.type='button';b.dataset.player=String(uid);b.onclick=()=>show(uid);b.style.background='#286b58';b.style.color='#ffffff';seats.append(b);buttons.set(uid,b);}table.append(seats);
    const dealer=node('div','bc-dealer'),portrait=node('div','bc-portrait');portrait.setAttribute('role','img');portrait.setAttribute('aria-label','原创翡翠牌厅发牌师');
    const dealerHand=node('div','bc-dealer-hand');dealerHand.append(node('div','bc-caption','庄家 · '+(s.dealer_hidden?'明牌 ':'合计 ')+(s.dealer_value||0)+' 点'));
    const dealerCards=node('div','bc-row');dealerCards.setAttribute('aria-label','庄家牌');for(const label of s.dealer||[])dealerCards.append(card(label));dealerHand.append(dealerCards);
    const shoe=node('button','bc-shoe');shoe.type='button';view.watch(shoe,can);shoe.dataset.action='hit';shoe.setAttribute('aria-label','从牌靴要牌');
    shoe.style.background='#102f2b url(/game-art/cards-blackjack-dealer.webp) center 20% / cover';shoe.append(node('span','','要牌 · '+(s.deck_remaining==null?'?':s.deck_remaining)));shoe.onclick=()=>send({action:'hit'});
    dealer.append(portrait,dealerHand,shoe);table.append(dealer);
    const zone=node('div','bc-player-zone'),stop=node('button','bc-stop','停牌');stop.type='button';stop.dataset.action='stand';view.watch(stop,can);stop.setAttribute('aria-label','放下停牌标记');
    stop.style.background='#f0dfb4';stop.style.color='#183e32';stop.style.borderRadius='50%';stop.style.border='4px double #4e5942';stop.onclick=()=>send({action:'stand'});zone.append(player,stop);table.append(zone);show(selected);
    table.append(node('div','bc-caption',s.status==='round_end'?'本轮已结算 · 等待下一轮':member?'点牌靴要牌，放下停牌标记结束行动':'旁观中 · 只能查看公开明牌'));box.append(table);view.refresh();
"""
