"""Atelier: real strokes, private prompt card and tangible paint tools."""
from boardgames.arcade_halloween import art,box,text,hit

ATLAS='arcade-atelier.webp'
COLORS=('#222222','#c93649','#e4b52c','#34805a','#3979bf','#9059b3')
WIDTHS=(2,5,10)
INK,PAPER,EDGE='#46415c','#f6eff8','#cbbbd5'


def member(st,ui):
    room=ui.get('room') or {};me=ui.get('me')
    members=room.get('players',st.get('players') or [int(k) for k in st.get('scores',{})] or [st.get('drawer_uid')])
    return me is not None and me in members and me not in room.get('spectators',[])


def can_draw(st,ui):
    return (member(st,ui) and ui.get('connected',True) is not False
            and (ui.get('room') or {}).get('status','playing')=='playing'
            and st.get('status')=='drawing' and st.get('drawer_uid')==ui.get('me'))


def send_guess(ui,st,context,entry):
    if (ui.get('state') is not st or ui.get('_room_context')!=context
            or not member(st,ui) or st.get('drawer_uid')==ui.get('me')
            or st.get('status')!='drawing' or ui.get('connected',True) is False):return
    value=entry.get().strip()
    if 0<len(value)<=30:
        ui['submit']({'guess':value});entry.delete(0,'end')
    return 'break'


def paint(cv,st,me,nick,submit,repaint,ui,priv,w,h):
    context=(ui.get('_room_context'),st.get('round'),st.get('drawer_uid'))
    if ui.get('atelier_context')!=context:
        ui.pop('dg_last',None);ui['atelier_context']=context
        entry=getattr(cv,'_atelier_entry',None)
        if entry is not None and isinstance(getattr(cv,'_w',None),str):entry.delete(0,'end')
    ui['atelier_hits']=[];drawing=can_draw(st,ui);own=member(st,ui) and me==st.get('drawer_uid')
    box(cv,(0,0,w,h),PAPER,PAPER);box(cv,(0,0,w,78),'#e6dcef',EDGE)
    art(cv,ATLAS,0 if own else 1,2,2,(10,8,72,70))
    text(cv,82,20,'光影画社 / 你画我猜',12,INK,bold=True)
    text(cv,82,42,'画手 '+nick(st.get('drawer_uid'))+' · 第 '+str(st.get('round',1))+' 轮',9,INK)
    if st.get('status')=='round_end':label='答案：'+str(st.get('word') or '')+' · '+('猜中 +1分' if st.get('guessed_by') is not None else '本轮结束')
    elif own:label='你的词卡：'+str((priv or {}).get('word') or '等待私密词卡')
    else:label='旁观画板' if not member(st,ui) else '看画猜词 · 答案仅画手可见'
    text(cv,82,63,label,9,'#81528e',width=w-92)
    top,bottom=88,h-100;scale=max(.05,min((w-24)/400,(bottom-top)/300));dw,dh=400*scale,300*scale
    ox,oy=(w-dw)/2,top+max(0,(bottom-top-dh)/2)
    ui['dg_map']=(ox,oy,scale)
    box(cv,(ox-4,oy-4,ox+dw+4,oy+dh+4),'#dccba5','#ae976c',2)
    box(cv,(ox,oy,ox+dw,oy+dh),'#ffffff','#c1b590')
    for stroke in st.get('strokes') or []:
        if not isinstance(stroke,dict) or stroke.get('type')!='line':continue
        try:
            cv.create_line(ox+float(stroke['x1'])*scale,oy+float(stroke['y1'])*scale,
                           ox+float(stroke['x2'])*scale,oy+float(stroke['y2'])*scale,
                           fill=stroke.get('color') or '#222222',width=max(1,int(stroke.get('width') or 3)*scale),capstyle='round',tags='dg_ink')
        except (KeyError,TypeError,ValueError):continue
    y=h-81
    art(cv,ATLAS,2,2,2,(9,y-4,45,y+32),contain=True)
    for i,color in enumerate(COLORS):
        x=58+i*25;selected=ui.get('dg_color',COLORS[0])==color
        cv.create_oval(x-10,y+2,x+10,y+22,fill=color,outline='#9b6baf' if selected else '#ffffff',width=3 if selected else 1)
        if drawing:ui['atelier_hits'].append((x-12,y,x+12,y+25,'color',color))
    for i,width in enumerate(WIDTHS):
        x=w-111+i*20;r=width/2
        cv.create_oval(x-r,y+13-r,x+r,y+13+r,fill=INK,outline=INK)
        if ui.get('dg_width',5)==width:cv.create_oval(x-8,y+5,x+8,y+21,outline='#9b6baf',width=2)
        if drawing:ui['atelier_hits'].append((x-9,y,x+9,y+26,'width',width))
    art(cv,ATLAS,3,2,2,(w-47,y-4,w-11,y+32),contain=True)
    if drawing:ui['atelier_hits'].append((w-50,y-4,w-8,y+33,'clear',None))
    text(cv,14,h-36,'画笔颜色 / 粗细 / 擦净' if drawing else '积分 '+ '  '.join(nick(int(u))+' '+str(s) for u,s in st.get('scores',{}).items()),8,INK,width=w-20)
    guessing=member(st,ui) and not own and st.get('status')=='drawing' and ui.get('connected',True) is not False
    if guessing and isinstance(getattr(cv,'_w',None),str):
        entry=getattr(cv,'_atelier_entry',None)
        if entry is None:
            import tkinter as tk
            entry=cv._atelier_entry=tk.Entry(cv,font=('Microsoft YaHei UI',10))
        context=ui.get('_room_context');callback=lambda e=None:send_guess(ui,st,context,entry)
        entry.bind('<Return>',callback)
        cv.create_window(12,h-16,anchor='w',width=max(50,w-82),height=25,window=entry)
        box(cv,(w-64,h-29,w-12,h-3),'#80528e','#67417c')
        text(cv,w-38,h-16,'猜词',9,'#ffffff','center',True)
        ui['atelier_hits'].append((w-64,h-29,w-12,h-3,'guess',callback))
    else:
        recent=(st.get('guess_log') or [])[-1:]
        text(cv,14,h-15,('最近猜词：'+recent[0]['text'] if recent else '在白色画布按住拖动绘画' if drawing else '等待下一幅作品'),8,'#817187',width=w-24)


def click(ui,x,y):
    st=ui.get('state') or {}
    for rect in ui.get('atelier_hits',[]):
        if not hit(rect[:4],x,y):continue
        kind,value=rect[4:]
        if kind=='guess':value();return
        if not can_draw(st,ui):return
        if kind=='color':ui['dg_color']=value;ui['repaint']()
        elif kind=='width':ui['dg_width']=value;ui['repaint']()
        elif kind=='clear':ui['submit']({'clear':True})
        return


WEB_JS=r"""
const AtelierTable=(()=>{
 const colors=['#222222','#c93649','#e4b52c','#34805a','#3979bf','#9059b3'];
 function el(tag,cls,label){const e=document.createElement(tag);e.className=cls||'';if(label!=null)e.textContent=label;return e;}
 function art(i,label){const e=el('span','atelier-art');e.style.backgroundPosition=(i%2*100)+'% '+(Math.floor(i/2)*100)+'%';e.setAttribute('role','img');e.setAttribute('aria-label',label);return e;}
 function member(s){const r=state.gst&&state.gst.room||{};return (r.players||Object.keys(s.scores||{}).map(Number)).includes(state.uid)&&!(r.spectators||[]).includes(state.uid);}
 function current(s,context,expectedRoom){const r=state.gst&&state.gst.room||{};return state.gst&&r===expectedRoom&&state.gst.state===s&&JSON.stringify([state.groom,r.round,state.uid,state.token])===context&&r.status==='playing'&&member(s)&&s.status==='drawing';}
 function render(box,s){
  const r=state.gst&&state.gst.room||{},context=JSON.stringify([state.groom,r.round,state.uid,state.token]),own=member(s)&&s.drawer_uid===state.uid,can=current(s,context,r)&&own;
  const root=el('section','atelier-table'),head=el('div','atelier-head'),labels=el('div');head.append(art(own?0:1,own?'画手':'赏画者'));labels.append(el('h3','','光影画社 / 你画我猜'),el('p','','画手 '+gnick(s.drawer_uid)+' · 第 '+s.round+' 轮'),el('b','',s.status==='round_end'?'答案：'+(s.word||''):own?'你的词卡：'+((state.gpriv||{}).word||'等待私密词卡'):member(s)?'看画猜词 · 答案仅画手可见':'旁观画板'));head.append(labels);root.append(head);
  const cv=el('canvas','atelier-canvas');cv.width=400;cv.height=300;cv.setAttribute('aria-label','可作画的400乘300画布');root.append(cv);const ctx=cv.getContext('2d');ctx.lineCap='round';
  function line(k){ctx.beginPath();ctx.moveTo(k.x1,k.y1);ctx.lineTo(k.x2,k.y2);ctx.strokeStyle=k.color||'#222222';ctx.lineWidth=k.width||5;ctx.stroke();}
  (s.strokes||[]).filter(k=>k&&k.type==='line').forEach(line);
  const tools=el('div','atelier-tools');tools.append(art(2,'调色盘与画笔'));
  colors.forEach(color=>{const b=el('button','atelier-color');b.type='button';b.style.background=color;b.dataset.color=color;b.setAttribute('aria-label','画笔颜色 '+color);b.setAttribute('aria-pressed',String((state.atelierColor||colors[0])===color));b.disabled=!can;b.onclick=()=>{if(current(s,context,r)&&own){state.atelierColor=color;renderGamePanel();}};tools.append(b);});
  const widths=el('span','atelier-widths');[2,5,10].forEach(width=>{const b=el('button','atelier-width'),dot=el('i');dot.style.width=dot.style.height=width+'px';b.type='button';b.dataset.width=width;b.setAttribute('aria-label','画笔粗细 '+width);b.setAttribute('aria-pressed',String((state.atelierWidth||5)===width));b.disabled=!can;b.append(dot);b.onclick=()=>{if(current(s,context,r)&&own){state.atelierWidth=width;renderGamePanel();}};widths.append(b);});tools.append(widths);
  const clear=el('button','atelier-clear');clear.type='button';clear.setAttribute('aria-label','擦净画板');clear.append(art(3,'擦净布'));clear.disabled=!can;clear.onclick=()=>{if(current(s,context,r)&&own)gameAPI('action',{room_id:state.groom,action:{clear:true}});};tools.append(clear);root.append(tools);
  if(can){let last=null,pending=[];const point=e=>{const b=cv.getBoundingClientRect();return [Math.max(0,Math.min(400,Math.round((e.clientX-b.left)*400/b.width))),Math.max(0,Math.min(300,Math.round((e.clientY-b.top)*300/b.height)))];};cv.style.touchAction='none';cv.onpointerdown=e=>{if(!current(s,context,r))return;e.preventDefault();cv.setPointerCapture(e.pointerId);last=point(e);};cv.onpointermove=e=>{if(!last||!current(s,context,r))return;const [x,y]=point(e),k={type:'line',x1:last[0],y1:last[1],x2:x,y2:y,color:state.atelierColor||colors[0],width:state.atelierWidth||5};if(x!==last[0]||y!==last[1]){line(k);pending.push(k);}last=[x,y];};const flush=()=>{if(!last)return;last=null;if(current(s,context,r))for(const stroke of pending)gameAPI('action',{room_id:state.groom,action:{stroke}},true);pending=[];};cv.onpointerup=flush;cv.onpointercancel=flush;}
  if(current(s,context,r)&&!own){const form=el('form','atelier-guess'),input=el('input'),b=el('button','','猜词');input.type='text';input.maxLength=30;input.placeholder='写下你猜的词';input.setAttribute('aria-label','猜测的词');b.type='submit';form.append(input,b);form.onsubmit=e=>{e.preventDefault();if(!current(s,context,r)||own)return;const guess=input.value.trim();if(guess&&guess.length<=30){gameAPI('action',{room_id:state.groom,action:{guess}});input.value='';}};root.append(form);}
  const scores=el('p','atelier-scores');scores.textContent=Object.entries(s.scores||{}).map(([u,v])=>gnick(+u)+' '+v+'分').join(' · ');root.append(scores);
  const guesses=el('div','atelier-guesses');(s.guess_log||[]).slice(-3).forEach(g=>guesses.append(el('span','',gnick(g.uid)+'：'+g.text+(g.ok?' ✓':''))));root.append(guesses);box.append(root);
 }
 return {render};
})();
"""

WEB_CSS=r"""
#gmain:has(.atelier-table){max-height:calc(90vh - 145px)}.atelier-table{background:#f6eff8;color:#46415c;padding:12px;border:1px solid #cbbbd5;border-radius:10px}.atelier-art{display:block;aspect-ratio:1;background:url('/game-art/arcade-atelier.webp');background-size:200% 200%;flex-shrink:0}.atelier-head{display:flex;gap:10px;align-items:center;margin-bottom:12px}.atelier-head .atelier-art{width:68px;border-radius:6px}.atelier-head h3{margin:0;font-size:17px}.atelier-head p{font-size:11px;margin:7px 0}.atelier-head b{font-size:11px;color:#81528e}.atelier-canvas{display:block;width:100%;max-width:520px;height:auto;aspect-ratio:4/3;background:#fff;border:5px solid #dccba5;box-sizing:border-box;margin:auto;touch-action:pan-y}.atelier-tools{display:flex;gap:6px;align-items:center;justify-content:space-between;margin:10px 0}.atelier-tools>.atelier-art{width:35px}.atelier-widths{display:flex;align-items:center;gap:1px}.atelier-width i{display:block;background:#46415c;border-radius:50%}#gmain .atelier-color{width:21px;height:21px;min-width:21px;padding:0;border:1px solid #fff;border-radius:50%;box-shadow:none}#gmain .atelier-width{width:20px;height:25px;padding:0;border:0;background:transparent;box-shadow:none;display:grid;place-items:center;border-radius:3px}#gmain .atelier-color[aria-pressed=true],#gmain .atelier-width[aria-pressed=true]{outline:2px solid #9b6baf;outline-offset:2px}#gmain .atelier-clear{width:37px;height:37px;border:0;background:transparent;padding:0;box-shadow:none}.atelier-clear .atelier-art{width:100%}.atelier-tools button:disabled{cursor:default;opacity:.65}.atelier-guess{display:flex;gap:6px}.atelier-guess input{min-width:0;flex:1;padding:7px;border:1px solid #b99cc7;border-radius:4px}.atelier-guess button{font-size:11px;padding:6px 12px}.atelier-scores,.atelier-guesses{font-size:11px;margin:9px 0 0}.atelier-guesses{display:flex;flex-direction:column;gap:4px}.atelier-table button:focus-visible{outline:3px solid #9b6baf}@media(max-width:420px){.atelier-table{padding:8px}.atelier-head h3{font-size:15px}.atelier-tools{gap:3px}.atelier-tools>.atelier-art{width:30px}#gmain .atelier-color{width:19px;height:19px;min-width:19px}#gmain .atelier-width{width:17px}.atelier-head .atelier-art{width:58px}}
"""
