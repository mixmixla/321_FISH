"""Four illustrated value cards and a tactile expression workbench."""
import re
from collections import Counter
from boardgames.arcade_halloween import art,box,text,hit

ATLAS='arcade-math.webp'
PAPER,INK,GREEN,GOLD='#f5edda','#253e4c','#3d695a','#b79656'
TOKENS=('+','-','*','/','(',')','⌫','C')


def allowed(st,ui):
    r=ui.get('room') or {};me=ui.get('me')
    return (ui.get('connected',True) is not False and me in r.get('players',st.get('players',[]))
            and me not in r.get('spectators',[]) and r.get('status','playing')=='playing'
            and st.get('status')=='answering' and st.get('solved_uid') is None)


def expression(ui):
    e=ui.get('calc_entry')
    value=e.get() if e is not None else ui.get('calc_expr','')
    if value!=ui.get('calc_generated',''):ui['calc_picked']=[]
    ui['calc_expr']=value
    return value


def used(cards,expr,picked=()):
    counts=Counter(int(n) for n in re.findall(r'\d+',expr));out=set()
    for i in list(picked)+list(range(len(cards))):
        if i not in out and i<len(cards) and counts[cards[i]]>0:out.add(i);counts[cards[i]]-=1
    return out


def edit(ui,value):
    ui['calc_expr']=ui['calc_generated']=value
    e=ui.get('calc_entry')
    if e is not None:e.delete(0,'end');e.insert(0,value)
    ui.get('repaint',lambda:None)()


def send(ui,st,context):
    if ui.get('state') is not st or ui.get('_room_context')!=context or not allowed(st,ui):return
    value=expression(ui).strip()
    if value:ui['submit']({'expr':value})
    return 'break'


def paint(cv,st,me,nick,submit,repaint,ui,priv,w,h):
    ctx=(ui.get('_room_context'),st.get('round'),me)
    real=isinstance(getattr(cv,'_w',None),str)
    if ui.get('calc_context')!=ctx:
        ui.update(calc_context=ctx,calc_expr='',calc_generated='',calc_picked=[])
        if ui.get('calc_entry') is not None:ui['calc_entry'].delete(0,'end')
    ui['calc_hits']=[];on=allowed(st,ui);expr=expression(ui);cards=st.get('cards') or [];taken=used(cards,expr,ui.get('calc_picked',()))
    box(cv,(0,0,w,h),PAPER,PAPER);box(cv,(0,0,w,52),INK,INK)
    text(cv,14,18,'星算社 / 24点',14,PAPER,bold=True)
    label='最终结算' if st.get('status')=='ended' else ('答对！ '+str(st.get('win_expr') or '')+' = 24' if st.get('solved_uid') is not None else '第 '+str(st.get('round',1))+' 轮 · 余 '+str(st.get('wait',0))+' 秒')
    text(cv,14,40,label,9,'#dec99b')
    members=st.get('players') or [];sw=(w-24)/max(1,len(members))
    for i,u in enumerate(members):
        score=(st.get('scores') or {}).get(u,(st.get('scores') or {}).get(str(u),0))
        text(cv,12+i*sw,68,nick(u)[:7]+('·我' if u==me else '')+' '+str(score)+'分',9,GREEN if u==me else INK,bold=u==me)
    cw=min(166,(w-30)/4-6);top=87;ch=min(cw+22,h-220)
    start=(w-4*cw-18)/2
    for i,value in enumerate(cards):
        x=start+i*(cw+6);y=top+(5 if i in taken else 0);rect=(x,y,x+cw,y+ch)
        box(cv,(x+2,y+3,x+cw+2,y+ch+3),'#c7b793','#c7b793')
        box(cv,rect,'#fffdf1',GREEN if i in taken else GOLD,3 if i in taken else 1)
        art(cv,ATLAS,i,2,2,(x+3,y+3,x+cw-3,y+ch-21))
        cv.create_oval(x+5,y+5,x+37,y+37,fill='#fff6db',outline=GOLD,width=2)
        text(cv,x+21,y+21,value,20,INK,'center',True)
        text(cv,x+cw/2,y+ch-10,'已用 ✓' if i in taken else '点击加入算式',8,GREEN if i in taken else INK,'center')
        if on and i not in taken:ui['calc_hits'].append((*rect,'card',i))
    fy=h-111
    text(cv,14,fy-18,'用四张牌各一次，四则运算凑出24',9,INK)
    if on and real:
        entry=getattr(cv,'_calc24_entry',None)
        if entry is None:
            import tkinter as tk
            entry=cv._calc24_entry=tk.Entry(cv,font=('Consolas',14),bg='#fffdf4',fg=INK,relief='flat')
        if ui.get('calc_entry') is not entry:
            ui['calc_entry']=entry;entry.delete(0,'end');entry.insert(0,expr)
        context=ui.get('_room_context');entry.bind('<Return>',lambda e:send(ui,st,context))
        cv.create_window(14,fy,anchor='w',height=30,width=w-104,window=entry)
    else:
        box(cv,(14,fy-16,w-89,fy+16),'#fffdf4',GOLD)
        text(cv,22,fy,st.get('win_expr') or expr or '…',14,INK)
    span=(w-110)/len(TOKENS)
    for i,token in enumerate(TOKENS):
        cx=14+(i+.5)*span;cy=h-52;r=min(18,span*.43)
        cv.create_oval(cx-r,cy-r,cx+r,cy+r,fill='#e3cf9d',outline='#ad8a4b',width=2)
        text(cv,cx,cy,{'*':'×','/':'÷'}.get(token,token),15,INK,'center',True)
        if on:ui['calc_hits'].append((cx-r,cy-r,cx+r,cy+r,'token',token))
    cx,cy=w-47,h-74
    cv.create_oval(cx-32,cy-32,cx+32,cy+32,fill='#a24958' if on else '#b6afa2',outline='#d5b879',width=3)
    text(cv,cx,cy,'24' if st.get('status')=='answering' else '✓',25,'#fff3d3','center',True)
    if on:ui['calc_hits'].append((cx-32,cy-32,cx+32,cy+32,'send',(st,ui.get('_room_context'))))
    text(cv,14,h-14,'点牌与运算筹片组合；也可直接输入表达式，Enter提交',8,'#7b806d')


def click(ui,x,y):
    st=ui.get('state') or {}
    if not allowed(st,ui):return
    for rect in ui.get('calc_hits',[]):
        if not hit(rect[:4],x,y):continue
        kind,value=rect[4:];expr=expression(ui)
        if kind=='card':
            cards=st.get('cards') or []
            if value in used(cards,expr,ui.get('calc_picked',())):return
            ui.setdefault('calc_picked',[]).append(value)
            edit(ui,expr+('*' if expr and (expr[-1].isdigit() or expr[-1]==')') else '')+str(cards[value]))
        elif kind=='token':edit(ui,'' if value=='C' else expr[:-1] if value=='⌫' else expr+value)
        elif kind=='send':send(ui,*value)
        return


WEB_JS=r"""
const MathTable=(()=>{
 function el(tag,cls,value){const e=document.createElement(tag);e.className=cls||'';if(value!=null)e.textContent=value;return e;}
 function active(s){const r=state.gst&&state.gst.room||{};return (r.players||s.players||[]).includes(state.uid)&&!(r.spectators||[]).includes(state.uid)&&r.status==='playing'&&s.status==='answering'&&s.solved_uid==null;}
 function used(cards,expr,picked){const counts={};for(const n of expr.match(/\d+/g)||[])counts[Number(n)]=(counts[Number(n)]||0)+1;const set=new Set();for(const i of [...picked,...cards.map((_,i)=>i)])if(!set.has(i)&&counts[cards[i]]>0){set.add(i);counts[cards[i]]--;}return set;}
 function render(box,s){
  const r=state.gst&&state.gst.room||{},context=JSON.stringify([state.groom,r.round,s.round,state.uid]);if(state.calcContext!==context){state.calcContext=context;state.calcExpr='';state.calcPicked=[];}const cards=s.cards||[],on=active(s),expr=state.calcExpr||'',picked=state.calcPicked||[],taken=used(cards,expr,picked);
  const captured={room:state.gst&&state.gst.room,round:state.gst&&state.gst.room&&state.gst.room.round,uid:state.uid,token:state.token,rid:state.groom};const sceneCurrent=()=>state.gst&&state.gst.room===captured.room&&state.gst.state===s&&state.gst.room.round===captured.round&&state.uid===captured.uid&&state.token===captured.token&&state.groom===captured.rid;
  const root=el('section','calc-table');root.append(el('h3','','星算社 / 24点'),el('p','calc-hint',s.solved_uid!=null?'答对！ '+s.win_expr+' = 24':s.status==='ended'?'最终结算':'第 '+s.round+' 轮 · 余 '+s.wait+' 秒'));
  const scores=el('div','calc-scores');(s.players||[]).forEach(u=>scores.append(el('span',u===state.uid?'mine':'',gnick(u)+(u===state.uid?'·我':'')+' '+((s.scores||{})[u]||0)+'分')));root.append(scores);
  let input;function current(){return sceneCurrent()&&active(s)&&context===state.calcContext;}
  function pull(){const value=input?input.value:state.calcExpr||'';if(value!==state.calcExpr)state.calcPicked=[];state.calcExpr=value;return value;}
  function update(value){state.calcExpr=value;renderGamePanel();}
  const row=el('div','calc-cards');cards.forEach((v,i)=>{const b=el('button','calc-card'+(taken.has(i)?' used':''));b.type='button';b.dataset.index=i;b.dataset.value=v;b.disabled=!on||taken.has(i);b.setAttribute('aria-label','数字牌 '+v+(taken.has(i)?' 已用':' 加入算式'));const image=el('span','calc-art');image.style.backgroundPosition=(i%2*100)+'% '+(Math.floor(i/2)*100)+'%';image.setAttribute('role','img');image.setAttribute('aria-label','星算社成员原画');b.append(image,el('b','calc-value',String(v)),el('small','',taken.has(i)?'已用 ✓':'点击加入算式'));b.onclick=()=>{if(!current())return;const value=pull();if(used(cards,value,state.calcPicked||[]).has(i))return;state.calcPicked=[...(state.calcPicked||[]),i];update(value+(/[\d)]$/.test(value)?'*':'')+v);};row.append(b);});root.append(row);
  root.append(el('p','calc-hint','四张牌各用一次，四则运算凑出24'));
  const form=el('form','calc-workbench'),work=el('div','calc-writing');input=el('input');input.type='text';input.value=expr;input.placeholder='点牌组合，或直接写表达式';input.setAttribute('aria-label','凑24的表达式');input.disabled=!on;input.oninput=()=>{state.calcExpr=input.value;state.calcPicked=[];};work.append(input);
  const tokens=el('div','calc-tokens');['+','-','*','/','(',')','⌫','C'].forEach(t=>{const b=el('button','calc-token',({'*':'×','/':'÷'})[t]||t);b.type='button';b.dataset.token=t;b.disabled=!on;b.setAttribute('aria-label',t==='⌫'?'撤回一字':t==='C'?'清空表达式':'运算 '+t);b.onclick=()=>{if(!current())return;const value=pull();update(t==='C'?'':t==='⌫'?value.slice(0,-1):value+t);};tokens.append(b);});work.append(tokens);
  const seal=el('button','calc-seal',s.status==='answering'?'24':'✓');seal.type='submit';seal.setAttribute('aria-label','提交表达式凑24');seal.disabled=!on;form.onsubmit=e=>{e.preventDefault();if(!current())return;const value=pull().trim();if(value)gameAPI('action',{room_id:state.groom,action:{expr:value}});};form.append(work,seal);root.append(form);
  if(s.win_expr)root.append(el('p','calc-result',gnick(s.solved_uid)+'：'+s.win_expr+' =24'));
  box.append(root);
 }
 return {render};
})();
"""

WEB_CSS=r"""
#gmain:has(.calc-table){max-height:calc(90vh - 145px)}.calc-table{background:#f5edda;color:#253e4c;padding:13px;border:1px solid #c8b384;border-radius:10px}.calc-table h3{font-size:18px;margin:0}.calc-hint{font-size:11px;color:#747858;margin:8px 0 12px}.calc-scores{display:flex;gap:10px;font-size:11px;flex-wrap:wrap;margin-bottom:15px}.calc-scores .mine{color:#3d695a;font-weight:700}.calc-cards{display:grid;grid-template-columns:repeat(4,1fr);gap:7px}#gmain .calc-card{position:relative;display:block;min-width:0;padding:3px;background:#fffdf1;color:#253e4c;border:1px solid #b79656;border-radius:3px;box-shadow:2px 3px 0 #c7b793;cursor:pointer;font:inherit}.calc-art{display:block;aspect-ratio:1;background:url('/game-art/arcade-math.webp');background-size:200% 200%}.calc-card small{display:block;font-size:9px;margin:6px 0}.calc-card .calc-value{position:absolute;top:7px;left:6px;background:#fff6db;border:2px solid #b79656;border-radius:50%;width:31px;height:31px;line-height:28px;font-size:22px;color:#253e4c}.calc-card.used{transform:translateY(5px);outline:2px solid #3d695a}.calc-card:disabled{cursor:default;opacity:1}.calc-workbench{display:flex;gap:10px;align-items:center;margin-top:12px}.calc-writing{flex:1;min-width:0}.calc-writing input{box-sizing:border-box;width:100%;font:17px Consolas,monospace;border:1px solid #b79656;border-radius:3px;background:#fffdf4;color:#253e4c;padding:7px 8px}.calc-tokens{display:flex;gap:4px;justify-content:space-between;margin-top:13px}#gmain .calc-token{width:29px;height:29px;padding:0;border:2px solid #ad8a4b;border-radius:50%;background:#e3cf9d;color:#253e4c;font-size:17px;box-shadow:0 2px 0 #b79a62;flex-shrink:0}#gmain .calc-seal{width:67px;height:67px;flex-shrink:0;border-radius:50%;border:3px double #d5b879;background:#a24958;color:#fff3d3;font-size:28px;padding:0;box-shadow:1px 3px 0 #73333e}.calc-seal:disabled{opacity:.5}.calc-result{font:15px Consolas,monospace;color:#3d695a}.calc-table button:focus-visible{outline:3px solid #3d695a;outline-offset:3px}@media(max-width:420px){.calc-table{padding:9px}.calc-cards{gap:5px}.calc-card .calc-value{width:25px;height:25px;line-height:23px;font-size:19px;top:4px;left:4px}.calc-card small{font-size:8px}.calc-workbench{gap:7px}#gmain .calc-seal{width:50px;height:50px;font-size:23px}#gmain .calc-token{width:25px;height:25px;font-size:14px}.calc-tokens{gap:2px}.calc-writing input{font-size:13px;padding:7px 4px}}
"""
