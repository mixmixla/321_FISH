"""UNO renderer body injected only in the existing UNO route."""
from boardgames.cards_pending_web import CARDS_PENDING_JS

WEB_CSS = r"""
.cu-table{min-width:0;max-width:100%;width:100%;background:#f6f3ef;color:#302e4d;padding:14px;border-radius:14px;font:14px 'Microsoft YaHei UI',sans-serif}
.cu-heading{display:flex;justify-content:space-between;gap:10px;align-items:center;margin:0 0 12px}.cu-heading h3{margin:0}
.cu-seats{display:flex;gap:7px;flex-wrap:wrap}.cu-seat{background:#e5e0ec;padding:5px 10px;border-radius:20px;font-size:12px}
.cu-seat.turn{outline:2px solid #a3752a}.cu-center{display:flex;justify-content:center;align-items:center;gap:25px;margin:18px 0}
.cu-pile{text-align:center}.cu-card{position:relative;display:inline-block;width:88px;height:132px;padding:4px;border:0;border-radius:9px;background:var(--cu-ink,#383650);box-shadow:0 3px 8px #302e4d30;vertical-align:top;overflow:hidden;color:#fff;font:700 14px 'Microsoft YaHei UI',sans-serif}
.cu-art{position:absolute;inset:4px 4px 27px;background:url(/game-art/cards-uno-dealer.webp) center 24% / cover;border-radius:6px}
.cu-value{position:absolute;top:5px;left:5px;padding:2px 4px;border-radius:3px;background:#fff;color:var(--cu-ink,#383650);font-size:12px}
.cu-label{position:absolute;bottom:4px;left:2px;right:2px;text-align:center}.cu-card:not(:disabled){cursor:pointer}.cu-card:disabled{opacity:1;cursor:default}
.cu-card.cu-locked{box-shadow:none;filter:saturate(.65)}.cu-card:focus-visible{outline:3px solid #e5a22e;outline-offset:3px}
.cu-card.cu-selected{outline:3px solid #dba441}.cu-hand{min-width:0;max-width:100%;display:flex;gap:10px;overflow-x:auto;padding:8px 3px 12px;scroll-snap-type:x proximity}.cu-hand .cu-card{flex:0 0 88px;scroll-snap-align:center}
.cu-caption{font-size:12px;color:#625a73;margin:8px 0}.cu-picker{padding:12px;background:#fff8e7;border:2px solid #c29649;border-radius:9px;margin:8px 0}
#gpanel:has(.cu-table) #glog{display:none}
.cu-colors{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.cu-color{min-height:44px;min-width:52px;border:0;border-radius:7px;font-weight:bold;color:white;padding:7px 14px;cursor:pointer}.cu-cancel{background:#e0dbe9;color:#302e4d}
@media(max-width:440px){.cu-table{padding:10px}.cu-card{width:76px;height:114px}.cu-hand .cu-card{flex-basis:76px}.cu-center{gap:18px}.cu-heading{font-size:12px}}
.cu-table{background:radial-gradient(ellipse at 50% 28%,#245d50,#143d34 80%);color:#fff2d2;border:3px solid #9c8654;box-shadow:inset 0 0 0 4px #234d40}
.cu-heading b{color:#f3d58b}.cu-seat{background:#275749;color:#f9edce}.cu-caption{color:#d9cc9f}.cu-center{position:relative;border:1px solid #497861;border-radius:50%;padding:12px 8px 18px;gap:22px}
.cu-dealer.cu-art{position:relative;inset:auto;flex:0 0 68px;width:68px;height:104px;border:2px solid #b29b62;border-radius:8px;background:url(/game-art/cards-uno-dealer.webp) center 25% / cover}
.cu-card{border:3px solid #fff5d4;box-shadow:2px 4px 5px #0b211b80;border-radius:9px;isolation:isolate}.cu-card:disabled{opacity:1}.cu-card.cu-locked{filter:none;box-shadow:2px 3px 4px #0b211b60}
.cu-corner{position:absolute;left:5px;top:0;font-size:20px;line-height:25px;color:white;text-shadow:1px 1px 0 #0003}.cu-corner.bottom{left:auto;top:auto;right:5px;bottom:0;transform:rotate(180deg)}
.cu-oval{position:absolute;inset:22% 12%;display:grid;place-items:center;background:#fff9e9;border-radius:50%;transform:rotate(-25deg);color:var(--cu-ink);font-size:43px;font-weight:900;line-height:1}
.cu-face-value{transform:rotate(25deg)}.cu-wild .cu-oval{background:conic-gradient(#c43848 0 25%,#e0b82f 25% 50%,#247759 50% 75%,#376dc6 75%);color:#fff;font-size:36px;border:1px solid #fff9e9}
.cu-action-name{position:absolute;bottom:18px;left:0;right:0;text-align:center;color:white;font-size:10px}
.cu-back{border-color:#d4c38c}.cu-back-mark{position:absolute;inset:19px 16px 26px;background:#e8dcb5;transform:rotate(-20deg);border:2px solid #fff2bd;display:flex;align-items:center;justify-content:center;gap:2px}
.cu-back-bars{width:9px;height:34px;border:1px solid #fff}.cu-back .cu-label{color:#fff1c7}.cu-pile{position:relative}.cu-pile:before{content:'';position:absolute;inset:4px -4px 26px 5px;border:1px solid #a5b18e;border-radius:9px;background:#1b3a3a;transform:rotate(4deg)}
.cu-hand{border:1px solid #497861;background:#11382f;border-radius:14px;padding:22px 13px 16px;min-height:158px;align-items:flex-start}.cu-hand .cu-card{margin-right:-27px;transform:rotate(var(--cu-tilt,0deg));transform-origin:50% 90%;flex-shrink:0}.cu-hand .cu-card:last-child{margin-right:0}
.cu-hand .cu-card:hover,.cu-hand .cu-card:focus-visible,.cu-hand .cu-card.cu-selected{transform:translateY(-9px) rotate(0);z-index:10}.cu-hand.cu-fan-short{justify-content:center}.cu-picker{color:#302e4d}
@media(max-width:440px){.cu-center{gap:14px}.cu-dealer.cu-art{width:56px;flex-basis:56px;height:90px}.cu-corner{font-size:18px}.cu-oval{font-size:36px}.cu-wild .cu-oval{font-size:29px}.cu-hand{min-height:140px;padding-left:8px;padding-right:8px}.cu-hand .cu-card{margin-right:-23px}}
"""

WEB_JS = CARDS_PENDING_JS + r"""
    const node=(tag,cls,value)=>{const e=document.createElement(tag);e.className=cls||'';if(value!=null)e.textContent=value;return e;};
    const colors={red:['红','#c43848'],yellow:['黄','#e0b82f'],green:['绿','#247759'],blue:['蓝','#376dc6']};
    const me=state.uid,origin=state.gst,roomId=state.groom,room=(state.gst||{}).room||{},member=(s.players||[]).includes(me)&&!(room.spectators||[]).includes(me)
      &&(!room.players||(room.players||[]).includes(me));
    const token=state.token,roomRound=room.round;
    const can=member&&s.game==='uno'&&s.status==='playing'&&s.current_uid===me&&room.status==='playing'&&room.game==='uno'&&room.room_id===roomId;
    const pv=member?(state.gpriv||{}):{},labels=pv.hand||[],ids=pv.hand_ids||[];
    const valid=Array.isArray(labels)&&Array.isArray(ids)&&labels.length===ids.length&&new Set(ids).size===ids.length
      &&ids.every(id=>Number.isInteger(id)&&id>=0&&id<108)&&labels.every(v=>typeof v==='string');
    const root=node('section','cu-table'),heading=node('header','cu-heading');root.dataset.game='uno';
    heading.append(node('h3','','UNO · 四色牌宴'),node('b','',can?'你来出牌':member?'等待 '+gnick(s.current_uid):'旁观中'));root.append(heading);
    const seats=node('div','cu-seats');for(const uid of s.players||[]){const seat=node('span','cu-seat'+(s.current_uid===uid?' turn':''),
      (uid===me?'我':gnick(uid))+' · '+((s.hand_counts||{})[uid]||0)+' 张 · '+((s.scores||{})[uid]||0)+' 分');seats.append(seat);}root.append(seats);
    const pending=cardPendingFor('uno',{uid:me,roomId,round:roomRound,publicFrame:s,privateFrame:state.gpriv});
    let picker=null;
    const stillCurrent=()=>{const latest=(state.gst||{}).state;return can&&root.isConnected&&state.token===token&&state.gst===origin&&state.gst.room===room&&room.round===roomRound&&room.room_id===roomId&&room.game==='uno'&&room.status==='playing'&&(room.players||[]).includes(me)&&!(room.spectators||[]).includes(me)&&s.game==='uno'&&s.status==='playing'&&s.current_uid===me&&(s.players||[]).includes(me)&&state.groom===roomId&&(!latest||latest===s)&&state.uid===me&&(!state.gpriv||state.gpriv===pv);};
    const view=pending.attach(root,stillCurrent);
    const send=action=>{if(!stillCurrent())return;pending.submit(()=>{
      if(picker)picker.remove();return gameAPI('action',{room_id:roomId,action});});};
    function card(label,enabled,back){
      const c=node('button','cu-card');c.type='button';view.watch(c,enabled);c.setAttribute('aria-label',back?'摸一张牌':label);
      const color=Object.values(colors).find(v=>label.startsWith(v[0]));c.style.setProperty('--cu-ink',color?color[1]:'#383650');
      // Rule colors must outrank the app theme's general button decoration.
      c.style.background=color?color[1]:'#383650';c.style.color='#ffffff';c.style.opacity='1';
      if(back){c.classList.add('cu-back');c.style.background='#182b46';const mark=node('span','cu-back-mark');
        for(const [,ink] of Object.values(colors)){const bar=node('i','cu-back-bars');bar.style.background=ink;mark.append(bar);}c.append(mark,node('span','cu-label','摸牌'));}
      else{const value=color?label.slice(1):label,symbol=({'跳过':'⊘','反转':'⇄','万能':'✦','万能+4':'+4'})[value]||value;
        if(!color)c.classList.add('cu-wild');const oval=node('span','cu-oval');oval.append(node('b','cu-face-value',symbol));
        c.append(oval,node('b','cu-corner',symbol),node('b','cu-corner bottom',symbol));
        if(!/^\d+$/.test(value))c.append(node('small','cu-action-name',value));}
      return c;
    }
    const center=node('div','cu-center'),drawPile=node('div','cu-pile'),topPile=node('div','cu-pile');
    const draw=card('摸牌',can,true);draw.dataset.action='draw';draw.onclick=()=>send({draw:true});
    drawPile.append(draw,node('div','cu-caption','牌堆 '+(s.deck_remaining==null?'?':s.deck_remaining)));
    const color=colors[s.top_color]||['?','#383650'];
    topPile.append(card(s.top||'?',false,false),node('div','cu-caption','当前 '+color[0]+'色 '+(s.direction||'→')));
    const dealer=node('div','cu-dealer cu-art');dealer.setAttribute('role','img');dealer.setAttribute('aria-label','桌边原创牌宴发牌师');
    center.append(dealer,drawPile,topPile);root.append(center);
    root.append(node('div','cu-caption',member?'你的真实手牌 · 点牌出牌，万能牌再选颜色':'旁观只显示公开牌数'));
    const hand=node('div','cu-hand'+(labels.length<=6?' cu-fan-short':''));hand.setAttribute('aria-label','你的手牌');
    if(valid)labels.forEach((label,i)=>{
      const id=ids[i],legal=!Array.isArray(pv.playable_ids)||pv.playable_ids.includes(id),c=card(label,can&&legal,false);
      c.dataset.cardId=String(id);if(!can||!legal)c.classList.add('cu-locked');
      c.style.setProperty('--cu-tilt',Math.max(-7,Math.min(7,(i-(labels.length-1)/2)*2))+'deg');
      c.title=label+(can?(legal?' · 点击出牌':' · 当前不能出'):' · 等待你的回合');
      c.onclick=()=>{
        if(!stillCurrent()||pending.isPending())return;
        if(!label.startsWith('万能')){send({card:id});return;}
        if(picker)picker.remove();hand.querySelectorAll('.cu-selected').forEach(e=>e.classList.remove('cu-selected'));c.classList.add('cu-selected');
        picker=node('div','cu-picker');picker.setAttribute('role','group');picker.setAttribute('aria-label','万能牌选颜色');
        picker.append(node('b','','万能牌 · 选择下一种颜色'));const row=node('div','cu-colors');
        for(const [key,[name,ink]] of Object.entries(colors)){const b=node('button','cu-color',name);b.type='button';b.style.background=ink;
          if(key==='yellow')b.style.color='#302e4d';b.dataset.color=key;view.watch(b,can);b.onclick=()=>send({card:id,color:key});row.append(b);}
        const cancel=node('button','cu-color cu-cancel','取消');cancel.type='button';cancel.onclick=()=>{picker.remove();picker=null;c.classList.remove('cu-selected');};
        row.append(cancel);picker.append(row);root.append(picker);view.refresh();picker.querySelector('button').focus();
      };hand.append(c);
    });root.append(hand);
    if(s.winner_uid!=null)root.append(node('b','',gnick(s.winner_uid)+' 出完手牌'+(s.match_winner!=null?' · 比赛冠军':'')));
    box.append(root);view.refresh();
"""
